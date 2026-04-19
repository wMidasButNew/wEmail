import os
import json
import base64
import hashlib
import secrets
import pickle
import requests as http_requests
from flask import (Flask, render_template, render_template_string,
                   jsonify, request, redirect, url_for, session, flash)
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-only-insecure-key')

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
CLIENT_SECRETS_FILE = os.environ.get('GOOGLE_CREDENTIALS_FILE', 'credentials.json')
TOKEN_FILE = os.environ.get('TOKEN_FILE', '/tmp/token.pickle')
BASE_URL = os.environ.get('BASE_URL', 'http://localhost:5000')

# ── Dashboard login (set DASHBOARD_USER and DASHBOARD_PASS in Render env vars) ─
DASHBOARD_USER = os.environ.get('DASHBOARD_USER', 'admin')
DASHBOARD_PASS = os.environ.get('DASHBOARD_PASS', 'admin')


# ── Auth decorator ─────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ── Error pages ───────────────────────────────────────────────────────────────
ERROR_PAGE = """
<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Erreur {{ code }}</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #f8f7f4; display: flex; align-items: center;
         justify-content: center; min-height: 100vh; }
  .card { background: white; border-radius: 16px; padding: 3rem 2.5rem;
          max-width: 480px; width: 90%; text-align: center;
          box-shadow: 0 4px 24px rgba(0,0,0,0.08); }
  .code { font-size: 72px; font-weight: 700; color: #e5e5e5; line-height: 1; }
  h1 { font-size: 22px; margin: 1rem 0 .5rem; color: #1a1a1a; }
  p { color: #6b6b6b; font-size: 14px; line-height: 1.6; }
  a { display: inline-block; margin-top: 1.5rem; background: #1a1a1a; color: white;
      text-decoration: none; padding: 10px 24px; border-radius: 8px; font-size: 13px; }
  a:hover { background: #333; }
</style></head><body>
<div class="card">
  <div class="code">{{ code }}</div>
  <h1>{{ title }}</h1>
  <p>{{ message }}</p>
  <a href="/">← Retour à l'accueil</a>
</div></body></html>
"""

@app.errorhandler(404)
def not_found(e):
    return render_template_string(ERROR_PAGE, code=404,
        title="Page introuvable",
        message="Cette page n'existe pas. Vérifie l'URL ou retourne à l'accueil."), 404

@app.errorhandler(500)
def server_error(e):
    return render_template_string(ERROR_PAGE, code=500,
        title="Erreur serveur",
        message="Quelque chose s'est mal passé. Réessaie dans quelques instants."), 500

@app.errorhandler(403)
def forbidden(e):
    return render_template_string(ERROR_PAGE, code=403,
        title="Accès refusé",
        message="Tu n'as pas les droits pour accéder à cette page."), 403


