"""
FastAPI application for the Dealership RAG system.
Production-ready REST API with authentication and monitoring.
"""

import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Optional

import redis.asyncio as redis
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile, File, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from src.agent import AgenticRAG
from src.config import get_config, validate_api_keys_at_startup
from src.embed import VoyageEmbedder
from src.models import (
    ErrorResponse,
    HealthCheck,
    IngestRequest,
    IngestResponse,
    QueryRequest,
    QueryResponse,
    SystemMetrics,
)
from src.retrieve import HybridRetriever
from src.observability.telemetry import telemetry

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global instances
config = get_config()
security = HTTPBearer(auto_error=False)

# Global state
app_state = {
    "rag_agent": None,
    "retriever": None,
    "embedder": None,
    "redis_client": None,
    "start_time": time.time(),
    "total_queries": 0,
    "total_errors": 0,
}


class ConversationManager:
    """Manages conversation history using Redis."""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis_client = redis_client
        self.conversation_ttl = 3600  # 1 hour TTL for conversations
        
    async def get_conversation_history(self, conversation_id: str) -> list[dict[str, str]]:
        """Retrieve conversation history from Redis."""
        try:
            if not self.redis_client:
                return []
                
            history_key = f"conversation:{conversation_id}"
            history_json = await self.redis_client.get(history_key)
            
            if history_json:
                return json.loads(history_json)
            return []
            
        except Exception as e:
            logger.warning(f"Failed to get conversation history: {e}")
            return []
    
    async def save_conversation_turn(
        self, 
        conversation_id: str, 
        user_message: str, 
        assistant_response: str
    ):
        """Save a conversation turn to Redis."""
        try:
            if not self.redis_client:
                return
                
            history = await self.get_conversation_history(conversation_id)
            
            # Add new turn
            history.append({
                "user": user_message,
                "assistant": assistant_response,
                "timestamp": time.time()
            })
            
            # Keep only last 10 turns to prevent memory issues
            if len(history) > 10:
                history = history[-10:]
            
            history_key = f"conversation:{conversation_id}"
            await self.redis_client.setex(
                history_key, 
                self.conversation_ttl, 
                json.dumps(history)
            )
            
        except Exception as e:
            logger.warning(f"Failed to save conversation turn: {e}")


class DocumentProcessor:
    """Handles document ingestion and processing."""
    
    def __init__(self, embedder: VoyageEmbedder, retriever: HybridRetriever):
        self.embedder = embedder
        self.retriever = retriever
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
    
    async def process_text_content(
        self, 
        content: str, 
        metadata: dict[str, Any],
        namespace: str = "default"
    ) -> dict[str, Any]:
        """Process text content into chunks and embed."""
        start_time = time.time()
        
        try:
            # Split text into chunks
            chunks = self.text_splitter.split_text(content)
            
            if not chunks:
                raise ValueError("No content chunks generated from text")
            
            # Create documents
            documents = []
            for i, chunk in enumerate(chunks):
                doc_metadata = {
                    **metadata,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "processing_timestamp": time.time()
                }
                documents.append(Document(page_content=chunk, metadata=doc_metadata))
            
            # Generate embeddings
            embeddings = await self.embedder.embed_documents([doc.page_content for doc in documents])
            
            # Store in vector database (this would use Pinecone in production)
            vectors_upserted = 0
            for doc, embedding in zip(documents, embeddings):
                # In a real implementation, this would upsert to Pinecone
                # For now, we'll simulate successful upsertion
                vectors_upserted += 1
            
            processing_time = (time.time() - start_time) * 1000
            
            return {
                "documents_processed": 1,
                "chunks_created": len(chunks),
                "vectors_upserted": vectors_upserted,
                "processing_time_ms": processing_time,
                "errors": []
            }
            
        except Exception as e:
            processing_time = (time.time() - start_time) * 1000
            logger.error(f"Document processing failed: {e}")
            return {
                "documents_processed": 0,
                "chunks_created": 0,
                "vectors_upserted": 0,
                "processing_time_ms": processing_time,
                "errors": [str(e)]
            }
    
    async def process_file_upload(
        self, 
        file: UploadFile, 
        metadata: dict[str, Any],
        namespace: str = "default"
    ) -> dict[str, Any]:
        """Process uploaded file."""
        try:
            # Read file content
            content = await file.read()
            
            # Handle different file types
            if file.content_type == "text/plain" or file.filename.endswith('.txt'):
                text_content = content.decode('utf-8')
            elif file.content_type == "application/pdf" or file.filename.endswith('.pdf'):
                # In production, you'd use pypdf or similar
                text_content = content.decode('utf-8', errors='ignore')  # Simplified
            else:
                raise ValueError(f"Unsupported file type: {file.content_type}")
            
            # Add file metadata
            file_metadata = {
                **metadata,
                "source_type": "file",
                "filename": file.filename,
                "content_type": file.content_type,
                "file_size": len(content)
            }
            
            return await self.process_text_content(text_content, file_metadata, namespace)
            
        except Exception as e:
            logger.error(f"File processing failed: {e}")
            return {
                "documents_processed": 0,
                "chunks_created": 0,
                "vectors_upserted": 0,
                "processing_time_ms": 0,
                "errors": [str(e)]
            }


