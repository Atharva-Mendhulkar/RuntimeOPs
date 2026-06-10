"""
IBM Bob - Test Configuration and Fixtures
Comprehensive pytest fixtures for all test types
"""

import asyncio
import os
import time
from datetime import datetime, timedelta
from typing import Any, AsyncGenerator, Dict, List
from uuid import uuid4

import pytest

# Test containers
pytest_plugins = ["pytest_asyncio"]

# ============================================================================
# Session-Level Configuration
# ============================================================================


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def test_config() -> Dict[str, Any]:
    """Test configuration"""
    return {
        "postgres": {
            "host": os.getenv("TEST_POSTGRES_HOST", "localhost"),
            "port": int(os.getenv("TEST_POSTGRES_PORT", "5432")),
            "database": os.getenv("TEST_POSTGRES_DB", "bob_test"),
            "user": os.getenv("TEST_POSTGRES_USER", "bob_test"),
            "password": os.getenv("TEST_POSTGRES_PASSWORD", "test_password"),
        },
        "neo4j": {
            "uri": os.getenv("TEST_NEO4J_URI", "bolt://localhost:7687"),
            "user": os.getenv("TEST_NEO4J_USER", "neo4j"),
            "password": os.getenv("TEST_NEO4J_PASSWORD", "test_password"),
        },
        "redis": {
            "host": os.getenv("TEST_REDIS_HOST", "localhost"),
            "port": int(os.getenv("TEST_REDIS_PORT", "6379")),
            "db": int(os.getenv("TEST_REDIS_DB", "1")),
        },
        "weaviate": {
            "url": os.getenv("TEST_WEAVIATE_URL", "http://localhost:8080"),
        },
    }


# ============================================================================
# Database Fixtures
# ============================================================================


@pytest.fixture(scope="session")
async def postgres_container(test_config):
    """PostgreSQL test container"""
    try:
        from testcontainers.postgres import PostgresContainer

        with PostgresContainer("postgres:15") as postgres:
            # Update config with container details
            test_config["postgres"]["host"] = postgres.get_container_host_ip()
            test_config["postgres"]["port"] = int(postgres.get_exposed_port(5432))
            yield postgres
    except ImportError:
        # Fallback to local PostgreSQL if testcontainers not available
        yield None


@pytest.fixture(scope="session")
async def neo4j_container(test_config):
    """Neo4j test container"""
    try:
        from testcontainers.neo4j import Neo4jContainer

        with Neo4jContainer("neo4j:5.13") as neo4j:
            test_config["neo4j"]["uri"] = neo4j.get_connection_url()
            yield neo4j
    except ImportError:
        yield None


@pytest.fixture(scope="session")
async def redis_container(test_config):
    """Redis test container"""
    try:
        from testcontainers.redis import RedisContainer

        with RedisContainer("redis:7") as redis:
            test_config["redis"]["host"] = redis.get_container_host_ip()
            test_config["redis"]["port"] = int(redis.get_exposed_port(6379))
            yield redis
    except ImportError:
        yield None


@pytest.fixture(scope="session")
async def weaviate_container(test_config):
    """Weaviate test container"""
    try:
        from testcontainers.core.container import DockerContainer

        weaviate = DockerContainer("semitechnologies/weaviate:1.24.0")
        weaviate.with_exposed_ports(8080)
        weaviate.with_env("AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED", "true")
        weaviate.with_env("PERSISTENCE_DATA_PATH", "/var/lib/weaviate")

        with weaviate:
            test_config["weaviate"][
                "url"
            ] = f"http://{weaviate.get_container_host_ip()}:{weaviate.get_exposed_port(8080)}"
            yield weaviate
    except ImportError:
        yield None


