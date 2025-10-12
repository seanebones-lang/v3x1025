"""
FastAPI application for Dealership RAG system.
Provides REST API endpoints for querying, ingesting, and managing the RAG system.
"""

import time
import uuid
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, status, File, UploadFile, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import redis.asyncio as redis

from src.config import settings
from src.models import (
    QueryRequest,
    QueryResponse,
    IngestRequest,
    IngestResponse,
    HealthCheck,
    SystemMetrics,
    ErrorResponse,
    SourceDocument
)
from src.agent import AgenticRAG
from src.ingest import DocumentIngestionPipeline
from src import __version__


# Global instances
agentic_rag: Optional[AgenticRAG] = None
ingestion_pipeline: Optional[DocumentIngestionPipeline] = None
redis_client: Optional[redis.Redis] = None

# Metrics tracking
metrics = {
    "total_queries": 0,
    "total_ingestions": 0,
    "total_errors": 0,
    "start_time": time.time()
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    global agentic_rag, ingestion_pipeline, redis_client
    
    # Startup
    print("🚀 Starting Dealership RAG System...")
    
    # Initialize components
    agentic_rag = AgenticRAG()
    ingestion_pipeline = DocumentIngestionPipeline()
    
    # Initialize Redis for caching
    try:
        redis_client = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True
        )
        await redis_client.ping()
        print("✅ Redis connection established")
    except Exception as e:
        print(f"⚠️  Redis connection failed: {e}")
        redis_client = None
    
    print(f"✅ Dealership RAG System v{__version__} ready!")
    
    yield
    
    # Shutdown
    print("👋 Shutting down Dealership RAG System...")
    if redis_client:
        await redis_client.close()


# Initialize FastAPI app
app = FastAPI(
    title="Dealership RAG API",
    description="Enterprise RAG system for automotive dealerships",
    version=__version__,
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Health & Status Endpoints
# ============================================================================

@app.get("/api/health", response_model=HealthCheck, tags=["System"])
async def health_check():
    """Check system health and service availability."""
    services = {
        "redis": redis_client is not None and await redis_client.ping() if redis_client else False,
        "agentic_rag": agentic_rag is not None,
        "ingestion": ingestion_pipeline is not None
    }
    
    # Determine overall status
    all_healthy = all(services.values())
    status_value = "healthy" if all_healthy else "degraded"
    
    return HealthCheck(
        status=status_value,
        timestamp=datetime.now(),
        version=__version__,
        services=services
    )


@app.get("/api/metrics", response_model=SystemMetrics, tags=["System"])
async def get_metrics():
    """Get system metrics and statistics."""
    uptime = time.time() - metrics["start_time"]
    
    # Get agent stats
    agent_stats = await agentic_rag.get_agent_stats() if agentic_rag else {}
    
    total_queries = metrics["total_queries"]
    avg_latency = 0  # Would be calculated from stored latencies
    
    return SystemMetrics(
        total_queries=total_queries,
        average_latency_ms=avg_latency,
        cache_hit_rate=0.0,  # Would be calculated from cache hits/misses
        error_rate=metrics["total_errors"] / max(total_queries, 1),
        total_documents=agent_stats.get("retriever_stats", {}).get("cached_documents", 0),
        uptime_seconds=uptime
    )


# ============================================================================
# Query Endpoints
# ============================================================================

@app.post("/api/query", response_model=QueryResponse, tags=["Query"])
async def query(request: QueryRequest):
    """
    Query the RAG system with a question.
    
    - **query**: The user's question
    - **conversation_id**: Optional conversation ID for context
    - **filters**: Optional metadata filters for retrieval
    - **top_k**: Number of results to return
    - **include_sources**: Whether to include source documents
    """
    start_time = time.time()
    
    try:
        if not agentic_rag:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="RAG system not initialized"
            )
        
        # Check cache if Redis available
        cache_key = None
        if redis_client and not request.conversation_id:
            cache_key = f"query:{hash(request.query)}"
            cached_result = await redis_client.get(cache_key)
            if cached_result:
                import json
                return QueryResponse(**json.loads(cached_result))
        
        # Process query
        result = await agentic_rag.process_query(
            query=request.query,
            conversation_history=None  # Would load from storage if conversation_id provided
        )
        
        # Calculate query time
        query_time_ms = (time.time() - start_time) * 1000
        
        # Build response
        response = QueryResponse(
            answer=result["answer"],
            sources=[
                SourceDocument(**source) for source in result.get("sources", [])
            ] if request.include_sources else [],
            conversation_id=request.conversation_id or str(uuid.uuid4()),
            query_time_ms=query_time_ms,
            model_used=result.get("model", "claude-4.5-sonnet"),
            intent=result.get("intent")
        )
        
        # Cache result
        if cache_key and redis_client:
            import json
            await redis_client.setex(
                cache_key,
                3600,  # 1 hour TTL
                json.dumps(response.model_dump())
            )
        
        # Update metrics
        metrics["total_queries"] += 1
        
        return response
    except Exception as e:
        metrics["total_errors"] += 1
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.post("/api/query/stream", tags=["Query"])
async def query_stream(request: QueryRequest):
    """Stream query response for real-time results."""
    try:
        if not agentic_rag:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="RAG system not initialized"
            )
        
        # Get context documents first
        context_documents = await agentic_rag.retriever.retrieve(
            query=request.query,
            top_k=settings.top_k_rerank
        )
        
        # Stream generation
        async def generate():
            async for chunk in agentic_rag.generator.generate_streaming_answer(
                query=request.query,
                context_documents=context_documents
            ):
                yield chunk
        
        return StreamingResponse(generate(), media_type="text/plain")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================================================
