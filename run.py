"""Entry point for running the Insider Threat Detection System locally.

Usage (PowerShell):
    python run.py

Then visit http://127.0.0.1:5000/health
"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
