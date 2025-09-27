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
from bot import initialize_telegram_bot
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
