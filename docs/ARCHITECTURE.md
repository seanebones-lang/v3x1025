# System Architecture

## Overview

The Dealership RAG system is a production-grade, agentic retrieval augmented generation platform designed specifically for automotive dealerships. It combines vector search, keyword matching, and large language models to provide accurate, contextual answers about inventory, service, and sales.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         FastAPI Backend                         │
│                    (src/app.py - REST API)                      │
└────────────┬────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Agentic RAG Core                          │
│                      (src/agent.py)                             │
│                                                                 │
│  ┌─────────────────┐                                           │
│  │ Intent Classifier│──────────► Route to Specialized Agent    │
│  │  (Claude 4.5)   │              (Sales/Service/Inventory)    │
│  └─────────────────┘                                           │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │              Tool Calling & DMS Integration               │ │
│  │  ┌────────────┐  ┌──────────────┐  ┌─────────────────┐  │ │
│  │  │   CDK      │  │   Reynolds   │  │   Mock DMS      │  │ │
│  │  │  Adapter   │  │   Adapter    │  │   (Demo)        │  │ │
│  │  └────────────┘  └──────────────┘  └─────────────────┘  │ │
│  └──────────────────────────────────────────────────────────┘ │
└─────────────┬───────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Hybrid Retrieval Engine                        │
│                    (src/retrieve.py)                            │
│                                                                 │
│  ┌──────────────────┐         ┌─────────────────┐             │
│  │  Vector Search   │         │   BM25 Search   │             │
│  │  (Pinecone)      │◄───────►│   (Keyword)     │             │
│  └──────────────────┘         └─────────────────┘             │
│           │                                                     │
│           ▼                                                     │
│  ┌──────────────────────────────────────────┐                 │
│  │   Reciprocal Rank Fusion (RRF)           │                 │
│  └──────────────────┬───────────────────────┘                 │
│                     │                                           │
│                     ▼                                           │
│  ┌──────────────────────────────────────────┐                 │
│  │    Cohere Rerank v3.5 (Precision)        │                 │
│  └──────────────────────────────────────────┘                 │
└─────────────┬───────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Answer Generation                              │
│                   (src/generate.py)                             │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │         Claude 4.5 Sonnet Generation                      │ │
│  │         - Anti-hallucination prompts                      │ │
│  │         - Source attribution                              │ │
│  │         - Conversation memory                             │ │
│  └──────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘

              ▲                              ▲
              │                              │
              │                              │
┌─────────────┴──────────────┐  ┌───────────┴──────────────────┐
│   Document Ingestion       │  │    Vector Database           │
│   (src/ingest.py)          │  │    (Pinecone Serverless)     │
│                            │  │                              │
│  - PDF/CSV/JSON/TXT        │  │  - 3072-dim vectors          │
│  - Chunking (1000/200)     │  │  - Metadata filtering        │
│  - Metadata extraction     │  │  - Hybrid search             │
└────────────────────────────┘  └──────────────────────────────┘

              ▲
              │
┌─────────────┴──────────────────────────────────────────────────┐
│                     Embedding Service                          │
│                     (src/embed.py)                             │
│                                                                 │
│        Voyage AI 3.5-large (SOTA Automotive Embeddings)        │
└─────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. API Layer (FastAPI)

**File**: `src/app.py`

**Responsibilities**:
- REST API endpoints (/query, /ingest, /health)
- Request validation (Pydantic models)
- Response caching (Redis)
- Rate limiting
- Background task management (Celery)
- Streaming responses

**Key Features**:
- Async operations for concurrency
- OpenAPI auto-documentation
- CORS middleware
- Health checks and metrics

### 2. Agentic RAG Core

**File**: `src/agent.py`

**Responsibilities**:
- Intent classification (sales/service/inventory/predictive/general)
- Query routing to specialized agents
- DMS tool calling
- Entity extraction
- Multi-turn conversation handling

**Intent Categories**:
- **Sales**: Pricing, financing, comparisons
- **Service**: Maintenance, repairs, appointments
- **Inventory**: Availability, specs, features
- **Predictive**: Trends, forecasts, analytics
- **General**: FAQs, general information

### 3. DMS Integration

**Files**: `src/dms/*.py`

**Adapters**:
- **CDK Global**: Enterprise DMS connector
- **Reynolds & Reynolds**: Alternative DMS
- **Mock**: Demo data generator (50+ vehicles)

**Capabilities**:
- Real-time inventory sync
- Vehicle details lookup (by VIN)
- Service history retrieval
- Pricing updates
- Availability checks

### 4. Hybrid Retrieval Engine

