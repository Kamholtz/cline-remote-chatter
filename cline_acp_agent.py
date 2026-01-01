import asyncio
from typing import Any

from acp import (
    Agent,
    AuthenticateResponse,
    InitializeResponse,
    NewSessionResponse,
    PromptResponse,
    PROTOCOL_VERSION,
    SetSessionModeResponse,
    run_agent,
)
from acp.helpers import text_block, update_agent_message
from acp.interfaces import Client
from acp.schema import AgentCapabilities, ClientCapabilities, Implementation

from bot_logging import DEBUG_INFO, debug_log
from cline_session import ClineSession


class ClineAgent(Agent):
    def __init__(self) -> None:
        self._conn: Client | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._session: ClineSession | None = None
        self._current_session_id: str | None = None
        self._next_session_id = 0
        self._sessions = set()

    def on_connect(self, conn: Client) -> None:
        self._conn = conn
        try:
            self._loop = asyncio.get_event_loop()
        except RuntimeError:
            self._loop = None

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **kwargs: Any,
    ) -> InitializeResponse:
        debug_log(DEBUG_INFO, "Agent received initialize request")
        return InitializeResponse(
            protocol_version=PROTOCOL_VERSION,
            agent_capabilities=AgentCapabilities(),
            agent_info=Implementation(name="cline-agent", title="Cline Agent", version="0.1.0"),
        )

    async def authenticate(self, method_id: str, **kwargs: Any) -> AuthenticateResponse | None:
        debug_log(DEBUG_INFO, "Agent authentication request", method_id=method_id)
        return AuthenticateResponse()

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[Any],
        **kwargs: Any,
    ) -> NewSessionResponse:
        session_id = str(self._next_session_id)
        self._next_session_id += 1
        self._sessions.add(session_id)
        self._current_session_id = session_id
        self._ensure_cline_running()
        debug_log(DEBUG_INFO, "New ACP session created", session_id=session_id, cwd=cwd)
        return NewSessionResponse(session_id=session_id, modes=None)

    async def set_session_mode(self, mode_id: str, session_id: str, **kwargs: Any) -> SetSessionModeResponse | None:
        debug_log(DEBUG_INFO, "Set session mode request", mode_id=mode_id, session_id=session_id)
        return SetSessionModeResponse()

    async def prompt(
        self,
        prompt: list[Any],
        session_id: str,
        **kwargs: Any,
    ) -> PromptResponse:
        debug_log(DEBUG_INFO, "Prompt received", session_id=session_id)
        self._ensure_cline_running()
        command = self._prompt_to_text(prompt)
        if command:
            self._session.send_command(command)
        else:
            self._session.send_enter()
        return PromptResponse(stop_reason="end_turn")

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        debug_log(DEBUG_INFO, "Cancel request received", session_id=session_id)
        if self._session:
            self._session.send_command("\x03")

    def _ensure_cline_running(self) -> None:
        if self._session and self._session.session_active:
            return
        self._session = ClineSession(output_callback=self._broadcast_output)
        self._session.start()

    def _broadcast_output(self, output: str) -> None:
        if not output.strip() or not self._conn or not self._current_session_id or not self._loop:
            return
        update = update_agent_message(text_block(output))
        try:
            asyncio.run_coroutine_threadsafe(
                self._conn.session_update(self._current_session_id, update), self._loop
            )
        except Exception as exc:
            debug_log(DEBUG_INFO, "Failed to push session update", error=str(exc))

    @staticmethod
    def _prompt_to_text(blocks: list[Any]) -> str:
        parts = []
        for block in blocks:
            content = getattr(block, "content", block)
            text = getattr(content, "text", None)
            if text:
                parts.append(text)
        return "\n".join(parts).strip()


async def main() -> None:
    agent = ClineAgent()
    await run_agent(agent)


if __name__ == "__main__":
    asyncio.run(main())
