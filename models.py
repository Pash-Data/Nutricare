from sqlmodel import SQLModel, Field
from pydantic import BaseModel
from typing import Optional

# Database model
class PatientDB(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    age: int
    weight_kg: float
    height_cm: float
    muac_mm: float
    bmi: float
    build: str
    nutrition_status: str
    recommendation: str

# Pydantic input model
class Patient(BaseModel):
    name: str
    age: int
    weight_kg: float
    height_cm: float
    muac_mm: float

# Pydantic response model
class PatientResponse(BaseModel):
    id: Optional[int]
    name: str
    age: int
    weight_kg: float
    height_cm: float
    muac_mm: float
    bmi: float
    build: str
    nutrition_status: str
    recommendation: str

    class Config:
        orm_mode = True

# Functions
def calculate_bmi(weight_kg: float, height_cm: float) -> float:
    height_m = height_cm / 100
    return weight_kg / (height_m * height_m)

def classify_build(bmi: float) -> str:
    if bmi < 18.5:
        return "Underweight"
    elif 18.5 <= bmi < 25:
        return "Normal"
    elif 25 <= bmi < 30:
        return "Overweight"
    else:
        return "Obese"

def classify_muac(muac_mm: float) -> str:
    if muac_mm < 115:
        return "SAM"  # Severe Acute Malnutrition
    elif 115 <= muac_mm < 125:
        return "MAM"  # Moderate Acute Malnutrition
    else:
        return "Normal"

def get_recommendation(nutrition_status: str) -> str:
    recommendations = {
        "SAM": "Immediate medical attention and nutritional support required.",
        "MAM": "Nutritional supplementation recommended.",
        "Normal": "Maintain healthy diet and regular check-ups."
    }
    return recommendations.get(nutrition_status, "Consult a healthcare provider.") 
