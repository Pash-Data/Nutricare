from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Dict
import csv
import io
import os
import asyncio
from dotenv import load_dotenv

# Telegram
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# ================= APP =================
app = FastAPI()
templates = Jinja2Templates(directory="templates")

patients: List[Dict] = []

# ================= MODELS =================
class Patient(BaseModel):
    name: str
    age: int
    weight_kg: float
    height_cm: float
    muac_mm: float

# ================= HELPERS ================
def calculate_bmi(w, h):
    return round(w / ((h / 100) ** 2), 2)

def classify_build(bmi):
    if bmi < 16: return "Severely underweight"
    elif bmi < 18.5: return "Underweight"
    elif bmi < 25: return "Normal"
    elif bmi < 30: return "Overweight"
    else: return "Obese"

def classify_muac(muac, age):
    if muac < 115: return "SAM (Severe Acute Malnutrition)"
    elif muac < 125: return "MAM (Moderate Acute Malnutrition)"
    else: return "Normal"

def get_recommendation(status):
    if "SAM" in status: return "URGENT: Refer to therapeutic feeding immediately"
    elif "MAM" in status: return "Provide supplementary feeding + monitoring"
    else: return "Normal – maintain healthy diet"

# ================= ROUTES =================
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    summary = {
        "total": len(patients),
        "sam": sum(1 for p in patients if "SAM" in p["nutrition_status"]),
        "mam": sum(1 for p in patients if "MAM" in p["nutrition_status"]),
        "normal": sum(1 for p in patients if "Normal" in p["nutrition_status"]),
    }
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "patients": patients,
        "summary": summary
    })


@app.post("/add")
async def add_patient(
    name: str = Form(...),
    age: int = Form(...),
    weight_kg: float = Form(...),
    height_cm: float = Form(...),
    muac_mm: float = Form(...)
):
    bmi = calculate_bmi(weight_kg, height_cm)
    status = classify_muac(muac_mm, age)
    rec = get_recommendation(status)

    patient_data = {
        "id": len(patients) + 1,
        "name": name,
        "age": age,
        "weight_kg": weight_kg,
        "height_cm": height_cm,
        "muac_mm": muac_mm,
        "bmi": bmi,
        "build": classify_build(bmi),
        "nutrition_status": status,
        "recommendation": rec
    }
    patients.append(patient_data)

    return RedirectResponse("/", status_code=303)


@app.get("/export")
def export_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID","Name","Age","Weight(kg)","Height(cm)","MUAC(mm)","BMI","Status","Recommendation"])

    for p in patients:
        writer.writerow([
            p["id"], p["name"], p["age"], p["weight_kg"], p["height_cm"],
            p["muac_mm"], p["bmi"], p["nutrition_status"], p["recommendation"]
        ])

    output.seek(0)
    return StreamingResponse(output, media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=nutricare.csv"}
    )

# ================= TELEGRAM BOT =================

if TELEGRAM_TOKEN:
    bot_app = Application.builder().token(TELEGRAM_TOKEN).build()

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "NutriCare Bot is ON!\n\nSend:\n"
            "Name: Aisha\nAge: 4\nWeight: 11.5\nHeight: 92\nMUAC: 112"
        )

    async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            text = update.message.text.strip()
            data = {}

            for line in text.split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    key = k.strip().lower()
                    val = v.strip()

                    if "name" in key: data["name"] = val
                    elif "age" in key: data["age"] = int(val)
                    elif "weight" in key: data["weight_kg"] = float(val)
                    elif "height" in key: data["height_cm"] = float(val)
                    elif "muac" in key: data["muac_mm"] = float(val)

            if len(data) != 5:
                await update.message.reply_text("Send all 5 fields.")
                return

            p = Patient(**data)
            bmi = calculate_bmi(p.weight_kg, p.height_cm)
            status = classify_muac(p.muac_mm, p.age)
            rec = get_recommendation(status)

            await update.message.reply_text(
                f"*{p.name}* ({p.age}y)\n"
                f"BMI: {bmi} → {classify_build(bmi)}\n"
                f"MUAC: {p.muac_mm} → {status}\n\n"
                f"{rec}",
                parse_mode="Markdown"
            )

        except Exception as e:
            await update.message.reply_text(f"Error: {str(e)}")

    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    @app.on_event("startup")
    async def start_bot():
        asyncio.create_task(bot_app.run_polling())

else:
    print("Telegram bot disabled — no token found.")
