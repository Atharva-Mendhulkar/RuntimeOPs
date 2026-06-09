# Troubleshooting Runbook

This runbook outlines steps for diagnosing and resolving common operational issues in the Repository Intelligence Service.

---

## Common Issues

### 1. Ingestion Failures
- **Symptom**: Ingestion job remains in `PENDING` or transitions to `FAILED`.
- **Diagnosis**:
  1. Check PostgreSQL registry status for error logs in the `ingestion_jobs` table.
  2. Inspect Git fetcher logs to verify if credentials or git token expired.
  3. Ensure AST parser is not crashing on syntax errors: check if target file path has valid syntax for its detected language.
- **Resolution**:
  - Re-trigger ingestion with correct credentials or check disk storage on the repository checkout directory.

---

### 2. Database Connection Errors
- **Symptom**: REST health endpoint returns `degraded` or `unhealthy`.
- **Diagnosis**:
  - Check which database service has `unhealthy` status in `/health`.
  - Validate connection credentials and network policies to the database.
- **Resolution**:
  - **Neo4j**: Verify connection URI (`NEO4J_URI`) and that Neo4j database is accepting BOLT connections.
  - **Weaviate**: Ensure Weaviate instance is running and responds to its schema REST port.
  - **Redis**: Check connection limits and rate-limiter keys configuration.

---

### 3. JWT Auth Failures (401 / 403)
- **Symptom**: REST queries return `401 Unauthorized` or `403 Forbidden`.
- **Diagnosis**:
  - Verify if `Authorization: Bearer <token>` header is present.
  - Check expiration (`exp` claim) of the JWT token.
- **Resolution**:
  - Refresh or re-issue JWT token from the identity provider with correct scopes.
