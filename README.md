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
