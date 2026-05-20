@echo off
REM ============================================================
REM  Demo Company Chat — Quick Start (instalacion + arranque)
REM ============================================================
REM  1) Chequea Python
REM  2) Instala dependencias
REM  3) Crea .env si no existe
REM  4) Te recuerda configurar los secrets
REM  5) Arranca el server
REM ============================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"
title Demo Company Chat - Quick Start

echo.
echo ============================================================
echo  Demo Company Chat - Quick Start
echo ============================================================
echo.

REM --- 1. Verificar Python ---
echo [1/5] Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] Python no esta instalado o no esta en el PATH.
    echo.
    echo Descargalo de: https://www.python.org/downloads/
    echo Durante la instalacion, MARCA "Add Python to PATH".
    echo.
    pause
    exit /b 1
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>nul
if errorlevel 1 (
    echo.
    echo [ERROR] Se requiere Python 3.11 o superior.
    echo Descarga la version mas nueva en https://www.python.org/downloads/
    pause
    exit /b 1
)
echo     Python OK.

REM --- 2. Instalar dependencias ---
echo.
echo [2/5] Instalando dependencias (puede tardar 1-2 minutos)...
python -m pip install --upgrade pip --quiet 2>nul
python -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo.
    echo [ERROR] Fallo la instalacion de dependencias.
    pause
    exit /b 1
)
echo     Dependencias OK.

REM --- 3. Crear .env si no existe ---
echo.
echo [3/5] Configurando .env...
if not exist ".env" (
    if not exist ".env.example" (
        echo [ERROR] Falta .env.example
        pause
        exit /b 1
    )
    copy ".env.example" ".env" >nul
    echo     .env creado desde .env.example
    set "FIRST_TIME=1"
) else (
    echo     .env ya existe.
    set "FIRST_TIME=0"
)

REM --- 4. Verificar / setear secrets ---
echo.
echo [4/5] Verificando secrets...
python -c "from dotenv import dotenv_values; v=dotenv_values('.env'); import sys; missing = [k for k in ('JWT_SECRET','GOOGLE_API_KEY','ADMIN_PASSWORD') if not v.get(k) or 'cambiar' in (v.get(k) or '').lower()]; sys.exit(1 if missing else 0); " 2>nul
if errorlevel 1 (
    echo.
    echo ============================================================
    echo  Faltan secrets por configurar. Ejecuta estos comandos:
    echo ============================================================
    echo.
    echo   python set_secret.py JWT_SECRET
    echo   python set_secret.py GOOGLE_API_KEY
    echo   python set_secret.py ADMIN_PASSWORD
    echo.
    echo Generar GOOGLE_API_KEY en: https://aistudio.google.com/apikey
    echo Generar JWT_SECRET aleatorio con:
    echo   python -c "import secrets; print(secrets.token_hex(32))"
    echo.
    echo Despues volve a correr quick_start.bat
    echo ============================================================
    pause
    exit /b 1
)
echo     Secrets OK.

REM --- 5. Arrancar server ---
echo.
echo [5/5] Arrancando el server...
echo.

REM Detectar IP LAN
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /R /C:"IPv4.*192\."') do (
    set "LAN_IP=%%a"
    goto :found
)
:found
set "LAN_IP=%LAN_IP: =%"

echo ============================================================
echo  Server arrancando...
echo ============================================================
echo  Esta PC:        http://localhost:8000
if defined LAN_IP echo  Otras PCs LAN:  http://%LAN_IP%:8000
echo.
echo  Cerrar esta ventana detiene el server.
echo ============================================================
echo.

python -m uvicorn main:app --host 0.0.0.0 --port 8000

echo.
echo Server detenido. Presiona cualquier tecla para cerrar.
pause >nul
