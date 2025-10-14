"""
Integration tests for the RAG API.
"""
import asyncio
import pytest
from httpx import AsyncClient
from src.app import app


@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_endpoint(client):
    """Test health endpoint returns 200."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert "status" in response.json()


@pytest.mark.asyncio 
async def test_query_endpoint_auth_required(client):
    """Test query endpoint requires authentication."""
    response = await client.post("/query", json={"query": "test"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_query_endpoint_success(client):
    """Test successful query processing."""
    headers = {"Authorization": "Bearer dev-secret-change-in-production"}
    response = await client.post(
        "/query", 
        json={"query": "What cars do you have?"},
        headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert "sources" in data


@pytest.mark.asyncio
async def test_metrics_endpoint(client):
    """Test metrics endpoint."""
    headers = {"Authorization": "Bearer dev-secret-change-in-production"}
    response = await client.get("/metrics", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "total_queries" in data