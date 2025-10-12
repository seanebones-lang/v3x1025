"""
Tests for anti-hallucination measures.
Ensures system doesn't fabricate information when context is insufficient.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock

from langchain.schema import Document
from src.generate import AnswerGenerator


@pytest.mark.asyncio
async def test_hallucination_with_no_context():
    """Test that generator doesn't hallucinate with no context."""
    generator = AnswerGenerator()
    
    # Mock Claude to return a proper "no info" response
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=Mock(
        content=[Mock(text="I don't have that specific information in my current knowledge base.")],
        usage=Mock(input_tokens=100, output_tokens=20)
    ))
    
    with patch.object(generator, 'client', mock_client):
        result = await generator.generate_answer(
            query="What is the torque specification for a fictional XYZ-2000 model?",
            context_documents=[]  # No context provided
        )
        
        answer = result["answer"].lower()
        
        # Should admit lack of information
        assert any(phrase in answer for phrase in [
            "don't have",
            "not found",
            "no information",
            "unable to find",
            "not available"
        ]), f"Expected admission of no info, got: {answer}"
        
        # Should NOT contain fabricated technical details
        assert "torque" not in answer or "don't" in answer
        assert "specification" not in answer or "no" in answer


@pytest.mark.asyncio
async def test_hallucination_with_irrelevant_context():
    """Test that generator doesn't hallucinate with irrelevant context."""
    generator = AnswerGenerator()
    
    # Provide context about unrelated topic
    irrelevant_docs = [
        Document(
            page_content="Our dealership offers great financing options starting at 2.9% APR.",
            metadata={"source": "financing.txt", "document_type": "policy"}
        ),
        Document(
            page_content="We are open Monday through Friday 8AM to 8PM.",
            metadata={"source": "hours.txt", "document_type": "info"}
        )
    ]
    
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=Mock(
        content=[Mock(text="I don't have specific information about the 2024 Ferrari engine specifications in my current knowledge base.")],
        usage=Mock(input_tokens=200, output_tokens=25)
    ))
    
    with patch.object(generator, 'client', mock_client):
        result = await generator.generate_answer(
            query="What are the engine specifications for the 2024 Ferrari F8?",
            context_documents=irrelevant_docs
        )
        
        answer = result["answer"].lower()
        
        # Should acknowledge lack of relevant information
        assert any(phrase in answer for phrase in [
            "don't have",
            "not found",
            "no information",
            "unable to provide"
        ])


@pytest.mark.asyncio
async def test_no_hallucination_with_partial_context():
    """Test that generator only uses provided context, not external knowledge."""
    generator = AnswerGenerator()
    
    # Context mentions price but not specs
    partial_docs = [
        Document(
            page_content="2024 Toyota Camry LE priced at $28,000. Available in Silver.",
            metadata={"source": "inventory.json", "document_type": "vehicle", "vin": "ABC123"}
        )
    ]
    
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=Mock(
        content=[Mock(text="The 2024 Toyota Camry LE is priced at $28,000 and available in Silver [Source: inventory.json]. I don't have engine specification details in the available information.")],
        usage=Mock(input_tokens=150, output_tokens=40)
    ))
    
    with patch.object(generator, 'client', mock_client):
        result = await generator.generate_answer(
            query="What are the engine specs and price of the 2024 Toyota Camry?",
            context_documents=partial_docs
        )
        
        answer = result["answer"]
        
        # Should mention the price (in context)
        assert "28,000" in answer or "$28" in answer
        
        # Should acknowledge missing engine specs
        assert any(phrase in answer.lower() for phrase in [
            "don't have",
            "not available",
            "no information",
            "engine" not in answer.lower()  # Shouldn't fabricate engine details
        ])


