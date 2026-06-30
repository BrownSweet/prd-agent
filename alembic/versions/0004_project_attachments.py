"""Add project attachment table.

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-27
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


def upgrade() -> None:
    op.create_table(
        "project_attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_path", sa.String(length=600), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("extracted_text", mysql.LONGTEXT(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "ix_project_attachments_project_id",
        "project_attachments",
        ["project_id"],
    )
    op.create_index(
        "ix_project_attachments_sha256",
        "project_attachments",
        ["sha256"],
    )
    op.create_index(
        "ix_project_attachments_kind",
        "project_attachments",
        ["kind"],
    )
    op.create_index(
        "ix_project_attachments_status",
        "project_attachments",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_project_attachments_status", table_name="project_attachments")
    op.drop_index("ix_project_attachments_kind", table_name="project_attachments")
    op.drop_index("ix_project_attachments_sha256", table_name="project_attachments")
    op.drop_index(
        "ix_project_attachments_project_id",
        table_name="project_attachments",
    )
    op.drop_table("project_attachments")
