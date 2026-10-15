"""Schema-v1 deployment identity; provider tasks add their concrete tables."""

from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    insert,
    inspect,
    select,
)
from sqlalchemy.engine import Connection

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


@dataclass(frozen=True)
class Deployment:
    identity: str
    epoch: str
    retention_profile: str
    configured_limits: bytes


def initialize(connection: Connection, identity: str, existed: bool) -> Deployment:
    """Create only a new file; never adopt or replace unrecognized state."""
    tables = inspect(connection).get_table_names()
    if not existed and not tables:
        metadata.create_all(connection)
        connection.execute(
            insert(deployment).values(
                singleton=1,
                schema_version=1,
                identity=identity,
                epoch=uuid4().hex,
                retention_profile="retain-all",
                configured_limits=b"{}",
            )
        )
    elif "deployment" not in tables:
        raise ValueError("Unrecognized retained schema")
    rows = connection.execute(select(deployment)).mappings().all()
    if len(rows) != 1 or rows[0]["schema_version"] != 1 or rows[0]["identity"] != identity:
        raise ValueError("Incompatible retained deployment")
    row = rows[0]
    return Deployment(
        row["identity"], row["epoch"], row["retention_profile"], row["configured_limits"]
    )
