"""
Locust load testing configuration for Dealership RAG API.
Run with: locust -f locustfile.py --host=http://localhost:8000
"""

from locust import HttpUser, task, between, events
import random
import json

# Sample queries from actual use cases
QUERIES = [
    "What low-mileage Toyota Camrys are in stock?",
    "Show me electric vehicles under $50k",
    "What are your financing options?",
    "When should I get an oil change?",
    "Do you have any SUVs with third-row seating?",
    "What is the warranty coverage?",
    "Tell me about the 2024 Ford F-150",
    "What are your hours of operation?",
    "Show me Honda Accord models",
    "What's the price range for trucks?"
]


class DealershipRAGUser(HttpUser):
    """Simulated user for load testing the RAG API."""
    
    wait_time = between(1, 3)  # 1-3 seconds between requests (realistic user behavior)
    
    @task(10)  # Weight: 10 (most common operation)
    def query_inventory(self):
        """Test query endpoint - inventory questions."""
        self.client.post(
            "/api/query",
            json={
                "query": random.choice(QUERIES),
                "include_sources": True,
                "top_k": 5
            },
            name="/api/query [inventory]"
        )
    
    @task(5)
    def query_simple(self):
        """Test query endpoint - simple questions."""
        simple_queries = ["What are your hours?", "Do you offer financing?", "What is your return policy?"]
        self.client.post(
            "/api/query",
            json={
                "query": random.choice(simple_queries),
                "include_sources": False
            },
            name="/api/query [simple]"
        )
    
    @task(2)
    def ingest_text(self):
        """Test text ingestion."""
        self.client.post(
            "/api/ingest",
            json={
                "source_type": "text",
                "content": f"Test vehicle {random.randint(1000, 9999)}: 2024 Test Model, Price: ${random.randint(20000, 50000)}",
                "metadata": {"test": True},
                "namespace": "test"
            },
            name="/api/ingest [text]"
        )
    
    @task(1)
    def health_check(self):
        """Periodic health checks."""
        self.client.get("/api/health", name="/api/health")
    
    @task(1)
    def get_metrics(self):
        """Get system metrics."""
        self.client.get("/api/metrics", name="/api/metrics")
    
    def on_start(self):
        """Called when a simulated user starts."""
        pass  # Optional: setup/authentication


@events.quitting.add_listener
def _(environment, **kw):
    """Print detailed summary on test completion."""
    stats = environment.stats.total
    
    print(f"\n{'='*70}")
    print(f"LOAD TEST RESULTS")
    print(f"{'='*70}")
    print(f"Total Requests:       {stats.num_requests}")
    print(f"Total Failures:       {stats.num_failures} ({stats.fail_ratio*100:.2f}%)")
    print(f"Requests/sec:         {stats.total_rps:.2f}")
    print(f"")
    print(f"Latency Metrics:")
    print(f"  Median (p50):       {stats.median_response_time}ms")
    print(f"  95th Percentile:    {stats.get_response_time_percentile(0.95):.0f}ms")
    print(f"  99th Percentile:    {stats.get_response_time_percentile(0.99):.0f}ms")
    print(f"  Average:            {stats.avg_response_time:.0f}ms")
    print(f"  Min:                {stats.min_response_time}ms")
    print(f"  Max:                {stats.max_response_time}ms")
    print(f"{'='*70}")
    
    # Validate against targets
    p95 = stats.get_response_time_percentile(0.95)
    fail_rate = stats.fail_ratio
    
    passed = []
    failed = []
    
    # Check failure rate
    if fail_rate < 0.01:
        passed.append(f"Error rate <1%: {fail_rate*100:.2f}%")
    else:
        failed.append(f"Error rate >{1%: {fail_rate*100:.2f}%")
    
    # Check p95 latency
    if p95 < 3000:
        passed.append(f"p95 latency <3s: {p95:.0f}ms")
    else:
        failed.append(f"p95 latency >3s: {p95:.0f}ms")
    
    # Check p50 latency
    if stats.median_response_time < 1500:
        passed.append(f"p50 latency <1.5s: {stats.median_response_time}ms")
    else:
        failed.append(f"p50 latency >1.5s: {stats.median_response_time}ms")
    
    # Check throughput
    if stats.total_rps > 20:
        passed.append(f"Throughput >20 RPS: {stats.total_rps:.2f}")
    else:
        failed.append(f"Throughput <20 RPS: {stats.total_rps:.2f}")
    
    print(f"\nPERFORMANCE VALIDATION:")
    print(f"{'='*70}")
    
    if passed:
        print("PASSED:")
        for p in passed:
            print(f"  ✓ {p}")
    
    if failed:
        print("\nFAILED:")
        for f in failed:
            print(f"  ✗ {f}")
    
    if not failed:
        print(f"\n✓ ALL PERFORMANCE TARGETS MET")
    
    print(f"{'='*70}\n")


# Usage examples
"""
# Basic load test (web UI)
locust -f locustfile.py --host=http://localhost:8000

# Headless mode with specific parameters
locust -f locustfile.py --host=http://localhost:8000 \\
  --users 100 --spawn-rate 10 --run-time 5m --headless

# Quick test (10 users, 1 minute)
locust -f locustfile.py --host=http://localhost:8000 \\
  --users 10 --spawn-rate 2 --run-time 1m --headless

# Sustained load (50 users, 10 minutes)
locust -f locustfile.py --host=http://localhost:8000 \\
  --users 50 --spawn-rate 5 --run-time 10m --headless

# Spike test (200 users, 2 minutes)
locust -f locustfile.py --host=http://localhost:8000 \\
  --users 200 --spawn-rate 50 --run-time 2m --headless
"""

