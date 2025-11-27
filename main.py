from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import csv
import os

app = FastAPI()

# Templates folder
templates = Jinja2Templates(directory="templates")

# Allow frontend + bot requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory database
patients_db = []


# Utility functions
def calculate_bmi(weight, height):
    h = height / 100
    return round(weight / (h * h), 2)

def classify_build(bmi):
    if bmi < 16:
        return "Severely underweight"
    elif bmi < 18.5:
        return "Underweight"
    elif bmi < 25:
        return "Normal"
    elif bmi < 30:
        return "Overweight"
    return "Obese"

def classify_muac(muac):
    if muac < 115:
        return "SAM"
    elif muac < 125:
        return "MAM"
    return "Normal"

def recommendation(status):
    if status == "SAM":
        return "Urgent referral to stabilization center + therapeutic feeding."
    elif status == "MAM":
        return "Supplementary feeding + weekly monitoring."
    else:
        return "Maintain balanced diet, follow up in 4 weeks."


# API — add via JSON
class Patient(BaseModel):
    name: str
    age: int
    weight_kg: float
    height_cm: float
    muac_mm: float

@app.post("/patients")
def api_add_patient(patient: Patient):
    bmi = calculate_bmi(patient.weight_kg, patient.height_cm)
    build = classify_build(bmi)
    status = classify_muac(patient.muac_mm)
    rec = recommendation(status)

    data = patient.dict()
    data.update({
        "bmi": bmi,
        "build": build,
        "nutrition_status": status,
        "recommendation": rec
    })

    patients_db.append(data)
    return {"status": "success", "data": data}


@app.get("/patients", response_model=List[dict])
def api_get_all():
    return patients_db


# ------------------------
# DASHBOARD ROUTES (HTML)
# ------------------------

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    summary = {
        "total": len(patients_db),
        "sam": len([p for p in patients_db if p["nutrition_status"] == "SAM"]),
        "mam": len([p for p in patients_db if p["nutrition_status"] == "MAM"]),
        "normal": len([p for p in patients_db if p["nutrition_status"] == "Normal"])
    }

    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "patients": patients_db, "summary": summary}
    )


@app.post("/dashboard/add")
def dashboard_add(
    request: Request,
    name: str = Form(...),
    age: int = Form(...),
    weight_kg: float = Form(...),
    height_cm: float = Form(...),
    muac_mm: float = Form(...)
):
    bmi = calculate_bmi(weight_kg, height_cm)
    build = classify_build(bmi)
    status = classify_muac(muac_mm)
    rec = recommendation(status)

    data = {
        "name": name,
        "age": age,
        "weight_kg": weight_kg,
        "height_cm": height_cm,
        "muac_mm": muac_mm,
        "bmi": bmi,
        "build": build,
        "nutrition_status": status,
        "recommendation": rec
    }

    patients_db.append(data)
    return dashboard(request)  # reload page


@app.get("/export")
def export_csv():
    filename = "patients.csv"

    with open(filename, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=patients_db[0].keys() if patients_db else [])
        writer.writeheader()
        for row in patients_db:
            writer.writerow(row)

    return FileResponse(filename, media_type="text/csv", filename=filename)
