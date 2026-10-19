"""Exercise real transactional PostgreSQL DDL against the previous schema."""

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

_path = (
    Path(__file__).resolve().parents[1]
    / "alembic/versions/d9e621a7f304_document_storage_cleanup.py"
)
_spec = importlib.util.spec_from_file_location("document_storage_migration", _path)
migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migration)


@pytest.fixture
async def legacy_schema(test_engine):
    schema = "document_migration_" + uuid.uuid4().hex
    async with test_engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        await connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
        await connection.execute(
            text("CREATE TABLE organizations (id integer PRIMARY KEY)")
        )
        await connection.execute(text("INSERT INTO organizations VALUES (1), (2)"))
        await connection.execute(
            text("""CREATE TABLE knowledge_base_documents (
            document_uuid varchar(36) PRIMARY KEY, organization_id integer NOT NULL,
            custom_metadata jsonb, is_active boolean NOT NULL)""")
        )
        yield connection
        # All test DDL is private to this schema, including failed migrations.
        await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


async def add_document(connection, *, org=1, active=True, key="owned"):
    identifier = str(uuid.uuid4())
    object_key = (
        f"knowledge_base/{org}/{identifier}/informe.txt" if key == "owned" else key
    )
    await connection.execute(
        text("""INSERT INTO knowledge_base_documents VALUES
            (:uuid, :org, jsonb_build_object('s3_key', CAST(:key AS text)), :active)"""),
        {"uuid": identifier, "org": org, "key": object_key, "active": active},
    )
    return identifier, object_key


async def run(connection, direction):
    def execute(sync_connection):
        with Operations.context(MigrationContext.configure(sync_connection)):
            getattr(migration, direction)()

    await connection.run_sync(execute)


async def test_backfill_preserves_active_and_historical_documents_and_scopes_deletions(
    legacy_schema,
):
    connection = legacy_schema
    active, active_key = await add_document(connection)
    inactive, inactive_key = await add_document(connection, org=2, active=False)
    external, _ = await add_document(connection, key=None)
    before = list(
        (
            await connection.execute(
                text("SELECT * FROM knowledge_base_documents ORDER BY document_uuid")
            )
        ).mappings()
    )
    await run(connection, "upgrade")
    rows = {
        row["document_uuid"]: row
        for row in (
            await connection.execute(
                text("SELECT * FROM knowledge_base_storage_objects")
            )
        ).mappings()
    }
    assert set(rows) == {active, inactive}
    assert rows[active]["state"] == "attached" and rows[active]["delete_after"] is None
    assert (
        rows[active]["object_key"] == active_key
        and rows[active]["organization_id"] == 1
    )
    assert (
        rows[inactive]["state"] == "deleting"
        and rows[inactive]["delete_after"] is not None
    )
    assert (
        rows[inactive]["object_key"] == inactive_key
        and rows[inactive]["organization_id"] == 2
    )
    assert external not in rows
    after = list(
        (
            await connection.execute(
                text("SELECT * FROM knowledge_base_documents ORDER BY document_uuid")
            )
        ).mappings()
    )
    assert before == after


@pytest.mark.parametrize(
    "key", ["knowledge_base/2/foreign/informe.txt", "../informe.txt"]
)
async def test_invalid_historical_destination_rolls_back_the_entire_migration(
    legacy_schema, key
):
    connection = legacy_schema
    await add_document(connection)
    await add_document(connection, key=key)
    with pytest.raises(RuntimeError, match="antes de migrar"):
        async with connection.begin_nested():
            await run(connection, "upgrade")
    assert (
        await connection.scalar(
            text(
                "SELECT to_regclass(current_schema() || '.knowledge_base_storage_objects')"
            )
        )
        is None
    )
    assert (
        await connection.scalar(text("SELECT count(*) FROM knowledge_base_documents"))
        == 2
    )


async def test_downgrade_rejects_pending_obligations_then_keeps_documents_intact(
    legacy_schema,
):
    connection = legacy_schema
    await add_document(connection, active=False)
    await run(connection, "upgrade")
    with pytest.raises(RuntimeError, match="limpiezas pendientes"):
        await run(connection, "downgrade")
    assert (
        await connection.scalar(
            text("SELECT count(*) FROM knowledge_base_storage_objects")
        )
        == 1
    )
    await connection.execute(
        text("UPDATE knowledge_base_storage_objects SET state='purged', object_key=''")
    )
    await run(connection, "downgrade")
    assert (
        await connection.scalar(
            text(
                "SELECT to_regclass(current_schema() || '.knowledge_base_storage_objects')"
            )
        )
        is None
    )
    assert (
        await connection.scalar(text("SELECT count(*) FROM knowledge_base_documents"))
        == 1
    )
