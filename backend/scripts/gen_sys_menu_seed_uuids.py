"""Generate RFC UUID v5 values for sys_menu_seed.sql (stdout)."""

from __future__ import annotations

import uuid

NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://minerva.local/sys_menu")

ROWS: list[tuple] = [
    ("overview", None, "概览", "nav.overview", 1, "/app/overview", "C", "BarChartOutlined"),
    ("sub-agents", None, "智能体", "nav.agents", 2, None, "M", "RobotOutlined"),
    ("agents-chat", "sub-agents", "对话", "nav.agentsChat", 1, "/app/agents/chat", "C", "CommentOutlined"),
    ("agents-skills", "sub-agents", "技能", "nav.agentsSkills", 2, "/app/agents/skills", "C", "ThunderboltOutlined"),
    ("agents-memory", "sub-agents", "记忆", "nav.agentsMemory", 3, "/app/agents/memory", "C", "DatabaseOutlined"),
    ("agents-mcp", "sub-agents", "MCP", "nav.agentsMcp", 4, "/app/agents/mcp", "C", "ApiOutlined"),
    ("sub-doc-translate", None, "文档翻译", "nav.docTranslate", 3, None, "M", "TranslationOutlined"),
    ("doc-translate-translate", "sub-doc-translate", "翻译", "nav.docTranslateTranslate", 1, "/app/translate", "C", "FileTextOutlined"),
    ("sub-dataset", None, "知识库", "nav.knowledgeBase", 4, None, "M", "ReadOutlined"),
    ("dataset-list", "sub-dataset", "数据集", "nav.dataset", 1, "/app/dataset", "C", "UnorderedListOutlined"),
    ("sub-smart-review", None, "智能审核", "nav.smartReview", 5, None, "M", "FileSearchOutlined"),
    ("smart-review-text-proofreading", "sub-smart-review", "文本校对", "nav.smartReviewTextProofreading", 1, "/app/smart-review/text-proofreading", "C", "FileTextOutlined"),
    ("smart-review-text-to-text", "sub-smart-review", "以文审文", "nav.smartReviewTextToText", 2, "/app/smart-review/review-by-text", "C", "AuditOutlined"),
    ("smart-review-drawing-review", "sub-smart-review", "图纸审核", "nav.smartReviewDrawingReview", 3, "/app/smart-review/drawing-review", "C", "PictureOutlined"),
    ("sub-rules", None, "规则", "nav.rules", 6, None, "M", "BookOutlined"),
    ("rules-overview", "sub-rules", "概览", "nav.rulesOverview", 1, "/app/rules/overview", "C", "DashboardOutlined"),
    ("rules-mgmt-list", "sub-rules", "规则列表", "nav.rulesManagementList", 2, "/app/rules/management", "C", "UnorderedListOutlined"),
    ("sub-rules-config", "sub-rules", "配置", "nav.rulesConfig", 3, None, "M", "SlidersOutlined"),
    ("rules-config-config-prompts", "sub-rules-config", "提示词管理", "nav.rulesPromptManagement", 1, "/app/rules/config/config-prompts", "C", "ApiOutlined"),
    ("sub-file-ocr", None, "文件 OCR", "nav.rulesFileOcr", 7, None, "M", "ScanOutlined"),
    ("file-ocr-overview", "sub-file-ocr", "概览", "nav.rulesFileOcrOverview", 1, "/app/file-ocr/overview", "C", "DashboardOutlined"),
    ("file-ocr-tasks", "sub-file-ocr", "任务列表", "nav.rulesFileOcrTaskList", 2, "/app/file-ocr/tasks", "C", "UnorderedListOutlined"),
    ("sub-settings", None, "设置", "nav.settings", 8, None, "M", "SettingOutlined"),
    ("settings-models", "sub-settings", "模型供应商", "settings.models", 1, "/app/settings/models", "C", "ApiOutlined"),
    ("settings-ocr", "sub-settings", "OCR 工具", "settings.ocr", 2, "/app/settings/ocr", "C", "FileTextOutlined"),
    ("settings-file-storage", "sub-settings", "文件存储", "settings.fileStorage", 3, "/app/settings/file-storage", "C", "FolderOpenOutlined"),
    ("settings-celery", "sub-settings", "任务调度", "settings.celery", 4, "/app/settings/celery", "C", "ClockCircleOutlined"),
    ("settings-data-sources", "sub-settings", "数据源", "settings.dataSources", 5, "/app/settings/data-sources", "C", "DatabaseOutlined"),
    ("settings-menus", "sub-settings", "菜单配置", "settings.menuConfig", 6, "/app/settings/menus", "C", "MenuOutlined"),
    ("settings-users", "sub-settings", "用户管理", "settings.users", 7, "/app/settings/users", "C", "UserOutlined"),
    ("settings-roles", "sub-settings", "角色管理", "settings.roles", 8, "/app/settings/roles", "C", "IdcardOutlined"),
    ("settings-dictionary", "sub-settings", "数据字典", "settings.dictionary", 9, "/app/settings/dictionary", "C", "TagsOutlined"),
]


def render_seed_sql() -> str:
    """Build seed SQL with RFC UUID v5 per menu_key."""

    ids = {mk: str(uuid.uuid5(NS, mk)) for mk, *_ in ROWS}
    lines = [
        "-- 初始侧栏菜单（UUID v5，由 menu_key + 固定 namespace 确定性生成）",
        f"-- namespace: {NS}",
        "-- 若曾导入旧版顺序 UUID，请先: DELETE FROM public.sys_menu;",
        "INSERT INTO public.sys_menu (",
        "  id, parent_id, menu_name, i18n_key, menu_key, order_num, path, menu_type, icon, visible, status",
        ") VALUES",
    ]
    parts: list[str] = []
    for mk, parent, name, i18n, order_num, path, mtype, icon in ROWS:
        idv = ids[mk]
        pid = "NULL" if parent is None else f"'{ids[parent]}'"
        path_sql = "NULL" if path is None else f"'{path}'"
        parts.append(
            f"  ('{idv}', {pid}, '{name}', '{i18n}', '{mk}', {order_num}, {path_sql}, '{mtype}', '{icon}', true, true)"
        )
    lines.append(",\n".join(parts))
    lines.append("ON CONFLICT (id) DO NOTHING;")
    return "\n".join(lines) + "\n"


def main() -> None:
    from pathlib import Path

    out = Path(__file__).resolve().parents[1] / "sql" / "seeds" / "sys_menu_seed.sql"
    out.write_text(render_seed_sql(), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
