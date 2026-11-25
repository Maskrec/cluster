@echo off
setlocal enabledelayedexpansion
title Lanzador del Cluster de Video
cls

:: Detectar ejecutable de Python valido
set "PY_CMD="

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" --version >nul 2>&1
    if !errorlevel! equ 0 (
        set "PY_CMD=.venv\Scripts\python.exe"
    )
)

if "%PY_CMD%"=="" (
    where python >nul 2>&1
    if !errorlevel! equ 0 (
        set "PY_CMD=python"
    )
)

if "%PY_CMD%"=="" (
    echo ========================================================
    echo  [AVISO] No se detecto un Python funcional en esta PC.
    echo ========================================================
    echo.
    echo Si acabas de copiar esta carpeta a una nueva computadora:
    echo Ejecuta primero el archivo: 'instalar_en_otra_pc.bat'
    echo.
    pause
    exit /b 1
)

echo ========================================================
echo         CLUSTER DISTRIBUIDO DE VIDEO - MENU
echo ========================================================
echo   Python detectado: %PY_CMD%
echo ========================================================
echo.
echo 1. Iniciar INTERFAZ GRAFICA (GUI) [Recomendado]
echo 2. Iniciar solo el SERVIDOR BROKER
echo 3. Iniciar un NODO WORKER (para ayudar al cluster)
echo 4. Iniciar TODO localmente (Broker + Worker + GUI)
echo 5. Generar video de prueba (sample_test.mp4)
echo.
set /p opt="Selecciona una opcion [1-5]: "

if "%opt%"=="1" (
    start "CLIENTE GUI" "%PY_CMD%" client/gui.py
    exit
)

if "%opt%"=="2" (
    "%PY_CMD%" broker/broker_server.py
    pause
    exit
)

if "%opt%"=="3" (
    set /p wid="Identificador del Worker [ej. worker_laptop2]: "
    set /p bip="IP del Broker de la PC 1 [ej. 192.168.1.50]: "
    if "%bip%"=="" (
        "%PY_CMD%" worker/worker_node.py --id %wid%
    ) else (
        "%PY_CMD%" worker/worker_node.py --id %wid% --host %bip%
    )
    pause
    exit
)

if "%opt%"=="4" (
    echo Iniciando Broker en ventana separada...
    start "BROKER - Orquestador" cmd /k ""%PY_CMD%" broker/broker_server.py"
    timeout /t 2 /nobreak >nul

    echo Iniciando Worker 1...
    start "WORKER 1" cmd /k ""%PY_CMD%" worker/worker_node.py --id worker_1"
    timeout /t 1 /nobreak >nul

    echo Iniciando Interfaz del Cliente...
    start "CLIENTE GUI" cmd /k ""%PY_CMD%" client/gui.py"
    exit
)

if "%opt%"=="5" (
    "%PY_CMD%" generate_sample_video.py
    pause
    exit
)
