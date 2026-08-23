"""HTTP routes for workspace graph knowledge bases."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api.deps import get_current_user
from app.core.domain.identity.models import User
from app.dependencies import get_db
from app.graph_kb.api.deps import require_graph_kb_workspace
from app.graph_kb.api.schemas import (
    GraphKbCreateIn,
    GraphKbDocumentDeleteOut,
    GraphKbDocumentListPageOut,
    GraphKbDocumentOut,
    GraphKbEntityListPageOut,
    GraphKbEntityOut,
    GraphKbGraphViewOut,
    GraphKbJobOut,
    GraphKbListPageOut,
    GraphKbOut,
    GraphKbPatchIn,
    GraphKbPlainTextIn,
    GraphKbQueryHistoryOut,
    GraphKbQueryHistoryPageOut,
    GraphKbQueryIn,
    GraphKbQueryOut,
    GraphKbRelationListPageOut,
    GraphKbRelationOut,
    GraphKbSummaryListPageOut,
    GraphKbSummaryOut,
)
from app.graph_kb.domain.db.models import GraphKb
from app.graph_kb.infrastructure import repository as repo
from app.graph_kb.service import deletion_service
from app.graph_kb.service import document_service as doc_svc
from app.graph_kb.service import graph_service as graph_svc
from app.graph_kb.service import index_service as index_svc
from app.graph_kb.service import query_service as query_svc
from app.graph_kb.service import view_service as view_svc
from app.graph_kb.service.actor import actor_from_user
from app.pagination import DEFAULT_PAGE_SIZE

router = APIRouter(prefix="/workspaces/{workspace_id}/graph-kbs", tags=["graph-kbs"])


async def _graph_out(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    row: GraphKb,
) -> GraphKbOut:
    """Build ``GraphKbOut`` including current member user ids."""

    member_ids = await repo.list_member_user_ids(
        session, workspace_id=workspace_id, graph_id=row.id
    )
    payload = GraphKbOut.model_validate(row)
    return payload.model_copy(update={"member_user_ids": sorted(member_ids, key=str)})


@router.get("", response_model=GraphKbListPageOut)
async def list_graph_kbs(
    workspace_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    name: str | None = Query(default=None, description="图谱名称关键词"),
    mine_only: bool = Query(default=False, description="仅返回当前用户创建的图谱"),
    user: User = Depends(get_current_user),
    _member: uuid.UUID = Depends(require_graph_kb_workspace),
    session: AsyncSession = Depends(get_db),
) -> GraphKbListPageOut:
    """List graphs visible to the caller with optional name / mine filters."""

    actor = await actor_from_user(session, user=user, workspace_id=workspace_id)
    rows, total = await graph_svc.list_graphs_for_actor(
        session,
        workspace_id=workspace_id,
        actor=actor,
        page=page,
        page_size=page_size,
        name=name,
        mine_only=mine_only,
    )
    items = [GraphKbOut.model_validate(row) for row in rows]
    return GraphKbListPageOut(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=GraphKbOut, status_code=201)
async def create_graph_kb(
    workspace_id: uuid.UUID,
    body: GraphKbCreateIn,
    user: User = Depends(get_current_user),
    _member: uuid.UUID = Depends(require_graph_kb_workspace),
    session: AsyncSession = Depends(get_db),
) -> GraphKbOut:
    """Create an empty graph; empty ``member_user_ids`` is allowed for partial_members."""

    row = await graph_svc.create_graph(
        session,
        workspace_id=workspace_id,
        user_id=user.id,
        name=body.name,
        engine=body.engine,
        permission=body.permission,
        llm_model=body.llm_model,
        llm_model_provider=body.llm_model_provider,
        embedding_model=body.embedding_model,
        embedding_model_provider=body.embedding_model_provider,
        description=body.description,
    )
    if body.member_user_ids:
        await graph_svc.replace_members(
            session,
            graph_id=row.id,
            workspace_id=workspace_id,
            user_ids=body.member_user_ids,
            created_by=user.id,
        )
    await session.commit()
    await session.refresh(row)
    return await _graph_out(session, workspace_id=workspace_id, row=row)


@router.get("/{graph_id}", response_model=GraphKbOut)
async def get_graph_kb(
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    user: User = Depends(get_current_user),
    _member: uuid.UUID = Depends(require_graph_kb_workspace),
    session: AsyncSession = Depends(get_db),
) -> GraphKbOut:
    """Return one graph the caller may view."""

    actor = await actor_from_user(session, user=user, workspace_id=workspace_id)
    row = await graph_svc.get_graph_for_view(
        session, workspace_id=workspace_id, graph_id=graph_id, actor=actor
    )
    return await _graph_out(session, workspace_id=workspace_id, row=row)


@router.patch("/{graph_id}", response_model=GraphKbOut)
async def patch_graph_kb(
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    body: GraphKbPatchIn,
    user: User = Depends(get_current_user),
    _member: uuid.UUID = Depends(require_graph_kb_workspace),
    session: AsyncSession = Depends(get_db),
) -> GraphKbOut:
    """Update mutable settings and optionally replace partial members."""

    actor = await actor_from_user(session, user=user, workspace_id=workspace_id)
    patch = body.model_dump(exclude_unset=True)
    member_ids = patch.pop("member_user_ids", None)
    row = await graph_svc.patch_graph(
        session,
        workspace_id=workspace_id,
        graph_id=graph_id,
        actor=actor,
        patch=patch,
    )
    if member_ids is not None:
        await graph_svc.replace_members(
            session,
            graph_id=row.id,
            workspace_id=workspace_id,
            user_ids=member_ids,
            created_by=user.id,
        )
    await session.commit()
    await session.refresh(row)
    return await _graph_out(session, workspace_id=workspace_id, row=row)


@router.delete("/{graph_id}", status_code=204)
async def delete_graph_kb(
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    user: User = Depends(get_current_user),
    _member: uuid.UUID = Depends(require_graph_kb_workspace),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Delete graph SQL rows synchronously; enqueue async Worker/object cleanup."""

    actor = await actor_from_user(session, user=user, workspace_id=workspace_id)
    graph = await graph_svc.get_graph_for_manage(
        session, workspace_id=workspace_id, graph_id=graph_id, actor=actor
    )
    engine = graph.engine
    await deletion_service.delete_graph_sql(
        session, workspace_id=workspace_id, graph_id=graph_id
    )
    await session.commit()
    await deletion_service.enqueue_cleanup(
        workspace_id=workspace_id, graph_id=graph_id, engine=engine
    )


