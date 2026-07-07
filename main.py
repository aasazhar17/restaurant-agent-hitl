# main.py
import uvicorn
from server import app

if __name__ == "__main__":
    print("Starting GourmetBot server on http://127.0.0.1:8000 ...")
    uvicorn.run(app, host="127.0.0.1", port=8000)