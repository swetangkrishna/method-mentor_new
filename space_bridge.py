"""Authenticated Gradio adapter for the existing human-validation engine.

Callbacks must pass ``request.username`` supplied by Gradio authentication;
never take this identity from a textbox, browser state, or API argument.
Only session IDs and new participant input cross the UI boundary. Conversation
history is always retrieved from the engine after its ownership check.
"""

import importlib
import logging
import traceback
import json
import os
import secrets
import time
from collections import OrderedDict
from pathlib import Path
from threading import Lock

from werkzeug.security import check_password_hash


class BridgeError(RuntimeError):
    """A safe message for the participant, without backend exception details."""

    def __init__(self, message, status_code=500):
        super().__init__(message)
        self.status_code = status_code


class SpaceBridge:
    def __init__(self, app=None):
        # Importing the engine opens its database and reads its configuration.
        # Delay that work until runtime secrets and paths have been prepared.
        self._app = app
        self._app_lock = Lock()
        self._auth_lock = Lock()
        self._failures = OrderedDict()

    @staticmethod
    def _accounts():
        try:
            path = os.environ.get("PARTICIPANTS_FILE")
            accounts = json.loads(Path(path).read_text()) if path else {}
            return accounts if isinstance(accounts, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    @classmethod
    def _account(cls, username):
        if not isinstance(username, str) or not username or len(username) > 100:
            return None
        account = cls._accounts().get(username)
        if not isinstance(account, dict) or not isinstance(account.get("password_hash"), str):
            return None
        return account if account["password_hash"] else None

    def auth(self, username, password):
        """Gradio's auth callback; passwords and account hashes are never cached."""
        if (not isinstance(username, str) or not 1 <= len(username) <= 100
                or not isinstance(password, str) or not 1 <= len(password) <= 4096):
            return False
        now = time.monotonic()
        with self._auth_lock:
            count, since = self._failures.get(username, (0, now))
            if now - since >= 300:
                count, since = 0, now
            if count >= 10:
                return False
            self._failures[username] = (count + 1, since)
            self._failures.move_to_end(username)
            if len(self._failures) > 2048:
                self._failures.popitem(last=False)
        account = self._account(username)
        try:
            authenticated = bool(account and check_password_hash(account["password_hash"], password))
        except (ValueError, TypeError):
            authenticated = False
        if authenticated:
            with self._auth_lock:
                self._failures.pop(username, None)
        return authenticated

    def _engine(self):
        with self._app_lock:
            if self._app is None:
                self._app = importlib.import_module("human_validation_server").app
        return self._app

    def _post(self, username, route, payload):
        if not self._account(username):
            raise BridgeError("Please sign in again. This participant account is unavailable.", 401)
        try:
            client = self._engine().test_client()
            token = secrets.token_urlsafe(32)
            # A fresh internal client for each operation prevents one participant's
            # cookies or CSRF token from being reused by another callback.
            with client.session_transaction(base_url="https://localhost") as session:
                session.clear()
                session.update(user=username, csrf=token)
            response = client.post(route, json=payload, base_url="https://localhost",
                                   headers={"X-CSRF-Token": token})
            result = response.get_json(silent=True)
        except Exception as error:
            # Diagnostic locations only: no request text, credentials or raw exceptions.
            frames = [(Path(f.filename).name, f.lineno, f.name)
                      for f in traceback.extract_tb(error.__traceback__)[-5:]]
            logging.getLogger(__name__).warning(
                "Study engine failure type=%s frames=%s", type(error).__name__, frames)
            raise BridgeError("The conversation could not be updated. Please try again shortly.") from None
        if response.status_code >= 400 or not isinstance(result, dict):
            # StudyError contains deliberately authored participant guidance,
            # never a provider/database exception or model response.
            if (response.status_code == 400 and isinstance(result, dict)
                    and result.get('code') == 'study_validation'
                    and isinstance(result.get('error'), str)):
                raise BridgeError(result['error'], 400)
            messages = {
                400: "This action could not be completed. Check your message or feedback and the session status.",
                401: "Please sign in again. This participant account is unavailable.",
                403: "This action is not permitted for this participant account.",
                404: "The session or scenario is unavailable for this participant account.",
                429: "Too many requests. Please wait a few minutes before trying again.",
                503: "This reply could not be generated. Your saved conversation is safe and your input stays in the reply box. Wait briefly, then press Send again; do not start over.",
            }
            status = response.status_code if response.status_code >= 400 else 500
            message=messages.get(status, "The conversation could not be updated. Please try again shortly.")
            if isinstance(result, dict) and result.get('code') == 'provider_content_filter':
                message = ('The model provider’s safety filter blocked this reply. '
                           'Your saved conversation is safe. Please report the reference below '
                           'to the researcher; repeated retries may give the same result.')
            if isinstance(result, dict) and result.get('code') == 'operation_unavailable':
                message = ('This action could not be completed. Your earlier saved records are retained. '
                           'Use Find my conversations to reopen the conversation before trying again.')
            reference=result.get('reference') if isinstance(result,dict) else None
            if isinstance(reference,str) and len(reference)==32 and all(c in '0123456789abcdef' for c in reference):
                message+=' Reference: '+reference
            raise BridgeError(message, status)
        return result

    @staticmethod
    def _session_id(session_id):
        if not isinstance(session_id, str) or not session_id or len(session_id) > 200:
            raise BridgeError("Start or resume a conversation first.", 400)
        return session_id

    def start(self, username, scenario_id="FREEFORM"):
        if not isinstance(scenario_id, str) or not 1 <= len(scenario_id) <= 100:
            raise BridgeError("Choose a research scenario first.", 400)
        return self._post(username, "/api/start", {"scenario_id": scenario_id})

    def message(self, username, session_id, message):
        if not isinstance(message, str) or not 1 <= len(message.strip()) <= 12000:
            raise BridgeError("Enter a message of 1–12,000 characters.", 400)
        return self._post(username, "/api/message", {
            "session_id": self._session_id(session_id), "message": message,
        })

    def resume(self, username, session_id):
        return self._post(username, "/api/resume", {"session_id": self._session_id(session_id)})

    def end(self, username, session_id, task_solved=False):
        if type(task_solved) is not bool:
            raise BridgeError("Choose whether your research question was resolved.", 400)
        return self._post(username, "/api/end", {
            "session_id": self._session_id(session_id), "task_solved": task_solved,
        })

    def survey(self, username, session_id, survey):
        if not isinstance(survey, dict):
            raise BridgeError("Complete the feedback questions first.", 400)
        return self._post(username, "/api/survey", {
            "session_id": self._session_id(session_id), "survey": survey,
        })

    def sessions(self, username):
        return self._post(username, '/api/sessions', {})

    def study_info(self, username):
        return self._post(username, '/api/study/info', {})

    def study_enroll(self, username, consent, pre, confidence):
        return self._post(username, '/api/study/enroll', {'consent':consent,'pre':pre,'confidence':confidence})

    def study_post(self, username, session_id, text, confidence, sus):
        return self._post(username, '/api/study/post', {'session_id':self._session_id(session_id),
                           'text':text,'confidence':confidence,'sus':sus})

    def study_withdraw(self, username, confirm):
        return self._post(username, '/api/study/withdraw', {'confirm':confirm})

    def transcript(self, username, session_id):
        """Return only this participant's engine-owned transcript as plain text.

        No temporary download file is shared through Gradio's file endpoint.
        The caller can show this text for copying or download it in the browser.
        """
        saved = self.resume(username, session_id)
        lines = ["Method Mentor conversation", f"Session: {saved['session_id']}", ""]
        labels = {"assistant": "Mentor", "user": "Participant"}
        for turn in saved["history"]:
            label = labels.get(turn.get("role"))
            content = turn.get("content")
            if label and isinstance(content, str):
                lines.extend([f"{label}: {content}", ""])
        if saved.get("survey_result"):
            lines.append("Feedback submitted.")
        return "\n".join(lines)
