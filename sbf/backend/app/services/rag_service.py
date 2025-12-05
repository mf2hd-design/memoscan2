"""
RAG (Retrieval-Augmented Generation) service for PDF document processing.
Uses in-memory ChromaDB for ephemeral storage during workflow execution.
"""

from typing import List, Optional
from fastapi import UploadFile
import tempfile
import os
import structlog

import chromadb
from chromadb.config import Settings
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings

from ..core.config import settings as app_settings

logger = structlog.get_logger()


class RAGService:
    """
    In-memory RAG service for PDF processing.
    Each workflow gets its own ephemeral collection that's auto-cleaned.
    """

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id

        # In-memory ChromaDB client (no persistence)
        self.client = chromadb.Client(Settings(
            anonymized_telemetry=False,
            is_persistent=False  # KEY: Ephemeral storage
        ))

        self.embeddings = OpenAIEmbeddings(
            openai_api_key=app_settings.OPENAI_API_KEY
        )

        self.collection = None
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )

        logger.info("rag_service_initialized", workflow_id=workflow_id)

    async def ingest_pdfs(
        self,
        files: List[UploadFile],
        brand_name: str = ""
    ) -> str:
        """
        Parse PDFs, chunk, embed, and store in ChromaDB.

        Args:
            files: List of uploaded PDF files
            brand_name: Brand name for contextualized queries

        Returns:
            Summary context string for LLM prompt
        """
        if not files:
            return ""

        logger.info("ingesting_pdfs", count=len(files), workflow_id=self.workflow_id)

        # Create collection for this workflow
        self.collection = self.client.create_collection(
            name=f"workflow_{self.workflow_id}",
            metadata={"workflow_id": self.workflow_id}
        )

        all_chunks = []
        chunk_id = 0

        for file_idx, file in enumerate(files):
            # Check file size
            content = await file.read()
            size_mb = len(content) / (1024 * 1024)

            if size_mb > app_settings.MAX_PDF_SIZE_MB:
                logger.warning(
                    "pdf_too_large",
                    filename=file.filename,
                    size_mb=size_mb,
                    max_mb=app_settings.MAX_PDF_SIZE_MB
                )
                continue

            # Save to temporary file (PyPDF needs file path)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            try:
                # Extract text from PDF
                pdf_reader = PdfReader(tmp_path)
                text = ""

                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n\n"

                if not text.strip():
                    logger.warning("pdf_no_text", filename=file.filename)
                    continue

                # Chunk the text
                chunks = self.text_splitter.split_text(text)

                # Store chunks with metadata
                for chunk in chunks:
                    if not chunk.strip():
                        continue

                    chunk_id += 1
                    self.collection.add(
                        documents=[chunk],
                        metadatas=[{
                            "source": file.filename or f"file_{file_idx + 1}",
                            "chunk_id": chunk_id
                        }],
                        ids=[f"chunk_{chunk_id}"]
                    )
                    all_chunks.append(chunk)

                logger.info(
                    "pdf_processed",
                    filename=file.filename,
                    pages=len(pdf_reader.pages),
                    chunks=len(chunks)
                )

            except Exception as e:
                logger.error("pdf_processing_error", filename=file.filename, error=str(e))

            finally:
                # Clean up temp file
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

        if not all_chunks:
            logger.warning("no_pdf_content", workflow_id=self.workflow_id)
            return ""

        # Query for most relevant chunks
        query_text = f"Key information about {brand_name}" if brand_name else "Important information"

        try:
            results = self.collection.query(
                query_texts=[query_text],
                n_results=min(5, len(all_chunks))
            )

            # Format context for LLM
            context = "\n--- UPLOADED DOCUMENTS CONTEXT ---\n"

            if results and results.get('documents') and results['documents'][0]:
                for idx, doc in enumerate(results['documents'][0]):
                    source = "uploaded PDF"
                    if results.get('metadatas') and results['metadatas'][0]:
                        source = results['metadatas'][0][idx].get('source', 'uploaded PDF')

                    context += f"\n[PDF {idx + 1}] From {source}:\n{doc}\n"

            logger.info(
                "pdf_ingestion_complete",
                total_chunks=len(all_chunks),
                context_length=len(context)
            )

            return context

        except Exception as e:
            logger.error("pdf_query_error", error=str(e))
            # Fallback: return first few chunks
            fallback_context = "\n--- UPLOADED DOCUMENTS CONTEXT ---\n"
            for idx, chunk in enumerate(all_chunks[:5]):
                fallback_context += f"\n[PDF {idx + 1}]:\n{chunk}\n"

            return fallback_context

    def query(self, query_text: str, n_results: int = 3) -> List[str]:
        """
        Query the vector store for relevant chunks.

        Args:
            query_text: Query string
            n_results: Number of results to return

        Returns:
            List of relevant text chunks
        """
        if not self.collection:
            return []

        try:
            results = self.collection.query(
                query_texts=[query_text],
                n_results=n_results
            )

            if results and results.get('documents') and results['documents'][0]:
                return results['documents'][0]

            return []

        except Exception as e:
            logger.error("rag_query_error", query=query_text, error=str(e))
            return []

    # No cleanup() method needed - Python GC handles in-memory ChromaDB
