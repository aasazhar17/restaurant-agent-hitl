# main.py
import os
import uvicorn
from server import app

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    print(f"Starting GourmetBot server on http://{host}:{port} ...")
    uvicorn.run(app, host=host, port=port)