@router.post("/{graph_id}/documents/upload", response_model=GraphKbDocumentOut, status_code=201)
async def upload_graph_document(
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    _member: uuid.UUID = Depends(require_graph_kb_workspace),
    session: AsyncSession = Depends(get_db),
) -> GraphKbDocumentOut:
    """Upload one source file into the graph document list."""

    actor = await actor_from_user(session, user=user, workspace_id=workspace_id)
    row = await doc_svc.add_upload_file(
        session,
        workspace_id=workspace_id,
        graph_id=graph_id,
        actor=actor,
        file=file,
    )
    await session.commit()
    await session.refresh(row)
    return GraphKbDocumentOut.model_validate(row)


@router.post("/{graph_id}/documents/text", response_model=GraphKbDocumentOut, status_code=201)
async def import_graph_plain_text(
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    body: GraphKbPlainTextIn,
    user: User = Depends(get_current_user),
    _member: uuid.UUID = Depends(require_graph_kb_workspace),
    session: AsyncSession = Depends(get_db),
) -> GraphKbDocumentOut:
    """Import a plain-text body as a graph document."""

    actor = await actor_from_user(session, user=user, workspace_id=workspace_id)
    row = await doc_svc.add_plain_text(
        session,
        workspace_id=workspace_id,
        graph_id=graph_id,
        actor=actor,
        name=body.name,
        text=body.text,
    )
    await session.commit()
    await session.refresh(row)
    return GraphKbDocumentOut.model_validate(row)


