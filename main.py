"""
telegram_limiter.py

Limits the use of Desktop Apps.
Uses tray icon by default. Launches Textual TUI console windows for interactive actions.
"""

import argparse
import secrets
import json
import os
import sys
from datetime import datetime, timedelta
from config import OVERRIDE_STRING_LEN, OVERRIDE_FILE, COOLDOWN_MIN, SESSION_MAX_MIN, OVERRIDE_SESSION_MAX_MIN
from state_manager import log_event, load_state, save_state, is_inside_hours, get_cooldown_status
from tray import start_tray

from textual.app import App, ComposeResult
from textual.widgets import Label, Input, Button, Static, Switch, TabbedContent, TabPane, Tabs
from textual.containers import Vertical, Horizontal

class MainMenuApp(App):
    CSS = """
    Screen {
        align: center middle;
        background: #1e1e2e;
    }
    
    #container {
        width: 75;
        height: 28;
        border: solid #89b4fa;
        background: #11111b;
        padding: 1 2;
    }
    
    .title {
        text-align: center;
        text-style: bold;
        color: #89b4fa;
        margin-bottom: 0;
    }
    
    TabbedContent {
        height: 20;
    }
    
    /* Dashboard Tab Styling */
    .dash-status-box {
        background: #313244;
        color: #cdd6f4;
        padding: 1 2;
        border: tall #313244;
        margin-bottom: 0;
        height: 7;
        margin-top: 1;
    }
    
    .dash-btn-row {
        layout: horizontal;
        height: 3;
        align: center middle;
        margin-top: 1;
    }
    
    .dash-btn {
        width: 32;
        margin: 0 1;
        border: none;
    }
    
    #dash_force_btn {
        background: #f38ba8;
        color: #11111b;
    }
    
    #dash_override_btn {
        background: #a6e3a1;
        color: #11111b;
    }
    
    /* Schedule Tab Styling */
    .schedule-container {
        margin-top: 1;
    }
    
    .schedule-row {
        layout: horizontal;
        height: 3;
        align: left middle;
        margin-bottom: 0;
    }
    
    .schedule-label {
        width: 25;
        color: #cdd6f4;
        content-align: left middle;
    }
    
    .schedule-input {
        width: 25;
        background: #313244;
        color: #cdd6f4;
        border: tall #313244;
    }
    
    .schedule-switch {
        margin-left: 0;
    }
    
    #save_schedule_btn {
        width: 100%;
        background: #a6e3a1;
        color: #11111b;
        margin-top: 1;
        border: none;
    }
    
    .schedule-msg {
        text-align: center;
        text-style: bold;
        color: #a6e3a1;
    }
    
    /* Stats Tab Styling */
    #nav-container {
        layout: horizontal;
        height: 3;
        align: center middle;
        margin-bottom: 1;
        margin-top: 1;
    }
    
    .nav-btn {
        width: 8;
        height: 3;
        background: #89b4fa;
        color: #11111b;
        border: none;
        margin: 0;
    }
    
    #date_label {
        width: 1fr;
        height: 3;
        text-align: center;
        text-style: bold;
        color: #89b4fa;
        content-align: center middle;
        margin: 0;
    }
    
    .stats-box {
        background: #313244;
        color: #cdd6f4;
        padding: 1 2;
        border: tall #313244;
        margin-bottom: 1;
        height: 11;
    }
    
    /* Override Tab Styling */
    .instruction {
        text-align: center;
        color: #a6adc8;
        margin-top: 1;
        margin-bottom: 1;
    }
    
    .challenge {
        text-align: center;
        background: #313244;
        color: #f9e2af;
        padding: 1 2;
        border: tall #313244;
        margin-bottom: 1;
        text-style: bold;
    }
    
    .error-msg {
        color: #f38ba8;
        text-align: center;
        margin-bottom: 1;
        text-style: bold;
    }
    
    .success-msg {
        color: #a6e3a1;
        text-align: center;
        margin-bottom: 1;
        text-style: bold;
    }
    
    #override_input {
        background: #313244;
        color: #cdd6f4;
        border: tall #313244;
        margin-bottom: 1;
    }
    
    #submit_override_btn {
        width: 100%;
        background: #a6e3a1;
        color: #11111b;
        border: none;
    }
    
    #close_window_btn {
        width: 100%;
        background: #f38ba8;
        color: #11111b;
        border: none;
    }
    """
    
    def __init__(self, events, initial_tab="dashboard", **kwargs):
        super().__init__(**kwargs)
        self.events = events
        self.initial_tab = initial_tab
        self.state = load_state()
        self.challenge = secrets.token_urlsafe(OVERRIDE_STRING_LEN)[:OVERRIDE_STRING_LEN]
        self.success = False
        self.last_override_value = ""
        
        self.daily_data = {}
        self.active_days = []
        self.current_index = 0
        
        # Group events by day
        for event in self.events:
            ts = event.get("ts")
            if not ts:
                continue
            date_str = ts[:10]
            if date_str not in self.daily_data:
                self.daily_data[date_str] = {
                    "total_events": 0,
                    "session_started": 0,
                    "blocked_cooldown": 0,
                    "override_granted": 0,
                    "override_failed": 0,
                    "session_ended_manually": 0
                }
            
            self.daily_data[date_str]["total_events"] += 1
            
            evt = event.get("event")
            if evt == "session_started":
                self.daily_data[date_str]["session_started"] += 1
            elif evt == "blocked_cooldown":
                self.daily_data[date_str]["blocked_cooldown"] += 1
            elif evt == "override_granted":
                self.daily_data[date_str]["override_granted"] += 1
            elif evt == "override_failed":
                self.daily_data[date_str]["override_failed"] += 1
            elif evt == "session_ended_manually":
                self.daily_data[date_str]["session_ended_manually"] += 1
                
        self.active_days = sorted(list(self.daily_data.keys()))
        self.current_index = len(self.active_days) - 1

    def compose(self) -> ComposeResult:
        with Vertical(id="container"):
            yield Label("WELLBEING CONTROL CENTER", classes="title")
            with TabbedContent(initial=self.initial_tab):
                with TabPane("Dashboard", id="dashboard"):
                    yield Static("", id="dash_status_box", classes="dash-status-box")
                    with Horizontal(classes="dash-btn-row"):
                        yield Button("Force End Session", id="dash_force_btn", classes="dash-btn")
                        yield Button("Trigger Override", id="dash_override_btn", classes="dash-btn")
                with TabPane("Schedule Settings", id="schedule"):
                    with Vertical(classes="schedule-container"):
                        with Horizontal(classes="schedule-row"):
                            yield Label("Enable Schedule:", classes="schedule-label")
                            yield Switch(value=self.state.get("schedule_enabled", False), id="schedule_switch", classes="schedule-switch")
                        with Horizontal(classes="schedule-row"):
                            yield Label("Work Start Time:", classes="schedule-label")
                            yield Input(value=self.state.get("work_start", "09:00"), id="start_time_input", classes="schedule-input", placeholder="09:00")
                        with Horizontal(classes="schedule-row"):
                            yield Label("Work End Time:", classes="schedule-label")
                            yield Input(value=self.state.get("work_end", "18:00"), id="end_time_input", classes="schedule-input", placeholder="18:00")
                        yield Label("", id="schedule_msg_label", classes="schedule-msg")
                        yield Button("Save Schedule Settings", id="save_schedule_btn")
                with TabPane("Usage Statistics", id="stats"):
                    with Horizontal(id="nav-container"):
                        yield Button("←", id="prev_btn", classes="nav-btn")
                        yield Label("", id="date_label")
                        yield Button("→", id="next_btn", classes="nav-btn")
                    yield Static("", classes="stats-box", id="stats_box")
                with TabPane("Emergency Override", id="override"):
                    yield Label("Type the string below EXACTLY (Copy-paste is disabled):", classes="instruction")
                    yield Static(self.challenge, classes="challenge", id="challenge_box")
                    yield Input(placeholder="Type here...", id="override_input")
                    yield Label("", id="override_msg_label", classes="error-msg")
                    yield Button("Submit Override", id="submit_override_btn")
            yield Button("Close Window", id="close_window_btn")

    def on_mount(self) -> None:
        self.update_dashboard()
        self.update_stats_display()
        self.set_interval(1.0, self.update_dashboard)
        
        if self.initial_tab == "override":
            self.query_one("#override_input", Input).focus()
        elif self.initial_tab == "schedule":
            self.query_one("#start_time_input", Input).focus()
        else:
            self.query_one("#dash_status_box", Static).focus()

    def update_dashboard(self) -> None:
        self.state = load_state()
        from process_monitor import is_running
        from config import PROCESS_NAMES
        running = is_running(PROCESS_NAMES)
        
        status_text = self.get_status_text_display(self.state, running)
        
        cooldown_active, _ = get_cooldown_status(self.state)
        
        try:
            dash_override_btn = self.query_one("#dash_override_btn", Button)
            dash_force_btn = self.query_one("#dash_force_btn", Button)
            dash_override_btn.disabled = not (cooldown_active and not running)
            dash_force_btn.disabled = not running
            
            schedule_enabled = self.state.get("schedule_enabled", False)
            sch_text = "Disabled"
            if schedule_enabled:
                sch_text = f"Enabled ({self.state.get('work_start')} - {self.state.get('work_end')})"
                
            box_text = (
                f" [bold #89b4fa]System Status Dashboard[/]\n\n"
                f"  [#cdd6f4]• Limiter Status:[/] [bold]{status_text}[/]\n"
                f"  [#cdd6f4]• Target App:[/] [bold #89b4fa]{', '.join(PROCESS_NAMES)}[/]\n"
                f"  [#cdd6f4]• Schedule Restrictions:[/] [bold #f9e2af]{sch_text}[/]"
            )
            self.query_one("#dash_status_box", Static).update(box_text)
        except Exception:
            pass

    def get_status_text_display(self, state, running):
        now = datetime.now()
        schedule_enabled = state.get("schedule_enabled", False)
        
        if schedule_enabled:
            inside = is_inside_hours(now, state.get("work_start", "09:00"), state.get("work_end", "18:00"))
            if not inside and state.get("paused", False):
                return "[#a6adc8]Paused (Non-work hours)[/]"
                
        if running:
            limit = OVERRIDE_SESSION_MAX_MIN if state.get("via_override") else SESSION_MAX_MIN
            elapsed = now - state["last_start"]
            remaining = timedelta(minutes=limit) - elapsed
            remaining_sec = max(0, int(remaining.total_seconds()))
            mins, secs = divmod(remaining_sec, 60)
            via = " (Override)" if state.get("via_override") else ""
            return f"[#a6e3a1]Active{via}: {mins:02d}:{secs:02d} left[/]"
        else:
            cooldown_active, remaining = get_cooldown_status(state)
            if cooldown_active:
                remaining_sec = max(0, int(remaining.total_seconds()))
                mins, secs = divmod(remaining_sec, 60)
                return f"[#f38ba8]Cooldown: {mins:02d}:{secs:02d} left[/]"
            else:
                if schedule_enabled and not is_inside_hours(now, state.get("work_start", "09:00"), state.get("work_end", "18:00")):
                    return "[#89b4fa]Ready (Non-work hours)[/]"
                return "[#89b4fa]Ready[/]"

    def go_prev_stats(self) -> None:
        if self.current_index > 0:
            self.current_index -= 1
            self.update_stats_display()
            
    def go_next_stats(self) -> None:
        if self.current_index < len(self.active_days) - 1:
            self.current_index += 1
            self.update_stats_display()
            
    def update_stats_display(self) -> None:
        try:
            stats_box = self.query_one("#stats_box", Static)
            date_label_widget = self.query_one("#date_label", Label)
            prev_btn = self.query_one("#prev_btn", Button)
            next_btn = self.query_one("#next_btn", Button)
        except Exception:
            return
        
        if not self.active_days:
            date_label_widget.update("No Data")
            stats_box.update("[bold #f38ba8]Log is empty.[/]")
            prev_btn.disabled = True
            next_btn.disabled = True
            return
            
        date_str = self.active_days[self.current_index]
        curr = self.daily_data[date_str]
        
        min_date_str = self.active_days[0]
        
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            prev_dt = dt - timedelta(days=1)
            prev_date_str = prev_dt.strftime("%Y-%m-%d")
        except Exception:
            prev_date_str = ""
            
        prev_exists_in_range = prev_date_str >= min_date_str if prev_date_str else False
        
        if prev_exists_in_range and prev_date_str in self.daily_data:
            prev = self.daily_data[prev_date_str]
        else:
            prev = {
                "total_events": 0,
                "session_started": 0,
                "blocked_cooldown": 0,
                "override_granted": 0,
                "override_failed": 0,
                "session_ended_manually": 0
            }
            
        total_curr = curr["total_events"]
        total_prev = prev["total_events"]
        started_curr = curr["session_started"]
        started_prev = prev["session_started"]
        blocked_curr = curr["blocked_cooldown"]
        blocked_prev = prev["blocked_cooldown"]
        override_curr = curr["override_granted"]
        override_prev = prev["override_granted"]
        failed_curr = curr["override_failed"]
        failed_prev = prev["override_failed"]
        manual_curr = curr.get("session_ended_manually", 0)
        manual_prev = prev.get("session_ended_manually", 0)
        
        ratio_curr = (override_curr / started_curr * 100) if started_curr > 0 else 0.0
        ratio_prev = (override_prev / started_prev * 100) if started_prev > 0 else 0.0
        
        def format_change(c, p):
            if not prev_exists_in_range:
                return ""
            if p == 0:
                if c > 0:
                    return " ([#a6e3a1]+100.0%[/])"
                else:
                    return " ([#a6adc8]0.0%[/])"
            change = ((c - p) / p) * 100
            if change > 0:
                return f" ([#a6e3a1]+{change:.1f}%[/])"
            elif change < 0:
                return f" ([#f38ba8]{change:.1f}%[/])"
            else:
                return " ([#a6adc8]0.0%[/])"

        def format_ratio_change(c, p):
            if not prev_exists_in_range:
                return ""
            diff = c - p
            if diff > 0:
                return f" ([#a6e3a1]+{diff:.1f}%[/])"
            elif diff < 0:
                return f" ([#f38ba8]{diff:.1f}%[/])"
            else:
                return " ([#a6adc8]0.0%[/])"

        try:
            date_dt = datetime.strptime(date_str, "%Y-%m-%d").date()
            today = datetime.now().date()
            yesterday = today - timedelta(days=1)
            if date_dt == today:
                date_lbl = f"{date_dt.strftime('%B %d, %Y')} (Today)"
            elif date_dt == yesterday:
                date_lbl = f"{date_dt.strftime('%B %d, %Y')} (Yesterday)"
            else:
                date_lbl = date_dt.strftime('%B %d, %Y')
        except Exception:
            date_lbl = date_str
            
        date_label_widget.update(f"📅 {date_lbl}")
        
        stats_lines = [
            f"  [#cdd6f4]• Total recorded events:[/] [bold #cdd6f4]{total_curr}[/]{format_change(total_curr, total_prev)}",
            f"  [#cdd6f4]• Sessions started:[/] [bold #a6e3a1]{started_curr}[/]{format_change(started_curr, started_prev)}",
            f"  [#cdd6f4]• Blocked attempts (cooldown):[/] [bold #f38ba8]{blocked_curr}[/]{format_change(blocked_curr, blocked_prev)}",
            f"  [#cdd6f4]• Overrides granted:[/] [bold #a6e3a1]{override_curr}[/]{format_change(override_curr, override_prev)}",
            f"  [#cdd6f4]• Failed override attempts:[/] [bold #f38ba8]{failed_curr}[/]{format_change(failed_curr, failed_prev)}",
            f"  [#cdd6f4]• Manual force ends:[/] [bold #f38ba8]{manual_curr}[/]{format_change(manual_curr, manual_prev)}",
            f"  [#cdd6f4]• Percentage via override:[/] [bold #f9e2af]{ratio_curr:.1f}%[/]{format_ratio_change(ratio_curr, ratio_prev)}"
        ]
        
        stats_box.update("\n".join(stats_lines))
        prev_btn.disabled = (self.current_index == 0)
        next_btn.disabled = (self.current_index == len(self.active_days) - 1)

    def on_key(self, event) -> None:
        try:
            active_tab = self.query_one(TabbedContent).active
        except Exception:
            return
            
        focused = self.screen.focused
        is_tabs_focused = isinstance(focused, Tabs)

        if active_tab == "stats" and not is_tabs_focused:
            if event.key == "left":
                self.go_prev_stats()
                event.prevent_default()
            elif event.key == "right":
                self.go_next_stats()
                event.prevent_default()
        
        if event.key == "down":
            self.screen.focus_next()
            event.prevent_default()
        elif event.key == "up":
            self.screen.focus_previous()
            event.prevent_default()
        
        if event.key in ("ctrl+v", "shift+insert"):
            event.prevent_default()
            if active_tab == "override":
                self.query_one("#override_input", Input).value = ""
                msg = self.query_one("#override_msg_label", Label)
                msg.set_classes("error-msg")
                msg.update("[PASTE BLOCKED] Clipboard shortcuts are disabled!")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "override_input":
            new_val = event.value
            old_val = getattr(self, "last_override_value", "")
            if len(new_val) - len(old_val) > 1:
                self.query_one("#override_input", Input).value = ""
                self.last_override_value = ""
                msg = self.query_one("#override_msg_label", Label)
                msg.set_classes("error-msg")
                msg.update("[PASTE DETECTED] Please type manually!")
            else:
                self.last_override_value = new_val

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "override_input":
            self.check_override()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close_window_btn":
            self.exit()
        elif event.button.id == "dash_force_btn":
            from tray import trigger_force_end
            trigger_force_end()
            self.update_dashboard()
        elif event.button.id == "dash_override_btn":
            self.query_one(TabbedContent).active = "override"
        elif event.button.id == "prev_btn":
            self.go_prev_stats()
        elif event.button.id == "next_btn":
            self.go_next_stats()
        elif event.button.id == "submit_override_btn":
            self.check_override()
        elif event.button.id == "save_schedule_btn":
            enabled = self.query_one("#schedule_switch", Switch).value
            start_str = self.query_one("#start_time_input", Input).value.strip()
            end_str = self.query_one("#end_time_input", Input).value.strip()
            
            def validate_time(s):
                try:
                    parts = s.split(':')
                    if len(parts) != 2:
                        return False
                    h, m = int(parts[0]), int(parts[1])
                    return 0 <= h < 24 and 0 <= m < 60
                except Exception:
                    return False
                    
            msg_label = self.query_one("#schedule_msg_label", Label)
            if not validate_time(start_str) or not validate_time(end_str):
                msg_label.update("[#f38ba8]Invalid time format! Use HH:MM (e.g. 09:00)[/]")
            else:
                self.state["schedule_enabled"] = enabled
                self.state["work_start"] = start_str
                self.state["work_end"] = end_str
                self.state["paused"] = False
                save_state(self.state)
                msg_label.update("[#a6e3a1]Settings saved successfully![/]")
                self.update_dashboard()

    def check_override(self) -> None:
        typed = self.query_one("#override_input", Input).value.strip()
        msg = self.query_one("#override_msg_label", Label)
        
        if typed == self.challenge:
            expires_at = datetime.now() + timedelta(minutes=1)
            with open(OVERRIDE_FILE, "w") as f:
                json.dump({"expires_at": expires_at.isoformat(), "used": False}, f)
            log_event("override_granted")
            
            msg.set_classes("success-msg")
            msg.update("[SUCCESS] Access granted! Exiting in 1.2s...")
            self.set_timer(1.2, self.exit)
        else:
            log_event("override_failed")
            msg.set_classes("error-msg")
            msg.update("[FAILED] Mismatch. Try again!")
            self.query_one("#override_input", Input).value = ""