@pytest.fixture
async def test_db(postgres_container, test_config):
    """Test database connection with cleanup"""
    import psycopg
    from psycopg.rows import dict_row

    config = test_config["postgres"]
    conn_string = f"postgresql://{config['user']}:{config['password']}@{config['host']}:{config['port']}/{config['database']}"  # noqa: E501

    async with await psycopg.AsyncConnection.connect(conn_string, row_factory=dict_row) as conn:
        # Create test tables
        async with conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS repositories (
                    id UUID PRIMARY KEY,
                    repo_id TEXT UNIQUE NOT NULL,
                    owner TEXT NOT NULL,
                    name TEXT NOT NULL,
                    default_branch TEXT,
                    indexed_at TIMESTAMP,
                    status TEXT
                )
            """)
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS index_jobs (
                    id UUID PRIMARY KEY,
                    repo_id UUID REFERENCES repositories(id),
                    status TEXT NOT NULL,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    error_message TEXT
                )
            """)
            await conn.commit()

        yield conn

        # Cleanup
        async with conn.cursor() as cur:
            await cur.execute("TRUNCATE TABLE index_jobs CASCADE")
            await cur.execute("TRUNCATE TABLE repositories CASCADE")
            await conn.commit()


@pytest.fixture
async def test_neo4j(neo4j_container, test_config):
    """Test Neo4j connection with cleanup"""
    from neo4j import AsyncGraphDatabase

    config = test_config["neo4j"]
    driver = AsyncGraphDatabase.driver(config["uri"], auth=(config["user"], config["password"]))

    yield driver

    # Cleanup
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")

    await driver.close()


@pytest.fixture
async def test_redis(redis_container, test_config):
    """Test Redis connection with cleanup"""
    import redis.asyncio as redis

    config = test_config["redis"]
    client = redis.Redis(
        host=config["host"], port=config["port"], db=config["db"], decode_responses=True
    )

    yield client

    # Cleanup
    await client.flushdb()
    await client.close()


@pytest.fixture
async def test_weaviate(weaviate_container, test_config):
    """Test Weaviate connection with cleanup"""
    import weaviate

    config = test_config["weaviate"]
    client = weaviate.Client(url=config["url"])

    # Create test schema
    schema = {
        "class": "CodeUnit",
        "vectorizer": "none",
        "properties": [
            {"name": "file_path", "dataType": ["text"]},
            {"name": "symbol_name", "dataType": ["text"]},
            {"name": "content", "dataType": ["text"]},
            {"name": "language", "dataType": ["text"]},
        ],
    }

    try:
        client.schema.create_class(schema)
    except Exception:
        pass  # Class might already exist

    yield client

    # Cleanup
    try:
        client.schema.delete_class("CodeUnit")
    except Exception:
        pass


# ============================================================================
# Mock Data Fixtures
# ============================================================================


@pytest.fixture
def sample_repository() -> Dict[str, Any]:
    """Sample repository data for testing"""
    return {
        "repo_id": "test/sample-repo",
        "owner": "test",
        "name": "sample-repo",
        "default_branch": "main",
        "files": [
            {
                "path": "src/main.py",
                "content": """def hello():
    '''Say hello'''
    return 'Hello, World!'

def goodbye():
    '''Say goodbye'''
    return 'Goodbye!'
""",
                "language": "python",
            },
            {
                "path": "src/utils.py",
                "content": """def calculate(value, divisor=1):
    '''Calculate result'''
    return value / divisor

def process_data(data):
    '''Process data'''
    result = calculate(data['value'])
    return result
""",
                "language": "python",
            },
            {
                "path": "src/auth.py",
                "content": """class AuthMiddleware:
    '''Authentication middleware'''

    def __init__(self, secret_key):
        self.secret_key = secret_key

    def authenticate(self, token):
        '''Authenticate user'''
        # Verify token
        return True
""",
                "language": "python",
            },
        ],
    }


