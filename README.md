# Nutricare App 

Nutricare is a **child malnutrition tracking system** designed for primary healthcare workers. It consists of a FastAPI backend, a Telegram bot for quick patient registration, and optional web dashboard (React) integration.

---
## Features
- Add patient details (name, age, weight, height, MUAC) via Telegram commands.
- View patient list and summary statistics.
- Export patient data as a CSV file.
- Web dashboard for manual data entry and visualization.
- Webhook support for Telegram integration using ngrok or Render.

## Prerequisites
- Python 3.8+
- Git (for cloning the repository)

## Installation

### 1. Clone the Repository
```bash
git clone https://github.com/Pash-Data/Nutricare.git
cd Nutricare 

## Usage

Telegram Commands:

/start: Welcome message.
/add: Add a new patient (follow prompts).
/list: View all patients.
/summary: Display patient statistics.
/cancel: Cancel ongoing operations.


Web Interface:

Access https://nutricare-nvw0.onrender.com/dashboard for a dashboard.
Access https://nutricare-nvw0.onrender.com/patients for database.
Access https://t.me/Nutricare_helper_bot for Telegram bot 

Project Structure
Nutricare/
├── main.py          # FastAPI and Telegram bot logic
├── requirements.txt # Python dependencies
├── templates/       # HTML templates for dashboard
├── .env            # Environment variables
└── patients.db     # SQLite database (generated)

## **Links**
GitHub Repository: https://github.com/Pash-Data/Nutricare
xAI Grok: https://x.ai/grok (for AI assistance)
Render: https://render.com (for deployment)
Telegram Bot API: https://core.telegram.org/bots/api
BotFather: https://t.me/BotFather

Acknowledgments
Thanks to the open-source communities of FastAPI, python-telegram-bot, and SQLModel.