# ---------- CLI Entrypoints ----------

def launch_menu_cli(tab="dashboard"):
    from config import LOG_FILE
    
    events = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except Exception:
                        pass
                        
    app = MainMenuApp(events=events, initial_tab=tab)
    app.run()


def install_startup():
    try:
        startup_dir = os.path.join(os.environ["APPDATA"], r"Microsoft\Windows\Start Menu\Programs\Startup")
        vbs_path = os.path.join(startup_dir, "wellbeing_limiter.vbs")
        
        main_py = os.path.abspath(sys.argv[0])
        pythonw = sys.executable.replace("python.exe", "pythonw.exe")
        
        vbs_content = f'Set WshShell = CreateObject("Wscript.Shell")\nWshShell.Run """{pythonw}"" ""{main_py}""", 0, False'
        
        with open(vbs_path, "w", encoding="utf-8") as f:
            f.write(vbs_content)
        print(f"[SUCCESS] Startup script created at: {vbs_path}")
        print("The app will now run automatically in the background when you log in.")
    except Exception as e:
        print(f"[ERROR] Failed to install startup script: {e}")


def remove_startup():
    try:
        startup_dir = os.path.join(os.environ["APPDATA"], r"Microsoft\Windows\Start Menu\Programs\Startup")
        vbs_path = os.path.join(startup_dir, "wellbeing_limiter.vbs")
        if os.path.exists(vbs_path):
            os.remove(vbs_path)
            print(f"[SUCCESS] Removed startup script from: {vbs_path}")
        else:
            print("Startup script was not installed.")
    except Exception as e:
        print(f"[ERROR] Failed to remove startup script: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--override", action="store_true", help="request emergency access in TUI")
    parser.add_argument("--stats", action="store_true", help="show statistics in TUI")
    parser.add_argument("--menu", action="store_true", help="open main menu in TUI")
    parser.add_argument("--tab", type=str, default="dashboard", help="initial tab to open (dashboard, stats, override, schedule)")
    parser.add_argument("--install-startup", action="store_true", help="install wellbeing limiter to Windows startup")
    parser.add_argument("--remove-startup", action="store_true", help="remove wellbeing limiter from Windows startup")
    args = parser.parse_args()

    if args.menu:
        launch_menu_cli(args.tab)
    elif args.override:
        launch_menu_cli("override")
    elif args.stats:
        launch_menu_cli("stats")
    elif args.install_startup:
        install_startup()
    elif args.remove_startup:
        remove_startup()
    else:
        start_tray()