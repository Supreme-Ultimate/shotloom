"""COS multipart upload sessions and video object references

Revision ID: 0003_cos_multipart_uploads
Revises: 0002_analysis_config_and_asr
Create Date: 2026-07-15
"""
from alembic import op
import sqlalchemy as sa


revision = "0003_cos_multipart_uploads"
down_revision = "0002_analysis_config_and_asr"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("videos") as batch_op:
        batch_op.add_column(sa.Column("storage_provider", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("storage_key", sa.String(), nullable=True))

    op.create_table(
        "cos_upload_sessions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("part_size", sa.Integer(), nullable=False),
        sa.Column("part_count", sa.Integer(), nullable=False),
        sa.Column("object_key", sa.String(), nullable=False, unique=True),
        sa.Column("cos_upload_id", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("video_id", sa.Integer(), sa.ForeignKey("videos.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_cos_upload_sessions_user_id", "cos_upload_sessions", ["user_id"])


def downgrade() -> None:
    op.drop_table("cos_upload_sessions")
    with op.batch_alter_table("videos") as batch_op:
        batch_op.drop_column("storage_key")
        batch_op.drop_column("storage_provider")
