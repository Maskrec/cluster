"""
Configuraciones globales del clúster de procesamiento de video.
Centraliza puertos de red, direcciones de host, buffers y rutas de almacenamiento.
Permite la comunicación entre diferentes dispositivos en la misma red local (LAN/Wi-Fi).
"""

import socket
from pathlib import Path


def get_local_ip() -> str:
    """Detecta automáticamente la dirección IP local de este dispositivo en la red."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            # No envía paquetes reales; solo determina la interfaz de salida activa
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


# Rutas del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
RAW_VIDEOS_DIR = STORAGE_DIR / "raw_videos"
PROCESSED_VIDEOS_DIR = STORAGE_DIR / "processed_videos"
TEMP_FRAMES_DIR = STORAGE_DIR / "temp_frames"

# Asegurar que existan los directorios
for directory in (RAW_VIDEOS_DIR, PROCESSED_VIDEOS_DIR, TEMP_FRAMES_DIR):
    directory.mkdir(parents=True, exist_ok=True)

# Dirección IP local detectada de este equipo
LOCAL_IP = get_local_ip()

# Para el Broker: "0.0.0.0" permite escuchar conexiones desde cualquier interfaz (localhost y otros dispositivos LAN)
BROKER_BIND_HOST = "0.0.0.0"

# Host por defecto al que se conectan los clientes y workers (puede sobrescribirse en la GUI o CLI)
DEFAULT_BROKER_HOST = LOCAL_IP

# Puertos separados para evitar colisiones entre el cliente y los nodos
BROKER_CLIENT_PORT = 5000
BROKER_WORKER_PORT = 5001

# Sockets y red
BUFFER_SIZE = 65536  # Buffer de 64 KB para transferencia de chunks
SOCKET_TIMEOUT = 600  # Timeout ampliado a 10 minutos para soportar videos largos sin desconexión

# Calidad de compresión de imagen para transferencia de fotogramas (1 a 100)
# 95 ofrece calidad visual prácticamente sin pérdidas manteniendo alta velocidad
JPEG_QUALITY = 95
