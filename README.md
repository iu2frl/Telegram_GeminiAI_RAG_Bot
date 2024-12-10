# AI Assistant Telegram Bot

This bot is an AI-powered assistant that uses Google's Gemini AI to process user queries and provide responses based on uploaded documents. It integrates with Telegram for user interaction.

The Gemini APIs for the basic model `gemini-1.5-flash` allows for a good number of interactions, I was never able to get over 2-3% with normal usage.

I found this code extremely helpful to quickly retrieve data from a collection of documents like my transceivers manuals, some datasheets and so on.

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

2. Create a `.env` File

Create a `.env` file in the project root directory with the following variables:

```env
TELEGRAM_API_KEY=your-telegram-bot-token
TELEGRAM_BOT_NAME=@your-bot-username
GOOGLE_API_KEY=your-google-api-key
GOOGLE_API_MODEL=gemini-1.5-flash
GOOGLE_API_MAX_ATTEMPTS=2
```

Please note: creating the `.env` file is optional, if the variables are set in the current environment, the bot will retrieve them from there (or from the Docker environment variables)

3. Prepare the `sources` Folder

Place the source documents you want the bot to query into the `sources` folder within the project directory. I provided an example using an apple pie recipe from Loni Jenks that I found on the internet. You can put any text file in this folder, it will be uploaded and processed by the AI.

## Running the Bot

1. Install Dependencies

```bash
pip install -r requirements.txt
```

2. Start the Bot using:

```bash
python bot.py
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
2. Build the container with `docker build -t olliter-bot:latest .`
3. Create the `docker-compose.yml` file containing:

```yaml
services:
    bot:
        container_name: olliter-telegram
        environment:
          - TELEGRAM_API_KEY=your-telegram-bot-token
          - TELEGRAM_BOT_NAME=@your-bot-username
          - GOOGLE_API_KEY=your-google-api-key
          - GOOGLE_API_MODEL=gemini-1.5-flash
          - GOOGLE_API_MAX_ATTEMPTS=2
        restart: unless-stopped
        image: olliter-bot:latest
        deploy:
          resources:
            limits:
              cpus: '1'
              memory: 256M
```

4. Start the container with `docker compose up`

## Automatic Docker image generation

A dedicated workflow was designed to automate the process of building and pushing Docker images to Docker Hub whenever a new tag is pushed to the repository or the workflow is triggered manually.

### Configuration Steps

#### Set Up Secrets in GitHub

To securely authenticate with Docker Hub, you need to add the following secrets to your GitHub repository:

1. Navigate to your repository on GitHub.
2. Go to **Settings** > **Secrets and variables** > **Actions** > **New repository secret**.
3. Add the following secrets:
   - **`DOCKERHUB_USERNAME`**: Your Docker Hub username.
   - **`DOCKERHUB_TOKEN`**: A Docker Hub access token (generate this from your Docker Hub account).
   - **`DOCKERHUB_IMAGENAME`**: The name of your Docker image (e.g., `my-app-image`).

### How to Trigger Image Generation

#### Creating a new release

- From the right side of the homepage of the GitHub repository select **Releases**
- Select **Create a new release**
- Make sure to add a tag with the current version (e.g. `1.0.1`)
- Fill in the details as needed

Once the release is created, the build workflow will start automatically and the image will be published to Docker Hub.

### What the Workflow Does

1. **Checks Out the Repository**: Fetches the source code for building the Docker image.
2. **Gets the Latest Git Tag**: Captures the most recent tag, used for tagging the Docker image.
3. **Sets Up QEMU and Buildx**: Prepares the environment for multi-platform builds.
4. **Authenticates to Docker Hub**: Logs into Docker Hub using the provided secrets.
5. **Builds and Pushes the Docker Image**:
   - Builds the image for multiple architectures: `linux/amd64`, `linux/arm/v7`, `linux/arm64/v8`, and `linux/arm64`.
   - Tags the image with the latest Git tag and `latest`.
   - Pushes the image to Docker Hub.

### **Image Publishing Example**

If the repository's latest tag is `v1.0.0` and the `DOCKERHUB_IMAGENAME` is `my-app`, the workflow will push the following images to Docker Hub:

- `your-dockerhub-username/my-app:v1.0.0`
- `your-dockerhub-username/my-app:latest`

These images will then be available for use or deployment from Docker Hub.
