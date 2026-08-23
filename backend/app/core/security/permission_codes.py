"""Platform permission codes and feature catalog constants."""

from __future__ import annotations

import fnmatch

TENANT_MEMBER_MANAGE = "tenant:member:manage"
TENANT_ROLE_MANAGE = "tenant:role:manage"
WORKSPACE_MANAGE = "workspace:manage"
PLATFORM_TENANT_MANAGE = "platform:tenant:manage"

FEATURE_AGENT = "feature:agent"
FEATURE_DATASET = "feature:dataset"
FEATURE_OCR = "feature:ocr"
FEATURE_SKILLS = "feature:skills"
FEATURE_TRANSLATE = "feature:translate"
FEATURE_RULES = "feature:rules"
FEATURE_FILE_STORAGE = "feature:file_storage"
FEATURE_GRAPH_KB = "feature:graph_kb"

FEATURE_CODES: frozenset[str] = frozenset(
    {
        FEATURE_AGENT,
        FEATURE_DATASET,
        FEATURE_OCR,
        FEATURE_SKILLS,
        FEATURE_TRANSLATE,
        FEATURE_RULES,
        FEATURE_FILE_STORAGE,
        FEATURE_GRAPH_KB,
    }
)

TENANT_ADMIN_IMPLICIT_PERMS: frozenset[str] = frozenset(
    {
        TENANT_MEMBER_MANAGE,
        TENANT_ROLE_MANAGE,
    }
)


def menu_key_to_feature(menu_key: str | None) -> str | None:
    if not menu_key:
        return None
    if menu_key == "agents-skills":
        return FEATURE_SKILLS
    if menu_key == "sub-agents" or fnmatch.fnmatch(menu_key, "agents-*"):
        return FEATURE_AGENT
    if menu_key == "sub-dataset" or fnmatch.fnmatch(menu_key, "dataset-*"):
        return FEATURE_DATASET
    if menu_key == "sub-file-ocr" or fnmatch.fnmatch(menu_key, "file-ocr-*"):
        return FEATURE_OCR
    if menu_key == "sub-doc-translate" or fnmatch.fnmatch(menu_key, "doc-translate-*"):
        return FEATURE_TRANSLATE
    if menu_key == "sub-rules" or fnmatch.fnmatch(menu_key, "rules-*"):
        return FEATURE_RULES
    if menu_key == "settings-file-storage":
        return FEATURE_FILE_STORAGE
    if menu_key == "sub-graph-kb" or fnmatch.fnmatch(menu_key, "graph-kb-*"):
        return FEATURE_GRAPH_KB
    return None


def derive_tenant_features_from_menu_keys(menu_keys: list[str]) -> frozenset[str]:
    out: set[str] = set()
    for key in menu_keys:
        code = menu_key_to_feature(key)
        if code:
            out.add(code)
    return frozenset(out)
