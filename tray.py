import threading
import time
import pystray
import subprocess
import sys
import os
from datetime import datetime, timedelta
from PIL import Image, ImageDraw
from config import (
    PROCESS_NAMES, COOLDOWN_MIN, SESSION_MAX_MIN, OVERRIDE_SESSION_MAX_MIN, POLL_INTERVAL_SEC, OVERRIDE_FILE,
    COLOR_GREEN, COLOR_RED, COLOR_BLUE, COLOR_MUTED
)
try:
    from config import SHOW_EXIT_OPTION
except ImportError:
    SHOW_EXIT_OPTION = True
from state_manager import (
    load_state, save_state, load_override, log_event,
    is_inside_hours, check_restrictions_active, get_cooldown_status
)
from process_monitor import is_running, kill_process

icon = None
running_daemon = True

def open_menu_console(tab="dashboard"):
    script_path = os.path.abspath(sys.argv[0])
    python_exe = sys.executable.replace("pythonw.exe", "python.exe")
    subprocess.Popen([python_exe, script_path, "--menu", "--tab", tab], creationflags=subprocess.CREATE_NEW_CONSOLE)

def create_image(color_hex):
    width, height = 64, 64
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    dc = ImageDraw.Draw(image)
    dc.ellipse([2, 2, width-3, height-3], fill=color_hex, outline="#11111b", width=3)
    dc.ellipse([30, 30, 34, 34], fill="#11111b")
    dc.line([32, 32, 32, 16], fill="#11111b", width=3)
    dc.line([32, 32, 44, 32], fill="#11111b", width=3)
    return image

def get_status_text(state, running):
    now = datetime.now()
    schedule_enabled = state.get("schedule_enabled", False)
    
    # If paused during non-working hours
    if schedule_enabled:
        inside = is_inside_hours(now, state.get("work_start", "09:00"), state.get("work_end", "18:00"))
        if not inside and state.get("paused", False):
            return "Paused (Off-hours)"
            
    if running:
        limit = OVERRIDE_SESSION_MAX_MIN if state.get("via_override") else SESSION_MAX_MIN
        elapsed = now - state["last_start"]
        remaining = timedelta(minutes=limit) - elapsed
        remaining_sec = max(0, int(remaining.total_seconds()))
        mins, secs = divmod(remaining_sec, 60)
        via = " (Override)" if state.get("via_override") else ""
        return f"Active{via}: {mins:02d}:{secs:02d} left"
    else:
        cooldown_active, remaining = get_cooldown_status(state)
        if cooldown_active:
            remaining_sec = max(0, int(remaining.total_seconds()))
            mins, secs = divmod(remaining_sec, 60)
            return f"Cooldown: {mins:02d}:{secs:02d} left"
        else:
            if schedule_enabled and not is_inside_hours(now, state.get("work_start", "09:00"), state.get("work_end", "18:00")):
                return "Ready (Off-hours)"
            return "Ready"

def trigger_force_end():
    kill_process(PROCESS_NAMES)
    state = load_state()
    if state["session_active"]:
        now = datetime.now()
        duration = (now - state["last_start"]).total_seconds()
        log_event("session_ended_manually", duration_seconds=int(duration))
        state["session_active"] = False
        state["last_end"] = now
        save_state(state)
    else:
        log_event("session_ended_manually")
    # Immediately update tray icon
    update_icon_status(state, False)

def get_menu(state, running):
    status_text = get_status_text(state, running)
    
    # Override button is enabled ONLY if cooldown is active and Telegram is NOT running
    cooldown_active, _ = get_cooldown_status(state)
    override_enabled = cooldown_active and not running
    
    # Force end is enabled if Telegram is running
    force_end_enabled = running
    
    now = datetime.now()
    schedule_enabled = state.get("schedule_enabled", False)
    inside_work_hours = True
    if schedule_enabled:
        inside_work_hours = is_inside_hours(now, state.get("work_start", "09:00"), state.get("work_end", "18:00"))
        
    show_pause_option = schedule_enabled and not inside_work_hours
    
    menu_items = [
        pystray.MenuItem(f"Status: {status_text}", lambda: None, enabled=False),
    ]
    
    if show_pause_option:
        is_paused = state.get("paused", False)
        pause_label = "Resume Limiter" if is_paused else "Pause Limiter"
        
        def toggle_pause():
            curr_state = load_state()
            curr_state["paused"] = not curr_state.get("paused", False)
            save_state(curr_state)
            update_icon_status(curr_state, is_running(PROCESS_NAMES))
            
        menu_items.append(pystray.MenuItem(pause_label, toggle_pause))
        
    menu_items.extend([
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Main Menu", lambda: open_menu_console("dashboard"), default=True),
        pystray.MenuItem("Request Override", lambda: open_menu_console("override"), enabled=override_enabled),
        pystray.MenuItem("Force End Session", lambda: trigger_force_end(), enabled=force_end_enabled),
        pystray.MenuItem("Show Statistics", lambda: open_menu_console("stats")),
        pystray.MenuItem("Schedule Settings", lambda: open_menu_console("schedule")),
    ])
    
    if SHOW_EXIT_OPTION:
        menu_items.append(pystray.Menu.SEPARATOR)
        menu_items.append(pystray.MenuItem("Exit", lambda: exit_app()))
        
    return pystray.Menu(*menu_items)

