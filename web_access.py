"""Invite-only browser access. Credentials live outside the source checkout."""
import json
import os
import secrets
import time
from collections import OrderedDict
from datetime import timedelta
from pathlib import Path
from threading import Lock

from flask import Response, g, jsonify, redirect, request, session
from markupsafe import escape
from werkzeug.security import check_password_hash


def install_access(app):
    accounts_path = os.environ.get('PARTICIPANTS_FILE')
    if not accounts_path:
        raise RuntimeError('PARTICIPANTS_FILE must point to a private account file')
    secret = os.environ.get('FLASK_SECRET', '')
    if len(secret) < 32:
        raise RuntimeError('FLASK_SECRET must contain at least 32 random characters')
    app.secret_key = secret
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE', '1') == '1',
                      PERMANENT_SESSION_LIFETIME=timedelta(hours=8), MAX_CONTENT_LENGTH=32768)
    failures = OrderedDict()
    guard = Lock()

    def accounts():
        return json.loads(Path(accounts_path).read_text())

    def login_page(error=''):
        token = session.setdefault('csrf', secrets.token_urlsafe(32))
        return Response(f'''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Method Mentor sign in</title></head><body style="font-family:system-ui;max-width:420px;margin:10vh auto;padding:24px">
<h1>Method Mentor</h1><p>Sign in using the account provided by your researcher.</p>
<p>{escape(error)}</p><form method="post"><input type="hidden" name="csrf" value="{escape(token)}">
<p><label>Participant ID <input name="username" required autocomplete="username"></label></p>
<p><label>Password <input name="password" type="password" required autocomplete="current-password"></label></p>
<button>Sign in</button></form></body></html>''', mimetype='text/html')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'GET':
            return login_page()
        if not secrets.compare_digest(request.form.get('csrf', ''), session.get('csrf', 'missing')):
            return login_page('Refresh this page and try again.'), 400
        username = request.form.get('username', '')[:100]
        now = time.monotonic()
        key = (request.remote_addr, username)
        with guard:
            count, since = failures.get(key, (0, now))
            if now - since > 300:
                count, since = 0, now
            if count >= 10:
                return login_page('Too many attempts. Please wait five minutes.'), 429
            failures[key] = (count + 1, since)
            if len(failures) > 2048:
                failures.popitem(last=False)
        account = accounts().get(username)
        if not account or not check_password_hash(account['password_hash'], request.form.get('password', '')):
            return login_page('Participant ID or password is incorrect.'), 401
        with guard:
            failures.pop(key, None)
        session.clear()
        session.update(user=username, csrf=secrets.token_urlsafe(32))
        session.permanent = True
        return redirect('/')

    @app.post('/logout')
    def logout():
        session.clear()
        return redirect('/login')

    @app.before_request
    def require_access():
        if request.path in ('/login', '/healthz'):
            return None
        user = session.get('user')
        account = accounts().get(user) if user else None
        if not account:
            if request.path.startswith('/api/'):
                return jsonify(error='Please sign in again.'), 401
            return redirect('/login')
        g.participant = user
        g.is_admin = account.get('role') == 'admin'
        if request.path in ('/results', '/api/results', '/api/db-stats') and not g.is_admin:
            return jsonify(error='Researcher access required.'), 403
        if request.method == 'POST':
            token = request.headers.get('X-CSRF-Token') or request.form.get('csrf', '')
            if not secrets.compare_digest(token, session.get('csrf', 'missing')):
                return jsonify(error='Refresh the page before continuing.'), 403

    @app.after_request
    def protect_response(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        return response
