"""Convenience launcher for local development.

Run with:  python run.py
Then open: http://127.0.0.1:8000

The reload flag restarts the server automatically when you edit code.
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
