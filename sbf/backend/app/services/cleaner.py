"""
HTML cleaning and text chunking service.
Converts HTML to clean text and chunks for LLM context management.
"""

from bs4 import BeautifulSoup
from langchain_text_splitters import RecursiveCharacterTextSplitter
from typing import List, Tuple
import re


class HTMLCleaner:
    """Service for cleaning HTML and preparing text for LLM analysis."""

    def __init__(self):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=4000,
            chunk_overlap=200,
            separators=["\n\n", "\n", ". ", " ", ""]
        )

    def clean_html(self, html_content: str) -> str:
        """
        Clean HTML and extract readable text.

        Args:
            html_content: Raw HTML string

        Returns:
            Clean text content
        """
        if not html_content or not html_content.strip():
            return ""

        soup = BeautifulSoup(html_content, "html.parser")

        # Remove unwanted elements
        for element in soup(["script", "style", "nav", "footer", "iframe", "noscript", "header"]):
            element.extract()

        # Get text
        text = soup.get_text(separator="\n")

        # Clean whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)

        # Remove excessive newlines
        text = re.sub(r'\n\s*\n+', '\n\n', text)

        return text.strip()

    def chunk_text(self, text: str, max_chunks: int = 5) -> List[str]:
        """
        Split text into manageable chunks for LLM processing.

        Args:
            text: Clean text to chunk
            max_chunks: Maximum number of chunks to return

        Returns:
            List of text chunks
        """
        if not text:
            return []

        docs = self.splitter.create_documents([text])
        chunks = [doc.page_content for doc in docs[:max_chunks]]

        return chunks

    def clean_and_chunk(self, html_content: str, source_id: int, max_chunks: int = 3) -> str:
        """
        Clean HTML and format with citation markers for LLM context.

        Args:
            html_content: Raw HTML
            source_id: Citation number for [x] markers
            max_chunks: Maximum chunks to include

        Returns:
            Formatted text with citation markers
        """
        # Clean HTML
        clean_text = self.clean_html(html_content)

        if not clean_text:
            return ""

        # Chunk text
        chunks = self.chunk_text(clean_text, max_chunks=max_chunks)

        # Format with citations
        formatted_chunks = []
        for idx, chunk in enumerate(chunks):
            chunk_header = f"\n--- SOURCE [{source_id}] PART {idx + 1} START ---\n"
            chunk_footer = f"\n--- SOURCE [{source_id}] PART {idx + 1} END ---\n"
            formatted_chunks.append(f"{chunk_header}{chunk}{chunk_footer}")

        return "\n".join(formatted_chunks)

    def extract_social_links(self, html_content: str) -> dict:
        """
        Extract social media links from HTML.

        Args:
            html_content: Raw HTML

        Returns:
            Dict with platform: url mapping
        """
        soup = BeautifulSoup(html_content, "html.parser")
        social_links = {
            "twitter": None,
            "linkedin": None,
            "facebook": None,
            "instagram": None,
            "youtube": None
        }

        # Find all links
        for link in soup.find_all('a', href=True):
            href = link['href'].lower()

            if 'twitter.com' in href or 'x.com' in href:
                social_links["twitter"] = link['href']
            elif 'linkedin.com' in href:
                social_links["linkedin"] = link['href']
            elif 'facebook.com' in href:
                social_links["facebook"] = link['href']
            elif 'instagram.com' in href:
                social_links["instagram"] = link['href']
            elif 'youtube.com' in href:
                social_links["youtube"] = link['href']

        return social_links

    def extract_keywords(self, text: str, max_keywords: int = 10) -> List[str]:
        """
        Extract potential keywords/topics from text.

        Args:
            text: Clean text
            max_keywords: Maximum keywords to return

        Returns:
            List of keywords
        """
        # Simple keyword extraction (could be enhanced with NLP)
        words = re.findall(r'\b[A-Z][a-z]+\b', text)

        # Count frequency
        from collections import Counter
        word_counts = Counter(words)

        # Return most common
        return [word for word, count in word_counts.most_common(max_keywords)]


# Singleton instance
html_cleaner = HTMLCleaner()
