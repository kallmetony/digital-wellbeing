import os

APPDATA = os.environ.get("APPDATA", ".")
STATE_FILE = os.path.join(APPDATA, "tg_limiter_state.json")
LOG_FILE = os.path.join(APPDATA, "tg_limiter_log.jsonl")
OVERRIDE_FILE = os.path.join(APPDATA, "tg_limiter_override.json")

PROCESS_NAME = "Telegram.exe"
COOLDOWN_MIN = 15
SESSION_MAX_MIN = 5
OVERRIDE_SESSION_MAX_MIN = 5
POLL_INTERVAL_SEC = 5
OVERRIDE_STRING_LEN = 40

# Theme Colors (Catppuccin Mocha)
COLOR_BG = "#1e1e2e"
COLOR_SURFACE = "#313244"
COLOR_TEXT = "#cdd6f4"
COLOR_MUTED = "#a6adc8"
COLOR_RED = "#f38ba8"
COLOR_GREEN = "#a6e3a1"
COLOR_BLUE = "#89b4fa"
COLOR_YELLOW = "#f9e2af"
COLOR_TEAL = "#94e2d5"
COLOR_CRUST = "#11111b"
