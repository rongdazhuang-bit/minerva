import uuid

import pytest

from app.exceptions import AppError
from app.sys.file_storage.domain.db.models import SysStorage
from app.sys.file_storage.service.path_validation import (
    normalize_local_path_segment,
    resolve_effective_local_root,
)


def test_sys_storage_has_local_path_column() -> None:
    cols = {c.key for c in SysStorage.__table__.columns}
    assert "local_path" in cols


def test_normalize_local_path_rejects_traversal() -> None:
    with pytest.raises(AppError) as exc:
        normalize_local_path_segment("../etc")
    assert exc.value.code == "file_storage.local_path_invalid"


def test_normalize_local_path_allows_backup() -> None:
    assert normalize_local_path_segment("backup") == "backup"
    assert normalize_local_path_segment("  ") is None


def test_resolve_effective_local_root(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FILE_STORAGE_LOCAL_ROOT", str(tmp_path))
    from importlib import reload
    import app.config as config_mod
    reload(config_mod)
    ws = uuid.uuid4()
    root = resolve_effective_local_root(workspace_id=ws, local_path="backup")
    assert root == (tmp_path / str(ws) / "backup").resolve()
