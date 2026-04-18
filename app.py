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

# Clé secrète pour les sessions (doit être définie dans Render)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-fallback-key-12345')

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Chemins des fichiers (configurés pour Render)
CLIENT_SECRETS_FILE = os.environ.get('GOOGLE_CREDENTIALS_FILE', 'credentials.json')
TOKEN_FILE = os.environ.get('TOKEN_FILE', '/tmp/token.pickle')
BASE_URL = os.environ.get('BASE_URL', 'https://wemail-civu.onrender.com')

def get_gemini_url():
    key = os.environ.get('GEMINI_API_KEY')
    if not key:
        return None
    return f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={key}'

def get_gmail_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as f:
            creds = pickle.load(f)
    
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(TOKEN_FILE, 'wb') as f:
                pickle.dump(creds, f)
        except Exception:
            return None

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

@app.route('/')
def index():
    service = get_gmail_service()
    connected = service is not None
    return render_template('index.html', connected=connected)

@app.route('/auth')
def auth():
    if not os.path.exists(CLIENT_SECRETS_FILE):
        return jsonify({"error": f"Fichier {CLIENT_SECRETS_FILE} introuvable sur le serveur."}), 400
    
    flow = Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES)
    # Cette URL doit être EXACTEMENT la même que dans la console Google Cloud
    flow.redirect_uri = f"{BASE_URL}/callback"
    
    auth_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    
    session['state'] = state
    return redirect(auth_url)

@app.route('/callback')
def oauth2callback():
    try:
        if 'state' not in session:
            return "Erreur : Session expirée ou état manquant. Veuillez recommencer.", 400

        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE, 
            scopes=SCOPES, 
            state=session['state']
        )
        flow.redirect_uri = f"{BASE_URL}/callback"
        
        # Correction pour HTTPS sur les serveurs distants (Render)
        authorization_response = request.url.replace('http://', 'https://')
        
        # Récupération du jeton (token)
        flow.fetch_token(authorization_response=authorization_response)
        
        creds = flow.credentials
        with open(TOKEN_FILE, 'wb') as f:
            pickle.dump(creds, f)
            
        return redirect(url_for('index'))
    except Exception as e:
        import traceback
        return f"<pre>ERREUR LORS DU CALLBACK :\n{traceback.format_exc()}</pre>", 500

@app.route('/api/status')
def api_status():
    service = get_gmail_service()
    return jsonify({"connected": service is not None})

if __name__ == '__main__':
    # Autorise le HTTP pour le développement local uniquement
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    app.run(debug=True, port=5000)
