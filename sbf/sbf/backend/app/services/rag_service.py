"""
RAG Service for PDF ingestion and retrieval.
Uses ChromaDB for vector storage (in-memory for MVP).
"""

import io
from typing import List, Optional
import structlog

from ..core.config import settings

logger = structlog.get_logger()


class RAGService:
    """
    RAG service for PDF document processing.
    Extracts text from PDFs and stores embeddings in ChromaDB.
    """

    def __init__(self, workflow_id: str):
        self.workflow_id = workflow_id
        self._collection = None

    def _get_collection(self):
        """Get or create ChromaDB collection."""
        if self._collection is not None:
            return self._collection

        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            # In-memory client for MVP
            client = chromadb.Client(ChromaSettings(
                anonymized_telemetry=False,
                allow_reset=True
            ))

            self._collection = client.get_or_create_collection(
                name=f"sbf_{self.workflow_id}",
                metadata={"workflow_id": self.workflow_id}
            )

            return self._collection

        except Exception as e:
            logger.error("chromadb_init_failed", error=str(e))
            raise

    async def ingest_pdfs(
        self,
        files: List,  # List[UploadFile]
        brand_name: str
    ) -> str:
        """
        Ingest PDF files and return combined context.

        Args:
            files: List of uploaded PDF files
            brand_name: Brand name for context

        Returns:
            Combined text context from PDFs
        """
        all_text = []

        for file in files:
            try:
                # Read file content
                content = await file.read()

                # Extract text from PDF
                text = await self._extract_pdf_text(content, file.filename)

                if text:
                    all_text.append(f"## {file.filename}\n{text}")
                    logger.info(
                        "pdf_extracted",
                        filename=file.filename,
                        text_length=len(text)
                    )

            except Exception as e:
                logger.error(
                    "pdf_extraction_failed",
                    filename=file.filename,
                    error=str(e)
                )
                continue

        if not all_text:
            return ""

        combined_text = "\n\n".join(all_text)

        # Store in vector DB for potential retrieval
        try:
            await self._store_embeddings(combined_text, brand_name)
        except Exception as e:
            logger.warning("embedding_storage_failed", error=str(e))

        # Truncate if too long
        max_context = settings.MAX_CONTEXT_TOKENS * 4  # Rough char estimate
        if len(combined_text) > max_context:
            combined_text = combined_text[:max_context] + "\n\n[Content truncated...]"

        return combined_text

    async def _extract_pdf_text(self, content: bytes, filename: str) -> str:
        """Extract text from PDF content."""
        try:
            import pypdf

            # Create PDF reader from bytes
            pdf_reader = pypdf.PdfReader(io.BytesIO(content))

            text_parts = []
            for page_num, page in enumerate(pdf_reader.pages):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
                except Exception as e:
                    logger.warning(
                        "page_extraction_failed",
                        filename=filename,
                        page=page_num,
                        error=str(e)
                    )

            return "\n\n".join(text_parts)

        except ImportError:
            # Fallback to pdfminer if pypdf not available
            try:
                from pdfminer.high_level import extract_text as pdfminer_extract

                return pdfminer_extract(io.BytesIO(content))

            except ImportError:
                logger.error("no_pdf_library_available")
                raise ImportError("No PDF extraction library available (pypdf or pdfminer)")

    async def _store_embeddings(self, text: str, brand_name: str):
        """Store text embeddings in ChromaDB."""
        try:
            from ..services.cleaner import text_splitter

            # Split text into chunks
            chunks = text_splitter.split(text)

            if not chunks:
                return

            collection = self._get_collection()

            # Add documents with IDs
            ids = [f"{self.workflow_id}_{i}" for i in range(len(chunks))]
            metadatas = [{"brand": brand_name, "chunk_index": i} for i in range(len(chunks))]

            collection.add(
                documents=chunks,
                ids=ids,
                metadatas=metadatas
            )

            logger.info(
                "embeddings_stored",
                workflow_id=self.workflow_id,
                chunks=len(chunks)
            )

        except Exception as e:
            logger.error("embedding_storage_error", error=str(e))
            raise

    async def query(
        self,
        query_text: str,
        n_results: int = 5
    ) -> List[str]:
        """
        Query stored documents for relevant context.

        Args:
            query_text: Query string
            n_results: Number of results to return

        Returns:
            List of relevant text chunks
        """
        try:
            collection = self._get_collection()

            results = collection.query(
                query_texts=[query_text],
                n_results=n_results
            )

            if results and results.get("documents"):
                return results["documents"][0]

            return []

        except Exception as e:
            logger.error("rag_query_failed", error=str(e))
            return []
