"""Initial workflow schema.

Revision ID: 0001
Revises:
Create Date: 2026-06-15
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("stage_status", sa.String(length=30), nullable=False),
        sa.Column("state_json", mysql.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_projects_stage", "projects", ["stage"])
    op.create_index("ix_projects_stage_status", "projects", ["stage_status"])
    op.create_index("ix_projects_updated_at", "projects", ["updated_at"])

    op.create_table(
        "requirement_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("requirement_json", mysql.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "version", name="uq_requirement_version"
        ),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "ix_requirement_snapshots_project_id",
        "requirement_snapshots",
        ["project_id"],
    )

    op.create_table(
        "questions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("question_id", sa.String(length=16), nullable=False),
        sa.Column("question_type", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("importance", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "question_id", name="uq_project_question"
        ),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_questions_project_id", "questions", ["project_id"])
    op.create_index("ix_questions_status", "questions", ["status"])

    op.create_table(
        "logic_issues",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("issue_id", sa.String(length=16), nullable=False),
        sa.Column("dimension", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "issue_id", name="uq_project_logic_issue"
        ),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_logic_issues_project_id", "logic_issues", ["project_id"])
    op.create_index("ix_logic_issues_severity", "logic_issues", ["severity"])
    op.create_index("ix_logic_issues_status", "logic_issues", ["status"])

    op.create_table(
        "artifacts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("artifact_type", sa.String(length=30), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", mysql.LONGTEXT(), nullable=False),
        sa.Column("metadata_json", mysql.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "artifact_type",
            "version",
            name="uq_artifact_version",
        ),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_artifacts_project_id", "artifacts", ["project_id"])
    op.create_index("ix_artifacts_artifact_type", "artifacts", ["artifact_type"])

    op.create_table(
        "approvals",
        sa.Column("approval_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("artifact_version", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("approval_id"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_approvals_project_id", "approvals", ["project_id"])

    op.create_table(
        "workflow_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details_json", mysql.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "ix_workflow_events_project_id", "workflow_events", ["project_id"]
    )
    op.create_index(
        "ix_workflow_events_event_type", "workflow_events", ["event_type"]
    )


def downgrade() -> None:
    op.drop_table("workflow_events")
    op.drop_table("approvals")
    op.drop_table("artifacts")
    op.drop_table("logic_issues")
    op.drop_table("questions")
    op.drop_table("requirement_snapshots")
    op.drop_table("projects")
