## Key Features
- **Real-Time DMS Integration**: Adapters for major systems; mock mode for demos.
- **Hybrid Retrieval**: Vector (Pinecone) + keyword (BM25) with Cohere re-rank for spot-on results.
- **Agentic Routing**: Classifies intents (sales/service/inventory/predictive) and calls tools for live data.
- **Anti-Hallucination Generation**: Claude-4.5-sonnet enforces context-only answers with citations.
- **Performance & Observability**: <2s latency, Redis caching, LangSmith tracing.
- **Compliance-Ready**: PII anonymization, GDPR hooks.
- **2025 Edges**: Hosted Inference for embeddings, EV-specific metadata, feedback loops.

## Technology Stack
| Component | Version/Choice | Why? |
|-----------|----------------|------|
| **Orchestration** | LangChain 0.3.27 | Battle-tested for RAG pipelines; agentic support.
| **Embeddings** | Voyage-3.5-large | SOTA for automotive jargon; integrated with Pinecone Hosted Inference.
| **Vector DB** | Pinecone (serverless) 6.0.0 | Auto-scales; hybrid search and inference baked in.
| **LLM** | Claude-4.5-sonnet (Anthropic 0.69.0) | Massive context, low hallucinations for factual output.
| **Re-ranker** | Cohere Rerank v3.5 | Precision on noisy docs like manuals/reviews.
| **Doc Parsing** | Unstructured.io 0.18.15 + SQLAlchemy 2.0.44 | Handles PDFs, DMS SQL/APIs seamlessly.
| **API Backend** | FastAPI 0.119.0 | Async, lightweight; auto-docs for handoff.
| **Testing** | Pytest 8.4.2 | 80%+ coverage; edge cases included.
| **Infra** | Docker + GitHub Actions | One-command deploy; CI/CD ready.

## Quick Start
### Prerequisites
- Python 3.12+
- API keys: Voyage, Anthropic, Cohere, Pinecone
- Optional: Redis for caching, Celery for scheduling

### Installation
1. Clone the repo:
git clone https://your-repo-url/dealership-rag.git
cd dealership-rag
text2. Set up environment:
cp .env.example .env
Edit .env with your API keys and DMS configs
text3. Install dependencies:
pip install -r requirements.txt
text4. Build and run with Docker:
docker-compose up --build
textThe app runs on `http://localhost:8000`. Check `/docs` for OpenAPI swagger.

## Usage
### Ingest Data
Upload docs or sync DMS:
curl -X POST http://localhost:8000/api/ingest -F "file=@data/sample_inventory.json"
textTriggers embedding and indexing.

### Query the System
Ask away:
curl -X POST http://localhost:8000/api/query 
-H "Content-Type: application/json" 
-d '{"query": "What low-mileage Camrys are in stock?"}'
textResponse: Factual answer with sources, e.g., "2024 Toyota Camry LE, VIN: XYZ, 12k miles, $28k [Source: Inventory DMS]".

### Health Check
curl http://localhost:8000/api/health
text## Demo Data
- `data/sample_inventory.json`: 50+ vehicles with specs.
- PDFs: Policies, manuals, FAQs.
- Run `python src/ingest.py --demo` to preload.

## Development & Testing
- Run tests: `pytest --cov=src`
- Monitor: Integrate LangSmith for traces.
- Extend: Swap DMS adapters in `src/dms/` or add agents in `src/agent.py`.

## Architecture Overview
![Architecture Diagram](docs/architecture.png)

High-level: Query → Router → Retrieve (hybrid) → Re-rank → Generate (Claude) → Respond.

## Contributing
Fork, PR, or ping for collabs. Focus on automotive edge cases.

## License
MIT—free to tweak for your dealership empire.

Built by Sean McDonnell 10/10/2025
