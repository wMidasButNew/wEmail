# Assistant Email IA

Dashboard local qui trie, résume et propose des réponses à tes emails Gmail grâce à l'IA.

---

## Installation

### 1. Installer les dépendances

```bash
cd email-assistant
pip install -r requirements.txt
```

### 2. Obtenir les credentials Google (Gmail API)

1. Va sur https://console.cloud.google.com
2. Crée un projet (ou utilise un existant)
3. Active l'API Gmail : **APIs & Services → Enable APIs → Gmail API**
4. Crée des identifiants OAuth 2.0 :
   - **APIs & Services → Credentials → Create Credentials → OAuth client ID**
   - Type : **Desktop application**
   - Télécharge le fichier JSON
5. Renomme-le `credentials.json` et place-le dans le dossier `email-assistant/`

### 3. Configurer ta clé Gemini

```bash
export GEMINI_API_KEY="AIza..."
```

Obtiens ta clé sur https://aistudio.google.com/apikey

Ou crée un fichier `.env` :
```
GEMINI_API_KEY=AIza...
```

---

## Lancement

```bash
python app.py
```

Puis ouvre http://localhost:5000 dans ton navigateur.

La première fois, clique sur **"Connecter Gmail"** pour autoriser l'accès.

---

## Fonctionnalités

- **Tri automatique** : urgent, pro, perso, newsletter, autre
- **Résumé IA** : 1-2 phrases par email
- **Suggestions de réponse** : 2 propositions adaptées au contexte
- **Filtres** par catégorie et période (1j, 3j, 7j, 30j)
- **Recherche** dans les emails

---

## Structure

```
email-assistant/
├── app.py              # Backend Flask + logique Gmail + Anthropic
├── templates/
│   └── index.html      # Dashboard web
├── requirements.txt    # Dépendances Python
├── credentials.json    # À ajouter (Google OAuth)
└── token.pickle        # Généré automatiquement après auth
```
