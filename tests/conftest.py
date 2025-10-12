"""
Pytest configuration and fixtures for testing.
"""

import pytest
import asyncio
from typing import List
from unittest.mock import Mock, AsyncMock, MagicMock

from langchain.schema import Document

from src.models import Vehicle
from src.dms.mock_adapter import MockDMSAdapter


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_documents() -> List[Document]:
    """Sample documents for testing."""
    return [
        Document(
            page_content="The 2024 Toyota Camry LE is priced at $28,000 with low mileage.",
            metadata={
                "source": "test_inventory.json",
                "document_type": "inventory",
                "make": "Toyota",
                "model": "Camry",
                "year": 2024
            }
        ),
        Document(
            page_content="Oil change service is recommended every 5,000 miles or 6 months.",
            metadata={
                "source": "service_manual.pdf",
                "document_type": "service",
                "service_type": "oil_change"
            }
        ),
        Document(
            page_content="We offer competitive financing rates starting at 2.9% APR for qualified buyers.",
            metadata={
                "source": "financing_info.txt",
                "document_type": "policy",
                "policy_type": "financing"
            }
        )
    ]


@pytest.fixture
def sample_vehicles() -> List[Vehicle]:
    """Sample vehicle data for testing."""
    return [
        Vehicle(
            vin="1HGBH41JXMN109186",
            make="Toyota",
            model="Camry",
            year=2024,
            trim="LE",
            mileage=1500,
            price=28000.00,
            status="available",
            color_exterior="Silver",
            color_interior="Black",
            engine="2.5L I4",
            transmission="Automatic",
            fuel_type="Gasoline",
            features=["Bluetooth", "Backup Camera", "Apple CarPlay"],
            images=[],
            location="Main Dealership",
            stock_number="STK1001"
        ),
        Vehicle(
            vin="5YJ3E1EA1KF123456",
            make="Tesla",
            model="Model 3",
            year=2023,
            trim="Long Range",
            mileage=12000,
            price=45000.00,
            status="available",
            color_exterior="Blue",
            color_interior="White",
            engine="Electric",
            transmission="Automatic",
            fuel_type="Electric",
            features=["Autopilot", "Premium Audio", "Glass Roof"],
            images=[],
            location="Main Dealership",
            stock_number="STK1002"
        )
    ]


@pytest.fixture
async def mock_dms_adapter(sample_vehicles):
    """Mock DMS adapter for testing."""
    adapter = MockDMSAdapter()
    adapter.inventory = sample_vehicles
    return adapter


@pytest.fixture
def mock_voyage_client():
    """Mock Voyage AI client for testing."""
    mock = Mock()
    mock.embed = Mock(return_value=Mock(
        embeddings=[[0.1] * 3072]  # Mock embedding vector
    ))
    return mock


@pytest.fixture
def mock_pinecone_index():
    """Mock Pinecone index for testing."""
    mock = MagicMock()
    mock.upsert = Mock(return_value=None)
    mock.query = Mock(return_value=Mock(
        matches=[
            Mock(
                id="test_id_1",
                score=0.95,
                metadata={
                    "text": "Test document content",
                    "source": "test.pdf"
                }
            )
        ]
    ))
    mock.delete = Mock(return_value=None)
    mock.describe_index_stats = Mock(return_value=Mock(
        total_vector_count=100,
        dimension=3072,
        namespaces={"default": Mock(vector_count=100)}
    ))
    return mock


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic Claude client for testing."""
    mock = AsyncMock()
    mock.messages.create = AsyncMock(return_value=Mock(
        content=[Mock(text="This is a test answer with [Source: test.pdf] citation.")],
        usage=Mock(input_tokens=100, output_tokens=50)
    ))
    return mock


@pytest.fixture
def mock_cohere_client():
    """Mock Cohere client for testing."""
    mock = Mock()
    mock.rerank = Mock(return_value=Mock(
        results=[
            Mock(index=0, relevance_score=0.95),
            Mock(index=1, relevance_score=0.85)
        ]
    ))
    return mock


@pytest.fixture
def sample_query_request():
    """Sample query request for API testing."""
    return {
        "query": "What Toyota Camry models are available?",
        "conversation_id": None,
        "filters": None,
        "top_k": 5,
        "include_sources": True,
        "stream": False
    }


@pytest.fixture
def sample_ingest_request():
    """Sample ingest request for API testing."""
    return {
        "source_type": "text",
        "source_identifier": None,
        "content": "Test document content for ingestion.",
        "metadata": {"test": True},
        "namespace": "test"
    }

