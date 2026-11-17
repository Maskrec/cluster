import socket
import sys
import time
from pathlib import Path

# Asegurar que la raíz del proyecto esté en sys.path para ejecuciones directas
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from typing import Callable, Optional

from common.protocol import (
    MSG_BROKER_PROCESSED_VIDEO,
    MSG_CLIENT_UPLOAD_VIDEO,
    MSG_ERROR,
    receive_message,
    send_message,
)
from config.settings import (
    BROKER_CLIENT_PORT,
    DEFAULT_BROKER_HOST,
    PROCESSED_VIDEOS_DIR,
    SOCKET_TIMEOUT,
)


class VideoClient:

    def __init__(self, host: str = DEFAULT_BROKER_HOST, port: int = BROKER_CLIENT_PORT):
        self.host = host
        self.port = port

    def send_video_for_processing(
        self,
        video_path: Path,
        filter_name: str = "grayscale",
        status_callback: Optional[Callable[[str], None]] = None,
    ) -> Path:
      
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"El video '{video_path}' no existe.")

        def notify(msg: str):
            if status_callback:
                status_callback(msg)

        notify(f"Leyendo archivo de video: {video_path.name}...")
        video_bytes = video_path.read_bytes()
        file_size_mb = len(video_bytes) / (1024 * 1024)
        notify(f"Tamaño del video: {file_size_mb:.2f} MB")

        notify(f"Conectando al Broker en {self.host}:{self.port}...")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(SOCKET_TIMEOUT)
            sock.connect((self.host, self.port))
            notify("Conectado con éxito al Broker.")

            # Preparar metadatos del mensaje
            metadata = {
                "type": MSG_CLIENT_UPLOAD_VIDEO,
                "filename": video_path.name,
                "filter": filter_name,
            }

            # Enviar mensaje con el video binario como payload
            notify("Transmitiendo video al Broker...")
            send_message(sock, metadata, payload=video_bytes)
            notify("Video enviado. Esperando a que el clúster procese los fotogramas...")

            # Queda a la espera de la respuesta del Broker
            response_meta, response_payload = receive_message(sock)

            msg_type = response_meta.get("type")
            if msg_type == MSG_ERROR:
                error_detail = response_meta.get("error", "Error desconocido en el servidor.")
                raise RuntimeError(f"Error devuelto por el Broker: {error_detail}")

            if msg_type != MSG_BROKER_PROCESSED_VIDEO:
                raise ValueError(f"Respuesta inesperada del Broker: {msg_type}")

            notify("¡Video procesado recibido del Broker! Guardando archivo...")

            # Guardar el video procesado resultante en disco
            timestamp = int(time.time())
            output_filename = f"processed_{timestamp}_{video_path.name}"
            output_path = PROCESSED_VIDEOS_DIR / output_filename
            output_path.write_bytes(response_payload)

            notify(f"Video guardado exitosamente en: {output_path.name}")
            return output_path
