#!/bin/bash
# Quickstart script for Dealership RAG System
# Sets up and launches the system in one command

set -e

echo " Dealership RAG System - Quickstart"
echo "======================================"
echo ""

# Check for Docker
if ! command -v docker &> /dev/null; then
    echo " Docker not found. Please install Docker first."
    echo "   Visit: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo " Docker Compose not found. Please install Docker Compose first."
    exit 1
fi

echo " Docker and Docker Compose found"
echo ""

# Check for .env file
if [ ! -f .env ]; then
    echo " Creating .env file from template..."
    cp .env.example .env
    echo "️  IMPORTANT: Edit .env with your API keys before running in production"
    echo "   Required keys: ANTHROPIC_API_KEY, VOYAGE_API_KEY, COHERE_API_KEY, PINECONE_API_KEY"
    echo ""
fi

# Build and start containers
echo "️  Building Docker containers..."
docker-compose build

echo ""
echo " Starting services..."
docker-compose up -d

echo ""
echo "⏳ Waiting for services to be ready..."
sleep 5

# Check if API is responding
echo " Checking API status..."
for i in {1..30}; do
    if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
        echo " API is ready!"
        break
    fi
    if [ $i -eq 30 ]; then
        echo " API failed to start. Check logs with: docker-compose logs api"
        exit 1
    fi
    sleep 2
    echo "   Waiting... ($i/30)"
done

echo ""
echo "======================================"
echo " System is ready!"
echo "======================================"
echo ""
echo " API Documentation: http://localhost:8000/docs"
echo " Health Check: http://localhost:8000/api/health"
echo ""
echo " Next steps:"
echo "   1. Edit .env with your API keys (required for production)"
echo "   2. Ingest demo data: docker-compose exec api python scripts/demo_ingest.py"
echo "   3. Test queries: docker-compose exec api python scripts/demo_query.py"
echo ""
echo " Useful commands:"
echo "   View logs:     docker-compose logs -f api"
echo "   Stop system:   docker-compose down"
echo "   Restart:       docker-compose restart"
echo ""
echo " Running in MOCK mode (demo data)"
echo "   Set DMS_ADAPTER=cdk or DMS_ADAPTER=reynolds in .env for real DMS"
echo ""

