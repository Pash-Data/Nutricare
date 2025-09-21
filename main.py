from dotenv import load_dotenv
import os
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
from fastapi.middleware.cors import CORSMiddleware

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # Not required by backend, just safe to keep

app = FastAPI()

# Allow frontend + bot requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data model
class Patient(BaseModel):
    name: str
    age: int
    weight_kg: float
    height_cm: float
    muac_mm: float

patients_db = []

# Utility functions
def calculate_bmi(weight, height):
    height_m = height / 100
    bmi = weight / (height_m ** 2)
    return round(bmi, 2)

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

# API endpoints
@app.post("/patients")
def add_patient(patient: Patient):
    bmi = calculate_bmi(patient.weight_kg, patient.height_cm)
    build = classify_build(bmi)
    muac_status = classify_muac(patient.muac_mm)

    patient_dict = patient.dict()
    patient_dict.update({
        "bmi": bmi,
        "build": build,
        "nutrition_status": muac_status
    })

    patients_db.append(patient_dict)

    return {"status": "success", "data": patient_dict}

@app.get("/patients", response_model=List[dict])
def get_patients():
    return patients_db
