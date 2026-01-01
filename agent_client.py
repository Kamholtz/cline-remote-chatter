import asyncio
import os
import shlex
import sys
from collections import deque
from pathlib import Path
from typing import Any, Deque, Iterable, Optional, Tuple

from acp import PROTOCOL_VERSION, spawn_agent_process, text_block
from acp.interfaces import Client
from acp.schema import (
    CreateTerminalRequest,
    CreateTerminalResponse,
    KillTerminalCommandRequest,
    KillTerminalCommandResponse,
    PermissionOption,
    RequestPermissionResponse,
    ReleaseTerminalRequest,
    ReleaseTerminalResponse,
    TerminalOutputRequest,
    TerminalOutputResponse,
    WaitForTerminalExitRequest,
    WaitForTerminalExitResponse,
)

from bot_logging import log_chat_history_event


CLINE_AGENT_SCRIPT = Path(__file__).parent / "cline_acp_agent.py"
CODEX_AGENT_SCRIPT = Path(__file__).parent / "codex_acp_agent_launcher.py"
DEFAULT_AGENT_TYPE = os.getenv("ACP_AGENT_TYPE", "cline").strip().lower()
CUSTOM_AGENT_COMMAND = os.getenv("ACP_AGENT_COMMAND")

AGENT_COMMANDS = {
    "cline": (sys.executable, str(CLINE_AGENT_SCRIPT)),
    "codex": (sys.executable, str(CODEX_AGENT_SCRIPT)),
}


