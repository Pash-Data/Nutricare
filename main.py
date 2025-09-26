from dotenv import load_dotenv
import os
import logging
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List
from fastapi.middleware.cors import CORSMiddleware
import csv
import io
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackContext
from sqlmodel import Field, Session, SQLModel, create_engine, select, Text

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN:
    logger.warning("TELEGRAM_TOKEN not set; bot will not initialize")

DATABASE_URL = os.getenv('DATABASE_URL', "sqlite:///patients.db")

engine = create_engine(DATABASE_URL, echo=False)

class PatientDB(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    age: int
    weight_kg: float
    height_cm: float
    muac_mm: float
    bmi: float
    build: str
    nutrition_status: str
    recommendation: str = Field(sa_column=Text)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

create_db_and_tables()

def get_session():
    with Session(engine) as session:
        yield session

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global application instance
application = None

@app.on_event("startup")
async def startup_event():
    global application
    if TELEGRAM_TOKEN:
        try:
            logger.info("Initializing Telegram application...")
            application = Application.builder().token(TELEGRAM_TOKEN).build()
            NAME, AGE, WEIGHT, HEIGHT, MUAC = range(5)

            async def start(update: Update, context: CallbackContext) -> None:
                await update.message.reply_text('Welcome to NutriCare Bot! Use /add to add a patient or /list to view patients.')

            # ... (include all other handlers as before: add_patient, name, age, weight, height, muac, cancel, list_patients, export_csv)

            # Add handlers
            application.add_handler(CommandHandler('start', start))
            application.add_handler(CommandHandler('list', list_patients))
            application.add_handler(conv_handler)  # Include conv_handler definition
            logger.info("Telegram bot initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Telegram bot: {e}")
            application = None

# Webhook endpoint
@app.post("/webhook")
async def webhook(request: Request):
    global application
    if not application:
        return {"ok": False, "error": "Telegram application not initialized"}
    try:
        json_data = await request.json()
        update = Update.de_json(json_data, application.bot)
        await application.process_update(update)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return {"ok": False, "error": str(e)}

# ... (rest of the code for Patient, PatientResponse, utility functions, API routes, dashboard, etc., as in your original)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
