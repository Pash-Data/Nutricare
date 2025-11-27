from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Dict
import csv
import io
import os
from dotenv import load_dotenv
import asyncio

# Telegram
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
patients: List[Dict] = []                               # in-memory, resets on deploy
templates = Jinja2Templates(directory=".")              # dashboard.html in root

app = FastAPI()

class Patient(BaseModel):
    name: str
    age: int
    weight_kg: float
    height_cm: float
    muac_mm: float

def calculate_bmi(w, h): return round(w/((h/100)**2), 2)
def classify_build(bmi):
    if bmi < 16: return "Severely underweight"
    elif bmi < 18.5: return "Underweight"
    elif bmi < 25: return "Normal"
    elif bmi < 30: return "Overweight"
    else: return "Obese"

def classify_muac(muac, _):                              # age not needed for simple rule
    if muac < 115: return "SAM (Severe Acute Malnutrition)"
    elif muac < 125: return "MAM (Moderate Acute Malnutrition)"
    else: return "Normal"

def get_recommendation(s):
    if "SAM" in s: return "URGENT – Refer to therapeutic feeding immediately"
    if "MAM" in s: return "Provide supplementary food + monitoring"
    return "Normal – continue healthy diet"

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    summary = {
        "total": len(patients),
        "sam": sum(1 for p in patients if "SAM" in p.get("nutrition_status","")),
        "mam": sum(1 for p in patients if "MAM" in p.get("nutrition_status","")),
        "normal": len(patients) - sum(1 for p in patients if "SAM" in p.get("nutrition_status","")) - sum(1 for p in patients if "MAM" in p.get("nutrition_status",""))
    }
    return templates.TemplateResponse("dashboard.html", {"request": request, "patients": patients, "summary": summary})

@app.post("/add")
async def add(name: str=Form(...), age: int=Form(...), weight_kg: float=Form(...), height_cm: float=Form(...), muac_mm: float=Form(...)):
    bmi = calculate_bmi(weight_kg, height_cm)
    new = {
        "id": len(patients)+1, "name": name, "age": age,
        "weight_kg": weight_kg, "height_cm": height_cm, "muac_mm": muac_mm,
        "bmi": bmi, "build": classify_build(bmi),
        "nutrition_status": classify_muac(muac_mm, age),
        "recommendation": get_recommendation(classify_muac(muac_mm, age))
    }
    patients.append(new)
    return RedirectResponse("/", status_code=303)

@app.get("/export")
def export():
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(["ID","Name","Age","Weight kg","Height cm","MUAC mm","BMI","Status","Recommendation"])
    for p in patients: w.writerow([p["id"],p["name"],p["age"],p["weight_kg"],p["height_cm"],p["muac_mm"],p["bmi"],p["nutrition_status"],p["recommendation"]])
    output.seek(0)
    return StreamingResponse(output, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=nutricare.csv"})

# Telegram bot (optional)
if TELEGRAM_TOKEN and TELEGRAM_TOKEN.strip():
    bot = Application.builder().token(TELEGRAM_TOKEN.strip()).build()
    async def start(u: Update, c): await u.message.reply_text("Send patient data → I’ll reply with result")
    async def msg(u: Update, c):
        try:
            d = {"name":"","age":0,"weight_kg":0.0,"height_cm":0.0,"muac_mm":0.0}
            for l in u.message.text.split("\n"):
                if ":" in l:
                    k,v = l.split(":",1)
                    k = k.strip().lower()
                    v = v.strip()
                    if "name" in k: d["name"]=v
                    if "age" in k: d["age"]=int(v)
                    if "weight" in k: d["weight_kg"]=float(v)
                    if "height" in k: d["height_cm"]=float(v)
                    if "muac" in k: d["muac_mm"]=float(v)
            p = Patient(**d)
            bmi = calculate_bmi(p.weight_kg, p.height_cm)
            status = classify_muac(p.muac_mm, p.age)
            await u.message.reply_text(f"*{p.name}*\nBMI {bmi} → {classify_build(bmi)}\nMUAC → *{status}*\n{get_recommendation(status)}", parse_mode="Markdown")
        except: await u.message.reply_text("Send all 5 fields correctly")
    bot.add_handler(CommandHandler("start", start))
    bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, msg))
    @app.on_event("startup")
    async def go(): 
        await bot.initialize(); await bot.start(); await bot.updater.start_polling()
