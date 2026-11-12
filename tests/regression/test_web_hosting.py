import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from werkzeug.security import generate_password_hash


class WebHostingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        accounts = {u: {'role': 'admin' if u == 'researcher' else 'participant',
                        'password_hash': generate_password_hash('test-password-12345')}
                    for u in ['p1', 'p2', 'researcher']}
        (root / 'accounts.json').write_text(json.dumps(accounts))
        cls.env = patch.dict(os.environ, {'PARTICIPANTS_FILE': str(root / 'accounts.json'),
              'FLASK_SECRET': 'test-secret-' * 4, 'DB_PATH': str(root / 'test.db'),
              'LLM_BACKEND': 'vllm', 'COOKIE_SECURE': '0'})
        cls.env.start()
        # Earlier migration tests can import database; use an isolated DB here.
        import database
        cls.db_patch = patch.object(database, 'Database', lambda: cls.real_db(root / 'test.db'))
        cls.real_db = database.Database
        cls.db_patch.start()
        cls.web = importlib.import_module('human_validation_server')
        cls.web.app.config['TESTING'] = True

    @classmethod
    def tearDownClass(cls):
        cls.web.DB.close()
        cls.db_patch.stop()
        cls.env.stop()
        sys.modules.pop('human_validation_server', None)
        cls.tmp.cleanup()

    def setUp(self):
        self.client = self.web.app.test_client()
        self.web.SESSIONS.clear()

    def login(self, user='p1', client=None):
        client = client or self.client
        client.get('/login')
        with client.session_transaction() as sess:
            token = sess['csrf']
        r = client.post('/login', data={'username': user, 'password': 'test-password-12345', 'csrf': token})
        self.assertEqual(r.status_code, 302)
        with client.session_transaction() as sess:
            return {'X-CSRF-Token': sess['csrf']}

    def test_auth_and_admin(self):
        self.assertEqual(self.client.get('/').status_code, 302)
        self.assertEqual(self.client.get('/healthz').status_code, 200)
        self.assertEqual(self.client.post('/api/start', json={}).status_code, 401)
        self.login()
        self.assertEqual(self.client.get('/results').status_code, 403)
        self.assertEqual(self.client.post('/api/start', json={}).status_code, 403)
        self.assertIn(b'My own research project', self.client.get('/').data)
        self.login('researcher')
        self.assertEqual(self.client.get('/results').status_code, 200)

    def test_freeform_message_rag_and_ownership(self):
        headers = self.login()
        output = {'response': 'What is your research question?', 'skill_name': 'probe-intended-decisions',
                  'reasoning': 'clarify', 'declared_stage': 1, 'stage_complete': False, 'task_solved': False}
        with patch.object(self.web, 'agent_turn', return_value=output) as call, \
             patch.object(self.web, '_retrieve_for_turn', return_value=('RAG reference', [], True)):
            r = self.client.post('/api/start', json={'scenario_id': 'FREEFORM'}, headers=headers)
            self.assertEqual(r.status_code, 200, r.data)
            sid = r.json['session_id']
            self.assertIn('RAG reference', call.call_args.kwargs['stage_context'])
            r = self.client.post('/api/message', json={'session_id': sid, 'message': 'I study AI pedagogy using interviews'}, headers=headers)
            self.assertEqual(r.status_code, 200, r.data)
            self.assertEqual(r.json['turn_count'], 2)
            # Simulate a worker restart: recover the checkpoint, including tracker sets.
            self.web.SESSIONS.clear()
            resumed = self.client.post('/api/resume', json={'session_id': sid}, headers=headers)
            self.assertEqual(resumed.status_code, 200)
            self.assertEqual(resumed.json['turn_count'], 2)
            self.assertIsInstance(self.web.SESSIONS[sid]['tracker'].completed_stages, set)
            with patch.object(self.web, 'agent_turn', side_effect=RuntimeError('secret provider detail')):
                failed = self.client.post('/api/message', json={'session_id': sid, 'message': 'new question'}, headers=headers)
                self.assertEqual(failed.status_code, 503)
                self.assertNotIn(b'secret provider detail', failed.data)
                self.assertEqual(self.web.SESSIONS[sid]['turn_count'], 2)
            other = self.web.app.test_client()
            other_headers = self.login('p2', other)
            for route in ['message', 'end', 'survey']:
                r = other.post('/api/' + route, json={'session_id': sid, 'message': 'hi'}, headers=other_headers)
                self.assertEqual(r.status_code, 404)
            self.assertEqual(self.client.post('/api/end', json={'session_id': sid}, headers=headers).status_code, 200)
            survey = {f'Q{i}': {'score': 4, 'comment': ''} for i in range(1, 6)}
            survey['Q_open'] = {'score': None, 'comment': 'Useful'}
            r = self.client.post('/api/survey', json={'session_id': sid, 'survey': survey}, headers=headers)
            self.assertEqual(r.status_code, 200, r.data)

    def test_revoked_account_and_logout(self):
        headers = self.login()
        self.assertEqual(self.client.post('/logout', headers=headers).status_code, 302)
        self.assertEqual(self.client.get('/api/results').status_code, 401)
        self.login()
        path = Path(os.environ['PARTICIPANTS_FILE'])
        original = path.read_text()
        data = json.loads(original)
        del data['p1']
        try:
            path.write_text(json.dumps(data))
            self.assertEqual(self.client.post('/api/resume', json={}, headers=headers).status_code, 401)
        finally:
            path.write_text(original)

    def test_invalid_password_and_missing_csrf(self):
        self.assertEqual(self.client.post('/login', data={'username':'p1', 'password':'test-password-12345'}).status_code, 400)
        self.client.get('/login')
        with self.client.session_transaction() as sess:
            token = sess['csrf']
        self.assertEqual(self.client.post('/login', data={'username':'p1', 'password':'bad', 'csrf':token}).status_code, 401)
