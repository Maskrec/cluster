"""
Protocolo de comunicación y serialización para el Clúster de Procesamiento.
Garantiza el correcto empaquetado y desempaquetado de mensajes sobre Sockets TCP,
evitando el problema de fragmentación de paquetes.

Formato del mensaje en red:
+-------------------+----------------------+--------------------+--------------------+
| Tamaño JSON (4B)  | Tamaño Payload (8B)  | Metadatos (JSON)   | Payload Binario    |
| struct: >I        | struct: >Q           | (UTF-8 string)     | (bytes brutos)     |
+-------------------+----------------------+--------------------+--------------------+
"""

import json
import socket
import struct
from typing import Any, Dict, Optional, Tuple

# Constantes de tipos de mensajes
MSG_CLIENT_UPLOAD_VIDEO = "CLIENT_UPLOAD_VIDEO"
MSG_BROKER_PROCESSED_VIDEO = "BROKER_PROCESSED_VIDEO"
MSG_WORKER_REGISTER = "WORKER_REGISTER"
MSG_WORKER_REGISTER_ACK = "WORKER_REGISTER_ACK"
MSG_WORKER_FRAME_TASK = "WORKER_FRAME_TASK"
MSG_WORKER_FRAME_RESULT = "WORKER_FRAME_RESULT"
MSG_ERROR = "ERROR"

HEADER_STRUCT = struct.Struct(">IQ")  # 4 bytes unsigned int + 8 bytes unsigned long long


def _recv_exact(sock: socket.socket, num_bytes: int) -> bytes:
    """Lee exactamente `num_bytes` del socket de forma continua."""
    buffer = bytearray()
    while len(buffer) < num_bytes:
        packet = sock.recv(num_bytes - len(buffer))
        if not packet:
            raise ConnectionError(
                f"Conexión cerrada prematuramente al esperar {num_bytes} bytes (se leyeron {len(buffer)})."
            )
        buffer.extend(packet)
    return bytes(buffer)


def send_message(sock: socket.socket, metadata: Dict[str, Any], payload: bytes = b"") -> None:
    """
    Envía un mensaje estructurado a través del socket.
    
    :param sock: Socket TCP conectado.
    :param metadata: Diccionario con la información y tipo de comando (serializado en JSON).
    :param payload: Bytes binarios adjuntos (ej. archivo de video o imagen de un frame).
    """
    metadata_bytes = json.dumps(metadata).encode("utf-8")
    header = HEADER_STRUCT.pack(len(metadata_bytes), len(payload))
    
    # Enviar encabezado + metadatos
    sock.sendall(header + metadata_bytes)
    
    # Enviar payload binario en bloques si existe
    if payload:
        sock.sendall(payload)


def receive_message(sock: socket.socket) -> Tuple[Dict[str, Any], bytes]:
    """
    Recibe un mensaje estructurado desde el socket.
    
    :param sock: Socket TCP conectado.
    :return: Tupla con (metadata: dict, payload: bytes).
    """
    header_bytes = _recv_exact(sock, HEADER_STRUCT.size)
    meta_size, payload_size = HEADER_STRUCT.unpack(header_bytes)
    
    metadata_bytes = _recv_exact(sock, meta_size)
    metadata = json.loads(metadata_bytes.decode("utf-8"))
    
    payload = _recv_exact(sock, payload_size) if payload_size > 0 else b""
    
    return metadata, payload
