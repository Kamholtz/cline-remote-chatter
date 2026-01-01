import json
import os
import re
import threading
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

CHAT_HISTORY_FILE = os.getenv("CHAT_HISTORY_FILE", "chat_history.jsonl")
_HISTORY_LOCK = threading.Lock()

DEBUG_INFO = "INFO"
DEBUG_WARN = "WARN"
DEBUG_ERROR = "ERROR"
DEBUG_DEBUG = "DEBUG"


def strip_ansi_codes(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    ansi_pattern = r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])'
    return re.sub(ansi_pattern, "", text)


def debug_log(level: str, message: str, **kwargs) -> None:
    """Write a timestamped debug entry."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    prefix = f"[{timestamp}] [{level}]"
    if kwargs:
        context = " | ".join(f"{k}={v}" for k, v in kwargs.items())
        print(f"{prefix} {message} | {context}")
    else:
        print(f"{prefix} {message}")


def log_chat_history_event(event: dict) -> None:
    """Persist a high-level event for later auditing."""
    entry = {"timestamp": datetime.utcnow().isoformat() + "Z", **event}
    try:
        with _HISTORY_LOCK, open(CHAT_HISTORY_FILE, "a", encoding="utf-8") as history_file:
            json.dump(entry, history_file, ensure_ascii=False)
            history_file.write("\n")
    except Exception as exc:
        debug_log(
            DEBUG_ERROR,
            "Failed to persist chat history",
            file=CHAT_HISTORY_FILE,
            error_type=type(exc).__name__,
            error=str(exc),
        )
