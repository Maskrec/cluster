"""
Configuraciones globales del clúster de procesamiento de video.
Centraliza puertos de red, direcciones de host, buffers y rutas de almacenamiento.
"""

from pathlib import Path

# Rutas del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
RAW_VIDEOS_DIR = STORAGE_DIR / "raw_videos"
PROCESSED_VIDEOS_DIR = STORAGE_DIR / "processed_videos"
TEMP_FRAMES_DIR = STORAGE_DIR / "temp_frames"

# Asegurar que existan los directorios
for directory in (RAW_VIDEOS_DIR, PROCESSED_VIDEOS_DIR, TEMP_FRAMES_DIR):
    directory.mkdir(parents=True, exist_ok=True)

# Configuraciones de red del BROKER
BROKER_HOST = "127.0.0.1"

# Puertos separados para evitar colisiones:
# - Uno dedicado a recibir solicitudes del Cliente (carga y descarga de video)
# - Uno dedicado a la comunicación interna con los Nodos Workers (registro y frames)
BROKER_CLIENT_PORT = 5000
BROKER_WORKER_PORT = 5001

# Configuración de Sockets
BUFFER_SIZE = 65536  # Buffer de 64 KB para transferencia eficiente de chunks
SOCKET_TIMEOUT = 120  # Tiempo máximo de espera en segundos para operaciones de red

# Parámetros de video
MAX_RECOMMENDED_VIDEO_SECONDS = 15
