"""Fail-closed single-process SQLite lifetime on a local file volume."""

import asyncio
import os
import sqlite3
from collections.abc import Callable
from pathlib import Path
from threading import Lock
from typing import BinaryIO

from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import URL, Connection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import ConnectionPoolEntry, NullPool

from craftreport.adapters.storage.schema import deployment, initialize


class StorageUnavailable(RuntimeError):
    """Configured retained storage cannot safely serve requests."""


def _local_path(path: Path) -> Path:
    if not path.is_absolute() or str(path).startswith(("\\\\", "//")):
        raise ValueError("An absolute local database path is required")
    resolved = path.resolve(strict=False)
    if str(resolved).startswith(("\\\\", "//")):
        raise ValueError("A resolved network database path is unsupported")
    if not resolved.parent.is_dir() or (resolved.exists() and not resolved.is_file()):
        raise ValueError("The local parent directory must exist and the target must be a file")
    if os.name == "nt":
        import ctypes

        drive_type = ctypes.windll.kernel32.GetDriveTypeW
        drive_type.argtypes = [ctypes.c_wchar_p]
        drive_type.restype = ctypes.c_uint
        if drive_type(resolved.anchor) not in (2, 3, 6):
            raise ValueError("The database requires a local file volume")
    return resolved


def _lock_file(path: Path) -> BinaryIO:
    handle = path.with_name(path.name + ".lock").open("a+b")
    try:
        if handle.seek(0, os.SEEK_END) == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        handle.close()
        raise
    return handle


def _configure(connection: sqlite3.Connection, _record: ConnectionPoolEntry) -> None:
    # SQLite requires autocommit while enabling foreign keys. Restore explicit
    # PEP-249 transactions before SQLAlchemy's Engine.begin takes ownership.
    connection.autocommit = True
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA synchronous = FULL")
        settings = (
            connection.execute("PRAGMA foreign_keys").fetchone(),
            connection.execute("PRAGMA synchronous").fetchone(),
            connection.execute("PRAGMA journal_mode").fetchone(),
        )
        if settings != ((1,), (2,), ("delete",)):
            raise sqlite3.DatabaseError("Unsupported SQLite durability configuration")
    finally:
        connection.autocommit = False


class Database:
    """One owner, one mutex, fresh connections and short synchronous callbacks.

    Callbacks must finish synchronously; they must not return live database
    results/handles or perform external I/O. Cancellation does not undo an
    already executing worker transaction; its committed state remains canonical.
    Network filesystems and multi-process hosts are unsupported.
    """

    def __init__(self, path: Path, deployment_id: str, *, maintenance: bool = False) -> None:
        self._mutex = Lock()
        self._closed = False
        if not deployment_id:
            raise StorageUnavailable("A deployment identity is required")
        try:
            self.path = _local_path(path)
            self._lock = _lock_file(self.path)
            if maintenance and not self.path.is_file():
                self._lock.close()
                raise StorageUnavailable("Maintenance requires an existing retained file")
        except (OSError, ValueError) as error:
            raise StorageUnavailable("Local storage is unavailable or already owned") from error
        self._engine = create_engine(
            URL.create("sqlite+pysqlite", database=str(self.path)),
            connect_args={"autocommit": False, "check_same_thread": False, "timeout": 1.0},
            poolclass=NullPool,
        )
        event.listen(self._engine, "connect", _configure)
        try:
            existed = self.path.exists()
            with self._engine.begin() as connection:
                if maintenance and connection.scalar(select(deployment.c.schema_version)) != 5:
                    raise ValueError("Maintenance requires the current retained schema")
                self.deployment = initialize(connection, deployment_id, existed)
        except (SQLAlchemyError, OSError, ValueError) as error:
            self._close()
            raise StorageUnavailable("Retained storage cannot be opened safely") from error

    async def transaction[T](self, action: Callable[[Connection], T]) -> T:
        """Commit the callback atomically, or roll it back on any exception."""
        return await asyncio.to_thread(self._transaction, action)

    def _transaction[T](self, action: Callable[[Connection], T]) -> T:
        with self._mutex:
            if self._closed:
                raise StorageUnavailable("Database lifetime is closed")
            try:
                with self._engine.begin() as connection:
                    return action(connection)
            except (SQLAlchemyError, sqlite3.Error, OSError) as error:
                raise StorageUnavailable("Retained transaction unavailable") from error

    async def close(self) -> None:
        await asyncio.to_thread(self._close)

    def _close(self) -> None:
        with self._mutex:
            if not self._closed:
                self._closed = True
                try:
                    self._engine.dispose()
                finally:
                    self._lock.close()