@router.get("/{graph_id}/documents", response_model=GraphKbDocumentListPageOut)
async def list_graph_documents(
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    user: User = Depends(get_current_user),
    _member: uuid.UUID = Depends(require_graph_kb_workspace),
    session: AsyncSession = Depends(get_db),
) -> GraphKbDocumentListPageOut:
    """List documents for a graph the caller may view."""

    actor = await actor_from_user(session, user=user, workspace_id=workspace_id)
    rows, total = await doc_svc.list_documents(
        session,
        workspace_id=workspace_id,
        graph_id=graph_id,
        actor=actor,
        page=page,
        page_size=page_size,
    )
    return GraphKbDocumentListPageOut(
        items=[GraphKbDocumentOut.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.delete("/{graph_id}/documents/{doc_id}", response_model=GraphKbDocumentDeleteOut)
async def delete_graph_document(
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    doc_id: uuid.UUID,
    user: User = Depends(get_current_user),
    _member: uuid.UUID = Depends(require_graph_kb_workspace),
    session: AsyncSession = Depends(get_db),
) -> GraphKbDocumentDeleteOut:
    """Delete one document; attempt reindex enqueue when the graph was indexed before."""

    actor = await actor_from_user(session, user=user, workspace_id=workspace_id)
    result = await doc_svc.delete_document(
        session,
        workspace_id=workspace_id,
        graph_id=graph_id,
        document_id=doc_id,
        actor=actor,
    )
    await session.commit()
    return GraphKbDocumentDeleteOut.model_validate(result)


@router.post("/{graph_id}/index", response_model=GraphKbJobOut, status_code=201)
async def enqueue_graph_index(
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    user: User = Depends(get_current_user),
    _member: uuid.UUID = Depends(require_graph_kb_workspace),
    session: AsyncSession = Depends(get_db),
) -> GraphKbJobOut:
    """Enqueue index/reindex; 409 when another index job is already active."""

    actor = await actor_from_user(session, user=user, workspace_id=workspace_id)
    await graph_svc.get_graph_for_manage(
        session, workspace_id=workspace_id, graph_id=graph_id, actor=actor
    )
    job = await index_svc.enqueue_index(
        session,
        workspace_id=workspace_id,
        graph_id=graph_id,
        user_id=user.id,
    )
    return GraphKbJobOut.model_validate(job)


@router.get("/{graph_id}/jobs/{job_id}", response_model=GraphKbJobOut)
async def get_graph_job(
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    job_id: uuid.UUID,
    user: User = Depends(get_current_user),
    _member: uuid.UUID = Depends(require_graph_kb_workspace),
    session: AsyncSession = Depends(get_db),
) -> GraphKbJobOut:
    """Return one job status for a graph the caller may view."""

    actor = await actor_from_user(session, user=user, workspace_id=workspace_id)
    await graph_svc.get_graph_for_view(
        session, workspace_id=workspace_id, graph_id=graph_id, actor=actor
    )
    job = await index_svc.get_job(
        session, workspace_id=workspace_id, graph_id=graph_id, job_id=job_id
    )
    return GraphKbJobOut.model_validate(job)


@router.post("/{graph_id}/query", response_model=GraphKbQueryOut)
async def query_graph_kb(
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    body: GraphKbQueryIn,
    user: User = Depends(get_current_user),
    _member: uuid.UUID = Depends(require_graph_kb_workspace),
    session: AsyncSession = Depends(get_db),
) -> GraphKbQueryOut:
    """Run a Worker query; Worker 503/502 propagate (not remapped to 200)."""

    actor = await actor_from_user(session, user=user, workspace_id=workspace_id)
    result = await query_svc.query_graph(
        session,
        workspace_id=workspace_id,
        graph_id=graph_id,
        actor=actor,
        query=body.query,
        mode=body.mode,
        top_k=body.top_k,
    )
    await session.commit()
    return GraphKbQueryOut(answer=result.answer, citations=list(result.citations))


@router.get("/{graph_id}/queries", response_model=GraphKbQueryHistoryPageOut)
async def list_graph_queries(
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    user: User = Depends(get_current_user),
    _member: uuid.UUID = Depends(require_graph_kb_workspace),
    session: AsyncSession = Depends(get_db),
) -> GraphKbQueryHistoryPageOut:
    """List persisted Q&A history for a viewable graph."""

    actor = await actor_from_user(session, user=user, workspace_id=workspace_id)
    rows, total = await query_svc.list_queries(
        session,
        workspace_id=workspace_id,
        graph_id=graph_id,
        actor=actor,
        page=page,
        page_size=page_size,
    )
    return GraphKbQueryHistoryPageOut(
        items=[GraphKbQueryHistoryOut.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{graph_id}/entities", response_model=GraphKbEntityListPageOut)
async def list_graph_entities(
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    name: str | None = Query(default=None, description="实体名称关键词"),
    entity_type: str | None = Query(default=None, description="实体类型"),
    user: User = Depends(get_current_user),
    _member: uuid.UUID = Depends(require_graph_kb_workspace),
    session: AsyncSession = Depends(get_db),
) -> GraphKbEntityListPageOut:
    """Paginate entity projections (default page size 10)."""

    actor = await actor_from_user(session, user=user, workspace_id=workspace_id)
    rows, total = await query_svc.list_entities(
        session,
        workspace_id=workspace_id,
        graph_id=graph_id,
        actor=actor,
        page=page,
        page_size=page_size,
        name=name,
        entity_type=entity_type,
    )
    return GraphKbEntityListPageOut(
        items=[GraphKbEntityOut.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{graph_id}/relations", response_model=GraphKbRelationListPageOut)
async def list_graph_relations(
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    user: User = Depends(get_current_user),
    _member: uuid.UUID = Depends(require_graph_kb_workspace),
    session: AsyncSession = Depends(get_db),
) -> GraphKbRelationListPageOut:
    """Paginate relation projections (default page size 10)."""

    actor = await actor_from_user(session, user=user, workspace_id=workspace_id)
    rows, total = await query_svc.list_relations(
        session,
        workspace_id=workspace_id,
        graph_id=graph_id,
        actor=actor,
        page=page,
        page_size=page_size,
    )
    return GraphKbRelationListPageOut(
        items=[GraphKbRelationOut.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{graph_id}/summaries", response_model=GraphKbSummaryListPageOut)
async def list_graph_summaries(
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    user: User = Depends(get_current_user),
    _member: uuid.UUID = Depends(require_graph_kb_workspace),
    session: AsyncSession = Depends(get_db),
) -> GraphKbSummaryListPageOut:
    """Paginate community / topic summary projections."""

    actor = await actor_from_user(session, user=user, workspace_id=workspace_id)
    rows, total = await query_svc.list_summaries(
        session,
        workspace_id=workspace_id,
        graph_id=graph_id,
        actor=actor,
        page=page,
        page_size=page_size,
    )
    return GraphKbSummaryListPageOut(
        items=[GraphKbSummaryOut.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{graph_id}/graph-view", response_model=GraphKbGraphViewOut)
async def get_graph_view(
    workspace_id: uuid.UUID,
    graph_id: uuid.UUID,
    seed_entity_id: str | None = Query(default=None),
    hops: int = Query(default=1, ge=1, le=2),
    community_id: uuid.UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
    _member: uuid.UUID = Depends(require_graph_kb_workspace),
    session: AsyncSession = Depends(get_db),
) -> GraphKbGraphViewOut:
    """Return a BFS subgraph (max 200 nodes) for canvas rendering."""

    actor = await actor_from_user(session, user=user, workspace_id=workspace_id)
    payload = await view_svc.graph_view(
        session,
        workspace_id=workspace_id,
        graph_id=graph_id,
        actor=actor,
        seed_entity_id=seed_entity_id,
        hops=hops,
        community_id=community_id,
    )
    return GraphKbGraphViewOut(nodes=payload["nodes"], edges=payload["edges"])
