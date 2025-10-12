"""
Tests for document ingestion pipeline.
"""

import pytest
from pathlib import Path
import tempfile
import json

from src.ingest import DocumentIngestionPipeline


@pytest.mark.asyncio
async def test_ingest_text():
    """Test text ingestion."""
    pipeline = DocumentIngestionPipeline()
    
    text = "This is a test document about vehicle specifications."
    chunks = await pipeline.ingest_text(text, metadata={"type": "test"})
    
    assert len(chunks) > 0
    assert chunks[0].page_content == text
    assert chunks[0].metadata["type"] == "test"
    assert "ingested_at" in chunks[0].metadata


@pytest.mark.asyncio
async def test_ingest_json():
    """Test JSON ingestion."""
    pipeline = DocumentIngestionPipeline()
    
    test_data = {
        "make": "Toyota",
        "model": "Camry",
        "year": 2024,
        "price": 28000
    }
    
    json_str = json.dumps(test_data)
    chunks = await pipeline.ingest_json(json_str, metadata={"source": "test"})
    
    assert len(chunks) > 0
    assert "Toyota" in chunks[0].page_content


@pytest.mark.asyncio
async def test_ingest_file_txt():
    """Test TXT file ingestion."""
    pipeline = DocumentIngestionPipeline()
    
    # Create temporary text file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("Test content for ingestion.\nMultiple lines of text.")
        temp_path = f.name
    
    try:
        chunks = await pipeline.ingest_file(temp_path)
        
        assert len(chunks) > 0
        assert "Test content" in chunks[0].page_content
        assert chunks[0].metadata["file_type"] == ".txt"
    finally:
        Path(temp_path).unlink()


@pytest.mark.asyncio
async def test_ingest_file_not_found():
    """Test error handling for missing file."""
    pipeline = DocumentIngestionPipeline()
    
    with pytest.raises(FileNotFoundError):
        await pipeline.ingest_file("nonexistent_file.txt")


def test_deduplicate_chunks(sample_documents):
    """Test chunk deduplication."""
    pipeline = DocumentIngestionPipeline()
    
    # Create duplicates
    documents = sample_documents + sample_documents
    
    unique_docs = pipeline.deduplicate_chunks(documents)
    
    assert len(unique_docs) == len(sample_documents)


def test_get_loader():
    """Test loader selection by file extension."""
    pipeline = DocumentIngestionPipeline()
    
    pdf_loader = pipeline._get_loader("test.pdf")
    txt_loader = pipeline._get_loader("test.txt")
    csv_loader = pipeline._get_loader("test.csv")
    
    # Just verify loaders are returned (types may vary)
    assert pdf_loader is not None
    assert txt_loader is not None
    assert csv_loader is not None


@pytest.mark.asyncio
async def test_chunking_parameters():
    """Test that chunking respects configuration."""
    pipeline = DocumentIngestionPipeline()
    
    # Create a long text
    long_text = "Word " * 2000  # Long enough to need chunking
    
    chunks = await pipeline.ingest_text(long_text)
    
    # Should create multiple chunks
    assert len(chunks) > 1
    
    # Each chunk should be roughly within chunk_size limits
    for chunk in chunks:
        assert len(chunk.page_content) <= pipeline.text_splitter.chunk_size + 100  # Some tolerance


@pytest.mark.asyncio
async def test_ingest_json_list():
    """Test ingesting JSON array."""
    pipeline = DocumentIngestionPipeline()
    
    test_data = [
        {"id": 1, "name": "Item 1"},
        {"id": 2, "name": "Item 2"}
    ]
    
    json_str = json.dumps(test_data)
    chunks = await pipeline.ingest_json(json_str)
    
    # Should create chunks for list items
    assert len(chunks) >= len(test_data)

