# SPDX-License-Identifier: AGPL-3.0-only
"""Append-only SQLite storage for the local, synthetic demonstration."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from farmcredit.application.saved_assessments import POLICY_VERSION, SavedAssessment
from farmcredit.domain.review import AdvisoryReview, ReviewRequest, validate_review


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

                CREATE TABLE IF NOT EXISTS case_state (
                    case_id TEXT PRIMARY KEY, fingerprint TEXT, revision INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS advisory_reviews (
                    operation_id TEXT PRIMARY KEY, assessment_id TEXT NOT NULL UNIQUE,
                    case_revision INTEGER NOT NULL, decision TEXT NOT NULL, note TEXT NOT NULL,
                    officer_id TEXT NOT NULL, officer_name TEXT NOT NULL, reviewed_at TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS reviews_no_update
                BEFORE UPDATE ON advisory_reviews BEGIN
                    SELECT RAISE(ABORT, 'Reviews are immutable');
                END;
                CREATE TRIGGER IF NOT EXISTS reviews_no_delete
                BEFORE DELETE ON advisory_reviews BEGIN
                    SELECT RAISE(ABORT, 'Reviews are immutable');
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

    def record_current_inputs(self, case_id: str, fingerprint: str | None) -> int:
        """Publish a submitted case state; invalid submissions invalidate approval."""
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT * FROM case_state WHERE case_id = ?",
                (case_id,),
            ).fetchone()
            if current and current["fingerprint"] == fingerprint:
                return current["revision"]
            revision = current["revision"] + 1 if current else 1
            connection.execute(
                "INSERT INTO case_state VALUES (?, ?, ?) ON CONFLICT(case_id) "
                "DO UPDATE SET fingerprint=excluded.fingerprint, revision=excluded.revision",
                (case_id, fingerprint, revision),
            )
            return revision

    def review_context(self, assessment_id: str) -> dict:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT a.snapshot_json, s.fingerprint, COALESCE(s.revision, 0) AS revision,
                    a.version = (SELECT MAX(version) FROM assessments WHERE case_id=a.case_id) AS latest
                FROM assessments a LEFT JOIN case_state s ON s.case_id=a.case_id
                WHERE a.assessment_id=?
            """,
                (assessment_id,),
            ).fetchone()
            review = connection.execute(
                "SELECT * FROM advisory_reviews WHERE assessment_id=?",
                (assessment_id,),
            ).fetchone()
            if row is None:
                raise ValueError("Saved assessment not found.")
            snapshot = json.loads(row["snapshot_json"])
            saved_fingerprint = snapshot["input_fingerprint"]
            policy_current = snapshot.get("inputs", {}).get("policy_version") == POLICY_VERSION
            current = (
                bool(row["latest"]) and row["fingerprint"] == saved_fingerprint and policy_current
            )
            return {
                "revision": row["revision"],
                "current": current,
                "review": AdvisoryReview(**dict(review)) if review else None,
                "review_current": bool(review)
                and current
                and review["case_revision"] == row["revision"],
            }

    def review(self, request: ReviewRequest) -> AdvisoryReview:
        with self._connection() as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            prior = connection.execute(
                "SELECT * FROM advisory_reviews WHERE operation_id=?",
                (request.operation_id,),
            ).fetchone()
            if prior:
                if (
                    prior["assessment_id"],
                    prior["decision"],
                    prior["note"],
                    prior["officer_id"],
                ) != (
                    request.assessment_id,
                    request.decision,
                    request.note,
                    request.officer.user_id,
                ):
                    raise ValueError("Conflicting review retry.")
                if not request.officer.may_review or not request.officer.name.strip():
                    raise ValueError("A named, authorised officer must review the advisory.")
                return AdvisoryReview(**dict(prior))
            assessment = connection.execute(
                "SELECT * FROM assessments WHERE assessment_id=?",
                (request.assessment_id,),
            ).fetchone()
            if assessment is None:
                raise ValueError("Saved assessment not found.")
            state = connection.execute(
                "SELECT * FROM case_state WHERE case_id=?",
                (assessment["case_id"],),
            ).fetchone()
            latest = connection.execute(
                "SELECT MAX(version) FROM assessments WHERE case_id=?",
                (assessment["case_id"],),
            ).fetchone()[0]
            existing = connection.execute(
                "SELECT 1 FROM advisory_reviews WHERE assessment_id=?",
                (request.assessment_id,),
            ).fetchone()
            policy_current = (
                json.loads(assessment["snapshot_json"]).get("inputs", {}).get("policy_version")
                == POLICY_VERSION
            )
            validate_review(
                request,
                latest=assessment["version"] == latest and policy_current,
                saved_fingerprint=json.loads(assessment["snapshot_json"])["input_fingerprint"],
                current_fingerprint=state["fingerprint"] if state else None,
                current_revision=state["revision"] if state else 0,
                already_reviewed=bool(existing),
            )
            review = AdvisoryReview(
                request.operation_id,
                request.assessment_id,
                state["revision"],
                request.decision,
                request.note,
                request.officer.user_id,
                request.officer.name,
                datetime.now(timezone.utc).isoformat(),
            )
            connection.execute(
                "INSERT INTO advisory_reviews VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    review.operation_id,
                    review.assessment_id,
                    review.case_revision,
                    review.decision,
                    review.note,
                    review.officer_id,
                    review.officer_name,
                    review.reviewed_at,
                ),
            )
            return review
