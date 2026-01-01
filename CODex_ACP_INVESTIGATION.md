# Codex ACP Research & Next Steps

## Summary
- `codex-acp` is a full ACP adapter around the Codex CLI: `src/codex_agent.rs` implements the `Agent` trait from the `agent-client-protocol` crate so ACP clients can initialize/authenticate, start sessions, and send prompts directly to Codex (`src/codex_agent.rs:22-140`).  
- The agent also manages authentication modes (ChatGPT, `CODEX_API_KEY`, `OPENAI_API_KEY`) and wires Codex conversations into ACP sessions, tracking session roots, MCP-capable file access (`AcpFs`), and spawns local Codex operations (`src/codex_agent.rs:90-180`).  
- Output reconciliation, context blocks, images, tool calls, and TODO slash commands are handled inside `src/conversation.rs`, which translates Codex-native content into `agent-client-protocol` content blocks (`src/conversation.rs:920-2360`). That file also keeps track of edit review and permission flows needed for tool calls, so the ACP client receives structured updates instead of raw terminal output.
- The binary exposes CLI overrides via `codex_arg0::arg0_dispatch_or_else`, runs `codex_acp::run_main`, and uses `RunMain` to bootstrap the agent (`src/main.rs:1-12`), so ACP clients can simply run `codex-acp` or `npx @zed-industries/codex-acp` to connect.

## Implications for our bot
1. Instead of hacking the Codex terminal through a PTY, we can re-use the ACP agent pattern: spawn `codex-acp` as a normal ACP agent, then treat the Telegram bot as an ACP client just like our `agent_client.py` already does for `cline`.  
2. The Rust adapter already maps Codex conversations, tool calls, context, and slash commands into ACP `session_update` payloads, so we can focus on wiring Telegram ↔ ACP rather than parsing terminal noise.  
3. Authentication and MCP-capable file access are already handled by the Codex agent, meaning we only need to supply the right API keys/environment and expose the correct client auth flows if necessary.

## Progress & Next Steps
- [x] **Agent selection plumbing** – `AgentClientManager` now supports `ACP_AGENT_TYPE`/`ACP_AGENT_COMMAND`, defaults to `cline`, and exposes `/agent` in Telegram to report or change the runtime agent (see `agent_client.py`, `cline_telegram_bot.py`).  
- [x] **Readme updated** – documented how to switch between agents and configure Codex vs. `cline` using env vars.  
- [x] **Add Codex-native agent launcher** – introduce a script or wrapper that simply runs `codex-acp` (or `npx @zed-industries/codex-acp`) so the new selection endpoint can point there without modifying `cline_acp_agent.py`.  
- [x] **Document Codex auth requirements** – incorporate authentication guidance from `src/codex_agent.rs` (ChatGPT, `CODEX_API_KEY`, `OPENAI_API_KEY`) into the README or investigation notes.  
- [x] **Improve output formatting** – revisit `TelegramACPClient._render_update` so Codex `session_update` updates (text, tool calls, MCP resources) render nicely in Telegram instead of raw `str(update)`.  
