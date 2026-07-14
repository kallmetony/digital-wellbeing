import json
import os
from datetime import datetime
from config import STATE_FILE, LOG_FILE, OVERRIDE_FILE

def log_event(event_type, **extra):
    entry = {"ts": datetime.now().isoformat(), "event": event_type, **extra}
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                data["last_start"] = datetime.fromisoformat(data["last_start"]) if data.get("last_start") else None
                return data
        except Exception:
            pass
    return {"last_start": None, "session_active": False, "via_override": False}

def save_state(state):
    data = dict(state)
    data["last_start"] = state["last_start"].isoformat() if state["last_start"] else None
    with open(STATE_FILE, "w") as f:
        json.dump(data, f)

def load_override():
    if os.path.exists(OVERRIDE_FILE):
        try:
            with open(OVERRIDE_FILE, "r") as f:
                data = json.load(f)
                data["expires_at"] = datetime.fromisoformat(data["expires_at"])
                return data
        except Exception:
            pass
    return None
