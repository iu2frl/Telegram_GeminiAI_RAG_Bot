# AI Assistant Telegram Bot

This bot is an AI-powered assistant that uses Google's Gemini AI to process user queries and provide responses based on uploaded documents. It integrates with Telegram for user interaction.

## Features

- Responds to user queries about specific documents or topics.
- Utilizes Google Gemini AI for natural language understanding and document-based querying.
- Handles Telegram messages and commands.
- Supports MarkdownV2 formatting for responses.

## Prerequisites

### Python environment

1. Python 3.8 or higher.
2. Required Python packages (install using `pip install -r requirements.txt`)

### Gemini API key

1. Generate a Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey?hl=it)

### Telegram API key

1. Use [@BotFather](https://t.me/BotFather) to generate a bot
2. Get the API key from the generate bot

## Setup

1. Clone the Repository

```bash
git clone <repository-url>
cd <repository-folder>
```

1. Create a `.env` File

Create a `.env` file in the project root directory with the following variables:

```env
TELEGRAM_API_KEY=your-telegram-bot-token
TELEGRAM_BOT_NAME=@your-bot-username
GOOGLE_API_KEY=your-google-api-key
GOOGLE_API_MODEL=gemini-2.0-flash
GOOGLE_API_MAX_ATTEMPTS=2
REPO_URL=https://github.com/octocat/hello-world
TELEGRAM_RESTART_DELAY_SECONDS=15
```

Please note: creating the `.env` file is optional, if the variables are set in the current environment, the bot will retrieve them from there (or from the Docker environment variables)

1. Prepare the sources

The bot pulls documents from the repository defined by `REPO_URL` and stores them in `./sources`. You can also place your documents directly inside the `sources` folder if you want to manage them locally.

## Running the Bot

1. Install Dependencies

```bash
pip install -r requirements.txt
```

1. Start the Bot using:

```bash
python main.py
```

## Usage

### Commands

- **`/start`**: Initiates interaction with the bot and provides an introductory message.

### Messaging

- Send a text message with your query to the bot, and it will respond based on the information in the uploaded documents.

## Logs

The bot logs all activity to the console. Logs are categorized into:

- **INFO**: General information about the bot's operation.
- **DEBUG**: Detailed logs for troubleshooting.
- **WARNING**: Potential issues that do not stop the bot.
- **ERROR**: Issues that prevent successful operation.

You can adjust the log level in the `configure_logging()` function.

## Troubleshooting

- **Missing API keys**: Ensure the `.env` file is correctly configured.
- **Google Gemini AI errors**: Check your API key and ensure the uploaded files meet the requirements.
- **Telegram bot issues**: Verify the bot token and bot username.

For detailed error messages, check the logs.

## Usage with Docker

1. Clone the repo
1. Build the container with `docker build -t notebook-lm-bot:latest .`
1. Create the `docker-compose.yml` file containing:

```yaml
services:
    bot:
        container_name: notebook-lm-bot
        environment:
          - TELEGRAM_API_KEY=your-telegram-bot-token
          - TELEGRAM_BOT_NAME=@your-bot-username
          - GOOGLE_API_KEY=your-google-api-key
          - GOOGLE_API_MODEL=gemini-2.0-flash
          - GOOGLE_API_MAX_ATTEMPTS=2
          - REPO_URL=https://github.com/octocat/hello-world
          - TELEGRAM_RESTART_DELAY_SECONDS=15
        restart: unless-stopped
        image: notebook-lm-bot:latest
        deploy:
          resources:
            limits:
              cpus: '1'
              memory: 256M
```

1. Start the container with `docker compose up`
