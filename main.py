from dotenv import load_dotenv
import os
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

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
    bmi: float
    build: str
    nutrition_status: str

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
        return "SAM"
    elif muac < 125:
        return "MAM"
    else:
        return "Normal"

# Routes
@app.get("/")
def root():
    return {"message": "Nutricare API is running!"}

@app.post("/patients", response_model=PatientResponse)
def add_patient(patient: Patient):
    bmi = calculate_bmi(patient.weight_kg, patient.height_cm)
    build = classify_build(bmi)
    nutrition_status = classify_muac(patient.muac_mm)

    patient_dict = patient.dict()
    patient_dict.update({
        "bmi": bmi,
        "build": build,
        "nutrition_status": nutrition_status
    })

    patient_response = PatientResponse(**patient_dict)
    patients_db.append(patient_response)
    return patient_response

@app.get("/patients", response_model=List[PatientResponse])
def get_patients():
    return patients_db
