#!/usr/bin/env python3
"""
Demo script to test queries against the RAG system.
Demonstrates various query types and intents.
"""

import requests
import json
from typing import Dict, Any


API_BASE_URL = "http://localhost:8000"


def print_result(query: str, response: Dict[str, Any]):
    """Pretty print query results."""
    print("\n" + "=" * 80)
    print(f" QUERY: {query}")
    print("=" * 80)
    
    if response.get("answer"):
        print(f"\n ANSWER:")
        print(f"{response['answer']}")
        
        if response.get("intent"):
            print(f"\n Intent: {response['intent']}")
        
        if response.get("sources"):
            print(f"\n SOURCES ({len(response['sources'])}):")
            for i, source in enumerate(response['sources'][:3], 1):
                print(f"   {i}. {source.get('metadata', {}).get('source', 'Unknown')}")
                print(f"      Score: {source.get('score', 'N/A')}")
        
        if response.get("query_time_ms"):
            print(f"\n Query Time: {response['query_time_ms']:.2f}ms")
    else:
        print(f"\n Error: {response.get('detail', 'Unknown error')}")


def check_health() -> bool:
    """Check if API is running."""
    try:
        response = requests.get(f"{API_BASE_URL}/api/health", timeout=5)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


def query_api(query: str, **kwargs) -> Dict[str, Any]:
    """Send query to API."""
    try:
        response = requests.post(
            f"{API_BASE_URL}/api/query",
            json={"query": query, **kwargs},
            timeout=30
        )
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"detail": str(e)}


def main():
    """Run demo queries."""
    print(" Dealership RAG System - Demo Queries")
    print("=" * 80)
    
    # Check if API is running
    print("\n Checking API status...")
    if not check_health():
        print(" API is not running!")
        print("\n Start the API first:")
        print("   docker-compose up")
        print("   or")
        print("   uvicorn src.app:app --host 0.0.0.0 --port 8000")
        return
    
    print(" API is running!\n")
    
    # Demo queries covering different intents
    demo_queries = [
        {
            "query": "What Toyota vehicles do you have available?",
            "description": "Inventory Query"
        },
        {
            "query": "How much does the Toyota Camry cost?",
            "description": "Sales/Pricing Query"
        },
        {
            "query": "Show me electric vehicles under $50,000",
            "description": "Filtered Inventory Query"
        },
        {
            "query": "What are your hours of operation?",
            "description": "General FAQ Query"
        },
        {
            "query": "Do you offer financing options?",
            "description": "Sales/Financing Query"
        },
    ]
    
    print(" Running demo queries...\n")
    input("Press Enter to start...\n")
    
    for i, demo in enumerate(demo_queries, 1):
        print(f"\n[Query {i}/{len(demo_queries)}] {demo['description']}")
        response = query_api(demo['query'], include_sources=True)
        print_result(demo['query'], response)
        
        if i < len(demo_queries):
            input("\nPress Enter for next query...")
    
    # Interactive mode
    print("\n" + "=" * 80)
    print(" Interactive Mode")
    print("=" * 80)
    print("Enter your own queries (type 'exit' to quit):\n")
    
    while True:
        try:
            user_query = input("\n Your query: ").strip()
            
            if user_query.lower() in ['exit', 'quit', 'q']:
                print("\n Goodbye!")
                break
            
            if not user_query:
                continue
            
            response = query_api(user_query, include_sources=True)
            print_result(user_query, response)
            
        except KeyboardInterrupt:
            print("\n\n Goodbye!")
            break
        except Exception as e:
            print(f"\n Error: {e}")


if __name__ == "__main__":
    main()

