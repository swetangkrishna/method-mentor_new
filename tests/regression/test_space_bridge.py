import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from space_bridge import BridgeError, SpaceBridge


class SpaceBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.accounts_path = root / "accounts.json"
        cls.accounts = {
            user: {"role": "participant", "password_hash": generate_password_hash("test-password-12345")}
            for user in ("p1", "p2")
        }
        cls.accounts_path.write_text(json.dumps(cls.accounts))
        cls.env = patch.dict(os.environ, {
            "PARTICIPANTS_FILE": str(cls.accounts_path), "FLASK_SECRET": "test-secret-" * 4,
            "DB_PATH": str(root / "test.db"), "WEB_SESSIONS_DIR": str(root / "sessions"),
            "LLM_BACKEND": "vllm", "COOKIE_SECURE": "1",
        })
        cls.env.start()
        import database
        real_db = database.Database
        cls.db_patch = patch.object(database, "Database", lambda: real_db(root / "test.db"))
        cls.db_patch.start()
        cls.web = importlib.import_module("human_validation_server")
        cls.web.app.config["TESTING"] = True

    @classmethod
    def tearDownClass(cls):
        cls.web.DB.close()
        cls.db_patch.stop()
        cls.env.stop()
        sys.modules.pop("human_validation_server", None)
        cls.tmp.cleanup()

    def setUp(self):
        self.accounts_path.write_text(json.dumps(self.accounts))
        self.web.SESSIONS.clear()
        self.bridge = SpaceBridge(self.web.app)
        self.output = {
            "response": "What is your research question?", "skill_name": "probe-intended-decisions",
            "reasoning": "clarify", "declared_stage": 1, "stage_complete": False,
            "task_solved": False,
        }
        self.agent = patch.object(self.web, "agent_turn", return_value=self.output)
        self.rag = patch.object(self.web, "_retrieve_for_turn", return_value=("RAG reference", [], True))
        self.agent_mock = self.agent.start()
        self.rag.start()
        self.addCleanup(self.agent.stop)
        self.addCleanup(self.rag.stop)

    def test_lazy_initialization_and_rate_limited_hash_auth(self):
        with patch("space_bridge.importlib.import_module", side_effect=AssertionError("early engine import")):
            bridge = SpaceBridge()
            self.assertTrue(bridge.auth("p1", "test-password-12345"))
            self.assertFalse(bridge.auth("missing", "test-password-12345"))
        with patch("space_bridge.time.monotonic", return_value=100):
            for _ in range(10):
                self.assertFalse(self.bridge.auth("p1", "incorrect"))
            self.assertFalse(self.bridge.auth("p1", "test-password-12345"))
        with patch("space_bridge.time.monotonic", return_value=401):
            self.assertTrue(self.bridge.auth("p1", "test-password-12345"))
        self.assertFalse(self.bridge.auth(None, "test-password-12345"))

    def test_existing_engine_rag_resume_and_transcript(self):
        started = self.bridge.start("p1")
        sid = started["session_id"]
        self.assertIn("RAG reference", self.agent_mock.call_args.kwargs["stage_context"])
        self.bridge.message("p1", sid, "I study AI pedagogy using interviews.")
        self.web.SESSIONS.clear()  # Simulate losing the in-memory worker state.
        resumed = self.bridge.resume("p1", sid)
        self.assertEqual(resumed["turn_count"], 2)
        self.assertEqual(len(resumed["history"]), 3)
        transcript = self.bridge.transcript("p1", sid)
        self.assertIn("Participant: I study AI pedagogy using interviews.", transcript)
        self.assertIn("Mentor: What is your research question?", transcript)
        self.assertNotIn("password", transcript)
        self.assertEqual(self.web.SESSIONS[sid]["owner"], "p1")

    def test_startup_diagnostics_exclude_sensitive_exception_text(self):
        with patch.object(self.bridge, '_engine', side_effect=RuntimeError('PRIVATE_CONNECTION_PASSWORD')):
            with self.assertLogs('space_bridge', level='WARNING') as logs:
                with self.assertRaises(BridgeError) as caught:
                    self.bridge.start('p1')
        self.assertIn('RuntimeError', ' '.join(logs.output))
        self.assertNotIn('PRIVATE_CONNECTION_PASSWORD', ' '.join(logs.output))
        self.assertNotIn('PRIVATE_CONNECTION_PASSWORD', str(caught.exception))

    def test_all_operations_deny_other_participant_and_revoked_account(self):
        sid = self.bridge.start("p1")["session_id"]
        operations = [
            lambda user: self.bridge.resume(user, sid),
            lambda user: self.bridge.message(user, sid, "Hello"),
            lambda user: self.bridge.end(user, sid),
            lambda user: self.bridge.survey(user, sid, {}),
            lambda user: self.bridge.transcript(user, sid),
        ]
        for operation in operations:
            with self.subTest(operation=operation), self.assertRaises(BridgeError) as raised:
                operation("p2")
            self.assertEqual(raised.exception.status_code, 404)
        self.accounts_path.write_text(json.dumps({"p2": self.accounts["p2"]}))
        for operation in operations + [lambda user: self.bridge.start(user)]:
            with self.subTest(revoked=operation), self.assertRaises(BridgeError) as raised:
                operation("p1")
            self.assertEqual(raised.exception.status_code, 401)
        self.assertFalse(self.bridge.auth("p1", "test-password-12345"))

    def test_feedback_and_model_failure_preserve_saved_history(self):
        sid = self.bridge.start("p1")["session_id"]
        self.agent_mock.side_effect = RuntimeError("SECRET PROVIDER ERROR")
        with self.assertRaises(BridgeError) as raised:
            self.bridge.message("p1", sid, "Unsaved message")
        self.assertEqual(raised.exception.status_code, 503)
        self.assertNotIn("SECRET", str(raised.exception))
        self.assertNotIn("Unsaved message", self.bridge.transcript("p1", sid))
        self.bridge.end("p1", sid, task_solved=True)
        survey = {f"Q{i}": {"score": 4, "comment": ""} for i in range(1, 6)}
        survey["Q_open"] = {"score": None, "comment": "Useful"}
        result = self.bridge.survey("p1", sid, survey)
        self.assertTrue(result["task_solved"])
        self.assertEqual(result, self.bridge.survey("p1", sid, survey))
        self.assertTrue(self.bridge.resume("p1", sid)["ended"])
        self.assertIn("Feedback submitted.", self.bridge.transcript("p1", sid))

    def test_corrupt_accounts_fail_closed_and_invalid_inputs_make_no_model_call(self):
        for action in [lambda: self.bridge.message("p1", "missing", {}),
                       lambda: self.bridge.resume("p1", None),
                       lambda: self.bridge.end("p1", "missing", "false")]:
            with self.assertRaises(BridgeError) as raised:
                action()
            self.assertEqual(raised.exception.status_code, 400)
        self.accounts_path.write_text("not JSON")
        self.assertFalse(self.bridge.auth("p1", "test-password-12345"))
        with self.assertRaises(BridgeError) as raised:
            self.bridge.start("p1")
        self.assertEqual(raised.exception.status_code, 401)
        self.agent_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