**File**: `src/retrieve.py`

**Pipeline**:
1. **Vector Search** (Pinecone)
   - Semantic similarity using Voyage embeddings
   - Metadata filtering
   - Top-20 initial results

2. **BM25 Search** (Keyword)
   - Exact term matching
   - Critical for VINs, part numbers, prices

3. **Reciprocal Rank Fusion (RRF)**
   - Combines vector + BM25 scores
   - Balances semantic + lexical relevance

4. **Cohere Rerank v3.5**
   - Precision filtering
   - Top-5 final results
   - Optimized for noisy automotive docs

### 5. Answer Generation

**File**: `src/generate.py`

**Features**:
- **Context-only responses**: Strict grounding in sources
- **Source attribution**: [Source: ...] citations
- **Anti-hallucination**: Validation prompts
- **Streaming support**: Real-time generation
- **Conversation memory**: Multi-turn context

**Claude 4.5 Sonnet**:
- 1M+ token context window
- Low hallucination rate
- Superior reasoning for complex queries

### 6. Document Ingestion

**File**: `src/ingest.py`

**Supported Formats**:
- PDF (via Unstructured.io)
- CSV (inventory exports)
- JSON (API responses)
- TXT/MD (policies, FAQs)
- DOCX (manuals)
- SQL (DMS queries)

**Processing**:
- RecursiveCharacterTextSplitter
- Chunk size: 1000 tokens
- Overlap: 200 tokens
- Metadata enrichment
- Deduplication

### 7. Embedding Service

**File**: `src/embed.py`

**Technology**:
- **Voyage AI 3.5-large**: SOTA embeddings
- 3072 dimensions
- Optimized for automotive jargon
- Batch processing (100 chunks)

**Pinecone Integration**:
- Serverless architecture
- Auto-scaling
- Namespace organization
- Hybrid search enabled

## Data Flow

### Query Flow

1. **User submits query** → FastAPI `/api/query`
2. **Intent classification** → Claude determines category
3. **Agent routing** → Specialized agent selected
4. **DMS tool call** (if needed) → Live data retrieval
5. **Hybrid retrieval** → Vector + BM25 search
6. **Re-ranking** → Cohere precision filter
7. **Answer generation** → Claude with sources
8. **Response** → JSON with answer + citations

### Ingestion Flow

1. **Document upload** → FastAPI `/api/ingest`
2. **Format detection** → Appropriate loader selected
3. **Parsing** → Extract text + metadata
4. **Chunking** → Split into 1000-token chunks
5. **Embedding** → Voyage generates vectors
6. **Upserting** → Pinecone stores vectors
7. **Indexing** → BM25 index updated

## Performance Optimizations

1. **Redis Caching**: 1-hour TTL on query results
2. **Async Operations**: All I/O non-blocking
3. **Batch Processing**: 100-chunk embedding batches
4. **Connection Pooling**: Database connections reused
5. **Streaming**: Long responses streamed

## Monitoring & Observability

- **LangSmith**: Query tracing, latency, token usage
- **Sentry**: Error tracking and alerts
- **Metrics API**: Real-time statistics
- **Health Checks**: Component availability

## Security & Compliance

- **API Key Authentication**: Bearer token
- **PII Anonymization**: Sensitive data handling
- **GDPR Hooks**: Data deletion support
- **Rate Limiting**: 100 req/min per IP

## Scalability

- **Horizontal**: FastAPI workers scale independently
- **Vertical**: Pinecone serverless auto-scales
- **Caching**: Redis reduces LLM calls by 40-60%
- **Background Jobs**: Celery for async processing

## Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Orchestration | LangChain | 0.3.27 |
| API Framework | FastAPI | 0.119.0 |
| LLM | Claude 4.5 Sonnet | Latest |
| Embeddings | Voyage AI | 3.5-large |
| Vector DB | Pinecone | 6.0.0 |
| Re-ranker | Cohere | v3.5 |
| Cache | Redis | 7.4 |
| Tasks | Celery | 5.4.0 |
| Testing | Pytest | 8.4.2 |

## Deployment Architecture

**Docker Compose Services**:
- `api`: FastAPI application (port 8000)
- `redis`: Caching + Celery broker
- `celery-worker`: Background tasks
- `celery-beat`: Scheduled jobs

**Environment Variables**: See `.env.example`

## Future Enhancements

1. **Multimodal**: Image search with CLIP embeddings
2. **Fine-tuning**: Custom automotive embeddings
3. **Mobile**: Edge deployment for dealership apps
4. **Analytics**: Predictive maintenance AI
5. **Voice**: Speech-to-text integration

