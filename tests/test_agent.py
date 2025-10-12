"""
Tests for agentic RAG system with intent classification and routing.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock

from src.agent import AgenticRAG, IntentType
from src.models import AgentIntent


@pytest.mark.asyncio
async def test_classify_intent_sales(mock_anthropic_client):
    """Test intent classification for sales queries."""
    agent = AgenticRAG()
    
    with patch.object(agent.claude, 'messages', mock_anthropic_client.messages):
        # Mock response for sales intent
        mock_anthropic_client.messages.create.return_value = Mock(
            content=[Mock(text="SALES|0.95")]
        )
        
        intent = await agent.classify_intent("How much does the Toyota Camry cost?")
        
        assert intent.intent == "sales"
        assert intent.confidence >= 0.9


@pytest.mark.asyncio
async def test_classify_intent_service(mock_anthropic_client):
    """Test intent classification for service queries."""
    agent = AgenticRAG()
    
    with patch.object(agent.claude, 'messages', mock_anthropic_client.messages):
        mock_anthropic_client.messages.create.return_value = Mock(
            content=[Mock(text="SERVICE|0.92")]
        )
        
        intent = await agent.classify_intent("When should I get an oil change?")
        
        assert intent.intent == "service"
        assert intent.confidence >= 0.9


@pytest.mark.asyncio
async def test_classify_intent_inventory(mock_anthropic_client):
    """Test intent classification for inventory queries."""
    agent = AgenticRAG()
    
    with patch.object(agent.claude, 'messages', mock_anthropic_client.messages):
        mock_anthropic_client.messages.create.return_value = Mock(
            content=[Mock(text="INVENTORY|0.88")]
        )
        
        intent = await agent.classify_intent("Do you have any electric vehicles in stock?")
        
        assert intent.intent == "inventory"


@pytest.mark.asyncio
async def test_classify_intent_fallback(mock_anthropic_client):
    """Test intent classification fallback on error."""
    agent = AgenticRAG()
    
    with patch.object(agent.claude, 'messages', mock_anthropic_client.messages):
        mock_anthropic_client.messages.create.side_effect = Exception("API Error")
        
        intent = await agent.classify_intent("Random query")
        
        # Should fallback to GENERAL
        assert intent.intent == "general"
        assert "error" in intent.entities


@pytest.mark.asyncio
async def test_route_to_agent_sales():
    """Test routing for sales intent."""
    agent = AgenticRAG()
    
    intent = AgentIntent(intent="sales", confidence=0.9, sub_intent=None, entities={})
    
    result = await agent._route_to_agent("pricing query", intent)
    
    assert result["agent"] == "sales"
    assert result["needs_dms_call"] is True
    assert "get_pricing" in result["tools_available"]


@pytest.mark.asyncio
async def test_route_to_agent_inventory():
    """Test routing for inventory intent."""
    agent = AgenticRAG()
    
    intent = AgentIntent(intent="inventory", confidence=0.9, sub_intent=None, entities={})
    
    result = await agent._route_to_agent("vehicle availability", intent)
    
    assert result["agent"] == "inventory"
    assert result["needs_dms_call"] is True
    assert "search_inventory" in result["tools_available"]


@pytest.mark.asyncio
async def test_call_dms_tools_inventory(mock_dms_adapter):
    """Test calling DMS tools for inventory queries."""
    agent = AgenticRAG()
    agent.dms_adapter = mock_dms_adapter
    
    intent = AgentIntent(intent="inventory", confidence=0.9, sub_intent=None, entities={})
    
    result = await agent._call_dms_tools("Toyota Camry", intent)
    
    assert result is not None
    assert result["tool"] == "get_inventory"
    assert "result" in result


@pytest.mark.asyncio
async def test_extract_vehicle_filters():
    """Test extracting filters from natural language."""
    agent = AgenticRAG()
    
    # Test make extraction
    filters = agent._extract_vehicle_filters("Show me Toyota vehicles")
    assert filters.get("make") == "Toyota"
    
    # Test year extraction
    filters = agent._extract_vehicle_filters("2024 models")
    assert filters.get("year") == 2024
    
    # Test price extraction
    filters = agent._extract_vehicle_filters("cars under $30k")
    assert filters.get("max_price") == 30000
    
    # Test fuel type extraction
    filters = agent._extract_vehicle_filters("electric vehicles")
    assert filters.get("fuel_type") == "Electric"


@pytest.mark.asyncio
async def test_process_query_end_to_end(
    mock_anthropic_client,
    mock_voyage_client,
    mock_pinecone_index,
    mock_dms_adapter,
    sample_documents
):
    """Test complete query processing pipeline."""
    agent = AgenticRAG()
    agent.dms_adapter = mock_dms_adapter
    
    # Mock all the components
    with patch.object(agent.claude, 'messages', mock_anthropic_client.messages), \
         patch.object(agent.retriever.embedding_manager, 'voyage_client', mock_voyage_client), \
         patch.object(agent.retriever.embedding_manager, 'index', mock_pinecone_index), \
         patch.object(agent.generator.client, 'messages', mock_anthropic_client.messages):
        
        # Mock intent classification
        mock_anthropic_client.messages.create.return_value = Mock(
            content=[Mock(text="SALES|0.95")],
            usage=Mock(input_tokens=100, output_tokens=50)
        )
        
        # Mock generation
        async def mock_create(*args, **kwargs):
            if "SALES" in str(args) or "classify" in str(kwargs):
                return Mock(content=[Mock(text="SALES|0.95")])
            return Mock(
                content=[Mock(text="Test answer [Source: test.pdf]")],
                usage=Mock(input_tokens=100, output_tokens=50)
            )
        
        mock_anthropic_client.messages.create.side_effect = mock_create
        
        result = await agent.process_query("How much is the Toyota Camry?")
        
        assert "answer" in result
        assert "intent" in result
        assert result["intent"] == "sales"


@pytest.mark.asyncio
async def test_get_agent_stats(mock_dms_adapter, mock_pinecone_index):
    """Test getting agent statistics."""
    agent = AgenticRAG()
    agent.dms_adapter = mock_dms_adapter
    
    with patch.object(agent.retriever.embedding_manager, 'index', mock_pinecone_index):
        stats = await agent.get_agent_stats()
        
        assert "retriever_stats" in stats
        assert "dms_adapter" in stats
        assert "dms_healthy" in stats
        assert "available_intents" in stats


@pytest.mark.asyncio
async def test_dms_tool_error_handling():
    """Test DMS tool error handling."""
    agent = AgenticRAG()
    
    # Mock DMS adapter that raises errors
    mock_adapter = Mock()
    mock_adapter.get_inventory = AsyncMock(side_effect=Exception("DMS Error"))
    agent.dms_adapter = mock_adapter
    
    intent = AgentIntent(intent="inventory", confidence=0.9, sub_intent=None, entities={})
    
    result = await agent._call_dms_tools("test query", intent)
    
    # Should return error info
    assert result is not None
    assert "error" in result


def test_intent_type_enum():
    """Test IntentType enum values."""
    assert IntentType.SALES.value == "sales"
    assert IntentType.SERVICE.value == "service"
    assert IntentType.INVENTORY.value == "inventory"
    assert IntentType.PREDICTIVE.value == "predictive"
    assert IntentType.GENERAL.value == "general"


@pytest.mark.asyncio
async def test_process_query_with_conversation_history(
    mock_anthropic_client,
    mock_voyage_client,
    mock_pinecone_index,
    mock_dms_adapter
):
    """Test query processing with conversation history."""
    agent = AgenticRAG()
    agent.dms_adapter = mock_dms_adapter
    
    conversation_history = [
        {"role": "user", "content": "Tell me about Toyota"},
        {"role": "assistant", "content": "Toyota makes reliable vehicles"}
    ]
    
    with patch.object(agent.claude, 'messages', mock_anthropic_client.messages), \
         patch.object(agent.retriever.embedding_manager, 'voyage_client', mock_voyage_client), \
         patch.object(agent.retriever.embedding_manager, 'index', mock_pinecone_index), \
         patch.object(agent.generator.client, 'messages', mock_anthropic_client.messages):
        
        mock_anthropic_client.messages.create.return_value = Mock(
            content=[Mock(text="GENERAL|0.8")],
            usage=Mock(input_tokens=150, output_tokens=75)
        )
        
        result = await agent.process_query(
            "What about their prices?",
            conversation_history=conversation_history
        )
        
        assert "answer" in result

