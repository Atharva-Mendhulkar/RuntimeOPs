# RuntimeOps - Repository Intelligence Agent

**Version:** 1.0.0  
**Status:** Development  
**Part of:** RuntimeOps Autonomous Incident Response Platform

---

## Overview

The Repository Intelligence Agent is at the core of RuntimeOps. It provides repository-wide semantic understanding, dependency analysis, and architectural intelligence to enable autonomous incident response workflows.

### Key Capabilities

- **Semantic Code Search**: Natural-language queries over entire codebases
- **Dependency Graph**: Service-to-service and file-to-file dependency tracing
- **Architecture Mapping**: Auto-generated service boundary diagrams and call graphs
- **Change Impact Analysis**: Predict affected services and tests from commit diffs
- **Root Cause Context**: Supply structured code context to incident response agents
- **Convention Extraction**: Detect patterns, naming standards, error handling norms

---

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- Poetry (for dependency management)
- 8GB RAM minimum, 16GB recommended

### Local Development Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd RuntimeOps
   ```

2. **Copy environment configuration**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Start infrastructure services**
   ```bash
   cd docker
   docker-compose up -d neo4j weaviate postgres redis jaeger prometheus grafana
   ```

4. **Install dependencies**
   ```bash
   poetry install
   ```

5. **Run database migrations**
   ```bash
   # PostgreSQL schema is auto-created via init-db.sql
   ```

6. **Start API**
   ```bash
   poetry run uvicorn bob.main:app --reload
   ```

7. **Verify installation**
   ```bash
   curl http://localhost:8000/health
   ```

### Using Docker Compose (Recommended)

```bash
cd docker
docker-compose up -d
```

This starts all services including the API.

**Access Points:**
- REST API: http://localhost:8000
- gRPC: localhost:50052
- Neo4j Browser: http://localhost:7474
- Weaviate: http://localhost:8080
- Grafana: http://localhost:3000 (admin/admin)
- Jaeger UI: http://localhost:16686
- Prometheus: http://localhost:9090

---

## Architecture

```
RuntimeOps/
├── src/
│   ├── ingestion/          # Repository cloning, parsing, indexing
│   ├── parsers/            # Tree-sitter language parsers
│   ├── graph/              # Neo4j graph operations
│   ├── semantic/           # Weaviate vector operations
│   ├── query/              # Query gateway and routing
│   ├── api/                # FastAPI + gRPC endpoints
│   ├── security/           # Authentication and encryption
│   ├── observability/      # OpenTelemetry tracing
│   ├── storage/            # Redis cache, PostgreSQL registry
│   └── tools/              # Agent-facing tool suite
├── tests/                  # Unit, integration, system tests
├── docs/                   # Documentation
├── docker/                 # Docker configurations
└── scripts/                # Utility scripts
```

---

## Development

### Running Tests

```bash
# Unit tests
poetry run pytest tests/unit -v

# Integration tests
poetry run pytest tests/integration -v

# All tests with coverage
poetry run pytest --cov=bob --cov-report=html

# Performance tests
poetry run locust -f tests/performance/locustfile.py
```

### Code Quality

```bash
# Format code
poetry run black src/ tests/
poetry run isort src/ tests/

# Lint
poetry run flake8 src/ tests/
poetry run mypy src/

# Security scan
poetry run bandit -r src/
```

### Pre-commit Hooks

```bash
# Install pre-commit hooks
poetry run pre-commit install

# Run manually
poetry run pre-commit run --all-files
```

---

## API Documentation

### REST API

Base URL: `http://localhost:8000/api/v1/bob/`

**Endpoints:**
- `POST /search` - Semantic code search
- `POST /resolve-stack-trace` - Resolve stack trace to files
- `GET /dependency-graph` - Retrieve dependency graph
- `POST /blast-radius` - Compute change impact
- `GET /file` - Fetch file content
- `GET /commit-diff` - Analyze commit diff
- `GET /health` - Service health check

**Interactive Docs:**
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### gRPC API

Port: `50052`

See `src/api/protos/` for service definitions.

---

## Configuration

Key environment variables (see `.env.example` for full list):

```bash
# Database connections
NEO4J_URI=bolt://localhost:7687
WEAVIATE_URL=http://localhost:8080
POSTGRES_HOST=localhost
REDIS_HOST=localhost

# LLM providers
OPENAI_API_KEY=your-key
LLM_PROVIDER=openai

# Security
JWT_SECRET_KEY=your-secret
ENCRYPTION_KEY=your-fernet-key

# Performance
MAX_CONCURRENT_INDEXING_JOBS=5
QUERY_TIMEOUT_SECONDS=10
```

---

## Monitoring

### Metrics

Prometheus metrics available at: `http://localhost:8000/metrics`

Key metrics:
- `bob_queries_total` - Total queries processed
- `bob_query_latency_seconds` - Query latency histogram
- `bob_ingest_jobs_total` - Total indexing jobs
- `bob_errors_total` - Error count

### Tracing

Distributed traces available in Jaeger: `http://localhost:16686`

### Dashboards

Grafana dashboards: `http://localhost:3000`

---

## Deployment

### Production Dockerfile

```bash
docker build -f docker/Dockerfile -t runtimeops:1.0.0 .
```

### Kubernetes

```bash
kubectl apply -f k8s/
```

See `docs/deployment/` for detailed deployment guides.

---

## Contributing

1. Create a feature branch from `develop`
2. Make changes following code style guidelines
3. Add tests for new functionality
4. Ensure all tests pass and coverage >80%
5. Submit pull request

See `CONTRIBUTING.md` for detailed guidelines.

---

## License

Proprietary - RuntimeOps Engineering

---

## Support

- **Documentation**: `docs/`
- **Issues**: GitHub Issues
- **Internal Slack**: #runtimeops-dev

---

## Roadmap

### v1.0 (Current)
- ✅ Multi-language parsing (Python, TS, Go, Java)
- ✅ Semantic code search
- ✅ Dependency graph analysis
- ✅ REST + gRPC APIs

### v1.1 (Planned)
- [ ] Kubernetes manifest analysis
- [ ] Infrastructure-as-Code support
- [ ] Cross-repository reasoning
- [ ] Enhanced security scanning

### v2.0 (Future)
- [ ] Real-time code intelligence
- [ ] Autonomous refactoring suggestions
- [ ] ML-based anomaly detection

---

*Repository Intelligence Agent v1.0.0 | RuntimeOps Engineering | May 2026*