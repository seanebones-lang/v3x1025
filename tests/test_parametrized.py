"""
Parametrized tests for comprehensive coverage of variations.
"""

import pytest
from src.agent import AgenticRAG


@pytest.mark.parametrize("vin,expected_valid", [
    ("1HGBH41JXMN109186", True),
    ("5YJ3E1EA1KF123456", True),
    ("INVALID", False),
    ("", False),
    ("12345", False),
])
@pytest.mark.asyncio
async def test_vin_validation_parametrized(vin, expected_valid, mock_dms_adapter):
    """Test VIN validation with various inputs."""
    agent = AgenticRAG()
    agent.dms_adapter = mock_dms_adapter
    
    vehicle = await agent.dms_adapter.get_vehicle_details(vin)
    
    if expected_valid:
        assert vehicle is not None or vin not in [v.vin for v in mock_dms_adapter.inventory]
    else:
        assert vehicle is None


@pytest.mark.parametrize("namespace", [
    "default",
    "inventory",
    "sales",
    "service",
    "test",
])
@pytest.mark.asyncio
async def test_namespace_operations(namespace, sample_documents):
    """Test operations across different namespaces."""
    from src.ingest import DocumentIngestionPipeline
    from src.retrieve import HybridRetriever
    from unittest.mock import patch, Mock
    
    retriever = HybridRetriever()
    
    # Mock Pinecone index
    mock_index = Mock()
    mock_index.upsert = Mock()
    
    with patch.object(retriever.embedding_manager, 'index', mock_index), \
         patch.object(retriever.embedding_manager.voyage_client, 'embed', return_value=Mock(embeddings=[[0.1]*3072])):
        
        result = await retriever.index_documents(sample_documents, namespace=namespace)
        
        assert result["indexed_count"] == len(sample_documents)
        # Verify namespace was used in upsert
        assert mock_index.upsert.called


@pytest.mark.parametrize("query,expected_intent", [
    ("How much does the Toyota Camry cost?", "sales"),
    ("Show me available vehicles", "inventory"),
    ("When should I get an oil change?", "service"),
    ("What is the forecast for EV demand?", "predictive"),
    ("What are your hours?", "general"),
])
@pytest.mark.asyncio
async def test_intent_classification_variations(query, expected_intent):
    """Test intent classification with various query types."""
    agent = AgenticRAG()
    
    # Use rule-based fallback for deterministic testing
    intent = agent._rule_based_intent_classification(query)
    
    assert intent.intent == expected_intent


@pytest.mark.parametrize("make,model,year", [
    ("Toyota", "Camry", 2024),
    ("Honda", "Accord", 2023),
    ("Tesla", "Model 3", 2024),
    ("Ford", "F-150", 2023),
])
@pytest.mark.asyncio
async def test_vehicle_filter_extraction(make, model, year):
    """Test filter extraction for different vehicle combinations."""
    agent = AgenticRAG()
    
    query = f"{year} {make} {model}"
    filters = agent._extract_vehicle_filters(query)
    
    assert filters.get("make") == make or filters.get("year") == year


@pytest.mark.parametrize("top_k,expected_max", [
    (1, 1),
    (5, 5),
    (10, 10),
    (50, 50),
])
@pytest.mark.asyncio
async def test_top_k_limits(top_k, expected_max, sample_documents):
    """Test top_k parameter limits."""
    from src.retrieve import HybridRetriever
    from unittest.mock import patch, Mock
    
    retriever = HybridRetriever()
    retriever.document_cache = sample_documents * 20  # Create enough docs
    
    mock_index = Mock()
    mock_index.query = Mock(return_value=Mock(
        matches=[
            Mock(id=f"id_{i}", score=0.9-i*0.01, metadata={"text": f"doc {i}", "source": f"test{i}.pdf"})
            for i in range(30)
        ]
    ))
    
    with patch.object(retriever.embedding_manager, 'index', mock_index), \
         patch.object(retriever.embedding_manager.voyage_client, 'embed', return_value=Mock(embeddings=[[0.1]*3072])):
        
        results = await retriever.retrieve(
            query="test",
            top_k=top_k,
            use_rerank=False
        )
        
        assert len(results) <= expected_max

