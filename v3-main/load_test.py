#!/usr/bin/env python3
"""
Load testing script for RAG API.
"""
import asyncio
import aiohttp
import time
import json
from statistics import mean, median
from typing import List, Dict, Any


async def make_request(session: aiohttp.ClientSession, url: str, headers: Dict[str, str]) -> Dict[str, Any]:
    """Make a single API request and measure response time."""
    start_time = time.time()
    
    test_query = {
        "query": "What Honda Accord models do you have available?",
        "top_k": 5
    }
    
    try:
        async with session.post(f"{url}/query", json=test_query, headers=headers) as response:
            response_time = (time.time() - start_time) * 1000
            status = response.status
            
            if status == 200:
                data = await response.json()
                return {
                    "status": "success",
                    "response_time_ms": response_time,
                    "status_code": status
                }
            else:
                return {
                    "status": "error", 
                    "response_time_ms": response_time,
                    "status_code": status
                }
                
    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        return {
            "status": "error",
            "response_time_ms": response_time,
            "error": str(e)
        }


async def load_test(base_url: str, api_key: str, concurrent_users: int, duration_seconds: int):
    """Run load test with specified parameters."""
    
    print(f"🚀 Starting load test:")
    print(f"   URL: {base_url}")
    print(f"   Concurrent users: {concurrent_users}")
    print(f"   Duration: {duration_seconds} seconds")
    print("="*50)
    
    headers = {"Authorization": f"Bearer {api_key}"}
    results = []
    start_time = time.time()
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        
        while time.time() - start_time < duration_seconds:
            # Maintain concurrent users
            if len(tasks) < concurrent_users:
                task = asyncio.create_task(make_request(session, base_url, headers))
                tasks.append(task)
            
            # Check completed tasks
            done_tasks = [task for task in tasks if task.done()]
            for task in done_tasks:
                result = await task
                results.append(result)
                tasks.remove(task)
            
            await asyncio.sleep(0.1)
        
        # Wait for remaining tasks
        remaining = await asyncio.gather(*tasks, return_exceptions=True)
        for result in remaining:
            if isinstance(result, dict):
                results.append(result)
    
    # Calculate statistics
    successful_requests = [r for r in results if r["status"] == "success"]
    failed_requests = [r for r in results if r["status"] == "error"]
    
    if successful_requests:
        response_times = [r["response_time_ms"] for r in successful_requests]
        
        print(f"📊 Load Test Results:")
        print(f"   Total requests: {len(results)}")
        print(f"   Successful: {len(successful_requests)}")
        print(f"   Failed: {len(failed_requests)}")
        print(f"   Success rate: {len(successful_requests)/len(results)*100:.1f}%")
        print(f"   Average response time: {mean(response_times):.1f}ms")
        print(f"   Median response time: {median(response_times):.1f}ms")
        print(f"   95th percentile: {sorted(response_times)[int(len(response_times)*0.95)]:.1f}ms")
        print(f"   Requests per second: {len(results)/duration_seconds:.1f}")
        
        # Performance thresholds
        if mean(response_times) > 5000:
            print("⚠️  WARNING: Average response time exceeds 5 seconds")
        if len(failed_requests)/len(results) > 0.01:
            print("⚠️  WARNING: Error rate exceeds 1%")
        if len(results)/duration_seconds < 10:
            print("⚠️  WARNING: Throughput below 10 requests/second")
    else:
        print("❌ All requests failed!")
        for result in failed_requests[:5]:  # Show first 5 errors
            print(f"   Error: {result.get('error', 'Unknown error')}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) != 5:
        print("Usage: python3 load_test.py <base_url> <api_key> <concurrent_users> <duration_seconds>")
        sys.exit(1)
    
    base_url = sys.argv[1]
    api_key = sys.argv[2] 
    concurrent_users = int(sys.argv[3])
    duration_seconds = int(sys.argv[4])
    
    asyncio.run(load_test(base_url, api_key, concurrent_users, duration_seconds))