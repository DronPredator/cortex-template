@echo off
REM Inicia el server de Demo Company Chat en localhost:8000
REM Doble-click para correr. Cerrá la ventana para detenerlo.

cd /d "%~dp0"

title Demo Company Chat - Server

echo ============================================
echo  Demo Company Chat Server
echo ============================================
echo.

REM Detectar IP LAN para mostrarla
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /R /C:"IPv4.*192\."') do (
    set "LAN_IP=%%a"
    goto :found
)
:found
set "LAN_IP=%LAN_IP: =%"

echo Acceso:
echo   Esta PC:        http://localhost:8000
echo   Otras PCs LAN:  http://%LAN_IP%:8000
echo.
echo Cerra esta ventana para detener el server.
echo.

python -m uvicorn main:app --host 0.0.0.0 --port 8000

REM Si llegamos aquí es porque el server se cayó. Mantener ventana abierta.
echo.
echo Server detenido. Presiona cualquier tecla para cerrar.
pause >nul
