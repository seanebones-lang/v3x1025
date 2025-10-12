"""
Maximal Marginal Relevance (MMR) algorithm for diverse retrieval.
True MMR implementation for variety in search results.
"""

from typing import List, Tuple
import numpy as np
from langchain.schema import Document


class MMRRetriever:
    """
    Maximal Marginal Relevance retrieval for diversity.
    Balances relevance with diversity to avoid redundant results.
    """
    
    @staticmethod
    def rerank_with_mmr(
        query_embedding: List[float],
        documents: List[Document],
        document_embeddings: List[List[float]],
        top_k: int = 5,
        lambda_mult: float = 0.5
    ) -> List[Document]:
        """
        Re-rank documents using MMR algorithm.
        
        Args:
            query_embedding: Query vector
            documents: List of documents
            document_embeddings: Embedding vectors for documents
            top_k: Number of results to return
            lambda_mult: Balance parameter (0=max diversity, 1=max relevance)
                        Default 0.5 balances both equally
        
        Returns:
            Re-ranked documents maximizing relevance and diversity
        """
        if not documents or len(documents) == 0:
            return []
        
        if len(documents) <= top_k:
            return documents
        
        # Convert to numpy arrays
        query_vec = np.array(query_embedding)
        doc_vecs = np.array(document_embeddings)
        
        # Calculate similarity to query for all documents
        query_similarities = cosine_similarity_batch(query_vec, doc_vecs)
        
        # MMR algorithm
        selected_indices = []
        remaining_indices = list(range(len(documents)))
        
        # Select first document (highest relevance)
        first_idx = int(np.argmax(query_similarities))
        selected_indices.append(first_idx)
        remaining_indices.remove(first_idx)
        
        # Iteratively select documents maximizing MMR score
        while len(selected_indices) < top_k and remaining_indices:
            mmr_scores = []
            
            for idx in remaining_indices:
                # Relevance component
                relevance = query_similarities[idx]
                
                # Diversity component (max similarity to already selected)
                if selected_indices:
                    selected_vecs = doc_vecs[selected_indices]
                    doc_vec = doc_vecs[idx]
                    similarities_to_selected = cosine_similarity_batch(doc_vec, selected_vecs)
                    max_similarity = np.max(similarities_to_selected)
                else:
                    max_similarity = 0
                
                # MMR score: λ * relevance - (1-λ) * max_similarity_to_selected
                mmr_score = lambda_mult * relevance - (1 - lambda_mult) * max_similarity
                mmr_scores.append((idx, mmr_score))
            
            # Select document with highest MMR score
            best_idx, best_score = max(mmr_scores, key=lambda x: x[1])
            selected_indices.append(best_idx)
            remaining_indices.remove(best_idx)
        
        # Return selected documents in MMR order
        return [documents[i] for i in selected_indices]


def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """
    Calculate cosine similarity between two vectors.
    
    Args:
        vec1: First vector
        vec2: Second vector
        
    Returns:
        Cosine similarity score (0-1)
    """
    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return float(dot_product / (norm1 * norm2))


def cosine_similarity_batch(vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """
    Calculate cosine similarity between a vector and a matrix of vectors.
    
    Args:
        vec: Query vector
        matrix: Matrix of document vectors
        
    Returns:
        Array of similarity scores
    """
    # Handle single vector case
    if len(matrix.shape) == 1:
        matrix = matrix.reshape(1, -1)
    
    # Compute dot products
    dot_products = np.dot(matrix, vec)
    
    # Compute norms
    vec_norm = np.linalg.norm(vec)
    matrix_norms = np.linalg.norm(matrix, axis=1)
    
    # Avoid division by zero
    matrix_norms[matrix_norms == 0] = 1e-10
    
    # Calculate similarities
    similarities = dot_products / (matrix_norms * vec_norm + 1e-10)
    
    return similarities

