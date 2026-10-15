"""Exact deployment/journal/resource schemas and reviewed v1/v2 transitions."""

import json
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    and_,
    column,
    insert,
    inspect,
    or_,
    select,
    table,
    update,
)
from sqlalchemy.engine import Connection
from sqlalchemy.schema import CreateTable

metadata = MetaData()
singleton = Column("singleton", Integer, primary_key=True)
deployment = Table(
    "deployment",
    metadata,
    singleton,
    Column("schema_version", Integer, nullable=False),
    Column("identity", String, nullable=False),
    Column("epoch", String, nullable=False),
    Column("retention_profile", String, nullable=False),
    Column("configured_limits", LargeBinary, nullable=False),
    CheckConstraint(singleton == 1),
)

commands = Table(
    "commands",
    metadata,
    Column("operation_id", String, primary_key=True),
    Column("record_kind", String, nullable=False),
    Column("deployment_scope", String, nullable=False),
    Column("subject", String, nullable=False),
    Column("operation_name", String, nullable=False),
    Column("contract_version", String, nullable=False),
    Column("caller_key", String),
    Column("intent_bytes", LargeBinary),
    Column("intent_digest", String),
    Column("revision", Integer, nullable=False),
    Column("receipt_bytes", LargeBinary, nullable=False),
    Column("receipt_digest", String, nullable=False),
    Column("handoff_ref", String),
    UniqueConstraint(
        "deployment_scope", "subject", "operation_name", "contract_version", "caller_key"
    ),
)
commands.append_constraint(
    CheckConstraint(
        or_(
            and_(
                commands.c.record_kind == "command",
                commands.c.caller_key.is_not(None),
                commands.c.intent_bytes.is_not(None),
                commands.c.intent_digest.is_not(None),
            ),
            and_(
                commands.c.record_kind == "query",
                commands.c.caller_key.is_(None),
                commands.c.intent_bytes.is_(None),
                commands.c.intent_digest.is_(None),
            ),
        )
    )
)
commands.append_constraint(CheckConstraint(commands.c.revision > 0))

observations = Table(
    "observations",
    metadata,
    Column("operation_id", String, ForeignKey("commands.operation_id"), primary_key=True),
    Column("revision", Integer, primary_key=True),
    Column("receipt_bytes", LargeBinary, nullable=False),
    Column("receipt_digest", String, nullable=False),
    Column("handoff_ref", String),
)
observations.append_constraint(CheckConstraint(observations.c.revision > 0))


feeds = Table(
    "feeds",
    metadata,
    Column("feed_id", String, primary_key=True),
    Column("subject", String, nullable=False),
    Column("high_water", Integer, nullable=False),
    Column("revision", Integer, nullable=False),
)
feeds.append_constraint(CheckConstraint(feeds.c.high_water > 0))
feeds.append_constraint(CheckConstraint(feeds.c.revision > 0))
snapshots = Table(
    "snapshots",
    metadata,
    Column("feed_id", String, ForeignKey("feeds.feed_id"), primary_key=True),
    Column("producer_version", Integer, primary_key=True),
    Column(
        "operation_id", String, ForeignKey("commands.operation_id"), nullable=False, unique=True
    ),
    Column("content_digest", String, nullable=False),
    Column("producer_bytes", LargeBinary, nullable=False),
    Column("snapshot_bytes", LargeBinary, nullable=False),
    Column("snapshot_digest", String, nullable=False),
)
snapshots.append_constraint(CheckConstraint(snapshots.c.producer_version > 0))
evidence = Table(
    "evidence",
    metadata,
    Column("identity", String, primary_key=True),
    Column("operation_id", String, ForeignKey("commands.operation_id"), nullable=False),
    Column("reference_bytes", LargeBinary, nullable=False),
    Column("reference_digest", String, nullable=False),
    Column("fact_bytes", LargeBinary, nullable=False),
    Column("fact_digest", String, nullable=False),
)


def _objects(connection: Connection) -> dict[tuple[str, str], str | None]:
    catalog = table(
        "sqlite_schema", column("name", String), column("type", String), column("sql", String)
    )
    return {
        (name, kind): ddl
        for name, kind, ddl in connection.execute(
            select(catalog.c.name, catalog.c.type, catalog.c.sql)
        )
        if not name.startswith("sqlite_")
    }


