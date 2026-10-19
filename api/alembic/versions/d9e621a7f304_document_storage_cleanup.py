"""Durable knowledge-base upload and cleanup intents.

Revision ID: d9e621a7f304
Revises: c82d4f6a9b10
"""

import hashlib
import json
import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "d9e621a7f304"
down_revision = "c82d4f6a9b10"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "knowledge_base_storage_objects",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Integer(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("document_uuid", sa.String(36), nullable=False),
        sa.Column("object_key", sa.String(1024), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("delete_after", sa.DateTime(timezone=True)),
        sa.Column("purged_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(40)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for field in ("organization_id", "document_uuid", "delete_after"):
        op.create_index(
            "ix_knowledge_base_storage_objects_" + field,
            "knowledge_base_storage_objects",
            [field],
        )
    # Carry existing inactive documents into the durable cleanup queue, while
    # preserving all active and historical document identifiers.
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT document_uuid, organization_id, custom_metadata, is_active FROM knowledge_base_documents"
        )
    )
    for row in rows.mappings():
        metadata = row["custom_metadata"] or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        key = metadata.get("s3_key")
        if not key:
            continue
        try:
            canonical = str(uuid.UUID(row["document_uuid"]))
        except (ValueError, TypeError, AttributeError) as error:
            raise RuntimeError(
                "Revisa la identidad del documento antes de migrar."
            ) from error
        prefix = f"knowledge_base/{row['organization_id']}/{row['document_uuid']}/"
        if not isinstance(key, str) or canonical != row["document_uuid"]:
            raise RuntimeError(
                "Revisa el destino de almacenamiento del documento antes de migrar."
            )
        name = key.removeprefix(prefix)
        if (
            not key.startswith(prefix)
            or not name
            or "/" in name
            or "\\" in name
            or name in {".", ".."}
        ):
            raise RuntimeError(
                f"Revisa el destino de almacenamiento del documento {row['document_uuid']} antes de migrar."
            )
        bind.execute(
            sa.text("""INSERT INTO knowledge_base_storage_objects
            (id,organization_id,document_uuid,object_key,state,delete_after,attempts,created_at)
            VALUES (:id,:org,:uuid,:key,:state,:after,0,:now)"""),
            {
                "id": hashlib.sha256(key.encode()).hexdigest(),
                "org": row["organization_id"],
                "uuid": row["document_uuid"],
                "key": key,
                "state": "attached" if row["is_active"] else "deleting",
                "after": None if row["is_active"] else datetime.now(UTC),
                "now": datetime.now(UTC),
            },
        )


def downgrade():
    # A database rollback must not silently erase pending deletion obligations.
    bind = op.get_bind()
    if bind.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM knowledge_base_storage_objects WHERE state IN ('awaiting','deleting'))"
        )
    ):
        raise RuntimeError(
            "Hay cargas o limpiezas pendientes; restaura la copia completa compatible."
        )
    op.drop_table("knowledge_base_storage_objects")
