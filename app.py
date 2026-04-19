# =========================
# wDashboard FINAL VERSION (Email + Modules Fully Integrated)
# =========================

import os
import json
import base64
import hashlib
import secrets
import pickle
import requests as http_requests
from datetime import timedelta
from flask import (Flask, render_template, render_template_string, jsonify,
                   request, redirect, url_for, session)
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-key')
app.permanent_session_lifetime = timedelta(minutes=30)

# =========================
# CONFIG
# =========================
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
CLIENT_SECRETS_FILE = os.environ.get('GOOGLE_CREDENTIALS_FILE', 'credentials.json')
TOKEN_FILE = '/tmp/token.pickle'
BASE_URL = os.environ.get('BASE_URL')

DASHBOARD_USER = os.environ.get('DASHBOARD_USER')
DASHBOARD_PASS = os.environ.get('DASHBOARD_PASS')

SCHEDULE_FILE = 'schedule.json'
NOTES_FILE = 'notes.json'
TODO_FILE = 'todo.json'

# =========================
# UTILS
# =========================

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper


def load_json(file):
    if not os.path.exists(file):
        return {}
    with open(file, 'r') as f:
        return json.load(f)


def save_json(file, data):
    with open(file, 'w') as f:
        json.dump(data, f, indent=2)

# =========================
# LOGIN
# =========================
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = ''
    if request.method == 'POST':
        if request.form['username'] == DASHBOARD_USER and request.form['password'] == DASHBOARD_PASS:
            session['logged_in'] = True
            session.permanent = True
            return redirect(url_for('hub'))
        error = 'Wrong credentials'

    return render_template_string(f"""
    <h2>wDashboard</h2>
    <p style='color:red;'>{error}</p>
    <form method='POST'>
      <input name='username' placeholder='user'><br>
      <input name='password' type='password' placeholder='pass'><br>
      <button>Login</button>
    </form>
    """)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# =========================
# HUB
# =========================
@app.route('/')
@login_required
def hub():
    return render_template_string("""
    <h1>wDashboard</h1>
    <a href='/logout'>Logout</a>
    <h3>Modules</h3>
    <ul>
      <li><a href='/email'>📧 wEmail</a></li>
      <li><a href='/schedule'>📅 wSchedule</a></li>
      <li><a href='/notes'>📝 Notes</a></li>
      <li><a href='/todo'>✅ Todo</a></li>
    </ul>
    """)

# =========================
# EMAIL MODULE (FULL)
# =========================

def get_gmail_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as f:
            creds = pickle.load(f)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        return None
    return build('gmail', 'v1', credentials=creds)

@app.route('/email')
@login_required
def email_home():
    service = get_gmail_service()
    connected = service is not None
    return render_template('index.html', connected=connected)

@app.route('/auth')
@login_required
def auth():
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).rstrip(b'=').decode()
    session['code_verifier'] = code_verifier
    flow = Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES)
    flow.redirect_uri = f"{BASE_URL}/callback"
    auth_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        code_challenge=code_challenge,
        code_challenge_method='S256'
    )
    session['state'] = state
    return redirect(auth_url)

@app.route('/callback')
def callback():
    flow = Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES, state=session['state'])
    flow.redirect_uri = f"{BASE_URL}/callback"
    flow.fetch_token(authorization_response=request.url, code_verifier=session['code_verifier'])
    with open(TOKEN_FILE, 'wb') as f:
        pickle.dump(flow.credentials, f)
    return redirect('/email')

@app.route('/api/emails')
@login_required
def api_emails():
    service = get_gmail_service()
    if not service:
        return jsonify({"error":"not connected"})
    results = service.users().messages().list(userId='me', maxResults=10).execute()
    return jsonify(results)

# =========================
# SCHEDULE
# =========================
@app.route('/schedule')
@login_required
def schedule_page():
    return render_template_string("""
    <h2>Schedule</h2>
    <textarea id='d'></textarea>
    <button onclick='s()'>Save</button>
    <script>
    async function l(){let r=await fetch('/api/schedule');let d=await r.json();document.getElementById('d').value=JSON.stringify(d,null,2)}
    async function s(){await fetch('/api/schedule',{method:'POST',headers:{'Content-Type':'application/json'},body:document.getElementById('d').value});alert('saved')}
    l();
    </script>
    <a href='/'>Back</a>
    """)

@app.route('/api/schedule', methods=['GET','POST'])
@login_required
def schedule_api():
    if request.method=='GET': return jsonify(load_json(SCHEDULE_FILE))
    save_json(SCHEDULE_FILE, request.json)
    return jsonify({'ok':True})

# =========================
# NOTES
# =========================
@app.route('/notes')
@login_required
def notes_page():
    return render_template_string("""
    <h2>Notes</h2>
    <textarea id='d'></textarea>
    <button onclick='s()'>Save</button>
    <script>
    async function l(){let r=await fetch('/api/notes');let d=await r.json();document.getElementById('d').value=JSON.stringify(d,null,2)}
    async function s(){await fetch('/api/notes',{method:'POST',headers:{'Content-Type':'application/json'},body:document.getElementById('d').value});alert('saved')}
    l();
    </script>
    <a href='/'>Back</a>
    """)

@app.route('/api/notes', methods=['GET','POST'])
@login_required
def notes_api():
    if request.method=='GET': return jsonify(load_json(NOTES_FILE))
    save_json(NOTES_FILE, request.json)
    return jsonify({'ok':True})

# =========================
# TODO
# =========================
@app.route('/todo')
@login_required
def todo_page():
    return render_template_string("""
    <h2>Todo</h2>
    <textarea id='d'></textarea>
    <button onclick='s()'>Save</button>
    <script>
    async function l(){let r=await fetch('/api/todo');let d=await r.json();document.getElementById('d').value=JSON.stringify(d,null,2)}
    async function s(){await fetch('/api/todo',{method:'POST',headers:{'Content-Type':'application/json'},body:document.getElementById('d').value});alert('saved')}
    l();
    </script>
    <a href='/'>Back</a>
    """)

@app.route('/api/todo', methods=['GET','POST'])
@login_required
def todo_api():
    if request.method=='GET': return jsonify(load_json(TODO_FILE))
    save_json(TODO_FILE, request.json)
    return jsonify({'ok':True})

# =========================
# RUN
# =========================
if __name__ == '__main__':
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    app.run(debug=True)
