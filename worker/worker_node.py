"""
Nodo de Procesamiento (Worker).
Responsable del cómputo intensivo e independiente:
1. Al iniciar, se conecta al BROKER y envía un mensaje de alta con su 'worker_id'.
2. Queda en un bucle a la escucha de tareas de fotogramas ('WORKER_FRAME_TASK').
3. Aplica la transformación requerida (usando ImageFilters / OpenCV).
4. Retorna el fotograma procesado al BROKER conservando estrictamente el 'frame_id'.
"""

import argparse
import os
import socket
import sys
import time
from pathlib import Path

# Asegurar que la raíz del proyecto esté en sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common.protocol import (
    MSG_ERROR,
    MSG_WORKER_FRAME_RESULT,
    MSG_WORKER_FRAME_TASK,
    MSG_WORKER_REGISTER,
    MSG_WORKER_REGISTER_ACK,
    receive_message,
    send_message,
)
from config.settings import BROKER_WORKER_PORT, DEFAULT_BROKER_HOST
from worker.image_filters import ImageFilters


class WorkerNode:
    """Representa una instancia de nodo de cómputo en el clúster."""

    def __init__(self, worker_id: str, host: str = DEFAULT_BROKER_HOST, port: int = BROKER_WORKER_PORT):
        self.worker_id = worker_id
        self.host = host
        self.port = port
        self.is_running = False

    def start(self):
        """Inicia el ciclo de vida del Worker: conexión, registro y bucle de trabajo."""
        self.is_running = True
        print(f"[{self.worker_id}] Iniciando nodo de procesamiento...")

        while self.is_running:
            try:
                print(f"[{self.worker_id}] Conectando al BROKER en {self.host}:{self.port}...")
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.connect((self.host, self.port))
                    print(f"[{self.worker_id}] Conexión establecida. Enviando mensaje de alta...")

                    # 1. Mensaje de alta / registro
                    send_message(
                        sock,
                        {
                            "type": MSG_WORKER_REGISTER,
                            "worker_id": self.worker_id,
                        },
                    )

                    # 2. Esperar confirmación del Broker
                    ack_meta, _ = receive_message(sock)
                    if ack_meta.get("type") != MSG_WORKER_REGISTER_ACK:
                        raise RuntimeError(f"El Broker rechazó el registro: {ack_meta}")

                    print(f"[{self.worker_id}] Registro exitoso. Listo para recibir fotogramas.")

                    # 3. Bucle de procesamiento de tareas
                    self._work_loop(sock)

            except ConnectionRefusedError:
                print(f"[{self.worker_id}] No se pudo conectar al Broker (¿está encendido?). Reintentando en 3 segundos...")
                time.sleep(3)
            except (ConnectionError, BrokenPipeError, ConnectionResetError) as conn_err:
                print(f"[{self.worker_id}] Conexión perdida con el Broker ({conn_err}). Reintentando en 3 segundos...")
                time.sleep(3)
            except KeyboardInterrupt:
                print(f"\n[{self.worker_id}] Deteniendo Worker por solicitud del usuario...")
                self.is_running = False
                break
            except Exception as exc:
                print(f"[{self.worker_id}] Error inesperado: {exc}. Reintentando en 3 segundos...")
                time.sleep(3)

    def _work_loop(self, sock: socket.socket):
        """Escucha tareas entrantes del Broker y retorna los resultados."""
        frames_processed = 0

        while self.is_running:
            meta, frame_bytes = receive_message(sock)
            msg_type = meta.get("type")

            if msg_type == MSG_WORKER_FRAME_TASK:
                frame_id = meta.get("frame_id")
                filter_name = meta.get("filter", "grayscale")

                t_start = time.perf_counter()

                # Aplicar el filtro de procesamiento de imagen
                processed_frame_bytes = ImageFilters.apply_filter(frame_bytes, filter_name)

                elapsed_ms = (time.perf_counter() - t_start) * 1000
                frames_processed += 1

                print(
                    f"[{self.worker_id}] Frame {frame_id:04d} procesado con éxito "
                    f"[Filtro: '{filter_name}'] en {elapsed_ms:.1f} ms. (Total: {frames_processed})"
                )

                # Retornar el frame procesado al Broker conservando estrictamente el frame_id
                send_message(
                    sock,
                    {
                        "type": MSG_WORKER_FRAME_RESULT,
                        "frame_id": frame_id,
                        "worker_id": self.worker_id,
                    },
                    payload=processed_frame_bytes,
                )

            elif msg_type == MSG_ERROR:
                print(f"[{self.worker_id}] Notificación de error del Broker: {meta.get('error')}")


def main():
    parser = argparse.ArgumentParser(
        description="Nodo de Procesamiento (Worker) del Clúster Distribuido.\nPuede ejecutarse en este u otros dispositivos conectados a la misma red.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--id",
        type=str,
        default=f"worker_{os.getpid()}",
        help="Identificador único para este nodo (ej. worker_1, worker_laptop, etc.)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=DEFAULT_BROKER_HOST,
        help="Dirección IP del servidor BROKER en la red (ej. 192.168.1.50 o 127.0.0.1)",
    )
    parser.add_argument("--port", type=int, default=BROKER_WORKER_PORT, help="Puerto de workers del Broker (defecto: 5001)")

    args = parser.parse_args()

    worker = WorkerNode(worker_id=args.id, host=args.host, port=args.port)
    worker.start()


if __name__ == "__main__":
    main()
