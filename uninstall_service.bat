@echo off
REM Desinstala el servicio Demo CompanyChat
setlocal
cd /d "%~dp0"

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Necesita Administrador.
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

set SERVICE_NAME=Demo CompanyChat

REM Encontrar nssm
set NSSM_EXE=
where nssm >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %%i in ('where nssm') do set NSSM_EXE=%%i
)
if "%NSSM_EXE%"=="" if exist "%~dp0nssm.exe" set NSSM_EXE=%~dp0nssm.exe

if "%NSSM_EXE%"=="" (
    echo [X] NSSM no encontrado. Usá: sc stop Demo CompanyChat ^&^& sc delete Demo CompanyChat
    pause
    exit /b 1
)

"%NSSM_EXE%" stop "%SERVICE_NAME%" >nul 2>&1
"%NSSM_EXE%" remove "%SERVICE_NAME%" confirm
echo [OK] Servicio "%SERVICE_NAME%" desinstalado.
pause
