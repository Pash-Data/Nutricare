import os
import asyncio
import logging
import csv
import io
from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List

from sqlmodel import Field, Session, SQLModel, create_engine, select, Text

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, filters, ContextTypes

# -------------------- Logging --------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------------------- Environment --------------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    logger.warning("TELEGRAM_TOKEN not set. Telegram bot will not run.")

# Use DATABASE_URL from env (fallback: SQLite)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///patients.db")

# Important: Ensure pg8000 driver is used in production
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+pg8000://")

# -------------------- Database --------------------
engine = create_engine(DATABASE_URL, echo=False)

class PatientDB(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    age: int
    weight_kg: float
    height_cm: float
    muac_mm: float
    bmi: float
    build: str
    nutrition_status: str
    recommendation: str = Field(sa_column=Text)

SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session

# -------------------- FastAPI --------------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")

# -------------------- Pydantic --------------------
class Patient(BaseModel):
    name: str
    age: int
    weight_kg: float
    height_cm: float
    muac_mm: float

class PatientResponse(Patient):
    id: int | None = None
    bmi: float
    build: str
    nutrition_status: str
    recommendation: str

# -------------------- Utils --------------------
def calculate_bmi(weight, height):
    return round(weight / ((height / 100) ** 2), 2)

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
        return "SAM"
    elif muac < 125:
        return "MAM"
    else:
        return "Normal"

def get_recommendation(nutrition_status):
    if nutrition_status == "SAM":
        return "Severe Acute Malnutrition - Immediate referral and therapeutic feeding."
    elif nutrition_status == "MAM":
        return "Moderate Acute Malnutrition - Provide supplementary feeding and monitor."
    else:
        return "Normal - Maintain healthy diet and regular check-ups."

# -------------------- Telegram Bot --------------------
if TELEGRAM_TOKEN:
    bot_app = Application.builder().token(TELEGRAM_TOKEN).build()
    NAME, AGE, WEIGHT, HEIGHT, MUAC = range(5)

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Welcome to NutriCare Bot! Use /add to add patient or /list to view patients.")

    async def add_patient(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Enter patient name:")
        return NAME

    async def name(update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['name'] = update.message.text
        await update.message.reply_text("Enter age in months:")
        return AGE

    async def age(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            context.user_data['age'] = int(update.message.text)
        except ValueError:
            await update.message.reply_text("Invalid age. Enter a number:")
            return AGE
        await update.message.reply_text("Enter weight in kg:")
        return WEIGHT

    async def weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            context.user_data['weight'] = float(update.message.text)
        except ValueError:
            await update.message.reply_text("Invalid weight. Enter a number:")
            return WEIGHT
        await update.message.reply_text("Enter height in cm:")
        return HEIGHT

    async def height(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            context.user_data['height'] = float(update.message.text)
        except ValueError:
            await update.message.reply_text("Invalid height. Enter a number:")
            return HEIGHT
        await update.message.reply_text("Enter MUAC in mm:")
        return MUAC

    async def muac(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            context.user_data['muac'] = float(update.message.text)
        except ValueError:
            await update.message.reply_text("Invalid MUAC. Enter a number:")
            return MUAC

        data = context.user_data
        bmi = calculate_bmi(data['weight'], data['height'])
        build = classify_build(bmi)
        nutrition_status = classify_muac(data['muac'])
        recommendation = get_recommendation(nutrition_status)

        # Save to DB
        with Session(engine) as session:
            patient = PatientDB(
                name=data['name'],
                age=data['age'],
                weight_kg=data['weight'],
                height_cm=data['height'],
                muac_mm=data['muac'],
                bmi=bmi,
                build=build,
                nutrition_status=nutrition_status,
                recommendation=recommendation
            )
            session.add(patient)
            session.commit()

        await update.message.reply_text(
            f"Patient: {data['name']}\nBMI: {bmi} ({build})\nNutrition: {nutrition_status}\nRecommendation: {recommendation}"
        )

        context.user_data.clear()
        return ConversationHandler.END

    async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Operation cancelled.")
        context.user_data.clear()
        return ConversationHandler.END

    async def list_patients(update: Update, context: ContextTypes.DEFAULT_TYPE):
        with Session(engine) as session:
            patients = session.exec(select(PatientDB)).all()
        if not patients:
            await update.message.reply_text("No patients in database.")
            return
        msg = "Patients:\n"
        for p in patients:
            msg += f"{p.name}: BMI {p.bmi} ({p.build}), Nutrition: {p.nutrition_status}\n"
        await update.message.reply_text(msg)

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add_patient)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, age)],
            WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, weight)],
            HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, height)],
            MUAC: [MessageHandler(filters.TEXT & ~filters.COMMAND, muac)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("list", list_patients))
    bot_app.add_handler(conv_handler)

