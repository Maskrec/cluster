import socket
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Asegurar que la raíz del proyecto esté en sys.path para ejecuciones directas
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common.protocol import (
    MSG_BROKER_PROCESSED_VIDEO,
    MSG_CLIENT_UPLOAD_VIDEO,
    MSG_ERROR,
    MSG_LIBRARY_DOWNLOAD_REQ,
    MSG_LIBRARY_DOWNLOAD_RESP,
    MSG_LIBRARY_LIST_REQ,
    MSG_LIBRARY_LIST_RESP,
    MSG_LIBRARY_UPLOAD_REQ,
    MSG_LIBRARY_UPLOAD_RESP,
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
        filter_name: str = "upscale_hd",
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

            metadata = {
                "type": MSG_CLIENT_UPLOAD_VIDEO,
                "filename": video_path.name,
                "filter": filter_name,
            }

            notify("Transmitiendo video al Broker...")
            send_message(sock, metadata, payload=video_bytes)
            notify("Video enviado. Esperando a que el clúster procese los fotogramas...")

            response_meta, response_payload = receive_message(sock)
            msg_type = response_meta.get("type")
            if msg_type == MSG_ERROR:
                error_detail = response_meta.get("error", "Error desconocido en el servidor.")
                raise RuntimeError(f"Error devuelto por el Broker: {error_detail}")

            if msg_type != MSG_BROKER_PROCESSED_VIDEO:
                raise ValueError(f"Respuesta inesperada del Broker: {msg_type}")

            notify("¡Video procesado recibido del Broker! Guardando archivo...")
            timestamp = int(time.time())
            output_filename = f"processed_{timestamp}_{video_path.name}"
            output_path = PROCESSED_VIDEOS_DIR / output_filename
            output_path.write_bytes(response_payload)

            notify(f"Video guardado exitosamente en: {output_path.name}")
            return output_path

    def list_shared_library(self, status_callback: Optional[Callable[[str], None]] = None) -> List[Dict[str, Any]]:
        """Consulta al Broker el catálogo de archivos en la biblioteca compartida."""
        def notify(msg: str):
            if status_callback:
                status_callback(msg)

        notify(f"Consultando catálogo de biblioteca en {self.host}:{self.port}...")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(30)
            sock.connect((self.host, self.port))
            send_message(sock, {"type": MSG_LIBRARY_LIST_REQ})

            meta, _ = receive_message(sock)
            if meta.get("type") == MSG_ERROR:
                raise RuntimeError(meta.get("error", "Error consultando catálogo"))

            files = meta.get("files", [])
            notify(f"Catálogo obtenido: {len(files)} archivo(s) disponibles.")
            return files

    def upload_to_library(self, video_path: Path, status_callback: Optional[Callable[[str], None]] = None) -> str:
        """Sube un archivo directamente a la biblioteca compartida del clúster."""
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"El archivo '{video_path}' no existe.")

        def notify(msg: str):
            if status_callback:
                status_callback(msg)

        video_bytes = video_path.read_bytes()
        notify(f"Subiendo '{video_path.name}' ({len(video_bytes)/1024/1024:.2f} MB) a la biblioteca compartida...")

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(SOCKET_TIMEOUT)
            sock.connect((self.host, self.port))

            send_message(
                sock,
                {"type": MSG_LIBRARY_UPLOAD_REQ, "filename": video_path.name},
                payload=video_bytes,
            )

            meta, _ = receive_message(sock)
            if meta.get("type") == MSG_ERROR:
                raise RuntimeError(meta.get("error", "Error subiendo archivo"))

            notify(f"'{video_path.name}' subido con éxito a la biblioteca compartida.")
            return meta.get("filename", video_path.name)

    def download_from_library(
        self,
        filename: str,
        dest_folder: Path,
        status_callback: Optional[Callable[[str], None]] = None,
    ) -> Path:
        """Descarga un archivo desde la biblioteca compartida del Broker a una carpeta local."""
        def notify(msg: str):
            if status_callback:
                status_callback(msg)

        notify(f"Solicitando descarga de '{filename}' desde {self.host}:{self.port}...")
        dest_folder = Path(dest_folder)
        dest_folder.mkdir(parents=True, exist_ok=True)
        target_path = dest_folder / filename

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(SOCKET_TIMEOUT)
            sock.connect((self.host, self.port))

            send_message(sock, {"type": MSG_LIBRARY_DOWNLOAD_REQ, "filename": filename})

            meta, payload = receive_message(sock)
            if meta.get("type") == MSG_ERROR:
                raise RuntimeError(meta.get("error", "Error descargando archivo"))

            notify(f"Recibiendo bytes ({len(payload)/1024/1024:.2f} MB)...")
            target_path.write_bytes(payload)
            notify(f"Descarga completada en: {target_path.resolve()}")
            return target_path
