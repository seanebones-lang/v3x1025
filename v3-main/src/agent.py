"""
Agentic RAG system with intent classification and tool calling.
Routes queries to specialized agents for sales, service, inventory, and predictive tasks.
"""

import asyncio
import logging
import re
from enum import Enum
from typing import Any, Optional

from anthropic import AsyncAnthropic
from langchain.schema import Document

from src.config import get_config
from src.dms.base import BaseDMSAdapter
from src.dms.cdk_adapter import CDKAdapter
from src.dms.mock_adapter import MockDMSAdapter
from src.dms.reynolds_adapter import ReynoldsAdapter
from src.generate import AnswerGenerator
from src.models import AgentIntent
from src.retrieve import HybridRetriever

logger = logging.getLogger(__name__)


class IntentType(str, Enum):
    """Intent types for query classification."""

    SALES = "sales"
    SERVICE = "service"
    INVENTORY = "inventory"
    PREDICTIVE = "predictive"
    GENERAL = "general"


class AgenticRAG:
    """Main agentic RAG system with routing and tool calling."""

    # Intent classification prompt
    INTENT_CLASSIFICATION_PROMPT = """You are an intent classifier for a car dealership assistant. Classify the user's query into one of the following categories:

*   **SALES**: Asking about vehicle price, financing, availability, features, or making a purchase.
*   **SERVICE**: Asking about vehicle maintenance, repairs, appointments, or service history.
*   **INVENTORY**: General questions about what vehicles are in stock.
*   **PREDICTIVE**: Asking for forecasts, trends, or market analysis.
*   **GENERAL**: All other questions, including greetings and conversation.

Query: "{query}"

Format: CATEGORY|CONFIDENCE
Example: SALES|0.95"""

    def __init__(self):
        """Initialize the agentic RAG system."""
        self.config = get_config()
        self.anthropic_client = AsyncAnthropic(api_key=self.config.anthropic_api_key)
        self.retriever = HybridRetriever()
        self.generator = AnswerGenerator()

        # Initialize DMS adapter based on config
        self.dms_adapter = self._initialize_dms_adapter()

        # Agent-specific retrievers (can be expanded)
        self.agent_namespaces = {
            IntentType.SALES: "sales-knowledge-base",
            IntentType.SERVICE: "service-manuals",
            IntentType.INVENTORY: "default",  # Default inventory namespace
            IntentType.PREDICTIVE: "market-data",
            IntentType.GENERAL: "default",
        }

    def _initialize_dms_adapter(self) -> BaseDMSAdapter:
        """Initialize appropriate DMS adapter."""
        adapter_type = self.config.dms_adapter

        if adapter_type == "cdk":
            return CDKAdapter(api_key=self.config.cdk_api_key, api_url=self.config.cdk_api_url)
        elif adapter_type == "reynolds":
            return ReynoldsAdapter(
                api_key=self.config.reynolds_api_key,
                api_url=self.config.reynolds_api_url,
            )
        else:  # mock
            return MockDMSAdapter()

    async def classify_intent(self, query: str) -> AgentIntent:
        """
        Classify user query intent with Claude fallback to rule-based.

        Args:
            query: User query string

        Returns:
            AgentIntent object with classification results
        """
        try:
            # Try Claude-based classification first
            prompt = self.INTENT_CLASSIFICATION_PROMPT.format(query=query)

            async with asyncio.timeout(5.0):  # Prevent hangs on slow API
                response = await self.anthropic_client.messages.create(
                    model=self.config.anthropic_model,
                    max_tokens=20,
                    messages=[{"role": "user", "content": prompt}],
                )

            result = response.content[0].text.strip()

            # Parse result
            if "|" in result:
                intent, confidence_str = result.split("|")
                confidence = float(confidence_str)
            else:
                intent = result.strip().lower()
                confidence = 0.5

            # Map to IntentType
            intent_map = {
                "sales": IntentType.SALES,
                "service": IntentType.SERVICE,
                "inventory": IntentType.INVENTORY,
                "predictive": IntentType.PREDICTIVE,
                "general": IntentType.GENERAL,
            }

            intent_type = intent_map.get(intent, IntentType.GENERAL)

            return AgentIntent(
                intent=intent_type.value,
                confidence=confidence,
                sub_intent=None,  # Placeholder for future sub-intent logic
                entities={},  # Placeholder for NER
            )
        except Exception as e:
            logger.warning(f"Claude classification failed, using rule-based fallback: {e}")
            return self._rule_based_intent_classification(query)

    async def process_query(
        self,
        query: str,
        conversation_history: Optional[list[dict[str, str]]] = None,
        max_tokens: int = 100000,
    ) -> dict[str, Any]:
        """
        Process a query through the agentic RAG pipeline.

        Args:
            query: User query
            conversation_history: Optional conversation history

        Returns:
            Dictionary with answer, sources, and metadata
        """
        # Step 1: Classify intent
        intent = await self.classify_intent(query)

        # Step 2: Route to appropriate agent
        agent_result = await self._route_to_agent(query, intent)

        # Step 3: Retrieve relevant context
        namespace = self.agent_namespaces.get(IntentType(intent.intent), "default")

        context_documents = await self.retriever.retrieve(
            query=query,
            namespace=namespace,
            filters=self._extract_vehicle_filters(query),
            top_k=self.config.top_k_rerank,
        )

        # Step 4: Check if DMS tool call is needed
        if agent_result.get("needs_dms_call", False):
            dms_data = await self._call_dms_tools(query, intent)
            if dms_data:
                dms_doc = Document(
                    page_content=f"DMS Tool Result:\n{dms_data}",
                    metadata={
                        "source": "DMS",
                        "timestamp": "now",
                        "tool_called": dms_data.get("tool_name", "unknown"),
                    },
                )
                context_documents.insert(0, dms_doc)

        # Step 5: Generate answer
        generation_result = await self.generator.generate_answer(
            query=query,
            context_documents=context_documents,
            conversation_history=conversation_history,
        )

        # Step 6: Combine results
        return {
            "answer": generation_result["answer"],
            "sources": generation_result["sources"],
            "intent": intent.intent,
            "model_used": self.config.anthropic_model,
            "retrieval_method": "hybrid",
        }

    async def _route_to_agent(self, query: str, intent: AgentIntent) -> dict[str, Any]:
        """
        Route query to appropriate agent based on intent.

        Args:
            query: User query
            intent: Classified intent

        Returns:
            Agent-specific routing result
        """
        intent_type = IntentType(intent.intent)

        routing_info = {
            "agent": intent_type.value,
            "confidence": intent.confidence,
            "tools_available": [],
        }

        if intent_type == IntentType.SALES:
            routing_info["tools_available"] = [
                "get_pricing",
                "check_financing",
                "compare_vehicles",
            ]
            routing_info["needs_dms_call"] = True

        elif intent_type == IntentType.SERVICE:
            routing_info["tools_available"] = [
                "get_service_history",
                "schedule_appointment",
                "check_recall",
            ]
            routing_info["needs_dms_call"] = True

        elif intent_type == IntentType.INVENTORY:
            routing_info["tools_available"] = [
                "search_inventory",
                "check_availability",
                "get_vehicle_details",
            ]
            routing_info["needs_dms_call"] = True

        elif intent_type == IntentType.PREDICTIVE:
            routing_info["tools_available"] = [
                "forecast_demand",
                "predict_maintenance",
                "analyze_trends",
            ]
            routing_info["needs_dms_call"] = False

        else:  # GENERAL
            routing_info["tools_available"] = []
            routing_info["needs_dms_call"] = False

        return routing_info

    async def _call_dms_tools(
        self, query: str, intent: AgentIntent
    ) -> Optional[dict[str, Any]]:
        """
        Call appropriate DMS tools based on query and intent with timeout protection.

        Args:
            query: User query
            intent: Classified intent

        Returns:
            DMS data or None
        """
        intent_type = IntentType(intent.intent)

        # Log tool call for production tracing
        logger.info(
            f"DMS tool call initiated - Intent: {intent_type.value}, Query: {query[:50]}..."
        )


        try:
            async with asyncio.timeout(10.0):
                if intent_type == IntentType.INVENTORY:
                    # For inventory queries, get all vehicles and let RAG filter
                    vehicles = await self.dms_adapter.get_inventory()
                    return {
                        "tool_name": "get_inventory",
                        "result": [v.model_dump() for v in vehicles],
                    }

                elif intent_type == IntentType.SERVICE:
                    # For service queries, get sample service data
                    # In a real system, this would parse a VIN or customer ID
                    vin = "VIN12345"  # Mock VIN
                    await self.dms_adapter.get_service_history(vin)
                    return {
                        "tool_name": "get_service_history",
                        "result": "Service information retrieved from DMS",
                    }

                elif intent_type == IntentType.SALES:
                    # Get sales-related data
                    vehicles = await self.dms_adapter.get_inventory(limit=5)
                    return {
                        "tool_name": "get_sales_info",
                        "result": [v.model_dump() for v in vehicles],
                    }

                return None
        except TimeoutError:
            logger.error(f"DMS tool call timeout after 10s - Intent: {intent_type.value}")
            return {
                "tool_name": "dms_tool_call",
                "error": "DMS tool call timed out.",
            }
        except Exception as e:
            logger.error(f"DMS tool call failed: {e}")
            return {
                "tool_name": "dms_tool_call",
                "error": str(e),
            }

    def _rule_based_intent_classification(self, query: str) -> AgentIntent:
        """
        Fallback rule-based intent classification (offline/low-cost mode).

        Args:
            query: User query string

        Returns:
            AgentIntent object
        """
        query_lower = query.lower()

        # Sales keywords
        if any(
            keyword in query_lower
            for keyword in [
                "price",
                "cost",
                "finance",
                "payment",
                "deal",
                "buy",
                "purchase",
            ]
        ):
            return AgentIntent(
                intent=IntentType.SALES.value,
                confidence=0.75,
                sub_intent="pricing",
                entities={},
            )

        # Service keywords
        if any(
            keyword in query_lower
            for keyword in [
                "service",
                "repair",
                "maintenance",
                "oil change",
                "tire",
                "brake",
                "appointment",
            ]
        ):
            return AgentIntent(
                intent=IntentType.SERVICE.value,
                confidence=0.75,
                sub_intent="maintenance",
                entities={},
            )

        # Inventory keywords
        if any(
            keyword in query_lower
            for keyword in [
                "available",
                "stock",
                "inventory",
                "have",
                "show me",
                "find",
                "vin",
            ]
        ):
            return AgentIntent(
                intent=IntentType.INVENTORY.value,
                confidence=0.75,
                sub_intent="availability",
                entities={},
            )

        # Predictive keywords
        if any(
            keyword in query_lower
            for keyword in [
                "forecast",
                "predict",
                "trend",
                "demand",
                "analytics",
                "future",
                "projection",
            ]
        ):
            return AgentIntent(
                intent=IntentType.PREDICTIVE.value,
                confidence=0.75,
                sub_intent="forecast",
                entities={},
            )

        # Default to general
        return AgentIntent(
            intent=IntentType.GENERAL.value,
            confidence=0.6,
            sub_intent=None,
            entities={},
        )

    @staticmethod
    def _extract_vehicle_filters(query: str) -> dict[str, Any]:
        """
        Extract vehicle filters from natural language query.

        Args:
            query: User query

        Returns:
            Dictionary of filters
        """
        filters = {}
        query_lower = query.lower()

        # Extract make (simplified)
        makes = ["toyota", "honda", "ford", "chevrolet", "tesla", "bmw", "mercedes"]
        for make in makes:
            if make in query_lower:
                filters["make"] = make.capitalize()

        # Extract year

        year_match = re.search(r"\b(20\d{2})\b", query)
        if year_match:
            filters["year"] = int(year_match.group(1))

        # Extract price range
        if "under" in query_lower:
            price_match = re.search(r"under \$?(\d{1,3}(,\d{3})*|\d+)", query_lower)
            if price_match:
                price_str = price_match.group(1).replace(",", "")
                price = int(price_str)
                if price < 200:  # Assume 'under 50' means '$50,000'
                    price *= 1000
                filters["max_price"] = price

        # Extract fuel type
        fuel_types = ["electric", "hybrid", "diesel", "gasoline"]
        for fuel in fuel_types:
            if fuel in query_lower:
                filters["fuel_type"] = fuel.capitalize()

        return filters

    async def get_agent_stats(self) -> dict[str, Any]:
        """
        Get statistics about the agent system.

        Returns:
            Dictionary with stats
        """
        retriever_stats = self.retriever.get_stats()
        dms_health = await self.dms_adapter.health_check()

        return {
            "retriever_stats": retriever_stats,
            "dms_health": dms_health,
            "active_agents": [e.value for e in IntentType],
        }