# Dealership RAG System

**Enterprise-grade Retrieval Augmented Generation for Automotive Dealerships**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.119.0-009688.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Built by Sean McDonnell | October 2025

---

## 🚀 Key Features

- **Real-Time DMS Integration**: Adapters for CDK Global, Reynolds & Reynolds, and mock mode for demos
- **Hybrid Retrieval**: Vector search (Pinecone) + keyword matching (BM25) with Cohere re-ranking
- **Agentic Routing**: Intelligent intent classification routes queries to specialized agents (Sales/Service/Inventory/Predictive)
- **Anti-Hallucination**: Claude 4.5 Sonnet enforces context-only answers with source citations
- **Performance**: <2s query latency with Redis caching and async operations
- **Compliance-Ready**: PII anonymization hooks, GDPR support
- **Production Patterns**: Docker containerized, full test coverage, CI/CD pipeline, observability

## 📋 Technology Stack

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Orchestration** | LangChain | 0.3.27 | RAG pipeline coordination |
| **LLM** | Claude 4.5 Sonnet | Latest | Answer generation & intent classification |
| **Embeddings** | Voyage AI | 3.5-large | SOTA automotive embeddings (3072-dim) |
| **Vector DB** | Pinecone | 6.0.0 | Serverless vector storage with hybrid search |
| **Re-ranker** | Cohere | v3.5 | Precision filtering for top results |
| **API** | FastAPI | 0.119.0 | Async REST API with auto-docs |
| **Cache** | Redis | 7.4 | Query caching & Celery broker |
| **Tasks** | Celery | 5.4.0 | Background job processing |
| **Testing** | Pytest | 8.4.2 | Comprehensive test suite |
| **Infrastructure** | Docker | Latest | Containerized deployment |

## 🏗️ Architecture

```
User Query → Intent Classifier (Claude) → Specialized Agent
                                              ↓
                        ┌─────────────────────┴─────────────────────┐
                        │                                           │
                   DMS Tools                              Hybrid Retrieval
              (Live Inventory Data)                    (Vector + BM25 + Rerank)
                        │                                           │
                        └─────────────────────┬─────────────────────┘
                                              ↓
                              Answer Generation (Claude)
                                   with Source Citations
                                              ↓
                                       JSON Response
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed system design.

## ⚡ Quick Start

### Prerequisites

- **Python 3.12+**
- **Docker & Docker Compose** (recommended)
- **API Keys** (for production use):
  - Anthropic (Claude)
  - Voyage AI (embeddings)
  - Cohere (re-ranking)
  - Pinecone (vector database)

### Installation

#### Option 1: Docker (Recommended)

```bash
# 1. Clone the repository
git clone https://github.com/seanebones-lang/AutoRAG.git
cd AutoRAG

# 2. Configure environment
cp .env.example .env
# Edit .env with your API keys

# 3. Launch the system
docker-compose up --build

# 4. Access the API
open http://localhost:8000/docs
```

#### Option 2: Local Development

```bash
# 1. Clone and setup
git clone https://github.com/seanebones-lang/AutoRAG.git
cd AutoRAG

# 2. Create virtual environment
python3.12 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your API keys

# 5. Run the application
uvicorn src.app:app --host 0.0.0.0 --port 8000 --reload
```

### First Run

```bash
# 1. Check system health
curl http://localhost:8000/api/health

# 2. Ingest sample data
python scripts/demo_ingest.py

# 3. Test a query
python scripts/demo_query.py

# Or use the API directly
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What Toyota vehicles are available under $30k?"}'
```

## 📖 Usage Examples

### Querying the System

```python
import requests

# Basic query
response = requests.post(
    "http://localhost:8000/api/query",
    json={
        "query": "Show me electric vehicles with low mileage",
        "include_sources": True,
        "top_k": 5
    }
)

result = response.json()
print(result["answer"])
for source in result["sources"]:
    print(f"Source: {source['metadata']['source']}")
```

### Ingesting Documents

```python
# Ingest text
response = requests.post(
    "http://localhost:8000/api/ingest",
    json={
        "source_type": "text",
        "content": "Your document content here",
        "metadata": {"type": "policy"},
        "namespace": "default"
    }
)

# Ingest file
files = {"file": open("document.pdf", "rb")}
response = requests.post(
    "http://localhost:8000/api/ingest/file",
    files=files,
    params={"namespace": "manuals"}
)
```

### Using Different Namespaces

```python
# Organize by data type
namespaces = {
    "sales": "Sales policies and pricing",
    "service": "Service manuals and procedures",
    "inventory": "Vehicle inventory data"
}

# Query specific namespace
response = requests.post(
    "http://localhost:8000/api/query",
    json={
        "query": "Oil change procedure",
        "filters": {"namespace": "service"}
    }
)
```

## 🧪 Testing

```bash
# Run all tests with coverage
pytest --cov=src --cov-report=html --cov-report=term

# Run specific test file
pytest tests/test_agent.py -v

# Run with markers
pytest -m "not slow" -v

# View coverage report
open htmlcov/index.html
```

## 🔧 Configuration

All configuration is managed through environment variables. See `.env.example` for all options.

### Key Settings

```bash
# API Keys (Required for production)
ANTHROPIC_API_KEY=sk-ant-your-key
VOYAGE_API_KEY=pa-your-key
COHERE_API_KEY=your-key
PINECONE_API_KEY=your-key