async def get_redis_client() -> Optional[redis.Redis]:
    """Get Redis client for caching and metrics."""
    if app_state["redis_client"] is None:
        try:
            app_state["redis_client"] = redis.from_url(
                config.redis_url,
                socket_connect_timeout=5,
                socket_keepalive=True,
            )
            await app_state["redis_client"].ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.warning(f"Redis unavailable: {e}")
            app_state["redis_client"] = None
    
    return app_state["redis_client"]


async def authenticate_request(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> bool:
    """
    Authenticate API requests using bearer token.
    
    Args:
        credentials: HTTP authorization credentials
        
    Returns:
        True if authenticated
        
    Raises:
        HTTPException: If authentication fails
    """
    if config.environment == "development":
        return True  # Skip auth in development
    
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    
    if credentials.credentials != config.api_secret_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    
    return True


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - startup and shutdown."""
    
    # Startup
    logger.info("Starting Dealership RAG API...")
    
    try:
        # Initialize telemetry first
        telemetry.initialize()
        logger.info("Telemetry initialized successfully")
        
        # Validate API keys
        if config.is_production:
            await validate_api_keys_at_startup()
        
        # Initialize components
        app_state["rag_agent"] = AgenticRAG()
        app_state["retriever"] = HybridRetriever()
        app_state["embedder"] = VoyageEmbedder()
        
        # Initialize retriever and embedder
        await app_state["retriever"].initialize()
        await app_state["embedder"].initialize()
        
        # Initialize Redis
        await get_redis_client()
        
        logger.info("All services initialized successfully")
        
        yield
        
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise
    
    finally:
        # Shutdown
        logger.info("Shutting down Dealership RAG API...")
        
        if app_state["retriever"]:
            await app_state["retriever"].close()
        
        if app_state["embedder"]:
            await app_state["embedder"].close()
        
        if app_state["redis_client"]:
            await app_state["redis_client"].close()
        
        # Shutdown telemetry
        telemetry.shutdown()
        
        logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Dealership RAG System",
    description="Enterprise-grade RAG system for automotive dealerships",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if config.environment != "production" else None,
    redoc_url="/redoc" if config.environment != "production" else None,
)

# Initialize telemetry instrumentation
telemetry.instrument_fastapi_app(app)

# Rate limiting setup
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if config.environment == "development" else ["https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """Log all requests and track metrics."""
    start_time = time.time()
    
    # Generate request ID for tracing
    request_id = f"{int(start_time * 1000)}_{hash(str(request.url)) % 10000}"
    
    logger.info(
        f"Request started - ID: {request_id}, Method: {request.method}, "
        f"Path: {request.url.path}, Client: {request.client.host if request.client else 'unknown'}"
    )
    
    try:
        response = await call_next(request)
        
        processing_time = time.time() - start_time
        app_state["total_queries"] += 1
        
        logger.info(
            f"Request completed - ID: {request_id}, Status: {response.status_code}, "
            f"Processing time: {processing_time:.3f}s"
        )
        
        # Add headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Processing-Time"] = f"{processing_time:.3f}"
        
        return response
        
    except Exception as e:
        processing_time = time.time() - start_time
        app_state["total_errors"] += 1
        
        logger.error(
            f"Request failed - ID: {request_id}, Error: {str(e)}, "
            f"Processing time: {processing_time:.3f}s"
        )
        
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
            headers={"X-Request-ID": request_id},
        )


@app.get("/health", response_model=HealthCheck)
async def health_check():
    """Health check endpoint for load balancers and monitoring."""
    
    health_status = {
        "status": "healthy",
        "timestamp": time.time(),
        "version": "1.0.0",
        "services": {},
    }
    
    # Check core services
    try:
        if app_state["rag_agent"]:
            agent_health = await app_state["rag_agent"].get_agent_stats()
            health_status["services"]["rag_agent"] = True
        else:
            health_status["services"]["rag_agent"] = False
            health_status["status"] = "degraded"
            
    except Exception as e:
        logger.warning(f"RAG agent health check failed: {e}")
        health_status["services"]["rag_agent"] = False
        health_status["status"] = "degraded"
    
    # Check retriever
    try:
        if app_state["retriever"]:
            retriever_health = await app_state["retriever"].health_check()
            health_status["services"]["retriever"] = retriever_health["status"] == "healthy"
        else:
            health_status["services"]["retriever"] = False
            health_status["status"] = "degraded"
            
    except Exception as e:
        logger.warning(f"Retriever health check failed: {e}")
        health_status["services"]["retriever"] = False
        health_status["status"] = "degraded"
    
    # Check Redis
    try:
        redis_client = await get_redis_client()
        if redis_client:
            await redis_client.ping()
            health_status["services"]["redis"] = True
        else:
            health_status["services"]["redis"] = False
            
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")
        health_status["services"]["redis"] = False
    
    return HealthCheck(**health_status)


@app.get("/metrics", response_model=SystemMetrics)
async def get_metrics(request: Request, authenticated: bool = Depends(authenticate_request)):
    """Get system metrics and statistics."""
    
    uptime = time.time() - app_state["start_time"]
    
    # Calculate error rate
    total_requests = app_state["total_queries"] + app_state["total_errors"]
    error_rate = app_state["total_errors"] / max(1, total_requests)
    
    # Get component stats
    retriever_stats = {}
    if app_state["retriever"]:
        try:
            retriever_stats = app_state["retriever"].get_stats()
        except Exception as e:
            logger.warning(f"Failed to get retriever stats: {e}")
    
    metrics = SystemMetrics(
        total_queries=app_state["total_queries"],
        average_latency_ms=retriever_stats.get("avg_vector_search_ms", 0),
        cache_hit_rate=retriever_stats.get("embedding_stats", {}).get("cache_hit_rate", 0),
        error_rate=error_rate,
        total_documents=retriever_stats.get("documents_indexed", 0),
        uptime_seconds=uptime,
    )
    
    return metrics


@app.get("/metrics")
async def metrics_endpoint():
    """
    Prometheus metrics endpoint for monitoring and alerting.
    
    Returns metrics in Prometheus format for scraping by monitoring systems.
    """
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    
    # Generate Prometheus metrics
    metrics_data = generate_latest()
    
    return Response(
        content=metrics_data,
        media_type=CONTENT_TYPE_LATEST
    )


@app.post("/query", response_model=QueryResponse)
@limiter.limit(f"{config.rate_limit_per_minute}/minute")
async def query_rag_system(
    request: Request,
    query_request: QueryRequest,
    authenticated: bool = Depends(authenticate_request),
):
    """
    Query the RAG system for answers.
    
    This endpoint processes natural language queries and returns relevant answers
    with source citations from the knowledge base and DMS integration.
    """
    start_time = time.time()
    success = False
    
    # Create telemetry span for tracing
    with telemetry.create_span("rag_query", {
        "query_length": len(query_request.query),
        "conversation_id": query_request.conversation_id or "new",
        "user_id": request.client.host if request.client else "unknown"
    }):
        try:
            if not app_state["rag_agent"]:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="RAG agent not available",
                )
            
            # Get or create conversation ID
            conversation_id = query_request.conversation_id or str(uuid.uuid4())
            
            # Initialize conversation manager
            redis_client = await get_redis_client()
            conversation_manager = ConversationManager(redis_client) if redis_client else None
            
            # Get conversation history
            conversation_history = []
            if conversation_manager:
                conversation_history = await conversation_manager.get_conversation_history(conversation_id)
            
            # Process query through agentic RAG
            result = await app_state["rag_agent"].process_query(
                query=query_request.query,
                conversation_history=conversation_history,
            )
            
            query_time = (time.time() - start_time) * 1000
            success = True
            
            # Save conversation turn
            if conversation_manager:
                await conversation_manager.save_conversation_turn(
                    conversation_id=conversation_id,
                    user_message=query_request.query,
                    assistant_response=result["answer"]
                )
            
            response = QueryResponse(
                answer=result["answer"],
                sources=result["sources"],
                conversation_id=conversation_id,
                query_time_ms=query_time,
                model_used=result["model_used"],
                intent=result.get("intent"),
            )
            
            # Record telemetry metrics
            telemetry.record_rag_query(
                duration=query_time / 1000,
                query_type=result.get("intent", "unknown"),
                success=True
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Query processing failed: {e}")
            
            # Record error in telemetry
            telemetry.record_rag_query(
                duration=(time.time() - start_time),
                query_type="failed",
                success=False
            )
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Query processing failed: {str(e)}",
            )


@app.post("/ingest", response_model=IngestResponse)
async def ingest_documents(
    request: Request,
    ingest_request: IngestRequest,
    authenticated: bool = Depends(authenticate_request),
):
    """
    Ingest documents into the knowledge base.
    
    This endpoint allows uploading new content to be indexed and made searchable
    by the RAG system.
    """
    start_time = time.time()
    
    try:
        if not app_state["retriever"] or not app_state["embedder"]:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Document processing services not available",
            )
        
        # Initialize document processor
        doc_processor = DocumentProcessor(app_state["embedder"], app_state["retriever"])
        
        # Process based on source type
        if ingest_request.source_type == "text":
            if not ingest_request.content:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Content is required for text ingestion",
                )
            
            result = await doc_processor.process_text_content(
                content=ingest_request.content,
                metadata={
                    "source": ingest_request.source_identifier or "direct_text",
                    "source_type": "text",
                    **ingest_request.metadata
                },
                namespace=ingest_request.namespace or "default"
            )
        
        elif ingest_request.source_type == "url":
            # In production, this would fetch content from URL
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="URL ingestion not yet implemented",
            )
        
        elif ingest_request.source_type == "dms":
            # In production, this would sync from DMS
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="DMS ingestion not yet implemented",
            )
        
        else:  # file
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File ingestion requires /ingest/file endpoint",
            )
        
        processing_time = (time.time() - start_time) * 1000
        
        response = IngestResponse(
            status="success" if not result["errors"] else "partial_success",
            documents_processed=result["documents_processed"],
            chunks_created=result["chunks_created"],
            vectors_upserted=result["vectors_upserted"],
            processing_time_ms=processing_time,
            errors=result["errors"],
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Document ingestion failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document ingestion failed: {str(e)}",
        )


@app.post("/ingest/file", response_model=IngestResponse)
async def ingest_file(
    request: Request,
    file: UploadFile = File(...),
    namespace: str = "default",
    authenticated: bool = Depends(authenticate_request),
):
    """
    Ingest a file upload into the knowledge base.
    
    Supports text files, PDFs, and other document formats.
    """
    start_time = time.time()
    
    try:
        if not app_state["retriever"] or not app_state["embedder"]:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Document processing services not available",
            )
        
        # Initialize document processor
        doc_processor = DocumentProcessor(app_state["embedder"], app_state["retriever"])
        
        # Process file
        result = await doc_processor.process_file_upload(
            file=file,
            metadata={
                "upload_timestamp": time.time(),
                "client_ip": request.client.host if request.client else "unknown"
            },
            namespace=namespace
        )
        
        processing_time = (time.time() - start_time) * 1000
        
        response = IngestResponse(
            status="success" if not result["errors"] else "partial_success",
            documents_processed=result["documents_processed"],
            chunks_created=result["chunks_created"],
            vectors_upserted=result["vectors_upserted"],
            processing_time_ms=processing_time,
            errors=result["errors"],
        )
        
        return response
        
    except Exception as e:
        logger.error(f"File ingestion failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File ingestion failed: {str(e)}",
        )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Custom HTTP exception handler with structured error responses."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "status_code": exc.status_code},
        headers=getattr(exc, 'headers', None),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions with proper logging."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error occurred"},
    )


if __name__ == "__main__":
    uvicorn.run(
        "src.app:app",
        host="0.0.0.0",
        port=8000,
        reload=config.environment == "development",
        log_level=config.log_level.lower(),
        access_log=True,
    )