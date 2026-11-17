import sys
import tempfile
from pathlib import Path
from typing import List, Tuple

# Asegurar que la raíz del proyecto esté en sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import cv2
import numpy as np

from config.settings import JPEG_QUALITY, RAW_VIDEOS_DIR, TEMP_FRAMES_DIR


class VideoManager:
    """Administra la conversión bidireccional entre video y fotogramas."""

    @staticmethod
    def extract_frames(video_bytes: bytes, filename_hint: str = "input.mp4") -> Tuple[List[Tuple[int, bytes]], float, Tuple[int, int]]:
        """
        Guarda temporalmente el video recibido en disco y extrae todos sus fotogramas.

        :param video_bytes: Bytes del archivo de video recibido del cliente.
        :param filename_hint: Nombre referencial del archivo.
        :return: Tupla con:
                 - Lista de tuplas: [(frame_id, jpeg_bytes), ...]
                 - fps: Tasa de fotogramas por segundo original del video.
                 - (width, height): Resolución del video.
        """
        temp_input_path = RAW_VIDEOS_DIR / f"temp_recv_{filename_hint}"
        temp_input_path.write_bytes(video_bytes)

        cap = cv2.VideoCapture(str(temp_input_path.resolve()))
        if not cap.isOpened():
            raise ValueError(f"No se pudo abrir el archivo de video '{filename_hint}' con OpenCV.")

        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0 or np.isnan(fps):
            fps = 30.0  # Valor por defecto si el contenedor no reporta FPS confiable

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        frames: List[Tuple[int, bytes]] = []
        frame_id = 0

        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                break

            # Codificar cada frame como JPEG de alta calidad en memoria
            success, encoded_jpg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
            if not success:
                raise RuntimeError(f"Error al codificar el fotograma {frame_id} a JPEG.")

            frames.append((frame_id, encoded_jpg.tobytes()))
            frame_id += 1

        cap.release()

        # Limpiar archivo temporal recibido si se desea conservar espacio
        try:
            if temp_input_path.exists():
                temp_input_path.unlink()
        except OSError:
            pass

        return frames, fps, (width, height)

    @staticmethod
    def build_video_from_frames(
        processed_frames: List[Tuple[int, bytes]],
        output_path: Path,
        fps: float,
        frame_size: Tuple[int, int],
    ) -> bytes:
        """
        Reordena estrictamente los fotogramas procesados por 'frame_id'
        y ensambla el video resultante en disco y en memoria.

        :param processed_frames: Lista de tuplas (frame_id, jpeg_bytes_procesados).
        :param output_path: Ruta destino para guardar el video generado.
        :param fps: Cuadros por segundo para el archivo final.
        :param frame_size: (width, height) de los fotogramas.
        :return: Bytes brutos del archivo de video resultante.
        """
        if not processed_frames:
            raise ValueError("No hay fotogramas para reconstruir el video.")

        # Ordenamiento estricto por frame_id para garantizar la integridad cronológica
        processed_frames.sort(key=lambda item: item[0])

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Detectar el tamaño real de los fotogramas procesados (permite que los workers aumenten la resolución)
        sample_arr = np.frombuffer(processed_frames[0][1], np.uint8)
        sample_img = cv2.imdecode(sample_arr, cv2.IMREAD_COLOR)
        if sample_img is not None:
            actual_frame_size = (sample_img.shape[1], sample_img.shape[0])
        else:
            actual_frame_size = frame_size

        # Usar códec mp4v ampliamente compatible con la resolución final (original o aumentada)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(output_path.resolve()), fourcc, fps, actual_frame_size)

        if not writer.isOpened():
            raise RuntimeError(f"No se pudo inicializar VideoWriter para la ruta '{output_path}'.")

        for frame_id, frame_bytes in processed_frames:
            # Decodificar el frame recibido desde bytes
            np_arr = np.frombuffer(frame_bytes, np.uint8)
            img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            if img is None:
                continue

            # Asegurar coincidencia con el tamaño de salida
            if (img.shape[1], img.shape[0]) != actual_frame_size:
                img = cv2.resize(img, actual_frame_size)

            writer.write(img)

        writer.release()

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError(f"El archivo de video generado en '{output_path}' está vacío o es inválido.")

        return output_path.read_bytes()
