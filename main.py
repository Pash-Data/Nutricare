from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Dict
import csv
import io
import os
from dotenv import load_dotenv
import asyncio

# Telegram
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

load_dotenv()

# ================= CONFIG =================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
patients: List[Dict] = []

# Fix for Render: template in root folder (not in subfolder)
templates = Jinja2Templates(directory=".")

app = FastAPI()

# ================= MODELS =================
class Patient(BaseModel):
    name: str
    age: int
    weight_kg: float
    height_cm: float
    muac_mm: float

# ================= CALCULATIONS =================
def calculate_bmi(w, h): return round(w / ((h/100)**2), 2)
def classify_build(bmi):
    if bmi < 16: return "Severely underweight"
    elif bmi < 18.5: return "Underweight"
    elif bmi < 25: return "Normal"
    elif bmi < 30: return "Overweight"
    else: return "Obese"

def classify_muac(muac, age):
    threshold_sam = 115
    threshold_mam = 125
    if muac < threshold_sam: return "SAM (Severe Acute Malnutrition)"
    elif muac < threshold_mam: return "MAM (Moderate Acute Malnutrition)"
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
        "sam": sum(1 for p in patients if "SAM" in p.get("nutrition_status", "")),
        "mam": sum(1 for p in patients if "MAM" in p.get("nutrition_status", "")),
        "normal": sum(1 for p in patients if "Normal" in p.get("nutrition_status", ""))
    }
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "patients": patients,
        "summary": summary
    })

@app.post("/add")
async def add_patient_form(
    name: str = Form(...),
    age: int = Form(...),
    weight_kg: float = Form(...),
    height_cm: float = Form(...),
    muac_mm: float = Form(...)
):
    patient = Patient(name=name, age=age, weight_kg=weight_kg,
                      height_cm=height_cm, muac_mm=muac_mm)
    
    bmi = calculate_bmi(patient.weight_kg, patient.height_cm)
    build = classify_build(bmi)
    status = classify_muac(patient.muac_mm, patient.age)
    rec = get_recommendation(status)

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
        "recommendation": rec
    }
    patients.append(new_patient)
    return RedirectResponse("/", status_code=303)

@app.get("/export")
def export_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID","Name","Age","Weight(kg)","Height(cm)","MUAC(mm)","BMI","Status","Recommendation"])
    for p in patients:
        writer.writerow([p["id"], p["name"], p["age"], p["weight_kg"], p["height_cm"],
                         p["muac_mm"], p["bmi"], p["nutrition_status"], p["recommendation"]])
    output.seek(0)
    return StreamingResponse(output, media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=nutricare.csv"})

# ================= TELEGRAM BOT =================
if TELEGRAM_TOKEN:
    bot_app = Application.builder().token(TELEGRAM_TOKEN).build()

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "NutriCare Bot is ON!\n\nSend patient data:\n"
            "Name: Musa\nAge: 5\nWeight: 14.5\nHeight: 100\nMUAC: 120"
        )

    async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            data = {}
            text = update.message.text.strip()
            for line in text.split("\n"):
                if ":" in line:
                    key, val = line.split(":", 1)
                    k = key.strip().lower()
                    v = val.strip()
                    if "name" in k: data["name"] = v
                    elif "age" in k: data["age"] = int(v)
                    elif "weight" in k: data["weight_kg"] = float(v)
                    elif "height" in k: data["height_cm"] = float(v)
                    elif "muac" in k: data["muac_mm"] = float(v)

            if len(data) != 5:
                await update.message.reply_text("Please send all 5 fields: Name, Age, Weight, Height, MUAC")
                return

            # Reuse the same logic as web form
            from tempfile import _get_candidate_names
            patient = Patient(**data)
            bmi = calculate_bmi(patient.weight_kg, patient.height_cm)
            status = classify_muac(patient.muac_mm, patient.age)
            rec = get_recommendation(status)

            response = (
                f"*{patient.name}* ({patient.age}y)\n\n"
                f"BMI: {bmi} → {classify_build(bmi)}\n"
                f"MUAC: {patient.muac_mm}mm → *{status}*\n\n"
                f"Recommendation: {rec}"
            )
            await update.message.reply_text(response, parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"Error: {str(e)}")

    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    @app.on_event("startup")
    async def startup_bot():
        await bot_app.initialize()
        await bot_app.start()
        await bot_app.updater.start_polling()
        print("Telegram bot running")

else:
    print("No TELEGRAM_TOKEN → bot disabled")
