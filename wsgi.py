"""
Production entry point for Gunicorn.

Start with:
    gunicorn wsgi:app --workers 2 --bind 0.0.0.0:5000

Or with a Unix socket (recommended behind nginx):
    gunicorn wsgi:app --workers 2 --bind unix:/tmp/email-assistant.sock
"""
from app import app

if __name__ == "__main__":
    app.run()
