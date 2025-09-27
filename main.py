from dotenv import load_dotenv
import os
import traceback
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List
from fastapi.middleware.cors import CORSMiddleware
import csv
import io
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackContext
from sqlmodel import Field, Session, SQLModel, create_engine, select, Text

load_dotenv()

print("Running in Alembic:", "alembic" in traceback.format_stack()[-1].lower())
if "alembic" not in traceback.format_stack()[-1].lower():
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_TOKEN not set in environment")
else:
    TELEGRAM_TOKEN = None

DATABASE_URL = os.getenv('DATABASE_URL', "sqlite:///patients.db")

engine = create_engine(DATABASE_URL, echo=True)

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

# Initialize Telegram application at app creation
if TELEGRAM_TOKEN:
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    bot = Bot(TELEGRAM_TOKEN)

    # Conversation states
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
        with Session(engine) as session:
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
        summary = get_patient_summary(session)
        msg += f"\nSummary - Total: {summary['total']}, SAM: {summary['sam']}, MAM: {summary['mam']}, Normal: {summary['normal']}"
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

    def get_patient_summary(session: Session):
        patients = session.exec(select(PatientDB)).all()
        return {
            "total": len(patients),
            "sam": sum(1 for p in patients if p.nutrition_status == "SAM"),
            "mam": sum(1 for p in patients if p.nutrition_status == "MAM"),
            "normal": sum(1 for p in patients if p.nutrition_status == "Normal")
        }

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
    application.add_handler(CommandHandler('export', export_csv))
    application.add_handler(conv_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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

@app.post("/webhook")
async def webhook(request: Request):
    try:
        json_data = await request.json()
        update = Update.de_json(json_data, application.bot)
        await application.process_update(update)
        return {"ok": True}
    except Exception as e:
        print(f"Webhook error: {e}")
        return {"ok": False, "error": str(e)}

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
=======
from dotenv import load_dotenv
import os
import logging
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import csv
import io
from sqlmodel import Session, create_engine, select
from telegram_bot import initialize_telegram_bot
import asyncio

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL', "sqlite:///patients.db")

# Defer engine creation to startup
engine = None

# Import models lazily to avoid side effects
def import_models():
    from models import PatientDB, Patient, PatientResponse, calculate_bmi, classify_build, classify_muac, get_recommendation
    return PatientDB, Patient, PatientResponse, calculate_bmi, classify_build, classify_muac, get_recommendation

def get_session():
    global engine
    if not engine:
        raise HTTPException(status_code=500, detail="Database not initialized")
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

async def startup_event():
    global engine, application
    try:
        # Database setup
        engine = create_engine(DATABASE_URL, echo=False)
        SQLModel.metadata.create_all(engine)
        logger.info("Database initialized")

        # Import models after engine is set
        PatientDB, Patient, PatientResponse, calculate_bmi, classify_build, classify_muac, get_recommendation = import_models()

        # Telegram setup with timeout
        try:
            async with asyncio.timeout(10):  # 10-second timeout
                application = await initialize_telegram_bot(engine)  # Pass engine as argument
            if application:
                logger.info("Telegram bot initialized successfully")
            else:
                logger.warning("Telegram bot initialization failed or skipped")
        except asyncio.TimeoutError:
            logger.error("Telegram initialization timed out")
            application = None
        except Exception as e:
            logger.error(f"Telegram initialization error: {e}")
            application = None
    except Exception as e:
        logger.error(f"Startup error: {e}")
        application = None

# Webhook endpoint
@app.post("/webhook")
async def webhook(request: Request):
    global application
    if not application:
        return {"ok": False, "error": "Telegram application not initialized"}
    try:
        json_data = await request.json()
        from models import PatientDB  # Deferred import
        update = Update.de_json(json_data, application.bot)
        await application.process_update(update)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return {"ok": False, "error": str(e)}

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
    try:
        patients = session.exec(select(PatientDB)).all()
        summary = {
            "total": len(patients),
            "sam": sum(1 for p in patients if p.nutrition_status == "SAM"),
            "mam": sum(1 for p in patients if p.nutrition_status == "MAM"),
            "normal": sum(1 for p in patients if p.nutrition_status == "Normal")
        }
        return templates.TemplateResponse("dashboard.html", {"request": request, "patients": patients, "summary": summary})
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return {"detail": "Dashboard temporarily unavailable. Check logs."}

@app.post("/dashboard/add")
async def add_from_dashboard(name: str = Form(...), age: int = Form(...), weight_kg: float = Form(...), height_cm: float = Form(...), muac_mm: float = Form(...), session: Session = Depends(get_session)):
    patient = Patient(name=name, age=age, weight_kg=weight_kg, height_cm=height_cm, muac_mm=muac_mm)
    return add_patient_api(patient, session)

# Register the startup event
app.add_event_handler("startup", startup_event)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
