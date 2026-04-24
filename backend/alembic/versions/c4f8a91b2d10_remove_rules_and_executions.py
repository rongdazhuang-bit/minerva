"""remove rules and executions tables

Revision ID: c4f8a91b2d10
Revises: bbec5fe9111a
Create Date: 2026-04-24

"""
from typing import Sequence, Union

from alembic import op

revision: str = "c4f8a91b2d10"
down_revision: Union[str, Sequence[str], None] = "bbec5fe9111a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(op.f("ix_execution_events_execution_id"), table_name="execution_events")
    op.drop_table("execution_events")
    op.drop_index(op.f("ix_executions_workspace_id"), table_name="executions")
    op.drop_index(op.f("ix_executions_rule_id"), table_name="executions")
    op.drop_table("executions")
    op.drop_constraint(
        "fk_rules_current_published_version_id", "rules", type_="foreignkey"
    )
    op.drop_index(op.f("ix_rule_versions_rule_id"), table_name="rule_versions")
    op.drop_table("rule_versions")
    op.drop_index(op.f("ix_rules_workspace_id"), table_name="rules")
    op.drop_table("rules")


def downgrade() -> None:
    """不恢复已删除的 rules / 执行子域；需回滚请从数据库备份或历史迁移重做。"""
