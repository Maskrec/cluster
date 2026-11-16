# Contexto del Proyecto: Clúster de Procesamiento de Video (Sistemas Distribuidos)

## Arquitectura del Sistema
El sistema funciona bajo un modelo distribuido con tres componentes principales. Toda la generación de código y asistencia debe respetar esta separación de responsabilidades:

### 1. Cliente (Interfaz Gráfica - Frontend)
- **Responsabilidad:** Interacción con el usuario final.
- **Flujo:** 
  1. Permite cargar o capturar un video de aproximadamente 15 segundos.
  2. Envía el archivo de video al servidor BROKER.
  3. Queda a la espera de la respuesta.
  4. Recibe el video procesado y lo reproduce/muestra en pantalla.

### 2. Servidor BROKER (Orquestador Central y Balanceador)
- **Responsabilidad:** Administración de la red, división de carga y ensamblaje.
- **Flujo:**
  1. Mantiene un registro dinámico (lista) de Nodos de Procesamiento activos.
  2. Recibe el video del Cliente y lo divide en fotogramas (frames).
  3. Asigna a cada frame un identificador numérico estricto (`frame_id`) para garantizar el orden.
  4. Envía los frames a los Nodos mediante un algoritmo de balanceo de carga (ej. Round Robin).
  5. Recibe los frames ya procesados, los ordena usando el `frame_id`, reconstruye el video y lo envía de vuelta al Cliente.

### 3. Nodos de Procesamiento (Workers)
- **Responsabilidad:** Cómputo intensivo e independiente (Procesamiento de imágenes).
- **Flujo:**
  1. Al iniciar el script, el nodo envía un mensaje de "alta" al BROKER para registrarse.
  2. Escucha peticiones de trabajo.
  3. Al recibir un frame, le aplica la transformación o filtro de imagen requerido (mediante OpenCV, PIL, etc.).
  4. Retorna el frame procesado al BROKER conservando el `frame_id` original.

## Reglas y Restricciones de Desarrollo
- **Protocolo de Comunicación:** [Definir aquí si se usarán Sockets TCP directos, HTTP REST, gRPC, etc.]. Todos los mensajes deben viajar serializados (ej. JSON para metadatos, bytes para las imágenes).
- **Independencia:** El Cliente nunca debe comunicarse directamente con los Nodos; toda transacción pasa obligatoriamente por el BROKER.
- **Orden de Ejecución para Pruebas:**
  1. Levantar el servicio del BROKER.
  2. Levantar las 3 instancias de los Nodos para que se registren.
  3. Levantar la Interfaz del Cliente para iniciar la transmisión.
- **Desarrollo Iterativo:** Probar primero la comunicación y transferencia de archivos con un video muy corto (o imágenes dummy) antes de integrar el procesamiento de video completo a 30 FPS.