class TelegramACPClient(Client):
    def __init__(self, output_queue: Deque[str]) -> None:
        self.output_queue = output_queue

    async def request_permission(
        self, options: list[PermissionOption], session_id: str, tool_call: Any, **kwargs: Any
    ) -> RequestPermissionResponse:
        return RequestPermissionResponse(outcome={"outcome": "cancelled"})

    async def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None:
        text = self._render_update(update)
        TelegramACPClient._log_agent_session_update(session_id, update, text)
        if text:
            self.output_queue.append(text)

    async def write_text_file(self, **kwargs: Any) -> None:
        return None

    async def read_text_file(self, **kwargs: Any) -> Any:
        return None

    async def create_terminal(self, **kwargs: Any) -> CreateTerminalResponse | None:
        return None

    async def terminal_output(self, **kwargs: Any) -> TerminalOutputResponse | None:
        return None

    async def release_terminal(self, **kwargs: Any) -> ReleaseTerminalResponse | None:
        return None

    async def wait_for_terminal_exit(self, **kwargs: Any) -> WaitForTerminalExitResponse | None:
        return None

    async def kill_terminal(self, **kwargs: Any) -> KillTerminalCommandResponse | None:
        return None

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        return {}

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        return None

    def on_connect(self, conn: Client) -> None:
        return None

    @staticmethod
    def _render_update(update: Any) -> str | None:
        if not update:
            return None
        session_update = getattr(update, "session_update", None)
        if session_update in {"user_message_chunk", "agent_message_chunk", "agent_thought_chunk"}:
            return TelegramACPClient._render_content_chunk(getattr(update, "content", None))
        if session_update == "tool_call":
            return TelegramACPClient._render_tool_call(update, prefix="🔧")
        if session_update == "tool_call_update":
            return TelegramACPClient._render_tool_call(update, prefix="⚙️")
        if session_update == "plan":
            return TelegramACPClient._render_plan(update)
        if session_update == "available_commands_update":
            return TelegramACPClient._render_available_commands(update)
        if session_update == "current_mode_update":
            return TelegramACPClient._render_current_mode(update)
        if session_update == "session_info_update":
            return TelegramACPClient._render_session_info(update)
        return str(update)

    @staticmethod
    def _log_agent_session_update(session_id: str, update: Any, text: str | None) -> None:
        log_chat_history_event(
            {
                "type": "agent_update",
                "direction": "agent->application",
                "session_id": session_id,
                "update_type": getattr(update, "session_update", None),
                "text": text,
                "summary": TelegramACPClient._shorten_text(str(update)),
            }
        )

    @staticmethod
    def _render_content_chunk(content: Any) -> str | None:
        return TelegramACPClient._format_content_block(content)

    @staticmethod
    def _render_tool_call(tool_call: Any, prefix: str) -> str | None:
        if not tool_call:
            return None
        title = getattr(tool_call, "title", "Codex tool call")
        header = f"{prefix} {title}"
        if kind := getattr(tool_call, "kind", None):
            header += f" [{kind}]"
        if status := getattr(tool_call, "status", None):
            header += f" ({status})"
        if tool_call_id := getattr(tool_call, "tool_call_id", None):
            header += f" id={tool_call_id[:8]}"
        lines = [header]

        if raw_input := getattr(tool_call, "raw_input", None):
            lines.append(f"Input: {TelegramACPClient._shorten_text(repr(raw_input))}")
        if raw_output := getattr(tool_call, "raw_output", None):
            lines.append(f"Output: {TelegramACPClient._shorten_text(repr(raw_output))}")

        locations = getattr(tool_call, "locations", None) or []
        loc_parts = []
        for loc in locations:
            if not getattr(loc, "path", None):
                continue
            path = loc.path
            if getattr(loc, "line", None) is not None:
                path = f"{path}:{loc.line}"
            loc_parts.append(path)
        if loc_parts:
            lines.append(f"Locations: {', '.join(loc_parts)}")

        for chunk in getattr(tool_call, "content", []) or []:
            rendered = TelegramACPClient._format_tool_content_chunk(chunk)
            if rendered:
                lines.append(f"- {rendered}")

        return "\n".join(lines)

    @staticmethod
    def _format_tool_content_chunk(chunk: Any) -> str | None:
        if not chunk:
            return None
        if content := getattr(chunk, "content", None):
            return TelegramACPClient._format_content_block(content)
        if path := getattr(chunk, "path", None):
            snippet = getattr(chunk, "new_text", None) or getattr(chunk, "old_text", None)
            if snippet:
                return f"Diff {path}: {TelegramACPClient._shorten_text(snippet)}"
            return f"Diff {path}"
        if terminal_id := getattr(chunk, "terminal_id", None):
            return f"Terminal output ({terminal_id})"
        return TelegramACPClient._shorten_text(str(chunk))

    @staticmethod
    def _format_content_block(content: Any) -> str | None:
        if not content:
            return None
        if text := getattr(content, "text", None):
            return str(text).strip()
        if resource := getattr(content, "resource", None):
            if uri := getattr(resource, "uri", None):
                return f"Embedded resource: {uri}"
            if res_text := getattr(resource, "text", None):
                return res_text.strip()
        if uri := getattr(content, "uri", None):
            label = getattr(content, "title", None) or getattr(content, "name", None) or "resource"
            if description := getattr(content, "description", None):
                label = f"{label} ({description})"
            return f"🔗 {label}: {uri}"
        if data := getattr(content, "data", None):
            mime = getattr(content, "mime_type", None) or getattr(content, "mimeType", None) or "image"
            size = len(data) if isinstance(data, str) else None
            size_text = f", {size} bytes" if size is not None else ""
            uri_part = f" @ {getattr(content, 'uri', None)}" if getattr(content, "uri", None) else ""
            return f"🖼️ Image ({mime}{size_text}){uri_part}"
        return TelegramACPClient._shorten_text(str(content))

    @staticmethod
    def _shorten_text(text: str, max_length: int = 380) -> str:
        clean = " ".join(str(text).split())
        if len(clean) <= max_length:
            return clean
        return f"{clean[: max_length - 1]}…"

    @staticmethod
    def _render_plan(update: Any) -> str | None:
        entries = getattr(update, "entries", []) or []
        if not entries:
            return None
        lines = ["🗂️ Plan update:"]
        for entry in entries[:5]:
            status = getattr(entry, "status", "unknown")
            priority = getattr(entry, "priority", None)
            content = getattr(entry, "content", "")
            line = f"- [{status}] {content}"
            if priority:
                line += f" ({priority})"
            lines.append(line)
        if len(entries) > 5:
            lines.append(f"...and {len(entries) - 5} more tasks")
        return "\n".join(lines)

    @staticmethod
    def _render_available_commands(update: Any) -> str | None:
        commands = getattr(update, "available_commands", []) or []
        if not commands:
            return None
        lines = ["⚡ Available commands:"]
        for cmd in commands[:10]:
            name = getattr(cmd, "name", None)
            description = getattr(cmd, "description", None)
            entry = f"- `{name}`" if name else "- unnamed command"
            if description:
                entry += f": {description}"
            if hint := TelegramACPClient._extract_command_hint(cmd):
                entry += f" (hint: {hint})"
            lines.append(entry)
        if len(commands) > 10:
            lines.append(f"...and {len(commands) - 10} more")
        return "\n".join(lines)

    @staticmethod
    def _extract_command_hint(cmd: Any) -> str | None:
        input_slot = getattr(cmd, "input", None)
        root = getattr(input_slot, "root", None) if input_slot else None
        return getattr(root, "hint", None)

    @staticmethod
    def _render_current_mode(update: Any) -> str | None:
        mode_id = getattr(update, "current_mode_id", None) or getattr(update, "currentModeId", None)
        return f"🎛️ Current mode: {mode_id}" if mode_id else None

    @staticmethod
    def _render_session_info(update: Any) -> str | None:
        title = getattr(update, "title", None)
        updated = getattr(update, "updated_at", None) or getattr(update, "updatedAt", None)
        parts = []
        if title:
            parts.append(f"title={title}")
        if updated:
            parts.append(f"updated={updated}")
        return f"ℹ️ Session info ({'; '.join(parts)})" if parts else None


