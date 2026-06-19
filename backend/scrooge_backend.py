from __future__ import annotations

import os

import uvicorn

from scrooge.main import app


def main() -> None:
    host = os.getenv("SCROOGE_HOST", "127.0.0.1")
    port = int(os.getenv("SCROOGE_PORT", "8750"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
