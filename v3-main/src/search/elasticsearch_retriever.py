"""
Production Elasticsearch integration for keyword search and BM25 scoring.
Replaces in-memory BM25 with scalable Elasticsearch cluster.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from elasticsearch import AsyncElasticsearch, exceptions as es_exceptions
from langchain.schema import Document

from src.config import get_config

logger = logging.getLogger(__name__)


class ElasticsearchError(Exception):
    """Custom exception for Elasticsearch-related errors."""
    
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error


class ElasticsearchRetriever:
    """
    Production Elasticsearch retriever with BM25 scoring and comprehensive error handling.
    """

    def __init__(self):
        """Initialize the Elasticsearch retriever."""
        self.config = get_config()
        
        # Elasticsearch configuration
        self.hosts = [
            {"host": self.config.elasticsearch_host, "port": self.config.elasticsearch_port}
        ]
        
        if self.config.elasticsearch_cloud_id:
            # Elasticsearch Cloud configuration
            self.es_client = AsyncElasticsearch(
                cloud_id=self.config.elasticsearch_cloud_id,
                http_auth=(self.config.elasticsearch_username, self.config.elasticsearch_password),
                request_timeout=30,
                max_retries=3,
                retry_on_timeout=True,
            )
        else:
            # Self-hosted Elasticsearch
            self.es_client = AsyncElasticsearch(
                hosts=self.hosts,
                http_auth=(self.config.elasticsearch_username, self.config.elasticsearch_password) 
                if self.config.elasticsearch_username else None,
                use_ssl=self.config.elasticsearch_use_ssl,
                verify_certs=self.config.elasticsearch_verify_certs,
                request_timeout=30,
                max_retries=3,
                retry_on_timeout=True,
            )
        
        # Index configuration
        self.index_prefix = "blue1-rag"
        
        # Performance tracking
        self.total_queries = 0
        self.total_index_operations = 0
        self.failed_queries = 0
        self.failed_index_operations = 0
        self.avg_query_time = 0.0

    async def initialize(self) -> None:
        """Initialize Elasticsearch connection and create indexes."""
        try:
            # Test connection
            info = await self.es_client.info()
            logger.info(f"Connected to Elasticsearch {info['version']['number']}")
            
            # Create main document index
            await self._create_document_index()
            
            logger.info("Elasticsearch retriever initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Elasticsearch: {e}")
            raise ElasticsearchError(f"Elasticsearch initialization failed: {e}", e)

    async def _create_document_index(self, namespace: str = "default") -> None:
        """
        Create document index with optimized BM25 settings.
        
        Args:
            namespace: Namespace for multi-tenancy
        """
        index_name = f"{self.index_prefix}-documents-{namespace}"
        
        try:
            # Check if index exists
            exists = await self.es_client.indices.exists(index=index_name)
            if exists:
                logger.info(f"Index {index_name} already exists")
                return
            
            # Define index settings with optimized BM25 parameters
            index_settings = {
                "settings": {
                    "number_of_shards": 3,
                    "number_of_replicas": 1,
                    "refresh_interval": "1s",
                    "max_result_window": 50000,
                    "analysis": {
                        "analyzer": {
                            "automotive_analyzer": {
                                "type": "custom",
                                "tokenizer": "standard",
                                "filter": [
                                    "lowercase",
                                    "automotive_synonyms",
                                    "automotive_stop_words",
                                    "stemmer"
                                ]
                            }
                        },
                        "filter": {
                            "automotive_synonyms": {
                                "type": "synonym",
                                "synonyms": [
                                    "car,vehicle,auto",
                                    "SUV,sport utility vehicle",
                                    "truck,pickup",
                                    "sedan,4-door",
                                    "mpg,miles per gallon,fuel economy",
                                    "AWD,all wheel drive,4WD,four wheel drive",
                                    "FWD,front wheel drive",
                                    "RWD,rear wheel drive"
                                ]
                            },
                            "automotive_stop_words": {
                                "type": "stop",
                                "stopwords": ["the", "and", "or", "but", "in", "on", "at", "to", "for"]
                            }
                        }
                    },
                    "similarity": {
                        "automotive_bm25": {
                            "type": "BM25",
                            "k1": 1.2,  # Term frequency saturation parameter
                            "b": 0.75   # Field-length normalization parameter
                        }
                    }
                },
                "mappings": {
                    "properties": {
                        "content": {
                            "type": "text",
                            "analyzer": "automotive_analyzer",
                            "similarity": "automotive_bm25",
                            "fields": {
                                "exact": {
                                    "type": "keyword"
                                }
                            }
                        },
                        "title": {
                            "type": "text",
                            "analyzer": "automotive_analyzer",
                            "similarity": "automotive_bm25",
                            "boost": 2.0
                        },
                        "source": {
                            "type": "keyword"
                        },
                        "document_type": {
                            "type": "keyword"
                        },
                        "vin": {
                            "type": "keyword"
                        },
                        "make": {
                            "type": "keyword"
                        },
                        "model": {
                            "type": "keyword"
                        },
                        "year": {
                            "type": "integer"
                        },
                        "price": {
                            "type": "float"
                        },
                        "mileage": {
                            "type": "integer"
                        },
                        "dealer_id": {
                            "type": "keyword"
                        },
                        "namespace": {
                            "type": "keyword"
                        },
                        "chunk_index": {
                            "type": "integer"
                        },
                        "total_chunks": {
                            "type": "integer"
                        },
                        "content_hash": {
                            "type": "keyword"
                        },
                        "timestamp": {
                            "type": "date"
                        },
                        "embedding_id": {
                            "type": "keyword"
                        }
                    }
                }
            }
            
            # Create index
            await self.es_client.indices.create(
                index=index_name,
                body=index_settings
            )
            
            logger.info(f"Created Elasticsearch index {index_name} with automotive BM25 configuration")
            
        except es_exceptions.RequestError as e:
            if "already_exists_exception" in str(e):
                logger.info(f"Index {index_name} already exists")
            else:
                raise ElasticsearchError(f"Failed to create index {index_name}: {e}", e)
        except Exception as e:
            raise ElasticsearchError(f"Index creation failed: {e}", e)

    async def index_documents(
        self,
        documents: List[Document],
        namespace: str = "default",
        batch_size: int = 500,
    ) -> Dict[str, Any]:
        """
        Index documents in Elasticsearch with bulk operations.
        
        Args:
            documents: List of documents to index
            namespace: Namespace for multi-tenancy
            batch_size: Documents per batch for bulk indexing
            
        Returns:
            Indexing statistics and error information
        """
        if not documents:
            return {"indexed": 0, "errors": []}

        start_time = time.time()
        indexed_count = 0
        errors = []
        
        try:
            # Ensure index exists
            await self._create_document_index(namespace)
            
            index_name = f"{self.index_prefix}-documents-{namespace}"
            
            # Process documents in batches
            for i in range(0, len(documents), batch_size):
                batch = documents[i:i + batch_size]
                
                try:
                    # Prepare bulk operations
                    bulk_operations = []
                    
                    for doc in batch:
                        # Generate document ID from content hash
                        content_hash = str(hash(doc.page_content))
                        doc_id = f"{namespace}_{content_hash}"
                        
                        # Index operation
                        bulk_operations.append({
                            "index": {
                                "_index": index_name,
                                "_id": doc_id
                            }
                        })
                        
                        # Document data
                        doc_data = {
                            "content": doc.page_content,
                            "title": doc.metadata.get("title", ""),
                            "source": doc.metadata.get("source", "unknown"),
                            "document_type": doc.metadata.get("document_type", "text"),
                            "namespace": namespace,
                            "chunk_index": doc.metadata.get("chunk_index", 0),
                            "total_chunks": doc.metadata.get("total_chunks", 1),
                            "content_hash": content_hash,
                            "timestamp": doc.metadata.get("timestamp", time.time()),
                            "embedding_id": doc.metadata.get("embedding_id", ""),
                        }
                        
                        # Add vehicle-specific metadata if available
                        if "vin" in doc.metadata:
                            doc_data.update({
                                "vin": doc.metadata["vin"],
                                "make": doc.metadata.get("make", ""),
                                "model": doc.metadata.get("model", ""),
                                "year": doc.metadata.get("year", 0),
                                "price": doc.metadata.get("price", 0.0),
                                "mileage": doc.metadata.get("mileage", 0),
                                "dealer_id": doc.metadata.get("dealer_id", ""),
                            })
                        
                        bulk_operations.append(doc_data)
                    
                    # Execute bulk operation
                    response = await self.es_client.bulk(
                        operations=bulk_operations,
                        refresh=True
                    )
                    
                    # Check for errors
                    if response.get("errors"):
                        for item in response["items"]:
                            if "index" in item and "error" in item["index"]:
                                error_msg = item["index"]["error"]["reason"]
                                errors.append(f"Bulk index error: {error_msg}")
                    else:
                        indexed_count += len(batch)
                    
                    self.total_index_operations += 1
                    logger.info(f"Indexed batch {i//batch_size + 1}: {len(batch)} documents")
                    
                except Exception as e:
                    self.failed_index_operations += 1
                    error_msg = f"Batch indexing failed at position {i}: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)

            processing_time = time.time() - start_time
            
            result = {
                "indexed": indexed_count,
                "processing_time_ms": processing_time * 1000,
                "errors": errors,
                "namespace": namespace,
                "batch_count": (len(documents) + batch_size - 1) // batch_size,
            }
            
            logger.info(f"Elasticsearch indexing completed: {result}")
            return result

        except Exception as e:
            processing_time = (time.time() - start_time) * 1000
            error_msg = f"Document indexing failed: {str(e)}"
            logger.error(error_msg)
            return {
                "indexed": indexed_count,
                "processing_time_ms": processing_time,
                "errors": [error_msg],
            }

    async def search(
        self,
        query: str,
        namespace: str = "default",
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 20,
    ) -> List[Document]:
        """
        Perform BM25 keyword search using Elasticsearch.
        
        Args:
            query: Search query
            namespace: Namespace for multi-tenancy
            filters: Additional filters to apply
            top_k: Number of results to return
            
        Returns:
            List of relevant documents with BM25 scores
        """
        if not query or not query.strip():
            return []

        start_time = time.time()
        self.total_queries += 1
        
        try:
            index_name = f"{self.index_prefix}-documents-{namespace}"
            
            # Build Elasticsearch query
            es_query = {
                "query": {
                    "bool": {
                        "must": [
                            {
                                "multi_match": {
                                    "query": query.strip(),
                                    "fields": [
                                        "content^1.0",
                                        "title^2.0"
                                    ],
                                    "type": "best_fields",
                                    "operator": "or",
                                    "fuzziness": "AUTO",
                                    "prefix_length": 2
                                }
                            }
                        ],
                        "filter": [
                            {"term": {"namespace": namespace}}
                        ]
                    }
                },
                "highlight": {
                    "fields": {
                        "content": {
                            "fragment_size": 150,
                            "number_of_fragments": 3
                        },
                        "title": {}
                    }
                },
                "size": top_k,
                "_source": True
            }
            
            # Add filters
            if filters:
                filter_clauses = es_query["query"]["bool"]["filter"]
                
                for key, value in filters.items():
                    if key == "source":
                        filter_clauses.append({"term": {"source": value}})
                    elif key == "document_type":
                        filter_clauses.append({"term": {"document_type": value}})
                    elif key == "vin":
                        filter_clauses.append({"term": {"vin": value}})
                    elif key == "make":
                        filter_clauses.append({"term": {"make": value}})
                    elif key == "model":
                        filter_clauses.append({"term": {"model": value}})
                    elif key == "year_min":
                        filter_clauses.append({"range": {"year": {"gte": value}}})
                    elif key == "year_max":
                        filter_clauses.append({"range": {"year": {"lte": value}}})
                    elif key == "price_min":
                        filter_clauses.append({"range": {"price": {"gte": value}}})
                    elif key == "price_max":
                        filter_clauses.append({"range": {"price": {"lte": value}}})
            
            # Execute search
            response = await self.es_client.search(
                index=index_name,
                body=es_query
            )
            
            # Parse results
            documents = []
            for hit in response["hits"]["hits"]:
                try:
                    source = hit["_source"]
                    
                    # Create document with BM25 score
                    doc = Document(
                        page_content=source["content"],
                        metadata={
                            **source,
                            "bm25_score": float(hit["_score"]),
                            "search_type": "elasticsearch_bm25",
                            "elasticsearch_id": hit["_id"],
                            "highlights": hit.get("highlight", {}),
                            "search_timestamp": int(time.time()),
                            "query": query.strip(),
                        }
                    )
                    documents.append(doc)
                    
                except Exception as e:
                    logger.warning(f"Failed to parse Elasticsearch result {hit['_id']}: {e}")
                    continue
            
            query_time = time.time() - start_time
            self.avg_query_time = (self.avg_query_time + query_time) / 2
            
            logger.info(f"Elasticsearch search returned {len(documents)} results in {query_time:.3f}s")
            return documents
            
        except Exception as e:
            self.failed_queries += 1
            logger.error(f"Elasticsearch search failed: {e}")
            return []

    async def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check on Elasticsearch cluster."""
        health = {
            "service": "elasticsearch",
            "status": "unknown",
            "timestamp": int(time.time()),
            "checks": {}
        }
        
        try:
            # Check cluster health
            cluster_health = await self.es_client.cluster.health()
            health["checks"]["cluster_status"] = cluster_health["status"]
            health["checks"]["number_of_nodes"] = cluster_health["number_of_nodes"]
            health["checks"]["active_shards"] = cluster_health["active_shards"]
            
            # Check if we can perform a basic search
            test_query = {
                "query": {"match_all": {}},
                "size": 1
            }
            
            search_response = await self.es_client.search(
                index=f"{self.index_prefix}-*",
                body=test_query
            )
            
            health["checks"]["search_functional"] = True
            health["checks"]["total_documents"] = search_response["hits"]["total"]["value"]
            
            # Overall status
            if cluster_health["status"] == "green":
                health["status"] = "healthy"
            elif cluster_health["status"] == "yellow":
                health["status"] = "degraded"
            else:
                health["status"] = "unhealthy"
            
            # Performance stats
            health["checks"]["total_queries"] = self.total_queries
            health["checks"]["failed_queries"] = self.failed_queries
            health["checks"]["avg_query_time_ms"] = self.avg_query_time * 1000
            health["checks"]["success_rate"] = 1.0 - (self.failed_queries / max(1, self.total_queries))
            
        except Exception as e:
            health["checks"]["connection_error"] = str(e)
            health["status"] = "unhealthy"
        
        return health

    async def close(self):
        """Clean up Elasticsearch connection."""
        try:
            await self.es_client.close()
            logger.info(f"Elasticsearch client closed - Total queries: {self.total_queries}, Failed: {self.failed_queries}")
        except Exception as e:
            logger.error(f"Error closing Elasticsearch client: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive Elasticsearch statistics."""
        return {
            "total_queries": self.total_queries,
            "failed_queries": self.failed_queries,
            "total_index_operations": self.total_index_operations,
            "failed_index_operations": self.failed_index_operations,
            "avg_query_time_ms": self.avg_query_time * 1000,
            "success_rate": 1.0 - (self.failed_queries / max(1, self.total_queries)),
            "index_success_rate": 1.0 - (self.failed_index_operations / max(1, self.total_index_operations)),
        }