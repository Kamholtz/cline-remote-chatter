#!/usr/bin/env python3
"""
Utility to replay the chat history log with diff-style output.

Reads newline-delimited JSON entries written by `cline_telegram_bot.py`
and emits the same diffing diagnostics provided by `parsing_diff_tracer`.
"""

import argparse
import json
from pathlib import Path
from typing import List

from parsing_diff_tracer import ParsingDiffTracer


DEFAULT_HISTORY_FILE = Path("chat_history.jsonl")


def load_history(path: Path) -> List[dict]:
    """Load each JSON entry from the history file."""
    entries = []

    with path.open(encoding="utf-8") as stream:
        for idx, line in enumerate(stream, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"Skipping invalid JSON entry {idx}: {exc}")

    return entries


def print_user_input(entry: dict) -> None:
    """Print a recorded user input event."""
    timestamp = entry.get("timestamp", "")
    authorized = entry.get("authorized", False)
    status = "authorized" if authorized else "unauthorized"
    message_id = entry.get("message_id")
    header_parts = [f"[{timestamp}] USER INPUT ({status})"]

    if message_id is not None:
        header_parts.append(f"message_id={message_id}")

    print(" ".join(header_parts))
    text = entry.get("text", "")
    print(text or "<empty message>")
    print()


def print_output(entry: dict, tracer: ParsingDiffTracer) -> None:
    """Replay an output entry via the diff tracer."""
    timestamp = entry.get("timestamp", "")
    filtered = entry.get("filtered_out", False)
    status = "filtered" if filtered else "queued"
    command = entry.get("current_command")
    queue = entry.get("queue_size")
    header_parts = [f"[{timestamp}] OUTPUT ({status})"]

    if command:
        header_parts.append(f"cmd={command}")

    if queue is not None:
        header_parts.append(f"queue={queue}")

    print(" ".join(header_parts))
    tracer.log_diff(
        before=entry.get("clean_output", ""),
        after=entry.get("final_output", entry.get("clean_output", "")),
        filters_applied=entry.get("filters_applied"),
        queue_size=queue or 0,
        current_command=command,
    )
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay the chat history log with parsing diffs."
    )
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=DEFAULT_HISTORY_FILE,
        help="Path to the chat history log (default: %(default)s)",
    )
    args = parser.parse_args()
    history_file = args.path

    if not history_file.exists():
        print(f"History file not found: {history_file}")
        return

    tracer = ParsingDiffTracer(enabled=True)
    entries = load_history(history_file)

    if not entries:
        print("No chat history entries found.")
        return

    for entry in entries:
        entry_type = entry.get("type")
        if entry_type == "user_input":
            print_user_input(entry)
        elif entry_type == "output":
            print_output(entry, tracer)
        else:
            print(f"[{entry.get('timestamp', '')}] Unknown entry type: {entry_type}")
            print(json.dumps(entry, indent=2))
            print()


if __name__ == "__main__":
    main()
