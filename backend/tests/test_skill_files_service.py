"""Tests for SkillFilesService."""

from __future__ import annotations

import pytest

from app.agent.service.skill_files_service import SkillFilesService
from app.exceptions import AppError


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
