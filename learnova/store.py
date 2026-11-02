"""SQLite persistence for lessons, answers, tutoring decisions and plans."""

import json
import sqlite3
from datetime import datetime, timezone

from .schemas import LessonAnalysis, TutoringPlan

SCHEMA = """
CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student TEXT NOT NULL,
    language TEXT NOT NULL,
    topic TEXT NOT NULL,
    lesson_text TEXT NOT NULL,
    analysis_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id INTEGER NOT NULL REFERENCES lessons(id),
    phase TEXT NOT NULL CHECK (phase IN ('quiz_a', 'practice', 'quiz_b')),
    concept_id TEXT NOT NULL,
    question TEXT NOT NULL,
    chosen TEXT,
    correct INTEGER NOT NULL,
    round INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id INTEGER NOT NULL REFERENCES lessons(id),
    concept_id TEXT NOT NULL,
    difficulty INTEGER NOT NULL,
    reason TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str = "learnova.db"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    # Lessons
    def create_lesson(self, student: str, language: str, lesson_text: str, analysis: LessonAnalysis) -> int:
        cur = self.conn.execute(
            "INSERT INTO lessons (student, language, topic, lesson_text, analysis_json, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (student, language, analysis.topic, lesson_text, analysis.model_dump_json(), _now()),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_lesson(self, lesson_id: int) -> tuple[sqlite3.Row, LessonAnalysis]:
        row = self.conn.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
        if row is None:
            raise KeyError(f"No lesson {lesson_id}")
        return row, LessonAnalysis.model_validate_json(row["analysis_json"])

    def update_analysis(self, lesson_id: int, analysis: LessonAnalysis) -> None:
        self.conn.execute("UPDATE lessons SET analysis_json = ? WHERE id = ?",
                          (analysis.model_dump_json(), lesson_id))
        self.conn.commit()

    # Attempts
    def record_attempt(self, lesson_id: int, phase: str, concept_id: str, question: str,
                       chosen: str | None, correct: bool, round_no: int = 0) -> None:
        self.conn.execute(
            "INSERT INTO attempts (lesson_id, phase, concept_id, question, chosen, correct, round, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (lesson_id, phase, concept_id, question, chosen, int(correct), round_no, _now()),
        )
        self.conn.commit()

    def attempts(self, lesson_id: int, phase: str | None = None) -> list[sqlite3.Row]:
        if phase:
            return self.conn.execute(
                "SELECT * FROM attempts WHERE lesson_id = ? AND phase = ? ORDER BY id", (lesson_id, phase)
            ).fetchall()
        return self.conn.execute("SELECT * FROM attempts WHERE lesson_id = ? ORDER BY id", (lesson_id,)).fetchall()

    # Tutoring decisions
    def record_decision(self, lesson_id: int, concept_id: str, difficulty: int, reason: str,
                        plan: TutoringPlan) -> int:
        cur = self.conn.execute(
            "INSERT INTO decisions (lesson_id, concept_id, difficulty, reason, plan_json, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (lesson_id, concept_id, difficulty, reason, plan.model_dump_json(), _now()),
        )
        self.conn.commit()
        return cur.lastrowid

    def decisions(self, lesson_id: int) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM decisions WHERE lesson_id = ? ORDER BY id", (lesson_id,)).fetchall()

    def latest_plan(self, lesson_id: int) -> tuple[sqlite3.Row, TutoringPlan] | None:
        rows = self.decisions(lesson_id)
        if not rows:
            return None
        return rows[-1], TutoringPlan.model_validate(json.loads(rows[-1]["plan_json"]))
