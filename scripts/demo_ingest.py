#!/usr/bin/env python3
"""
Demo script to ingest sample data into the RAG system.
Run this after starting the API server to populate the system with demo data.
"""

import asyncio
import json
from pathlib import Path

from src.ingest import DocumentIngestionPipeline
from src.agent import AgenticRAG


async def main():
    """Ingest all sample data."""
    print("🚀 Starting demo data ingestion...")
    print("=" * 60)
    
    # Initialize components
    pipeline = DocumentIngestionPipeline()
    rag = AgenticRAG()
    
    total_chunks = 0
    total_docs = 0
    
    # 1. Ingest sample inventory JSON
    print("\n📦 Ingesting sample inventory...")
    inventory_path = Path("data/sample_inventory.json")
    
    if inventory_path.exists():
        try:
            with open(inventory_path, 'r') as f:
                inventory_data = json.load(f)
            
            # Convert to text documents
            for vehicle in inventory_data:
                doc_text = f"""
Vehicle: {vehicle['year']} {vehicle['make']} {vehicle['model']} {vehicle.get('trim', '')}
VIN: {vehicle['vin']}
Price: ${vehicle.get('price', 'N/A')}
Mileage: {vehicle.get('mileage', 'N/A')} miles
Status: {vehicle.get('status', 'unknown')}
Color: {vehicle.get('color_exterior', 'N/A')}
Engine: {vehicle.get('engine', 'N/A')}
Transmission: {vehicle.get('transmission', 'N/A')}
Fuel Type: {vehicle.get('fuel_type', 'N/A')}
Features: {', '.join(vehicle.get('features', []))}
Stock #: {vehicle.get('stock_number', 'N/A')}
"""
                chunks = await pipeline.ingest_text(
                    doc_text,
                    metadata={
                        "source": "sample_inventory.json",
                        "document_type": "vehicle",
                        "vin": vehicle['vin'],
                        "make": vehicle['make'],
                        "model": vehicle['model'],
                        "year": vehicle['year']
                    }
                )
                
                # Index chunks
                await rag.retriever.index_documents(chunks, namespace="inventory")
                total_chunks += len(chunks)
                total_docs += 1
            
            print(f"   ✅ Ingested {total_docs} vehicles")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    else:
        print(f"   ⚠️  File not found: {inventory_path}")
    
    # 2. Ingest FAQs
    print("\n❓ Ingesting FAQs...")
    faq_path = Path("data/faqs.txt")
    
    if faq_path.exists():
        try:
            chunks = await pipeline.ingest_file(
                str(faq_path),
                metadata={
                    "source": "faqs.txt",
                    "document_type": "faq",
                    "category": "general"
                }
            )
            
            await rag.retriever.index_documents(chunks, namespace="general")
            total_chunks += len(chunks)
            print(f"   ✅ Ingested FAQs ({len(chunks)} chunks)")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    else:
        print(f"   ⚠️  File not found: {faq_path}")
    
    # Summary
    print("\n" + "=" * 60)
    print(f"✨ Ingestion Complete!")
    print(f"   Total Documents: {total_docs}")
    print(f"   Total Chunks: {total_chunks}")
    print(f"   Indexed in: inventory, general")
    print("\n💡 Ready to query! Try:")
    print("   python scripts/demo_query.py")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

