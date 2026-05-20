@echo off
REM ─────────────────────────────────────────────────────────────
REM Instalador del servicio Demo Company Chat usando NSSM
REM
REM Requisitos:
REM   1. Tener NSSM (https://nssm.cc/download) en alguna ubicación
REM      accesible. Si nssm.exe no está en PATH ni en .\nssm.exe,
REM      el script lo intenta descargar a .\nssm\nssm.exe.
REM   2. Correr este .bat como Administrador (necesario para
REM      instalar/modificar servicios de Windows).
REM
REM Lo que hace:
REM   • Instala el servicio "Demo CompanyChat"
REM   • Configura auto-start al boot
REM   • Auto-reinicia si crashea (delay 3s, máx 3 intentos / 60s)
REM   • Loguea stdout/stderr a .\logs\service_*.log
REM ─────────────────────────────────────────────────────────────

setlocal enabledelayedexpansion
cd /d "%~dp0"

REM Pedir elevación si no somos admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Este script necesita permisos de Administrador.
    echo     Reintentando como admin...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

set SERVICE_NAME=Demo CompanyChat
set APP_DIR=%~dp0
if "%APP_DIR:~-1%"=="\" set APP_DIR=%APP_DIR:~0,-1%

REM ── Encontrar Python ─────────────────────────────────────────
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [X] Python no está en PATH. Instalá Python 3.11+ con "Add to PATH".
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('where python') do (
    set PYTHON_EXE=%%i
    goto :found_python
)
:found_python
echo [OK] Python: %PYTHON_EXE%

REM ── Encontrar NSSM ───────────────────────────────────────────
set NSSM_EXE=
where nssm >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %%i in ('where nssm') do (
        set NSSM_EXE=%%i
        goto :found_nssm
    )
)
if exist "%APP_DIR%\nssm.exe" set NSSM_EXE=%APP_DIR%\nssm.exe
if exist "%APP_DIR%\nssm\nssm.exe" set NSSM_EXE=%APP_DIR%\nssm\nssm.exe

if "%NSSM_EXE%"=="" (
    echo [!] NSSM no encontrado. Descargando...
    powershell -Command "& {Invoke-WebRequest -Uri 'https://nssm.cc/release/nssm-2.24.zip' -OutFile '%APP_DIR%\nssm.zip'; Expand-Archive -Force '%APP_DIR%\nssm.zip' '%APP_DIR%\nssm_tmp'; Copy-Item '%APP_DIR%\nssm_tmp\nssm-2.24\win64\nssm.exe' '%APP_DIR%\nssm.exe'; Remove-Item -Recurse -Force '%APP_DIR%\nssm_tmp','%APP_DIR%\nssm.zip'}"
    if not exist "%APP_DIR%\nssm.exe" (
        echo [X] No se pudo descargar NSSM. Bajalo manualmente de https://nssm.cc/download y dejá nssm.exe junto a este .bat
        pause
        exit /b 1
    )
    set NSSM_EXE=%APP_DIR%\nssm.exe
)
:found_nssm
echo [OK] NSSM: %NSSM_EXE%

REM ── Crear carpeta de logs ────────────────────────────────────
if not exist "%APP_DIR%\logs" mkdir "%APP_DIR%\logs"

REM ── Si el servicio ya existe, removerlo primero ──────────────
sc query "%SERVICE_NAME%" >nul 2>&1
if %errorlevel% equ 0 (
    echo [i] El servicio "%SERVICE_NAME%" ya existe. Lo reinstalo...
    "%NSSM_EXE%" stop "%SERVICE_NAME%" >nul 2>&1
    "%NSSM_EXE%" remove "%SERVICE_NAME%" confirm >nul 2>&1
)

REM ── Instalar el servicio ─────────────────────────────────────
echo [i] Instalando servicio "%SERVICE_NAME%"...
"%NSSM_EXE%" install "%SERVICE_NAME%" "%PYTHON_EXE%" "-m" "uvicorn" "main:app" "--host" "0.0.0.0" "--port" "8000"
"%NSSM_EXE%" set "%SERVICE_NAME%" AppDirectory "%APP_DIR%"
"%NSSM_EXE%" set "%SERVICE_NAME%" DisplayName "Demo Company Chat — Agente Consultor"
"%NSSM_EXE%" set "%SERVICE_NAME%" Description "Chatbot interno de Demo Company S.A. para consultas de catálogo (FastAPI + Uvicorn)."
"%NSSM_EXE%" set "%SERVICE_NAME%" Start SERVICE_AUTO_START

REM ── Auto-restart on crash ────────────────────────────────────
"%NSSM_EXE%" set "%SERVICE_NAME%" AppExit Default Restart
"%NSSM_EXE%" set "%SERVICE_NAME%" AppRestartDelay 3000
"%NSSM_EXE%" set "%SERVICE_NAME%" AppThrottle 60000

REM ── Logs ─────────────────────────────────────────────────────
"%NSSM_EXE%" set "%SERVICE_NAME%" AppStdout "%APP_DIR%\logs\service_stdout.log"
"%NSSM_EXE%" set "%SERVICE_NAME%" AppStderr "%APP_DIR%\logs\service_stderr.log"
"%NSSM_EXE%" set "%SERVICE_NAME%" AppRotateFiles 1
"%NSSM_EXE%" set "%SERVICE_NAME%" AppRotateOnline 1
"%NSSM_EXE%" set "%SERVICE_NAME%" AppRotateBytes 10485760

REM ── Arrancar ────────────────────────────────────────────────
echo [i] Arrancando servicio...
"%NSSM_EXE%" start "%SERVICE_NAME%"
if %errorlevel% neq 0 (
    echo [X] Falló el arranque del servicio. Revisá logs\service_stderr.log
    pause
    exit /b 1
)

echo.
echo ─────────────────────────────────────────────────────────────
echo  [OK] Servicio "%SERVICE_NAME%" instalado y corriendo.
echo.
echo  Probá: http://localhost:8000/api/health
echo.
echo  Comandos útiles:
echo    nssm start    %SERVICE_NAME%
echo    nssm stop     %SERVICE_NAME%
echo    nssm restart  %SERVICE_NAME%
echo    nssm status   %SERVICE_NAME%
echo    nssm remove   %SERVICE_NAME% confirm    (desinstalar)
echo.
echo  Logs del servicio en: %APP_DIR%\logs\
echo  Logs de la app    en: %APP_DIR%\logs\app.log
echo ─────────────────────────────────────────────────────────────
pause
