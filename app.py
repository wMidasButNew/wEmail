import os
import json
import base64
import requests as http_requests
from flask import Flask, render_template, jsonify, request, redirect, url_for, session
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import pickle
from datetime import datetime

app = Flask(__name__)

# ── Secret key: read from env var, fallback for local dev only ─────────────────
app.secret_key = os.environ.get('SECRET_KEY', 'dev-only-insecure-key')

# ── Config ─────────────────────────────────────────────────────────────────────
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
CLIENT_SECRETS_FILE = os.environ.get('GOOGLE_CREDENTIALS_FILE', 'credentials.json')
TOKEN_FILE = os.environ.get('TOKEN_FILE', 'token.pickle')

# Base URL of your server (no trailing slash), e.g. https://myapp.example.com
BASE_URL = os.environ.get('BASE_URL', 'http://localhost:5000')


def get_gemini_url():
    """Build Gemini URL at request time so missing key only errors on use."""
    key = os.environ.get('GEMINI_API_KEY')
    if not key:
        raise RuntimeError("GEMINI_API_KEY environment variable is not set.")
    return (
        f'https://generativelanguage.googleapis.com/v1beta/models/'
        f'gemini-2.0-flash:generateContent?key={key}'
    )


# ── Gmail helpers ──────────────────────────────────────────────────────────────

def get_gmail_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as f:
            creds = pickle.load(f)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, 'wb') as f:
            pickle.dump(creds, f)
    if not creds or not creds.valid:
        return None
    return build('gmail', 'v1', credentials=creds)


def decode_body(payload):
    body = ''
    if 'parts' in payload:
        for part in payload['parts']:
            if part['mimeType'] == 'text/plain' and 'data' in part.get('body', {}):
                body += base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
            elif part['mimeType'] == 'text/html' and not body and 'data' in part.get('body', {}):
                body += base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
            elif 'parts' in part:
                body += decode_body(part)
    elif 'body' in payload and 'data' in payload['body']:
        body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
    return body[:2000]


# ── Gemini analysis ────────────────────────────────────────────────────────────

def analyze_email(sender, subject, body, snippet):
    prompt = f"""Analyse cet email et réponds UNIQUEMENT en JSON valide, sans markdown.

Expéditeur: {sender}
Sujet: {subject}
Extrait: {snippet}
Corps: {body[:800]}

Format:
{{
  "category": "urgent|pro|perso|newsletter|autre",
  "summary": "Résumé clair en 1-2 phrases en français.",
  "replies": ["suggestion 1", "suggestion 2"]
}}

Règles:
- urgent: action requise rapidement (sécurité, délai, problème)
- pro: professionnel/travail
- perso: famille, amis
- newsletter: promotions, bulletins, notifications automatiques
- autre: transactionnel, confirmations
- replies: 2 suggestions courtes et naturelles en français (vide [] si newsletter/automatique)
- Uniquement le JSON, rien d'autre."""

    resp = http_requests.post(get_gemini_url(), json={
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 400}
    }, timeout=15)
    resp.raise_for_status()
    text = resp.json()['candidates'][0]['content']['parts'][0]['text']
    text = text.strip().replace('```json', '').replace('```', '').strip()
    return json.loads(text)


# ── Email fetching ─────────────────────────────────────────────────────────────

def fetch_emails(max_results=20, query="newer_than:7d"):
    service = get_gmail_service()
    if not service:
        return None, "Non connecté à Gmail"

    results = service.users().messages().list(
        userId='me', maxResults=max_results, q=query
    ).execute()
    messages = results.get('messages', [])

    emails = []
    for msg in messages:
        try:
            full = service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
            headers = {h['name']: h['value'] for h in full['payload'].get('headers', [])}
            sender = headers.get('From', 'Inconnu')
            subject = headers.get('Subject', '(sans objet)')
            date_str = headers.get('Date', '')
            snippet = full.get('snippet', '')
            body = decode_body(full['payload'])

            try:
                analysis = analyze_email(sender, subject, body, snippet)
            except Exception:
                analysis = {"category": "autre", "summary": snippet[:150], "replies": []}

            name = sender.split('<')[0].strip().strip('"') or sender
            email_addr = sender.split('<')[-1].replace('>', '').strip() if '<' in sender else sender

            emails.append({
                "id": msg['id'],
                "from": name,
                "email": email_addr,
                "subject": subject,
                "date": date_str,
                "snippet": snippet,
                "category": analysis.get("category", "autre"),
                "summary": analysis.get("summary", snippet[:150]),
                "replies": analysis.get("replies", [])
            })
        except Exception:
            continue

    return emails, None


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    service = get_gmail_service()
    connected = service is not None
    return render_template('index.html', connected=connected)


@app.route('/auth')
def auth():
    if not os.path.exists(CLIENT_SECRETS_FILE):
        return jsonify({"error": "Fichier credentials.json introuvable. Voir README.md"}), 400
    flow = Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES)
    # Use BASE_URL so the redirect works on a real domain (not localhost)
    flow.redirect_uri = f"{BASE_URL}/oauth2callback"
    auth_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true')
    session['state'] = state
    return redirect(auth_url)


@app.route('/oauth2callback')
def oauth2callback():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES, state=session['state']
    )
    flow.redirect_uri = f"{BASE_URL}/oauth2callback"
    # Render (and most reverse proxies) forward requests internally as HTTP
    # even though the public URL is HTTPS — force https so oauthlib doesn't reject it
    authorization_response = request.url.replace('http://', 'https://')
    flow.fetch_token(authorization_response=authorization_response)
    creds = flow.credentials
    with open(TOKEN_FILE, 'wb') as f:
        pickle.dump(creds, f)
    return redirect(url_for('index'))


@app.route('/api/emails')
def api_emails():
    query = request.args.get('q', 'newer_than:7d')
    limit = int(request.args.get('limit', 20))
    emails, error = fetch_emails(max_results=limit, query=query)
    if error:
        return jsonify({"error": error}), 401
    return jsonify({"emails": emails, "total": len(emails)})


@app.route('/api/status')
def api_status():
    service = get_gmail_service()
    return jsonify({"connected": service is not None})


# ── Dev entry point (never used in production) ─────────────────────────────────

if __name__ == '__main__':
    # Allow HTTP for local dev only
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    print("\n✅ Assistant Email démarré → http://localhost:5000\n")
    app.run(debug=True, port=5000)
