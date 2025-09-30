# Nutricare App 

Nutricare is a **child malnutrition tracking system** designed for primary healthcare workers. It consists of a FastAPI backend, a Telegram bot for quick patient registration, and optional web dashboard (React) integration.
---

## Prerequisites
- Python 3.10 or higher
- pip (Python package manager)

## Features
- **Dashboard**: View patient summaries (total, SAM, MAM, Normal) and a table of all patients.
- **Add Patient**: Enter patient details (name, age, weight, height, MUAC) via a form.
- **API Endpoints**:
- `GET /`: Health check.
- `POST /patients`: Add a new patient.
- `GET /patients`: List all patients.
- `GET /export`: Export patient data as CSV.
- **Nutrition Classification**: Uses WHO standards for 0-5 years children (MUAC <115 mm for SAM, 115-125 mm for MAM, >125 mm for Normal) and original cutoffs for >5 years.

## Development
- The app uses SQLite by default. For production, configure a different `DATABASE_URL` (e.g., PostgreSQL).
- Customize `templates/dashboard.html` for styling or additional features.

## Contributing
Feel free to submit issues or pull requests on the repository.
## **Links**
GitHub Repository: https://github.com/Pash-Data/Nutricare
Access: https://nutricare-nvw0.onrender.com/dashboard for dashboard
Access: https://nutricare-nvw0.onrender.com/patients for database
Access: https://nutricare-nvw0.onrender.com/export for download
Access: https://t.me/Nutricare_helper_bot for nutricare AI agent 
Render: https://render.com (for deployment)

Acknowledgments
Thanks to the open-source communities of FastAPI, python-telegram-bot, and SQLModel.
