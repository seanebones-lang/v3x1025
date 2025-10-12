# Configuration Schema

Auto-generated schema for API consumers and infrastructure teams.

## Environment Variables

### Required for Production

| Variable | Type | Required | Description |
|----------|------|----------|-------------|
| ANTHROPIC_API_KEY | string | Yes (prod) | Anthropic API key for Claude LLM |
| VOYAGE_API_KEY | string | Yes (prod) | Voyage AI API key for embeddings |
| COHERE_API_KEY | string | Yes (prod) | Cohere API key for re-ranking |
| PINECONE_API_KEY | string | Yes (prod) | Pinecone API key for vector database |

### Optional Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| PINECONE_ENVIRONMENT | string | us-east-1-aws | Pinecone environment region |
| PINECONE_INDEX_NAME | string | dealership-rag | Pinecone index name |
| DMS_ADAPTER | enum | mock | DMS adapter: cdk, reynolds, mock |
| CDK_API_KEY | string | "" | CDK Global API key |
| CDK_API_URL | string | https://api.cdkglobal.com/v1 | CDK API endpoint |
| REYNOLDS_API_KEY | string | "" | Reynolds & Reynolds API key |
| REYNOLDS_API_URL | string | https://api.reyrey.com/v1 | Reynolds API endpoint |

### Redis Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| REDIS_HOST | string | localhost | Redis host address |
| REDIS_PORT | integer | 6379 | Redis port |
| REDIS_PASSWORD | string | "" | Redis password (if auth enabled) |
| REDIS_DB | integer | 0 | Redis database number |

### Application Settings

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| API_SECRET_KEY | string | dev-secret-change-in-production | API authentication secret |
| ENVIRONMENT | enum | development | Environment: development, staging, production |
| LOG_LEVEL | string | INFO | Logging level: DEBUG, INFO, WARNING, ERROR |

### Performance Tuning

| Variable | Type | Default | Range | Description |
|----------|------|---------|-------|-------------|
| CHUNK_SIZE | integer | 1000 | 500-2000 | Text chunk size for splitting |
| CHUNK_OVERLAP | integer | 200 | 0-500 | Overlap between chunks |
| TOP_K_RETRIEVAL | integer | 20 | 5-50 | Initial retrieval count |
| TOP_K_RERANK | integer | 5 | 1-20 | Final results after rerank |
| MAX_TOKENS_GENERATION | integer | 1000 | 100-4000 | Max LLM generation tokens |
| QUERY_TIMEOUT_SECONDS | integer | 30 | 10-120 | Query timeout limit |

### Rate Limiting

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| RATE_LIMIT_PER_MINUTE | integer | 100 | Requests per minute per IP |
| RATE_LIMIT_BURST | integer | 20 | Burst allowance |

## Configuration Examples

### Development

```bash
ENVIRONMENT=development
LOG_LEVEL=DEBUG
DMS_ADAPTER=mock
ANTHROPIC_API_KEY=
VOYAGE_API_KEY=
COHERE_API_KEY=
PINECONE_API_KEY=
```

### Production

```bash
ENVIRONMENT=production
LOG_LEVEL=INFO
DMS_ADAPTER=cdk
ANTHROPIC_API_KEY=sk-ant-api03-xxx
VOYAGE_API_KEY=pa-xxx
COHERE_API_KEY=xxx
PINECONE_API_KEY=xxx
CDK_API_KEY=xxx
REDIS_HOST=prod-redis.example.com
REDIS_PASSWORD=secure-password
API_SECRET_KEY=production-secret-key-change-me
CHUNK_SIZE=1000
TOP_K_RETRIEVAL=20
TOP_K_RERANK=5
RATE_LIMIT_PER_MINUTE=100
```

## JSON Schema

```json
{
  "type": "object",
  "properties": {
    "anthropic_api_key": {"type": "string", "minLength": 1},
    "voyage_api_key": {"type": "string", "minLength": 1},
    "cohere_api_key": {"type": "string", "minLength": 1},
    "pinecone_api_key": {"type": "string", "minLength": 1},
    "environment": {"enum": ["development", "staging", "production"]},
    "chunk_size": {"type": "integer", "minimum": 500, "maximum": 2000},
    "top_k_retrieval": {"type": "integer", "minimum": 5, "maximum": 50}
  }
}
```

## Validation

Configuration is validated at startup using Pydantic. Invalid values will raise clear error messages.

Test configuration:
```bash
python -c "from src.config import settings; print(settings.model_dump_json(indent=2))"
```

