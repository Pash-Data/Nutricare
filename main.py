from dotenv import load_dotenv
import os
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
from fastapi.middleware.cors import CORSMiddleware

# Load environment variables
load_dotenv()

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

# MUAC classification
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
    nutrition_status = classify_muac(patient.muac_mm)

    patient_dict = patient.dict()
    patient_dict.update({
        "bmi": bmi,
        "build": build,
        "nutrition_status": nutrition_status
    })

    patients_db.append(patient_dict)

    return {
        "status": "success",
        "data": patient_dict
    }

@app.get("/")
def root():
    return {"message": "Nutricare API is running!"}
    
@app.get("/patients", response_model=List[dict])
def get_patients():
    return patients_db

