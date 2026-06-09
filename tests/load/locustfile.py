"""
IBM Bob - Load Testing with Locust
Simulates realistic user load patterns for performance testing
"""

import random
from locust import HttpUser, task, between, events
from locust.exception import RescheduleTask


# ============================================================================
# Configuration
# ============================================================================

# Sample queries for load testing
SAMPLE_QUERIES = [
    "authentication middleware",
    "database connection pool",
    "error handling function",
    "API endpoint handler",
    "data validation logic",
    "logging utility",
    "configuration parser",
    "cache manager",
    "request handler",
    "response formatter",
    "user authentication",
    "session management",
    "rate limiting",
    "retry logic",
    "circuit breaker"
]

# Sample file paths
SAMPLE_FILES = [
    "src/main.py",
    "src/utils.py",
    "src/auth.py",
    "src/api/handlers.py",
    "src/db/connection.py",
    "src/middleware/auth.py",
    "src/services/user.py",
    "src/models/user.py",
    "src/config.py",
    "src/cache.py"
]

# Sample repository IDs
SAMPLE_REPOS = [
    "test/sample-repo",
    "test/sample-repo-2",
    "test/large-repo"
]


# ============================================================================
# Base User Class
# ============================================================================


class BobUser(HttpUser):
    """Base user class for Bob load testing"""
    
    wait_time = between(1, 3)  # Wait 1-3 seconds between tasks
    
    def on_start(self):
        """Login and get auth token"""
        # In production, this would authenticate with real credentials
        # For testing, we'll use a test token
        response = self.client.post(
            "/auth/login",
            json={
                "username": "test_user",
                "password": "test_password"
            },
            catch_response=True
        )
        
        if response.status_code == 200:
            self.token = response.json().get("access_token")
            self.headers = {"Authorization": f"Bearer {self.token}"}
            response.success()
        else:
            # If auth fails, use a mock token for testing
            self.token = "test_token_for_load_testing"
            self.headers = {"Authorization": f"Bearer {self.token}"}
            response.failure("Authentication failed, using mock token")
    
    @task(3)
    def semantic_search(self):
        """Perform semantic search (most common operation)"""
        query = random.choice(SAMPLE_QUERIES)
        repo_id = random.choice(SAMPLE_REPOS)
        
        with self.client.post(
            "/api/v1/search",
            json={
                "query": query,
                "repo_id": repo_id,
                "k": 10
            },
            headers=self.headers,
            catch_response=True,
            name="/api/v1/search"
        ) as response:
            if response.status_code == 200:
                results = response.json().get("results", [])
                if len(results) > 0:
                    response.success()
                else:
                    response.failure("No results returned")
            else:
                response.failure(f"Status code: {response.status_code}")
    
    @task(2)
    def get_dependencies(self):
        """Get dependency graph"""
        file_path = random.choice(SAMPLE_FILES)
        repo_id = random.choice(SAMPLE_REPOS)
        hops = random.choice([1, 2, 3])
        
        with self.client.get(
            "/api/v1/dependencies",
            params={
                "file_path": file_path,
                "repo_id": repo_id,
                "hops": hops,
                "direction": "both"
            },
            headers=self.headers,
            catch_response=True,
            name="/api/v1/dependencies"
        ) as response:
            if response.status_code == 200:
                graph = response.json().get("graph", {})
                if "nodes" in graph and len(graph["nodes"]) > 0:
                    response.success()
                else:
                    response.failure("Empty graph returned")
            else:
                response.failure(f"Status code: {response.status_code}")
    
    @task(1)
    def resolve_stack_trace(self):
        """Resolve stack trace"""
        repo_id = random.choice(SAMPLE_REPOS)
        
        # Sample stack trace
        stack_trace = f"""Traceback (most recent call last):
  File "{random.choice(SAMPLE_FILES)}", line 42, in main
    result = process_data(data)
  File "{random.choice(SAMPLE_FILES)}", line 15, in process_data
    return calculate(value)
ValueError: invalid value"""
        
        with self.client.post(
            "/api/v1/stack-trace/resolve",
            json={
                "trace": stack_trace,
                "repo_id": repo_id
            },
            headers=self.headers,
            catch_response=True,
            name="/api/v1/stack-trace/resolve"
        ) as response:
            if response.status_code == 200:
                frames = response.json().get("frames", [])
                if len(frames) > 0:
                    response.success()
                else:
                    response.failure("No frames resolved")
            else:
                response.failure(f"Status code: {response.status_code}")
    
    @task(1)
    def get_file_content(self):
        """Get file content"""
        file_path = random.choice(SAMPLE_FILES)
        repo_id = random.choice(SAMPLE_REPOS)
        
        with self.client.get(
            "/api/v1/file",
            params={
                "file_path": file_path,
                "repo_id": repo_id
            },
            headers=self.headers,
            catch_response=True,
            name="/api/v1/file"
        ) as response:
            if response.status_code == 200:
                content = response.json().get("content")
                if content:
                    response.success()
                else:
                    response.failure("No content returned")
            elif response.status_code == 404:
                # File not found is acceptable
                response.success()
            else:
                response.failure(f"Status code: {response.status_code}")
    
    @task(1)
    def get_blast_radius(self):
        """Get blast radius analysis"""
        files = random.sample(SAMPLE_FILES, k=min(3, len(SAMPLE_FILES)))
        repo_id = random.choice(SAMPLE_REPOS)
        
        with self.client.post(
            "/api/v1/blast-radius",
            json={
                "files": files,
                "repo_id": repo_id
            },
            headers=self.headers,
            catch_response=True,
            name="/api/v1/blast-radius"
        ) as response:
            if response.status_code == 200:
                result = response.json()
                if "impacted_files" in result:
                    response.success()
                else:
                    response.failure("No impacted files returned")
            else:
                response.failure(f"Status code: {response.status_code}")
    
    @task(1)
    def health_check(self):
        """Health check endpoint"""
        with self.client.get(
            "/health/ready",
            catch_response=True,
            name="/health/ready"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status code: {response.status_code}")


# ============================================================================
# Specialized User Classes
# ============================================================================


class SearchHeavyUser(HttpUser):
    """User that primarily performs searches"""
    
    wait_time = between(0.5, 2)
    
    def on_start(self):
        """Setup"""
        self.token = "test_token"
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    @task(10)
    def semantic_search(self):
        """Perform semantic search"""
        query = random.choice(SAMPLE_QUERIES)
        repo_id = random.choice(SAMPLE_REPOS)
        
        self.client.post(
            "/api/v1/search",
            json={
                "query": query,
                "repo_id": repo_id,
                "k": 10
            },
            headers=self.headers,
            name="/api/v1/search [heavy]"
        )
    
    @task(1)
    def health_check(self):
        """Health check"""
        self.client.get("/health/ready", name="/health/ready [heavy]")


class GraphHeavyUser(HttpUser):
    """User that primarily queries dependency graphs"""
    
    wait_time = between(1, 4)
    
    def on_start(self):
        """Setup"""
        self.token = "test_token"
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    @task(10)
    def get_dependencies(self):
        """Get dependency graph"""
        file_path = random.choice(SAMPLE_FILES)
        repo_id = random.choice(SAMPLE_REPOS)
        hops = random.choice([2, 3, 4])  # More hops for graph-heavy users
        
        self.client.get(
            "/api/v1/dependencies",
            params={
                "file_path": file_path,
                "repo_id": repo_id,
                "hops": hops,
                "direction": "both"
            },
            headers=self.headers,
            name="/api/v1/dependencies [heavy]"
        )
    
    @task(1)
    def health_check(self):
        """Health check"""
        self.client.get("/health/ready", name="/health/ready [heavy]")


class BurstUser(HttpUser):
    """User that sends bursts of requests"""
    
    wait_time = between(5, 10)  # Long wait between bursts
    
    def on_start(self):
        """Setup"""
        self.token = "test_token"
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    @task
    def burst_requests(self):
        """Send a burst of requests"""
        num_requests = random.randint(5, 15)
        
        for _ in range(num_requests):
            query = random.choice(SAMPLE_QUERIES)
            repo_id = random.choice(SAMPLE_REPOS)
            
            self.client.post(
                "/api/v1/search",
                json={
                    "query": query,
                    "repo_id": repo_id,
                    "k": 5
                },
                headers=self.headers,
                name="/api/v1/search [burst]"
            )


# ============================================================================
# Event Handlers for Custom Metrics
# ============================================================================


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when test starts"""
    print("\n" + "="*80)
    print("Bob Load Test Starting")
    print("="*80)
    print(f"Target: {environment.host}")
    print(f"Users: {environment.runner.target_user_count if hasattr(environment.runner, 'target_user_count') else 'N/A'}")
    print("="*80 + "\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when test stops"""
    print("\n" + "="*80)
    print("Bob Load Test Complete")
    print("="*80)
    
    # Print summary statistics
    stats = environment.stats
    
    print("\nRequest Statistics:")
    print(f"  Total Requests: {stats.total.num_requests}")
    print(f"  Total Failures: {stats.total.num_failures}")
    print(f"  Failure Rate: {stats.total.fail_ratio:.2%}")
    print(f"  Average Response Time: {stats.total.avg_response_time:.0f}ms")
    print(f"  Median Response Time: {stats.total.median_response_time:.0f}ms")
    print(f"  95th Percentile: {stats.total.get_response_time_percentile(0.95):.0f}ms")
    print(f"  99th Percentile: {stats.total.get_response_time_percentile(0.99):.0f}ms")
    print(f"  Requests/sec: {stats.total.total_rps:.2f}")
    
    print("\nTop Endpoints by Request Count:")
    sorted_stats = sorted(
        stats.entries.values(),
        key=lambda x: x.num_requests,
        reverse=True
    )[:5]
    
    for stat in sorted_stats:
        print(f"  {stat.name}: {stat.num_requests} requests, "
              f"{stat.avg_response_time:.0f}ms avg, "
              f"{stat.fail_ratio:.2%} failure rate")
    
    print("="*80 + "\n")


# ============================================================================
# Custom Load Shapes
# ============================================================================


from locust import LoadTestShape


class StepLoadShape(LoadTestShape):
    """
    Step load pattern: gradually increase load in steps
    """
    
    step_time = 60  # Each step lasts 60 seconds
    step_load = 10  # Increase by 10 users each step
    spawn_rate = 5  # Spawn 5 users per second
    time_limit = 600  # Total test duration: 10 minutes
    
    def tick(self):
        run_time = self.get_run_time()
        
        if run_time > self.time_limit:
            return None
        
        current_step = run_time // self.step_time
        user_count = (current_step + 1) * self.step_load
        
        return (user_count, self.spawn_rate)


class SpikeLoadShape(LoadTestShape):
    """
    Spike load pattern: sudden increases in load
    """
    
    time_limit = 300  # 5 minutes
    
    def tick(self):
        run_time = self.get_run_time()
        
        if run_time > self.time_limit:
            return None
        
        # Create spikes every 60 seconds
        if run_time % 60 < 10:
            # Spike: 100 users
            return (100, 20)
        else:
            # Normal: 20 users
            return (20, 5)


class WaveLoadShape(LoadTestShape):
    """
    Wave load pattern: sinusoidal load variation
    """
    
    import math
    
    time_limit = 600  # 10 minutes
    min_users = 10
    max_users = 100
    
    def tick(self):
        run_time = self.get_run_time()
        
        if run_time > self.time_limit:
            return None
        
        # Calculate sinusoidal user count
        amplitude = (self.max_users - self.min_users) / 2
        offset = self.min_users + amplitude
        user_count = int(amplitude * self.math.sin(run_time / 60) + offset)
        
        return (user_count, 10)


# ============================================================================
# Usage Instructions
# ============================================================================

"""
Run load tests with different configurations:

1. Basic load test (default user mix):
   locust -f locustfile.py --host=http://localhost:8000

2. Web UI mode:
   locust -f locustfile.py --host=http://localhost:8000 --web-port=8089

3. Headless mode with specific user count:
   locust -f locustfile.py --host=http://localhost:8000 --headless -u 100 -r 10 -t 5m

4. Search-heavy workload:
   locust -f locustfile.py --host=http://localhost:8000 --headless -u 50 -r 5 --class-picker SearchHeavyUser

5. With step load shape:
   locust -f locustfile.py --host=http://localhost:8000 --headless --class-picker StepLoadShape

6. Generate HTML report:
   locust -f locustfile.py --host=http://localhost:8000 --headless -u 100 -r 10 -t 5m --html=report.html

Parameters:
  -u, --users: Number of concurrent users
  -r, --spawn-rate: Rate to spawn users (users per second)
  -t, --run-time: Test duration (e.g., 5m, 1h)
  --headless: Run without web UI
  --html: Generate HTML report
"""

# Made with Bob