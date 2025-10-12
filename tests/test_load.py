"""
Load testing configuration using Locust.
Tests API performance under concurrent load.

Run with: locust -f tests/test_load.py --host=http://localhost:8000
"""

from locust import HttpUser, task, between
import random


class DealershipRAGUser(HttpUser):
    """Simulated user for load testing the RAG API."""
    
    # Wait 1-3 seconds between tasks
    wait_time = between(1, 3)
    
    # Sample queries for testing
    queries = [
        "What Toyota vehicles are available?",
        "Show me electric vehicles under $50k",
        "How much does the Honda Accord cost?",
        "What are your financing options?",
        "When should I get an oil change?",
        "What are your hours of operation?",
        "Do you have any SUVs in stock?",
        "Tell me about warranty coverage",
    ]
    
    @task(10)  # Weight: 10 (most common operation)
    def query_api(self):
        """Test query endpoint."""
        query = random.choice(self.queries)
        
        self.client.post(
            "/api/query",
            json={
                "query": query,
                "include_sources": True,
                "top_k": 5
            },
            name="/api/query"
        )
    
    @task(1)  # Weight: 1 (less common)
    def health_check(self):
        """Test health endpoint."""
        self.client.get("/api/health", name="/api/health")
    
    @task(1)
    def get_metrics(self):
        """Test metrics endpoint."""
        self.client.get("/api/metrics", name="/api/metrics")
    
    @task(2)
    def ingest_text(self):
        """Test text ingestion."""
        self.client.post(
            "/api/ingest",
            json={
                "source_type": "text",
                "content": "Test vehicle: 2024 Test Model, Price: $25,000",
                "metadata": {"test": True},
                "namespace": "test"
            },
            name="/api/ingest"
        )
    
    def on_start(self):
        """Called when a simulated user starts."""
        # Optional: authenticate or setup
        pass


# Performance test scenarios
class QuickLoadTest(HttpUser):
    """Quick load test - 10 users, ramp up over 10 seconds."""
    wait_time = between(0.5, 1.5)
    
    @task
    def quick_query(self):
        self.client.post(
            "/api/query",
            json={"query": "Test query", "include_sources": False}
        )


class SustainedLoadTest(HttpUser):
    """Sustained load test - 50 users, constant load."""
    wait_time = between(1, 2)
    
    @task
    def sustained_query(self):
        self.client.post(
            "/api/query",
            json={"query": random.choice(DealershipRAGUser.queries)}
        )


class SpikeTest(HttpUser):
    """Spike test - sudden traffic surge."""
    wait_time = between(0.1, 0.5)
    
    @task
    def spike_query(self):
        self.client.post(
            "/api/query",
            json={"query": "Quick test"}
        )


# Usage examples:
# Basic load test: locust -f tests/test_load.py --host=http://localhost:8000 --users 10 --spawn-rate 2
# Sustained load: locust -f tests/test_load.py --host=http://localhost:8000 --users 50 --spawn-rate 5 --run-time 5m
# Spike test: locust -f tests/test_load.py --host=http://localhost:8000 --users 100 --spawn-rate 50 --run-time 2m

# Performance targets:
# - p50 latency: <1.5s
# - p95 latency: <3s
# - p99 latency: <5s
# - Error rate: <1%
# - Throughput: >50 req/s with 2 workers

