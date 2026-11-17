"""
Script auxiliar para generar un video de prueba sintético con contador de frames.
Útil para verificar que el ordenamiento de 'frame_id' y los filtros funcionen perfectamente.
"""

import sys
from pathlib import Path

# Asegurar que la raíz del proyecto esté en sys.path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import cv2
import numpy as np

from config.settings import RAW_VIDEOS_DIR


def generate_sample_video(filename: str = "sample_test.mp4", duration_seconds: int = 5, fps: int = 30):
    output_path = RAW_VIDEOS_DIR / filename
    width, height = 640, 480
    total_frames = duration_seconds * fps

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_path.resolve()), fourcc, float(fps), (width, height))

    print(f"Generando video de prueba '{filename}' ({duration_seconds}s, {total_frames} frames)...")

    for frame_id in range(total_frames):
        # Fondo con gradiente dinámico
        img = np.zeros((height, width, 3), dtype=np.uint8)
        color_val = int((frame_id / total_frames) * 255)
        img[:] = (color_val // 2, 40, 120)

        # Círculo en movimiento
        cx = int((width // 2) + 150 * np.sin(2 * np.pi * frame_id / fps))
        cy = int((height // 2) + 80 * np.cos(2 * np.pi * frame_id / fps))
        cv2.circle(img, (cx, cy), 35, (0, 255, 255), -1)

        # Contador de Frame ID impreso en pantalla
        text = f"FRAME #{frame_id:04d}"
        cv2.putText(img, text, (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (255, 255, 255), 3, cv2.LINE_AA)

        # Marca de tiempo
        time_text = f"Tiempo: {frame_id / fps:.2f} s"
        cv2.putText(img, time_text, (50, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (200, 255, 200), 2, cv2.LINE_AA)

        writer.write(img)

    writer.release()
    print(f"Video generado con éxito en: {output_path.resolve()}")
    return output_path


if __name__ == "__main__":
    generate_sample_video()