@pytest.mark.asyncio
async def test_source_citation_prevents_hallucination():
    """Test that requiring source citations prevents hallucination."""
    generator = AnswerGenerator()
    
    docs = [
        Document(
            page_content="The 2023 Honda Accord has a 1.5L turbocharged engine producing 192 horsepower.",
            metadata={"source": "specs.pdf", "document_type": "manual"}
        )
    ]
    
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=Mock(
        content=[Mock(text="The 2023 Honda Accord has a 1.5L turbocharged engine producing 192 horsepower [Source: specs.pdf].")],
        usage=Mock(input_tokens=120, output_tokens=30)
    ))
    
    with patch.object(generator, 'client', mock_client):
        result = await generator.generate_answer(
            query="What engine does the 2023 Honda Accord have?",
            context_documents=docs
        )
        
        answer = result["answer"]
        sources = result["sources"]
        
        # Should cite the source
        assert "[Source:" in answer or "source" in answer.lower()
        
        # Should have sources in metadata
        assert len(sources) > 0
        assert any("specs.pdf" in str(s) for s in sources)


@pytest.mark.asyncio
async def test_junk_context_handling():
    """Test handling of malformed or junk context."""
    generator = AnswerGenerator()
    
    junk_docs = [
        Document(
            page_content="Lorem ipsum dolor sit amet consectetur adipiscing elit.",
            metadata={"source": "test.txt", "document_type": "junk"}
        ),
        Document(
            page_content="12345 !@#$% ABCDEFG",
            metadata={"source": "garbage.txt", "document_type": "junk"}
        )
    ]
    
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=Mock(
        content=[Mock(text="I don't have information about Toyota Camry pricing in the provided context.")],
        usage=Mock(input_tokens=100, output_tokens=20)
    ))
    
    with patch.object(generator, 'client', mock_client):
        result = await generator.generate_answer(
            query="What's the price of a Toyota Camry?",
            context_documents=junk_docs
        )
        
        answer = result["answer"].lower()
        
        # Should recognize lack of useful information
        assert any(phrase in answer for phrase in [
            "don't have",
            "not found",
            "no information"
        ])
        
        # Should NOT contain fabricated price
        assert not any(char.isdigit() for char in answer) or "don't" in answer


@pytest.mark.asyncio
async def test_validation_detects_hallucination():
    """Test that validation function can detect potential hallucinations."""
    generator = AnswerGenerator()
    
    # Answer that doesn't match context
    answer = "The 2024 Tesla Model S has a V8 engine and gets 15 MPG."
    
    context = [
        Document(
            page_content="The 2024 Tesla Model S is an electric vehicle with dual motors.",
            metadata={"source": "tesla.pdf", "document_type": "specs"}
        )
    ]
    
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=Mock(
        content=[Mock(text="Groundedness Score: 2/10\nUnsupported Claims: V8 engine, 15 MPG (Tesla is electric)")],
        usage=Mock(input_tokens=150, output_tokens=30)
    ))
    
    with patch.object(generator, 'client', mock_client):
        validation = await generator.validate_answer(answer, context)
        
        assert validation["validation_complete"]
        validation_text = validation["validation_text"].lower()
        
        # Should flag the hallucinated claims
        assert "unsupported" in validation_text or "2/10" in validation_text or "low" in validation_text


@pytest.mark.asyncio
async def test_edge_case_empty_string_context():
    """Test handling of empty string in context."""
    generator = AnswerGenerator()
    
    empty_docs = [
        Document(
            page_content="",
            metadata={"source": "empty.txt", "document_type": "unknown"}
        )
    ]
    
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=Mock(
        content=[Mock(text="I don't have information available to answer this question.")],
        usage=Mock(input_tokens=80, output_tokens=15)
    ))
    
    with patch.object(generator, 'client', mock_client):
        result = await generator.generate_answer(
            query="Tell me about your inventory",
            context_documents=empty_docs
        )
        
        answer = result["answer"].lower()
        
        # Should handle gracefully
        assert "don't" in answer or "no" in answer or "not" in answer

