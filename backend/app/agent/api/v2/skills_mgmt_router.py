"""Skills filesystem management routes (tenant owner/admin only)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from fastapi.responses import FileResponse

from app.agent.api.v2.schemas import (
    SkillFileContentOut,
    SkillFileTreeNodeOut,
    SkillFileWriteIn,
    SkillRegistryItemOut,
    SkillRegistryOut,
    SkillWriteResultOut,
)
from app.agent.infrastructure.skill_loader import invalidate_skill_cache
from app.agent.service.skill_files_service import SkillFilesService
from app.core.api.deps import require_tenant_owner_or_admin
from app.exceptions import AppError

router = APIRouter(prefix="/skills-mgmt", tags=["agent-skills-mgmt"])


def _tree_node_from_dict(data: dict[str, Any]) -> SkillFileTreeNodeOut:
    """Map one service tree dict to the API response model."""

    children_raw = data.get("children")
    children = (
        [_tree_node_from_dict(child) for child in children_raw]
        if isinstance(children_raw, list)
        else []
    )
    return SkillFileTreeNodeOut(
        name=str(data["name"]),
        path=str(data["path"]),
        is_dir=bool(data["is_dir"]),
        size=data.get("size") if data.get("size") is None else int(data["size"]),
        children=children,
    )


def _invalidate_after_binary_write(rel: str) -> None:
    """Mirror ``SkillFilesService`` cache rules after a non-text upload."""

    parts = rel.split("/")
    if not parts:
        return
    if parts[0] == "INDEX.json" or rel == "INDEX.json":
        invalidate_skill_cache(None)
        return
    if len(parts) == 1:
        invalidate_skill_cache(parts[0])
        return
    if parts[1] == "tools.py":
        invalidate_skill_cache(parts[0])
        return
    invalidate_skill_cache(None)


@router.get("/registry", response_model=SkillRegistryOut)
async def get_skill_registry(
    workspace_id: uuid.UUID,
    _workspace: uuid.UUID = Depends(require_tenant_owner_or_admin),
) -> SkillRegistryOut:
    """List indexed skills with descriptions and on-disk file counts."""

    svc = SkillFilesService()
    rows = svc.list_registry()
    return SkillRegistryOut(
        skills=[
            SkillRegistryItemOut(
                id=str(row["id"]),
                description=str(row["description"]),
                file_count=int(row["file_count"]),
            )
            for row in rows
        ]
    )


@router.get("/{skill_id}/tree", response_model=list[SkillFileTreeNodeOut])
async def get_skill_file_tree(
    workspace_id: uuid.UUID,
    skill_id: str,
    _workspace: uuid.UUID = Depends(require_tenant_owner_or_admin),
) -> list[SkillFileTreeNodeOut]:
    """Return the recursive file tree for one skill directory."""

    svc = SkillFilesService()
    nodes = svc.build_tree(skill_id)
    return [_tree_node_from_dict(node) for node in nodes]


@router.get("/files", response_model=SkillFileContentOut)
async def read_skill_file(
    workspace_id: uuid.UUID,
    path: str = Query(..., min_length=1),
    _workspace: uuid.UUID = Depends(require_tenant_owner_or_admin),
) -> SkillFileContentOut:
    """Read one UTF-8 text file under the global skills root."""

    svc = SkillFilesService()
    content = svc.read_text(path)
    rel = svc.resolve_relative(path).relative_to(svc.root).as_posix()
    return SkillFileContentOut(path=rel, content=content)


@router.put("/files", response_model=SkillWriteResultOut)
async def write_skill_file(
    workspace_id: uuid.UUID,
    body: SkillFileWriteIn,
    path: str = Query(..., min_length=1),
    _workspace: uuid.UUID = Depends(require_tenant_owner_or_admin),
) -> SkillWriteResultOut:
    """Save ``.md`` / ``.py`` / ``.json`` and invalidate skill caches."""

    svc = SkillFilesService()
    svc.write_text(path, body.content)
    rel = svc.resolve_relative(path).relative_to(svc.root).as_posix()
    return SkillWriteResultOut(path=rel, cache_reloaded=True)


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_skill_package(
    workspace_id: uuid.UUID,
    file: UploadFile = File(...),
    _workspace: uuid.UUID = Depends(require_tenant_owner_or_admin),
) -> dict[str, str]:
    """Install one zip skill package whose archive root is a single directory."""

    svc = SkillFilesService()
    data = await file.read()
    result = svc.upload_skill_zip(data)
    return result


@router.post("/files/upload", response_model=SkillWriteResultOut, status_code=status.HTTP_201_CREATED)
async def upload_skill_file(
    workspace_id: uuid.UUID,
    path: str = Query(..., min_length=1, description="Target directory relative to skills root."),
    file: UploadFile = File(...),
    _workspace: uuid.UUID = Depends(require_tenant_owner_or_admin),
) -> SkillWriteResultOut:
    """Upload one file into an existing skill directory."""

    svc = SkillFilesService()
    dir_path = svc.resolve_relative(path)
    if not dir_path.is_dir():
        raise AppError("skills.not_found", "Directory not found", 404)

    raw_name = (file.filename or "upload").replace("\\", "/").strip("/")
    filename = raw_name.rsplit("/", 1)[-1] if raw_name else "upload"
    if not filename or filename in {".", ".."}:
        raise AppError("skills.path_invalid", "Invalid filename", 400)

    target = (dir_path / filename).resolve()
    if not str(target).startswith(str(svc.root)):
        raise AppError("skills.path_invalid", "Path escapes skills root", 400)

    data = await file.read()
    rel = target.relative_to(svc.root).as_posix()
    suffix = target.suffix.lower()
    if suffix in {".md", ".py", ".json"}:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as e:
            raise AppError("skills.path_invalid", "Text file must be UTF-8", 400) from e
        svc.write_text(rel, text)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        _invalidate_after_binary_write(rel)

    return SkillWriteResultOut(path=rel, cache_reloaded=True)


@router.get("/files/download")
async def download_skill_file(
    workspace_id: uuid.UUID,
    path: str = Query(..., min_length=1),
    _workspace: uuid.UUID = Depends(require_tenant_owner_or_admin),
) -> FileResponse:
    """Download one file from the global skills root."""

    svc = SkillFilesService()
    file_path = svc.resolve_relative(path)
    if not file_path.is_file():
        raise AppError("skills.not_found", "File not found", 404)
    return FileResponse(path=file_path, filename=file_path.name)


@router.delete("/files", status_code=204)
async def delete_skill_path(
    workspace_id: uuid.UUID,
    path: str = Query(..., min_length=1),
    _workspace: uuid.UUID = Depends(require_tenant_owner_or_admin),
) -> Response:
    """Delete one file or directory under the skills root."""

    svc = SkillFilesService()
    svc.delete_path(path)
    return Response(status_code=204)


@router.delete("/{skill_id}", status_code=204)
async def delete_skill_package(
    workspace_id: uuid.UUID,
    skill_id: str,
    _workspace: uuid.UUID = Depends(require_tenant_owner_or_admin),
) -> Response:
    """Delete an entire skill package directory."""

    svc = SkillFilesService()
    svc.delete_skill(skill_id)
    return Response(status_code=204)