# DMS Integration
DMS_ADAPTER=mock  # Options: cdk, reynolds, mock
CDK_API_KEY=your-cdk-key
REYNOLDS_API_KEY=your-reynolds-key

# Performance Tuning
CHUNK_SIZE=1000
CHUNK_OVERLAP=200
TOP_K_RETRIEVAL=20
TOP_K_RERANK=5

# Caching
REDIS_HOST=localhost
REDIS_PORT=6379
```

## 📊 Monitoring & Observability

### Health Checks

```bash
# System health
curl http://localhost:8000/api/health

# Detailed metrics
curl http://localhost:8000/api/metrics

# System statistics
curl http://localhost:8000/api/stats
```

### LangSmith Integration

```bash
# Enable in .env
LANGSMITH_API_KEY=your-key
LANGSMITH_PROJECT=dealership-rag
LANGSMITH_TRACING=true
```

### Sentry Error Tracking

```bash
# Configure in .env
SENTRY_DSN=your-sentry-dsn
```

## 🔌 API Endpoints

Full API documentation available at `http://localhost:8000/docs`

### Query Endpoints

- `POST /api/query` - Submit a query
- `POST /api/query/stream` - Stream query response

### Ingestion Endpoints

- `POST /api/ingest` - Ingest documents
- `POST /api/ingest/file` - Upload and ingest file

### Management Endpoints

- `GET /api/health` - System health check
- `GET /api/metrics` - Performance metrics
- `GET /api/stats` - Detailed statistics
- `DELETE /api/index/{namespace}` - Clear namespace

See [docs/API.md](docs/API.md) for detailed API documentation.

## 🗂️ Project Structure

```
dealership-rag/
├── src/
│   ├── agent.py           # Agentic routing & intent classification
│   ├── app.py             # FastAPI application
│   ├── config.py          # Configuration management
│   ├── models.py          # Pydantic data models
│   ├── ingest.py          # Document ingestion pipeline
│   ├── embed.py           # Embedding generation & vector storage
│   ├── retrieve.py        # Hybrid retrieval engine
│   ├── generate.py        # Answer generation with Claude
│   ├── tasks.py           # Celery background tasks
│   └── dms/               # DMS adapter implementations
│       ├── base.py        # Abstract adapter interface
│       ├── mock_adapter.py
│       ├── cdk_adapter.py
│       └── reynolds_adapter.py
├── tests/                 # Comprehensive test suite
├── data/                  # Sample data
├── docs/                  # Documentation
├── scripts/               # Demo & utility scripts
├── docker-compose.yml     # Multi-container orchestration
├── Dockerfile            # Application container
└── requirements.txt      # Python dependencies
```

## 🚦 Development Workflow

### Adding a New DMS Adapter

1. Create new adapter in `src/dms/your_adapter.py`
2. Inherit from `BaseDMSAdapter`
3. Implement required methods
4. Add tests in `tests/test_dms.py`
5. Register in `src/dms/__init__.py`

### Adding a New Agent

1. Define intent in `src/agent.py` `IntentType` enum
2. Add routing logic in `_route_to_agent()`
3. Implement tool calling in `_call_dms_tools()`
4. Add tests in `tests/test_agent.py`

### Custom Embeddings

Replace Voyage AI in `src/embed.py`:

```python
from your_embedding_provider import YourEmbeddings

self.embeddings = YourEmbeddings(
    api_key=settings.your_api_key,
    model="your-model"
)
```

## 🐛 Troubleshooting

### Common Issues

**Redis Connection Failed**
```bash
# Start Redis manually
docker run -d -p 6379:6379 redis:7.4-alpine
```

**API Key Errors**
```bash
# Verify keys are set
python -c "from src.config import settings; print(settings.anthropic_api_key[:10])"
```

**Import Errors**
```bash
# Ensure you're in the project root and venv is activated
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

**Pinecone Index Not Found**
```bash
# Index is created automatically on first run
# Or create manually via Pinecone console
```

## 📈 Performance Optimization

- **Caching**: Redis stores query results for 1 hour
- **Batch Processing**: Embeddings processed in batches of 100
- **Async Operations**: All I/O operations are non-blocking
- **Connection Pooling**: Database connections are reused
- **Streaming**: Long responses streamed to reduce latency

## 🔒 Security

- API key authentication via Bearer token
- Rate limiting (100 requests/minute per IP)
- Input validation with Pydantic
- SQL injection protection
- CORS configuration for production
- Environment variable secrets (never commit `.env`)

## 📄 License

MIT License - see [LICENSE](LICENSE) for details

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Ensure all tests pass
5. Submit a pull request

Focus areas:
- Additional DMS adapters
- Performance optimizations
- Test coverage improvements
- Documentation enhancements

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/seanebones-lang/AutoRAG/issues)
- **Documentation**: [docs/](docs/)
- **API Reference**: `http://localhost:8000/docs`

## 🎯 Roadmap

- [ ] Multimodal support (vehicle images with CLIP)
- [ ] Voice interface integration
- [ ] Custom fine-tuned embeddings
- [ ] Mobile app SDK
- [ ] Multi-language support
- [ ] Advanced analytics dashboard
- [ ] Kubernetes deployment configs

---

**Built with precision for automotive excellence** 🚗⚡

*Production-ready RAG system following 2025 best practices*
