-- IBM Bob - Security Schema
-- Database tables for authentication, authorization, and audit logging

-- Users table
CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(255) PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(100) UNIQUE NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'viewer',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMP,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);

-- API Keys table
CREATE TABLE IF NOT EXISTS api_keys (
    key_id VARCHAR(255) PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    hashed_secret TEXT NOT NULL,
    scopes TEXT[] NOT NULL,
    environment VARCHAR(10) NOT NULL CHECK (environment IN ('live', 'test')),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMP,
    expires_at TIMESTAMP,
    usage_count INTEGER NOT NULL DEFAULT 0,
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    revoked_at TIMESTAMP
);

CREATE INDEX idx_api_keys_user_id ON api_keys(user_id);
CREATE INDEX idx_api_keys_environment ON api_keys(environment);
CREATE INDEX idx_api_keys_revoked ON api_keys(revoked);

-- Organizations table
CREATE TABLE IF NOT EXISTS organizations (
    org_id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Organization members table
CREATE TABLE IF NOT EXISTS organization_members (
    org_id VARCHAR(255) NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
    user_id VARCHAR(255) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL DEFAULT 'member',
    joined_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (org_id, user_id)
);

CREATE INDEX idx_org_members_user_id ON organization_members(user_id);

-- Repositories table (extends existing)
CREATE TABLE IF NOT EXISTS repositories (
    repo_id VARCHAR(255) PRIMARY KEY,
    organization_id VARCHAR(255) REFERENCES organizations(org_id),
    name VARCHAR(255) NOT NULL,
    full_name VARCHAR(500) NOT NULL,
    is_public BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_repositories_org_id ON repositories(organization_id);
CREATE INDEX idx_repositories_is_public ON repositories(is_public);

-- Repository ACL (Access Control List)
CREATE TABLE IF NOT EXISTS repository_acl (
    user_id VARCHAR(255) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    repo_id VARCHAR(255) NOT NULL REFERENCES repositories(repo_id) ON DELETE CASCADE,
    action VARCHAR(20) NOT NULL CHECK (action IN ('read', 'write')),
    granted_at TIMESTAMP NOT NULL DEFAULT NOW(),
    granted_by VARCHAR(255) REFERENCES users(user_id),
    PRIMARY KEY (user_id, repo_id, action)
);

CREATE INDEX idx_repo_acl_user_id ON repository_acl(user_id);
CREATE INDEX idx_repo_acl_repo_id ON repository_acl(repo_id);

-- Audit logs table
CREATE TABLE IF NOT EXISTS audit_logs (
    log_id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    resource VARCHAR(500) NOT NULL,
    action VARCHAR(100) NOT NULL,
    result VARCHAR(20) NOT NULL CHECK (result IN ('success', 'failure', 'detected')),
    metadata JSONB,
    ip_address VARCHAR(45),
    user_agent TEXT,
    request_id VARCHAR(255),
    timestamp TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_event_type ON audit_logs(event_type);
CREATE INDEX idx_audit_logs_timestamp ON audit_logs(timestamp DESC);
CREATE INDEX idx_audit_logs_resource ON audit_logs(resource);
CREATE INDEX idx_audit_logs_request_id ON audit_logs(request_id);

-- Rate limit tier assignments
CREATE TABLE IF NOT EXISTS rate_limit_tiers (
    user_id VARCHAR(255) PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    tier VARCHAR(20) NOT NULL CHECK (tier IN ('free', 'developer', 'team', 'enterprise')),
    assigned_at TIMESTAMP NOT NULL DEFAULT NOW(),
    assigned_by VARCHAR(255) REFERENCES users(user_id)
);

-- Insert default admin user (password should be changed immediately)
INSERT INTO users (user_id, email, username, role, is_active)
VALUES 
    ('admin', 'admin@example.com', 'admin', 'admin', TRUE)
ON CONFLICT (user_id) DO NOTHING;

-- Insert default rate limit tier for admin
INSERT INTO rate_limit_tiers (user_id, tier)
VALUES ('admin', 'enterprise')
ON CONFLICT (user_id) DO NOTHING;

-- Made with Bob