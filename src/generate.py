"""
Answer generation with Claude 4.5 Sonnet.
Includes prompt templates, source attribution, and anti-hallucination measures.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime

from anthropic import AsyncAnthropic
from langchain.schema import Document

from src.config import settings


class AnswerGenerator:
    """Generate answers using Claude with source attribution."""
    
    # System prompt for Claude
    SYSTEM_PROMPT = """You are an expert automotive dealership assistant with deep knowledge of vehicle specifications, dealership operations, service procedures, and customer service.

Your responsibilities:
1. Answer questions ONLY using the provided context documents
2. Never invent or hallucinate information
3. Always cite your sources using [Source: ...] notation
4. If the context doesn't contain enough information, clearly state that
5. Be concise, professional, and customer-focused
6. For vehicle queries, provide specific details like VIN, price, specifications
7. For service questions, reference exact procedures from manuals

Key principles:
- FACTUAL ONLY: Only use information from the provided sources
- CITE SOURCES: Every factual statement must reference its source
- ADMIT LIMITATIONS: If unsure or lacking information, say so explicitly
- BE SPECIFIC: Use exact numbers, VINs, model names, not generalizations
- CUSTOMER FIRST: Prioritize helpfulness while maintaining accuracy"""
    
    # User prompt template
    USER_PROMPT_TEMPLATE = """Context Documents:
{context}

Customer Question: {query}

Instructions:
1. Analyze the context documents carefully
2. Answer the question using ONLY information from the context
3. Cite sources for each factual claim using [Source: document_name]
4. If the context doesn't answer the question, say: "I don't have that specific information in my current knowledge base."
5. Be specific and include relevant details (VIN, prices, specs, etc.)

