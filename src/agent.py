"""
Agentic RAG system with intent classification and tool calling.
Routes queries to specialized agents for sales, service, inventory, and predictive tasks.
"""

import logging
from typing import Dict, Any, List, Optional, Literal
from enum import Enum

from anthropic import AsyncAnthropic
from langchain.schema import Document

from src.config import settings

# Configure logging for production tracing
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
from src.models import AgentIntent, AgentAction
from src.dms import MockDMSAdapter, CDKAdapter, ReynoldsAdapter, BaseDMSAdapter
from src.retrieve import HybridRetriever
from src.generate import AnswerGenerator


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
    INTENT_CLASSIFICATION_PROMPT = """You are an intent classifier for a car dealership assistant. Classify the user's query into one of these categories:

1. SALES - Questions about buying, pricing, financing, trade-ins, deals
2. SERVICE - Questions about repairs, maintenance, service appointments, recalls
3. INVENTORY - Questions about vehicle availability, specifications, features, stock
4. PREDICTIVE - Questions about trends, forecasts, recommendations, analytics
5. GENERAL - General questions, greetings, or unclear intents

User Query: {query}

Respond with ONLY the category name (SALES, SERVICE, INVENTORY, PREDICTIVE, or GENERAL) and a confidence score 0-1.

Format: CATEGORY|CONFIDENCE
Example: SALES|0.95"""
    
    def __init__(self):
        """Initialize the agentic RAG system."""
        self.claude = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.retriever = HybridRetriever()
        self.generator = AnswerGenerator()
        
        # Initialize DMS adapter based on config
        self.dms_adapter = self._initialize_dms_adapter()
        
        # Agent-specific retrievers (can be expanded)
        self.agent_namespaces = {
            IntentType.SALES: "sales",
            IntentType.SERVICE: "service",
            IntentType.INVENTORY: "inventory",
            IntentType.PREDICTIVE: "predictive",
            IntentType.GENERAL: "default"
        }
    
    def _initialize_dms_adapter(self) -> BaseDMSAdapter:
        """Initialize appropriate DMS adapter."""
        adapter_type = settings.dms_adapter
        
        if adapter_type == "cdk":
            return CDKAdapter(
                api_key=settings.cdk_api_key,
                api_url=settings.cdk_api_url
            )
        elif adapter_type == "reynolds":
            return ReynoldsAdapter(
                api_key=settings.reynolds_api_key,
                api_url=settings.reynolds_api_url
            )
        else:  # mock
            return MockDMSAdapter()
    
    async def classify_intent(self, query: str) -> AgentIntent:
        """
        Classify user query intent.
        
        Args:
            query: User query string
            
        Returns:
            AgentIntent object with classification results
        """
        try:
            prompt = self.INTENT_CLASSIFICATION_PROMPT.format(query=query)
            
            response = await self.claude.messages.create(
                model="claude-4.5-sonnet-20241022",
                max_tokens=50,
                messages=[{"role": "user", "content": prompt}]
            )
            
            result = response.content[0].text.strip()
            
            # Parse result
            if "|" in result:
                intent_str, confidence_str = result.split("|")
                intent = intent_str.strip().lower()
                confidence = float(confidence_str.strip())
            else:
                intent = result.strip().lower()
                confidence = 0.5
            
            # Map to IntentType
            intent_map = {
                "sales": IntentType.SALES,
                "service": IntentType.SERVICE,
                "inventory": IntentType.INVENTORY,
                "predictive": IntentType.PREDICTIVE,
                "general": IntentType.GENERAL
            }
            
            intent_type = intent_map.get(intent, IntentType.GENERAL)
            
            return AgentIntent(
                intent=intent_type.value,
                confidence=confidence,
                sub_intent=None,
                entities={}
            )
        except Exception as e:
            # Default to general on error
            return AgentIntent(
                intent=IntentType.GENERAL.value,
                confidence=0.5,
                sub_intent=None,
                entities={"error": str(e)}
            )
    
    async def process_query(
        self,
        query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
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
        namespace = self.agent_namespaces.get(
            IntentType(intent.intent),
            "default"
        )
        
        context_documents = await self.retriever.retrieve(
            query=query,
            namespace=namespace,
            top_k=settings.top_k_rerank
        )
        
        # Step 4: Check if DMS tool call is needed
        if agent_result.get("needs_dms_call", False):
            dms_data = await self._call_dms_tools(query, intent)
            # Add DMS data to context
            if dms_data:
                dms_doc = Document(
                    page_content=str(dms_data),
                    metadata={
                        "source": "DMS",
                        "document_type": "live_data",
                        "intent": intent.intent
                    }
                )
                context_documents.insert(0, dms_doc)
        
        # Step 5: Generate answer
        generation_result = await self.generator.generate_answer(
            query=query,
            context_documents=context_documents,
            conversation_history=conversation_history
        )
        
        # Step 6: Combine results
        return {
            **generation_result,
            "intent": intent.intent,
            "intent_confidence": intent.confidence,
            "agent_result": agent_result,
            "retrieval_method": "hybrid"
        }
    
    async def _route_to_agent(
        self,
        query: str,
        intent: AgentIntent
    ) -> Dict[str, Any]:
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
            "needs_dms_call": False,
            "tools_available": []
        }
        
        if intent_type == IntentType.SALES:
            routing_info["tools_available"] = ["get_pricing", "check_financing", "compare_vehicles"]
            routing_info["needs_dms_call"] = True
            
        elif intent_type == IntentType.SERVICE:
            routing_info["tools_available"] = ["get_service_history", "schedule_appointment", "check_recall"]
            routing_info["needs_dms_call"] = True
            
        elif intent_type == IntentType.INVENTORY:
            routing_info["tools_available"] = ["search_inventory", "check_availability", "get_vehicle_details"]
            routing_info["needs_dms_call"] = True
            
        elif intent_type == IntentType.PREDICTIVE:
            routing_info["tools_available"] = ["forecast_demand", "predict_maintenance", "analyze_trends"]
            routing_info["needs_dms_call"] = False
            
        else:  # GENERAL
            routing_info["tools_available"] = []
            routing_info["needs_dms_call"] = False
        
        return routing_info
    
    async def _call_dms_tools(
        self,
        query: str,
        intent: AgentIntent
    ) -> Optional[Dict[str, Any]]:
        """
        Call appropriate DMS tools based on query and intent.
        
        Args:
            query: User query
            intent: Classified intent
            
        Returns:
            DMS data or None
        """
        intent_type = IntentType(intent.intent)
        
        # Log tool call for production tracing
        logger.info(f"DMS tool call initiated - Intent: {intent_type.value}, Query: {query[:50]}...")
        
        try:
            if intent_type == IntentType.INVENTORY:
                # Extract vehicle filters from query (simplified)
                filters = self._extract_vehicle_filters(query)
                vehicles = await self.dms_adapter.get_inventory(filters=filters, limit=10)
                logger.info(f"DMS inventory retrieved: {len(vehicles)} vehicles with filters {filters}")
                return {
                    "tool": "get_inventory",
                    "result": [v.model_dump() for v in vehicles[:5]]
                }
            
            elif intent_type == IntentType.SERVICE:
                # For service queries, get sample service data
                # In production, would extract VIN from query
                return {
                    "tool": "service_info",
                    "result": "Service information retrieved from DMS"
                }
            
            elif intent_type == IntentType.SALES:
                # Get sales-related data
                vehicles = await self.dms_adapter.get_inventory(limit=5)
                return {
                    "tool": "sales_inventory",
                    "result": [v.model_dump() for v in vehicles]
                }
            
            return None
        except Exception as e:
            return {
                "tool": "error",
                "error": str(e)
            }
    
    @staticmethod
    def _extract_vehicle_filters(query: str) -> Dict[str, Any]:
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
        import re
        year_match = re.search(r'\b(20\d{2})\b', query)
        if year_match:
            filters["year"] = int(year_match.group(1))
        
        # Extract price range
        if "under" in query_lower:
            price_match = re.search(r'under\s+\$?(\d+)k?', query_lower)
            if price_match:
                price = int(price_match.group(1))
                if price < 1000:  # Likely in thousands
                    price *= 1000
                filters["max_price"] = price
        
        # Extract fuel type
        fuel_types = ["electric", "hybrid", "diesel", "gasoline"]
        for fuel in fuel_types:
            if fuel in query_lower:
                filters["fuel_type"] = fuel.capitalize()
        
        return filters
    
    async def get_agent_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the agent system.
        
        Returns:
            Dictionary with stats
        """
        retriever_stats = self.retriever.get_stats()
        dms_health = await self.dms_adapter.health_check()
        
        return {
            "retriever_stats": retriever_stats,
            "dms_adapter": settings.dms_adapter,
            "dms_healthy": dms_health,
            "available_intents": [intent.value for intent in IntentType],
            "namespaces": self.agent_namespaces
        }

