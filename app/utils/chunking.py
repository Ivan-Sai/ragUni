from typing import List
from app.config import get_settings

settings = get_settings()


def chunk_text(text: str, chunk_size: int = None, overlap: int = None) -> List[str]:
    """
    Split text into overlapping chunks

    Args:
        text: Input text to chunk
        chunk_size: Size of each chunk in characters
        overlap: Number of overlapping characters between chunks

    Returns:
        List of text chunks
    """
    if chunk_size is None:
        chunk_size = settings.chunk_size
    if overlap is None:
        overlap = settings.chunk_overlap

    if not text or len(text) == 0:
        return []

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        # Try to break at sentence boundary if possible
        if end < len(text):
            # Look for sentence endings near the end of chunk
            for punctuation in ['. ', '! ', '? ', '\n\n']:
                last_punct = text.rfind(punctuation, start, end)
                if last_punct != -1 and last_punct > start + chunk_size // 2:
                    end = last_punct + len(punctuation)
                    break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Move start position with overlap
        start = end - overlap if end < len(text) else end

    return chunks


def chunk_by_paragraphs(text: str, max_chunk_size: int = None) -> List[str]:
    """
    Chunk text by paragraphs, combining small paragraphs

    Args:
        text: Input text to chunk
        max_chunk_size: Maximum size of each chunk

    Returns:
        List of text chunks
    """
    if max_chunk_size is None:
        max_chunk_size = settings.chunk_size

    paragraphs = text.split('\n\n')
    chunks = []
    current_chunk = []
    current_size = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        para_size = len(para)

        if current_size + para_size > max_chunk_size and current_chunk:
            # Save current chunk and start new one
            chunks.append('\n\n'.join(current_chunk))
            current_chunk = [para]
            current_size = para_size
        else:
            current_chunk.append(para)
            current_size += para_size

    # Add remaining chunk
    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))

    return chunks
