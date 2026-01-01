# Cline Remote Chatter

A Telegram bot for remote communication and interaction.

## Description

Cline Remote Chatter is a Python-based Telegram bot designed to facilitate remote communication and provide various chat functionalities.

## Features

- Remote messaging capabilities
- Telegram bot integration
- Python-based implementation
- Easy deployment and configuration

## Installation

1. Clone the repository:
```bash
git clone git@github.com:joshld/cline-remote-chatter.git
cd cline-remote-chatter
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

1. Set up your Telegram bot token in the configuration
2. Run the bot:
```bash
python cline_telegram_bot.py
```

### Agent Client Protocol integration

The Telegram bot now uses the [`agent-client-protocol`](https://github.com/agentclientprotocol/python-sdk) to spawn `cline_acp_agent.py`, which wraps the `cline` CLI as an ACP agent. The bot drives that agent via `/start`, `/act`, `/plan`, and regular text messages, while streamed updates are relayed back to you over Telegram.

Make sure `agent-client-protocol` is installed (it's included in `requirements.txt`) and the environment still exposes `TELEGRAM_BOT_TOKEN` and `AUTHORIZED_USER_ID` as described above.

You can choose which ACP agent the bot launches using `ACP_AGENT_TYPE` (`cline` or `codex`, default `cline`). If you need a custom command (for example, calling `npx @zed-industries/codex-acp`), set `ACP_AGENT_COMMAND` to the shell command you want to run. Inside Telegram, `/agent codex` switches the runtime to the Codex ACP agent and `/agent` shows the current selection and supported values.

### Codex agent launcher

Switching to `ACP_AGENT_TYPE=codex` now runs `codex_acp_agent_launcher.py`, which first looks for a native `codex-acp` binary and, if that is not installed, falls back to `npx @zed-industries/codex-acp`. You can point the fallback to another package with `CODEX_ACP_NPX_PACKAGE` if you build a customized wrapper.

### Codex agent authentication

Per `@zed-industries/codex-acp/src/codex_agent.rs`, three authentication flows are exposed:

1. **ChatGPT login** – opens the standard Codex login server so you can authenticate with a paid ChatGPT account. Most remote deployments should *not* set `NO_BROWSER`, because the login server is removed when that env var is present.
2. **`CODEX_API_KEY`** – set the environment variable to the API key you obtained from the Codex dashboard; the agent will call `codex_login::login_with_api_key`.
3. **`OPENAI_API_KEY`** – set the OpenAI API key when you want the Codex CLI to re-use an existing OpenAI credential instead.

Set the appropriate env vars before launching the bot so the Creds are available when `codex_acp_agent_launcher.py` spins up the agent.

## Chat History Review

The bot now records every inbound user message and outbound Cline output to `chat_history.jsonl` (or the path configured through `CHAT_HISTORY_FILE`). Each entry is stored as a newline-delimited JSON object so you can audit the full session history.

To replay that log with parsing diffs, run:
```bash
python parse_chat_history.py [path/to/chat_history.jsonl]
```

## Configuration

Create a `.env` file with your Telegram bot token and authorized user ID:
```
TELEGRAM_BOT_TOKEN=your_bot_token_here
AUTHORIZED_USER_ID=your_telegram_user_id
```

## Development

- Python 3.8+
- Requirements listed in `requirements.txt`

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## License

[MIT](https://choosealicense.com/licenses/mit/)
