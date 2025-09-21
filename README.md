# Nutricare App

Nutricare is a **child malnutrition tracking system** designed for primary healthcare workers. It consists of a FastAPI backend, a Telegram bot for quick patient registration, and optional web dashboard (React) integration.

---

## **Features**

- Register children with age, weight, height, and MUAC.
- Automatically calculate BMI, build, and nutrition status (SAM/MAM/Normal).
- Summarize patient data.
- Export all patient records as CSV via Telegram.
- FastAPI backend for data storage and retrieval.

---

## **Project Structure**

Nutricare/
├─ .gitignore
├─ README.md
├─ requirements.txt
├─ main.py # FastAPI backend
└─ bot.py # Telegram bot
