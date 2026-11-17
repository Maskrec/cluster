# Contexto del Proyecto: Clúster de Procesamiento y Super-Resolución de Video (Sistemas Distribuidos)

## Arquitectura del Sistema
El sistema funciona bajo un modelo distribuido con tres componentes principales. Toda la generación de código y asistencia debe respetar esta separación de responsabilidades:

### 1. Cliente (Interfaz Gráfica - Frontend)
- **Responsabilidad:** Interacción con el usuario final y conectividad multidispositivo.
- **Flujo:** 
  1. Permite cargar cualquier video local o capturar directamente desde la cámara web (sin límites de duración).
  2. Permite configurar la IP y Puerto del servidor BROKER para operar en red local (LAN/Wi-Fi).
  3. Selecciona la operación deseada (ej. Super-Resolución 2X HD, Realce de Detalles, Contraste CLAHE, etc.).
  4. Envía el archivo de video al servidor BROKER en segundo plano sin congelar la interfaz.
  5. Recibe el video final mejorado en mayor calidad/resolución y lo reproduce en pantalla.

### 2. Servidor BROKER (Orquestador Central y Balanceador)
- **Responsabilidad:** Administración de la red, división de carga y ensamblaje multihilo.
- **Flujo:**
  1. Escucha en `0.0.0.0` y anuncia su IP local para que otros dispositivos (laptops, PCs) se conecten.
  2. Mantiene un registro dinámico (lista) de Nodos de Procesamiento (Workers) activos.
  3. Recibe el video del Cliente y lo divide en fotogramas (frames) con calidad JPEG al 95%.
  4. Asigna a cada frame un identificador numérico estricto (`frame_id`) para garantizar el orden.
  5. Distribuye concurrentemente los frames a los Nodos mediante Round Robin.
  6. Recibe los frames procesados/aumentados de resolución, los ordena por `frame_id`, detecta la nueva resolución de salida, reconstruye el video en alta definición y lo envía de vuelta al Cliente.

### 3. Nodos de Procesamiento (Workers)
- **Responsabilidad:** Cómputo intensivo, escalado de resolución y mejora de imagen en paralelo.
- **Flujo:**
  1. Al iniciar el script (en la misma máquina o en otra de la red con `--host <IP>`), el nodo envía un mensaje de "alta" al BROKER para registrarse.
  2. Escucha peticiones de trabajo.
  3. Aplica el pipeline de mejora requerido con OpenCV:
     - **Super-Resolución 2X HD (`upscale_hd`):** Reducción de ruido + Escalado al doble con interpolación Lanczos4 + Realce de texturas (`cv2.detailEnhance`) + Máscara de enfoque (Unsharp Masking) + Contraste dinámico LAB.
     - **Realce Profundo de Detalles (`detail_enhance`):** Acentuación de nitidez y contornos a resolución nativa.
     - **Filtros complementarios:** Contraste CLAHE, Denoise, Grayscale, Canny, Blur, Sepia.
  4. Retorna el frame procesado al BROKER conservando estrictamente el `frame_id` original.

## Reglas y Restricciones de Desarrollo
- **Protocolo de Comunicación:** Sockets TCP directos con encabezado binario fijo (`struct >IQ`: longitud JSON + longitud payload) para evitar fragmentación.
- **Independencia:** El Cliente nunca debe comunicarse directamente con los Nodos; toda transacción pasa obligatoriamente por el BROKER.
- **Sin límite de tiempo:** Soporta videos de cualquier longitud y tamaño.
- **Orden de Ejecución para Pruebas:**
  1. Levantar el servicio del BROKER (`start_cluster.bat` o `python broker/broker_server.py`).
  2. Levantar las instancias de los Nodos (`python worker/worker_node.py --id worker_1`).
  3. Levantar la Interfaz del Cliente (`python client/gui.py`).