from dotenv import load_dotenv
import os
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List
from fastapi.middleware.cors import CORSMiddleware
import csv
import io
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackContext

load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN not set in environment")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup Telegram Application for webhooks
application = Application.builder().token(TELEGRAM_TOKEN).build()

# Pydantic models
class Patient(BaseModel):
    name: str
    age: int
    weight_kg: float
    height_cm: float
    muac_mm: float

class PatientResponse(Patient):
    bmi: float
    build: str
    nutrition_status: str
    recommendation: str  # New field for MUAC recommendations

patients_db: List[PatientResponse] = []

# Utility functions
def calculate_bmi(weight, height):
    height_m = height / 100
    return round(weight / (height_m ** 2), 2)

def classify_build(bmi):
    if bmi < 16:
        return "Severely underweight"
    elif bmi < 18.5:
        return "Underweight"
    elif bmi < 25:
        return "Normal"
    elif bmi < 30:
        return "Overweight"
    else:
        return "Obese"

def classify_muac(muac):
    if muac < 115:
        return "SAM"  # Severe Acute Malnutrition
    elif muac < 125:
        return "MAM"  # Moderate Acute Malnutrition
    else:
        return "Normal"

def get_recommendation(nutrition_status):
    if nutrition_status == "SAM":
        return "Severe Acute Malnutrition - Immediate referral to therapeutic feeding program, medical evaluation, and supplementary feeding."
    elif nutrition_status == "MAM":
        return "Moderate Acute Malnutrition - Provide supplementary feeding, monitor closely, and educate on balanced diet."
    else:
        return "Normal - Maintain healthy diet and regular check-ups."

# Bot states and handlers (adapted for webhook)
NAME, AGE, WEIGHT, HEIGHT, MUAC = range(5)

async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text('Welcome to NutriCare Bot! Use /add to add a patient or /list to view patients.')

async def add_patient(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text('Enter patient name:')
    return NAME

async def name(update: Update, context: CallbackContext) -> int:
    context.user_data['name'] = update.message.text
    await update.message.reply_text('Enter age:')
    return AGE

async def age(update: Update, context: CallbackContext) -> int:
    try:
        context.user_data['age'] = int(update.message.text)
    except ValueError:
        await update.message.reply_text('Invalid age. Enter a number:')
        return AGE
    await update.message.reply_text('Enter weight in kg:')
    return WEIGHT

async def weight(update: Update, context: CallbackContext) -> int:
    try:
        context.user_data['weight'] = float(update.message.text)
    except ValueError:
        await update.message.reply_text('Invalid weight. Enter a number:')
        return WEIGHT
    await update.message.reply_text('Enter height in cm:')
    return HEIGHT

async def height(update: Update, context: CallbackContext) -> int:
    try:
        context.user_data['height'] = float(update.message.text)
    except ValueError:
        await update.message.reply_text('Invalid height. Enter a number:')
        return HEIGHT
    await update.message.reply_text('Enter MUAC in mm:')
    return MUAC

async def muac(update: Update, context: CallbackContext) -> int:
    try:
        context.user_data['muac'] = float(update.message.text)
    except ValueError:
        await update.message.reply_text('Invalid MUAC. Enter a number:')
        return MUAC

    data = context.user_data
    bmi = calculate_bmi(data['weight'], data['height'])
    build = classify_build(bmi)
    nutrition_status = classify_muac(data['muac'])
    recommendation = get_recommendation(nutrition_status)

    feedback = f"Patient: {data['name']}, Age: {data['age']}\nBMI: {bmi} ({build})\nNutrition: {nutrition_status}\nRecommendation: {recommendation}"
    await update.message.reply_text(feedback)

    # Add to DB
    patient_dict = {
        "name": data['name'],
        "age": data['age'],
        "weight_kg": data['weight'],
        "height_cm": data['height'],
        "muac_mm": data['muac'],
        "bmi": bmi,
        "build": build,
        "nutrition_status": nutrition_status,
        "recommendation": recommendation
    }
    patient_response = PatientResponse(**patient_dict)
    patients_db.append(patient_response)
    await update.message.reply_text('Patient added!')

    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text('Operation cancelled.')
    context.user_data.clear()
    return ConversationHandler.END

async def list_patients(update: Update, context: CallbackContext) -> None:
    if not patients_db:
        await update.message.reply_text('No patients in database.')
        return
    msg = "Patients:\n"
    for p in patients_db:
        msg += f"{p.name}: BMI {p.bmi} ({p.build}), Nutrition: {p.nutrition_status}, Rec: {p.recommendation}\n"
    await update.message.reply_text(msg)

# Setup bot handlers
conv_handler = ConversationHandler(
    entry_points=[CommandHandler('add', add_patient)],
    states={
        NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name)],
        AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, age)],
        WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, weight)],
        HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, height)],
        MUAC: [MessageHandler(filters.TEXT & ~filters.COMMAND, muac)],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)

application.add_handler(CommandHandler('start', start))
application.add_handler(CommandHandler('list', list_patients))
application.add_handler(conv_handler)

# Webhook endpoint
@app.post(f"/webhook/{TELEGRAM_TOKEN}")
async def webhook(request: Request):
    json_data = await request.json()
    update = Update.de_json(json_data, application.bot)
    await application.process_update(update)
    return {"ok": True}

# API Routes
@app.get("/")
def root():
    return {"message": "Nutricare API is running!"}

@app.post("/patients", response_model=PatientResponse)
def add_patient(patient: Patient):
    bmi = calculate_bmi(patient.weight_kg, patient.height_cm)
    build = classify_build(bmi)
    nutrition_status = classify_muac(patient.muac_mm)
    recommendation = get_recommendation(nutrition_status)

    patient_dict = patient.dict()
    patient_dict.update({
        "bmi": bmi,
        "build": build,
        "nutrition_status": nutrition_status,
        "recommendation": recommendation
    })

    patient_response = PatientResponse(**patient_dict)
    patients_db.append(patient_response)
    return patient_response

@app.get("/patients", response_model=List[PatientResponse])
def get_patients():
    return patients_db

@app.get("/export")
def export_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["name", "age", "weight_kg", "height_cm", "muac_mm", "bmi", "build", "nutrition_status", "recommendation"])
    for p in patients_db:
        writer.writerow([p.name, p.age, p.weight_kg, p.height_cm, p.muac_mm, p.bmi, p.build, p.nutrition_status, p.recommendation])
    output.seek(0)
    return StreamingResponse(output, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=patients.csv"})

# Dashboard setup
templates = Jinja2Templates(directory="templates")

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    summary = {
        "total": len(patients_db),
        "sam": sum(1 for p in patients_db if p.nutrition_status == "SAM"),
        "mam": sum(1 for p in patients_db if p.nutrition_status == "MAM"),
        "normal": sum(1 for p in patients_db if p.nutrition_status == "Normal")
    }
    return templates.TemplateResponse("dashboard.html", {"request": request, "patients": patients_db, "summary": summary})

@app.post("/dashboard/add")
async def add_from_dashboard(name: str = Form(...), age: int = Form(...), weight_kg: float = Form(...), height_cm: float = Form(...), muac_mm: float = Form(...)):
    patient = Patient(name=name, age=age, weight_kg=weight_kg, height_cm=height_cm, muac_mm=muac_mm)
    add_patient(patient)  # Reuse the add function
    return {"message": "Patient added"}
