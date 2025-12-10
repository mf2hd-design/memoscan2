"""
HTML cleaning and text processing utilities.
"""

import re
from typing import List, Optional
from bs4 import BeautifulSoup
import structlog

logger = structlog.get_logger()


class HTMLCleaner:
    """Clean and extract text from HTML content."""

    # Tags to completely remove (including content)
    REMOVE_TAGS = [
        'script', 'style', 'noscript', 'iframe', 'svg', 'canvas',
        'video', 'audio', 'map', 'object', 'embed'
    ]

    # Tags to unwrap (keep content, remove tag)
    UNWRAP_TAGS = [
        'span', 'div', 'section', 'article', 'main', 'aside',
        'header', 'footer', 'nav', 'figure', 'figcaption'
    ]

    def __init__(self, max_length: int = 50000):
        self.max_length = max_length

    def clean(self, html: str) -> str:
        """Clean HTML and extract readable text."""
        if not html:
            return ""

        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Remove unwanted tags completely
            for tag in self.REMOVE_TAGS:
                for element in soup.find_all(tag):
                    element.decompose()

            # Remove HTML comments (not regular text nodes)
            from bs4 import Comment
            for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
                comment.extract()

            # Get text
            text = soup.get_text(separator=' ', strip=True)

            # Clean up whitespace
            text = re.sub(r'\s+', ' ', text)
            text = re.sub(r'\n\s*\n', '\n\n', text)

            # Truncate if needed
            if len(text) > self.max_length:
                text = text[:self.max_length] + "..."

            return text.strip()

        except Exception as e:
            logger.error("html_clean_error", error=str(e))
            return ""

    def extract_structured(self, html: str) -> dict:
        """Extract structured content from HTML."""
        if not html:
            return {"title": "", "headings": [], "paragraphs": [], "links": []}

        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Remove unwanted tags
            for tag in self.REMOVE_TAGS:
                for element in soup.find_all(tag):
                    element.decompose()

            # Extract title
            title = ""
            title_tag = soup.find('title')
            if title_tag:
                title = title_tag.get_text(strip=True)

            # Extract headings
            headings = []
            for level in range(1, 7):
                for h in soup.find_all(f'h{level}'):
                    text = h.get_text(strip=True)
                    if text:
                        headings.append({"level": level, "text": text})

            # Extract paragraphs
            paragraphs = []
            for p in soup.find_all('p'):
                text = p.get_text(strip=True)
                if text and len(text) > 20:  # Filter short paragraphs
                    paragraphs.append(text)

            # Extract links
            links = []
            for a in soup.find_all('a', href=True):
                href = a.get('href', '')
                text = a.get_text(strip=True)
                if href and text and href.startswith('http'):
                    links.append({"url": href, "text": text})

            return {
                "title": title,
                "headings": headings[:20],  # Limit
                "paragraphs": paragraphs[:50],  # Limit
                "links": links[:30]  # Limit
            }

        except Exception as e:
            logger.error("html_extract_error", error=str(e))
            return {"title": "", "headings": [], "paragraphs": [], "links": []}


class TextSplitter:
    """Split text into chunks for processing."""

    def __init__(
        self,
        chunk_size: int = 4000,
        chunk_overlap: int = 200,
        separators: Optional[List[str]] = None
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", ". ", " ", ""]

    def split(self, text: str) -> List[str]:
        """Split text into overlapping chunks."""
        if not text:
            return []

        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        current_chunk = ""

        # Split by paragraphs first
        paragraphs = text.split("\n\n")

        for para in paragraphs:
            if len(current_chunk) + len(para) + 2 <= self.chunk_size:
                current_chunk += para + "\n\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    # Keep overlap
                    overlap_start = max(0, len(current_chunk) - self.chunk_overlap)
                    current_chunk = current_chunk[overlap_start:] + para + "\n\n"
                else:
                    # Paragraph itself is too long - split further
                    if len(para) > self.chunk_size:
                        # Split by sentences
                        sentences = re.split(r'(?<=[.!?])\s+', para)
                        for sentence in sentences:
                            if len(current_chunk) + len(sentence) + 1 <= self.chunk_size:
                                current_chunk += sentence + " "
                            else:
                                if current_chunk:
                                    chunks.append(current_chunk.strip())
                                current_chunk = sentence + " "
                    else:
                        current_chunk = para + "\n\n"

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks


class CitationMarker:
    """Add citation markers to text chunks."""

    @staticmethod
    def add_citations(chunks: List[str], source_url: str) -> List[str]:
        """Add source citation markers to chunks."""
        marked = []
        for i, chunk in enumerate(chunks):
            citation = f"[Source: {source_url}, Chunk {i+1}]"
            marked.append(f"{chunk}\n\n{citation}")
        return marked

    @staticmethod
    def extract_citations(text: str) -> List[dict]:
        """Extract citation markers from text."""
        pattern = r'\[Source: ([^,]+), Chunk (\d+)\]'
        matches = re.findall(pattern, text)
        return [{"url": url, "chunk": int(chunk)} for url, chunk in matches]


# Convenience instances
html_cleaner = HTMLCleaner()
text_splitter = TextSplitter()