def update_icon_status(state, running):
    global icon
    if not icon:
        return
        
    status_text = get_status_text(state, running)
    icon.title = f"Telegram Limiter\nStatus: {status_text}"
    
    now = datetime.now()
    schedule_enabled = state.get("schedule_enabled", False)
    inside_work_hours = True
    if schedule_enabled:
        inside_work_hours = is_inside_hours(now, state.get("work_start", "09:00"), state.get("work_end", "18:00"))
        
    if schedule_enabled and not inside_work_hours and state.get("paused", False):
        color = COLOR_MUTED
    elif running:
        color = COLOR_GREEN
    else:
        cooldown_active, _ = get_cooldown_status(state)
        if cooldown_active:
            color = COLOR_RED
        else:
            color = COLOR_BLUE
        
    icon.icon = create_image(color)
    icon.menu = get_menu(state, running)

def exit_app():
    global icon, running_daemon
    running_daemon = False
    if icon:
        icon.stop()

def run_daemon():
    global running_daemon
    log_event("daemon_started")

    while running_daemon:
        state = load_state()
        now = datetime.now()
        running = is_running(PROCESS_NAMES)

        # Check if restrictions are active
        active = check_restrictions_active(state, now)
        
        if not active:
            if state["session_active"]:
                state["session_active"] = False
                state["via_override"] = False
                state["last_end"] = now
                save_state(state)
            update_icon_status(state, running)
            time.sleep(POLL_INTERVAL_SEC)
            continue

        if running:
            if not state["session_active"]:
                override = load_override()
                override_valid = override and not override["used"] and now < override["expires_at"]

                if override_valid:
                    state["last_start"] = now
                    state["session_active"] = True
                    state["via_override"] = True
                    import json
                    with open(OVERRIDE_FILE, "w") as f:
                        json.dump({"expires_at": override["expires_at"].isoformat(), "used": True}, f)
                    save_state(state)
                    log_event("session_started", via_override=True)

                else:
                    cooldown_active, remaining = get_cooldown_status(state)
                    if cooldown_active:
                        kill_process(PROCESS_NAMES)
                        log_event("blocked_cooldown", remaining_seconds=int(remaining.total_seconds()))
                    else:
                        state["last_start"] = now
                        state["session_active"] = True
                        state["via_override"] = False
                        save_state(state)
                        log_event("session_started", via_override=False)

            else:
                limit = OVERRIDE_SESSION_MAX_MIN if state.get("via_override") else SESSION_MAX_MIN
                if now - state["last_start"] > timedelta(minutes=limit):
                    kill_process(PROCESS_NAMES)
                    log_event("session_time_exceeded", limit_min=limit)
                    state["session_active"] = False
                    state["last_end"] = now
                    save_state(state)
        else:
            if state["session_active"]:
                duration = (now - state["last_start"]).total_seconds()
                log_event("session_ended_early", duration_seconds=int(duration))
                state["session_active"] = False
                state["last_end"] = now
                save_state(state)

        update_icon_status(state, running)
        time.sleep(POLL_INTERVAL_SEC)

def start_tray():
    global icon
    state = load_state()
    running = is_running(PROCESS_NAMES)
    
    now = datetime.now()
    schedule_enabled = state.get("schedule_enabled", False)
    inside_work_hours = True
    if schedule_enabled:
        inside_work_hours = is_inside_hours(now, state.get("work_start", "09:00"), state.get("work_end", "18:00"))
        
    if schedule_enabled and not inside_work_hours and state.get("paused", False):
        color = COLOR_MUTED
    elif running:
        color = COLOR_GREEN
    else:
        cooldown_active, _ = get_cooldown_status(state)
        if cooldown_active:
            color = COLOR_RED
        else:
            color = COLOR_BLUE
        
    status_text = get_status_text(state, running)
    
    icon = pystray.Icon(
        "tg_limiter",
        create_image(color),
        f"Telegram Limiter\nStatus: {status_text}",
        menu=get_menu(state, running)
    )
    
    threading.Thread(target=run_daemon, daemon=True).start()
    icon.run()

