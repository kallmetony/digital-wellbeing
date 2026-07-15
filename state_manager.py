import json
import os
from datetime import datetime
from config import STATE_FILE, LOG_FILE, OVERRIDE_FILE

def log_event(event_type, **extra):
    entry = {"ts": datetime.now().isoformat(), "event": event_type, **extra}
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def load_state():
    defaults = {
        "last_start": None,
        "last_end": None,
        "session_active": False,
        "via_override": False,
        "schedule_enabled": False,
        "work_start": "09:00",
        "work_end": "18:00",
        "paused": False
    }
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                if data.get("last_start"):
                    data["last_start"] = datetime.fromisoformat(data["last_start"])
                if data.get("last_end"):
                    data["last_end"] = datetime.fromisoformat(data["last_end"])
                # Merge defaults
                for k, v in defaults.items():
                    if k not in data:
                        data[k] = v
                return data
        except Exception:
            pass
    return defaults

def save_state(state):
    data = dict(state)
    data["last_start"] = state["last_start"].isoformat() if state["last_start"] else None
    data["last_end"] = state["last_end"].isoformat() if state["last_end"] else None
    with open(STATE_FILE, "w") as f:
        json.dump(data, f)

def get_cooldown_status(state):
    from datetime import timedelta
    from config import COOLDOWN_MIN

    now = datetime.now()
    ref_time = state.get("last_end")
    if not ref_time and state.get("last_start"):
        try:
            from config import SESSION_MAX_MIN
        except ImportError:
            SESSION_MAX_MIN = 5
        ref_time = state["last_start"] + timedelta(minutes=SESSION_MAX_MIN)

    if not ref_time:
        return False, timedelta(0)

    elapsed = now - ref_time
    cooldown_limit = timedelta(minutes=COOLDOWN_MIN)
    if elapsed < cooldown_limit:
        return True, cooldown_limit - elapsed
    return False, timedelta(0)

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

def is_inside_hours(t, start_str, end_str):
    try:
        sh, sm = map(int, start_str.split(':'))
        eh, em = map(int, end_str.split(':'))
    except Exception:
        return True
    
    start_time = t.replace(hour=sh, minute=sm, second=0, microsecond=0).time()
    end_time = t.replace(hour=eh, minute=em, second=0, microsecond=0).time()
    curr_time = t.time()
    
    if start_time <= end_time:
        return start_time <= curr_time <= end_time
    else: # Overnight, e.g. 22:00 to 06:00
        return curr_time >= start_time or curr_time <= end_time

def check_restrictions_active(state, now):
    if not state.get("schedule_enabled", False):
        return True
    
    inside = is_inside_hours(now, state.get("work_start", "09:00"), state.get("work_end", "18:00"))
    if inside:
        if state.get("paused", False):
            state["paused"] = False
            save_state(state)
        return True
    else:
        return not state.get("paused", False)

