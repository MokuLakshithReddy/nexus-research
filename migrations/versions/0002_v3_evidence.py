"""Add the V3 evidence ledger and immutable research snapshots.

Revision ID: 0002_v3_evidence
Revises: 0001_v2_schema
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0002_v3_evidence"
down_revision = "0001_v2_schema"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return inspect(op.get_bind()).has_table(name)


def _index_exists(table: str, name: str) -> bool:
    return any(index.get("name") == name for index in inspect(op.get_bind()).get_indexes(table))


def upgrade() -> None:
    # V2's first migration uses Base.metadata.create_all. On a fresh database
    # this may already create V3 tables; an existing V2 database needs them added.
    if not _table_exists("evidence_claims"):
        op.create_table(
            "evidence_claims",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("claim_key", sa.String(length=64), nullable=False),
            sa.Column("assessment", sa.String(length=32), nullable=False, server_default="needs_review"),
            sa.Column("extraction_method", sa.String(length=40), nullable=False, server_default="extractive"),
            sa.Column("review_status", sa.String(length=24), nullable=False, server_default="unreviewed"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("project_id", "claim_key", name="uq_evidence_claim_project_key"),
        )
    if not _table_exists("claim_evidence"):
        op.create_table(
            "claim_evidence",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("claim_id", sa.Integer(), sa.ForeignKey("evidence_claims.id", ondelete="CASCADE"), nullable=False),
            sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
            sa.Column("chunk_index", sa.Integer(), nullable=False),
            sa.Column("relation", sa.String(length=16), nullable=False, server_default="context"),
            sa.Column("excerpt", sa.Text(), nullable=False),
            sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("claim_id", "source_id", "chunk_index", name="uq_claim_evidence_passage"),
            sa.CheckConstraint("relation IN ('supports', 'contradicts', 'context')", name="ck_claim_evidence_relation"),
        )
    if not _table_exists("research_snapshots"):
        op.create_table(
            "research_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("digest", sa.String(length=64), nullable=False),
            sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("manifest", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint("project_id", "digest", name="uq_snapshot_project_digest"),
        )

    for table, name, columns in [
        ("evidence_claims", "ix_evidence_claims_project_id", ["project_id"]),
        ("claim_evidence", "ix_claim_evidence_claim_id", ["claim_id"]),
        ("claim_evidence", "ix_claim_evidence_source_id", ["source_id"]),
        ("research_snapshots", "ix_research_snapshots_project_id", ["project_id"]),
        ("evidence_claims", "ix_claims_project_created", ["project_id", "created_at"]),
        ("claim_evidence", "ix_claim_evidence_source", ["source_id", "claim_id"]),
        ("research_snapshots", "ix_snapshots_project_created", ["project_id", "created_at"]),
    ]:
        if not _index_exists(table, name):
            op.create_index(name, table, columns, unique=False)


def downgrade() -> None:
    for table, name in [
        ("research_snapshots", "ix_snapshots_project_created"),
        ("claim_evidence", "ix_claim_evidence_source"),
        ("evidence_claims", "ix_claims_project_created"),
    ]:
        if _table_exists(table) and _index_exists(table, name):
            op.drop_index(name, table_name=table)
    for table in ["research_snapshots", "claim_evidence", "evidence_claims"]:
        if _table_exists(table):
            op.drop_table(table)
