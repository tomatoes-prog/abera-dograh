"""Tenant-configured OpenAI-compatible embeddings, checked against pgvector."""

import math

import httpx

from .openai_service import EMBEDDING_DIMENSION, OpenAIEmbeddingService


def validate_embedding_vectors(
    vectors: list[list[float]], *, expected_count: int
) -> None:
    if len(vectors) != expected_count:
        raise ValueError(
            "El proveedor devolvió un número de embeddings distinto al solicitado."
        )
    for vector in vectors:
        if not isinstance(vector, (list, tuple)):
            raise ValueError(
                "El proveedor devolvió un embedding con formato no válido."
            )
        if len(vector) != EMBEDDING_DIMENSION:
            raise ValueError(
                f"El modelo devuelve {len(vector)} dimensiones. "
                f"La base de conocimiento requiere {EMBEDDING_DIMENSION}; usa un modelo compatible."
            )
        if any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            for value in vector
        ):
            raise ValueError(
                "El proveedor devolvió un embedding con valores no válidos."
            )


class OpenAICompatibleEmbeddingService(OpenAIEmbeddingService):
    def __init__(self, *, db_client, api_key: str | None, model_id: str, base_url: str):
        super().__init__(
            db_client=db_client,
            api_key=api_key,
            model_id=model_id,
            base_url=base_url,
            http_client=httpx.AsyncClient(follow_redirects=False, trust_env=False)
            if api_key
            else None,
        )

    def _request_kwargs(self):
        return {"encoding_format": "float"}

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors = await super().embed_texts(texts)
        validate_embedding_vectors(vectors, expected_count=len(texts))
        return vectors