# ── Login page ─────────────────────────────────────────────────────────────────
LOGIN_PAGE = """
<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Connexion — Assistant Email</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #f8f7f4; display: flex; align-items: center;
         justify-content: center; min-height: 100vh; }
  .card { background: white; border-radius: 16px; padding: 2.5rem 2rem;
          max-width: 380px; width: 90%;
          box-shadow: 0 4px 24px rgba(0,0,0,0.08); }
  .logo { display: flex; align-items: center; gap: 10px; margin-bottom: 2rem; }
  .logo-icon { width: 36px; height: 36px; background: #1a1a1a; border-radius: 10px;
               display: flex; align-items: center; justify-content: center; }
  .logo-icon svg { width: 18px; height: 18px; fill: white; }
  .logo-text { font-size: 17px; font-weight: 600; }
  h1 { font-size: 20px; font-weight: 600; margin-bottom: .5rem; }
  p { color: #6b6b6b; font-size: 13px; margin-bottom: 1.5rem; }
  label { display: block; font-size: 12px; font-weight: 600; color: #444;
          margin-bottom: 5px; }
  input { width: 100%; border: 1px solid #e5e5e5; border-radius: 8px;
          padding: 10px 12px; font-size: 14px; outline: none;
          margin-bottom: 1rem; font-family: inherit; }
  input:focus { border-color: #999; }
  button { width: 100%; background: #1a1a1a; color: white; border: none;
           border-radius: 8px; padding: 11px; font-size: 14px; font-weight: 500;
           cursor: pointer; font-family: inherit; }
  button:hover { background: #333; }
  .error { background: #fef2f2; border: 1px solid #fca5a5; border-radius: 8px;
           padding: 10px 12px; font-size: 13px; color: #991b1b; margin-bottom: 1rem; }
</style></head><body>
<div class="card">
  <div class="logo">
    <div class="logo-icon">
      <svg viewBox="0 0 24 24"><path d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/></svg>
    </div>
    <span class="logo-text">Assistant Email</span>
  </div>
  <h1>Connexion</h1>
  <p>Accède à ton tableau de bord email.</p>
  {% if error %}<div class="error">{{ error }}</div>{% endif %}
  <form method="POST">
    <label>Identifiant</label>
    <input type="text" name="username" placeholder="admin" required autofocus>
    <label>Mot de passe</label>
    <input type="password" name="password" placeholder="••••••••" required>
    <button type="submit">Se connecter</button>
  </form>
</div></body></html>
"""

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if (request.form['username'] == DASHBOARD_USER and
                request.form['password'] == DASHBOARD_PASS):
            session['logged_in'] = True
            return redirect(url_for('index'))
        error = "Identifiant ou mot de passe incorrect."
    return render_template_string(LOGIN_PAGE, error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ── Gemini ─────────────────────────────────────────────────────────────────────
def get_gemini_url():
    key = os.environ.get('GEMINI_API_KEY')
    if not key:
        raise RuntimeError("GEMINI_API_KEY non défini.")
    return (f'https://generativelanguage.googleapis.com/v1beta/models/'
            f'gemini-2.0-flash:generateContent?key={key}')


# ── Gmail ──────────────────────────────────────────────────────────────────────
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


def fetch_emails(max_results=20, query="newer_than:7d"):
    service = get_gmail_service()
    if not service:
        return None, "Non connecté à Gmail"
    try:
        results = service.users().messages().list(
            userId='me', maxResults=max_results, q=query
        ).execute()
    except HttpError as e:
        return None, f"Erreur Gmail API: {e.status_code} — {e.reason}"

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
@login_required
def index():
    service = get_gmail_service()
    connected = service is not None
    return render_template('index.html', connected=connected)


@app.route('/auth')
@login_required
def auth():
    if not os.path.exists(CLIENT_SECRETS_FILE):
        return jsonify({"error": "Fichier credentials.json introuvable."}), 400
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b'=').decode()
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
def oauth2callback():
    try:
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE, scopes=SCOPES, state=session['state']
        )
        flow.redirect_uri = f"{BASE_URL}/callback"
        authorization_response = request.url.replace('http://', 'https://')
        flow.fetch_token(
            authorization_response=authorization_response,
            code_verifier=session['code_verifier']
        )
        creds = flow.credentials
        with open(TOKEN_FILE, 'wb') as f:
            pickle.dump(creds, f)
        return redirect(url_for('index'))
    except Exception:
        import traceback
        return render_template_string(ERROR_PAGE, code=500,
            title="Erreur d'authentification",
            message=f"<pre style='text-align:left;font-size:12px'>{traceback.format_exc()}</pre>"), 500


@app.route('/api/emails')
@login_required
def api_emails():
    try:
        query = request.args.get('q', 'newer_than:7d')
        limit = int(request.args.get('limit', 20))
        emails, error = fetch_emails(max_results=limit, query=query)
        if error:
            return jsonify({"error": error}), 400
        return jsonify({"emails": emails, "total": len(emails)})
    except Exception:
        import traceback
        return jsonify({"error": traceback.format_exc()}), 500


@app.route('/api/status')
@login_required
def api_status():
    service = get_gmail_service()
    return jsonify({"connected": service is not None})


if __name__ == '__main__':
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    print("\n✅ Assistant Email démarré → http://localhost:5000\n")
    app.run(debug=True, port=5000)
