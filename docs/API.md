# Dealership RAG API Documentation

## Overview

The Dealership RAG API provides enterprise-grade retrieval augmented generation capabilities for automotive dealerships. Built with FastAPI, Claude 4.5 Sonnet, and Pinecone vector search.

**Base URL**: `http://localhost:8000`

**OpenAPI Documentation**: `http://localhost:8000/docs`

## Authentication

Currently supports Bearer token authentication. Add API key to `.env`:

```
API_SECRET_KEY=your-secret-key
```

Include in requests:
```
Authorization: Bearer your-secret-key
```

## Endpoints

### System Endpoints

#### Health Check
```http
GET /api/health
```

Returns system health status and service availability.

**Response**:
```json
{
  "status": "healthy",
  "timestamp": "2024-10-12T10:00:00Z",
  "version": "1.0.0",
  "services": {
    "redis": true,
    "agentic_rag": true,
    "ingestion": true
  }
}
```

#### System Metrics
```http
GET /api/metrics
```

Returns system performance metrics.

**Response**:
```json
{
  "total_queries": 1000,
  "average_latency_ms": 1500,
  "cache_hit_rate": 0.65,
  "error_rate": 0.02,
  "total_documents": 5000,
  "uptime_seconds": 86400
}
```

### Query Endpoints

#### Query (Standard)
```http
POST /api/query
```

Submit a query to the RAG system.

**Request Body**:
```json
{
  "query": "What Toyota Camry models are available?",
  "conversation_id": null,
  "filters": {"make": "Toyota"},
  "top_k": 5,
  "include_sources": true,
  "stream": false
}
```

**Response**:
```json
{
  "answer": "We have several Toyota Camry models available...",
  "sources": [
    {
      "content": "2024 Toyota Camry LE, VIN: 1HGBH41JXMN109186",
      "metadata": {"source": "inventory.json"},
      "score": 0.95
    }
  ],
  "conversation_id": "conv-123",
  "query_time_ms": 1250,
  "model_used": "claude-4.5-sonnet",
  "intent": "inventory"
}
```

#### Query (Streaming)
```http
POST /api/query/stream
```

Stream query response in real-time.

**Request Body**: Same as standard query

**Response**: Server-sent events (text/plain stream)

### Ingestion Endpoints

#### Ingest Data
```http
POST /api/ingest
```

Ingest documents into the RAG system.

**Request Body**:
```json
{
  "source_type": "text",
  "source_identifier": null,
  "content": "Document content to ingest",
  "metadata": {"type": "policy"},
  "namespace": "default"
}
```

**Response**:
```json
{
  "status": "success",
  "documents_processed": 1,
  "chunks_created": 5,
  "vectors_upserted": 5,
  "processing_time_ms": 850,
  "errors": []
}
```

#### Ingest File
```http
POST /api/ingest/file
```

Upload and ingest a file.

**Parameters**:
- `file`: File upload (multipart/form-data)
- `namespace`: Target namespace (query param)

**Supported formats**: PDF, TXT, CSV, JSON, DOCX, HTML, MD

### Management Endpoints

#### Clear Namespace
```http
DELETE /api/index/{namespace}
```

Clear all documents from a namespace.

**Response**:
```json
{
  "success": true,
  "namespace": "test",
  "message": "Namespace 'test' cleared successfully"
}
```

#### Get Stats
```http
GET /api/stats
```

Get detailed system statistics.

**Response**:
```json
{
  "agent_stats": {
    "retriever_stats": {...},
    "dms_adapter": "mock",
    "dms_healthy": true
  },
  "api_metrics": {...},
  "uptime_seconds": 86400
}
```

## Error Responses

All endpoints return standard error responses:

```json
{
  "detail": "Error message description"
}
```

**Status Codes**:
- `400`: Bad Request
- `404`: Not Found
- `500`: Internal Server Error
- `503`: Service Unavailable

## Rate Limiting

Default rate limit: 100 requests per minute per IP

Configure in `.env`:
```
RATE_LIMIT_PER_MINUTE=100
RATE_LIMIT_BURST=20
```

## Examples

### Python Client
```python
import requests

url = "http://localhost:8000/api/query"
payload = {
    "query": "Show me electric vehicles under $50k",
    "include_sources": True
}

response = requests.post(url, json=payload)
result = response.json()

print(result["answer"])
for source in result["sources"]:
    print(f"Source: {source['metadata']['source']}")
```

### cURL
```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What financing options are available?",
    "include_sources": true
  }'
```

## Best Practices

1. **Caching**: Responses are cached for 1 hour (with Redis)
2. **Namespaces**: Use namespaces to organize different data types
3. **Filters**: Apply metadata filters for targeted retrieval
4. **Streaming**: Use streaming for long-form responses
5. **Sources**: Always include sources for transparency

## Support

For issues or questions, refer to the main README or GitHub issues.

