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
import pyperclip
from datetime import datetime, timedelta
from config import OVERRIDE_STRING_LEN, OVERRIDE_FILE
from state_manager import log_event
from tray import start_tray

from textual.app import App, ComposeResult
from textual.widgets import Label, Input, Button, Static
from textual.containers import Vertical, Horizontal

# ---------- Textual TUI Apps ----------

class OverrideApp(App):
    CSS = """
    Screen {
        align: center middle;
        background: #1e1e2e;
    }
    
    #container {
        width: 65;
        height: auto;
        border: solid #f38ba8;
        background: #11111b;
        padding: 1 2;
    }
    
    .title {
        text-align: center;
        text-style: bold;
        color: #f38ba8;
        margin-bottom: 1;
    }
    
    .instruction {
        text-align: center;
        color: #a6adc8;
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
    
    Input {
        background: #313244;
        color: #cdd6f4;
        border: tall #313244;
        margin-bottom: 1;
    }
    
    Button {
        width: 100%;
        border: none;
    }
    
    #submit_btn {
        background: #a6e3a1;
        color: #11111b;
        margin-bottom: 1;
    }
    
    #quit_btn {
        background: #f38ba8;
        color: #11111b;
    }
    """
    
    def __init__(self, challenge, **kwargs):
        super().__init__(**kwargs)
        self.challenge = challenge
        self.success = False
        self.last_value = ""
        
    def compose(self) -> ComposeResult:
        with Vertical(id="container"):
            yield Label("EMERGENCY OVERRIDE", classes="title")
            yield Label("Type the string below EXACTLY (Copy-paste is disabled):", classes="instruction")
            yield Static(self.challenge, classes="challenge")
            yield Input(placeholder="Type here...", id="input_field")
            yield Label("", id="message_label")
            yield Button("Submit Override", id="submit_btn")
            yield Button("Quit", id="quit_btn")
            
    def on_mount(self) -> None:
        self.query_one("#input_field", Input).focus()

    def on_key(self, event) -> None:
        if event.key in ("ctrl+v", "shift+insert"):
            event.prevent_default()
            self.query_one("#input_field", Input).value = ""
            msg = self.query_one("#message_label", Label)
            msg.set_classes("error-msg")
            msg.update("[PASTE BLOCKED] Clipboard shortcuts are disabled!")
        elif event.key == "down":
            self.screen.focus_next()
        elif event.key == "up":
            self.screen.focus_previous()

    def on_input_changed(self, event: Input.Changed) -> None:
        # Detect paste by verifying if change in length is greater than 1 character
        new_val = event.value
        old_val = getattr(self, "last_value", "")
        if len(new_val) - len(old_val) > 1:
            self.query_one("#input_field", Input).value = ""
            self.last_value = ""
            msg = self.query_one("#message_label", Label)
            msg.set_classes("error-msg")
            msg.update("[PASTE DETECTED] Please type manually!")
        else:
            self.last_value = new_val
            
    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.check_result()
        
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "submit_btn":
            self.check_result()
        elif event.button.id == "quit_btn":
            self.exit_app()
            
    def check_result(self) -> None:
        typed = self.query_one("#input_field", Input).value.strip()
        msg = self.query_one("#message_label", Label)
        
        if typed == self.challenge:
            self.success = True
            msg.set_classes("success-msg")
            msg.update("[SUCCESS] Access granted! Exiting...")
            self.set_timer(1.2, self.exit_app)
        else:
            msg.set_classes("error-msg")
            msg.update("[FAILED] Mismatch. Try again!")
            self.query_one("#input_field", Input).value = ""
            
    def exit_app(self) -> None:
        self.exit(self.success)


