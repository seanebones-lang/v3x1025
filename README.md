# Production Dealership RAG System

Enterprise-grade Retrieval-Augmented Generation (RAG) system tailored for automotive dealerships. Integrates with Dealer Management Systems (DMS) like CDK Global, Reynolds & Reynolds, and Dealertrack for real-time inventory pulls, customer queries, sales assistance, and service documentation. Built on 2025 best practices: branched agentic architecture for dynamic workflows, hybrid retrieval for precision, and multimodal-ready for car images or EVs. Anti-hallucination safeguards ensure factual responses—perfect for boosting sales conversions and service efficiency without the BS.

This project's your golden ticket, Sean—modular code for easy handoff, full tests, and a Docker setup that deploys in minutes. It handles fuzzy queries like "Low-mileage EVs under 40k?" or pulls VIN specs without fabricating details. Extensible for predictive maintenance or tariff impacts.

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
