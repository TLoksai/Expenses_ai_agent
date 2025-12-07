# Expense Tracker Telegram Bot

This is an enhanced Telegram bot that processes receipt images, extracts details using AI, and saves them to Google Sheets with investor tracking and colored formatting.

## Features

- 📸 Upload receipts (photos or files: JPG, PNG, PDF, WEBP, GIF)
- 👥 Select or add investors/persons
- 🤖 AI-powered text extraction and parsing
- 📊 Automatic saving to Google Sheets with formatting
- 🎨 Alternating row colors and currency formatting
- 🔗 Store receipt image links

## Setup

1. **Clone or download the code** to your local machine.

2. **Google Sheets Setup:**
   - Create a new Google Sheet named "My Expenses 2025"
   - Create a Google Cloud Project and enable Google Sheets API
   - Create a Service Account and download the JSON key
   - Share the Google Sheet with the service account email
   - Copy the entire JSON content of the key file

3. **Environment Variables:**
    - `GROQ_API_KEY`: Your Groq API key
    - `TELEGRAM_TOKEN`: Your Telegram Bot Token
    - `CREDENTIALS_JSON`: The entire JSON content of your service account key file (as a string)
    - `WEBHOOK_URL`: Your deployment URL (e.g., https://your-app-name.onrender.com) - required for production

## Deployment

### Railway (Recommended)

Railway is recommended for easy deployment of this bot.

1. **Create a GitHub Repository:**
    - Create a new repo on GitHub
    - Push this code to the repo

2. **Deploy on Railway:**
    - Go to [Railway.app](https://railway.app) and sign up/login
    - Click "New Project" > "Deploy from GitHub repo"
    - Connect your GitHub account and select the repo
    - Railway will auto-detect Python and install dependencies

3. **Set Environment Variables in Railway:**
    - In your Railway project, go to Variables
    - Add:
      - `GROQ_API_KEY` = your_groq_api_key
      - `TELEGRAM_TOKEN` = your_telegram_bot_token
      - `CREDENTIALS_JSON` = paste the entire JSON content of your service account key file

4. **Deploy:**
    - Railway will build and deploy automatically
    - The bot will start running 24/7

### Render (Current Deployment)

Successfully deployed on Render.com:

- **Service URL**: https://expenses_ai_agent-5.onrender.com
- **Status**: Live with webhook mode for 24/7 operation
- **Environment Variables Set**:
  - `GROQ_API_KEY`
  - `TELEGRAM_TOKEN`
  - `CREDENTIALS_JSON`
  - `WEBHOOK_URL` = https://expenses_ai_agent-5.onrender.com

**Note**: The URL is a webhook endpoint (shows 404 for browsers) - users access the bot through Telegram.

## Local Testing

To test locally:

```bash
pip install -r requirements.txt
python app.py
```

Make sure to set environment variables or hardcode them temporarily for testing.

## Usage

- Start the bot with `/start`
- Send a receipt image
- Select the person/investor
- The bot will process and save to Google Sheets

## Notes

- The bot uses webhooks in production (when WEBHOOK_URL is set) and polling for local development
- Images are temporarily downloaded for processing and then deleted
- Google Sheets is formatted with headers, colors, and currency formatting
- For production deployment, ensure WEBHOOK_URL is set to avoid polling conflicts