Your Answer:"""
    
    def __init__(self, temperature: float = 0.2):
        """
        Initialize the answer generator with Claude client.
        
        Args:
            temperature: Generation temperature (0.0-1.0). Lower = more factual.
                        Default 0.2 balances naturalness with factual accuracy.
        """
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = "claude-4.5-sonnet-20241022"
        self.max_tokens = settings.max_tokens_generation
        self.temperature = temperature
    
    async def generate_answer(
        self,
        query: str,
        context_documents: List[Document],
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Generate an answer using Claude with context.
        
        Args:
            query: User query
            context_documents: Retrieved context documents
            conversation_history: Optional conversation history
            
        Returns:
            Dictionary with answer, sources, and metadata
        """
        start_time = datetime.now()
        
        # Format context from documents
        context_text = self._format_context(context_documents)
        
        # Build user prompt
        user_prompt = self.USER_PROMPT_TEMPLATE.format(
            context=context_text,
            query=query
        )
        
        # Build messages
        messages = []
        
        # Add conversation history if available (truncate to last 5 turns to avoid token blowout)
        if conversation_history:
            truncated_history = conversation_history[-10:]  # Last 5 turns = 10 messages (user + assistant)
            messages.extend(truncated_history)
        
        # Add current query
        messages.append({
            "role": "user",
            "content": user_prompt
        })
        
        try:
            # Call Claude API with temperature for natural responses
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,  # 0.2 = factual but natural
                system=self.SYSTEM_PROMPT,
                messages=messages
            )
            
            # Extract answer
            answer = response.content[0].text
            
            # Calculate processing time
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            
            # Extract source citations
            sources = self._extract_sources(answer, context_documents)
            
            return {
                "answer": answer,
                "sources": sources,
                "model": self.model,
                "processing_time_ms": processing_time,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "context_docs_count": len(context_documents)
            }
        except Exception as e:
            return {
                "answer": f"I apologize, but I encountered an error processing your query: {str(e)}",
                "sources": [],
                "model": self.model,
                "processing_time_ms": 0,
                "error": str(e)
            }
    
    async def generate_streaming_answer(
        self,
        query: str,
        context_documents: List[Document],
        conversation_history: Optional[List[Dict[str, str]]] = None
    ):
        """
        Generate an answer with streaming response.
        
        Args:
            query: User query
            context_documents: Retrieved context documents
            conversation_history: Optional conversation history
            
        Yields:
            Chunks of the generated answer
        """
        # Format context
        context_text = self._format_context(context_documents)
        
        # Build user prompt
        user_prompt = self.USER_PROMPT_TEMPLATE.format(
            context=context_text,
            query=query
        )
        
        # Build messages
        messages = []
        if conversation_history:
            messages.extend(conversation_history)
        messages.append({
            "role": "user",
            "content": user_prompt
        })
        
        try:
            # Stream response from Claude
            async with self.client.messages.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                system=self.SYSTEM_PROMPT,
                messages=messages
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception as e:
            yield f"Error: {str(e)}"
    
    @staticmethod
    def _format_context(documents: List[Document]) -> str:
        """
        Format context documents for the prompt with multi-source merging.
        Merges related documents from same source for concise context.
        
        Args:
            documents: List of Document objects
            
        Returns:
            Formatted context string
        """
        if not documents:
            return "No context documents available."
        
        # Group documents by source for potential merging
        source_groups = {}
        for doc in documents:
            source = doc.metadata.get("source", "Unknown")
            if source not in source_groups:
                source_groups[source] = []
            source_groups[source].append(doc)
        
        context_parts = []
        doc_num = 1
        
        for source, docs in source_groups.items():
            doc_type = docs[0].metadata.get("document_type", "document")
            
            # If multiple docs from same source, merge content
            if len(docs) > 1:
                merged_content = "\n\n".join([d.page_content for d in docs[:3]])  # Limit to 3 chunks per source
                context_parts.append(
                    f"[Document {doc_num} - Source: {source}, Type: {doc_type}, Merged: {len(docs)} chunks]\n{merged_content}\n"
                )
                doc_num += 1
            else:
                context_parts.append(
                    f"[Document {doc_num} - Source: {source}, Type: {doc_type}]\n{docs[0].page_content}\n"
                )
                doc_num += 1
        
        return "\n---\n".join(context_parts)
    
    @staticmethod
    def _extract_sources(answer: str, documents: List[Document]) -> List[Dict[str, Any]]:
        """
        Extract and format source citations from the answer.
        
        Args:
            answer: Generated answer text
            documents: Context documents used
            
        Returns:
            List of source information dictionaries
        """
        sources = []
        seen_sources = set()
        
        for doc in documents:
            source = doc.metadata.get("source", "Unknown")
            
            # Check if this source is mentioned in the answer
            if source in answer and source not in seen_sources:
                seen_sources.add(source)
                
                sources.append({
                    "source": source,
                    "type": doc.metadata.get("document_type", "document"),
                    "content_snippet": doc.page_content[:200] + "...",
                    "metadata": {
                        k: v for k, v in doc.metadata.items()
                        if k not in ["text", "page_content"]
                    }
                })
        
        return sources
    
    async def validate_answer(
        self,
        answer: str,
        context_documents: List[Document]
    ) -> Dict[str, Any]:
        """
        Validate that the answer is grounded in context (anti-hallucination check).
        
        Args:
            answer: Generated answer
            context_documents: Context documents
            
        Returns:
            Validation results
        """
        # Extract key claims from answer
        validation_prompt = f"""Given this answer and the context it was based on, evaluate if the answer contains only information from the context.

Answer:
{answer}

Context:
{self._format_context(context_documents)}

Evaluate:
1. Are all factual claims in the answer supported by the context?
2. List any claims that appear to be unsupported or hallucinated
3. Rate the answer's groundedness on a scale of 1-10

Provide your evaluation in this format:
Groundedness Score: [1-10]
Supported Claims: [list]
Unsupported Claims: [list]
Overall Assessment: [brief summary]"""
        
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=500,
                system="You are an expert fact-checker evaluating answer quality.",
                messages=[{"role": "user", "content": validation_prompt}]
            )
            
            validation_text = response.content[0].text
            
            return {
                "validation_complete": True,
                "validation_text": validation_text,
                "model": self.model
            }
        except Exception as e:
            return {
                "validation_complete": False,
                "error": str(e)
            }

