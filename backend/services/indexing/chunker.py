import re
from dataclasses import dataclass
from typing import List


@dataclass
class Chunk:
    text: str
    chunk_index: int
    char_start: int
    char_end: int
    metadata: dict


class Chunker:
    """
    Splits documents into overlapping chunks using a sliding window strategy.
    Uses sentence-aware splitting to avoid cutting mid-sentence.
    """

    def __init__(self, chunk_size: int = 512, overlap: int = 64):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str, metadata: dict) -> List[Chunk]:
        sentences = self._split_sentences(text)
        chunks = []
        current, char_start = [], 0
        current_len = 0

        for sentence in sentences:
            s_len = len(sentence)
            if current_len + s_len > self.chunk_size and current:
                chunk_text = " ".join(current)
                chunks.append(
                    Chunk(
                        text=chunk_text,
                        chunk_index=len(chunks),
                        char_start=char_start,
                        char_end=char_start + len(chunk_text),
                        metadata=metadata,
                    )
                )
                # Overlap: keep last N chars worth of sentences
                overlap_text = chunk_text[-self.overlap :]
                char_start += len(chunk_text) - self.overlap
                current = [overlap_text]
                current_len = len(overlap_text)

            current.append(sentence)
            current_len += s_len

        if current:
            chunk_text = " ".join(current)
            chunks.append(
                Chunk(
                    text=chunk_text,
                    chunk_index=len(chunks),
                    char_start=char_start,
                    char_end=char_start + len(chunk_text),
                    metadata=metadata,
                )
            )

        return chunks

    def _split_sentences(self, text: str) -> List[str]:
        return re.split(r"(?<=[.!?])\s+", text.strip())
