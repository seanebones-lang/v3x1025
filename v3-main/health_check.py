#!/usr/bin/env python3
"""
System health check script for deployment verification.
"""

import asyncio
import os
import sys
import time
from typing import Dict, Any

import aiohttp


async def check_system_health(base_url: str = "http://localhost:8000") -> Dict[str, Any]:
    """Perform comprehensive system health check."""
    
    results = {
        "timestamp": time.time(),
        "overall_status": "unknown",
        "checks": {}
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            # Health endpoint
            async with session.get(f"{base_url}/health", timeout=10) as response:
                health_data = await response.json()
                results["checks"]["health_endpoint"] = {
                    "status": "pass" if response.status == 200 else "fail",
                    "response_code": response.status,
                    "data": health_data
                }
            
            # Test query (if API key available)
            api_key = os.getenv("API_SECRET_KEY", "dev-secret-change-in-production")
            headers = {"Authorization": f"Bearer {api_key}"}
            
            test_query = {"query": "System health check test"}
            
            async with session.post(
                f"{base_url}/query", 
                json=test_query,
                headers=headers,
                timeout=30
            ) as response:
                results["checks"]["query_endpoint"] = {
                    "status": "pass" if response.status == 200 else "fail",
                    "response_code": response.status
                }
    
    except Exception as e:
        results["checks"]["connection"] = {
            "status": "fail",
            "error": str(e)
        }
    
    # Determine overall status
    all_passed = all(
        check.get("status") == "pass" 
        for check in results["checks"].values()
    )
    results["overall_status"] = "healthy" if all_passed else "unhealthy"
    
    return results


if __name__ == "__main__":
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    
    results = asyncio.run(check_system_health(base_url))
    
    print(f"System Health Check Results:")
    print(f"Overall Status: {results['overall_status']}")
    print(f"Timestamp: {time.ctime(results['timestamp'])}")
    
    for check_name, check_result in results["checks"].items():
        status = check_result["status"]
        print(f"- {check_name}: {status}")
        
        if status == "fail" and "error" in check_result:
            print(f"  Error: {check_result['error']}")
    
    # Exit with appropriate code
    sys.exit(0 if results["overall_status"] == "healthy" else 1)