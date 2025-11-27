from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Dict
import csv
import io
import os
from dotenv import load_dotenv
import asyncio

# Telegram Bot
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

load_dotenv()

# === CONFIG ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    print("WARNING: TELEGRAM_TOKEN not set — bot will not start")

# In-memory storage (replaces database)
patients: List[Dict] = []

# FastAPI app
app = FastAPI(title="NutriCare")
templates = Jinja2Templates(directory="templates")

# Pydantic models
class Patient(BaseModel):
    name: str
    age: int
    weight_kg: float
    height_cm: float
    muac_mm: float

class PatientResponse(Patient):
    id: int
    bmi: float
    build: str
    nutrition_status: str
    recommendation: str

# === CALCULATION FUNCTIONS ===
def calculate_bmi(weight, height):
    return round(weight / ((height / 100) ** 2), 2)

def classify_build(bmi):
    if bmi < 16: return "Severely underweight"
    elif bmi < 18.5: return "Underweight"
    elif bmi < 25: return "Normal"
    elif bmi < 30: return "Overweight"
    else: return "Obese"

def classify_muac(muac, age):
    if age <= 5:
        if muac < 115: return "SAM (Severe Acute Malnutrition)"
        elif muac < 125: return "MAM (Moderate Acute Malnutrition)"
        else: return "Normal"
    else:
        if muac < 115: return "SAM"
        elif muac < 125: return "MAM"
        else: return "Normal"

def get_recommendation(status):
    if "SAM" in status:
        return "URGENT: Severe Acute Malnutrition — Refer to therapeutic feeding immediately."
    elif "MAM" in status:
        return "Moderate Acute Malnutrition — Provide supplementary food and monitoring."
    else:
        return "Normal — Continue healthy diet and regular check-ups."

# === FASTAPI ROUTES ===
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    summary = {
        "total": len(patients),
        "sam": sum(1 for p in patients if "SAM" in p["nutrition_status"]),
        "mam": sum(1 for p in patients if "MAM" in p["nutrition_status"]),
        "normal": sum(1 for p in patients if "Normal" in p["nutrition_status"])
    }
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "patients": patients,
        "summary": summary
    })

@app.post("/patients", response_model=PatientResponse)
def add_patient(patient: Patient):
    bmi = calculate_bmi(patient.weight_kg, patient.height_cm)
    build = classify_build(bmi)
    status = classify_muac(patient.muac_mm, patient.age)
    recommendation = get_recommendation(status)

    new_patient = {
        "id": len(patients) + 1,
        "name": patient.name,
        "age": patient.age,
        "weight_kg": patient.weight_kg,
        "height_cm": patient.height_cm,
        "muac_mm": patient.muac_mm,
        "bmi": bmi,
        "build": build,
        "nutrition_status": status,
        "recommendation": recommendation
    }
    patients.append(new_patient)
    return PatientResponse(**new_patient)

@app.get("/export")
def export_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Name", "Age", "Weight(kg)", "Height(cm)", "MUAC(mm)", "BMI", "Build", "Status", "Recommendation"])
    for p in patients:
        writer.writerow([p["id"], p["name"], p["age"], p["weight_kg"], p["height_cm"], p["muac_mm"], p["bmi"], p["build"], p["nutrition_status"], p["recommendation"]])
    output.seek(0)
    return StreamingResponse(output, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=nutricare_patients.csv"})

# === TELEGRAM BOT ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "NutriCare Bot Active!\n"
        "Send patient data in this format:\n\n"
        "Name: John Doe\nAge: 4\nWeight: 12.5\nHeight: 95\nMUAC: 118"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send patient details — I'll analyze instantly!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        lines = [l.strip() for l in text.split("\n") if ":" in l]
        data = {}
        for line in lines:
            key, value = line.split(":", 1)
            key = key.strip().lower()
            value = value.strip()
            if "name" in key: data["name"] = value
            elif "age" in key: data["age"] = int(value)
            elif "weight" in key: data["weight_kg"] = float(value)
            elif "height" in key: data["height_cm"] = float(value)
            elif "muac" in key: data["muac_mm"] = float(value)

        if len(data) != 5:
            await update.message.reply_text("Please provide all: Name, Age, Weight, Height, MUAC")
            return

        patient = Patient(**data)
        result = add_patient(patient)

        response = (
            f"*{result.name}* ({result.age} years)\n\n"
            f"BMI: {result.bmi} → *{result.build}*\n"
            f"MUAC: {result.muac_mm} mm → *{result.nutrition_status}*\n\n"
            f"*{result.recommendation}*"
        )
        await update.message.reply_text(response, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}\nSend data correctly.")

# Start Telegram bot in background
if TELEGRAM_TOKEN:
    app_bot = Application.builder().token(TELEGRAM_TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("help", help_command))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    async def run_bot():
        await app_bot.initialize()
        await app_bot.start()
        await app_bot.updater.start_polling()
        print("Telegram bot started!")
        while True:
            await asyncio.sleep(3600)

    # Run bot in background
    @app.on_event("startup")
    async def startup_event():
        asyncio.create_task(run_bot())

else:
    print("No TELEGRAM_TOKEN — bot disabled")

# === HTML FORM POST ===
@app.post("/add")
async def add_from_form(
    name: str = Form(...),
    age: int = Form(...),
    weight_kg: float = Form(...),
    height_cm: float = Form(...),
    muac_mm: float = Form(...)
):
    patient = Patient(name=name, age=age, weight_kg=weight_kg, height_cm=height_cm, muac_mm=muac_mm)
    add_patient(patient)
    return {"success": True, "message": "Patient added!"}
