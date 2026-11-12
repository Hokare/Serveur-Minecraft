import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=os.environ.get("PANEL_HOST", "127.0.0.1"),
        port=int(os.environ.get("PANEL_PORT", "8080")),
        log_level="info",
    )
