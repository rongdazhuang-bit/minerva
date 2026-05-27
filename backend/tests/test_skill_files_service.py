"""Tests for SkillFilesService."""

from __future__ import annotations

import io
import zipfile

import pytest

from app.agent.service.skill_files_service import SkillFilesService
from app.exceptions import AppError


def _make_zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


@pytest.fixture
def svc(tmp_path):
    root = tmp_path / "skills"
    root.mkdir()
    (root / "INDEX.md").write_text("# Index", encoding="utf-8")
    skill = root / "demo"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# Demo", encoding="utf-8")
    return SkillFilesService(root=root)


def test_reject_path_traversal(svc: SkillFilesService):
    with pytest.raises(AppError) as exc:
        svc.read_text("../outside.txt")
    assert exc.value.code == "skills.path_invalid"


def test_read_write_skill_md(svc: SkillFilesService):
    content = svc.read_text("demo/SKILL.md")
    assert content == "# Demo"
    svc.write_text("demo/SKILL.md", "# Updated")
    assert svc.read_text("demo/SKILL.md") == "# Updated"


def test_reject_non_editable_extension(svc: SkillFilesService):
    (svc.root / "demo" / "data.bin").write_bytes(b"\x00")
    with pytest.raises(AppError) as exc:
        svc.write_text("demo/data.bin", "nope")
    assert exc.value.code == "skills.not_editable"


def test_validate_skill_id_reserved():
    with pytest.raises(AppError):
        SkillFilesService.validate_skill_id("registry")


def test_upload_zip_single_root_folder(svc: SkillFilesService):
    z = _make_zip(
        {
            "newskill/SKILL.md": b"# New",
            "newskill/tools.py": b"# tools",
        }
    )
    result = svc.upload_skill_zip(z)
    assert result == {"skill_id": "newskill"}
    assert (svc.root / "newskill" / "SKILL.md").is_file()
    assert (svc.root / "newskill" / "tools.py").is_file()


def test_upload_zip_rejects_multiple_roots(svc: SkillFilesService):
    z = _make_zip({"a/SKILL.md": b"#", "b/SKILL.md": b"#"})
    with pytest.raises(AppError) as exc:
        svc.upload_skill_zip(z)
    assert exc.value.code == "skills.zip_invalid"


def test_upload_zip_rejects_duplicate(svc: SkillFilesService):
    z = _make_zip({"demo/SKILL.md": b"#"})
    with pytest.raises(AppError) as exc:
        svc.upload_skill_zip(z)
    assert exc.value.code == "skills.duplicate"


def test_build_tree(svc: SkillFilesService):
    (svc.root / "demo" / "tools.py").write_text("# tools", encoding="utf-8")
    tree = svc.build_tree("demo")
    names = {node["name"] for node in tree}
    assert names == {"SKILL.md", "tools.py"}
    skill_md = next(node for node in tree if node["name"] == "SKILL.md")
    assert skill_md["path"] == "demo/SKILL.md"
    assert skill_md["is_dir"] is False
    assert skill_md["children"] == []


def test_list_registry(svc: SkillFilesService):
    (svc.root / "demo" / "tools.py").write_text("# tools", encoding="utf-8")
    registry = svc.list_registry()
    assert len(registry) == 1
    assert registry[0]["id"] == "demo"
    assert registry[0]["file_count"] == 2


def test_delete_path_file(svc: SkillFilesService):
    (svc.root / "demo" / "extra.md").write_text("# extra", encoding="utf-8")
    svc.delete_path("demo/extra.md")
    assert not (svc.root / "demo" / "extra.md").exists()


def test_delete_skill(svc: SkillFilesService):
    svc.delete_skill("demo")
    assert not (svc.root / "demo").exists()