# Ingestion Endpoints
# ============================================================================

@app.post("/api/ingest", response_model=IngestResponse, tags=["Ingestion"])
async def ingest_data(request: IngestRequest, background_tasks: BackgroundTasks):
    """
    Ingest documents into the RAG system.
    
    - **source_type**: Type of data source (file, dms, url, text)
    - **source_identifier**: File path, URL, or identifier
    - **content**: Direct text content
    - **metadata**: Additional metadata
    - **namespace**: Pinecone namespace for organization
    """
    start_time = time.time()
    
    try:
        if not ingestion_pipeline or not agentic_rag:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Ingestion system not initialized"
            )
        
        chunks = []
        
        # Ingest based on source type
        if request.source_type == "file" and request.source_identifier:
            chunks = await ingestion_pipeline.ingest_file(
                file_path=request.source_identifier,
                metadata=request.metadata
            )
        elif request.source_type == "text" and request.content:
            chunks = await ingestion_pipeline.ingest_text(
                text=request.content,
                metadata=request.metadata
            )
        elif request.source_type == "dms":
            # Sync DMS data in background
            background_tasks.add_task(sync_dms_data, request.namespace)
            return IngestResponse(
                status="success",
                documents_processed=0,
                chunks_created=0,
                vectors_upserted=0,
                processing_time_ms=0,
                errors=["DMS sync started in background"]
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid source_type or missing required fields"
            )
        
        # Index documents
        indexing_result = await agentic_rag.retriever.index_documents(
            documents=chunks,
            namespace=request.namespace or "default"
        )
        
        processing_time_ms = (time.time() - start_time) * 1000
        
        metrics["total_ingestions"] += 1
        
        return IngestResponse(
            status="success",
            documents_processed=1,
            chunks_created=len(chunks),
            vectors_upserted=indexing_result.get("vectors_upserted", 0),
            processing_time_ms=processing_time_ms,
            errors=[]
        )
    except Exception as e:
        metrics["total_errors"] += 1
        return IngestResponse(
            status="failed",
            documents_processed=0,
            chunks_created=0,
            vectors_upserted=0,
            processing_time_ms=0,
            errors=[str(e)]
        )


@app.post("/api/ingest/file", response_model=IngestResponse, tags=["Ingestion"])
async def ingest_file(
    file: UploadFile = File(...),
    namespace: str = "default"
):
    """Upload and ingest a file."""
    import tempfile
    import os
    
    try:
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
        
        # Ingest file
        request = IngestRequest(
            source_type="file",
            source_identifier=tmp_path,
            namespace=namespace,
            metadata={"filename": file.filename}
        )
        
        result = await ingest_data(request, BackgroundTasks())
        
        # Cleanup
        os.unlink(tmp_path)
        
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================================================
# Management Endpoints
# ============================================================================

@app.delete("/api/index/{namespace}", tags=["Management"])
async def clear_namespace(namespace: str):
    """Clear all documents from a namespace."""
    try:
        if not agentic_rag:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="RAG system not initialized"
            )
        
        success = await agentic_rag.retriever.clear_index(namespace)
        
        return {
            "success": success,
            "namespace": namespace,
            "message": f"Namespace '{namespace}' cleared successfully" if success else "Failed to clear namespace"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.get("/api/stats", tags=["Management"])
async def get_stats():
    """Get detailed system statistics."""
    try:
        if not agentic_rag:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="RAG system not initialized"
            )
        
        agent_stats = await agentic_rag.get_agent_stats()
        
        return {
            "agent_stats": agent_stats,
            "api_metrics": metrics,
            "uptime_seconds": time.time() - metrics["start_time"]
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================================================
# Background Tasks
# ============================================================================

async def sync_dms_data(namespace: str = "default"):
    """Background task to sync data from DMS."""
    try:
        if not agentic_rag:
            return
        
        # Get inventory from DMS
        inventory = await agentic_rag.dms_adapter.get_inventory(limit=100)
        
        # Convert to documents
        from langchain.schema import Document
        documents = []
        
        for vehicle in inventory:
            doc_text = f"""
Vehicle: {vehicle.year} {vehicle.make} {vehicle.model}
VIN: {vehicle.vin}
Price: ${vehicle.price}
Mileage: {vehicle.mileage} miles
Status: {vehicle.status}
Features: {', '.join(vehicle.features)}
"""
            doc = Document(
                page_content=doc_text,
                metadata={
                    "source": "DMS",
                    "document_type": "vehicle",
                    "vin": vehicle.vin,
                    "make": vehicle.make,
                    "model": vehicle.model,
                    "year": vehicle.year
                }
            )
            documents.append(doc)
        
        # Index documents
        await agentic_rag.retriever.index_documents(documents, namespace)
        
        print(f"✅ Synced {len(documents)} vehicles from DMS")
    except Exception as e:
        print(f"❌ DMS sync failed: {e}")


# Root endpoint
@app.get("/", tags=["System"])
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Dealership RAG API",
        "version": __version__,
        "status": "operational",
        "docs": "/docs",
        "health": "/api/health"
    }

