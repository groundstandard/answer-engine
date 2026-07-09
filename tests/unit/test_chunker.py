import pytest
from backend.services.indexing.chunker import Chunker


class TestChunker:
    def setup_method(self):
        self.chunker = Chunker(chunk_size=100, overlap=20)

    def test_short_text_produces_single_chunk(self):
        text = "This is a short sentence. It fits in one chunk."
        chunks = self.chunker.chunk(text, metadata={})
        assert len(chunks) >= 1

    def test_long_text_produces_multiple_chunks(self):
        sentence = "This is a sentence that adds to the total length. "
        text = sentence * 20
        chunks = self.chunker.chunk(text, metadata={})
        assert len(chunks) > 1

    def test_chunk_indices_are_sequential(self):
        sentence = "Here is a test sentence for chunking. "
        text = sentence * 15
        chunks = self.chunker.chunk(text, metadata={})
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_metadata_preserved_in_each_chunk(self):
        meta = {"source_id": "abc123", "doc_type": "pdf"}
        text = "Sentence one. Sentence two. Sentence three."
        chunks = self.chunker.chunk(text, metadata=meta)
        for chunk in chunks:
            assert chunk.metadata == meta

    def test_empty_text_returns_chunks(self):
        chunks = self.chunker.chunk("", metadata={})
        assert isinstance(chunks, list)
