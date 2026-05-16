"""Tests for workspace-scoped agent file sandbox."""

from __future__ import annotations

import uuid

import pytest

from app.agent.infrastructure.agent_file_sandbox import AgentFileSandbox
from app.config import settings


@pytest.fixture
def sandbox_root(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> object:
    """Point agent files root at a temp directory."""

    root = tmp_path / "agent-files"
    monkeypatch.setattr(settings, "agent_files_root", str(root))
    return root


def test_resolve_rejects_parent_traversal(sandbox_root: object) -> None:
    """Paths with ``..`` are rejected."""

    ws = uuid.uuid4()
    box = AgentFileSandbox(workspace_id=ws)
    with pytest.raises(AgentFileSandbox.Error) as exc:
        box.resolve("../etc/passwd")
    assert exc.value.code == "path_invalid"


@pytest.mark.parametrize(
    "path",
    [
        "etc/passwd",
        "Windows/System32/drivers",
        "notes/proc/1/status",
        "Program Files/app/config.ini",
        "dev/null",
        "CON.txt",
    ],
)
def test_resolve_rejects_os_reserved_segments(sandbox_root: object, path: str) -> None:
    """Linux/Windows-like system path segments are forbidden inside the sandbox."""

    ws = uuid.uuid4()
    box = AgentFileSandbox(workspace_id=ws)
    with pytest.raises(AgentFileSandbox.Error) as exc:
        box.resolve(path)
    assert exc.value.code == "os_path_forbidden"


def test_resolve_allows_non_os_paths(sandbox_root: object) -> None:
    """Normal project paths under custom directories remain allowed."""

    ws = uuid.uuid4()
    box = AgentFileSandbox(workspace_id=ws)
    target = box.resolve("notes/readme.md")
    assert target.name == "readme.md"


def test_workspace_isolation(sandbox_root: object) -> None:
    """Two workspaces cannot read each other's files."""

    ws_a = uuid.uuid4()
    ws_b = uuid.uuid4()
    box_a = AgentFileSandbox(workspace_id=ws_a)
    box_b = AgentFileSandbox(workspace_id=ws_b)
    box_a.write_file("secret.txt", "alpha")
    with pytest.raises(AgentFileSandbox.Error) as exc:
        box_b.read_file("secret.txt")
    assert exc.value.code == "not_found"


@pytest.mark.asyncio
async def test_write_read_roundtrip(sandbox_root: object) -> None:
    """write_file then read_file returns same UTF-8 text."""

    ws = uuid.uuid4()
    box = AgentFileSandbox(workspace_id=ws)
    w = await box.write_file_async("notes/a.txt", "hello 文件")
    assert w["ok"] is True
    r = await box.read_file_async("notes/a.txt")
    assert r["ok"] is True
    assert r["content"] == "hello 文件"


def test_list_dir_lists_children(sandbox_root: object) -> None:
    """list_dir returns files and directories under the target path."""

    ws = uuid.uuid4()
    box = AgentFileSandbox(workspace_id=ws)
    box.mkdir("notes")
    box.write_file("notes/a.txt", "x")
    out = box.list_dir("notes")
    assert out["ok"] is True
    names = {e["name"] for e in out["entries"]}  # type: ignore[index]
    assert names == {"a.txt"}


def test_delete_non_empty_dir_requires_recursive(sandbox_root: object) -> None:
    """Non-empty directories need recursive delete."""

    ws = uuid.uuid4()
    box = AgentFileSandbox(workspace_id=ws)
    box.write_file("d/f.txt", "x")
    with pytest.raises(AgentFileSandbox.Error) as exc:
        box.delete_path("d", recursive=False)
    assert exc.value.code == "directory_not_empty"
    box.delete_path("d", recursive=True)
    assert not box.resolve("d").exists()


def test_too_large_read(sandbox_root: object, monkeypatch: pytest.MonkeyPatch) -> None:
    """Files larger than configured max cannot be read."""

    monkeypatch.setattr(settings, "agent_file_max_bytes", 4)
    ws = uuid.uuid4()
    box = AgentFileSandbox(workspace_id=ws)
    target = box.resolve("big.txt")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"12345")
    with pytest.raises(AgentFileSandbox.Error) as exc:
        box.read_file("big.txt")
    assert exc.value.code == "too_large"
