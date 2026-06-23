@echo off
title SIRA Startup
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo Error: Python no encontrado en PATH.
    echo Instalalo o activa el entorno de Laragon.
    pause
    exit /b 1
)

python startup.py
if errorlevel 1 pause
