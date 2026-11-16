# Clúster de Procesamiento de Video (Sistemas Distribuidos)

## Estructura del Proyecto

```text
cluster/
│
├── agent.md                    # Especificación y requerimientos del sistema
├── requirements.txt            # Dependencias del proyecto
├── .gitignore                  # Reglas de exclusión de git
├── README.md                   # Documentación general y estructura
│
├── config/                     # Configuración centralizada
│   ├── __init__.py
│   └── settings.py             # Hosts, puertos, buffers y rutas de almacenamiento
│
├── common/                     # Módulos transversales compartidos
│   ├── __init__.py
│   ├── protocol.py             # Definición del protocolo de comunicación y serialización
│   └── utils.py                # Helpers y utilidades generales
│
├── broker/                     # Servidor Broker (Orquestador Central y Balanceador)
│   ├── __init__.py
│   ├── broker_server.py        # Servidor principal y administración de conexiones
│   ├── load_balancer.py        # Registro de workers y algoritmo de balanceo (Round Robin)
│   └── video_manager.py        # Descomposición en frames y reconstrucción del video
│
├── worker/                     # Nodo de Procesamiento (Workers)
│   ├── __init__.py
│   ├── worker_node.py          # Ciclo de vida del worker (registro, escucha y envío)
│   └── image_filters.py        # Filtros de imagen y transformaciones (OpenCV/PIL)
│
├── client/                     # Cliente (Frontend / Interfaz de Usuario)
│   ├── __init__.py
│   ├── client_app.py           # Conexión y transferencia de video con el Broker
│   └── gui.py                  # Interfaz gráfica (carga/captura y reproducción)
│
└── storage/                    # Almacenamiento temporal de archivos
    ├── raw_videos/             # Videos originales recibidos
    ├── processed_videos/       # Videos finales procesados y reconstruidos
    └── temp_frames/            # Frames temporales durante el procesamiento
```

## Orden de Ejecución para Pruebas
1. Levantar el servicio del **BROKER**: `python broker/broker_server.py`
2. Levantar las instancias de los **Nodos (Workers)**: `python worker/worker_node.py` (instancia 1, 2, 3...)
3. Levantar la **Interfaz del Cliente**: `python client/gui.py` o `python client/client_app.py`

