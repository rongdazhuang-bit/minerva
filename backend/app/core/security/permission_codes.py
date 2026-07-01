"""Platform permission codes and feature catalog constants."""

from __future__ import annotations

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

FEATURE_CODES: frozenset[str] = frozenset(
    {
        FEATURE_AGENT,
        FEATURE_DATASET,
        FEATURE_OCR,
        FEATURE_SKILLS,
        FEATURE_TRANSLATE,
        FEATURE_RULES,
        FEATURE_FILE_STORAGE,
    }
)

TENANT_ADMIN_IMPLICIT_PERMS: frozenset[str] = frozenset(
    {
        TENANT_MEMBER_MANAGE,
        TENANT_ROLE_MANAGE,
    }
)
