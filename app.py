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

# La clé secrète doit absolument être définie dans les variables d'environnement Render
# pour maintenir les sessions utilisateur.
app.secret_key = os.environ.get('SECRET_KEY')
if not app.secret_key:
    # Fallback uniquement pour le développement, mais Render doit avoir sa propre clé.
    app.secret_key = 'super-secret-production-key-change-me'

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Chemins des fichiers configurés pour le serveur distant (Render)
# On récupère le chemin du fichier credentials depuis les variables d'environnement (Secret Files)
CLIENT_SECRETS_FILE = os.environ.get('GOOGLE_CREDENTIALS_FILE', '/etc/secrets/credentials.json')

# Sur Render, le système de fichiers est éphémère. On utilise /tmp pour le stockage temporaire du token.
TOKEN_FILE = os.environ.get('TOKEN_FILE', '/tmp/token.pickle')

# L'URL de base doit être celle de ton application Render (ex: https://wemail-civu.onrender.com)
BASE_URL = os.environ.get('BASE_URL', 'https://wemail-civu.onrender.com')

def get_gemini_url():
    key = os.environ.get('GEMINI_API_KEY')
    if not key:
        return None
    # Utilisation du modèle flash pour une analyse rapide et efficace
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
            # En cas d'échec du refresh, on force une reconnexion
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
        return jsonify({"error": f"Fichier de configuration Google introuvable sur le serveur ({CLIENT_SECRETS_FILE})."}), 400
    
    flow = Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES)
    # L'URL de redirection doit correspondre exactement à celle configurée dans la console Google Cloud
    flow.redirect_uri = f"{BASE_URL}/callback"
    
    # On demande un accès offline pour obtenir un refresh_token
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
            return "Erreur : Session expirée ou état de sécurité manquant. Veuillez retenter la connexion.", 400

        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE, 
            scopes=SCOPES, 
            state=session['state']
        )
        flow.redirect_uri = f"{BASE_URL}/callback"
        
        # Sur un serveur distant, on s'assure que l'URL capturée par Flask utilise bien HTTPS
        # car Render gère le SSL en amont (proxy).
        authorization_response = request.url.replace('http://', 'https://')
        
        # Échange du code contre un jeton d'accès (token)
        flow.fetch_token(authorization_response=authorization_response)
        
        creds = flow.credentials
        with open(TOKEN_FILE, 'wb') as f:
            pickle.dump(creds, f)
            
        return redirect(url_for('index'))
    except Exception as e:
        import traceback
        # En production, il vaut mieux loguer l'erreur côté serveur, 
        # mais ici on l'affiche pour faciliter ton débogage immédiat.
        return f"<pre>ERREUR CRITIQUE LORS DU CALLBACK :\n{traceback.format_exc()}</pre>", 500

@app.route('/api/status')
def api_status():
    service = get_gmail_service()
    return jsonify({"connected": service is not None})

# Note : Le bloc 'if __name__ == "__main__"' n'est utilisé qu'en local.
# Sur Render, c'est Gunicorn (ou un autre serveur WSGI) qui lancera l'application via wsgi.py.
if __name__ == '__main__':
    # Autorise temporairement le HTTP pour les tests locaux (ne sera pas utilisé sur Render)
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    app.run(debug=True, port=5000)