@pytest.fixture
def large_repository() -> Dict[str, Any]:
    """Large repository for performance testing"""
    files = []
    for i in range(1000):
        files.append(
            {
                "path": f"src/module_{i}.py",
                "content": f"""def function_{i}():
    '''Function {i}'''
    return {i}

class Class_{i}:
    '''Class {i}'''

    def method_{i}(self):
        '''Method {i}'''
        return {i}
""",
                "language": "python",
            }
        )

    return {
        "repo_id": "test/large-repo",
        "owner": "test",
        "name": "large-repo",
        "default_branch": "main",
        "files": files,
    }


@pytest.fixture
def sample_code_units() -> List[Dict[str, Any]]:
    """Sample parsed code units"""
    return [
        {
            "file_path": "src/main.py",
            "type": "function",
            "name": "hello",
            "line_start": 1,
            "line_end": 3,
            "imports": [],
            "calls": [],
            "docstring": "Say hello",
        },
        {
            "file_path": "src/main.py",
            "type": "function",
            "name": "goodbye",
            "line_start": 5,
            "line_end": 7,
            "imports": [],
            "calls": [],
            "docstring": "Say goodbye",
        },
        {
            "file_path": "src/utils.py",
            "type": "function",
            "name": "calculate",
            "line_start": 1,
            "line_end": 3,
            "imports": [],
            "calls": [],
            "docstring": "Calculate result",
        },
        {
            "file_path": "src/utils.py",
            "type": "function",
            "name": "process_data",
            "line_start": 5,
            "line_end": 8,
            "imports": [],
            "calls": ["calculate"],
            "docstring": "Process data",
        },
    ]


@pytest.fixture
def sample_stack_trace() -> str:
    """Sample stack trace for testing"""
    return """Traceback (most recent call last):
  File "src/main.py", line 10, in <module>
    result = process_data({'value': 10})
  File "src/utils.py", line 7, in process_data
    result = calculate(data['value'])
  File "src/utils.py", line 2, in calculate
    return value / divisor
ZeroDivisionError: division by zero"""


@pytest.fixture
def sample_error_stack_trace() -> str:
    """Sample error stack trace with multiple frames"""
    return """Traceback (most recent call last):
  File "app.py", line 42, in main
    response = handle_request(request)
  File "handlers.py", line 15, in handle_request
    data = validate_input(request.data)
  File "validators.py", line 8, in validate_input
    schema.validate(data)
  File "schema.py", line 23, in validate
    raise ValidationError("Invalid data")
ValidationError: Invalid data"""


# ============================================================================
# API Test Client Fixtures
# ============================================================================


@pytest.fixture
async def test_client() -> AsyncGenerator:
    """FastAPI test client"""
    from httpx import AsyncClient

    from bob.main import app

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
def test_user() -> Dict[str, Any]:
    """Test user data"""
    return {
        "user_id": str(uuid4()),
        "username": "test_user",
        "email": "test@example.com",
        "scopes": ["repo:read", "repo:write", "index:trigger"],
    }


@pytest.fixture
def auth_headers(test_user) -> Dict[str, str]:
    """Authentication headers for API tests"""
    from bob.security.auth import create_access_token

    token = create_access_token(
        data={"sub": test_user["user_id"], "scopes": test_user["scopes"]},
        expires_delta=timedelta(hours=1),
    )

    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def limited_auth_headers() -> Dict[str, str]:
    """Limited authentication headers (read-only)"""
    from bob.security.auth import create_access_token

    token = create_access_token(
        data={"sub": str(uuid4()), "scopes": ["repo:read"]}, expires_delta=timedelta(hours=1)
    )

    return {"Authorization": f"Bearer {token}"}


# ============================================================================
# Performance Testing Fixtures
# ============================================================================


