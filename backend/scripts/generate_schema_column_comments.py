#!/usr/bin/env python3
"""Generate PostgreSQL COMMENT ON statements for schema columns."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "sql"
SCHEMA = SQL_DIR / "schema_postgresql.sql"
PATCH_OUT = SQL_DIR / "patches" / "2026-07-01-schema-column-comments.sql"

TABLE_DEFAULTS: dict[str, str] = {
    "sys_tenant": "租户",
    "sys_user": "平台用户",
    "sys_permission": "平台权限目录",
    "sys_role_permission": "角色与权限关联",
    "sys_tenant_permission": "租户菜单开通（超管授权）",
    "sys_user_grant": "用户授权 grant（RBAC+ABAC）",
    "refresh_tokens": "刷新令牌会话",
    "sys_tenant_user": "用户与租户成员关系",
    "sys_workspaces": "工作空间",
    "sys_workspace_user": "用户与工作空间成员关系",
    "sys_menu": "系统菜单（全局）",
    "sys_role": "租户作用域角色",
    "dataset": "知识库",
    "dataset_process_rule": "知识库分段规则",
    "dataset_upload_file": "知识库上传文件",
    "dataset_document": "知识库文档",
    "dataset_document_segment": "知识库文档分段",
    "dataset_child_chunk": "子块（父子分段）",
    "dataset_embedding": "分段向量嵌入",
    "dataset_keyword_table": "关键词倒排表",
    "dataset_query": "知识库检索查询记录",
    "dataset_collection_binding": "向量集合绑定",
    "agent_plan": "单次 run 的结构化计划",
    "agent_long_term_memory": "长期记忆（SQL 检索）",
    "agent_memory_profile": "Agent 持久人物画像",
    "checkpoints": "LangGraph checkpoint 主表",
    "checkpoint_blobs": "LangGraph checkpoint blob 分片",
    "checkpoint_writes": "LangGraph checkpoint 写入缓冲",
}

COLUMN_DEFAULTS: dict[str, str] = {
    "id": "主键",
    "workspace_id": "所属 workspace",
    "tenant_id": "所属 tenant",
    "user_id": "用户 id",
    "role_id": "角色 id",
    "menu_id": "菜单 id",
    "permission_id": "权限 id",
    "session_id": "会话 id",
    "run_id": "运行 id",
    "dataset_id": "知识库 id",
    "document_id": "文档 id",
    "segment_id": "分段 id",
    "message_id": "消息 id",
    "file_id": "文件 id",
    "dict_uuid": "所属字典 id",
    "parent_id": "父节点 id",
    "parent_uuid": "父字典项 id",
    "parent_node_id": "父节点 id",
    "department_item_id": "部门字典项 id",
    "granted_by_user_id": "授权人用户 id",
    "scope_id": "授权范围 id（tenant/workspace）",
    "collection_binding_id": "向量集合绑定 id",
    "dataset_process_rule_id": "分段规则 id",
    "object_key": "对象存储键",
    "storage_key": "存储键",
    "name": "名称",
    "slug": "标识",
    "email": "邮箱",
    "password_hash": "密码哈希",
    "nickname": "昵称",
    "phone": "手机号",
    "status": "状态",
    "remark": "备注",
    "role": "成员角色",
    "create_at": "创建时间",
    "update_at": "修改时间",
    "created_at": "创建时间",
    "updated_at": "更新时间",
    "create_at": "创建时间",
    "enabled": "是否启用",
    "visible": "是否可见",
    "description": "描述",
    "content": "内容",
    "size": "大小（字节）",
    "extension": "文件扩展名",
    "mime_type": "MIME 类型",
    "created_by": "创建人用户 id",
    "updated_by": "最后修改人用户 id",
    "position": "排序位置",
    "word_count": "字数",
    "tokens": "token 数",
    "keywords": "关键词",
    "hit_count": "命中次数",
    "error": "错误信息",
    "provider": "供应商标识",
    "permission": "可见性权限",
    "model_name": "模型名称",
    "provider_name": "供应商名称",
    "type": "类型",
    "hash": "哈希",
    "embedding": "向量嵌入",
    "keyword_table": "关键词表 JSON",
    "mode": "模式",
    "rules": "规则 JSON",
    "source": "来源",
    "source_app_id": "来源应用 id",
    "created_by_role": "创建者角色",
    "jti": "刷新令牌唯一 id",
    "expires_at": "过期时间",
    "revoked_at": "撤销时间",
    "is_super_admin": "是否平台超级管理员",
    "grant_type": "授权类型：role/direct_permission/tenant_admin",
    "scope_type": "授权范围类型：platform/tenant/workspace",
    "perm_code": "权限码（全局唯一）",
    "perm_name": "权限名称",
    "perm_type": "权限类型：menu/api/data/feature",
    "resource_pattern": "ABAC 资源匹配模式",
    "create_by": "创建人用户 id",
    "role_name": "角色名称",
    "role_key": "权限字符",
    "role_sort": "显示顺序",
    "menu_name": "菜单名称",
    "i18n_key": "i18n 键",
    "menu_key": "菜单稳定键",
    "order_num": "显示顺序",
    "path": "路由地址",
    "menu_type": "菜单类型 M/C/F",
    "perms": "权限标识",
    "icon": "图标名",
    "is_external": "是否外链",
    "kind": "种类",
    "key": "键",
    "tags": "标签 JSON",
    "source_run_id": "来源 run id",
    "profile_text": "画像文本",
    "updated_by": "最后更新人",
    "steps_json": "计划步骤 JSON",
    "thread_id": "LangGraph 线程 id",
    "checkpoint_ns": "checkpoint 命名空间",
    "checkpoint_id": "checkpoint id",
    "parent_checkpoint_id": "父 checkpoint id",
    "channel": "通道名",
    "version": "版本",
    "blob": "二进制载荷",
    "task_id": "任务 id",
    "task_path": "任务路径",
    "idx": "写入序号",
    "checkpoint": "checkpoint 快照",
    "metadata": "元数据 JSON",
    "ocr_type": "OCR 引擎类型",
    "ocr_config": "OCR 配置 JSON",
    "file_name": "文件名",
    "content_type": "Content-Type",
    "summary_text": "会话摘要文本",
}

EXPLICIT: dict[tuple[str, str], str] = {
    ("sys_tenant", "id"): "主键",
    ("sys_tenant", "name"): "租户名称",
    ("sys_tenant", "slug"): "租户标识（全局唯一）",
    ("sys_user", "id"): "主键",
    ("sys_role", "tenant_id"): "所属 tenant",
    ("sys_role", "workspace_id"): "所属 workspace；NULL 表示 tenant 内通用角色",
    ("sys_permission", "perm_code"): "权限码（全局唯一）",
    ("sys_permission", "perm_type"): "权限类型：menu/api/data/feature",
    ("sys_permission", "menu_id"): "逻辑引用 sys_menu.id（menu 型权限）",
    ("sys_user_grant", "role_id"): "逻辑引用 sys_role.id",
    ("sys_user_grant", "permission_id"): "逻辑引用 sys_permission.id",
    ("refresh_tokens", "user_id"): "用户 id",
    ("sys_tenant_user", "id"): "主键",
    ("sys_tenant_user", "role"): "租户成员角色 admin/member",
    ("sys_workspace_user", "id"): "主键",
    ("sys_workspace_user", "role"): "工作空间成员角色 admin/member",
    ("sys_workspaces", "id"): "主键",
    ("sys_workspaces", "name"): "工作空间名称",
    ("sys_workspaces", "slug"): "工作空间标识（租户内唯一）",
    ("sys_role", "id"): "主键",
    ("sys_role_permission", "id"): "主键",
    ("sys_tenant_permission", "id"): "主键",
    ("sys_tenant_permission", "menu_id"): "逻辑引用 sys_menu.id",
    ("sys_user_grant", "id"): "主键",
    ("dataset", "index_struct"): "索引结构 JSON",
    ("dataset", "embedding_model"): "嵌入模型名",
    ("dataset", "embedding_model_provider"): "嵌入模型供应商",
    ("dataset", "keyword_number"): "关键词数量上限",
    ("dataset", "retrieval_model"): "检索模型配置 JSON",
    ("dataset", "chunk_structure"): "分段结构",
    ("dataset", "data_source_type"): "数据源类型",
    ("dataset", "indexing_technique"): "索引技术",
    ("dataset_document", "indexing_status"): "索引状态",
    ("dataset_document", "batch"): "导入批次号",
    ("dataset_document", "created_from"): "创建来源",
    ("dataset_document", "doc_form"): "文档形式",
    ("dataset_document", "doc_type"): "文档类型",
    ("dataset_document", "doc_language"): "文档语言",
    ("dataset_document", "indexing_latency"): "索引耗时（秒）",
    ("dataset_document", "processing_started_at"): "处理开始时间",
    ("dataset_document", "parsing_completed_at"): "解析完成时间",
    ("dataset_document", "cleaning_completed_at"): "清洗完成时间",
    ("dataset_document", "splitting_completed_at"): "切分完成时间",
    ("dataset_document", "completed_at"): "处理完成时间",
    ("dataset_document", "stopped_at"): "停止时间",
    ("dataset_document", "archived"): "是否归档",
    ("dataset_document", "is_paused"): "是否暂停",
    ("dataset_document_segment", "answer"): "问答对答案",
    ("dataset_document_segment", "index_node_id"): "向量索引节点 id",
    ("dataset_document_segment", "index_node_hash"): "向量索引节点哈希",
    ("dataset_child_chunk", "type"): "子块类型",
    ("agent_message_attachment", "id"): "主键",
    ("agent_message_attachment", "workspace_id"): "工作空间 id",
    ("agent_message_attachment", "session_id"): "会话 id",
    ("agent_message_attachment", "message_id"): "消息 id",
    ("agent_message_attachment", "object_key"): "对象存储键",
    ("agent_message_attachment", "file_name"): "原始文件名",
    ("agent_message_attachment", "content_type"): "MIME 类型",
    ("agent_message_attachment", "size"): "文件大小（字节）",
    ("agent_message_attachment", "created_by"): "上传用户 id",
    ("agent_message_attachment", "created_at"): "创建时间",
    ("agent_plan", "id"): "主键",
    ("agent_plan", "run_id"): "所属 run",
    ("agent_plan", "steps_json"): "计划步骤 JSON",
    ("agent_plan", "status"): "计划状态",
    ("agent_plan", "created_at"): "创建时间",
    ("agent_long_term_memory", "id"): "主键",
    ("agent_long_term_memory", "workspace_id"): "工作空间 id",
    ("agent_long_term_memory", "session_id"): "会话 id（可空表示全局）",
    ("agent_long_term_memory", "kind"): "记忆种类",
    ("agent_long_term_memory", "key"): "记忆键",
    ("agent_long_term_memory", "content"): "记忆内容",
    ("agent_long_term_memory", "tags"): "标签 JSON",
    ("agent_long_term_memory", "source_run_id"): "写入来源 run",
    ("agent_long_term_memory", "created_at"): "创建时间",
    ("agent_long_term_memory", "expires_at"): "过期时间",
    ("agent_memory_profile", "id"): "主键",
    ("agent_memory_profile", "workspace_id"): "工作空间 id",
    ("agent_memory_profile", "session_id"): "会话 id（NULL 为工作区级）",
    ("agent_memory_profile", "profile_text"): "画像文本",
    ("agent_memory_profile", "updated_by"): "最后更新用户 id",
    ("agent_memory_profile", "updated_at"): "更新时间",
    ("agent_mcp_client", "id"): "主键",
    ("agent_mcp_client", "enabled"): "是否启用",
    ("agent_mcp_client", "remark"): "备注",
    ("agent_mcp_client", "last_test_at"): "最近连通测试时间",
    ("agent_mcp_client", "last_test_ok"): "最近连通测试是否成功",
    ("agent_mcp_server", "id"): "主键",
    ("agent_mcp_server", "auth_type"): "认证类型",
    ("agent_mcp_server", "auth_secret"): "认证密钥（加密存储）",
    ("agent_session", "summary_text"): "会话摘要",
}


def _load_existing_comments() -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    table_comments: dict[str, str] = {}
    column_comments: dict[tuple[str, str], str] = {}
    for path in SQL_DIR.rglob("*.sql"):
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(
            r"COMMENT ON TABLE (?:public\.)?(\w+) IS '((?:''|[^'])*)';", text
        ):
            table_comments[m.group(1)] = m.group(2).replace("''", "'")
        for m in re.finditer(
            r"COMMENT ON (?:COLUMN )?(?:public\.)?(\w+)\.(?:(\w+)|\"(\w+)\") IS '((?:''|[^'])*)';",
            text,
        ):
            col = m.group(2) or m.group(3)
            val = m.group(4).replace("''", "'")
            column_comments[(m.group(1), col)] = val
    return table_comments, column_comments


def _parse_tables(schema_text: str) -> dict[str, list[str]]:
    tables: dict[str, list[str]] = {}
    for m in re.finditer(
        r"CREATE TABLE IF NOT EXISTS (?:public\.)?(\w+)\s*\((.*?)\);",
        schema_text,
        re.S,
    ):
        name = m.group(1)
        body = m.group(2)
        cols: list[str] = []
        for line in body.split("\n"):
            line = line.strip().rstrip(",")
            if not line or line.startswith("CONSTRAINT") or line.startswith("PRIMARY"):
                continue
            qm = re.match(r'"(\w+)"\s+', line)
            if qm:
                cols.append(qm.group(1))
                continue
            cm = re.match(r"(\w+)\s+", line)
            if cm:
                cols.append(cm.group(1))
        tables[name] = cols
    return tables


def _infer_comment(table: str, column: str) -> str:
    key = (table, column)
    if key in EXPLICIT:
        return EXPLICIT[key]
    if column in COLUMN_DEFAULTS:
        return COLUMN_DEFAULTS[column]
    return f"{column} 字段"


def _quote_col(col: str) -> str:
    if col in {"name", "type"}:
        return f'"{col}"'
    return col


def _escape_sql_string(value: str) -> str:
    return value.replace("'", "''")


def _resolve_table_comment(table: str, table_comments: dict[str, str]) -> str:
    if table in TABLE_DEFAULTS:
        return TABLE_DEFAULTS[table]
    return table_comments.get(table, f"{table} 表")


def _resolve_column_comment(
    table: str, column: str, column_comments: dict[tuple[str, str], str]
) -> str:
    if (table, column) in EXPLICIT:
        return EXPLICIT[(table, column)]
    key = (table, column)
    if key in column_comments:
        return column_comments[key]
    return _infer_comment(table, column)


def _apply_schema_comment_overrides(schema_text: str) -> str:
    for (table, col), comment in EXPLICIT.items():
        qcol = _quote_col(col)
        pattern = (
            rf"COMMENT ON COLUMN public\.{table}\.{qcol} IS '((?:''|[^'])*)';"
        )
        replacement = (
            f"COMMENT ON COLUMN public.{table}.{qcol} IS "
            f"'{_escape_sql_string(comment)}';"
        )
        schema_text = re.sub(pattern, replacement, schema_text)
    for table, comment in TABLE_DEFAULTS.items():
        pattern = rf"COMMENT ON TABLE public\.{table} IS '((?:''|[^'])*)';"
        replacement = (
            f"COMMENT ON TABLE public.{table} IS '{_escape_sql_string(comment)}';"
        )
        if re.search(pattern, schema_text):
            schema_text = re.sub(pattern, replacement, schema_text)
        else:
            # insert before first column comment of this table
            anchor = rf"(CREATE TABLE IF NOT EXISTS (?:public\.)?{table}[\s\S]*?)(COMMENT ON COLUMN public\.{table}\.)"
            schema_text = re.sub(
                anchor,
                rf"\1COMMENT ON TABLE public.{table} IS '{_escape_sql_string(comment)}';\n\2",
                schema_text,
                count=1,
            )
    return schema_text


def _comments_from_schema(schema_text: str) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    table_comments: dict[str, str] = {}
    column_comments: dict[tuple[str, str], str] = {}
    for m in re.finditer(
        r"COMMENT ON TABLE (?:public\.)?(\w+) IS '((?:''|[^'])*)';", schema_text
    ):
        table_comments[m.group(1)] = m.group(2).replace("''", "'")
    for m in re.finditer(
        r"COMMENT ON (?:COLUMN )?(?:public\.)?(\w+)\.(?:(\w+)|\"(\w+)\") IS '((?:''|[^'])*)';",
        schema_text,
    ):
        col = m.group(2) or m.group(3)
        column_comments[(m.group(1), col)] = m.group(4).replace("''", "'")
    return table_comments, column_comments


def _sync_table_sql_files(
    tables: dict[str, list[str]],
    table_comments: dict[str, str],
    column_comments: dict[tuple[str, str], str],
) -> None:
    tables_dir = SQL_DIR / "tables"
    if not tables_dir.is_dir():
        return
    for path in sorted(tables_dir.glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        m = re.search(r"CREATE TABLE IF NOT EXISTS (?:public\.)?(\w+)", text)
        if not m:
            continue
        table = m.group(1)
        if table not in tables:
            continue
        base = text.split("\nCOMMENT ON ", 1)[0].strip()
        lines = [base, ""]
        tbl = _resolve_table_comment(table, table_comments)
        lines.append(
            f"COMMENT ON TABLE public.{table} IS '{_escape_sql_string(tbl)}';"
        )
        for col in tables[table]:
            comment = _resolve_column_comment(table, col, column_comments)
            qcol = _quote_col(col)
            lines.append(
                f"COMMENT ON COLUMN public.{table}.{qcol} IS '{_escape_sql_string(comment)}';"
            )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    schema_text = SCHEMA.read_text(encoding="utf-8")
    table_comments_existing, column_comments_existing = _load_existing_comments()
    tables = _parse_tables(schema_text)

    table_comments_in_schema: set[str] = set()
    for m in re.finditer(r"COMMENT ON TABLE (?:public\.)?(\w+)", schema_text):
        table_comments_in_schema.add(m.group(1))

    column_comments_in_schema: set[tuple[str, str]] = set()
    for m in re.finditer(
        r"COMMENT ON (?:COLUMN )?(?:public\.)?(\w+)\.(?:(\w+)|\"(\w+)\")",
        schema_text,
    ):
        column_comments_in_schema.add((m.group(1), m.group(2) or m.group(3)))

    insert_after: dict[int, list[str]] = {}

    # Merge missing comments into schema after each table block
    for table, cols in tables.items():
        block_start = schema_text.find(f"CREATE TABLE IF NOT EXISTS {table} ")
        if block_start < 0:
            block_start = schema_text.find(f"CREATE TABLE IF NOT EXISTS public.{table} ")
        if block_start < 0:
            continue
        next_create = schema_text.find("\nCREATE TABLE", block_start + 1)
        if next_create < 0:
            next_create = len(schema_text)
        block = schema_text[block_start:next_create]
        to_add: list[str] = []
        if table not in table_comments_in_schema and table in TABLE_DEFAULTS:
            tbl_comment = table_comments_existing.get(table, TABLE_DEFAULTS[table])
            to_add.append(
                f"COMMENT ON TABLE public.{table} IS '{_escape_sql_string(tbl_comment)}';"
            )
        for col in cols:
            if (table, col) in column_comments_in_schema:
                continue
            comment = column_comments_existing.get((table, col))
            if comment is None:
                comment = _infer_comment(table, col)
            qcol = _quote_col(col)
            to_add.append(
                f"COMMENT ON COLUMN public.{table}.{qcol} IS '{_escape_sql_string(comment)}';"
            )
        if not to_add:
            continue
        insert_pos = next_create
        insert_after.setdefault(insert_pos, []).extend(to_add)

    if insert_after:
        out: list[str] = []
        pos = 0
        for insert_pos in sorted(insert_after.keys()):
            out.append(schema_text[pos:insert_pos])
            out.append("\n".join(insert_after[insert_pos]) + "\n")
            pos = insert_pos
        out.append(schema_text[pos:])
        SCHEMA.write_text("".join(out), encoding="utf-8")

    # Re-read schema and emit full patch + sync tables/*.sql
    schema_final = _apply_schema_comment_overrides(SCHEMA.read_text(encoding="utf-8"))
    SCHEMA.write_text(schema_final, encoding="utf-8")
    table_comments_final, column_comments_from_schema = _comments_from_schema(schema_final)
    column_comments_final: dict[tuple[str, str], str] = dict(column_comments_from_schema)
    for table, cols in tables.items():
        for col in cols:
            column_comments_final[(table, col)] = _resolve_column_comment(
                table, col, column_comments_from_schema
            )

    patch_lines: list[str] = [
        "-- 补齐/更新全库表与字段 COMMENT（可重复执行）",
        "-- Apply: psql -U minerva -d minerva -f backend/sql/patches/2026-07-01-schema-column-comments.sql",
        "",
    ]
    for table in sorted(tables.keys()):
        tbl = _resolve_table_comment(table, table_comments_final)
        patch_lines.append(
            f"COMMENT ON TABLE public.{table} IS '{_escape_sql_string(tbl)}';"
        )
        for col in tables[table]:
            comment = _resolve_column_comment(table, col, column_comments_final)
            qcol = _quote_col(col)
            patch_lines.append(
                f"COMMENT ON COLUMN public.{table}.{qcol} IS '{_escape_sql_string(comment)}';"
            )
    PATCH_OUT.write_text("\n".join(patch_lines) + "\n", encoding="utf-8")
    _sync_table_sql_files(tables, table_comments_final, column_comments_final)

    missing = sum(
        1
        for t, cols in tables.items()
        for c in cols
        if (t, c) not in column_comments_existing
    )
    print(f"Wrote {PATCH_OUT.relative_to(ROOT)}")
    print(f"Updated {SCHEMA.relative_to(ROOT)}")
    print(f"Synced {len(list((SQL_DIR / 'tables').glob('*.sql')))} files under sql/tables/")
    print(f"Generated comments for {missing} previously missing columns")


if __name__ == "__main__":
    main()
