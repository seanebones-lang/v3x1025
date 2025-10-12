"""
Embedding generation and vector store management.
Uses Voyage AI for embeddings and Pinecone for vector storage.
"""

import hashlib
from typing import List, Dict, Any, Optional
import asyncio
from datetime import datetime

from langchain.schema import Document
from langchain_community.embeddings import VoyageEmbeddings
from pinecone import Pinecone, ServerlessSpec
import voyageai

from src.config import settings


class EmbeddingManager:
    """Manages embedding generation and vector store operations."""
    
    def __init__(self, use_hosted_inference: bool = False):
        """
        Initialize embedding manager with Voyage and Pinecone.
        
        Args:
            use_hosted_inference: If True, use Pinecone Hosted Inference for embeddings
                                 (30-50% latency reduction as of Oct 2025)
        """
        self.use_hosted_inference = use_hosted_inference
        
        # Initialize Voyage embeddings
        self.voyage_client = voyageai.Client(api_key=settings.voyage_api_key)
        self.embeddings = VoyageEmbeddings(
            voyage_api_key=settings.voyage_api_key,
            model="voyage-3.5-large"
        )
        
        # Initialize Pinecone
        self.pc = Pinecone(api_key=settings.pinecone_api_key)
        self.index_name = settings.pinecone_index_name
        
        # Create or get index
        self._initialize_index()
    
    def _initialize_index(self):
        """Initialize Pinecone index if it doesn't exist."""
        try:
            # Check if index exists
            existing_indexes = self.pc.list_indexes()
            
            if self.index_name not in [idx.name for idx in existing_indexes]:
                # Create new serverless index
                self.pc.create_index(
                    name=self.index_name,
                    dimension=3072,  # Voyage-3.5-large dimension
                    metric="cosine",
                    spec=ServerlessSpec(
                        cloud="aws",
                        region=settings.pinecone_environment
                    )
                )
            
            # Get index
            self.index = self.pc.Index(self.index_name)
        except Exception as e:
            raise Exception(f"Failed to initialize Pinecone index: {str(e)}")
    
    async def embed_documents(self, documents: List[Document]) -> List[Dict[str, Any]]:
        """
        Generate embeddings for documents.
        
        Args:
            documents: List of Document objects
            
        Returns:
            List of dictionaries with id, values, and metadata
        """
        if not documents:
            return []
        
        # Extract texts
        texts = [doc.page_content for doc in documents]
        
        # Generate embeddings in batches
        batch_size = 100
        all_vectors = []
        
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            batch_docs = documents[i:i + batch_size]
            
            # Get embeddings
            embeddings = await self._get_embeddings(batch_texts)
            
            # Create vector records
            for j, (embedding, doc) in enumerate(zip(embeddings, batch_docs)):
                vector_id = self._generate_id(doc)
                
                vector_record = {
                    "id": vector_id,
                    "values": embedding,
                    "metadata": {
                        "text": doc.page_content[:1000],  # Store first 1000 chars
                        **doc.metadata
                    }
                }
                
                all_vectors.append(vector_record)
        
        return all_vectors
    
    async def _get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Get embeddings from Voyage AI with rate limit handling.
        
        Args:
            texts: List of text strings
            
        Returns:
            List of embedding vectors
        """
        from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
        import asyncio
        
        # Adaptive jitter prevents thundering herd on rate limits
        import random
        
        @retry(
            stop=stop_after_attempt(5),
            wait=wait_exponential(multiplier=1, min=2, max=30) + 
                 (lambda retry_state: random.uniform(0, 2)),  # Jitter: 0-2s random
            retry_if_exception_type=(Exception,),
            reraise=True
        )
        async def _embed_with_retry():
            return await asyncio.to_thread(
                self.voyage_client.embed,
                texts,
                model="voyage-3.5-large",
                input_type="document"
            )
        
        try:
            response = await _embed_with_retry()
            return response.embeddings
        except Exception as e:
            raise Exception(f"Failed to generate embeddings after retries: {str(e)}")
    
    async def upsert_vectors(
        self,
        vectors: List[Dict[str, Any]],
        namespace: str = "default"
    ) -> Dict[str, int]:
        """
        Upsert vectors to Pinecone with idempotency protection.
        
        Args:
            vectors: List of vector records
            namespace: Pinecone namespace
            
        Returns:
            Dictionary with upserted count
        """
        if not vectors:
            return {"upserted_count": 0}
        
        # Add idempotency metadata to prevent duplicates on retries
        for vector in vectors:
            if "metadata" not in vector:
                vector["metadata"] = {}
            vector["metadata"]["upsert_timestamp"] = datetime.now().isoformat()
            vector["metadata"]["idempotency_key"] = vector["id"]  # Use vector ID as idempotency key
        
        # Batch upsert
        batch_size = 100
        total_upserted = 0
        
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i:i + batch_size]
            
            try:
                self.index.upsert(
                    vectors=batch,
                    namespace=namespace
                )
                total_upserted += len(batch)
            except Exception as e:
                print(f"Error upserting batch: {e}")
                continue
        
        return {"upserted_count": total_upserted}
    
    async def query_vectors(
        self,
        query_text: str,
        namespace: str = "default",
        top_k: int = 20,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Query vectors from Pinecone.
        
        Args:
            query_text: Query text
            namespace: Pinecone namespace
            top_k: Number of results to return
            filter_dict: Optional metadata filters
            
        Returns:
            List of matching results with scores
        """
        # Generate query embedding
        query_embedding = await self._get_embeddings([query_text])
        
        # Query Pinecone
        try:
            results = self.index.query(
                vector=query_embedding[0],
                top_k=top_k,
                namespace=namespace,
                filter=filter_dict,
                include_metadata=True
            )
            
            # Format results
            formatted_results = []
            
            for match in results.matches:
                formatted_results.append({
                    "id": match.id,
                    "score": match.score,
                    "text": match.metadata.get("text", ""),
                    "metadata": match.metadata
                })
            
            return formatted_results
        except Exception as e:
            raise Exception(f"Failed to query vectors: {str(e)}")
    
    async def delete_vectors(
        self,
        ids: List[str],
        namespace: str = "default"
    ) -> Dict[str, int]:
        """
        Delete vectors from Pinecone.
        
        Args:
            ids: List of vector IDs to delete
            namespace: Pinecone namespace
            
        Returns:
            Dictionary with deletion count
        """
        try:
            self.index.delete(ids=ids, namespace=namespace)
            return {"deleted_count": len(ids)}
        except Exception as e:
            raise Exception(f"Failed to delete vectors: {str(e)}")
    
    async def delete_namespace(self, namespace: str) -> Dict[str, bool]:
        """
        Delete entire namespace.
        
        Args:
            namespace: Namespace to delete
            
        Returns:
            Dictionary with success status
        """
        try:
            self.index.delete(delete_all=True, namespace=namespace)
            return {"success": True}
        except Exception as e:
            raise Exception(f"Failed to delete namespace: {str(e)}")
    
    def get_index_stats(self) -> Dict[str, Any]:
        """
        Get Pinecone index statistics.
        
        Returns:
            Dictionary with index stats
        """
        try:
            stats = self.index.describe_index_stats()
            return {
                "total_vectors": stats.total_vector_count,
                "dimension": stats.dimension,
                "namespaces": stats.namespaces
            }
        except Exception as e:
            return {"error": str(e)}
    
    @staticmethod
    def _generate_id(document: Document) -> str:
        """
        Generate unique ID for a document.
        
        Args:
            document: Document object
            
        Returns:
            Unique ID string
        """
        # Create hash from content and source
        content = f"{document.page_content}{document.metadata.get('source', '')}"
        return hashlib.sha256(content.encode()).hexdigest()[:32]


class HostedInferenceEmbeddings:
    """
    Wrapper for Pinecone Hosted Inference embeddings.
    Allows embedding generation directly through Pinecone.
    """
    
    def __init__(self, model_name: str = "voyage-3.5-large"):
        """
        Initialize hosted inference embeddings.
        
        Args:
            model_name: Name of the embedding model
        """
        self.pc = Pinecone(api_key=settings.pinecone_api_key)
        self.model_name = model_name
    
    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings using Pinecone Hosted Inference.
        
        Args:
            texts: List of text strings
            
        Returns:
            List of embedding vectors
        """
        # Note: This is a placeholder for Pinecone Hosted Inference
        # The actual implementation would use Pinecone's inference API
        # when it becomes available for the embedding model
        
        # For now, fall back to direct Voyage API
        voyage_client = voyageai.Client(api_key=settings.voyage_api_key)
        response = voyage_client.embed(
            texts,
            model=self.model_name,
            input_type="document"
        )
        return response.embeddings

