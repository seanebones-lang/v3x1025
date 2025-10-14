"""
Answer generation service using Anthropic Claude.
Handles context-aware response generation with conversation history and source attribution.
"""

import asyncio
import json
import logging
import time
from typing import Any, Optional

from anthropic import AsyncAnthropic
from langchain.schema import Document

from .config import get_config

logger = logging.getLogger(__name__)


class GenerationError(Exception):
    """Custom exception for generation-related errors."""
    pass


class AnswerGenerator:
    """Production-ready answer generation service with Claude."""

    # System prompt for automotive dealership RAG
    SYSTEM_PROMPT = """You are an expert automotive assistant for a large dealership network. Your role is to provide accurate, helpful, and professional responses to customer inquiries about vehicles, services, and dealership operations.

Key Guidelines:
- Always base your answers on the provided context documents
- If information isn't in the context, clearly state what you don't know
- For vehicle recommendations, consider customer needs and budget
- Provide specific details like VINs, prices, and features when available
- Be concise but comprehensive
- Use professional but friendly tone
- For service questions, emphasize safety and manufacturer recommendations
- Always cite your sources when making specific claims

If you cannot answer a question based on the provided context, suggest how the customer can get the information they need (contact sales, service department, etc.)."""

    def __init__(self):
        """Initialize the answer generation service."""
        self.config = get_config()
        
        if not self.config.anthropic_api_key:
            raise GenerationError("Anthropic API key not configured")
            
        self.client = AsyncAnthropic(api_key=self.config.anthropic_api_key)
        
        # Performance tracking
        self.total_generations = 0
        self.total_tokens_used = 0
        self.generation_time = 0.0
        self.error_count = 0

    def _build_context_string(self, documents: list[Document]) -> str:
        """
        Build context string from retrieved documents.
        
        Args:
            documents: List of relevant documents
            
        Returns:
            Formatted context string
        """
        if not documents:
            return "No relevant context found."

        context_parts = []
        
        for i, doc in enumerate(documents, 1):
            # Extract source information
            source = doc.metadata.get("source", "Unknown")
            score = doc.metadata.get("rerank_score") or doc.metadata.get("vector_score", 0)
            
            # Format document
            context_part = f"""[Document {i}]
Source: {source}
Relevance Score: {score:.3f}
Content: {doc.page_content.strip()}
---"""
            context_parts.append(context_part)
        
        return "\n\n".join(context_parts)

    def _build_conversation_context(
        self, 
        conversation_history: Optional[list[dict[str, str]]]
    ) -> str:
        """
        Build conversation context from history.
        
        Args:
            conversation_history: List of previous exchanges
            
        Returns:
            Formatted conversation string
        """
        if not conversation_history:
            return ""

        context_parts = ["Previous Conversation:"]
        
        for exchange in conversation_history[-5:]:  # Last 5 exchanges
            if "user" in exchange and "assistant" in exchange:
                context_parts.append(f"Customer: {exchange['user']}")
                context_parts.append(f"Assistant: {exchange['assistant']}")
                context_parts.append("---")
        
        return "\n".join(context_parts)

    def _extract_sources(self, documents: list[Document]) -> list[dict[str, Any]]:
        """
        Extract source information from documents.
        
        Args:
            documents: Source documents
            
        Returns:
            List of source metadata
        """
        sources = []
        
        for i, doc in enumerate(documents):
            source_info = {
                "index": i + 1,
                "source": doc.metadata.get("source", "Unknown"),
                "relevance_score": (
                    doc.metadata.get("rerank_score") or 
                    doc.metadata.get("vector_score", 0)
                ),
                "content_preview": doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content,
                "metadata": {
                    key: value for key, value in doc.metadata.items()
                    if key in ["chunk_index", "timestamp", "search_type", "final_rank"]
                }
            }
            sources.append(source_info)
        
        return sources

    async def generate_answer(
        self,
        query: str,
        context_documents: list[Document],
        conversation_history: Optional[list[dict[str, str]]] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        """
        Generate answer using Claude with context and conversation history.
        
        Args:
            query: User's question
            context_documents: Relevant documents from retrieval
            conversation_history: Previous conversation exchanges
            max_tokens: Maximum tokens to generate
            temperature: Generation temperature
            
        Returns:
            Dictionary with answer, sources, and metadata
        """
        start_time = time.time()
        max_tokens = max_tokens or self.config.max_tokens_generation
        
        try:
            # Build context components
            context_string = self._build_context_string(context_documents)
            conversation_context = self._build_conversation_context(conversation_history)
            
            # Construct user message
            user_message_parts = []
            
            if conversation_context:
                user_message_parts.append(conversation_context)
                user_message_parts.append("\n" + "="*50 + "\n")
            
            user_message_parts.append("Context Documents:")
            user_message_parts.append(context_string)
            user_message_parts.append("\n" + "="*50 + "\n")
            user_message_parts.append(f"Customer Question: {query}")
            user_message_parts.append("\nPlease provide a helpful and accurate response based on the context above.")
            
            user_message = "\n\n".join(user_message_parts)
            
            # Generate response with timeout
            async with asyncio.timeout(self.config.query_timeout_seconds):
                response = await self.client.messages.create(
                    model=self.config.anthropic_model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=self.SYSTEM_PROMPT,
                    messages=[{
                        "role": "user",
                        "content": user_message
                    }]
                )
            
            # Extract answer
            answer = response.content[0].text
            
            # Track usage
            self.total_generations += 1
            self.total_tokens_used += response.usage.input_tokens + response.usage.output_tokens
            generation_time = time.time() - start_time
            self.generation_time += generation_time
            
            # Extract sources
            sources = self._extract_sources(context_documents)
            
            return {
                "answer": answer,
                "sources": sources,
                "model_used": self.config.anthropic_model,
                "tokens_used": {
                    "input": response.usage.input_tokens,
                    "output": response.usage.output_tokens,
                    "total": response.usage.input_tokens + response.usage.output_tokens,
                },
                "generation_time_ms": generation_time * 1000,
                "temperature": temperature,
                "context_documents_count": len(context_documents),
            }
            
        except asyncio.TimeoutError:
            self.error_count += 1
            logger.error(f"Answer generation timed out after {self.config.query_timeout_seconds}s")
            raise GenerationError("Answer generation timed out")
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"Answer generation failed: {e}")
            raise GenerationError(f"Failed to generate answer: {str(e)}")

    async def generate_follow_up_questions(
        self,
        query: str,
        answer: str,
        context_documents: list[Document],
    ) -> list[str]:
        """
        Generate relevant follow-up questions based on the query and answer.
        
        Args:
            query: Original query
            answer: Generated answer
            context_documents: Context used for answer
            
        Returns:
            List of follow-up questions
        """
        try:
            follow_up_prompt = f"""Based on this customer inquiry and response, suggest 3 relevant follow-up questions that the customer might want to ask next.

Original Question: {query}
Response: {answer}

Generate questions that are:
1. Naturally related to the original inquiry
2. Helpful for the customer's car buying/service journey  
3. Specific enough to be actionable

Return only the questions, one per line, without numbering."""

            response = await self.client.messages.create(
                model=self.config.anthropic_model,
                max_tokens=200,
                temperature=0.3,
                messages=[{
                    "role": "user",
                    "content": follow_up_prompt
                }]
            )
            
            # Parse questions
            questions = [
                q.strip() 
                for q in response.content[0].text.split('\n') 
                if q.strip() and not q.strip().startswith(('1.', '2.', '3.'))
            ]
            
            return questions[:3]  # Limit to 3 questions
            
        except Exception as e:
            logger.warning(f"Follow-up question generation failed: {e}")
            return []

    async def summarize_conversation(
        self,
        conversation_history: list[dict[str, str]],
        max_length: int = 300,
    ) -> str:
        """
        Generate a summary of the conversation history.
        
        Args:
            conversation_history: List of conversation exchanges
            max_length: Maximum summary length
            
        Returns:
            Conversation summary
        """
        try:
            if not conversation_history or len(conversation_history) < 2:
                return ""

            # Build conversation string
            conversation_text = []
            for exchange in conversation_history:
                if "user" in exchange and "assistant" in exchange:
                    conversation_text.append(f"Customer: {exchange['user']}")
                    conversation_text.append(f"Assistant: {exchange['assistant']}")
            
            conversation_string = "\n".join(conversation_text)
            
            summary_prompt = f"""Summarize this customer service conversation in {max_length} characters or less. Focus on:
1. Main topics discussed
2. Customer needs identified
3. Key recommendations made

Conversation:
{conversation_string}

Summary:"""

            response = await self.client.messages.create(
                model=self.config.anthropic_model,
                max_tokens=max_length // 3,  # Rough token estimate
                temperature=0.1,
                messages=[{
                    "role": "user",
                    "content": summary_prompt
                }]
            )
            
            return response.content[0].text.strip()
            
        except Exception as e:
            logger.warning(f"Conversation summarization failed: {e}")
            return "Conversation summary unavailable"

    def get_stats(self) -> dict[str, Any]:
        """Get generation service statistics."""
        avg_generation_time = self.generation_time / max(1, self.total_generations)
        avg_tokens_per_request = self.total_tokens_used / max(1, self.total_generations)
        error_rate = self.error_count / max(1, self.total_generations)

        return {
            "total_generations": self.total_generations,
            "total_tokens_used": self.total_tokens_used,
            "error_count": self.error_count,
            "error_rate": error_rate,
            "avg_generation_time_ms": avg_generation_time * 1000,
            "avg_tokens_per_request": avg_tokens_per_request,
            "model": self.config.anthropic_model,
        }

    async def health_check(self) -> dict[str, Any]:
        """Perform health check on generation service."""
        health = {
            "service": "generation",
            "status": "healthy",
            "timestamp": int(time.time()),
        }

        try:
            # Test generation with minimal query
            test_response = await self.client.messages.create(
                model=self.config.anthropic_model,
                max_tokens=10,
                messages=[{"role": "user", "content": "Test health check"}]
            )
            
            health["api_available"] = True
            health["model"] = self.config.anthropic_model
            
        except Exception as e:
            health["status"] = "unhealthy"
            health["api_available"] = False
            health["error"] = str(e)

        return health