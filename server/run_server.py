import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
uvicorn.run("server.app:app", host="127.0.0.1", port=8890, log_level="warning")
