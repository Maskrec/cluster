"""
Módulo de Procesamiento, Filtros y Super-Resolución de Imagen para los Workers.
Aplica algoritmos de mejora de calidad, aumento de resolución y filtros de visión por computadora
sobre fotogramas individuales utilizando OpenCV.
"""

import sys
from pathlib import Path

# Asegurar que la raíz del proyecto esté en sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import cv2
import numpy as np

from config.settings import JPEG_QUALITY


class ImageFilters:
    """Conjunto de filtros de imagen y algoritmos de super-resolución aplicables a fotogramas."""

    @staticmethod
    def apply_filter(frame_bytes: bytes, filter_name: str) -> bytes:
        """
        Decodifica los bytes de un fotograma, aplica la mejora o filtro especificado
        y retorna el fotograma procesado en alta calidad.

        :param frame_bytes: Bytes del fotograma en formato JPEG/PNG.
        :param filter_name:
               - 'upscale_hd': Aumento de resolución a 2X (Lanczos4) + Realce de detalles + Enfoque + Contraste dinámico.
               - 'detail_enhance': Realce profundo de texturas, nitidez y claridad a resolución nativa.
               - 'contrast': Ecualización adaptativa de contraste y luz (CLAHE en espacio LAB).
               - 'denoise': Reducción de ruido y artefactos con suavizado bilateral que preserva bordes.
               - 'sharpen': Máscara de enfoque y realce de contornos.
               - 'grayscale': Escala de grises.
               - 'edge_detection': Detección de contornos Canny.
               - 'blur': Desenfoque gaussiano.
               - 'sepia': Tonalidad vintage/sepia.
               - 'invert': Negativo fotográfico.
        :return: Bytes del fotograma procesado en JPEG de alta calidad.
        """
        np_arr = np.frombuffer(frame_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if img is None:
            raise ValueError("No se pudo decodificar el fotograma a una matriz de imagen válida.")

        filter_name = (filter_name or "upscale_hd").lower()

        # =====================================================================
        # 1. MEJORAS DE CALIDAD Y SUPER-RESOLUCIÓN
        # =====================================================================
        if filter_name in ("upscale_hd", "super_res", "super_resolution"):
            # A. Eliminación de ruido y artefactos de compresión preservando bordes
            h, w = img.shape[:2]
            clean = cv2.edgePreservingFilter(img, flags=1, sigma_s=40, sigma_r=0.3)

            # B. Aumento de resolución al doble (2X) con interpolación Lanczos en ventana 8x8
            upscaled = cv2.resize(clean, (w * 2, h * 2), interpolation=cv2.INTER_LANCZOS4)

            # C. Realce profundo de micro-texturas y detalles
            enhanced = cv2.detailEnhance(upscaled, sigma_s=10, sigma_r=0.15)

            # D. Máscara de enfoque (Unsharp Masking) para contornos de alta definición
            blurred = cv2.GaussianBlur(enhanced, (0, 0), 2.5)
            crisp = cv2.addWeighted(enhanced, 1.4, blurred, -0.4, 0)

            # E. Realce de rango dinámico y viveza de color en el espacio LAB
            lab = cv2.cvtColor(crisp, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            cl = clahe.apply(l)
            merged = cv2.merge((cl, a, b))
            processed = cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)

        elif filter_name in ("detail_enhance", "clarity"):
            # Realce de texturas y nitidez profunda a resolución nativa
            clean = cv2.edgePreservingFilter(img, flags=1, sigma_s=30, sigma_r=0.25)
            enhanced = cv2.detailEnhance(clean, sigma_s=12, sigma_r=0.15)
            blurred = cv2.GaussianBlur(enhanced, (0, 0), 2.0)
            processed = cv2.addWeighted(enhanced, 1.35, blurred, -0.35, 0)

        elif filter_name in ("sharpen", "enhance"):
            # Máscara de enfoque clásica para contornos
            kernel = np.array([
                [0, -1, 0],
                [-1, 5, -1],
                [0, -1, 0]
            ], dtype=np.float32)
            processed = cv2.filter2D(img, -1, kernel)

        elif filter_name == "contrast":
            # Mejora de contraste adaptativo CLAHE en luminancia LAB
            lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            cl = clahe.apply(l)
            merged = cv2.merge((cl, a, b))
            processed = cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)

        elif filter_name == "denoise":
            # Reducción de ruido bilateral preservando bordes
            processed = cv2.bilateralFilter(img, d=9, sigmaColor=75, sigmaSpace=75)

        # =====================================================================
        # 2. FILTROS ARTÍSTICOS Y DE VISIÓN COMPUTACIONAL
        # =====================================================================
        elif filter_name == "grayscale":
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            processed = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

        elif filter_name == "invert":
            processed = cv2.bitwise_not(img)

        elif filter_name == "edge_detection":
            edges = cv2.Canny(img, threshold1=100, threshold2=200)
            processed = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)

        elif filter_name == "blur":
            processed = cv2.GaussianBlur(img, (15, 15), 0)

        elif filter_name == "sepia":
            kernel = np.array([
                [0.272, 0.534, 0.131],
                [0.349, 0.686, 0.168],
                [0.393, 0.769, 0.189],
            ])
            transformed = cv2.transform(img, kernel)
            processed = np.clip(transformed, 0, 255).astype(np.uint8)

        else:
            processed = img

        success, encoded_jpg = cv2.imencode(".jpg", processed, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        if not success:
            raise RuntimeError("Error al codificar el fotograma procesado a JPEG.")

        return encoded_jpg.tobytes()