@pytest.fixture
def performance_tracker():
    """Track performance metrics during tests"""

    class PerformanceTracker:
        def __init__(self):
            self.metrics = []

        def record(self, operation: str, duration: float, **kwargs):
            """Record a performance metric"""
            self.metrics.append(
                {
                    "operation": operation,
                    "duration": duration,
                    "timestamp": datetime.utcnow().isoformat(),
                    **kwargs,
                }
            )

        def get_stats(self, operation: str = None):
            """Get statistics for recorded metrics"""
            metrics = self.metrics
            if operation:
                metrics = [m for m in metrics if m["operation"] == operation]

            if not metrics:
                return {}

            durations = [m["duration"] for m in metrics]
            return {
                "count": len(durations),
                "mean": sum(durations) / len(durations),
                "min": min(durations),
                "max": max(durations),
                "p50": sorted(durations)[len(durations) // 2],
                "p95": sorted(durations)[int(len(durations) * 0.95)],
                "p99": sorted(durations)[int(len(durations) * 0.99)],
            }

    return PerformanceTracker()


@pytest.fixture
def timer():
    """Simple timer context manager"""

    class Timer:
        def __init__(self):
            self.start_time = None
            self.end_time = None
            self.duration = None

        def __enter__(self):
            self.start_time = time.time()
            return self

        def __exit__(self, *args):
            self.end_time = time.time()
            self.duration = self.end_time - self.start_time

    return Timer


# ============================================================================
# Security Testing Fixtures
# ============================================================================


@pytest.fixture
def sql_injection_payloads() -> List[str]:
    """SQL injection test payloads"""
    return [
        "'; DROP TABLE users; --",
        "1' OR '1'='1",
        "admin'--",
        "' UNION SELECT * FROM users--",
        "1; DELETE FROM repositories WHERE 1=1--",
        "' OR 1=1--",
        "admin' OR '1'='1'--",
    ]


@pytest.fixture
def xss_payloads() -> List[str]:
    """XSS test payloads"""
    return [
        "<script>alert('XSS')</script>",
        "<img src=x onerror=alert('XSS')>",
        "<svg onload=alert('XSS')>",
        "javascript:alert('XSS')",
        "<iframe src='javascript:alert(\"XSS\")'></iframe>",
    ]


@pytest.fixture
def path_traversal_payloads() -> List[str]:
    """Path traversal test payloads"""
    return [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32",
        "....//....//....//etc/passwd",
        "..%2F..%2F..%2Fetc%2Fpasswd",
        "..%252F..%252F..%252Fetc%252Fpasswd",
    ]


# ============================================================================
# Chaos Engineering Fixtures
# ============================================================================


@pytest.fixture
def chaos_controller():
    """Controller for chaos engineering tests"""

    class ChaosController:
        def __init__(self):
            self.failures = []

        async def inject_latency(self, service: str, duration: float):
            """Inject latency into a service"""
            await asyncio.sleep(duration)

        async def kill_service(self, service: str):
            """Simulate service failure"""
            self.failures.append(service)

        async def restore_service(self, service: str):
            """Restore failed service"""
            if service in self.failures:
                self.failures.remove(service)

        def is_service_healthy(self, service: str) -> bool:
            """Check if service is healthy"""
            return service not in self.failures

    return ChaosController()


# ============================================================================
# Utility Fixtures
# ============================================================================


@pytest.fixture
def mock_github_api(mocker):
    """Mock GitHub API responses"""
    mock = mocker.patch("bob.ingestion.fetcher.GitHubFetcher")

    mock.return_value.fetch_repository.return_value = {
        "owner": "test",
        "name": "repo",
        "default_branch": "main",
        "files": [],
    }

    return mock


@pytest.fixture
def mock_llm_api(mocker):
    """Mock LLM API responses"""
    mock = mocker.patch("bob.semantic.embedder.Embedder")

    # Mock embedding generation
    mock.return_value.generate_embedding.return_value = [0.1] * 1536

    return mock


@pytest.fixture
async def cleanup_databases(test_db, test_neo4j, test_redis, test_weaviate):
    """Cleanup all databases after test"""
    yield

    # Cleanup is handled by individual fixtures
    pass


# Made with Bob
