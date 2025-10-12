# Sequence Diagrams - Query Lifecycle

## Standard Query Flow

```
┌──────┐          ┌─────────┐        ┌────────┐        ┌──────────┐       ┌─────────┐       ┌────────┐
│Client│          │FastAPI  │        │Agent   │        │Retriever │       │Generator│       │DMS     │
└──┬───┘          └────┬────┘        └───┬────┘        └────┬─────┘       └────┬────┘       └───┬────┘
   │                   │                 │                  │                   │                │
   │ POST /api/query   │                 │                  │                   │                │
   ├──────────────────>│                 │                  │                   │                │
   │                   │                 │                  │                   │                │
   │              [Check Cache]          │                  │                   │                │
   │                   │                 │                  │                   │                │
   │              Cache Miss             │                  │                   │                │
   │                   │                 │                  │                   │                │
   │                   │ classify_intent │                  │                   │                │
   │                   ├────────────────>│                  │                   │                │
   │                   │                 │                  │                   │                │
   │                   │            [Call Claude]           │                   │                │
   │                   │                 │                  │                   │                │
   │                   │    Intent+Conf  │                  │                   │                │
   │                   │<────────────────┤                  │                   │                │
   │                   │                 │                  │                   │                │
   │                   │   route_agent   │                  │                   │                │
   │                   ├────────────────>│                  │                   │                │
   │                   │                 │                  │                   │                │
   │                   │              Check if DMS needed   │                   │                │
   │                   │                 │                  │                   │                │
   │                   │                 │ get_inventory    │                   │                │
   │                   │                 ├─────────────────────────────────────────────────────>│
   │                   │                 │                  │                   │                │
   │                   │                 │                  │                   │    [Query DMS] │
   │                   │                 │                  │                   │                │
   │                   │                 │  Vehicle Data    │                   │                │
   │                   │                 │<─────────────────────────────────────────────────────┤
   │                   │                 │                  │                   │                │
   │                   │                 │  retrieve()      │                   │                │
   │                   │                 ├─────────────────>│                   │                │
   │                   │                 │                  │                   │                │
   │                   │                 │           [Vector Search]            │                │
   │                   │                 │                  │                   │                │
   │                   │                 │           [BM25 Search]              │                │
   │                   │                 │                  │                   │                │
   │                   │                 │           [RRF Combine]              │                │
   │                   │                 │                  │                   │                │
   │                   │                 │           [Cohere Rerank]            │                │
   │                   │                 │                  │                   │                │
   │                   │                 │  Context Docs    │                   │                │
   │                   │                 │<─────────────────┤                   │                │
   │                   │                 │                  │                   │                │
   │                   │                 │            generate_answer            │                │
   │                   │                 ├────────────────────────────────────>│                │
   │                   │                 │                  │                   │                │
   │                   │                 │                  │            [Call Claude]           │
   │                   │                 │                  │                   │                │
   │                   │                 │   Answer + Sources                  │                │
   │                   │                 │<────────────────────────────────────┤                │
   │                   │                 │                  │                   │                │
   │                   │  Response       │                  │                   │                │
   │                   │<────────────────┤                  │                   │                │
   │                   │                 │                  │                   │                │
   │              [Cache Result]         │                  │                   │                │
   │                   │                 │                  │                   │                │
   │   JSON Response   │                 │                  │                   │                │
   │<──────────────────┤                 │                  │                   │                │
   │                   │                 │                  │                   │                │
```

**Timing:** ~1.5-2.5s end-to-end

## Failure Mode: Pinecone Rate Limit

```
┌──────┐          ┌─────────┐        ┌────────┐        ┌──────────┐       ┌─────────┐
│Client│          │FastAPI  │        │Agent   │        │Retriever │       │Generator│
└──┬───┘          └────┬────┘        └───┬────┘        └────┬─────┘       └────┬────┘
   │                   │                 │                  │                   │
   │ POST /api/query   │                 │                  │                   │
   ├──────────────────>│                 │                  │                   │
   │                   │                 │                  │                   │
   │                   ├─ classify ─────>│                  │                   │
   │                   │<────────────────┤                  │                   │
   │                   │                 │                  │                   │
   │                   ├─ retrieve ──────┼─────────────────>│                   │
   │                   │                 │                  │                   │
   │                   │                 │           [Vector Query]             │
   │                   │                 │                  │                   │
   │                   │                 │             Pinecone 429             │
   │                   │                 │                  │                   │
   │                   │                 │          [Retry with backoff]        │
   │                   │                 │                  │                   │
   │                   │                 │          [Retry with backoff]        │
   │                   │                 │                  │                   │
   │                   │                 │             Pinecone 429             │
   │                   │                 │                  │                   │
   │                   │                 │          [Circuit Breaker Opens]     │
   │                   │                 │                  │                   │
   │                   │                 │     [Fallback to BM25 only]          │
   │                   │                 │                  │                   │
   │                   │                 │  Limited Results │                   │
   │                   │                 │<─────────────────┤                   │
   │                   │                 │                  │                   │
   │                   ├─ generate ──────┼──────────────────┼──────────────────>│
   │                   │                 │                  │                   │
   │                   │  Answer (degraded mode noted)       │                   │
   │<──────────────────┤                 │                  │                   │
   │                   │                 │                  │                   │
```

**Degraded Operation:** Falls back to BM25-only retrieval if vector search fails

## Ingestion Flow with Deduplication

