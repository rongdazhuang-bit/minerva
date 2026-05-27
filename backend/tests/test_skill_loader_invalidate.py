"""Tests for skill_loader cache invalidation."""

from __future__ import annotations

import sys

import pytest

from app.agent.infrastructure import skill_loader


def test_invalidate_skill_cache_clears_index(monkeypatch, tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "INDEX.md").write_text(
        "# Index\n\n## 子技能列表\n\n- `alpha`：Alpha skill\n",
        encoding="utf-8",
    )
    (skills_dir / "alpha").mkdir()
    (skills_dir / "alpha" / "SKILL.md").write_text("# Alpha", encoding="utf-8")

    monkeypatch.setattr(skill_loader, "_SKILLS_ROOT", skills_dir)
    skill_loader.list_indexed_skills.cache_clear()

    assert [s.id for s in skill_loader.list_indexed_skills()] == ["alpha"]

    (skills_dir / "INDEX.md").write_text(
        "# Index\n\n## 子技能列表\n\n- `beta`：Beta skill\n",
        encoding="utf-8",
    )
    assert [s.id for s in skill_loader.list_indexed_skills()] == ["alpha"]

    skill_loader.invalidate_skill_cache()
    assert [s.id for s in skill_loader.list_indexed_skills()] == ["beta"]


def test_invalidate_skill_cache_evicts_tools_module(monkeypatch, tmp_path):
    mod_name = "app.agent.skills.fake_skill.tools"
    fake_mod = type(sys)("fake")
    sys.modules[mod_name] = fake_mod
    skill_loader.invalidate_skill_cache("fake_skill")
    assert mod_name not in sys.modules
