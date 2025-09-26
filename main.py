from dotenv import load_dotenv
import os
import traceback
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
import asyncio

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# Debug for Alembic environment
print("Running in Alembic:", "alembic" in traceback.format_stack()[-1].lower())
if "alembic" not in traceback.format_stack()[-1].lower():
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_TOKEN not set in environment")
else:
    TELEGRAM_TOKEN = None

DATABASE_URL = os.getenv('DATABASE_URL', "sqlite:///patients.db")

engine = create_engine(DATABASE_URL, echo=True)  # Remove echo=True in production

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

# Global application instance with initialization lock
application = None
is_telegram_initialized = False
telegram_init_lock = asyncio.Lock()

async def setup_telegram():
    global application, is_telegram_initialized
    async with telegram_init_lock:
        if TELEGRAM_TOKEN and not is_telegram_initialized:
            try:
                application = Application.builder().token(TELEGRAM_TOKEN).build()
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
                    with Session(engine) as session:
                        patient_db = PatientDB(
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
                        session.add(patient_db)
                        session.commit()
                    await update.message.reply_text('Patient added to database!')
                    context.user_data.clear()
                    return ConversationHandler.END

                async def cancel(update: Update, context: CallbackContext) -> int:
                    await update.message.reply_text('Operation cancelled.')
                    context.user_data.clear()
                    return ConversationHandler.END

                async def list_patients(update: Update, context: CallbackContext) -> None:
                    with Session(engine) as session:
                        patients = session.exec(select(PatientDB)).all()
                    if not patients:
                        await update.message.reply_text('No patients in database.')
                        return
                    msg = "Patients:\n"
                    for p in patients:
                        msg += f"{p.name}: BMI {p.bmi} ({p.build}), Nutrition: {p.nutrition_status}, Rec: {p.recommendation[:50]}...\n"
                    await update.message.reply_text(msg)

                async def export_csv(update: Update, context: CallbackContext) -> None:
                    with Session(engine) as session:
                        patients = session.exec(select(PatientDB)).all()
                        output = io.StringIO()
                        writer = csv.writer(output)
                        writer.writerow(["id", "name", "age", "weight_kg", "height_cm", "muac_mm", "bmi", "build", "nutrition_status", "recommendation"])
                        for p in patients:
                            writer.writerow([p.id, p.name, p.age, p.weight_kg, p.height_cm, p.muac_mm, p.bmi, p.build, p.nutrition_status, p.recommendation])
                        output.seek(0)
                        await update.message.reply_document(document=output, filename="patients.csv")
                        output.close()

                # Add handlers
                application.add_handler(CommandHandler('start', start))
                application.add_handler(CommandHandler('list', list_patients))
                application.add_handler(CommandHandler('export', export_csv))
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
                application.add_handler(conv_handler)

                # Initialize and start the bot
                await application.initialize()
                await application.start()
                is_telegram_initialized = True
                logger.info("Telegram bot started with webhook support")
            except Exception as e:
                logger.error(f"Failed to initialize Telegram bot: {e}")
                raise

# Run Telegram setup on app startup
app.add_event_handler("startup", setup_telegram)

# Webhook endpoint with initialization check
@app.post("/webhook")
async def webhook(request: Request):
    global application, is_telegram_initialized
    if not is_telegram_initialized or not application:
        logger.error("Telegram application not initialized")
        return {"ok": False, "error": "Telegram application not initialized"}
    try:
        json_data = await request.json()
        update = Update.de_json(json_data, application.bot)
        await application.process_update(update)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return {"ok": False, "error": str(e)}

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
        return "SAM"
    elif muac < 125:
        return "MAM"
    else:
        return "Normal"

def get_recommendation(nutrition_status):
    if nutrition_status == "SAM":
        return "Severe Acute Malnutrition - Immediate referral to therapeutic feeding program, medical evaluation, and supplementary feeding."
    elif nutrition_status == "MAM":
        return "Moderate Acute Malnutrition - Provide supplementary feeding, monitor closely, and educate on balanced diet."
    else:
        return "Normal - Maintain healthy diet and regular check-ups."

@app.get("/")
def root():
    return {"message": "Nutricare API is running!"}

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
    return PatientResponse(id=db_patient.id, **db_patient.dict(exclude={'id'}))

@app.get("/patients", response_model=List[PatientResponse])
def get_patients(session: Session = Depends(get_session)):
    patients = session.exec(select(PatientDB)).all()
    return [PatientResponse(id=p.id, **p.dict(exclude={'id'})) for p in patients]

@app.get("/export")
def export_csv(session: Session = Depends(get_session)):
    patients = session.exec(select(PatientDB)).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "name", "age", "weight_kg", "height_cm", "muac_mm", "bmi", "build", "nutrition_status", "recommendation"])
    for p in patients:
        writer.writerow([p.id, p.name, p.age, p.weight_kg, p.height_cm, p.muac_mm, p.bmi, p.build, p.nutrition_status, p.recommendation])
    output.seek(0)
    return StreamingResponse(output, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=patients.csv"})

templates = Jinja2Templates(directory="templates")

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, session: Session = Depends(get_session)):
    patients = session.exec(select(PatientDB)).all()
    summary = {
        "total": len(patients),
        "sam": sum(1 for p in patients if p.nutrition_status == "SAM"),
        "mam": sum(1 for p in patients if p.nutrition_status == "MAM"),
        "normal": sum(1 for p in patients if p.nutrition_status == "Normal")
    }
    return templates.TemplateResponse("dashboard.html", {"request": request, "patients": patients, "summary": summary})

@app.post("/dashboard/add")
async def add_from_dashboard(name: str = Form(...), age: int = Form(...), weight_kg: float = Form(...), height_cm: float = Form(...), muac_mm: float = Form(...), session: Session = Depends(get_session)):
    patient = Patient(name=name, age=age, weight_kg=weight_kg, height_cm=height_cm, muac_mm=muac_mm)
    return add_patient_api(patient, session)
