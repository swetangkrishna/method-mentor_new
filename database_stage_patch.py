"""
database_stage_patch.py — Stage-logging support for the existing Database class.

The 6-stage integration calls `db.log_stage(...)` once per agent turn. The main
run_experiment.py wraps this call in a try/except, so the experiment runs fine
even if your database.py does not yet have this method. To PERSIST stage data
to SQLite, add the method below to your Database class and run the migration.

────────────────────────────────────────────────────────────────────────────
STEP 1 — add this column / table (run once against your SQLite file)
────────────────────────────────────────────────────────────────────────────

    CREATE TABLE IF NOT EXISTS stage_log (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id      TEXT    NOT NULL,
        turn_id         INTEGER,
        turn_number     INTEGER NOT NULL,
        stage           INTEGER NOT NULL,
        declared_stage  INTEGER,
        stage_complete  INTEGER NOT NULL DEFAULT 0,
        created_at      TEXT    DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (session_id) REFERENCES sessions(session_id)
    );

────────────────────────────────────────────────────────────────────────────
STEP 2 — add this method to your Database class in database.py
────────────────────────────────────────────────────────────────────────────

    def log_stage(self, session_id, turn_id, turn_number, stage,
                  declared=None, stage_complete=False):
        '''Record the conversation stage in effect for one agent turn.'''
        self.conn.execute(
            "INSERT INTO stage_log "
            "(session_id, turn_id, turn_number, stage, declared_stage, stage_complete) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, turn_id, turn_number, int(stage),
             None if declared is None else int(declared),
             1 if stage_complete else 0),
        )
        self.conn.commit()

────────────────────────────────────────────────────────────────────────────
STEP 3 — (optional) store final stage on the session row
────────────────────────────────────────────────────────────────────────────

If your sessions table has (or you add) a `final_stage` and `reached_final`
column, you can extend complete_session to store them, or simply rely on the
per-run JSON file, which already contains the full `stage_progression` block:

    {
      "final_stage": 6,
      "stage_history": [1, 2, 3, 4, 5, 5, 6],
      "completed_stages": [1, 2, 3, 4, 5],
      "reached_final": true,
      "stage_corrections": 0,
      "user_requested_exit": false,
      "max_stage_reached": 6
    }
"""