```
┌──────┐          ┌─────────┐        ┌────────┐        ┌────────┐       ┌──────────┐
│Upload│          │FastAPI  │        │Ingest  │        │Embed   │       │Pinecone  │
└──┬───┘          └────┬────┘        └───┬────┘        └───┬────┘       └────┬─────┘
   │                   │                 │                  │                  │
   │ POST /ingest/file │                 │                  │                  │
   ├──────────────────>│                 │                  │                  │
   │                   │                 │                  │                  │
   │              [Validate size/type]   │                  │                  │
   │                   │                 │                  │                  │
   │                   │  process_file   │                  │                  │
   │                   ├────────────────>│                  │                  │
   │                   │                 │                  │                  │
   │                   │            [Load with UnstructuredLoader]             │
   │                   │                 │                  │                  │
   │                   │            [Chunk (1000/200)]      │                  │
   │                   │                 │                  │                  │
   │                   │            [Deduplicate]           │                  │
   │                   │                 │                  │                  │
   │                   │                 │   embed_batch    │                  │
   │                   │                 ├─────────────────>│                  │
   │                   │                 │                  │                  │
   │                   │                 │            [Voyage API]             │
   │                   │                 │                  │                  │
   │                   │                 │            [Add idempotency keys]   │
   │                   │                 │                  │                  │
   │                   │                 │  Vectors         │                  │
   │                   │                 │<─────────────────┤                  │
   │                   │                 │                  │                  │
   │                   │                 │            upsert (with retry)      │
   │                   │                 ├────────────────────────────────────>│
   │                   │                 │                  │                  │
   │                   │                 │            [Check existing by ID]   │
   │                   │                 │                  │                  │
   │                   │                 │            [Upsert batch=100]       │
   │                   │                 │                  │                  │
   │                   │                 │  Success         │                  │
   │                   │                 │<────────────────────────────────────┤
   │                   │                 │                  │                  │
   │                   │  Stats          │                  │                  │
   │                   │<────────────────┤                  │                  │
   │                   │                 │                  │                  │
   │   202 Accepted    │                 │                  │                  │
   │<──────────────────┤                 │                  │                  │
   │                   │                 │                  │                  │
```

## DMS Sync with Error Handling

```
┌───────┐          ┌────────┐        ┌────────┐        ┌─────────┐
│Celery │          │Tasks   │        │DMS     │        │Pinecone │
└───┬───┘          └───┬────┘        └───┬────┘        └────┬────┘
    │                  │                  │                  │
    │ sync_dms_hourly  │                  │                  │
    ├─────────────────>│                  │                  │
    │                  │                  │                  │
    │             [Connect to DMS]        │                  │
    │                  ├─────────────────>│                  │
    │                  │                  │                  │
    │                  │  Inventory Data  │                  │
    │                  │<─────────────────┤                  │
    │                  │                  │                  │
    │             [Transform to docs]     │                  │
    │                  │                  │                  │
    │             [Generate embeddings]   │                  │
    │                  │                  │                  │
    │                  │            Upsert vectors           │
    │                  ├────────────────────────────────────>│
    │                  │                  │                  │
    │                  │  Success         │                  │
    │                  │<────────────────────────────────────┤
    │                  │                  │                  │
    │  Task Complete   │                  │                  │
    │<─────────────────┤                  │                  │
    │                  │                  │                  │
```

## Failure Modes & Recovery

### Scenario 1: Claude API Timeout
- **Detection:** asyncio.timeout(5s) on intent classification
- **Fallback:** Rule-based intent classification
- **Impact:** Reduced accuracy (75% vs 95%) but no service interruption
- **Recovery:** Automatic, no user impact

### Scenario 2: DMS API Slow Response
- **Detection:** asyncio.timeout(10s) on DMS calls
- **Fallback:** Use cached data or return partial results
- **Impact:** Potentially stale inventory data
- **Recovery:** Log error, retry on next sync

### Scenario 3: Pinecone Rate Limit
- **Detection:** HTTP 429 from Pinecone API
- **Fallback:** Use BM25-only retrieval
- **Impact:** Lower semantic relevance, keyword-based results only
- **Recovery:** Exponential backoff retry, circuit breaker after 3 failures

### Scenario 4: Redis Connection Loss
- **Detection:** Connection exception on cache operations
- **Fallback:** Direct query processing (no cache)
- **Impact:** Increased latency, higher LLM API costs
- **Recovery:** Continue operating, reconnect in background

### Scenario 5: Large File Upload
- **Detection:** File size > 10MB
- **Fallback:** Queue to Celery for background processing
- **Impact:** Async processing, immediate 202 response
- **Recovery:** N/A - normal degraded mode

## Performance Characteristics

### Latency Breakdown (Typical Query)
```
Total: 1.8s
├─ Intent Classification: 0.3s (Claude API)
├─ DMS Tool Call: 0.4s (if needed)
├─ Vector Search: 0.2s (Pinecone)
├─ BM25 Search: 0.1s (local)
├─ Reranking: 0.3s (Cohere API)
└─ Generation: 0.5s (Claude API)
```

### Scalability Limits

**Current Architecture:**
- Concurrent queries: ~50/s (2 FastAPI workers)
- Vector storage: Unlimited (Pinecone serverless)
- Cache hit rate: 60-70% (1 hour TTL)
- DMS sync: Hourly (configurable)

**With Horizontal Scaling (K8s):**
- Concurrent queries: ~500/s (20 replicas)
- Autoscaling triggers: CPU > 70%, Memory > 80%
- Load balancer: Round-robin with health checks
- Redis: Clustered with read replicas

## Circuit Breaker States

```
[CLOSED] ──> [OPEN] ──> [HALF-OPEN] ──> [CLOSED]
   │           │             │             │
   │           │             │             │
Failures    Timeout      Test Call    Success
Threshold   Expires      Succeeds     Rate OK
Reached     (30s)
```

**Parameters:**
- Failure threshold: 5 errors in 60 seconds
- Open timeout: 30 seconds
- Half-open test calls: 3
- Success threshold to close: 3 consecutive successes

