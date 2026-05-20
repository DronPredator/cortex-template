@echo off
REM ============================================================
REM  Demo Company Chat — Instalador para PC nueva
REM ============================================================
REM  Que hace:
REM    1. Chequea que Python este instalado (>= 3.11)
REM    2. Instala las dependencias (pip install)
REM    3. Crea .env si no existe (a partir de .env.example)
REM    4. Te guia para setear la API key y otros secretos
REM ============================================================

setlocal enabledelayedexpansion

cd /d "%~dp0"

echo.
echo ============================================================
echo  Demo Company Chat - Instalador
echo ============================================================
echo.

REM --- 1. Verificar Python ---
echo [1/4] Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] Python no esta instalado o no esta en el PATH.
    echo.
    echo Descargalo de: https://www.python.org/downloads/
    echo Durante la instalacion, MARCA la casilla "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo     Python %PY_VER% detectado.

REM Validar version >= 3.11
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>nul
if errorlevel 1 (
    echo.
    echo [ERROR] Se requiere Python 3.11 o superior. Tenes %PY_VER%.
    echo Descarga la version mas nueva en https://www.python.org/downloads/
    pause
    exit /b 1
)

REM --- 2. Instalar dependencias ---
echo.
echo [2/4] Instalando dependencias (esto puede tardar 1-2 minutos)...
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] Fallo la instalacion de dependencias.
    echo Revisa tu conexion a internet y volve a correr este instalador.
    pause
    exit /b 1
)
echo     Dependencias instaladas OK.

REM --- 3. Configurar .env ---
echo.
echo [3/4] Configurando archivo .env...
if exist ".env" (
    echo     .env ya existe. Lo dejo como esta.
) else (
    if not exist ".env.example" (
        echo [ERROR] Falta .env.example en la carpeta. Algo se rompio.
        pause
        exit /b 1
    )
    copy ".env.example" ".env" >nul
    echo     .env creado a partir de .env.example.
)

REM --- 4. Mostrar pasos finales ---
echo.
echo [4/4] Configurando secretos...
echo.
echo ============================================================
echo  AHORA tenes que configurar 3 cosas:
echo ============================================================
echo.
echo  1) JWT_SECRET (cambialo por uno aleatorio):
echo       python set_secret.py JWT_SECRET
echo.
echo  2) GOOGLE_API_KEY (generar en https://aistudio.google.com/apikey):
echo       python set_secret.py GOOGLE_API_KEY
echo.
echo  3) ADMIN_PASSWORD (la contrasena para el panel admin):
echo       python set_secret.py ADMIN_PASSWORD
echo.
echo ============================================================
echo  Cuando termines, arranca el server con:
echo       start_server.bat
echo  y abri http://localhost:8000 en tu navegador.
echo ============================================================
echo.
pause
