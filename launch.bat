@echo off
netstat -ano | findstr /C:":5000 " >nul 2>&1
if errorlevel 1 (
    start "" /B .venv\Scripts\python.exe server.py
    timeout /t 3 /nobreak >nul
)
start "" "http://localhost:5000"
