"""
End-to-End Testing Suite for RAG System
"""
import asyncio
import pytest
import aiohttp
from typing import Dict, List
import json


class E2ETestSuite:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.test_results = []
    
    async def test_full_rag_pipeline(self):
        """Test complete RAG pipeline: ingest -> query -> response"""
        async with aiohttp.ClientSession() as session:
            
            # 1. Test document ingestion
            test_doc = {
                "source_type": "text",
                "content": "We have a 2023 Honda Accord EX available for $32,000. VIN: 1HGCV1F30NA123456. Features: Lane Assist, Apple CarPlay, Moonroof.",
                "metadata": {"source": "test_inventory"}
            }
            
            async with session.post(
                f"{self.base_url}/ingest",
                json=test_doc,
                headers=self.headers
            ) as response:
                assert response.status == 200
                ingest_result = await response.json()
                assert ingest_result["status"] == "success"
            
            # 2. Wait for indexing (in real system)
            await asyncio.sleep(2)
            
            # 3. Test query retrieval
            test_query = {
                "query": "Do you have any Honda Accord models available?",
                "top_k": 5
            }
            
            async with session.post(
                f"{self.base_url}/query",
                json=test_query,
                headers=self.headers
            ) as response:
                assert response.status == 200
                query_result = await response.json()
                assert "answer" in query_result
                assert "honda" in query_result["answer"].lower()
                assert len(query_result["sources"]) > 0
    
    async def test_conversation_continuity(self):
        """Test multi-turn conversation handling"""
        async with aiohttp.ClientSession() as session:
            # First query
            query1 = {"query": "What cars do you have?"}
            async with session.post(f"{self.base_url}/query", json=query1, headers=self.headers) as response:
                result1 = await response.json()
                conversation_id = result1["conversation_id"]
            
            # Follow-up query with conversation context
            query2 = {
                "query": "What about the price for the Honda?",
                "conversation_id": conversation_id
            }
            async with session.post(f"{self.base_url}/query", json=query2, headers=self.headers) as response:
                result2 = await response.json()
                assert result2["conversation_id"] == conversation_id
    
    async def test_dms_integration(self):
        """Test DMS adapter functionality"""
        # This would test actual DMS API calls
        pass
    
    async def test_error_handling(self):
        """Test system behavior under error conditions"""
        async with aiohttp.ClientSession() as session:
            # Test malformed request
            async with session.post(f"{self.base_url}/query", json={}, headers=self.headers) as response:
                assert response.status == 422  # Validation error
            
            # Test authentication failure
            bad_headers = {"Authorization": "Bearer invalid_key"}
            async with session.post(f"{self.base_url}/query", json={"query": "test"}, headers=bad_headers) as response:
                assert response.status == 401
    
    async def test_performance_requirements(self):
        """Test system meets performance SLAs"""
        import time
        async with aiohttp.ClientSession() as session:
            start_time = time.time()
            
            async with session.post(
                f"{self.base_url}/query",
                json={"query": "What inventory do you have?"},
                headers=self.headers
            ) as response:
                response_time = (time.time() - start_time) * 1000
                assert response_time < 5000  # Under 5 seconds
                assert response.status == 200
    
    async def run_all_tests(self):
        """Run complete test suite"""
        tests = [
            self.test_full_rag_pipeline,
            self.test_conversation_continuity,
            self.test_dms_integration,
            self.test_error_handling,
            self.test_performance_requirements
        ]
        
        for test in tests:
            try:
                await test()
                self.test_results.append({"test": test.__name__, "status": "PASS"})
            except Exception as e:
                self.test_results.append({"test": test.__name__, "status": "FAIL", "error": str(e)})
        
        return self.test_results


if __name__ == "__main__":
    import sys
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    api_key = sys.argv[2] if len(sys.argv) > 2 else "dev-secret-change-in-production"
    
    suite = E2ETestSuite(base_url, api_key)
    results = asyncio.run(suite.run_all_tests())
    
    print("🧪 E2E Test Results:")
    for result in results:
        status_emoji = "✅" if result["status"] == "PASS" else "❌"
        print(f"{status_emoji} {result['test']}: {result['status']}")
        if result["status"] == "FAIL":
            print(f"   Error: {result['error']}")