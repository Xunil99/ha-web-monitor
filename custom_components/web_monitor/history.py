"""SQLite history store for Web Monitor."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import aiosqlite

_LOGGER = logging.getLogger(__name__)


class HistoryStore:
    """Async SQLite store for scraping history."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def async_setup(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                monitor_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                value TEXT,
                previous_value TEXT,
                changed INTEGER DEFAULT 0,
                screenshot_path TEXT
            )
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_readings_monitor
            ON readings (monitor_id, timestamp DESC)
        """)
        await self._db.commit()

    async def add_reading(
        self,
        monitor_id: str,
        value: str | None,
        previous_value: str | None = None,
        changed: bool = False,
        screenshot_path: str | None = None,
    ) -> None:
        await self._db.execute(
            """INSERT INTO readings (monitor_id, timestamp, value, previous_value, changed, screenshot_path)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (monitor_id, datetime.utcnow().isoformat(), value, previous_value, int(changed), screenshot_path),
        )
        await self._db.commit()

    async def get_readings(self, monitor_id: str, limit: int = 100) -> list[dict]:
        cursor = await self._db.execute(
            """SELECT * FROM readings WHERE monitor_id = ?
               ORDER BY timestamp DESC LIMIT ?""",
            (monitor_id, limit),
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": row["id"],
                "monitor_id": row["monitor_id"],
                "timestamp": row["timestamp"],
                "value": row["value"],
                "previous_value": row["previous_value"],
                "changed": bool(row["changed"]),
                "screenshot_path": row["screenshot_path"],
            }
            for row in rows
        ]

    async def get_reading_count(self, monitor_id: str) -> int:
        cursor = await self._db.execute(
            "SELECT COUNT(*) as cnt FROM readings WHERE monitor_id = ?",
            (monitor_id,),
        )
        row = await cursor.fetchone()
        return row["cnt"]

    async def clear_readings(self, monitor_id: str) -> None:
        await self._db.execute(
            "DELETE FROM readings WHERE monitor_id = ?", (monitor_id,)
        )
        await self._db.commit()

    async def cleanup_older_than(self, days: int) -> int:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        cursor = await self._db.execute(
            "DELETE FROM readings WHERE timestamp < ?", (cutoff,)
        )
        await self._db.commit()
        return cursor.rowcount

    async def async_close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None
