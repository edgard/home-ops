# n8n AI Workflows

This directory contains n8n workflow templates for home automation AI tasks.

## Setup Instructions

### 1. Credentials
Configure these credentials in n8n (Settings -> Credentials):

| Credential Name | Type | Value |
|----------------|------|-------|
| **Paperless API** | `HTTP Header Auth` | Name: `Authorization`, Value: `Token <your-token>` |
| **Karakeep API** | `HTTP Header Auth` | Name: `Authorization`, Value: `Bearer <your-token>` |
| **OpenRouter API** | `OpenRouter API` | API Key: `<your-sk-or-key>` |
| **Telegram Bot** | `Telegram API` | Access Token: `<your-bot-token>` |

### 2. Workflows

#### Paperless AI Classifier (`paperless-ai-classifier.json`)
- **Purpose**: Automatically tags, titles, and classifies new documents in Paperless-ngx
- **Schedule**: Daily at 2:05 AM
- **AI Model**: Claude Sonnet 3.5 (via OpenRouter)
- **Features**:
  - Uses native LangChain `Basic LLM Chain` node
  - Enforces JSON structure via `Structured Output Parser`
  - Updates document metadata (correspondent, type, date)
  - Adds `ai-processed` tag to prevent re-processing

#### Karakeep List Organizer (`karakeep-list-organizer.json`)
- **Purpose**: Moves unorganized bookmarks into appropriate lists
- **Schedule**: Daily at 3:00 AM
- **AI Model**: GPT-4o-mini (via OpenRouter)
- **Features**:
  - Fetches all available lists dynamically
  - Analyzes bookmark content (title, summary, tags)
  - Moves bookmark ONLY if confidence > 70%
  - Sends daily summary to Telegram

### 3. Usage
1. Import the `.json` files into n8n
2. Open each workflow and verify nodes are connected (no red errors)
3. Update the **Telegram Chat ID** in the "Send Telegram" nodes (default: `52094995`)
4. Activate the workflows
