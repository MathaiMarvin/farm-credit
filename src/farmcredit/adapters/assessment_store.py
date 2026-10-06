# SPDX-License-Identifier: AGPL-3.0-only
"""Append-only SQLite storage for the local, synthetic demonstration."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from farmcredit.application.saved_assessments import SavedAssessment


class AssessmentStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    @contextmanager
    def _connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS assessments (
                    assessment_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    saved_at TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    UNIQUE(case_id, version)
                );
                CREATE TRIGGER IF NOT EXISTS assessments_no_update
                BEFORE UPDATE ON assessments BEGIN
                    SELECT RAISE(ABORT, 'Assessments are immutable');
                END;
                CREATE TRIGGER IF NOT EXISTS assessments_no_delete
                BEFORE DELETE ON assessments BEGIN
                    SELECT RAISE(ABORT, 'Assessments are immutable');
                END;
            """)
            yield connection
        finally:
            connection.close()

    def save(self, snapshot_json: str, operation_id: str) -> SavedAssessment:
        case_id = json.loads(snapshot_json)["case_id"]
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM assessments WHERE assessment_id = ?",
                (operation_id,),
            ).fetchone()
            if existing:
                if existing["snapshot_json"] != snapshot_json:
                    raise ValueError(
                        "This save identifier already belongs to a different snapshot."
                    )
                return SavedAssessment(**dict(existing))
            version = connection.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM assessments WHERE case_id = ?",
                (case_id,),
            ).fetchone()[0]
            saved = SavedAssessment(
                operation_id,
                case_id,
                version,
                datetime.now(timezone.utc).isoformat(),
                snapshot_json,
            )
            connection.execute(
                "INSERT INTO assessments VALUES (?, ?, ?, ?, ?)",
                (
                    saved.assessment_id,
                    saved.case_id,
                    saved.version,
                    saved.saved_at,
                    saved.snapshot_json,
                ),
            )
            return saved

    def get(self, assessment_id: str) -> SavedAssessment | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM assessments WHERE assessment_id = ?",
                (assessment_id,),
            ).fetchone()
            return SavedAssessment(**dict(row)) if row else None

    def history(self, case_id: str) -> tuple[SavedAssessment, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM assessments WHERE case_id = ? ORDER BY version DESC",
                (case_id,),
            ).fetchall()
            return tuple(SavedAssessment(**dict(row)) for row in rows)
