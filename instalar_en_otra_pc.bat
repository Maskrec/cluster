@echo off
title Configurador para Nueva Computadora
cls
echo ========================================================
echo   CONFIGURANDO EL CLUSTER EN ESTA NUEVA COMPUTADORA
echo ========================================================
echo.

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python no esta instalado o no esta agregado al PATH de Windows.
    echo.
    echo Solucion:
    echo 1. Descarga Python desde https://www.python.org
    echo 2. AL INSTALAR MARCA LA CASILLA: "Add python.exe to PATH"
    echo.
    pause
    exit /b 1
)

echo [Paso 1/3] Limpiando entorno virtual copiado anterior (si existe)...
if exist ".venv" (
    rmdir /s /q .venv
)

echo [Paso 2/3] Creando entorno virtual nuevo para esta computadora...
python -m venv .venv
if %errorlevel% neq 0 (
    echo [ERROR] No se pudo crear el entorno virtual.
    pause
    exit /b 1
)

echo [Paso 3/3] Instalando librerias del proyecto (PyQt6, OpenCV, Numpy, Pillow)...
.\.venv\Scripts\pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Ocurrio un problema instalando las librerias.
    pause
    exit /b 1
)

echo.
echo ========================================================
echo   TODO LISTO! Esta computadora ya quedo configurada.
echo   Ya puedes hacer doble clic en 'start_cluster.bat'
echo ========================================================
echo.
pause
