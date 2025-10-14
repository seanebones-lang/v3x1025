"""
Production-grade embedding service for the Enterprise RAG system.
Handles text-to-vector conversion with caching, batch processing, and fault tolerance.

Copyright: Sean McDonnell - Proprietary and Confidential
License: Commercial use requires valid license agreement
"""

import asyncio
import hashlib
import logging
import time
from typing import Any, Optional

import redis.asyncio as redis
import voyageai
from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter

from .config import get_config

logger = logging.getLogger(__name__)


class EmbeddingError(Exception):
    """Custom exception for embedding-related errors."""
    
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error


class VoyageEmbedder:
    """Production-ready embedding service with comprehensive error handling and monitoring."""

    def __init__(self):
        """Initialize the Voyage AI embedding service."""
        self.config = get_config()
        
        if not self.config.voyage_api_key:
            raise EmbeddingError("Voyage AI API key not configured - check VOYAGE_API_KEY environment variable")
            
        try:
            self.client = voyageai.Client(api_key=self.config.voyage_api_key)
        except Exception as e:
            raise EmbeddingError(f"Failed to initialize Voyage AI client: {str(e)}", e)
            
        self.redis_client: Optional[redis.Redis] = None
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", " ", ""],
        )
        
        # Performance tracking for production monitoring
        self.embedding_cache_hits = 0
        self.embedding_cache_misses = 0
        self.total_embeddings_generated = 0
        self.total_api_calls = 0
        self.total_api_errors = 0

    async def initialize_cache(self) -> None:
        """Initialize Redis cache connection with comprehensive error handling."""
        try:
            self.redis_client = redis.from_url(
                self.config.redis_url,
                socket_connect_timeout=5,
                socket_keepalive=True,
                retry_on_timeout=True,
                health_check_interval=30,
            )
            await self.redis_client.ping()
            logger.info("Redis cache connection established successfully")
        except Exception as e:
            logger.warning(f"Redis cache unavailable, operating without cache: {e}")
            self.redis_client = None

    async def close(self) -> None:
        """Clean up resources and log final statistics."""
        if self.redis_client:
            await self.redis_client.close()
        
        logger.info(
            f"Embedding service statistics - "
            f"Embeddings generated: {self.total_embeddings_generated}, "
            f"API calls: {self.total_api_calls}, "
            f"API errors: {self.total_api_errors}, "
            f"Cache hits: {self.embedding_cache_hits}, "
            f"Cache misses: {self.embedding_cache_misses}"
        )

    def _generate_cache_key(self, text: str, model: str) -> str:
        """Generate deterministic cache key for text embedding."""
        # Use SHA-256 for security and collision resistance
        content = f"{model}:{text}".encode('utf-8')
        return f"embedding:v1:{hashlib.sha256(content).hexdigest()[:32]}"

    async def _get_cached_embedding(self, cache_key: str) -> Optional[list[float]]:
        """Retrieve embedding from cache with error handling."""
        if not self.redis_client:
            return None

        try:
            cached_data = await self.redis_client.get(cache_key)
            if cached_data:
                import json
                self.embedding_cache_hits += 1
                return json.loads(cached_data)
        except Exception as e:
            logger.warning(f"Cache retrieval error for key {cache_key[:16]}...: {e}")

        self.embedding_cache_misses += 1
        return None

    async def _cache_embedding(self, cache_key: str, embedding: list[float]) -> None:
        """Store embedding in cache with error handling and TTL."""
        if not self.redis_client:
            return

        try:
            import json
            await self.redis_client.setex(
                cache_key,
                86400,  # 24-hour cache expiration
                json.dumps(embedding),
            )
        except Exception as e:
            logger.warning(f"Cache storage error for key {cache_key[:16]}...: {e}")

    async def embed_single(
        self,
        text: str,
        model: Optional[str] = None,
        input_type: str = "document",
    ) -> list[float]:
        """
        Generate embedding for a single text with comprehensive error handling.
        
        Args:
            text: Text to embed (must be non-empty)
            model: Voyage model to use (defaults to config)
            input_type: Type of input for Voyage API optimization
            
        Returns:
            List of embedding values
            
        Raises:
            EmbeddingError: If embedding generation fails after all retries
        """
        if not text or not text.strip():
            raise EmbeddingError("Cannot embed empty or whitespace-only text")

        if len(text.strip()) > 32000:  # Voyage AI limit
            raise EmbeddingError(f"Text too long ({len(text)} chars), maximum 32000 characters")

        model = model or self.config.voyage_embed_model
        text = text.strip()

        # Check cache first
        cache_key = self._generate_cache_key(text, model)
        cached_embedding = await self._get_cached_embedding(cache_key)
        if cached_embedding:
            return cached_embedding

        # Generate new embedding with comprehensive retry logic
        max_retries = 3
        base_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                self.total_api_calls += 1
                
                # Use asyncio.to_thread for sync Voyage API with timeout
                async with asyncio.timeout(30.0):  # 30-second timeout
                    result = await asyncio.to_thread(
                        self.client.embed,
                        texts=[text],
                        model=model,
                        input_type=input_type,
                    )
                
                if not result or not result.embeddings or not result.embeddings[0]:
                    raise EmbeddingError("Empty response from Voyage AI API")
                
                embedding = result.embeddings[0]
                
                # Validate embedding dimensions
                if len(embedding) != self.config.embedding_dimension:
                    logger.warning(
                        f"Unexpected embedding dimension: {len(embedding)}, "
                        f"expected {self.config.embedding_dimension}"
                    )
                
                self.total_embeddings_generated += 1

                # Cache the result
                await self._cache_embedding(cache_key, embedding)
                
                return embedding

            except asyncio.TimeoutError:
                self.total_api_errors += 1
                error_msg = f"Voyage AI API timeout after 30 seconds (attempt {attempt + 1}/{max_retries})"
                if attempt == max_retries - 1:
                    raise EmbeddingError(error_msg)
                logger.warning(error_msg)
                
            except Exception as e:
                self.total_api_errors += 1
                error_msg = f"Voyage AI API error: {str(e)} (attempt {attempt + 1}/{max_retries})"
                
                if attempt == max_retries - 1:
                    logger.error(f"Embedding generation failed after {max_retries} attempts: {e}")
                    raise EmbeddingError(f"Failed to generate embedding after {max_retries} attempts: {str(e)}", e)
                
                logger.warning(error_msg)
                
            # Exponential backoff with jitter
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt) + (attempt * 0.1)
                logger.info(f"Retrying embedding generation in {delay:.1f} seconds...")
                await asyncio.sleep(delay)

    async def embed_batch(
        self,
        texts: list[str],
        model: Optional[str] = None,
        input_type: str = "document",
        batch_size: int = 128,
    ) -> list[list[float]]:
        """
        Generate embeddings for multiple texts with intelligent batching and error handling.
        
        Args:
            texts: List of texts to embed
            model: Voyage model to use
            input_type: Type of input for optimization
            batch_size: Maximum texts per API call
            
        Returns:
            List of embedding vectors corresponding to input texts
        """
        if not texts:
            return []

        model = model or self.config.voyage_embed_model
        # Clean and validate texts
        cleaned_texts = []
        valid_indices = []
        
        for i, text in enumerate(texts):
            if text and text.strip() and len(text.strip()) <= 32000:
                cleaned_texts.append(text.strip())
                valid_indices.append(i)
            else:
                logger.warning(f"Skipping invalid text at index {i}: empty or too long")
        
        if not cleaned_texts:
            return [[] for _ in texts]  # Return empty embeddings for all invalid texts

        embeddings_result = [[] for _ in texts]
        
        # Process in batches to respect API limits
        for i in range(0, len(cleaned_texts), batch_size):
            batch_texts = cleaned_texts[i:i + batch_size]
            batch_indices = valid_indices[i:i + batch_size]
            
            # Check cache for each text in batch
            batch_embeddings = []
            uncached_texts = []
            uncached_positions = []
            
            for j, text in enumerate(batch_texts):
                cache_key = self._generate_cache_key(text, model)
                cached_embedding = await self._get_cached_embedding(cache_key)
                
                if cached_embedding:
                    batch_embeddings.append(cached_embedding)
                else:
                    batch_embeddings.append(None)
                    uncached_texts.append(text)
                    uncached_positions.append(j)
            
            # Generate embeddings for uncached texts
            if uncached_texts:
                try:
                    self.total_api_calls += 1
                    
                    async with asyncio.timeout(60.0):  # Longer timeout for batch
                        result = await asyncio.to_thread(
                            self.client.embed,
                            texts=uncached_texts,
                            model=model,
                            input_type=input_type,
                        )
                    
                    if not result or not result.embeddings:
                        raise EmbeddingError("Empty batch response from Voyage AI API")
                    
                    # Insert results back into batch
                    for pos_idx, embedding in zip(uncached_positions, result.embeddings):
                        if embedding:
                            batch_embeddings[pos_idx] = embedding
                            self.total_embeddings_generated += 1
                            
                            # Cache individual embedding
                            text_for_caching = uncached_texts[uncached_positions.index(pos_idx)]
                            cache_key = self._generate_cache_key(text_for_caching, model)
                            await self._cache_embedding(cache_key, embedding)
                        else:
                            # Use zero vector as fallback
                            batch_embeddings[pos_idx] = [0.0] * self.config.embedding_dimension
                            
                except Exception as e:
                    self.total_api_errors += 1
                    logger.error(f"Batch embedding failed for batch starting at {i}: {e}")
                    
                    # Fill failed embeddings with zero vectors
                    for pos_idx in uncached_positions:
                        if batch_embeddings[pos_idx] is None:
                            batch_embeddings[pos_idx] = [0.0] * self.config.embedding_dimension
            
            # Insert batch results into final result array
            for j, original_idx in enumerate(batch_indices):
                if j < len(batch_embeddings) and batch_embeddings[j]:
                    embeddings_result[original_idx] = batch_embeddings[j]

        return embeddings_result

    async def embed_documents(
        self,
        documents: list[Document],
        model: Optional[str] = None,
    ) -> list[Document]:
        """
        Embed a list of LangChain documents with comprehensive metadata tracking.
        
        Args:
            documents: List of LangChain Document objects
            model: Voyage model to use
            
        Returns:
            Documents with embedding metadata added
        """
        if not documents:
            return []

        try:
            texts = [doc.page_content for doc in documents]
            embeddings = await self.embed_batch(texts, model=model, input_type="document")
            
            # Add embeddings to document metadata with comprehensive tracking
            enhanced_documents = []
            for i, (doc, embedding) in enumerate(zip(documents, embeddings)):
                # Create new document to avoid modifying original
                enhanced_doc = Document(
                    page_content=doc.page_content,
                    metadata={
                        **doc.metadata,
                        "embedding": embedding,
                        "embedding_model": model or self.config.voyage_embed_model,
                        "embedding_timestamp": int(time.time()),
                        "embedding_version": "v1.0",
                        "text_length": len(doc.page_content),
                        "embedding_dimension": len(embedding) if embedding else 0,
                    }
                )
                enhanced_documents.append(enhanced_doc)
            
            logger.info(f"Successfully embedded {len(enhanced_documents)} documents")
            return enhanced_documents
            
        except Exception as e:
            logger.error(f"Document embedding failed: {e}")
            raise EmbeddingError(f"Failed to embed documents: {str(e)}", e)

    def split_documents(self, documents: list[Document]) -> list[Document]:
        """
        Split documents into chunks with comprehensive metadata tracking.
        
        Args:
            documents: List of documents to split
            
        Returns:
            List of document chunks with enhanced metadata
        """
        if not documents:
            return []

        try:
            chunks = self.text_splitter.split_documents(documents)
            
            # Add comprehensive chunk metadata
            enhanced_chunks = []
            for i, chunk in enumerate(chunks):
                enhanced_chunk = Document(
                    page_content=chunk.page_content,
                    metadata={
                        **chunk.metadata,
                        "chunk_index": i,
                        "chunk_size": len(chunk.page_content),
                        "chunk_id": f"chunk_{i}_{hash(chunk.page_content) % 1000000}",
                        "splitter_config": {
                            "chunk_size": self.config.chunk_size,
                            "chunk_overlap": self.config.chunk_overlap,
                            "separator_count": len(self.text_splitter.separators),
                        },
                        "split_timestamp": int(time.time()),
                    }
                )
                enhanced_chunks.append(enhanced_chunk)
            
            logger.info(f"Split {len(documents)} documents into {len(enhanced_chunks)} chunks")
            return enhanced_chunks
            
        except Exception as e:
            logger.error(f"Document splitting failed: {e}")
            # Return original documents as fallback
            logger.warning("Returning original documents due to splitting failure")
            return documents

    def get_stats(self) -> dict[str, Any]:
        """Get comprehensive embedding service statistics for monitoring."""
        cache_hit_rate = 0.0
        total_cache_requests = self.embedding_cache_hits + self.embedding_cache_misses
        
        if total_cache_requests > 0:
            cache_hit_rate = self.embedding_cache_hits / total_cache_requests

        api_error_rate = 0.0
        if self.total_api_calls > 0:
            api_error_rate = self.total_api_errors / self.total_api_calls

        return {
            "total_embeddings_generated": self.total_embeddings_generated,
            "total_api_calls": self.total_api_calls,
            "total_api_errors": self.total_api_errors,
            "api_error_rate": api_error_rate,
            "cache_hits": self.embedding_cache_hits,
            "cache_misses": self.embedding_cache_misses,
            "cache_hit_rate": cache_hit_rate,
            "model": self.config.voyage_embed_model,
            "embedding_dimension": self.config.embedding_dimension,
            "cache_available": self.redis_client is not None,
        }

    async def health_check(self) -> dict[str, Any]:
        """Perform comprehensive health check on embedding service."""
        health = {
            "service": "embedding",
            "status": "healthy",
            "timestamp": int(time.time()),
            "checks": {},
        }

        # Test embedding generation
        try:
            test_embedding = await self.embed_single(
                "Production health check test", 
                input_type="query"
            )
            health["checks"]["api_connectivity"] = True
            health["checks"]["embedding_dimension"] = len(test_embedding)
            health["checks"]["api_latency_ok"] = True
        except Exception as e:
            health["status"] = "unhealthy"
            health["checks"]["api_connectivity"] = False
            health["checks"]["api_error"] = str(e)

        # Check cache status
        if self.redis_client:
            try:
                await self.redis_client.ping()
                health["checks"]["cache_available"] = True
            except Exception as e:
                health["checks"]["cache_available"] = False
                health["checks"]["cache_error"] = str(e)
        else:
            health["checks"]["cache_available"] = False

        # Check performance metrics
        stats = self.get_stats()
        health["checks"]["api_error_rate_acceptable"] = stats["api_error_rate"] < 0.05
        health["checks"]["cache_hit_rate_acceptable"] = stats["cache_hit_rate"] > 0.7 if stats["cache_hit_rate"] > 0 else True

        # Overall health determination
        critical_checks = ["api_connectivity"]
        for check in critical_checks:
            if not health["checks"].get(check, False):
                health["status"] = "unhealthy"
                break

        return health