@echo off
title Lanzador del Cluster de Video
cls
echo ========================================================
echo         CLUSTER DISTRIBUIDO DE VIDEO - MENU
echo ========================================================
echo.
echo 1. Iniciar TODO localmente (Broker + 2 Workers + Cliente GUI)
echo 2. Iniciar solo el SERVIDOR BROKER
echo 3. Iniciar un NODO WORKER (en esta u otra maquina)
echo 4. Iniciar la INTERFAZ DEL CLIENTE (GUI)
echo 5. Generar video de prueba (sample_test.mp4)
echo.
set /p opt="Selecciona una opcion [1-5]: "

if "%opt%"=="1" (
    echo Iniciando Broker en ventana separada...
    start "BROKER - Orquestador" cmd /k ".venv\Scripts\python.exe broker/broker_server.py"
    timeout /t 2 /nobreak >nul

    echo Iniciando Worker 1...
    start "WORKER 1" cmd /k ".venv\Scripts\python.exe worker/worker_node.py --id worker_1"
    timeout /t 1 /nobreak >nul

    echo Iniciando Worker 2...
    start "WORKER 2" cmd /k ".venv\Scripts\python.exe worker/worker_node.py --id worker_2"
    timeout /t 1 /nobreak >nul

    echo Iniciando Interfaz del Cliente...
    start "CLIENTE GUI" cmd /k ".venv\Scripts\python.exe client/gui.py"
    exit
)

if "%opt%"=="2" (
    .venv\Scripts\python.exe broker/broker_server.py
    pause
    exit
)

if "%opt%"=="3" (
    set /p wid="Identificador del Worker [ej. worker_laptop]: "
    set /p bip="IP del Broker [presiona Enter para IP local]: "
    if "%bip%"=="" (
        .venv\Scripts\python.exe worker/worker_node.py --id %wid%
    ) else (
        .venv\Scripts\python.exe worker/worker_node.py --id %wid% --host %bip%
    )
    pause
    exit
)

if "%opt%"=="4" (
    .venv\Scripts\python.exe client/gui.py
    exit
)

if "%opt%"=="5" (
    .venv\Scripts\python.exe generate_sample_video.py
    pause
    exit
)