# -------------------- FastAPI Routes --------------------
@app.get("/")
def root():
    return {"message": "NutriCare API is running!"}

@app.post("/patients", response_model=PatientResponse)
def add_patient_api(patient: Patient, session: Session = Depends(get_session)):
    bmi = calculate_bmi(patient.weight_kg, patient.height_cm)
    build = classify_build(bmi)
    nutrition_status = classify_muac(patient.muac_mm)
    recommendation = get_recommendation(nutrition_status)
    db_patient = PatientDB(
        name=patient.name,
        age=patient.age,
        weight_kg=patient.weight_kg,
        height_cm=patient.height_cm,
        muac_mm=patient.muac_mm,
        bmi=bmi,
        build=build,
        nutrition_status=nutrition_status,
        recommendation=recommendation
    )
    session.add(db_patient)
    session.commit()
    session.refresh(db_patient)
    return PatientResponse(
        id=db_patient.id,
        name=db_patient.name,
        age=db_patient.age,
        weight_kg=db_patient.weight_kg,
        height_cm=db_patient.height_cm,
        muac_mm=db_patient.muac_mm,
        bmi=db_patient.bmi,
        build=db_patient.build,
        nutrition_status=db_patient.nutrition_status,
        recommendation=db_patient.recommendation,
    )

@app.get("/patients", response_model=List[PatientResponse])
def get_patients(session: Session = Depends(get_session)):
    patients = session.exec(select(PatientDB)).all()
    return [
        PatientResponse(
            id=p.id,
            name=p.name,
            age=p.age,
            weight_kg=p.weight_kg,
            height_cm=p.height_cm,
            muac_mm=p.muac_mm,
            bmi=p.bmi,
            build=p.build,
            nutrition_status=p.nutrition_status,
            recommendation=p.recommendation,
        )
        for p in patients
    ]

@app.get("/export")
def export_csv(session: Session = Depends(get_session)):
    patients = session.exec(select(PatientDB)).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id","name","age","weight_kg","height_cm","muac_mm","bmi","build","nutrition_status","recommendation"])
    for p in patients:
        writer.writerow([p.id,p.name,p.age,p.weight_kg,p.height_cm,p.muac_mm,p.bmi,p.build,p.nutrition_status,p.recommendation])
    output.seek(0)
    return StreamingResponse(output, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=patients.csv"})

# -------------------- Templates --------------------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, session: Session = Depends(get_session)):
    patients = session.exec(select(PatientDB)).all()
    summary = {
        "total": len(patients),
        "sam": sum(1 for p in patients if p.nutrition_status=="SAM"),
        "mam": sum(1 for p in patients if p.nutrition_status=="MAM"),
        "normal": sum(1 for p in patients if p.nutrition_status=="Normal")
    }
    return templates.TemplateResponse("dashboard.html", {"request": request, "patients": patients, "summary": summary})

@app.post("/dashboard/add")
def add_from_dashboard(name: str = Form(...), age: int = Form(...), weight_kg: float = Form(...), height_cm: float = Form(...), muac_mm: float = Form(...), session: Session = Depends(get_session)):
    patient = Patient(name=name, age=age, weight_kg=weight_kg, height_cm=height_cm, muac_mm=muac_mm)
    return add_patient_api(patient, session)

# -------------------- Run Both Bot + FastAPI --------------------
async def main():
    if TELEGRAM_TOKEN:
        asyncio.create_task(bot_app.run_polling())
    port = int(os.environ.get("PORT", 8000))
    import uvicorn
    uvicorn_config = uvicorn.Config("main:app", host="0.0.0.0", port=port)
    server = uvicorn.Server(uvicorn_config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
