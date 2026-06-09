-- IBM Bob - PostgreSQL Index Registry Schema
-- Version: 1.0.0
-- Date: May 16, 2026

-- Create index_registry table
CREATE TABLE IF NOT EXISTS index_registry (
    repo_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    github_url TEXT NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL CHECK (status IN ('idle', 'indexing', 'error', 'stale')),
    last_full_index TIMESTAMPTZ,
    last_incremental TIMESTAMPTZ,
    file_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    coverage_pct FLOAT DEFAULT 0.0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create repo_access table for RBAC
CREATE TABLE IF NOT EXISTS repo_access (
    id SERIAL PRIMARY KEY,
    repo_id UUID NOT NULL REFERENCES index_registry(repo_id) ON DELETE CASCADE,
    org_id VARCHAR(255) NOT NULL,
    granted_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(repo_id, org_id)
);

-- Create index_jobs table for tracking ingest jobs
CREATE TABLE IF NOT EXISTS index_jobs (
    job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id UUID NOT NULL REFERENCES index_registry(repo_id) ON DELETE CASCADE,
    job_type VARCHAR(20) NOT NULL CHECK (job_type IN ('full', 'incremental')),
    status VARCHAR(20) NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    files_processed INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX idx_index_registry_status ON index_registry(status);
CREATE INDEX idx_index_registry_github_url ON index_registry(github_url);
CREATE INDEX idx_repo_access_org_id ON repo_access(org_id);
CREATE INDEX idx_index_jobs_repo_id ON index_jobs(repo_id);
CREATE INDEX idx_index_jobs_status ON index_jobs(status);

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger for index_registry
CREATE TRIGGER update_index_registry_updated_at
    BEFORE UPDATE ON index_registry
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Insert sample data for development
INSERT INTO index_registry (github_url, status, file_count, coverage_pct)
VALUES 
    ('https://github.com/example/payment-api', 'idle', 150, 98.5),
    ('https://github.com/example/auth-service', 'idle', 85, 100.0)
ON CONFLICT (github_url) DO NOTHING;

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO bob;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO bob;