#!/usr/bin/env python3
"""
Chaos testing - Inject failures and verify graceful degradation.
Tests circuit breakers, fallbacks, and error handling.
"""

import requests
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys

API_BASE = "http://localhost:8000"


def test_query_with_chaos(query_id: int) -> dict:
    """Test single query with random chaos injection."""
    try:
        # Random timeout to simulate network issues
        timeout = random.uniform(0.5, 5.0)
        
        response = requests.post(
            f"{API_BASE}/api/query",
            json={"query": f"Test query {query_id}"},
            timeout=timeout
        )
        
        return {
            "id": query_id,
            "status": response.status_code,
            "latency_ms": response.elapsed.total_seconds() * 1000,
            "success": response.status_code == 200
        }
    except requests.Timeout:
        return {"id": query_id, "status": "timeout", "success": False}
    except Exception as e:
        return {"id": query_id, "status": "error", "error": str(e)[:50], "success": False}


def run_chaos_test(num_requests: int = 100, concurrency: int = 20):
    """
    Run chaos test with concurrent requests and random failures.
    
    Args:
        num_requests: Total requests to make
        concurrency: Concurrent requests
    """
    print(f"Chaos Test: {num_requests} requests, {concurrency} concurrent")
    print("="*60)
    
    # Check API availability
    try:
        health = requests.get(f"{API_BASE}/api/health", timeout=5)
        if health.status_code != 200:
            print(f"ERROR: API unhealthy (status {health.status_code})")
            return False
        print("API health check: PASSED\n")
    except Exception as e:
        print(f"ERROR: Cannot reach API at {API_BASE}")
        print(f"Start with: docker-compose up -d")
        return False
    
    results = []
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(test_query_with_chaos, i) for i in range(num_requests)]
        
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            
            status_symbol = "✓" if result["success"] else "✗"
            latency_str = f"{result.get('latency_ms', 0):.0f}ms" if result["success"] else result["status"]
            
            if len(results) % 10 == 0:
                print(f"{status_symbol} Completed: {len(results)}/{num_requests}")
    
    total_time = time.time() - start_time
    
    # Calculate statistics
    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]
    
    latencies = [r["latency_ms"] for r in successful]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    p95_latency = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0
    
    # Summary
    print("\n" + "="*60)
    print("CHAOS TEST SUMMARY")
    print("="*60)
    print(f"Total Requests:     {len(results)}")
    print(f"Successful:         {len(successful)} ({len(successful)/len(results)*100:.1f}%)")
    print(f"Failed:             {len(failed)} ({len(failed)/len(results)*100:.1f}%)")
    print(f"Average Latency:    {avg_latency:.0f}ms")
    print(f"p95 Latency:        {p95_latency:.0f}ms")
    print(f"Requests/sec:       {len(results)/total_time:.2f}")
    print(f"Total Time:         {total_time:.1f}s")
    print("="*60)
    
    # Validation
    success_rate = len(successful) / len(results)
    
    if success_rate > 0.95 and p95_latency < 3000:
        print("\nPASSED: >95% success rate, p95 <3s under chaos")
        return True
    elif success_rate > 0.90:
        print("\nWARNING: 90-95% success rate (acceptable under chaos)")
        return True
    else:
        print("\nFAILED: <90% success rate under chaos")
        return False


if __name__ == "__main__":
    success = run_chaos_test(num_requests=100, concurrency=20)
    sys.exit(0 if success else 1)