def _validate_table(connection: Connection, expected: Table) -> None:
    inspector = inspect(connection)
    columns = inspector.get_columns(expected.name)
    actual_columns = [
        (item["name"], str(item["type"]), item["nullable"], item.get("default")) for item in columns
    ]
    wanted_columns = [(item.name, str(item.type), item.nullable, None) for item in expected.columns]
    primary = inspector.get_pk_constraint(expected.name)
    if (
        actual_columns != wanted_columns
        or primary["constrained_columns"] != [c.name for c in expected.primary_key]
        or primary.get("name") is not None
        or inspector.get_indexes(expected.name)
    ):
        raise ValueError("Unrecognized retained columns, primary key or indexes")
    actual_unique = inspector.get_unique_constraints(expected.name)
    wanted_unique = sorted(
        tuple(c.name for c in constraint.columns)
        for constraint in expected.constraints
        if isinstance(constraint, UniqueConstraint)
    )
    if sorted(tuple(item["column_names"]) for item in actual_unique) != wanted_unique or any(
        item.get("name") is not None for item in actual_unique
    ):
        raise ValueError("Unrecognized retained unique constraints")
    checks = inspector.get_check_constraints(expected.name)
    expected_checks = sorted(
        str(
            constraint.sqltext.compile(
                dialect=connection.dialect,
                compile_kwargs={"literal_binds": True, "include_table": False},
            )
        )
        for constraint in expected.constraints
        if isinstance(constraint, CheckConstraint)
    )
    if sorted(item["sqltext"] for item in checks) != expected_checks or any(
        item.get("name") is not None for item in checks
    ):
        raise ValueError("Unrecognized retained check constraints")
    foreign = inspector.get_foreign_keys(expected.name)
    wanted_foreign = sorted(
        (
            tuple(element.parent.name for element in constraint.elements),
            next(iter(constraint.elements)).column.table.name,
            tuple(element.column.name for element in constraint.elements),
        )
        for constraint in expected.foreign_key_constraints
    )
    if sorted(
        (
            tuple(item["constrained_columns"]),
            item["referred_table"],
            tuple(item["referred_columns"]),
        )
        for item in foreign
    ) != wanted_foreign or any(
        item.get("name") is not None
        or item.get("referred_schema") is not None
        or item.get("options")
        for item in foreign
    ):
        raise ValueError("Unrecognized retained foreign keys")


def _validate_schema(connection: Connection, version: int) -> None:
    expected = (deployment,) if version == 1 else (deployment, commands, observations)
    if version == 3:
        expected += (feeds, snapshots, evidence)
    objects = _objects(connection)
    if set(objects) != {(item.name, "table") for item in expected}:
        raise ValueError("Unrecognized retained schema objects")
    for item in expected:
        # Inspector omits SQLite collations and table flags. Accept only the
        # exact deployed library-generated DDL, without parsing or executing it.
        ddl = str(CreateTable(item).compile(dialect=connection.dialect)).strip()
        if objects[(item.name, "table")] != ddl:
            raise ValueError("Unrecognized retained table definition")
        _validate_table(connection, item)


@dataclass(frozen=True)
class Deployment:
    identity: str
    epoch: str
    retention_profile: str
    configured_limits: bytes


def initialize(connection: Connection, identity: str, existed: bool) -> Deployment:
    """Validate before writes; migrate only exact deployment v1 or journal v2."""
    if not existed and not _objects(connection):
        metadata.create_all(connection)
        connection.execute(
            insert(deployment).values(
                singleton=1,
                schema_version=3,
                identity=identity,
                epoch=uuid4().hex,
                retention_profile="retain-all",
                configured_limits=b"{}",
            )
        )
    objects = _objects(connection)
    if set(objects) not in (
        {("deployment", "table")},
        {("deployment", "table"), ("commands", "table"), ("observations", "table")},
        {(item.name, "table") for item in metadata.tables.values()},
    ):
        raise ValueError("Unrecognized retained schema objects")
    _validate_table(connection, deployment)
    rows = connection.execute(select(deployment)).mappings().all()
    if len(rows) != 1:
        raise ValueError("Incompatible retained deployment")
    row = rows[0]
    if (
        row["singleton"] != 1
        or row["schema_version"] not in (1, 2, 3)
        or row["identity"] != identity
        or not isinstance(row["identity"], str)
        or not row["identity"].strip()
        or not isinstance(row["epoch"], str)
        or not row["epoch"].strip()
        or row["retention_profile"] != "retain-all"
        or type(row["configured_limits"]) is not bytes
    ):
        raise ValueError("Incompatible retained deployment")
    try:
        settings = json.loads(row["configured_limits"])
        if not isinstance(settings, dict):
            raise ValueError("Retained settings must be a finite JSON object")
        json.dumps(settings, allow_nan=False)
    except RecursionError as error:
        raise ValueError("Retained settings cannot be safely decoded") from error
    _validate_schema(connection, row["schema_version"])
    if row["schema_version"] == 1:
        commands.create(connection)
        observations.create(connection)
        _validate_schema(connection, 2)
        connection.execute(update(deployment).values(schema_version=2))
    if row["schema_version"] in (1, 2):
        feeds.create(connection)
        snapshots.create(connection)
        evidence.create(connection)
        _validate_schema(connection, 3)
        connection.execute(update(deployment).values(schema_version=3))
    return Deployment(
        row["identity"], row["epoch"], row["retention_profile"], row["configured_limits"]
    )
