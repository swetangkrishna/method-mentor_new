"""
database.py

SQLite database for the pedagogical RL experiment.
Stores every session, every turn, every skill use, and every survey response.

Tables:
  sessions       — one row per episode (automated or human)
  turns          — one row per agent/learner turn
  skill_uses     — one row per skill invocation (FK → turns)
  survey_responses — one row per survey question answer (FK → sessions)
  rewards        — one row per completed episode reward breakdown

All writes go through this module. Nothing else touches the DB directly.

Usage:
    db = Database()              # opens/creates pedagogy_rl.db
    session_id = db.create_session(...)
    turn_id    = db.log_turn(...)
    db.log_skill_use(...)
    db.log_survey(...)
    db.log_reward(...)
    db.close()
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).parent / "db" / "pedagogy_rl.db"


class Database:
    def __init__(self, db_path: Path = DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")  # safe for concurrent Flask + runner
        self._create_tables()
        print(f"[db] Connected to {db_path}")

    # ── Schema ────────────────────────────────────────────────────────────────

    def _create_tables(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id              TEXT PRIMARY KEY,
            scenario_id     TEXT NOT NULL,
            scenario_topic  TEXT,
            mode            TEXT NOT NULL DEFAULT 'automated',  -- 'automated' | 'human_validation'
            backend         TEXT,          -- 'huggingface' | 'ollama' | 'anthropic'
            model           TEXT,          -- model name used
            status          TEXT DEFAULT 'running',  -- 'running' | 'completed' | 'abandoned'
            task_solved     INTEGER DEFAULT 0,
            max_turns       INTEGER,
            total_turns     INTEGER DEFAULT 0,
            started_at      TEXT NOT NULL,
            ended_at        TEXT,
            persona_name    TEXT,
            notes           TEXT
        );

        CREATE TABLE IF NOT EXISTS turns (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT NOT NULL REFERENCES sessions(id),
            turn_number     INTEGER NOT NULL,
            speaker         TEXT NOT NULL,   -- 'agent' | 'persona' | 'human'
            message         TEXT NOT NULL,
            understanding_level INTEGER,     -- 0-10, persona only
            learner_ready   INTEGER DEFAULT 0,
            agent_declared_solved INTEGER DEFAULT 0,
            timestamp       TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS skill_uses (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT NOT NULL REFERENCES sessions(id),
            turn_id         INTEGER REFERENCES turns(id),
            turn_number     INTEGER NOT NULL,
            skill_name      TEXT NOT NULL,
            reasoning       TEXT,
            timestamp       TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS survey_responses (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT NOT NULL REFERENCES sessions(id),
            question_id     TEXT NOT NULL,   -- 'Q1' .. 'Q5' | 'Q_open'
            score           INTEGER,         -- NULL for open text
            comment         TEXT,
            respondent_type TEXT DEFAULT 'persona',  -- 'persona' | 'human'
            timestamp       TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rewards (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id              TEXT NOT NULL REFERENCES sessions(id),
            total_reward            REAL NOT NULL,
            reward_band             TEXT,
            task_solved_score       REAL,
            survey_score_normalised REAL,
            survey_score_raw_mean   REAL,
            efficiency_score        REAL,
            turns_used              INTEGER,
            max_turns               INTEGER,
            weight_task             REAL,
            weight_survey           REAL,
            weight_efficiency       REAL,
            timestamp               TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_turns_session    ON turns(session_id);
        CREATE INDEX IF NOT EXISTS idx_skill_session    ON skill_uses(session_id);
        CREATE INDEX IF NOT EXISTS idx_survey_session   ON survey_responses(session_id);
        CREATE INDEX IF NOT EXISTS idx_skill_name       ON skill_uses(skill_name);
        """)
        self.conn.commit()

    # ── Sessions ──────────────────────────────────────────────────────────────

    def create_session(
        self,
        session_id: str,
        scenario_id: str,
        scenario_topic: str,
        mode: str,
        backend: str,
        model: str,
        max_turns: int,
        persona_name: str = "",
        notes: str = "",
    ) -> str:
        self.conn.execute("""
            INSERT INTO sessions
              (id, scenario_id, scenario_topic, mode, backend, model,
               max_turns, started_at, persona_name, notes, status)
            VALUES (?,?,?,?,?,?,?,?,?,?,'running')
        """, (session_id, scenario_id, scenario_topic, mode, backend, model,
              max_turns, _now(), persona_name, notes))
        self.conn.commit()
        return session_id

    def complete_session(self, session_id: str, task_solved: bool, total_turns: int):
        self.conn.execute("""
            UPDATE sessions SET status='completed', task_solved=?, total_turns=?, ended_at=?
            WHERE id=?
        """, (int(task_solved), total_turns, _now(), session_id))
        self.conn.commit()

    def get_session(self, session_id: str) -> Optional[Dict]:
        row = self.conn.execute(
            "SELECT * FROM sessions WHERE id=?", (session_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_sessions(self, scenario_id: str = None, mode: str = None) -> List[Dict]:
        q = "SELECT * FROM sessions WHERE 1=1"
        params = []
        if scenario_id: q += " AND scenario_id=?"; params.append(scenario_id)
        if mode:        q += " AND mode=?";        params.append(mode)
        q += " ORDER BY started_at DESC"
        return [dict(r) for r in self.conn.execute(q, params).fetchall()]

    # ── Turns ─────────────────────────────────────────────────────────────────

    def log_turn(
        self,
        session_id: str,
        turn_number: int,
        speaker: str,
        message: str,
        understanding_level: int = None,
        learner_ready: bool = False,
        agent_declared_solved: bool = False,
    ) -> int:
        cur = self.conn.execute("""
            INSERT INTO turns
              (session_id, turn_number, speaker, message,
               understanding_level, learner_ready, agent_declared_solved, timestamp)
            VALUES (?,?,?,?,?,?,?,?)
        """, (session_id, turn_number, speaker, message,
              understanding_level, int(learner_ready),
              int(agent_declared_solved), _now()))
        self.conn.commit()
        return cur.lastrowid

    def get_turns(self, session_id: str) -> List[Dict]:
        rows = self.conn.execute(
            "SELECT * FROM turns WHERE session_id=? ORDER BY turn_number, id",
            (session_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Skill uses ────────────────────────────────────────────────────────────

    def log_skill_use(
        self,
        session_id: str,
        turn_id: int,
        turn_number: int,
        skill_name: str,
        reasoning: str = "",
    ):
        self.conn.execute("""
            INSERT INTO skill_uses
              (session_id, turn_id, turn_number, skill_name, reasoning, timestamp)
            VALUES (?,?,?,?,?,?)
        """, (session_id, turn_id, turn_number, skill_name, reasoning, _now()))
        self.conn.commit()

    def get_skill_uses(self, session_id: str) -> List[Dict]:
        rows = self.conn.execute(
            "SELECT * FROM skill_uses WHERE session_id=? ORDER BY turn_number",
            (session_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def skill_frequency(self, scenario_id: str = None) -> List[Dict]:
        """Return skill usage counts across all (or one) scenario."""
        q = """
            SELECT su.skill_name, COUNT(*) as uses,
                   AVG(r.total_reward) as avg_reward
            FROM skill_uses su
            JOIN sessions s ON su.session_id = s.id
            LEFT JOIN rewards r ON r.session_id = s.id
            WHERE s.status = 'completed'
        """
        params = []
        if scenario_id:
            q += " AND s.scenario_id = ?"; params.append(scenario_id)
        q += " GROUP BY su.skill_name ORDER BY uses DESC"
        return [dict(r) for r in self.conn.execute(q, params).fetchall()]

    def skill_sequence_for_session(self, session_id: str) -> List[str]:
        rows = self.conn.execute(
            "SELECT skill_name FROM skill_uses WHERE session_id=? ORDER BY turn_number",
            (session_id,)
        ).fetchall()
        return [r["skill_name"] for r in rows]

    # ── Survey ────────────────────────────────────────────────────────────────

    def log_survey(
        self,
        session_id: str,
        survey_data: Dict,
        respondent_type: str = "persona",
    ):
        """Persist survey answers.

        Preferred format::
            {"Q1": {"score": 4, "comment": ""},
             "Q_open": {"score": None, "comment": "Helpful"}}

        Scalar numeric and string values are accepted for backward compatibility.
        """
        ts = _now()
        for q_id, data in survey_data.items():
            if isinstance(data, dict):
                score = data.get("score")
                comment = data.get("comment", "")
            elif isinstance(data, (int, float)) and not isinstance(data, bool):
                score = data
                comment = ""
            elif isinstance(data, str):
                score = None
                comment = data
            elif data is None:
                score = None
                comment = ""
            else:
                score = None
                comment = str(data)

            self.conn.execute("""
                INSERT INTO survey_responses
                  (session_id, question_id, score, comment, respondent_type, timestamp)
                VALUES (?,?,?,?,?,?)
            """, (session_id, q_id, score, comment, respondent_type, ts))
        self.conn.commit()

    def get_survey(self, session_id: str) -> Dict:
        rows = self.conn.execute(
            "SELECT * FROM survey_responses WHERE session_id=? ORDER BY question_id",
            (session_id,)
        ).fetchall()
        result = {}
        for r in rows:
            result[r["question_id"]] = {"score": r["score"], "comment": r["comment"]}
        return result

    def survey_mean(self, session_id: str) -> Optional[float]:
        row = self.conn.execute("""
            SELECT AVG(score) as mean FROM survey_responses
            WHERE session_id=? AND question_id != 'Q_open' AND score IS NOT NULL
        """, (session_id,)).fetchone()
        return round(row["mean"], 2) if row and row["mean"] is not None else None

    # ── Rewards ───────────────────────────────────────────────────────────────

    def log_reward(self, session_id: str, reward_data: Dict):
        c = reward_data.get("components", {})
        self.conn.execute("""
            INSERT INTO rewards
              (session_id, total_reward, reward_band, task_solved_score,
               survey_score_normalised, survey_score_raw_mean, efficiency_score,
               turns_used, max_turns, weight_task, weight_survey, weight_efficiency,
               timestamp)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            session_id,
            reward_data["reward"],
            reward_data.get("reward_band", ""),
            c.get("task_solved_score"),
            c.get("survey_score_normalised"),
            c.get("survey_score_raw_mean"),
            c.get("efficiency_score"),
            reward_data.get("turns_used"),
            reward_data.get("max_turns"),
            reward_data.get("weights", {}).get("task_solved"),
            reward_data.get("weights", {}).get("survey_score"),
            reward_data.get("weights", {}).get("efficiency"),
            _now(),
        ))
        self.conn.commit()

    def get_reward(self, session_id: str) -> Optional[Dict]:
        row = self.conn.execute(
            "SELECT * FROM rewards WHERE session_id=?", (session_id,)
        ).fetchone()
        return dict(row) if row else None

    # ── Analytics queries ─────────────────────────────────────────────────────

    def best_skill_per_turn_position(self, scenario_id: str = None) -> Dict[int, Dict]:
        """For each turn position, which skill had the highest mean reward?"""
        q = """
            SELECT su.turn_number, su.skill_name,
                   AVG(r.total_reward) as mean_reward,
                   COUNT(*) as n
            FROM skill_uses su
            JOIN sessions s  ON su.session_id = s.id
            JOIN rewards r   ON r.session_id  = s.id
            WHERE s.status = 'completed'
        """
        params = []
        if scenario_id:
            q += " AND s.scenario_id=?"; params.append(scenario_id)
        q += " GROUP BY su.turn_number, su.skill_name ORDER BY su.turn_number, mean_reward DESC"

        rows = self.conn.execute(q, params).fetchall()
        policy = {}
        for r in rows:
            pos = r["turn_number"]
            if pos not in policy:  # first row per position = highest reward
                policy[pos] = {
                    "skill_name":   r["skill_name"],
                    "mean_reward":  round(r["mean_reward"], 3),
                    "n":            r["n"],
                }
        return policy

    def session_summary_table(self) -> List[Dict]:
        rows = self.conn.execute("""
            SELECT s.id, s.scenario_id, s.mode, s.task_solved, s.total_turns,
                   s.model, s.backend, s.started_at,
                   r.total_reward, r.reward_band,
                   sr.mean_survey
            FROM sessions s
            LEFT JOIN rewards r ON r.session_id = s.id
            LEFT JOIN (
                SELECT session_id, AVG(score) as mean_survey
                FROM survey_responses
                WHERE question_id != 'Q_open' AND score IS NOT NULL
                GROUP BY session_id
            ) sr ON sr.session_id = s.id
            WHERE s.status = 'completed'
            ORDER BY r.total_reward DESC
        """).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self.conn.close()


# ── Helper ────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


# ── CLI inspection ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    db = Database()
    sessions = db.list_sessions()
    print(f"Sessions in DB: {len(sessions)}")
    for s in sessions[:5]:
        print(f"  {s['id']}  {s['scenario_id']}  {s['mode']}  solved={s['task_solved']}")

    skill_freq = db.skill_frequency()
    print(f"\nTop skills by usage:")
    for sf in skill_freq[:8]:
        avg = f"{sf['avg_reward']:.3f}" if sf['avg_reward'] else "—"
        print(f"  {sf['skill_name']:45s}  uses={sf['uses']}  avg_reward={avg}")
    db.close()
