"""
Document ingestion pipeline.
Handles loading, parsing, and chunking of various document formats.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    UnstructuredFileLoader,
    CSVLoader,
    TextLoader,
    PyPDFLoader,
)
from langchain.schema import Document
from sqlalchemy import create_engine, text

from src.config import settings


class DocumentIngestionPipeline:
    """Pipeline for ingesting and processing documents."""
    
    def __init__(self):
        """Initialize the ingestion pipeline."""
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
    
    async def ingest_file(
        self,
        file_path: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        """
        Ingest a single file.
        
        Args:
            file_path: Path to the file
            metadata: Optional metadata to attach to documents
            
        Returns:
            List of Document objects with chunks
        """
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Select appropriate loader based on file extension
        loader = self._get_loader(file_path)
        
        # Load documents
        raw_documents = loader.load()
        
        # Add metadata
        for doc in raw_documents:
            doc.metadata.update({
                "source": file_path,
                "file_type": path.suffix,
                "ingested_at": datetime.now().isoformat(),
                **(metadata or {})
            })
        
        # Split into chunks
        chunks = self.text_splitter.split_documents(raw_documents)
        
        return chunks
    
    async def ingest_directory(
        self,
        directory_path: str,
        glob_pattern: str = "**/*",
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        """
        Ingest all files in a directory.
        
        Args:
            directory_path: Path to directory
            glob_pattern: Glob pattern for file selection
            metadata: Optional metadata to attach
            
        Returns:
            List of Document objects
        """
        directory = Path(directory_path)
        
        if not directory.exists() or not directory.is_dir():
            raise NotADirectoryError(f"Invalid directory: {directory_path}")
        
        all_chunks = []
        
        for file_path in directory.glob(glob_pattern):
            if file_path.is_file():
                try:
                    chunks = await self.ingest_file(str(file_path), metadata)
                    all_chunks.extend(chunks)
                except Exception as e:
                    print(f"Error processing {file_path}: {e}")
                    continue
        
        return all_chunks
    
    async def ingest_json(
        self,
        json_data: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        """
        Ingest JSON data.
        
        Args:
            json_data: JSON string or file path
            metadata: Optional metadata
            
        Returns:
            List of Document objects
        """
        # Try to parse as JSON
        try:
            data = json.loads(json_data)
        except json.JSONDecodeError:
            # If not valid JSON, treat as file path
            with open(json_data, 'r') as f:
                data = json.load(f)
        
        documents = []
        
        # Handle different JSON structures
        if isinstance(data, list):
            for item in data:
                doc_text = json.dumps(item, indent=2)
                doc = Document(
                    page_content=doc_text,
                    metadata={
                        "source": "json",
                        "type": "json_object",
                        "ingested_at": datetime.now().isoformat(),
                        **(metadata or {})
                    }
                )
                documents.append(doc)
        elif isinstance(data, dict):
            doc_text = json.dumps(data, indent=2)
            doc = Document(
                page_content=doc_text,
                metadata={
                    "source": "json",
                    "type": "json_object",
                    "ingested_at": datetime.now().isoformat(),
                    **(metadata or {})
                }
            )
            documents.append(doc)
        
        # Split into chunks
        chunks = self.text_splitter.split_documents(documents)
        
        return chunks
    
    async def ingest_sql_query(
        self,
        database_url: str,
        query: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        """
        Ingest data from SQL query results.
        
        Args:
            database_url: Database connection URL
            query: SQL query to execute
            metadata: Optional metadata
            
        Returns:
            List of Document objects
        """
        engine = create_engine(database_url)
        
        with engine.connect() as connection:
            result = connection.execute(text(query))
            rows = result.fetchall()
            columns = result.keys()
        
        documents = []
        
        for row in rows:
            row_dict = dict(zip(columns, row))
            doc_text = json.dumps(row_dict, indent=2)
            
            doc = Document(
                page_content=doc_text,
                metadata={
                    "source": "database",
                    "type": "sql_query",
                    "ingested_at": datetime.now().isoformat(),
                    **(metadata or {})
                }
            )
            documents.append(doc)
        
        # Split into chunks
        chunks = self.text_splitter.split_documents(documents)
        
        return chunks
    
    async def ingest_text(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        """
        Ingest raw text.
        
        Args:
            text: Text content
            metadata: Optional metadata
            
        Returns:
            List of Document objects
        """
        doc = Document(
            page_content=text,
            metadata={
                "source": "text_input",
                "type": "text",
                "ingested_at": datetime.now().isoformat(),
                **(metadata or {})
            }
        )
        
        # Split into chunks
        chunks = self.text_splitter.split_documents([doc])
        
        return chunks
    
    def _get_loader(self, file_path: str):
        """
        Get appropriate document loader based on file extension.
        
        Args:
            file_path: Path to file
            
        Returns:
            Document loader instance
        """
        path = Path(file_path)
        extension = path.suffix.lower()
        
        loader_map = {
            '.pdf': PyPDFLoader,
            '.txt': TextLoader,
            '.csv': CSVLoader,
            '.json': UnstructuredFileLoader,
            '.md': TextLoader,
            '.html': UnstructuredFileLoader,
            '.docx': UnstructuredFileLoader,
            '.doc': UnstructuredFileLoader,
        }
        
        loader_class = loader_map.get(extension, UnstructuredFileLoader)
        
        return loader_class(file_path)
    
    def deduplicate_chunks(self, chunks: List[Document]) -> List[Document]:
        """
        Remove duplicate chunks based on content hash.
        
        Args:
            chunks: List of Document objects
            
        Returns:
            Deduplicated list of Document objects
        """
        seen_hashes = set()
        unique_chunks = []
        
        for chunk in chunks:
            content_hash = hash(chunk.page_content)
            
            if content_hash not in seen_hashes:
                seen_hashes.add(content_hash)
                unique_chunks.append(chunk)
        
        return unique_chunks

