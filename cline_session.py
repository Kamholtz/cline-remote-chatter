import os
import pty
import select
import shlex
import subprocess
import threading
import time
import re
from collections import deque

import psutil
from bot_logging import (
    DEBUG_DEBUG,
    DEBUG_ERROR,
    DEBUG_INFO,
    DEBUG_WARN,
    debug_log,
    log_chat_history_event,
    strip_ansi_codes,
)
from parsing_diff_tracer import get_tracer

CLINE_COMMAND = os.getenv("CLINE_COMMAND", "cline")
if isinstance(CLINE_COMMAND, str):
    CLINE_COMMAND = shlex.split(CLINE_COMMAND)
if not CLINE_COMMAND:
    CLINE_COMMAND = ["cline"]


class ClineSession:
    """Manage the PTY-backed cline process and deliver cleaned output."""

    def __init__(self, output_callback=None):
        self.master_fd = None
        self.slave_fd = None
        self.process = None
        self.child_pids = set()
        self.session_active = False
        self.is_running = False

        self.output_queue = deque()
        self.output_thread = None
        self.stop_reading = False

        self.waiting_for_input = False
        self.input_prompt = ""
        self.current_command = None

        self.output_callback = output_callback
        self.command_queue = deque()

        debug_log(
            DEBUG_INFO,
            "ClineSession initialized",
            cline_command=CLINE_COMMAND,
        )

    def _find_child_processes(self, parent_pid):
        children = set()
        try:
            parent = psutil.Process(parent_pid)
            for child in parent.children(recursive=True):
                children.add(child.pid)
            children.add(parent_pid)
        except psutil.NoSuchProcess:
            pass
        return children

    def _kill_process_tree(self, pid):
        try:
            children = self._find_child_processes(pid)
            debug_log(DEBUG_DEBUG, "Killing process tree", parent_pid=pid, children=list(children))
            for child_pid in children:
                try:
                    psutil.Process(child_pid).terminate()
                except psutil.NoSuchProcess:
                    continue
            time.sleep(0.5)
            for child_pid in children:
                try:
                    proc = psutil.Process(child_pid)
                    if proc.is_running():
                        proc.kill()
                except psutil.NoSuchProcess:
                    pass
            time.sleep(0.2)
            debug_log(DEBUG_DEBUG, "Process tree killed", parent_pid=pid)
        except Exception as exc:
            debug_log(
                DEBUG_ERROR,
                "Error killing process tree",
                pid=pid,
                error_type=type(exc).__name__,
                error=str(exc),
            )

    def _ensure_session_clean(self):
        cline_processes = []
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                cmd = proc.info["cmdline"] or []
                cmdline_str = " ".join(cmd)
                if "cline" in cmdline_str and "python" not in cmdline_str:
                    cline_processes.append(proc.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        if cline_processes:
            debug_log(DEBUG_WARN, "Existing cline processes found", pids=cline_processes)
            for pid in cline_processes:
                self._kill_process_tree(pid)
            time.sleep(1)
            debug_log(DEBUG_INFO, "Cleaned up existing cline processes")
        else:
            debug_log(DEBUG_DEBUG, "No existing cline processes detected")

    def start(self) -> bool:
        if self.session_active:
            debug_log(DEBUG_WARN, "Session already active - skipping start")
            return False
        self._ensure_session_clean()
        try:
            self.master_fd, self.slave_fd = pty.openpty()
            env = dict(os.environ, TERM="xterm-256color", COLUMNS="80", LINES="24")
            self.process = subprocess.Popen(
                CLINE_COMMAND,
                stdin=self.slave_fd,
                stdout=self.slave_fd,
                stderr=self.slave_fd,
                preexec_fn=os.setsid,
                env=env,
            )
            self.child_pids = {self.process.pid}
            time.sleep(0.5)
            if self.process.poll() is not None:
                raise RuntimeError("Cline process exited immediately")
            self.is_running = True
            self.session_active = True
            self.stop_reading = False
            self.output_thread = threading.Thread(target=self._output_reader, daemon=True)
            self.output_thread.start()
            debug_log(DEBUG_INFO, "Cline session started", pid=self.process.pid)
            time.sleep(1)
            return True
        except Exception as exc:
            debug_log(
                DEBUG_ERROR,
                "Failed to start cline session",
                error_type=type(exc).__name__,
                error=str(exc),
            )
            self._cleanup_resources()
            return False

    def stop(self):
        self.stop_reading = True
        self.session_active = False
        if self.process:
            self._kill_process_tree(self.process.pid)
        if self.output_thread and self.output_thread.is_alive():
            self.output_thread.join(timeout=2.0)
        self._cleanup_file_descriptors()
        self.process = None
        self.child_pids.clear()
        self.is_running = False
        self.waiting_for_input = False
        self.input_prompt = ""
        self.command_queue = deque()
        self.output_queue.clear()
        debug_log(DEBUG_INFO, "Cline session stopped")

    def _cleanup_file_descriptors(self):
        if self.master_fd:
            try:
                os.close(self.master_fd)
            except Exception as exc:
                debug_log(DEBUG_ERROR, "Error closing master FD", error=str(exc))
            self.master_fd = None
        if self.slave_fd:
            try:
                os.close(self.slave_fd)
            except Exception as exc:
                debug_log(DEBUG_ERROR, "Error closing slave FD", error=str(exc))
            self.slave_fd = None

    def _cleanup_resources(self):
        self.stop_reading = True
        if self.process:
            self._kill_process_tree(self.process.pid)
            self.process = None
        self._ensure_session_clean()
        self._cleanup_file_descriptors()
        self.is_running = False
        self.session_active = False
        self.child_pids.clear()
        self.output_queue.clear()
        self.command_queue.clear()

    def _output_reader(self):
        read_count = 0
        error_count = 0
        while not self.stop_reading and self.is_running:
            try:
                ready, _, _ = select.select([self.master_fd], [], [], 0.1)
                if ready:
                    data = os.read(self.master_fd, 4096)
                    if not data:
                        debug_log(DEBUG_WARN, "PTY closed")
                        break
                    read_count += 1
                    self._process_output(data.decode("utf-8", errors="replace"))
                else:
                    time.sleep(0.05)
            except Exception as exc:
                error_count += 1
                if error_count > 10:
                    debug_log(DEBUG_ERROR, "Too many read errors, stopping reader", errors=error_count)
                    break
                time.sleep(0.1)
        debug_log(DEBUG_INFO, "Output reader stopped", total_reads=read_count, total_errors=error_count)

    def _process_output(self, output):
        clean_output = strip_ansi_codes(output)
        tracer = get_tracer()
        ui_indicators = [
            "╭",
            "╰",
            "│",
            "┃",
            "╮",
            "╯",
            "cline cli preview",
            "/plan or /act",
            "alt+enter",
            "openrouter/xiaomi",
            "~/cline-workspace",
            "enter submit",
            "new line",
            "open editor",
        ]
        ui_score = sum(1 for indicator in ui_indicators if indicator in clean_output)
        lines = clean_output.split("\n")
        empty_lines = sum(1 for line in lines if not line.strip())
        is_welcome_screen = "cline cli preview" in clean_output and "openrouter/xiaomi" in clean_output
        is_ui_heavy = ui_score >= 2 and not is_welcome_screen
        is_ui_heavy = is_ui_heavy or (lines and empty_lines / len(lines) > 0.5)
        is_box_char = clean_output.strip() in ["╭", "╰", "│", "┃", "╮", "╯"]
        is_box_line = bool(re.match(r"^[\s│┃╭╰╮╯]+$", clean_output.strip()))
        api_patterns = [
            r"## API request completed",
            r"↑.*↓.*\$",
            r"Tokens:.*Prompt:.*Completion:",
            r"Cost:.*\$",
            r"Elapsed:.*s",
        ]
        is_api_metadata = any(re.search(pat, clean_output, re.IGNORECASE) for pat in api_patterns)
        is_command_echo = False
        if self.current_command and self.current_command not in ["/plan", "/act"]:
            pattern = r"^[\s│┃]*" + re.escape(self.current_command) + r"[\s│┃]*$"
            if re.match(pattern, clean_output.strip()):
                is_command_echo = True
        is_mode_switch_confirmation = False
        if self.current_command in ["/plan", "/act"]:
            mode_indicators = ["switch to plan mode", "switch to act mode", "plan mode", "act mode"]
            if any(ind in clean_output.lower() for ind in mode_indicators):
                is_mode_switch_confirmation = True
        filters_matched = []
        if is_ui_heavy:
            filters_matched.append("is_ui_heavy")
        if is_box_char:
            filters_matched.append("is_box_char")
        if is_box_line:
            filters_matched.append("is_box_line")
        if is_api_metadata:
            filters_matched.append("is_api_metadata")
        if is_command_echo:
            filters_matched.append("is_command_echo")
        if (
            not is_welcome_screen
            and not is_mode_switch_confirmation
            and any([is_ui_heavy, is_box_char, is_box_line, is_api_metadata, is_command_echo])
        ):
            if clean_output.strip():
                debug_log(DEBUG_DEBUG, "Filtered UI/metadata", preview=clean_output[:30].replace("\n", "\\n"))
                tracer.log_diff(before=clean_output, after="", filters_applied=filters_matched)
                self._record_output_history(output, clean_output, "", filters_matched, len(self.output_queue), True)
            return
        if clean_output.strip() and len(clean_output) > 20:
            debug_log(DEBUG_DEBUG, "Queued output", preview=clean_output[:50].replace("\n", "\\n"))
        prompt_patterns = [
            r"\[y/N\]",
            r"\[Y/n\]",
            r"\(y/n\)",
            r"\(Y/N\)",
            r"Continue\?",
            r"Proceed\?",
            r"Are you sure\?",
            r"Enter .*:\s*$",
            r"Password:\s*$",
            r"Press.*Enter.*to.*continue",
            r"Press.*any.*key",
            r"\[.*\]\s*$",
            r"Press.*to.*exit",
            r"Press.*to.*return",
        ]
        prompt_detected = False
        for pattern in prompt_patterns:
            if re.search(pattern, clean_output, re.IGNORECASE):
                self.waiting_for_input = True
                self.input_prompt = clean_output.strip()
                prompt_detected = True
                debug_log(DEBUG_INFO, "Interactive prompt detected", prompt=self.input_prompt[:50])
                break
        if not prompt_detected and re.search(r"[\[\(].*[\]\)]\s*$", clean_output.strip()):
            self.waiting_for_input = True
            self.input_prompt = clean_output.strip()
            prompt_detected = True
            debug_log(DEBUG_INFO, "Continuation prompt detected", prompt_preview=clean_output[:50])
        if not prompt_detected and self.waiting_for_input:
            debug_log(DEBUG_DEBUG, "Output while waiting for input")
        self.output_queue.append(clean_output)
        debug_log(DEBUG_DEBUG, "Added output to queue", queue_size=len(self.output_queue))
        self._record_output_history(output, clean_output, clean_output, filters_matched, len(self.output_queue), False)
        tracer.log_diff(
            before=clean_output,
            after=clean_output,
            filters_applied=None if not filters_matched else filters_matched,
            queue_size=len(self.output_queue),
            current_command=self.current_command,
        )
        if self.output_callback and clean_output.strip():
            try:
                self.output_callback(clean_output)
            except Exception as exc:
                debug_log(
                    DEBUG_ERROR,
                    "Output callback failed",
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
        if len(self.output_queue) > 100:
            self.output_queue.popleft()
            debug_log(DEBUG_WARN, "Output queue overflow, trimming oldest")

    def _record_output_history(self, raw_output, clean_output, final_output, filters, queue_size, filtered_out):
        log_chat_history_event(
            {
                "type": "output",
                "direction": "outbound",
                "current_command": self.current_command,
                "filtered_out": filtered_out,
                "filters_applied": filters or [],
                "queue_size": queue_size,
                "raw_output": raw_output,
                "clean_output": clean_output,
                "final_output": final_output,
                "raw_length": len(raw_output),
                "clean_length": len(clean_output),
                "final_length": len(final_output),
                "session_active": self.session_active,
            }
        )

    def send_command(self, command: str) -> str:
        if not self.is_running:
            return "Error: session not running"
        old_waiting = self.waiting_for_input
        self.waiting_for_input = False
        self.input_prompt = ""
        self.current_command = command
        submission_methods = (
            f"{command}\n",
            f"{command}\r",
            f"{command}\r\n",
            f"{command}\x04",
        )
        try:
            for index, method in enumerate(submission_methods):
                os.write(self.master_fd, method.encode())
                time.sleep(0.3)
                if len(self.output_queue) > 0:
                    break
            debug_log(DEBUG_INFO, "Command sent", command=command)
            return "Command sent"
        except Exception as exc:
            debug_log(
                DEBUG_ERROR,
                "Failed to write command",
                command=command,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            self.waiting_for_input = old_waiting
            return f"Error sending command: {exc}"

    def send_enter(self) -> bool:
        if not self.is_running:
            return False
        try:
            os.write(self.master_fd, b"\n")
            time.sleep(0.2)
            return True
        except Exception as exc:
            debug_log(DEBUG_ERROR, "Failed to send Enter", error=str(exc))
            return False

    def get_pending_output(self, max_length=4000):
        if not self.output_queue:
            return None
        combined = ""
        while self.output_queue and len(combined) < max_length:
            chunk = self.output_queue.popleft()
            if len(combined) + len(chunk) > max_length:
                self.output_queue.appendleft(chunk)
                break
            combined += chunk
        result = combined.strip()
        debug_log(
            DEBUG_DEBUG,
            "Prepared pending output",
            len=len(result),
            queue_size=len(self.output_queue),
        )
        return result

    def is_waiting_for_input(self) -> bool:
        return self.waiting_for_input
