"""
ThreadMetaStore: manages the `thread_meta` table in the shared SQLite database.

This table stores lightweight metadata about each chat thread so that
GET /threads can return a list of threads without reading the full
LangGraph checkpoint store.
"""

from __future__ import annotations

import aiosqlite


class ThreadMetaStore:
    """
    Thin async wrapper around the `thread_meta` SQLite table.

    Parameters
    ----------
    conn:
        An open ``aiosqlite.Connection``. The caller (lifespan handler) owns
        the connection lifetime; this class never closes it.
    """

    _MAX_FIRST_MESSAGE_LEN = 500

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    # ------------------------------------------------------------------
    # DDL
    # ------------------------------------------------------------------

    async def ensure_table(self) -> None:
        """
        Create the ``thread_meta`` table if it does not already exist.

        Schema::

            thread_id           TEXT PRIMARY KEY
            created_at          TEXT NOT NULL   -- ISO-8601 UTC timestamp
            first_human_message TEXT NOT NULL   -- plain text, max 500 chars
        """
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS thread_meta (
                thread_id           TEXT PRIMARY KEY,
                created_at          TEXT NOT NULL,
                first_human_message TEXT NOT NULL
            )
            """
        )
        await self._conn.commit()

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def insert(
        self,
        thread_id: str,
        created_at: str,
        first_human_message: str,
    ) -> None:
        """
        Insert a new row into ``thread_meta``.

        ``first_human_message`` is silently truncated to
        :attr:`_MAX_FIRST_MESSAGE_LEN` characters before storage.

        Parameters
        ----------
        thread_id:
            UUID string identifying the thread.
        created_at:
            ISO-8601 UTC timestamp string (e.g. ``"2025-01-15T10:30:00Z"``).
        first_human_message:
            Plain-text content of the first human message in the thread.
        """
        truncated = first_human_message[: self._MAX_FIRST_MESSAGE_LEN]
        await self._conn.execute(
            """
            INSERT INTO thread_meta (thread_id, created_at, first_human_message)
            VALUES (?, ?, ?)
            """,
            (thread_id, created_at, truncated),
        )
        await self._conn.commit()

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def list_threads(self, limit: int = 100) -> list[dict]:
        """
        Return thread metadata rows ordered by ``created_at`` descending.

        Parameters
        ----------
        limit:
            Maximum number of rows to return. Defaults to 100.

        Returns
        -------
        list[dict]
            Each dict has keys ``thread_id``, ``created_at``, and
            ``first_human_message``.
        """
        async with self._conn.execute(
            """
            SELECT thread_id, created_at, first_human_message
            FROM thread_meta
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()

        return [
            {
                "thread_id": row[0],
                "created_at": row[1],
                "first_human_message": row[2],
            }
            for row in rows
        ]

    async def get_thread(self, thread_id: str) -> dict | None:
        """
        Fetch a single thread row by its ``thread_id``.

        Parameters
        ----------
        thread_id:
            UUID string identifying the thread.

        Returns
        -------
        dict | None
            Dict with keys ``thread_id``, ``created_at``, and
            ``first_human_message``, or ``None`` if no matching row exists.
        """
        async with self._conn.execute(
            """
            SELECT thread_id, created_at, first_human_message
            FROM thread_meta
            WHERE thread_id = ?
            """,
            (thread_id,),
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            return None

        return {
            "thread_id": row[0],
            "created_at": row[1],
            "first_human_message": row[2],
        }
