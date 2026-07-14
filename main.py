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
from textual.containers import Vertical

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
    
    .stats-box {
        background: #313244;
        color: #cdd6f4;
        padding: 1 2;
        border: tall #313244;
        margin-bottom: 1;
    }
    
    Button {
        width: 100%;
        background: #f38ba8;
        color: #11111b;
        border: none;
    }
    """
    
    def __init__(self, stats_text, **kwargs):
        super().__init__(**kwargs)
        self.stats_text = stats_text
        
    def compose(self) -> ComposeResult:
        with Vertical(id="container"):
            yield Label("USAGE STATISTICS", classes="title")
            yield Static(self.stats_text, classes="stats-box")
            yield Button("Close Window", id="close_btn")
            
    def on_mount(self) -> None:
        self.query_one("#close_btn", Button).focus()
            
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close_btn":
            self.exit()

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
        stats_text = "[bold #f38ba8]Log is empty - no events recorded yet.[/]"
    else:
        events = []
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))

        if not events:
            stats_text = "[bold #f38ba8]Log is empty.[/]"
        else:
            counts = {}
            for e in events:
                counts[e["event"]] = counts.get(e["event"], 0) + 1

            first_ts = events[0]["ts"]
            last_ts = events[-1]["ts"]

            try:
                first_dt = datetime.fromisoformat(first_ts).strftime("%Y-%m-%d %H:%M")
                last_dt = datetime.fromisoformat(last_ts).strftime("%Y-%m-%d %H:%M")
            except Exception:
                first_dt = first_ts
                last_dt = last_ts

            blocked = counts.get("blocked_cooldown", 0)
            started = counts.get("session_started", 0)
            overrides = counts.get("override_granted", 0)
            overrides_failed = counts.get("override_failed", 0)
            ratio = (overrides / started * 100) if started > 0 else 0.0

            stats_lines = [
                f"[#a6adc8]Period:[/] [#89b4fa]{first_dt}[/] to [#89b4fa]{last_dt}[/]",
                f"[#a6adc8]Total recorded events:[/] [#cdd6f4]{len(events)}[/]",
                "",
                "[bold #89b4fa]Event Breakdown:[/]",
                f"  [#cdd6f4]• Sessions started:[/] [bold #a6e3a1]{started}[/]",
                f"  [#cdd6f4]• Blocked attempts (cooldown):[/] [bold #f38ba8]{blocked}[/]",
                f"  [#cdd6f4]• Overrides granted:[/] [bold #a6e3a1]{overrides}[/]",
                f"  [#cdd6f4]• Failed override attempts:[/] [bold #f38ba8]{overrides_failed}[/]",
                f"  [#cdd6f4]• Percentage via override:[/] [bold #f9e2af]{ratio:.1f}%[/]"
            ]
            stats_text = "\n".join(stats_lines)
            
    app = StatsApp(stats_text)
    app.run()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--override", action="store_true", help="request emergency access in TUI")
    parser.add_argument("--stats", action="store_true", help="show statistics in TUI")
    args = parser.parse_args()

    if args.override:
        request_override_cli()
    elif args.stats:
        show_stats_cli()
    else:
        start_tray()