class StatsApp(App):
    CSS = """
    Screen {
        align: center middle;
        background: #1e1e2e;
    }
    
    #container {
        width: 65;
        height: auto;
        border: solid #89b4fa;
        background: #11111b;
        padding: 1 2;
    }
    
    .title {
        text-align: center;
        text-style: bold;
        color: #89b4fa;
        margin-bottom: 1;
    }
    
    #nav-container {
        layout: horizontal;
        height: 3;
        align: center middle;
        margin-bottom: 1;
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
    
    #close_btn {
        width: 100%;
        background: #f38ba8;
        color: #11111b;
        border: none;
    }
    """
    
    def __init__(self, events, **kwargs):
        super().__init__(**kwargs)
        self.events = events
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
        self.current_index = len(self.active_days) - 1 # Default to latest day

    def compose(self) -> ComposeResult:
        with Vertical(id="container"):
            yield Label("USAGE STATISTICS", classes="title")
            with Horizontal(id="nav-container"):
                yield Button("←", id="prev_btn", classes="nav-btn")
                yield Label("", id="date_label")
                yield Button("→", id="next_btn", classes="nav-btn")
            yield Static("", classes="stats-box")
            yield Button("Close Window", id="close_btn")
            
    def on_mount(self) -> None:
        self.update_display()
        self.query_one("#close_btn", Button).focus()
        
    def go_prev(self) -> None:
        if self.current_index > 0:
            self.current_index -= 1
            self.update_display()
            
    def go_next(self) -> None:
        if self.current_index < len(self.active_days) - 1:
            self.current_index += 1
            self.update_display()
            
    def on_key(self, event) -> None:
        if event.key == "left":
            self.go_prev()
        elif event.key == "right":
            self.go_next()
        elif event.key == "down":
            self.screen.focus_next()
        elif event.key == "up":
            self.screen.focus_previous()
            
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "prev_btn":
            self.go_prev()
        elif event.button.id == "next_btn":
            self.go_next()
        elif event.button.id == "close_btn":
            self.exit()
            
    def update_display(self) -> None:
        if not self.active_days:
            self.query_one("#date_label", Label).update("No Data")
            self.query_one(".stats-box", Static).update("[bold #f38ba8]Log is empty.[/]")
            self.query_one("#prev_btn", Button).disabled = True
            self.query_one("#next_btn", Button).disabled = True
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
        
        attempts_curr = override_curr + failed_curr
        attempts_prev = override_prev + failed_prev
        
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
                date_label = f"{date_dt.strftime('%B %d, %Y')} (Today)"
            elif date_dt == yesterday:
                date_label = f"{date_dt.strftime('%B %d, %Y')} (Yesterday)"
            else:
                date_label = date_dt.strftime('%B %d, %Y')
        except Exception:
            date_label = date_str
            
        self.query_one("#date_label", Label).update(f"📅 {date_label}")
        
        stats_lines = [
            f"  [#cdd6f4]• Total recorded events:[/] [bold #cdd6f4]{total_curr}[/]{format_change(total_curr, total_prev)}",
            f"  [#cdd6f4]• Sessions started:[/] [bold #a6e3a1]{started_curr}[/]{format_change(started_curr, started_prev)}",
            f"  [#cdd6f4]• Blocked attempts (cooldown):[/] [bold #f38ba8]{blocked_curr}[/]{format_change(blocked_curr, blocked_prev)}",
            f"  [#cdd6f4]• Overrides granted:[/] [bold #a6e3a1]{override_curr}[/]{format_change(override_curr, override_prev)}",
            f"  [#cdd6f4]• Failed override attempts:[/] [bold #f38ba8]{failed_curr}[/]{format_change(failed_curr, failed_prev)}",
            f"  [#cdd6f4]• Manual force ends:[/] [bold #f38ba8]{manual_curr}[/]{format_change(manual_curr, manual_prev)}",
            f"  [#cdd6f4]• Percentage via override:[/] [bold #f9e2af]{ratio_curr:.1f}%[/]{format_ratio_change(ratio_curr, ratio_prev)}"
        ]
        
        self.query_one(".stats-box", Static).update("\n".join(stats_lines))
        self.query_one("#prev_btn", Button).disabled = (self.current_index == 0)
        self.query_one("#next_btn", Button).disabled = (self.current_index == len(self.active_days) - 1)


# ---------- CLI Entrypoints ----------

def request_override_cli():
    challenge = secrets.token_urlsafe(OVERRIDE_STRING_LEN)[:OVERRIDE_STRING_LEN]
    app = OverrideApp(challenge)
    success = app.run()
    
    if success:
        expires_at = datetime.now() + timedelta(minutes=1)
        with open(OVERRIDE_FILE, "w") as f:
            json.dump({"expires_at": expires_at.isoformat(), "used": False}, f)
        log_event("override_granted")


def show_stats_cli():
    from config import LOG_FILE
    
    if not os.path.exists(LOG_FILE):
        events = []
    else:
        events = []
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except Exception:
                        pass
                        
    app = StatsApp(events)
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
    parser.add_argument("--install-startup", action="store_true", help="install wellbeing limiter to Windows startup")
    parser.add_argument("--remove-startup", action="store_true", help="remove wellbeing limiter from Windows startup")
    args = parser.parse_args()

    if args.override:
        request_override_cli()
    elif args.stats:
        show_stats_cli()
    elif args.install_startup:
        install_startup()
    elif args.remove_startup:
        remove_startup()
    else:
        start_tray()