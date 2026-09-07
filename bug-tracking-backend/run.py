"""
run.py
-------
Local development entry point.

  python run.py

starts the Flask dev server. In production (Render), gunicorn imports
`app` directly from this file instead (see Procfile), so the dev server
below is never used in production.
"""

import os
from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=app.config.get("DEBUG", False))