class AgentClientManager:
    def __init__(
        self,
        output_queue: Deque[str],
        agent_type: Optional[str] = None,
        agent_command_override: Optional[str] = None,
    ) -> None:
        self.output_queue = output_queue
        self._client = TelegramACPClient(output_queue)
        self._agent_type = (agent_type or DEFAULT_AGENT_TYPE).strip().lower()
        self._agent_command_override = agent_command_override or CUSTOM_AGENT_COMMAND
        self._context = None
        self.conn = None
        self.session_id = None
        self._running = False
        self._ensure_agent_type_valid()

    def _ensure_agent_type_valid(self) -> None:
        if self._agent_type not in AGENT_COMMANDS:
            raise ValueError(f"Unknown agent type: {self._agent_type}")

    def _build_agent_command(self) -> Tuple[str, ...]:
        if self._agent_command_override:
            return tuple(shlex.split(self._agent_command_override))
        return AGENT_COMMANDS.get(self._agent_type, AGENT_COMMANDS["cline"])


    async def start(self) -> bool:
        if self.conn:
            return True
        cmd = self._build_agent_command()
        self._context = spawn_agent_process(self._client, *cmd)
        self.conn, _proc = await self._context.__aenter__()
        await self.conn.initialize(protocol_version=PROTOCOL_VERSION)
        session = await self.conn.new_session(cwd=os.getcwd(), mcp_servers=[])
        self.session_id = session.session_id
        self._running = True
        return True

    async def stop(self) -> None:
        if not self.conn:
            return
        try:
            await self.conn.cancel(session_id=self.session_id)
        except Exception:
            pass
        if self._context:
            await self._context.__aexit__(None, None, None)
        self.conn = None
        self.session_id = None
        self._context = None
        self._running = False

    async def send_prompt(self, text: str) -> bool:
        if not self.conn or not self.session_id:
            return False
        self._log_agent_prompt(text)
        await self.conn.prompt(prompt=[text_block(text)], session_id=self.session_id)
        return True

    def _log_agent_prompt(self, text: str) -> None:
        log_chat_history_event(
            {
                "type": "application_to_agent",
                "direction": "application->agent",
                "session_id": self.session_id,
                "agent_type": self._agent_type,
                "prompt": text,
            }
        )

    async def set_mode(self, mode_id: str) -> None:
        if not self.conn or not self.session_id:
            return
        await self.conn.set_session_mode(mode_id, session_id=self.session_id)

    async def cancel(self) -> bool:
        if not self.conn or not self.session_id:
            return False
        await self.conn.cancel(session_id=self.session_id)
        return True

    @property
    def running(self) -> bool:
        return self._running

    async def set_agent_type(self, agent_type: str) -> None:
        agent_type = agent_type.strip().lower()
        if agent_type == self._agent_type:
            return
        if self.running:
            await self.stop()
        self._agent_type = agent_type
        self._ensure_agent_type_valid()

    def available_agent_types(self) -> Iterable[str]:
        return AGENT_COMMANDS.keys()

    @property
    def current_agent_type(self) -> str:
        return self._agent_type
