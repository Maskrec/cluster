"""
Servidor BROKER (Orquestador Central y Balanceador de Carga).
Administra:
1. Puerto de Workers (5001): Registro dinámico de nodos de procesamiento.
2. Puerto de Clientes (5000): Recepción de videos, partición en frames,
   balanceo de carga vía Round Robin y reensamblado final.
"""

import concurrent.futures
import socket
import sys
import threading
import time
from pathlib import Path
from typing import List, Tuple

# Asegurar que la raíz del proyecto esté en sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from broker.load_balancer import LoadBalancer, WorkerConnection
from broker.video_manager import VideoManager
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
    MSG_WORKER_FRAME_RESULT,
    MSG_WORKER_FRAME_TASK,
    MSG_WORKER_REGISTER,
    MSG_WORKER_REGISTER_ACK,
    receive_message,
    send_message,
)
from config.settings import (
    BROKER_BIND_HOST,
    BROKER_CLIENT_PORT,
    BROKER_WORKER_PORT,
    LOCAL_IP,
    PROCESSED_VIDEOS_DIR,
    RAW_VIDEOS_DIR,
    SHARED_LIBRARY_DIR,
)


class BrokerServer:
    """Orquestador central del clúster distribuido."""

    def __init__(self, host: str = BROKER_BIND_HOST, client_port: int = BROKER_CLIENT_PORT, worker_port: int = BROKER_WORKER_PORT):
        self.host = host
        self.client_port = client_port
        self.worker_port = worker_port

        self.load_balancer = LoadBalancer()
        self.is_running = False

    def start(self):
        """Inicia los listeners para Workers y Clientes en hilos separados."""
        self.is_running = True

        print("=" * 65)
        print(f" [BROKER] Servidor Central Distribuido Iniciado")
        print(f" [BROKER] IP Local para otros dispositivos: {LOCAL_IP}")
        print(f" [BROKER] -> Clientes de otros PCs deben apuntar a: {LOCAL_IP}:{self.client_port}")
        print(f" [BROKER] -> Workers de otros PCs deben apuntar a:  {LOCAL_IP}:{self.worker_port}")
        print("=" * 65)

        # Hilo de escucha para Workers (Registro de nodos)
        worker_thread = threading.Thread(target=self._run_worker_listener, daemon=True, name="WorkerListener")
        worker_thread.start()

        # Servidor principal para Clientes (bucle principal)
        self._run_client_listener()

    # =========================================================================
    # GESTIÓN DE WORKERS (Nodos de Procesamiento)
    # =========================================================================

    def _run_worker_listener(self):
        """Escucha conexiones entrantes de nuevos nodos de procesamiento."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_sock:
            server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_sock.bind((self.host, self.worker_port))
            server_sock.listen(10)
            print(f"[BROKER] Escuchando WORKERS en {self.host}:{self.worker_port}")

            while self.is_running:
                try:
                    conn, addr = server_sock.accept()
                    threading.Thread(
                        target=self._handle_worker_registration,
                        args=(conn, addr),
                        daemon=True,
                    ).start()
                except Exception as exc:
                    if self.is_running:
                        print(f"[BROKER] Error aceptando worker: {exc}")

    def _handle_worker_registration(self, conn: socket.socket, addr: Tuple[str, int]):
        """Procesa el mensaje de alta de un Worker."""
        try:
            metadata, _ = receive_message(conn)
            if metadata.get("type") == MSG_WORKER_REGISTER:
                worker_id = metadata.get("worker_id", f"worker_{addr[0]}_{addr[1]}")
                worker_conn = self.load_balancer.register_worker(worker_id, conn, addr)

                # Confirmar registro al Worker
                send_message(conn, {"type": MSG_WORKER_REGISTER_ACK, "status": "OK"})

                # Mantener la conexión abierta para monitoreo continuo
                self._monitor_worker_alive(worker_conn)
            else:
                conn.close()
        except Exception as exc:
            print(f"[BROKER] Fallo en registro de worker desde {addr}: {exc}")
            try:
                conn.close()
            except Exception:
                pass

    def _monitor_worker_alive(self, worker_conn: WorkerConnection):
        """Monitorea pasivamente la conexión para detectar cuando el nodo se cae."""
        try:
            while self.is_running:
                # Si el worker cierra el socket abruptamente, recv retornará 0 bytes
                worker_conn.sock.settimeout(None)
                data = worker_conn.sock.recv(1, socket.MSG_PEEK)
                if not data:
                    break
                time.sleep(2)
        except Exception:
            pass
        finally:
            self.load_balancer.unregister_worker(worker_conn.worker_id)

    # =========================================================================
    # GESTIÓN DE CLIENTES
    # =========================================================================

    def _run_client_listener(self):
        """Escucha peticiones de clientes."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_sock:
            server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_sock.bind((self.host, self.client_port))
            server_sock.listen(5)
            print(f"[BROKER] Escuchando CLIENTES en {self.host}:{self.client_port}")
            print(f"[BROKER] Sistema listo. Presiona Ctrl+C para detener.")

            try:
                while self.is_running:
                    conn, addr = server_sock.accept()
                    threading.Thread(
                        target=self._handle_client,
                        args=(conn, addr),
                        daemon=True,
                    ).start()
            except KeyboardInterrupt:
                print("\n[BROKER] Deteniendo servidor...")
            finally:
                self.is_running = False

    def _handle_client(self, conn: socket.socket, addr: Tuple[str, int]):
        """Atiende a un cliente: procesa videos o gestiona la biblioteca compartida."""
        print(f"[BROKER] Cliente conectado desde {addr}")
        try:
            meta, payload = receive_message(conn)
            msg_type = meta.get("type")

            # =====================================================================
            # BIBLIOTECA COMPARTIDA: Listar archivos disponibles
            # =====================================================================
            if msg_type == MSG_LIBRARY_LIST_REQ:
                files_list = []
                seen_names = set()

                # Revisar archivos en biblioteca compartida y en procesados
                for directory in (SHARED_LIBRARY_DIR, PROCESSED_VIDEOS_DIR):
                    if not directory.exists():
                        continue
                    for f in directory.iterdir():
                        if f.is_file() and not f.name.startswith(".") and f.name not in seen_names:
                            seen_names.add(f.name)
                            stat = f.stat()
                            files_list.append({
                                "filename": f.name,
                                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                                "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
                                "origin": "Procesado" if "output" in f.name or "processed" in f.name else "Compartido",
                            })

                # Ordenar por fecha descendente
                files_list.sort(key=lambda x: x["modified"], reverse=True)
                send_message(conn, {"type": MSG_LIBRARY_LIST_RESP, "files": files_list})
                return

            # =====================================================================
            # BIBLIOTECA COMPARTIDA: Subir archivo directamente
            # =====================================================================
            elif msg_type == MSG_LIBRARY_UPLOAD_REQ:
                filename = meta.get("filename", f"shared_{int(time.time())}.mp4")
                target_path = SHARED_LIBRARY_DIR / filename
                target_path.write_bytes(payload)
                print(f"[BROKER] Archivo '{filename}' guardado en la Biblioteca Compartida ({len(payload)/1024/1024:.2f} MB).")
                send_message(conn, {"type": MSG_LIBRARY_UPLOAD_RESP, "filename": filename, "status": "OK"})
                return

            # =====================================================================
            # BIBLIOTECA COMPARTIDA: Descargar archivo específico
            # =====================================================================
            elif msg_type == MSG_LIBRARY_DOWNLOAD_REQ:
                filename = meta.get("filename", "")
                target_path = SHARED_LIBRARY_DIR / filename
                if not target_path.exists():
                    target_path = PROCESSED_VIDEOS_DIR / filename

                if not target_path.exists() or not target_path.is_file():
                    send_message(conn, {"type": MSG_ERROR, "error": f"Archivo '{filename}' no encontrado en la biblioteca."})
                    return

                print(f"[BROKER] Transfiriendo archivo '{filename}' al cliente {addr}...")
                file_bytes = target_path.read_bytes()
                send_message(
                    conn,
                    {"type": MSG_LIBRARY_DOWNLOAD_RESP, "filename": filename, "size_mb": round(len(file_bytes)/(1024*1024), 2)},
                    payload=file_bytes,
                )
                return

            # =====================================================================
            # PROCESAMIENTO DISTRIBUIDO: Enviar video al clúster
            # =====================================================================
            elif msg_type == MSG_CLIENT_UPLOAD_VIDEO:
                video_payload = payload
                filename = meta.get("filename", "input.mp4")
                filter_name = meta.get("filter", "upscale_hd")

                print(f"[BROKER] Video recibido '{filename}' ({len(video_payload) / 1024 / 1024:.2f} MB). Filtro solicitado: '{filter_name}'")

                # 1. Validar disponibilidad de workers en el clúster
                if self.load_balancer.active_count() == 0:
                    print("[BROKER] ERROR: No hay Nodos de Procesamiento (Workers) activos.")
                    send_message(
                        conn,
                        {
                            "type": MSG_ERROR,
                            "error": "No hay ningún Nodo de Procesamiento (Worker) activo en el clúster. Inicia los workers primero desde la interfaz.",
                        },
                    )
                    return

                # 2. Descomponer el video en fotogramas
                print(f"[BROKER] Descomponiendo '{filename}' en fotogramas...")
                frames, fps, frame_size = VideoManager.extract_frames(video_payload, filename)
                total_frames = len(frames)
                print(f"[BROKER] Extracción completa: {total_frames} fotogramas a {fps:.1f} FPS, resolución {frame_size[0]}x{frame_size[1]}")

                if total_frames == 0:
                    send_message(conn, {"type": MSG_ERROR, "error": "El video no contiene fotogramas válidos."})
                    return

                # 3. Distribuir fotogramas a los Workers mediante Round Robin concurrente
                start_time = time.time()
                print(f"[BROKER] Distribuyendo {total_frames} frames entre {self.load_balancer.active_count()} workers activos...")
                processed_frames = self._distribute_frames_to_workers(frames, filter_name)

                elapsed_processing = time.time() - start_time
                print(f"[BROKER] Procesamiento distribuido completado en {elapsed_processing:.2f} s. Reensamblando video...")

                # 4. Reconstruir el video en orden estricto de frame_id
                output_filename = f"broker_output_{int(time.time())}_{filename}"
                output_path = PROCESSED_VIDEOS_DIR / output_filename
                processed_video_bytes = VideoManager.build_video_from_frames(
                    processed_frames=processed_frames,
                    output_path=output_path,
                    fps=fps,
                    frame_size=frame_size,
                )

                # Guardar automáticamente copia en la Biblioteca Compartida para acceso entre laptops
                try:
                    shared_copy = SHARED_LIBRARY_DIR / output_filename
                    shared_copy.write_bytes(processed_video_bytes)
                except Exception as e:
                    print(f"[BROKER] Aviso al guardar en biblioteca compartida: {e}")

                # 5. Enviar el video final al Cliente
                print(f"[BROKER] Enviando video final al Cliente ({len(processed_video_bytes) / 1024 / 1024:.2f} MB)...")
                send_message(
                    conn,
                    {
                        "type": MSG_BROKER_PROCESSED_VIDEO,
                        "filename": output_filename,
                        "frames_count": total_frames,
                    },
                    payload=processed_video_bytes,
                )
                print(f"[BROKER] Transacción con cliente {addr} finalizada con éxito.")
                return

            else:
                send_message(conn, {"type": MSG_ERROR, "error": f"Tipo de mensaje no reconocido: '{msg_type}'."})
                return

        except Exception as exc:
            print(f"[BROKER] Error procesando cliente {addr}: {exc}")
            try:
                send_message(conn, {"type": MSG_ERROR, "error": str(exc)})
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _distribute_frames_to_workers(
        self,
        frames: List[Tuple[int, bytes]],
        filter_name: str,
    ) -> List[Tuple[int, bytes]]:
        """
        Distribuye los frames entre los workers usando un pool de hilos
        y reintentos automáticos si un worker cae durante el proceso.
        """
        results: List[Tuple[int, bytes]] = []
        lock = threading.Lock()

        def process_single_frame(frame_data: Tuple[int, bytes]) -> Tuple[int, bytes]:
            frame_id, frame_bytes = frame_data
            max_retries = 3

            for attempt in range(max_retries):
                worker = self.load_balancer.get_next_worker()
                if not worker:
                    raise RuntimeError("Todos los workers se desconectaron durante el procesamiento.")

                try:
                    # Adquirir el lock del worker para que no se mezclen frames en su socket
                    with worker.lock:
                        send_message(
                            worker.sock,
                            {
                                "type": MSG_WORKER_FRAME_TASK,
                                "frame_id": frame_id,
                                "filter": filter_name,
                            },
                            payload=frame_bytes,
                        )

                        resp_meta, resp_payload = receive_message(worker.sock)

                        if resp_meta.get("type") == MSG_WORKER_FRAME_RESULT:
                            return (resp_meta["frame_id"], resp_payload)
                        else:
                            raise RuntimeError(f"Respuesta inesperada del worker: {resp_meta}")

                except Exception as exc:
                    print(f"[BROKER] Fallo comunicando con {worker.worker_id} en frame {frame_id}: {exc}. Reintentando...")
                    self.load_balancer.unregister_worker(worker.worker_id)
                    time.sleep(0.1)

            raise RuntimeError(f"No se pudo procesar el frame {frame_id} tras {max_retries} intentos.")

        # Pool concurrente para saturar eficientemente los workers disponibles
        workers_count = max(1, self.load_balancer.active_count())
        max_threads = min(16, workers_count * 4)

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
            future_to_frame = {executor.submit(process_single_frame, f): f[0] for f in frames}
            for future in concurrent.futures.as_completed(future_to_frame):
                frame_res = future.result()
                with lock:
                    results.append(frame_res)

        return results


def main():
    broker = BrokerServer()
    broker.start()


if __name__ == "__main__":
    main()
