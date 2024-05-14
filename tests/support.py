"""Opening a database for a test.

Every test that touches storage comes through here, so the journal mode is
decided in one place rather than in thirty fixtures.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from arc.storage.schema import connect, migrate

__all__ = ["open_test_database"]


def open_test_database(path: Path | str) -> sqlite3.Connection:
    """A migrated database that is not expected to survive anything."""
    connection = connect(path, journal_mode="memory")
    migrate(connection)
    return connection
