# AI Assistant Telegram Bot

This bot is an AI-powered assistant that uses Google's Gemini AI to process user queries and provide responses based on uploaded documents. It integrates with Telegram for user interaction.

## Features

- Responds to user queries about specific documents or topics.
- Utilizes Google Gemini AI for natural language understanding and document-based querying.
- Handles Telegram messages and commands.
- Supports Telegram HTML formatting for responses.
- Summarizes mathematical formulas in plain language without returning LaTeX or formula notation.
- Supports dynamic loading of documents from a specified GitHub repository.
- Supports rate limit handling for Gemini API models when using free-tier accounts (only if `GOOGLE_API_MODEL` is set to `auto`).

> [!WARNING]
> If the `GOOGLE_API_MODEL` environment variable is set to a specific model name (e.g., `gemini-2.0-flash`), the bot will not monitor rate limits automatically. This may lead to unexpected costs or rate limiting issues.

> [!WARNING]
> The list of supported free-tier Gemini models may change over time. Please refer to the [official documentation](https://ai.google.dev/gemini-api/docs/deprecations) for the most up-to-date information. If a model expires, it can no longer be used by the bot until the code in `modules/state.py` is updated.

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
HEALTH_HOST=0.0.0.0
HEALTH_PORT=8080
BUILD_DATE=Unknown
```

Please note: creating the `.env` file is optional. If the variables are set in the current environment, the bot will retrieve them from there. Never commit this file or copy it into a container image.

### Environment variables

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `TELEGRAM_API_KEY` | Yes | None | Telegram bot token. |
| `TELEGRAM_BOT_NAME` | Yes | None | Telegram bot username. |
| `GOOGLE_API_KEY` | Yes | None | Google Gemini API key. |
| `REPO_URL` | Yes | None | Git repository containing source documents. |
| `GOOGLE_API_MODEL` | No | `auto` | Gemini model name, or `auto` for automatic selection. |
| `GOOGLE_API_MAX_ATTEMPTS` | No | `2` | Maximum Gemini request attempts. |
| `TELEGRAM_RESTART_DELAY_SECONDS` | No | `15` | Restart delay after Telegram flood control. |
| `HEALTH_HOST` | No | `0.0.0.0` | Bind address for the internal health server. |
| `HEALTH_PORT` | No | `8080` | Internal health server port. |
| `BUILD_DATE` | No | `Unknown` | Build metadata reported in startup logs; Docker builds can set it with `--build-arg`. |

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
- **`/reset`**: Clears your recent conversation context.

### Messaging

- Send a text message with your query to the bot, and it will respond based on the information in the uploaded documents.
- Recent exchanges are kept separately per Telegram user to support follow-up questions. Context is bounded in memory and is cleared with `/reset`.

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

### Manual build

1. Clone the repo
1. Build the container with `docker build -t notebook-lm-bot:latest .`
1. Create the `docker-compose.yml` file containing the text below
1. Start the container with `docker compose up`

```yaml
services:
    bot:
        container_name: notebook-lm-bot
        env_file:
          - .env
        restart: unless-stopped
        image: notebook-lm-bot:latest
        healthcheck:
          test: ["CMD", "python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz')"]
          interval: 30s
          timeout: 5s
          retries: 3
          start_period: 10s
        deploy:
          resources:
            limits:
              cpus: '1'
              memory: 256M
```

### Using pre-built image

```yaml
services:
    bot:
        container_name: telegram-gemini-bot
        environment:
          - "GOOGLE_API_KEY=xxxxxxxxxxxxxxxxxxx"
          - "TELEGRAM_API_KEY=xxxxxxxxxxxxxxxxxxx"
          - "TELEGRAM_BOT_NAME=@zzzzzzz_bot"
          - "GOOGLE_API_MODEL=auto"
          - "GOOGLE_API_MAX_ATTEMPTS=2"
          - "REPO_URL=https://github.com/iu2frl/Telegram_GeminiAI_RAG_Bot.git"
          - "TELEGRAM_RESTART_DELAY_SECONDS=15"
          - "HEALTH_HOST=0.0.0.0"
          - "HEALTH_PORT=8080"
        restart: unless-stopped
        image: ghcr.io/iu2frl/telegram_geminiai_rag_bot:latest
        deploy:
          resources:
            limits:
              cpus: '0.5'
              memory: 128M
```
