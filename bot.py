import os
import requests
import csv
from dotenv import load_dotenv
from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Load token from .env
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Backend API URL
API_URL = "http://127.0.0.1:8000/patients"

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to Nutricare Bot!\n\n"
        "To register a child, use:\n"
        "/add Name Age Weight(kg) Height(cm) MUAC(mm)\n\n"
        "Example:\n"
        "/add John 5 15 100 120\n\n"
        "Use /summary to see patient records.\n"
        "Use /export to download all records as CSV."
    )

# /add command
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        if len(args) != 5:
            await update.message.reply_text(
                "⚠️ Usage: /add Name Age Weight(kg) Height(cm) MUAC(mm)\n"
                "Example: /add John 5 15 100 120"
            )
            return

        name, age, weight, height, muac = args
        payload = {
            "name": name,
            "age": int(age),
            "weight_kg": float(weight),
            "height_cm": float(height),
            "muac_mm": float(muac)
        }

        response = requests.post(API_URL, json=payload)
        data = response.json()
        await update.message.reply_text(
            f"✅ Added: {data['data']['name']} ({data['data']['nutrition_status']})"
        )

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# /summary command
async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        response = requests.get(API_URL)
        patients = response.json()
        if not patients:
            await update.message.reply_text("📭 No patients yet.")
            return
        
        total = len(patients)
        sam = sum(1 for p in patients if p["nutrition_status"] == "SAM")
        mam = sum(1 for p in patients if p["nutrition_status"] == "MAM")
        normal = sum(1 for p in patients if p["nutrition_status"] == "Normal")

        header = (
            f"📊 **Nutricare Summary**\n"
            f"👥 Total patients: {total}\n"
            f"🚨 SAM: {sam} | ⚠️ MAM: {mam} | ✅ Normal: {normal}\n"
            "======================"
        )

        msg_lines = [header]
        for p in patients:
            if p["nutrition_status"] == "SAM":
                recommendation = "🚑 Immediate referral for therapeutic care."
            elif p["nutrition_status"] == "MAM":
                recommendation = "🥗 Provide supplementary feeding & follow-up."
            else:
                recommendation = "✅ Continue normal feeding, routine monitoring."

            msg_lines.append(
                f"👶 {p['name']} ({p['age']} yrs)\n"
                f"📏 Height: {p['height_cm']} cm | ⚖️ Weight: {p['weight_kg']} kg\n"
                f"📐 BMI: {p['bmi']} ({p['build']})\n"
                f"🎯 MUAC: {p['muac_mm']} mm → {p['nutrition_status']}\n"
                f"💡 Recommendation: {recommendation}\n"
                "----------------------"
            )
        
        msg = "\n".join(msg_lines)
        await update.message.reply_text(msg)

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# /export command
async def export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        response = requests.get(API_URL)
        patients = response.json()
        if not patients:
            await update.message.reply_text("📭 No patients to export.")
            return

        # Save to CSV
        filename = "patients_export.csv"
        with open(filename, mode="w", newline="") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=["name", "age", "weight_kg", "height_cm", "muac_mm", "bmi", "build", "nutrition_status"]
            )
            writer.writeheader()
            writer.writerows(patients)

        # Send file back to user
        with open(filename, "rb") as file:
            await update.message.reply_document(InputFile(file, filename))

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# Build and run bot
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("add", add))
app.add_handler(CommandHandler("summary", summary))
app.add_handler(CommandHandler("export", export))

print("Nutricare Bot is running...")
app.run_polling()
