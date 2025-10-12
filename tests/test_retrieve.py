"""
Tests for hybrid retrieval system.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock

from src.retrieve import HybridRetriever


@pytest.mark.asyncio
async def test_index_documents(sample_documents, mock_voyage_client, mock_pinecone_index):
    """Test document indexing."""
    retriever = HybridRetriever()
    
    with patch.object(retriever.embedding_manager, 'voyage_client', mock_voyage_client), \
         patch.object(retriever.embedding_manager, 'index', mock_pinecone_index):
        
        result = await retriever.index_documents(sample_documents, namespace="test")
        
        assert result["indexed_count"] == len(sample_documents)
        assert result["total_documents"] >= len(sample_documents)
        assert mock_pinecone_index.upsert.called


@pytest.mark.asyncio
async def test_retrieve_vector_search(sample_documents, mock_voyage_client, mock_pinecone_index):
    """Test vector retrieval."""
    retriever = HybridRetriever()
    
    # Index documents first
    retriever.document_cache = sample_documents
    
    with patch.object(retriever.embedding_manager, 'voyage_client', mock_voyage_client), \
         patch.object(retriever.embedding_manager, 'index', mock_pinecone_index):
        
        results = await retriever.retrieve(
            query="Toyota Camry price",
            namespace="test",
            top_k=3,
            use_rerank=False
        )
        
        assert isinstance(results, list)
        assert mock_voyage_client.embed.called


@pytest.mark.asyncio
async def test_retrieve_with_filters(mock_voyage_client, mock_pinecone_index):
    """Test retrieval with metadata filters."""
    retriever = HybridRetriever()
    
    with patch.object(retriever.embedding_manager, 'voyage_client', mock_voyage_client), \
         patch.object(retriever.embedding_manager, 'index', mock_pinecone_index):
        
        filters = {"make": "Toyota", "year": 2024}
        
        results = await retriever.retrieve(
            query="Available vehicles",
            filters=filters,
            use_rerank=False
        )
        
        # Verify filters were passed to Pinecone query
        assert mock_pinecone_index.query.called


@pytest.mark.asyncio
async def test_rerank_documents(sample_documents, mock_cohere_client):
    """Test Cohere re-ranking."""
    retriever = HybridRetriever()
    retriever.cohere_client = mock_cohere_client
    
    reranked = await retriever._rerank_documents(
        query="Toyota Camry",
        documents=sample_documents,
        top_k=2
    )
    
    assert len(reranked) <= 2
    assert mock_cohere_client.rerank.called
    
    # Check that rerank scores are added
    for doc in reranked:
        assert "rerank_score" in doc.metadata


def test_combine_results(sample_documents):
    """Test reciprocal rank fusion combining."""
    retriever = HybridRetriever()
    
    vector_docs = sample_documents[:2]
    bm25_docs = sample_documents[1:]  # Overlap on second doc
    
    combined = retriever._combine_results(vector_docs, bm25_docs, max_results=5)
    
    assert len(combined) <= 5
    
    # Check that RRF scores are added
    for doc in combined:
        assert "rrf_score" in doc.metadata


@pytest.mark.asyncio
async def test_clear_index(mock_pinecone_index):
    """Test clearing index."""
    retriever = HybridRetriever()
    
    with patch.object(retriever.embedding_manager, 'index', mock_pinecone_index):
        # Add some cached documents
        retriever.document_cache = ["doc1", "doc2"]
        
        success = await retriever.clear_index(namespace="test")
        
        assert success
        assert len(retriever.document_cache) == 0
        assert retriever.bm25_retriever is None


def test_get_stats(mock_pinecone_index):
    """Test retriever statistics."""
    retriever = HybridRetriever()
    
    with patch.object(retriever.embedding_manager, 'index', mock_pinecone_index):
        retriever.document_cache = ["doc1", "doc2", "doc3"]
        
        stats = retriever.get_stats()
        
        assert stats["cached_documents"] == 3
        assert "pinecone_stats" in stats


@pytest.mark.asyncio
async def test_retrieve_empty_query(mock_voyage_client, mock_pinecone_index):
    """Test handling of empty or invalid queries."""
    retriever = HybridRetriever()
    
    with patch.object(retriever.embedding_manager, 'voyage_client', mock_voyage_client), \
         patch.object(retriever.embedding_manager, 'index', mock_pinecone_index):
        
        results = await retriever.retrieve(
            query="",
            use_rerank=False
        )
        
        # Should handle gracefully
        assert isinstance(results, list)


@pytest.mark.asyncio
async def test_rerank_fallback_on_error(sample_documents):
    """Test that reranking falls back gracefully on error."""
    retriever = HybridRetriever()
    
    # Mock Cohere client to raise error
    mock_client = Mock()
    mock_client.rerank = Mock(side_effect=Exception("Cohere API error"))
    retriever.cohere_client = mock_client
    
    reranked = await retriever._rerank_documents(
        query="test",
        documents=sample_documents,
        top_k=2
    )
    
    # Should fallback to original order
    assert len(reranked) <= 2

