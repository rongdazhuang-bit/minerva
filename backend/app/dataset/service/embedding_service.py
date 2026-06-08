"""Embedding calls for dataset indexing."""



from __future__ import annotations



import uuid



from sqlalchemy.ext.asyncio import AsyncSession



from app.dataset.rag.embedding.cached_embedding import embed_texts_with_cache

from app.dataset.service.embedding_resolver import resolve_embedding_model





async def resolve_embedding_by_names(

    session: AsyncSession,

    *,

    workspace_id: uuid.UUID,

    provider_name: str,

    model_name: str,

):

    """Resolve embedding model by provider + model name within workspace."""



    return await resolve_embedding_model(

        session,

        workspace_id=workspace_id,

        provider_name=provider_name,

        model_name=model_name,

    )





async def embed_texts(

    session: AsyncSession,

    *,

    workspace_id: uuid.UUID,

    provider_name: str,

    model_name: str,

    texts: list[str],

    batch_size: int = 16,

) -> list[list[float]]:

    """Embed strings via configured endpoint with dataset_embedding cache."""



    return await embed_texts_with_cache(

        session,

        workspace_id=workspace_id,

        provider_name=provider_name,

        model_name=model_name,

        texts=texts,

        batch_size=batch_size,

    )

