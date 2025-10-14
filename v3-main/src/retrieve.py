"""
Production-grade hybrid retrieval system combining vector and keyword search.
Implements dense vector search via Pinecone and BM25 keyword search with RRF fusion.

Copyright: Sean McDonnell - Proprietary and Confidential
License: Commercial use requires valid license agreement
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

import cohere
import pinecone
import redis.asyncio as redis
from langchain.schema import Document
from pinecone import Pinecone, ServerlessSpec
from rank_bm25 import BM25Okapi

from .config import get_config
from .embed import VoyageEmbedder, EmbeddingError
from .search.elasticsearch_retriever import ElasticsearchRetriever

logger = logging.getLogger(__name__)


class RetrievalError(Exception):
    """Custom exception for retrieval-related errors."""
    
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error


class HybridRetriever:
    """Production-ready hybrid retrieval system with comprehensive error handling and monitoring."""

    def __init__(self):
        """Initialize the hybrid retrieval system."""
        self.config = get_config()
        
        # Initialize embedding service
        self.embedder = VoyageEmbedder()
        
        # Initialize Elasticsearch retriever (replaces BM25)
        self.elasticsearch_retriever = ElasticsearchRetriever()
        
        # Pinecone setup with validation
        if not self.config.pinecone_api_key:
            raise RetrievalError("Pinecone API key not configured - check PINECONE_API_KEY environment variable")
            
        try:
            self.pinecone_client = Pinecone(api_key=self.config.pinecone_api_key)
        except Exception as e:
            raise RetrievalError(f"Failed to initialize Pinecone client: {str(e)}", e)
            
        self.index = None
        
        # Cohere re-ranking setup
        self.cohere_client = None
        if self.config.cohere_api_key:
            try:
                self.cohere_client = cohere.AsyncClient(api_key=self.config.cohere_api_key)
            except Exception as e:
                logger.warning(f"Failed to initialize Cohere client: {e}")
        
        # BM25 keyword search (in-memory for demo, would use Elasticsearch in production)
        self.bm25_index = None
        self.document_store: List[Document] = []
        
        # Redis cache
        self.redis_client: Optional[redis.Redis] = None
        
        # Performance tracking for production monitoring
        self.total_queries = 0
        self.cache_hits = 0
        self.vector_search_time = 0.0
        self.keyword_search_time = 0.0
        self.rerank_time = 0.0
        self.vector_search_errors = 0
        self.keyword_search_errors = 0
        self.rerank_errors = 0

    async def initialize(self) -> None:
        """Initialize all retrieval components with comprehensive error handling."""
        # Initialize embedding service cache
        await self.embedder.initialize_cache()
        
        # Initialize Elasticsearch retriever
        try:
            await self.elasticsearch_retriever.initialize()
            logger.info("Elasticsearch retriever initialized successfully")
        except Exception as e:
            logger.error(f"Elasticsearch initialization failed: {e}")
            raise RetrievalError(f"Failed to initialize Elasticsearch: {e}", e)
        
        # Initialize Redis cache
        try:
            self.redis_client = redis.from_url(
                self.config.redis_url,
                socket_connect_timeout=5,
                socket_keepalive=True,
                health_check_interval=30,
            )
            await self.redis_client.ping()
            logger.info("Retrieval cache initialized successfully")
        except Exception as e:
            logger.warning(f"Retrieval cache unavailable, operating without cache: {e}")
            self.redis_client = None
        
        # Initialize Pinecone index with creation if needed
        try:
            existing_indexes = self.pinecone_client.list_indexes().names()
            
            if self.config.pinecone_index_name not in existing_indexes:
                logger.info(f"Creating Pinecone index: {self.config.pinecone_index_name}")
                self.pinecone_client.create_index(
                    name=self.config.pinecone_index_name,
                    dimension=self.config.embedding_dimension,
                    metric="cosine",
                    spec=ServerlessSpec(
                        cloud="aws",
                        region=self.config.pinecone_environment,
                    ),
                )
                
                # Wait for index to be ready
                logger.info("Waiting for Pinecone index to be ready...")
                await asyncio.sleep(60)  # Serverless indexes take time to initialize
            
            self.index = self.pinecone_client.Index(self.config.pinecone_index_name)
            logger.info("Pinecone index ready for operations")
            
        except Exception as e:
            logger.error(f"Pinecone initialization failed: {e}")
            raise RetrievalError(f"Failed to initialize Pinecone: {e}", e)

    async def close(self) -> None:
        """Clean up resources and log final statistics."""
        await self.embedder.close()
        
        if self.elasticsearch_retriever:
            await self.elasticsearch_retriever.close()
        
        if self.redis_client:
            await self.redis_client.close()
        
        logger.info(
            f"Retrieval service statistics - "
            f"Total queries: {self.total_queries}, "
            f"Cache hits: {self.cache_hits}, "
            f"Vector errors: {self.vector_search_errors}, "
            f"Keyword errors: {self.keyword_search_errors}, "
            f"Rerank errors: {self.rerank_errors}"
        )

    async def index_documents(
        self,
        documents: list[Document],
        namespace: str = "default",
        batch_size: int = 100,
    ) -> dict[str, Any]:
        """
        Index documents for both vector and keyword search with comprehensive error handling.
        
        Args:
            documents: List of documents to index
            namespace: Namespace for tenant isolation
            batch_size: Documents per batch for processing
            
        Returns:
            Indexing statistics and error information
        """
        if not documents:
            return {"indexed": 0, "chunks_created": 0, "errors": []}

        start_time = time.time()
        indexed_count = 0
        errors = []

        try:
            # Validate namespace for tenant isolation
            if not namespace or not namespace.strip():
                namespace = "default"
            namespace = namespace.strip().lower()
            
            # Split documents into chunks
            try:
                chunks = self.embedder.split_documents(documents)
                logger.info(f"Split {len(documents)} documents into {len(chunks)} chunks")
            except Exception as e:
                error_msg = f"Document splitting failed: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
                chunks = documents  # Fallback to original documents

            # Generate embeddings with error handling
            try:
                embedded_chunks = await self.embedder.embed_documents(chunks)
            except EmbeddingError as e:
                error_msg = f"Embedding generation failed: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
                return {
                    "indexed": 0,
                    "chunks_created": len(chunks),
                    "processing_time_ms": (time.time() - start_time) * 1000,
                    "errors": errors,
                }

            # Index in Elasticsearch
            try:
                es_result = await self.elasticsearch_retriever.index_documents(
                    embedded_chunks,
                    namespace=namespace,
                    batch_size=batch_size
                )
                indexed_count += es_result["indexed"]
                errors.extend(es_result.get("errors", []))
            except Exception as e:
                error_msg = f"Elasticsearch indexing failed: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)

            # Index in Pinecone (vector search)
            for i in range(0, len(embedded_chunks), batch_size):
                batch = embedded_chunks[i:i + batch_size]
                
                try:
                    # Prepare vectors for Pinecone
                    vectors = []
                    for j, chunk in enumerate(batch):
                        if not chunk.metadata.get("embedding"):
                            logger.warning(f"Skipping chunk {i+j} - no embedding found")
                            continue
                            
                        vector_id = f"{namespace}_{i + j}_{hash(chunk.page_content) % 1000000}"
                        
                        # Validate embedding dimension
                        embedding = chunk.metadata["embedding"]
                        if len(embedding) != self.config.embedding_dimension:
                            logger.error(f"Invalid embedding dimension: {len(embedding)}, expected {self.config.embedding_dimension}")
                            continue
                        
                        vectors.append({
                            "id": vector_id,
                            "values": embedding,
                            "metadata": {
                                "text": chunk.page_content[:1000],  # Limit text size for Pinecone
                                "source": chunk.metadata.get("source", "unknown"),
                                "chunk_index": chunk.metadata.get("chunk_index", 0),
                                "timestamp": int(time.time()),
                                "namespace": namespace,
                                "document_id": chunk.metadata.get("document_id", ""),
                                "content_hash": str(hash(chunk.page_content)),
                            }
                        })
                    
                    if not vectors:
                        logger.warning(f"No valid vectors in batch starting at {i}")
                        continue
                    
                    # Upsert to Pinecone with retry logic
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            await asyncio.to_thread(
                                self.index.upsert,
                                vectors=vectors,
                                namespace=namespace,
                            )
                            break
                        except Exception as e:
                            if attempt == max_retries - 1:
                                raise e
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    
                    logger.info(f"Indexed batch {i//batch_size + 1}: {len(vectors)} vectors")
                    
                except Exception as e:
                    error_msg = f"Pinecone batch indexing failed at position {i}: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)

            processing_time = time.time() - start_time
            
            result = {
                "indexed": indexed_count,
                "chunks_created": len(chunks),
                "processing_time_ms": processing_time * 1000,
                "errors": errors,
                "namespace": namespace,
                "batch_count": (len(embedded_chunks) + batch_size - 1) // batch_size,
            }
            
            logger.info(f"Document indexing completed: {result}")
            return result

        except Exception as e:
            processing_time = (time.time() - start_time) * 1000
            error_msg = f"Document indexing failed: {str(e)}"
            logger.error(error_msg)
            return {
                "indexed": indexed_count,
                "chunks_created": 0,
                "processing_time_ms": processing_time,
                "errors": [error_msg],
            }

    async def vector_search(
        self,
        query: str,
        namespace: str = "default",
        top_k: int = 20,
        filters: Optional[dict] = None,
    ) -> list[Document]:
        """
        Perform dense vector search using Pinecone with comprehensive error handling.
        
        Args:
            query: Search query
            namespace: Pinecone namespace for tenant isolation
            top_k: Number of results to return
            filters: Metadata filters for search refinement
            
        Returns:
            List of relevant documents with vector scores
        """
        start_time = time.time()
        
        try:
            if not query or not query.strip():
                return []
                
            # Generate query embedding
            try:
                query_embedding = await self.embedder.embed_single(
                    query.strip(),
                    input_type="query"
                )
            except EmbeddingError as e:
                self.vector_search_errors += 1
                logger.error(f"Query embedding failed: {e}")
                return []
            
            # Validate namespace
            if not namespace or not namespace.strip():
                namespace = "default"
            namespace = namespace.strip().lower()
            
            # Prepare filters for Pinecone
            pinecone_filters = {}
            if filters:
                for key, value in filters.items():
                    if key in ["source", "document_id", "namespace"]:
                        pinecone_filters[key] = {"$eq": str(value)}
                    elif key.endswith("_min") and isinstance(value, (int, float)):
                        base_key = key[:-4]
                        pinecone_filters[base_key] = pinecone_filters.get(base_key, {})
                        pinecone_filters[base_key]["$gte"] = value
                    elif key.endswith("_max") and isinstance(value, (int, float)):
                        base_key = key[:-4]
                        pinecone_filters[base_key] = pinecone_filters.get(base_key, {})
                        pinecone_filters[base_key]["$lte"] = value
            
            # Search Pinecone with retry logic
            max_retries = 3
            search_results = None
            
            for attempt in range(max_retries):
                try:
                    search_results = await asyncio.to_thread(
                        self.index.query,
                        vector=query_embedding,
                        top_k=top_k,
                        namespace=namespace,
                        filter=pinecone_filters if pinecone_filters else None,
                        include_metadata=True,
                    )
                    break
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise e
                    logger.warning(f"Pinecone query attempt {attempt + 1} failed: {e}")
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
            
            if not search_results or not search_results.matches:
                logger.info(f"No vector search results found for query in namespace {namespace}")
                return []
            
            # Convert to LangChain documents
            documents = []
            for match in search_results.matches:
                try:
                    metadata = match.metadata or {}
                    doc = Document(
                        page_content=metadata.get("text", ""),
                        metadata={
                            **metadata,
                            "vector_score": float(match.score),
                            "search_type": "vector",
                            "search_id": match.id,
                            "search_namespace": namespace,
                            "search_timestamp": int(time.time()),
                        }
                    )
                    documents.append(doc)
                except Exception as e:
                    logger.warning(f"Failed to process search result {match.id}: {e}")
                    continue
            
            self.vector_search_time += time.time() - start_time
            logger.info(f"Vector search returned {len(documents)} results in {(time.time() - start_time):.3f}s")
            return documents
            
        except Exception as e:
            self.vector_search_errors += 1
            logger.error(f"Vector search failed: {e}")
            return []

    async def keyword_search(
        self,
        query: str,
        namespace: str = "default",
        filters: Optional[dict] = None,
        top_k: int = 20,
    ) -> list[Document]:
        """
        Perform keyword search using Elasticsearch with BM25 scoring.
        
        Args:
            query: Search query
            namespace: Namespace for multi-tenancy
            filters: Additional filters to apply
            top_k: Number of results to return
            
        Returns:
            List of relevant documents with BM25 scores
        """
        start_time = time.time()
        
        try:
            if not query or not query.strip():
                return []
                
            # Use Elasticsearch for keyword search
            documents = await self.elasticsearch_retriever.search(
                query=query.strip(),
                namespace=namespace,
                filters=filters,
                top_k=top_k
            )
            
            # Add keyword search metadata
            for i, doc in enumerate(documents):
                doc.metadata.update({
                    "search_type": "keyword_elasticsearch",
                    "keyword_rank": i + 1,
                    "search_timestamp": int(time.time()),
                    "query_tokens": query.strip().lower().split(),
                })
            
            self.keyword_search_time += time.time() - start_time
            logger.info(f"Elasticsearch keyword search returned {len(documents)} results in {(time.time() - start_time):.3f}s")
            return documents
            
        except Exception as e:
            self.keyword_search_errors += 1
            logger.error(f"Elasticsearch keyword search failed: {e}")
            return []

    def reciprocal_rank_fusion(
        self,
        vector_results: list[Document],
        keyword_results: list[Document],
        k: int = 60,
    ) -> list[Document]:
        """
        Combine vector and keyword search results using Reciprocal Rank Fusion.
        
        Args:
            vector_results: Results from vector search
            keyword_results: Results from keyword search
            k: RRF parameter for fusion calculation
            
        Returns:
            Fused and ranked results with RRF scores
        """
        try:
            # Create document lookup by content hash for deduplication
            all_docs = {}
            
            # Process vector results
            for rank, doc in enumerate(vector_results):
                try:
                    content_hash = hash(doc.page_content)
                    if content_hash not in all_docs:
                        all_docs[content_hash] = Document(
                            page_content=doc.page_content,
                            metadata={**doc.metadata}
                        )
                        all_docs[content_hash].metadata["rrf_score"] = 0.0
                    
                    # Add RRF score from vector search
                    rrf_contribution = 1.0 / (k + rank + 1)
                    all_docs[content_hash].metadata["rrf_score"] += rrf_contribution
                    all_docs[content_hash].metadata["vector_rank"] = rank + 1
                    all_docs[content_hash].metadata["vector_rrf_contribution"] = rrf_contribution
                    
                except Exception as e:
                    logger.warning(f"Failed to process vector result at rank {rank}: {e}")
                    continue

            # Process keyword results
            for rank, doc in enumerate(keyword_results):
                try:
                    content_hash = hash(doc.page_content)
                    if content_hash not in all_docs:
                        all_docs[content_hash] = Document(
                            page_content=doc.page_content,
                            metadata={**doc.metadata}
                        )
                        all_docs[content_hash].metadata["rrf_score"] = 0.0
                    else:
                        # Merge metadata from keyword search
                        for key, value in doc.metadata.items():
                            if key.startswith("bm25_") or key in ["search_type", "keyword_rank", "query_tokens"]:
                                all_docs[content_hash].metadata[key] = value
                    
                    # Add RRF score from keyword search
                    rrf_contribution = 1.0 / (k + rank + 1)
                    all_docs[content_hash].metadata["rrf_score"] += rrf_contribution
                    all_docs[content_hash].metadata["keyword_rank"] = rank + 1
                    all_docs[content_hash].metadata["keyword_rrf_contribution"] = rrf_contribution
                    
                except Exception as e:
                    logger.warning(f"Failed to process keyword result at rank {rank}: {e}")
                    continue

            # Sort by RRF score and add final ranking metadata
            ranked_docs = sorted(
                all_docs.values(),
                key=lambda x: x.metadata["rrf_score"],
                reverse=True
            )
            
            for i, doc in enumerate(ranked_docs):
                doc.metadata.update({
                    "final_rank": i + 1,
                    "fusion_method": "rrf",
                    "fusion_k_parameter": k,
                    "fusion_timestamp": int(time.time()),
                })

            logger.info(f"RRF fusion combined {len(vector_results)} vector + {len(keyword_results)} keyword results into {len(ranked_docs)} unique results")
            return ranked_docs
            
        except Exception as e:
            logger.error(f"RRF fusion failed: {e}")
            # Fallback to vector results
            logger.warning("Falling back to vector results only")
            return vector_results

    async def rerank_documents(
        self,
        query: str,
        documents: list[Document],
        top_k: int = 5,
    ) -> list[Document]:
        """
        Re-rank documents using Cohere re-ranking model with comprehensive error handling.
        
        Args:
            query: Original search query
            documents: Documents to re-rank
            top_k: Number of top results to return
            
        Returns:
            Re-ranked documents with relevance scores
        """
        if not self.cohere_client or not documents:
            logger.info(f"Cohere re-ranking not available, returning top {top_k} documents")
            return documents[:top_k]

        if not query or not query.strip():
            logger.warning("Empty query provided for re-ranking")
            return documents[:top_k]

        start_time = time.time()
        
        try:
            # Prepare documents for Cohere (limit text length)
            texts = []
            for doc in documents:
                text = doc.page_content
                if len(text) > 2000:  # Cohere has text length limits
                    text = text[:2000] + "..."
                texts.append(text)
            
            if not texts:
                return []
            
            # Re-rank using Cohere with timeout and retry
            max_retries = 3
            rerank_result = None
            
            for attempt in range(max_retries):
                try:
                    async with asyncio.timeout(30.0):  # 30-second timeout
                        rerank_result = await self.cohere_client.rerank(
                            model=self.config.cohere_rerank_model,
                            query=query.strip(),
                            documents=texts,
                            top_k=min(top_k, len(documents)),
                        )
                    break
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise e
                    logger.warning(f"Cohere rerank attempt {attempt + 1} failed: {e}")
                    await asyncio.sleep(2 ** attempt)
            
            if not rerank_result or not rerank_result.results:
                logger.warning("Empty rerank results from Cohere")
                return documents[:top_k]
            
            # Reorder documents based on re-ranking with comprehensive metadata
            reranked_docs = []
            for result in rerank_result.results:
                try:
                    if result.index >= len(documents):
                        logger.warning(f"Invalid rerank index {result.index}")
                        continue
                        
                    original_doc = documents[result.index]
                    
                    # Create enhanced document with rerank metadata
                    reranked_doc = Document(
                        page_content=original_doc.page_content,
                        metadata={
                            **original_doc.metadata,
                            "rerank_score": float(result.relevance_score),
                            "rerank_position": len(reranked_docs) + 1,
                            "rerank_model": self.config.cohere_rerank_model,
                            "rerank_timestamp": int(time.time()),
                            "original_rank": result.index + 1,
                        }
                    )
                    reranked_docs.append(reranked_doc)
                    
                except Exception as e:
                    logger.warning(f"Failed to process rerank result {result.index}: {e}")
                    continue
            
            self.rerank_time += time.time() - start_time
            logger.info(f"Cohere re-ranking completed: {len(reranked_docs)} documents in {(time.time() - start_time):.3f}s")
            return reranked_docs
            
        except Exception as e:
            self.rerank_errors += 1
            logger.error(f"Re-ranking failed: {e}")
            # Fallback to original ranking
            logger.warning(f"Falling back to original document ranking")
            return documents[:top_k]

    async def retrieve(
        self,
        query: str,
        namespace: str = "default",
        filters: Optional[dict] = None,
        top_k: int = 5,
        use_reranking: bool = True,
    ) -> list[Document]:
        """
        Main retrieval method with comprehensive error handling and monitoring.
        
        Args:
            query: Search query
            namespace: Index namespace for tenant isolation
            filters: Metadata filters for search refinement
            top_k: Final number of results to return
            use_reranking: Whether to use Cohere re-ranking
            
        Returns:
            List of most relevant documents with comprehensive metadata
        """
        if not query or not query.strip():
            return []
            
        self.total_queries += 1
        start_time = time.time()
        
        try:
            logger.info(f"Starting hybrid retrieval for query in namespace '{namespace}'")
            
            # Parallel vector and keyword search with comprehensive error handling
            vector_task = self.vector_search(
                query=query.strip(),
                namespace=namespace,
                top_k=self.config.top_k_retrieval,
                filters=filters,
            )
            
            keyword_task = asyncio.to_thread(
                self.keyword_search,
                query=query.strip(),
                top_k=self.config.top_k_retrieval,
            )
            
            # Wait for both searches with error handling
            try:
                vector_results, keyword_results = await asyncio.gather(
                    vector_task, keyword_task, return_exceptions=True
                )
            except Exception as e:
                logger.error(f"Search gathering failed: {e}")
                vector_results, keyword_results = [], []
            
            # Handle search exceptions
            if isinstance(vector_results, Exception):
                logger.error(f"Vector search failed: {vector_results}")
                vector_results = []
            
            if isinstance(keyword_results, Exception):
                logger.error(f"Keyword search failed: {keyword_results}")
                keyword_results = []
            
            # Ensure we have lists
            if not isinstance(vector_results, list):
                vector_results = []
            if not isinstance(keyword_results, list):
                keyword_results = []
            
            logger.info(f"Search results: {len(vector_results)} vector, {len(keyword_results)} keyword")
            
            # Fusion using RRF
            fused_results = self.reciprocal_rank_fusion(vector_results, keyword_results)
            
            # Re-ranking (optional)
            if use_reranking and self.cohere_client and fused_results:
                final_results = await self.rerank_documents(
                    query=query.strip(),
                    documents=fused_results,
                    top_k=top_k,
                )
            else:
                final_results = fused_results[:top_k]
            
            # Add comprehensive retrieval metadata
            retrieval_time = time.time() - start_time
            for doc in final_results:
                doc.metadata.update({
                    "retrieval_time_ms": retrieval_time * 1000,
                    "retrieval_method": "hybrid_rrf",
                    "query": query.strip(),
                    "namespace": namespace,
                    "retrieval_timestamp": int(time.time()),
                    "filters_applied": bool(filters),
                    "reranking_used": use_reranking and self.cohere_client is not None,
                })

            logger.info(f"Hybrid retrieval completed: {len(final_results)} results in {retrieval_time:.3f}s")
            return final_results
            
        except Exception as e:
            logger.error(f"Retrieval failed: {e}")
            raise RetrievalError(f"Retrieval operation failed: {str(e)}", e)

    def get_stats(self) -> dict[str, Any]:
        """Get comprehensive retrieval system statistics for monitoring."""
        avg_vector_time = self.vector_search_time / max(1, self.total_queries)
        avg_keyword_time = self.keyword_search_time / max(1, self.total_queries)
        avg_rerank_time = self.rerank_time / max(1, self.total_queries)

        vector_error_rate = self.vector_search_errors / max(1, self.total_queries)
        keyword_error_rate = self.keyword_search_errors / max(1, self.total_queries)
        rerank_error_rate = self.rerank_errors / max(1, self.total_queries)

        elasticsearch_stats = {}
        if self.elasticsearch_retriever:
            elasticsearch_stats = self.elasticsearch_retriever.get_stats()

        return {
            "total_queries": self.total_queries,
            "cache_hits": self.cache_hits,
            "avg_vector_search_ms": avg_vector_time * 1000,
            "avg_keyword_search_ms": avg_keyword_time * 1000,
            "avg_rerank_ms": avg_rerank_time * 1000,
            "vector_search_errors": self.vector_search_errors,
            "keyword_search_errors": self.keyword_search_errors,
            "rerank_errors": self.rerank_errors,
            "vector_error_rate": vector_error_rate,
            "keyword_error_rate": keyword_error_rate,
            "rerank_error_rate": rerank_error_rate,
            "elasticsearch_available": self.elasticsearch_retriever is not None,
            "cohere_available": self.cohere_client is not None,
            "embedding_stats": self.embedder.get_stats(),
            "elasticsearch_stats": elasticsearch_stats,
        }

    async def health_check(self) -> dict[str, Any]:
        """Perform comprehensive health check on retrieval system."""
        health = {
            "service": "retrieval",
            "status": "healthy",
            "timestamp": int(time.time()),
            "checks": {},
        }

        # Check Pinecone connectivity
        try:
            if self.index:
                stats = await asyncio.to_thread(self.index.describe_index_stats)
                health["checks"]["pinecone_available"] = True
                health["checks"]["total_vectors"] = stats.get("total_vector_count", 0)
                health["checks"]["index_fullness"] = stats.get("index_fullness", 0)
            else:
                health["checks"]["pinecone_available"] = False
        except Exception as e:
            health["checks"]["pinecone_available"] = False
            health["checks"]["pinecone_error"] = str(e)

        # Check Elasticsearch
        try:
            if self.elasticsearch_retriever:
                es_health = await self.elasticsearch_retriever.health_check()
                health["checks"]["elasticsearch_status"] = es_health["status"]
                health["checks"]["elasticsearch_details"] = es_health["checks"]
            else:
                health["checks"]["elasticsearch_status"] = "unavailable"
        except Exception as e:
            health["checks"]["elasticsearch_status"] = "unhealthy"
            health["checks"]["elasticsearch_error"] = str(e)

        # Check embedding service
        try:
            embed_health = await self.embedder.health_check()
            health["checks"]["embedding_service"] = embed_health["status"]
        except Exception:
            health["checks"]["embedding_service"] = "unhealthy"

        # Check Cohere availability
        health["checks"]["cohere_available"] = self.cohere_client is not None

        # Check performance metrics
        stats = self.get_stats()
        health["checks"]["error_rates_acceptable"] = (
            stats["vector_error_rate"] < 0.05 and
            stats["keyword_error_rate"] < 0.05 and
            stats["rerank_error_rate"] < 0.1
        )

        # Overall health determination
        critical_checks = ["pinecone_available", "embedding_service", "elasticsearch_status"]
        for check in critical_checks:
            check_value = health["checks"].get(check, False)
            if not check_value or check_value in ["unhealthy", "unavailable"]:
                health["status"] = "degraded"
                break

        return health