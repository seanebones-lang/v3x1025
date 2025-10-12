"""
Hybrid retrieval engine with BM25 and vector search.
Includes Cohere re-ranking for precision.
"""

from typing import List, Dict, Any, Optional
import asyncio

from langchain.schema import Document
from langchain.retrievers import BM25Retriever, EnsembleRetriever
import cohere

from src.config import settings
from src.embed import EmbeddingManager


class HybridRetriever:
    """Hybrid retrieval combining vector search, BM25, and re-ranking with tunable weights."""
    
    def __init__(self, vector_weight: float = 0.6, bm25_weight: float = 0.4):
        """
        Initialize hybrid retriever with vector and keyword search.
        
        Args:
            vector_weight: Weight for vector search results (default: 0.6)
            bm25_weight: Weight for BM25 keyword results (default: 0.4)
                        Note: Weights should sum to 1.0 for proper RRF scoring
        """
        self.embedding_manager = EmbeddingManager()
        self.cohere_client = cohere.ClientV2(api_key=settings.cohere_api_key)
        
        # Tunable weights for ensemble retrieval (A/B test in production)
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight
        
        # Cache for BM25 retriever (will be populated with documents)
        self.bm25_retriever: Optional[BM25Retriever] = None
        self.document_cache: List[Document] = []
    
    async def index_documents(
        self,
        documents: List[Document],
        namespace: str = "default"
    ) -> Dict[str, Any]:
        """
        Index documents for retrieval.
        
        Args:
            documents: List of Document objects
            namespace: Pinecone namespace
            
        Returns:
            Dictionary with indexing statistics
        """
        if not documents:
            return {"indexed_count": 0, "error": "No documents provided"}
        
        # Add to document cache for BM25
        self.document_cache.extend(documents)
        
        # Update BM25 retriever
        self.bm25_retriever = BM25Retriever.from_documents(self.document_cache)
        self.bm25_retriever.k = settings.top_k_retrieval
        
        # Generate embeddings and upsert to Pinecone
        vectors = await self.embedding_manager.embed_documents(documents)
        result = await self.embedding_manager.upsert_vectors(vectors, namespace)
        
        return {
            "indexed_count": len(documents),
            "vectors_upserted": result.get("upserted_count", 0),
            "total_documents": len(self.document_cache)
        }
    
    async def retrieve(
        self,
        query: str,
        namespace: str = "default",
        top_k: int = None,
        filters: Optional[Dict[str, Any]] = None,
        use_rerank: bool = True
    ) -> List[Document]:
        """
        Retrieve relevant documents using hybrid search.
        
        Args:
            query: Query text
            namespace: Pinecone namespace
            top_k: Number of final results (after re-ranking)
            filters: Optional metadata filters
            use_rerank: Whether to use Cohere re-ranking
            
        Returns:
            List of relevant Document objects
        """
        if top_k is None:
            top_k = settings.top_k_rerank
        
        # Get more results initially for re-ranking
        initial_k = settings.top_k_retrieval
        
        # Step 1: Vector search with Pinecone
        vector_results = await self.embedding_manager.query_vectors(
            query_text=query,
            namespace=namespace,
            top_k=initial_k,
            filter_dict=filters
        )
        
        # Convert to Documents
        vector_documents = [
            Document(
                page_content=result["text"],
                metadata={
                    **result["metadata"],
                    "score": result["score"],
                    "retrieval_method": "vector"
                }
            )
            for result in vector_results
        ]
        
        # Step 2: BM25 keyword search (if available)
        bm25_documents = []
        if self.bm25_retriever and self.document_cache:
            try:
                bm25_documents = self.bm25_retriever.get_relevant_documents(query)
                for doc in bm25_documents:
                    doc.metadata["retrieval_method"] = "bm25"
            except Exception as e:
                print(f"BM25 retrieval error: {e}")
        
        # Step 3: Combine results
        combined_documents = self._combine_results(
            vector_documents,
            bm25_documents,
            initial_k
        )
        
        # Step 4: Re-rank with Cohere (if enabled)
        if use_rerank and combined_documents:
            ranked_documents = await self._rerank_documents(
                query,
                combined_documents,
                top_k
            )
            return ranked_documents
        
        return combined_documents[:top_k]
    
    async def _rerank_documents(
        self,
        query: str,
        documents: List[Document],
        top_k: int
    ) -> List[Document]:
        """
        Re-rank documents using Cohere Rerank v3.5.
        
        Args:
            query: Query text
            documents: List of Document objects
            top_k: Number of results to return
            
        Returns:
            Re-ranked list of Document objects
        """
        if not documents:
            return []
        
        try:
            # Prepare documents for Cohere
            docs_text = [doc.page_content for doc in documents]
            
            # Call Cohere Rerank API
            response = self.cohere_client.rerank(
                model="rerank-v3.5",
                query=query,
                documents=docs_text,
                top_n=top_k,
                return_documents=True
            )
            
            # Map results back to original documents
            reranked = []
            for result in response.results:
                original_doc = documents[result.index]
                original_doc.metadata["rerank_score"] = result.relevance_score
                original_doc.metadata["rerank_position"] = len(reranked) + 1
                reranked.append(original_doc)
            
            return reranked
        except Exception as e:
            print(f"Reranking error: {e}")
            # Fallback to original order
            return documents[:top_k]
    
    def _combine_results(
        self,
        vector_docs: List[Document],
        bm25_docs: List[Document],
        max_results: int
    ) -> List[Document]:
        """
        Combine vector and BM25 results using weighted reciprocal rank fusion.
        
        Args:
            vector_docs: Documents from vector search
            bm25_docs: Documents from BM25 search
            max_results: Maximum number of combined results
            
        Returns:
            Combined and ranked list of documents
        """
        k = 60  # RRF constant
        
        # Calculate RRF scores with tunable weights
        scores: Dict[str, float] = {}
        doc_map: Dict[str, Document] = {}
        
        # Score vector results (with weight)
        for rank, doc in enumerate(vector_docs, 1):
            doc_id = id(doc)
            scores[doc_id] = scores.get(doc_id, 0) + (self.vector_weight / (k + rank))
            doc_map[doc_id] = doc
        
        # Score BM25 results (with weight)
        for rank, doc in enumerate(bm25_docs, 1):
            doc_id = id(doc)
            scores[doc_id] = scores.get(doc_id, 0) + (self.bm25_weight / (k + rank))
            if doc_id not in doc_map:
                doc_map[doc_id] = doc
        
        # Sort by RRF score
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        
        # Return top results
        combined = []
        for doc_id in sorted_ids[:max_results]:
            doc = doc_map[doc_id]
            doc.metadata["rrf_score"] = scores[doc_id]
            combined.append(doc)
        
        return combined
    
    async def clear_index(self, namespace: str = "default") -> bool:
        """
        Clear all documents from index.
        
        Args:
            namespace: Pinecone namespace to clear
            
        Returns:
            Success status
        """
        try:
            await self.embedding_manager.delete_namespace(namespace)
            self.document_cache.clear()
            self.bm25_retriever = None
            return True
        except Exception:
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get retriever statistics.
        
        Returns:
            Dictionary with stats
        """
        pinecone_stats = self.embedding_manager.get_index_stats()
        
        return {
            "cached_documents": len(self.document_cache),
            "bm25_available": self.bm25_retriever is not None,
            "pinecone_stats": pinecone_stats
        }

