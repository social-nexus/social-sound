"""Persistent narration queue and duration-aware text segmentation.

This module is deliberately independent from any TTS engine. It stores jobs and
review candidates so the API/worker can use one engine at a time and only publish
a regenerated part after explicit approval.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any


def split_for_duration(text: str, target_seconds: int = 60,
                       chars_per_minute: int = 850) -> list[str]:
    """Split at paragraph/sentence boundaries, estimating spoken duration.

    The estimate is a planning aid, not a promise: actual speech rate varies by
    engine, voice and punctuation. Long sentences are split only at word edges.
    """
    clean = " ".join((text or "").replace("\r", "").split())
    if not clean:
        return []
    if not 15 <= target_seconds <= 300:
        raise ValueError("target_seconds must be between 15 and 300")
    if not 300 <= chars_per_minute <= 1500:
        raise ValueError("chars_per_minute must be between 300 and 1500")

    target_chars = max(1, round(chars_per_minute * target_seconds / 60))
    # Prefer full sentences; preserve punctuation and never split a word.
    sentences = []
    import re
    for paragraph in re.split(r"\n\s*\n+", (text or "").strip()):
        paragraph = " ".join(paragraph.split())
        if not paragraph:
            continue
        found = re.findall(r".+?(?:[.!?…]+(?:[”’\"')\]]*)?(?=\s|$)|$)", paragraph)
        sentences.extend(s.strip() for s in found if s.strip())
    if not sentences:
        sentences = [clean]

    units: list[str] = []
    for sentence in sentences:
        if len(sentence) <= target_chars:
            units.append(sentence)
            continue
        # A single unusually long sentence: split at word boundaries.
        words = sentence.split()
        part = ""
        for word in words:
            candidate = f"{part} {word}".strip()
            if part and len(candidate) > target_chars:
                units.append(part)
                part = word
            else:
                part = candidate
        if part:
            units.append(part)

    chunks: list[str] = []
    current = ""
    for unit in units:
        candidate = f"{current} {unit}".strip()
        if current and len(candidate) > target_chars:
            chunks.append(current)
            current = unit
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


class NarrationQueue:
    """SQLite-backed sequential queue with explicit regeneration approval."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS narration_jobs (
                    id TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    voice TEXT NOT NULL,
                    engine TEXT NOT NULL,
                    settings_json TEXT NOT NULL,
                    parts_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    error TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_narration_jobs_queue
                    ON narration_jobs(status, created_at);
                CREATE TABLE IF NOT EXISTS narration_candidates (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES narration_jobs(id) ON DELETE CASCADE,
                    part_index INTEGER NOT NULL,
                    audio_path TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'awaiting_approval',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)

    def enqueue(self, text: str, voice: str, engine: str,
                parts: list[str], settings: dict[str, Any] | None = None) -> dict:
        if not text.strip() or not parts:
            raise ValueError("A non-empty narration and at least one part are required")
        job_id = str(uuid.uuid4())
        with self._connect() as db:
            db.execute(
                """INSERT INTO narration_jobs
                   (id,text,voice,engine,settings_json,parts_json,status)
                   VALUES(?,?,?,?,?,?, 'queued')""",
                (job_id, text, voice, engine,
                 json.dumps(settings or {}, ensure_ascii=False),
                 json.dumps([{"text": p, "status": "pending", "audio_path": None}
                             for p in parts], ensure_ascii=False))
            )
        return self.get(job_id)

    def get(self, job_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM narration_jobs WHERE id=?", (job_id,)).fetchone()
        return self._row_dict(row) if row else None

    def list_jobs(self) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM narration_jobs ORDER BY created_at, rowid"
            ).fetchall()
        return [self._row_dict(row) for row in rows]

    @staticmethod
    def _row_dict(row):
        item = dict(row)
        item["settings"] = json.loads(item.pop("settings_json"))
        item["parts"] = json.loads(item.pop("parts_json"))
        return item

    def claim_next(self) -> dict | None:
        """Atomically claim one queued job; only one worker should call this."""
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            active = db.execute(
                "SELECT 1 FROM narration_jobs WHERE status='processing' LIMIT 1"
            ).fetchone()
            if active is not None:
                db.commit()
                return None
            row = db.execute(
                "SELECT * FROM narration_jobs WHERE status='queued' "
                "ORDER BY created_at, rowid LIMIT 1"
            ).fetchone()
            if row is None:
                db.commit()
                return None
            changed = db.execute(
                "UPDATE narration_jobs SET status='processing', updated_at=CURRENT_TIMESTAMP "
                "WHERE id=? AND status='queued'", (row["id"],)
            ).rowcount
            db.commit()
            return self.get(row["id"]) if changed else None

    def update_part(self, job_id: str, part_index: int, **changes) -> dict:
        allowed = {"status", "audio_path"}
        if set(changes) - allowed:
            raise ValueError("Unsupported part fields")
        with self._connect() as db:
            row = db.execute("SELECT parts_json FROM narration_jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            parts = json.loads(row["parts_json"])
            if not 0 <= part_index < len(parts):
                raise IndexError(part_index)
            parts[part_index].update(changes)
            db.execute(
                "UPDATE narration_jobs SET parts_json=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (json.dumps(parts, ensure_ascii=False), job_id)
            )
        return self.get(job_id)

    def finish(self, job_id: str, error: str | None = None) -> dict:
        with self._connect() as db:
            db.execute(
                "UPDATE narration_jobs SET status=?, error=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                ("failed" if error else "completed", error, job_id)
            )
        return self.get(job_id)

    def recover_interrupted(self) -> int:
        """Mark jobs left running at shutdown; queued jobs remain queued."""
        with self._connect() as db:
            cur = db.execute(
                "UPDATE narration_jobs SET status='interrupted', "
                "updated_at=CURRENT_TIMESTAMP WHERE status='processing'"
            )
            return cur.rowcount

    def requeue(self, job_id: str) -> dict:
        with self._connect() as db:
            cur = db.execute(
                "UPDATE narration_jobs SET status='queued', error=NULL, "
                "updated_at=CURRENT_TIMESTAMP WHERE id=? AND status IN ('interrupted','failed')",
                (job_id,)
            )
            if not cur.rowcount:
                raise ValueError("Only interrupted or failed jobs can be requeued")
        return self.get(job_id)

    def stage_candidate(self, job_id: str, part_index: int, audio_path: str) -> str:
        job = self.get(job_id)
        if job is None:
            raise KeyError(job_id)
        if not 0 <= part_index < len(job["parts"]):
            raise IndexError(part_index)
        candidate_id = str(uuid.uuid4())
        with self._connect() as db:
            db.execute(
                "INSERT INTO narration_candidates(id,job_id,part_index,audio_path) VALUES(?,?,?,?)",
                (candidate_id, job_id, part_index, audio_path)
            )
        return candidate_id

    def candidate(self, candidate_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM narration_candidates WHERE id=?", (candidate_id,)).fetchone()
        return dict(row) if row else None

    def approve_candidate(self, candidate_id: str) -> dict:
        """Publish candidate path in job metadata only after explicit approval."""
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM narration_candidates WHERE id=? AND status='awaiting_approval'",
                (candidate_id,)
            ).fetchone()
            if row is None:
                raise KeyError(candidate_id)
            job_row = db.execute(
                "SELECT parts_json FROM narration_jobs WHERE id=?", (row["job_id"],)
            ).fetchone()
            parts = json.loads(job_row["parts_json"])
            parts[row["part_index"]]["audio_path"] = row["audio_path"]
            parts[row["part_index"]]["status"] = "approved"
            db.execute(
                "UPDATE narration_jobs SET parts_json=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (json.dumps(parts, ensure_ascii=False), row["job_id"])
            )
            db.execute(
                "UPDATE narration_candidates SET status='approved' WHERE id=?", (candidate_id,)
            )
            db.commit()
        return self.get(row["job_id"])

    def discard_candidate(self, candidate_id: str) -> None:
        with self._connect() as db:
            cur = db.execute(
                "UPDATE narration_candidates SET status='discarded' "
                "WHERE id=? AND status='awaiting_approval'", (candidate_id,)
            )
            if not cur.rowcount:
                raise KeyError(candidate_id)
