@echo off
echo ==============================
echo Testing Nutricare FastAPI
echo ==============================

:: Test root endpoint
echo.
echo 1️⃣ Root endpoint (/)
curl "https://nutricare-nvw0.onrender.com/"
echo.
echo ------------------------------

:: Add a patient (POST /patients)
echo 2️⃣ Add patient (/patients)
curl -X POST "https://nutricare-nvw0.onrender.com/patients" -H "Content-Type: application/json" -d "{\"name\":\"John\",\"age\":5,\"weight_kg\":15,\"height_cm\":100,\"muac_mm\":120}"
echo.
echo ------------------------------

:: Get all patients (GET /patients)
echo 3️⃣ Get all patients (/patients)
curl "https://nutricare-nvw0.onrender.com/patients"
echo.
echo ==============================
echo Test complete
pause
