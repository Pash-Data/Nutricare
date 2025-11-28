from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import csv
from io import StringIO

app = FastAPI()

templates = Jinja2Templates(directory="templates")

# In-memory data storage
patients = []

# ----- Helper Functions -----

def calculate_bmi(weight, height):
    height_m = height / 100
    return round(weight / (height_m ** 2), 2)

def classify_build(bmi):
    if bmi < 16:
        return "Severely Underweight"
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

def get_recommendation(status):
    if status == "SAM":
        return "Urgent referral to stabilization center required."
    if status == "MAM":
        return "Provide supplementary feeding and follow-up."
    return "Child is healthy. Continue normal growth monitoring."


# ----- Dashboard Route -----
@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    summary = {
        "total": len(patients),
        "sam": sum(1 for p in patients if p["nutrition_status"] == "SAM"),
        "mam": sum(1 for p in patients if p["nutrition_status"] == "MAM"),
        "normal": sum(1 for p in patients if p["nutrition_status"] == "Normal"),
    }

    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "patients": patients, "summary": summary}
    )


# ----- Add Patient -----
@app.post("/dashboard/add")
def add_patient(
    request: Request,
    name: str = Form(...),
    age: int = Form(...),
    weight_kg: float = Form(...),
    height_cm: float = Form(...),
    muac_mm: float = Form(...)
):
    bmi = calculate_bmi(weight_kg, height_cm)
    build = classify_build(bmi)
    nutrition = classify_muac(muac_mm)
    recommendation = get_recommendation(nutrition)

    patients.append({
        "name": name,
        "age": age,
        "weight": weight_kg,
        "height": height_cm,
        "muac": muac_mm,
        "bmi": bmi,
        "build": build,
        "nutrition_status": nutrition,
        "recommendation": recommendation
    })

    return dashboard(request)


# ----- Export CSV -----
@app.get("/export")
def export_csv():
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Age", "BMI", "Build", "Nutrition", "Recommendation"])

    for p in patients:
        writer.writerow([p["name"], p["age"], p["bmi"], p["build"], p["nutrition_status"], p["recommendation"]])

    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=patients.csv"}
    )
