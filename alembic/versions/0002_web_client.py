"""Add web client workflow tables.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-15
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


def upgrade() -> None:
    op.create_table(
        "llm_configs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("api_key", mysql.LONGTEXT(), nullable=True),
        sa.Column("base_url", sa.String(length=500), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("native_structured_output", sa.Boolean(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_llm_config_name"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_llm_configs_is_default", "llm_configs", ["is_default"])
    op.create_index("ix_llm_configs_archived_at", "llm_configs", ["archived_at"])

    op.add_column(
        "projects",
        sa.Column("llm_config_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column("archived_at", sa.DateTime(), nullable=True),
    )
    op.create_foreign_key(
        "fk_projects_llm_config",
        "projects",
        "llm_configs",
        ["llm_config_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_projects_llm_config_id", "projects", ["llm_config_id"])
    op.create_index("ix_projects_archived_at", "projects", ["archived_at"])

    op.create_table(
        "workflow_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("job_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("payload_json", mysql.JSON(), nullable=False),
        sa.Column("result_json", mysql.JSON(), nullable=False),
        sa.Column("llm_config_id", sa.String(length=36), nullable=True),
        sa.Column("llm_config_version", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["llm_config_id"], ["llm_configs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_job_idempotency_key"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_workflow_jobs_project_id", "workflow_jobs", ["project_id"])
    op.create_index("ix_workflow_jobs_status", "workflow_jobs", ["status"])
    op.create_index("ix_workflow_jobs_created_at", "workflow_jobs", ["created_at"])

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value_json", mysql.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
        **TABLE_OPTIONS,
    )


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_table("workflow_jobs")
    op.drop_index("ix_projects_archived_at", table_name="projects")
    op.drop_index("ix_projects_llm_config_id", table_name="projects")
    op.drop_constraint("fk_projects_llm_config", "projects", type_="foreignkey")
    op.drop_column("projects", "archived_at")
    op.drop_column("projects", "llm_config_id")
    op.drop_table("llm_configs")
