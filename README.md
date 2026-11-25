# Clúster de Procesamiento de Video (Sistemas Distribuidos)

Sistema distribuido cliente-servidor para procesamiento y transformación de video en paralelo mediante balanceo de carga (Round Robin).

---

## Características Principales

- **Control Total desde la Interfaz Gráfica:** Puedes iniciar y detener el Broker y los Workers con un solo clic desde la propia ventana de la aplicación, sin necesidad de abrir terminales adicionales.
- **Biblioteca Compartida Distribuida:** Repositorio centralizado de videos donde cualquier computadora/laptop conectada puede:
  - Ver el catálogo de videos en red.
  - Subir y compartir videos a la biblioteca del clúster.
  - Descargar cualquier video a su disco local a través del sistema por Sockets TCP.
  - Previsualizar y reproducir videos compartidos o procesados.
- **Conexión Multidispositivo (LAN/Wi-Fi):** Puedes conectar múltiples computadoras, laptops o nodos en la misma red local para acelerar el procesamiento de fotogramas en paralelo.
- **Sin límite de tiempo:** Soporta videos de cualquier duración y tamaño.
- **Grabador de Cámara Web Integrado:** Opción para capturar video en vivo desde la cámara web directamente en la interfaz gráfica del cliente.
- **Super-Resolución y Mejora de Calidad:**
  - `upscale_hd`: Aumento de resolución a 2X (Lanczos4) + Realce de detalles + Enfoque + Contraste dinámico.
  - `detail_enhance`: Realce profundo de texturas y nitidez a resolución nativa.
  - `contrast`: Ecualización adaptativa de contraste y luz (CLAHE).
  - `denoise`: Reducción de ruido bilateral preservando contornos.
  - Filtros clásicos: Grayscale, Canny, Blur, Sepia, Invert.

---

## Estructura del Proyecto

```text
cluster/
│
├── agent.md                    # Especificación y requerimientos del sistema
├── requirements.txt            # Dependencias del proyecto
├── start_cluster.bat           # Menú interactivo para iniciar todo o partes del clúster
├── generate_sample_video.py    # Generador de videos sintéticos de prueba con contador de frames
├── .gitignore                  # Reglas de exclusión de git
├── README.md                   # Documentación general y arquitectura
│
├── config/                     # Configuración centralizada
│   ├── __init__.py
│   └── settings.py             # Detección de IP local, puertos, buffers y calidad
│
├── common/                     # Protocolo de red y serialización
│   ├── __init__.py
│   ├── protocol.py             # Empaquetado y desempaquetado de sockets TCP (Header + JSON + Payload)
│   └── utils.py                # Helpers auxiliares
│
├── broker/                     # Servidor BROKER (Orquestador Central y Balanceador)
│   ├── __init__.py
│   ├── broker_server.py        # Escucha dual (puerto 5001 para workers, 5000 para clientes)
│   ├── load_balancer.py        # Registro dinámico y balanceo Round Robin multihilo
│   └── video_manager.py        # Extracción y ensamblado ordenado por 'frame_id'
│
├── worker/                     # Nodos de Procesamiento (Workers)
│   ├── __init__.py
│   ├── worker_node.py          # Proceso worker independiente (--id, --host, --port)
│   └── image_filters.py        # Biblioteca de filtros y transformaciones con OpenCV
│
├── client/                     # Cliente (Frontend / Interfaz de Usuario)
│   ├── __init__.py
│   ├── client_app.py           # Conexión TCP con el Broker en segundo plano
│   └── gui.py                  # Interfaz gráfica PyQt6 (Grabadora de cámara y reproductores)
│
└── storage/                    # Almacenamiento local de archivos
    ├── raw_videos/             # Videos originales y grabaciones de cámara
    ├── processed_videos/       # Videos finales reconstruidos por el clúster
    └── temp_frames/            # Frames temporales durante la ejecución
```

---

## Cómo Ejecutar el Sistema

### Opción Rápida (Windows):
Ejecuta el archivo:
```powershell
.\start_cluster.bat
```
Y selecciona la opción **1** para abrir automáticamente el Broker, 2 Workers y la Interfaz Gráfica en ventanas separadas.

---

### Opción Manual / Multidispositivo:

#### 1. En la máquina principal (Servidor BROKER):
```powershell
.\.venv\Scripts\python.exe broker/broker_server.py
```
> Al iniciar, la consola mostrará la **IP Local** de la máquina (por ejemplo `192.168.1.50`).

#### 2. En las máquinas que actuarán como WORKERS:
- **En la misma PC:**
  ```powershell
  .\.venv\Scripts\python.exe worker/worker_node.py --id worker_1
  .\.venv\Scripts\python.exe worker/worker_node.py --id worker_2
  ```
- **En otra laptop/PC de la misma red Wi-Fi:**
  ```powershell
  python worker/worker_node.py --id laptop_worker --host 192.168.1.50
  ```

#### 3. En la máquina que usará el CLIENTE (GUI):
- Abre la interfaz:
  ```powershell
  .\.venv\Scripts\python.exe client/gui.py
  ```
- En la barra superior, escribe la **IP del Broker** (ej. `192.168.1.50` si está en otra máquina, o déjalo tal cual si corre en la misma).
- Carga un archivo de video o presiona **"🎥 Grabar desde Cámara"**.
- Elige el filtro o mejora deseada y presiona **"🚀 Enviar al Clúster"**.
