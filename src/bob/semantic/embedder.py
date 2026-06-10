"""
IBM Bob - Semantic Embedder
Generates vector embeddings for code symbols using LLM APIs
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

try:
    import openai
    from sentence_transformers import SentenceTransformer
except ImportError:
    openai = None
    SentenceTransformer = None

from bob.config import get_settings
from bob.exceptions import EmbeddingError, LLMAPIError
from bob.parsers.base import CodeSymbol, ParseResult

logger = logging.getLogger(__name__)


@dataclass
class CodeChunk:
    """Represents a chunk of code for embedding"""

    content: str
    file_path: str
    symbol_name: str
    symbol_type: str
    start_line: int
    end_line: int
    token_count: int


@dataclass
class Embedding:
    """Represents a vector embedding"""

    vector: list[float]
    chunk: CodeChunk
    model: str
    timestamp: float


class SemanticEmbedder:
    """
    Generates semantic embeddings for code symbols.

    Responsibilities:
    - Implement chunking strategy (≤512 tokens per chunk)
    - Integrate OpenAI/Gemini embeddings API
    - Batch requests, exponential backoff on rate limits
    - Fall back to local model (all-MiniLM) if quota exceeded
    - Generate embeddings per function/class
    """

    def __init__(self) -> None:
        """Initialize the semantic embedder"""
        self.settings = get_settings()
        self._local_model: Any = None
        self._openai_client: Any = None
        self._rate_limit_delay = 0.1  # Start with 100ms delay
        self._max_retries = 3

    def __enter__(self) -> "SemanticEmbedder":
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit"""
        pass

    def embed_text(self, text: str) -> Embedding:
        """Generate embedding for a single text query"""
        chunk = CodeChunk(
            content=text,
            file_path="",
            symbol_name="",
            symbol_type="",
            start_line=0,
            end_line=0,
            token_count=len(text) // 4,
        )

        try:
            if self.settings.llm_provider == "openai" and self.settings.openai_api_key:
                embeddings = self._embed_with_openai([chunk])
            elif self.settings.llm_provider == "gemini" and self.settings.gemini_api_key:
                embeddings = self._embed_with_gemini([chunk])
            else:
                embeddings = self._embed_with_local_model([chunk])
        except Exception as e:
            logger.warning(f"API embedding failed, using local model: {e}")
            embeddings = self._embed_with_local_model([chunk])

        if not embeddings:
            raise EmbeddingError("Failed to generate embedding for query")

        return embeddings[0]

    def _get_openai_client(self) -> Any:
        """Get or create OpenAI client"""
        if self._openai_client is None:
            if openai is None:
                raise ImportError("openai package not installed")

            if not self.settings.openai_api_key:
                raise EmbeddingError(
                    "OpenAI API key not configured",
                    details={"provider": "openai"},
                )

            self._openai_client = openai.OpenAI(api_key=self.settings.openai_api_key)

        return self._openai_client

    def _get_local_model(self) -> Any:
        """Get or load local embedding model"""
        if self._local_model is None:
            if SentenceTransformer is None:
                raise ImportError("sentence-transformers package not installed")

            logger.info("Loading local embedding model: all-MiniLM-L6-v2")
            self._local_model = SentenceTransformer("all-MiniLM-L6-v2")

        return self._local_model

    def embed_parse_results(
        self,
        parse_results: list[ParseResult],
        use_local_fallback: bool = True,
    ) -> list[Embedding]:
        """
        Generate embeddings for all symbols in parse results.

        Args:
            parse_results: List of parse results
            use_local_fallback: Whether to fall back to local model on API failure

        Returns:
            List of embeddings
        """
        logger.info(f"Generating embeddings for {len(parse_results)} files")

        # Extract chunks from parse results
        chunks = self._extract_chunks(parse_results)
        logger.info(f"Extracted {len(chunks)} code chunks")

        # Generate embeddings
        embeddings = []

        try:
            # Try API first
            if self.settings.llm_provider == "openai" and self.settings.openai_api_key:
                embeddings = self._embed_with_openai(chunks)
            elif self.settings.llm_provider == "gemini" and self.settings.gemini_api_key:
                embeddings = self._embed_with_gemini(chunks)
            else:
                # No API configured, use local model
                logger.info("No LLM API configured, using local model")
                embeddings = self._embed_with_local_model(chunks)

        except (LLMAPIError, EmbeddingError) as e:
            logger.warning(f"API embedding failed: {e}")

            if use_local_fallback:
                logger.info("Falling back to local embedding model")
                embeddings = self._embed_with_local_model(chunks)
            else:
                raise

        logger.info(f"Generated {len(embeddings)} embeddings")
        return embeddings

    def _extract_chunks(self, parse_results: list[ParseResult]) -> list[CodeChunk]:
        """
        Extract code chunks from parse results.

        Implements chunking strategy with ≤512 tokens per chunk.
        """
        chunks = []

        for result in parse_results:
            for symbol in result.symbols:
                # Skip symbols without body
                if not symbol.body:
                    continue

                # Estimate token count (rough approximation: 1 token ≈ 4 chars)
                estimated_tokens = len(symbol.body) // 4

                if estimated_tokens <= 512:
                    # Single chunk
                    chunk = CodeChunk(
                        content=symbol.body,
                        file_path=result.file_path,
                        symbol_name=symbol.name,
                        symbol_type=symbol.symbol_type.value,
                        start_line=symbol.start_line,
                        end_line=symbol.end_line,
                        token_count=estimated_tokens,
                    )
                    chunks.append(chunk)
                else:
                    # Split into multiple chunks with overlap
                    sub_chunks = self._split_into_chunks(symbol, result.file_path)
                    chunks.extend(sub_chunks)

        return chunks

    def _split_into_chunks(
        self,
        symbol: CodeSymbol,
        file_path: str,
        max_tokens: int = 512,
        overlap_tokens: int = 50,
    ) -> list[CodeChunk]:
        """
        Split large symbol into smaller chunks with overlap.

        Args:
            symbol: Code symbol to split
            file_path: File path
            max_tokens: Maximum tokens per chunk
            overlap_tokens: Overlap between chunks for context

        Returns:
            List of code chunks
        """
        chunks = []

        if not symbol.body:
            return chunks

        # Split by lines
        lines = symbol.body.split("\n")

        # Approximate chars per chunk
        max_chars = max_tokens * 4
        overlap_chars = overlap_tokens * 4

        current_chunk = []
        current_chars = 0
        chunk_start_line = symbol.start_line

        for i, line in enumerate(lines):
            line_chars = len(line)

            if current_chars + line_chars > max_chars and current_chunk:
                # Create chunk
                chunk_content = "\n".join(current_chunk)
                chunk_end_line = symbol.start_line + i - 1

                chunks.append(
                    CodeChunk(
                        content=chunk_content,
                        file_path=file_path,
                        symbol_name=symbol.name,
                        symbol_type=symbol.symbol_type.value,
                        start_line=chunk_start_line,
                        end_line=chunk_end_line,
                        token_count=current_chars // 4,
                    )
                )

                # Start new chunk with overlap
                overlap_lines = []
                overlap_size = 0
                for prev_line in reversed(current_chunk):
                    if overlap_size + len(prev_line) <= overlap_chars:
                        overlap_lines.insert(0, prev_line)
                        overlap_size += len(prev_line)
                    else:
                        break

                current_chunk = overlap_lines + [line]
                current_chars = overlap_size + line_chars
                chunk_start_line = symbol.start_line + i - len(overlap_lines)
            else:
                current_chunk.append(line)
                current_chars += line_chars

        # Add final chunk
        if current_chunk:
            chunk_content = "\n".join(current_chunk)
            chunks.append(
                CodeChunk(
                    content=chunk_content,
                    file_path=file_path,
                    symbol_name=symbol.name,
                    symbol_type=symbol.symbol_type.value,
                    start_line=chunk_start_line,
                    end_line=symbol.end_line,
                    token_count=current_chars // 4,
                )
            )

        return chunks

    def _embed_with_openai(self, chunks: list[CodeChunk]) -> list[Embedding]:
        """Generate embeddings using OpenAI API"""
        client = self._get_openai_client()
        embeddings = []

        # Batch process chunks
        batch_size = 100  # OpenAI allows up to 2048 inputs per request

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]  # noqa: E203
            texts = [chunk.content for chunk in batch]

            # Retry with exponential backoff
            for attempt in range(self._max_retries):
                try:
                    response = client.embeddings.create(
                        model=self.settings.embedding_model,
                        input=texts,
                    )

                    # Create embedding objects
                    for j, embedding_data in enumerate(response.data):
                        embeddings.append(
                            Embedding(
                                vector=embedding_data.embedding,
                                chunk=batch[j],
                                model=self.settings.embedding_model,
                                timestamp=time.time(),
                            )
                        )

                    # Success - reset rate limit delay
                    self._rate_limit_delay = 0.1
                    break

                except openai.RateLimitError as e:
                    if attempt < self._max_retries - 1:
                        # Exponential backoff
                        delay = self._rate_limit_delay * (2**attempt)
                        logger.warning(
                            f"Rate limit hit, retrying in {delay:.2f}s (attempt {attempt + 1}/{self._max_retries})"  # noqa: E501
                        )
                        time.sleep(delay)
                    else:
                        raise LLMAPIError(
                            f"OpenAI rate limit exceeded after {self._max_retries} retries",
                            details={"batch": i // batch_size},
                        ) from e

                except Exception as e:
                    raise LLMAPIError(
                        f"OpenAI API error: {str(e)}",
                        details={"batch": i // batch_size},
                    ) from e

            # Small delay between batches
            if i + batch_size < len(chunks):
                time.sleep(self._rate_limit_delay)

        return embeddings

    def _embed_with_gemini(self, chunks: list[CodeChunk]) -> list[Embedding]:
        """Generate embeddings using Gemini API"""
        # Placeholder for Gemini implementation
        # Would use google-generativeai package
        raise NotImplementedError("Gemini embeddings not yet implemented")

    def _embed_with_local_model(self, chunks: list[CodeChunk]) -> list[Embedding]:
        """Generate embeddings using local model"""
        model = self._get_local_model()
        embeddings = []

        # Batch process for efficiency
        batch_size = 32

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]  # noqa: E203
            texts = [chunk.content for chunk in batch]

            try:
                # Generate embeddings
                vectors = model.encode(texts, show_progress_bar=False)

                # Create embedding objects
                for j, vector in enumerate(vectors):
                    embeddings.append(
                        Embedding(
                            vector=vector.tolist(),
                            chunk=batch[j],
                            model="all-MiniLM-L6-v2",
                            timestamp=time.time(),
                        )
                    )

            except Exception as e:
                raise EmbeddingError(
                    f"Local model embedding failed: {str(e)}",
                    details={"batch": i // batch_size},
                ) from e

        return embeddings

    async def embed_parse_results_async(
        self,
        parse_results: list[ParseResult],
        use_local_fallback: bool = True,
    ) -> list[Embedding]:
        """
        Async version of embed_parse_results.

        Args:
            parse_results: List of parse results
            use_local_fallback: Whether to fall back to local model on API failure

        Returns:
            List of embeddings
        """
        # For now, just wrap the sync version
        # A production implementation would use async HTTP clients
        return await asyncio.to_thread(self.embed_parse_results, parse_results, use_local_fallback)


Embedder = SemanticEmbedder

# Made with Bob
