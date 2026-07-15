"""analysis configuration presets, task snapshots, and ASR transcripts

Revision ID: 0002_analysis_config_and_asr
Revises: 0001_initial
Create Date: 2026-07-15
"""
from alembic import op
import sqlalchemy as sa


revision = "0002_analysis_config_and_asr"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analysis_presets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("config", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_analysis_presets_id", "analysis_presets", ["id"])
    op.create_index("ix_analysis_presets_user_id", "analysis_presets", ["user_id"])

    op.create_table(
        "video_analysis_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("video_id", sa.Integer(), sa.ForeignKey("videos.id"), nullable=False),
        sa.Column("draft_config", sa.Text(), nullable=False),
        sa.Column("active_snapshot", sa.Text(), nullable=True),
        sa.Column("draft_revision", sa.Integer(), nullable=False),
        sa.Column("active_revision", sa.Integer(), nullable=True),
        sa.Column("draft_hash", sa.String(), nullable=False),
        sa.Column("active_hash", sa.String(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_video_analysis_configs_id", "video_analysis_configs", ["id"])
    op.create_index("ix_video_analysis_configs_video_id", "video_analysis_configs", ["video_id"], unique=True)

    op.create_table(
        "video_transcripts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("video_id", sa.Integer(), sa.ForeignKey("videos.id"), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("provider_task_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("language", sa.String(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("usage", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_video_transcripts_id", "video_transcripts", ["id"])
    op.create_index("ix_video_transcripts_video_id", "video_transcripts", ["video_id"], unique=True)

    op.create_table(
        "analysis_task_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.String(), sa.ForeignKey("analysis_tasks.id"), nullable=False),
        sa.Column("config_revision", sa.Integer(), nullable=True),
        sa.Column("config", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_analysis_task_snapshots_id", "analysis_task_snapshots", ["id"])
    op.create_index("ix_analysis_task_snapshots_task_id", "analysis_task_snapshots", ["task_id"], unique=True)


def downgrade() -> None:
    for table in [
        "analysis_task_snapshots",
        "video_transcripts",
        "video_analysis_configs",
        "analysis_presets",
    ]:
        op.drop_table(table)
