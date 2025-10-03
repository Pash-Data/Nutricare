from dotenv import load_dotenv
import os
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List
from fastapi.middleware.cors import CORSMiddleware
import csv
import io
from sqlmodel import Field, Session, SQLModel, create_engine, select, Text

load_dotenv()

# Check if running in Alembic environment to avoid token requirement during migrations
if "ALEMBIC" not in os.environ:
    DATABASE_URL = os.getenv('DATABASE_URL', "sqlite:///patients.db")  # Fallback to SQLite for local
else:
    DATABASE_URL = "sqlite:///patients.db"  # Default for Alembic
# SQLAlchemy/SQLModel setup
engine = create_engine(DATABASE_URL, echo=True)  # echo=True for debug (remove in prod)

# SQLModel for Patient table
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

# Create DB and tables on startup
def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

create_db_and_tables()

# Dependency for DB session
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

# Pydantic models
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

def classify_muac(muac, age):
    if age <= 5:  # WHO standards for children 0-5 years
        if muac < 115:  # <11.5 cm
            return "SAM (Severe Acute Malnutrition)"
        elif muac < 125:  # 11.5-12.5 cm
            return "MAM (Moderate Acute Malnutrition)"
        else:  # >12.5 cm
            return "Normal"
    else:  # Original logic for ages >5
        if muac < 115:
            return "SAM"
        elif muac < 125:
            return "MAM"
        else:
            return "Normal"

def get_recommendation(nutrition_status):
    if "SAM" in nutrition_status:
        return "Severe Acute Malnutrition - Immediate referral to therapeutic feeding program, medical evaluation, and supplementary feeding."
    elif "MAM" in nutrition_status:
        return "Moderate Acute Malnutrition - Provide supplementary feeding, monitor closely, and educate on balanced diet."
    else:
        return "Normal - Maintain healthy diet and regular check-ups."

# API Routes
@app.get("/")
def root():
    return {"message": "Nutricare Web API is running!"}

@app.post("/patients", response_model=PatientResponse)
def add_patient_api(patient: Patient, session: Session = Depends(get_session)):
    bmi = calculate_bmi(patient.weight_kg, patient.height_cm)
    build = classify_build(bmi)
    nutrition_status = classify_muac(patient.muac_mm, patient.age)
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

# Dashboard setup
templates = Jinja2Templates(directory="templates")

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, session: Session = Depends(get_session)):
    patients = session.exec(select(PatientDB)).all()
    summary = {
        "total": len(patients),
        "sam": sum(1 for p in patients if "SAM" in p.nutrition_status),
        "mam": sum(1 for p in patients if "MAM" in p.nutrition_status),
        "normal": sum(1 for p in patients if "Normal" in p.nutrition_status)
    }
    return templates.TemplateResponse("dashboard.html", {"request": request, "patients": patients, "summary": summary})

@app.post("/dashboard/add")
async def add_from_dashboard(name: str = Form(...), age: int = Form(...), weight_kg: float = Form(...), height_cm: float = Form(...), muac_mm: float = Form(...), session: Session = Depends(get_session)):
    patient = Patient(name=name, age=age, weight_kg=weight_kg, height_cm=height_cm, muac_mm=muac_mm)
    return add_patient_api(patient, session)

if __name__ == "__main__":
    import uvicorn
    # Run FastAPI in the main thread
    config = uvicorn.Config("main:app", host="0.0.0.0", port=8000, reload=True)
    server = uvicorn.Server(config)
    server.run()
