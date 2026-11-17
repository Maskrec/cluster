"""
Balanceador de Carga y Registro Dinámico de Nodos para el BROKER.
Administra el ciclo de vida de los Nodos de Procesamiento (Workers) activos
y distribuye los fotogramas utilizando el algoritmo Round Robin de forma concurrente y segura.
"""

import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from socket import socket
from typing import Dict, List, Optional, Tuple

# Asegurar que la raíz del proyecto esté en sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


@dataclass
class WorkerConnection:
    """Representa un nodo de procesamiento activo en el clúster."""
    worker_id: str
    sock: socket
    address: Tuple[str, int]
    lock: threading.Lock  # Para garantizar que el envío/recepción sobre el socket del worker sea atómico


class LoadBalancer:
    """Registro de workers y balanceador de carga tipo Round Robin."""

    def __init__(self):
        self._workers: Dict[str, WorkerConnection] = {}
        self._worker_ids: List[str] = []
        self._current_index: int = 0
        self._lock = threading.Lock()

    def register_worker(self, worker_id: str, sock: socket, address: Tuple[str, int]) -> WorkerConnection:
        """
        Registra dinámicamente un nuevo Worker en el clúster.
        """
        with self._lock:
            # Si ya existía una conexión previa con el mismo ID, cerrar y reemplazar
            if worker_id in self._workers:
                try:
                    self._workers[worker_id].sock.close()
                except Exception:
                    pass
                if worker_id in self._worker_ids:
                    self._worker_ids.remove(worker_id)

            worker_conn = WorkerConnection(
                worker_id=worker_id,
                sock=sock,
                address=address,
                lock=threading.Lock(),
            )
            self._workers[worker_id] = worker_conn
            self._worker_ids.append(worker_id)
            print(f"[LoadBalancer] Worker registrado: '{worker_id}' desde {address}. Total activos: {len(self._worker_ids)}")
            return worker_conn

    def unregister_worker(self, worker_id: str) -> None:
        """
        Da de baja a un Worker desconectado o con error.
        """
        with self._lock:
            if worker_id in self._workers:
                try:
                    self._workers[worker_id].sock.close()
                except Exception:
                    pass
                del self._workers[worker_id]

            if worker_id in self._worker_ids:
                self._worker_ids.remove(worker_id)

            print(f"[LoadBalancer] Worker retirado: '{worker_id}'. Total activos: {len(self._worker_ids)}")

    def get_next_worker(self) -> Optional[WorkerConnection]:
        """
        Selecciona el siguiente Worker disponible mediante Round Robin.
        Retorna None si no hay ningún Worker activo en el clúster.
        """
        with self._lock:
            if not self._worker_ids:
                return None

            # Avanzar circularmente el puntero
            self._current_index = self._current_index % len(self._worker_ids)
            selected_id = self._worker_ids[self._current_index]
            self._current_index = (self._current_index + 1) % len(self._worker_ids)

            return self._workers.get(selected_id)

    def active_count(self) -> int:
        """Retorna la cantidad de workers activos actualmente."""
        with self._lock:
            return len(self._worker_ids)
