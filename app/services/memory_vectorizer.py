import struct
import json
import logging
import math

import requests
from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.research_memory import ResearchMemory

logger = logging.getLogger(__name__)


class MemoryVectorizer:

    def __init__(self):
        self._provider = None
        self._ollama_base_url = "http://localhost:11434"
        self._embedding_model = "nomic-embed-text"
        self._openai_model = "text-embedding-3-small"
        self._detect_provider()

    def _detect_provider(self):
        settings = get_settings()
        provider_pref = getattr(settings, "embedding_provider", "auto")
        self._ollama_base_url = getattr(settings, "ollama_base_url", self._ollama_base_url)
        self._embedding_model = getattr(settings, "embedding_model", self._embedding_model)

        if provider_pref == "disabled":
            self._provider = None
            logger.info("Embedding provider explicitly disabled")
            return

        if provider_pref == "openai":
            if settings.llm_api_key:
                self._provider = "openai"
                logger.info("Embedding provider forced to OpenAI")
                return
            logger.warning("OpenAI embedding requested but no API key configured")
            self._provider = None
            return

        if provider_pref == "ollama":
            if self._check_ollama():
                self._provider = "ollama"
                logger.info("Embedding provider forced to Ollama")
                return
            logger.warning("Ollama embedding requested but Ollama not reachable")
            self._provider = None
            return

        if self._check_ollama():
            self._provider = "ollama"
            logger.info("Auto-detected Ollama as embedding provider")
            return

        if settings.llm_api_key:
            self._provider = "openai"
            logger.info("Falling back to OpenAI as embedding provider")
            return

        self._provider = None
        logger.info("No embedding provider available (Ollama unreachable, no OpenAI key)")

    def _check_ollama(self) -> bool:
        try:
            resp = requests.get(f"{self._ollama_base_url}/api/tags", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    def embed_text(self, text: str) -> list[float] | None:
        if not text or not text.strip():
            return None
        if self._provider == "ollama":
            return self._embed_ollama(text)
        if self._provider == "openai":
            return self._embed_openai(text)
        return None

    def embed_query(self, query: str) -> list[float] | None:
        return self.embed_text(query)

    def embed_texts_batch(self, texts: list[str]) -> list[list[float] | None]:
        if not texts:
            return []
        if self._provider == "ollama":
            return [self._embed_ollama(t) for t in texts]
        if self._provider == "openai":
            return self._embed_openai_batch(texts)
        return [None] * len(texts)

    def _embed_ollama(self, text: str) -> list[float] | None:
        try:
            resp = requests.post(
                f"{self._ollama_base_url}/api/embed",
                json={"model": self._embedding_model, "input": text},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["embeddings"][0]
        except Exception as e:
            logger.warning("Ollama embedding failed: %s", e)
            return None

    def _embed_openai(self, text: str) -> list[float] | None:
        try:
            settings = get_settings()
            client = OpenAI(
                base_url=settings.llm_api_base,
                api_key=settings.llm_api_key,
                timeout=30,
            )
            response = client.embeddings.create(
                model=self._openai_model,
                input=text,
            )
            return response.data[0].embedding
        except Exception as e:
            logger.warning("OpenAI embedding failed: %s", e)
            return None

    def _embed_openai_batch(self, texts: list[str]) -> list[list[float] | None]:
        try:
            settings = get_settings()
            client = OpenAI(
                base_url=settings.llm_api_base,
                api_key=settings.llm_api_key,
                timeout=60,
            )
            valid_indices = []
            valid_texts = []
            for i, t in enumerate(texts):
                if t and t.strip():
                    valid_indices.append(i)
                    valid_texts.append(t)

            if not valid_texts:
                return [None] * len(texts)

            response = client.embeddings.create(
                model=self._openai_model,
                input=valid_texts,
            )

            results: list[list[float] | None] = [None] * len(texts)
            for idx, emb_obj in enumerate(response.data):
                original_idx = valid_indices[emb_obj.index] if len(valid_indices) > emb_obj.index else valid_indices[idx]
                results[original_idx] = emb_obj.embedding
            return results
        except Exception as e:
            logger.warning("OpenAI batch embedding failed: %s", e)
            return [None] * len(texts)

    def backfill_embeddings(self, db: Session) -> dict:
        if self._provider is None:
            logger.info("No embedding provider available, skipping backfill")
            return {"processed": 0, "failed": 0}

        memories = (
            db.query(ResearchMemory)
            .filter(ResearchMemory.embedding.is_(None))
            .order_by(ResearchMemory.id.asc())
            .all()
        )

        if not memories:
            return {"processed": 0, "failed": 0}

        processed = 0
        failed = 0
        batch_size = 20

        for batch_start in range(0, len(memories), batch_size):
            batch = memories[batch_start : batch_start + batch_size]
            texts = [m.content for m in batch]
            embeddings = self.embed_texts_batch(texts)

            for memory, embedding in zip(batch, embeddings):
                if embedding is not None:
                    memory.embedding = self._encode_embedding(embedding)
                    memory.embedding_model = self._embedding_model if self._provider == "ollama" else self._openai_model
                    processed += 1
                else:
                    failed += 1

            try:
                db.commit()
            except Exception as e:
                db.rollback()
                logger.warning("Failed to commit embedding batch: %s", e)
                failed += len(batch) - processed
                processed = 0

        return {"processed": processed, "failed": failed}

    @staticmethod
    def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)

    @staticmethod
    def _encode_embedding(embedding: list[float]) -> bytes:
        return struct.pack(f"<{len(embedding)}f", *embedding)

    @staticmethod
    def _decode_embedding(blob: bytes) -> list[float]:
        count = len(blob) // struct.calcsize("<f")
        return list(struct.unpack(f"<{count}f", blob))


memory_vectorizer = MemoryVectorizer()
