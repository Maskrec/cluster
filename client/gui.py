"""
Interfaz Gráfica de Usuario (Frontend) con PyQt6.
Permite:
1. Centro de Control para iniciar/detener el Broker y Workers con 1 clic desde la misma interfaz.
2. Cargar videos locales O grabar directamente con la cámara web.
3. Biblioteca Compartida Distribuida: transferencia de archivos y descarga/subida entre computadoras.
4. Procesamiento de Super-Resolución 2X HD y filtros avanzados.
"""

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Asegurar que la raíz del proyecto esté en sys.path para ejecuciones directas
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import cv2
import numpy as np
from PyQt6.QtCore import QThread, QTimer, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QImage, QPixmap
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from client.client_app import VideoClient
from config.settings import (
    BASE_DIR,
    BROKER_CLIENT_PORT,
    DEFAULT_BROKER_HOST,
    LOCAL_IP,
    PROCESSED_VIDEOS_DIR,
    RAW_VIDEOS_DIR,
    SHARED_LIBRARY_DIR,
)

# Detectar ejecutable de Python del entorno virtual
VENV_PYTHON = BASE_DIR / ".venv" / "Scripts" / "python.exe"
PYTHON_EXEC = str(VENV_PYTHON.resolve()) if VENV_PYTHON.exists() else sys.executable


class CameraRecordingDialog(QDialog):
    """Ventana modal para vista previa y grabación directa desde la cámara web."""

    video_recorded = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Grabador de Cámara Web - Sin límites")
        self.resize(680, 560)

        self.cap: Optional[cv2.VideoCapture] = None
        self.writer: Optional[cv2.VideoWriter] = None
        self.recording_path: Optional[Path] = None

        self.is_recording = False
        self.start_record_time = 0.0

        layout = QVBoxLayout(self)

        self.video_surface = QLabel("Iniciando cámara web...")
        self.video_surface.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_surface.setStyleSheet("background-color: black; border-radius: 6px;")
        self.video_surface.setMinimumSize(640, 420)
        layout.addWidget(self.video_surface)

        self.status_label = QLabel("Cámara lista. Presiona 'Iniciar Grabación'.")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        layout.addWidget(self.status_label)

        btn_layout = QHBoxLayout()

        self.rec_button = QPushButton("🔴 Iniciar Grabación")
        self.rec_button.setStyleSheet("background-color: #d93025; color: white; font-weight: bold; padding: 8px;")
        self.rec_button.clicked.connect(self.toggle_recording)
        btn_layout.addWidget(self.rec_button)

        self.cancel_button = QPushButton("Cerrar")
        self.cancel_button.clicked.connect(self.close)
        btn_layout.addWidget(self.cancel_button)

        layout.addLayout(btn_layout)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._next_frame)

        self._start_camera()

    def _start_camera(self):
        self.cap = cv2.VideoCapture(0)
        if not self.cap or not self.cap.isOpened():
            self.video_surface.setText("No se pudo acceder a ninguna cámara web conectada.")
            self.rec_button.setEnabled(False)
            return

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.timer.start(30)

    def _next_frame(self):
        if not self.cap or not self.cap.isOpened():
            return

        ret, frame = self.cap.read()
        if not ret or frame is None:
            return

        if self.is_recording and self.writer:
            self.writer.write(frame)
            elapsed = time.time() - self.start_record_time
            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            self.status_label.setText(f"🔴 Grabando: {mins:02d}:{secs:02d} (Presiona 'Detener' al finalizar)")

        h, w, ch = frame.shape
        bytes_per_line = ch * w
        q_img = QImage(frame.data, w, h, bytes_per_line, QImage.Format.Format_BGR888)
        scaled_pixmap = QPixmap.fromImage(q_img).scaled(
            self.video_surface.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.video_surface.setPixmap(scaled_pixmap)

    def toggle_recording(self):
        if not self.is_recording:
            timestamp = int(time.time())
            self.recording_path = RAW_VIDEOS_DIR / f"recorded_{timestamp}.mp4"

            w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            self.writer = cv2.VideoWriter(str(self.recording_path.resolve()), fourcc, 30.0, (w, h))

            self.is_recording = True
            self.start_record_time = time.time()
            self.rec_button.setText("⏹ Detener y Cargar Video")
            self.rec_button.setStyleSheet("background-color: #1a73e8; color: white; font-weight: bold; padding: 8px;")
        else:
            self.is_recording = False
            if self.writer:
                self.writer.release()
                self.writer = None

            if self.recording_path and self.recording_path.exists():
                self.video_recorded.emit(str(self.recording_path.resolve()))
                self.accept()

    def closeEvent(self, event):
        self.timer.stop()
        if self.writer:
            self.writer.release()
        if self.cap:
            self.cap.release()
        super().closeEvent(event)


class VideoProcessingThread(QThread):
    """Hilo para envío de video al clúster sin bloquear la GUI."""

    status_updated = pyqtSignal(str)
    success = pyqtSignal(str)
    failure = pyqtSignal(str)

    def __init__(self, video_path: Path, filter_name: str, host: str, port: int):
        super().__init__()
        self.video_path = video_path
        self.filter_name = filter_name
        self.host = host
        self.port = port

    def run(self):
        try:
            client = VideoClient(host=self.host, port=self.port)
            result_path = client.send_video_for_processing(
                video_path=self.video_path,
                filter_name=self.filter_name,
                status_callback=self.status_updated.emit,
            )
            self.success.emit(str(result_path))
        except Exception as exc:
            self.failure.emit(str(exc))


class LibraryActionThread(QThread):
    """Hilo en segundo plano para operaciones con la biblioteca compartida."""

    status_updated = pyqtSignal(str)
    list_ready = pyqtSignal(list)
    upload_done = pyqtSignal(str)
    download_done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, action: str, host: str, port: int, **kwargs):
        super().__init__()
        self.action = action
        self.host = host
        self.port = port
        self.kwargs = kwargs

    def run(self):
        try:
            client = VideoClient(host=self.host, port=self.port)
            if self.action == "list":
                files = client.list_shared_library(status_callback=self.status_updated.emit)
                self.list_ready.emit(files)
            elif self.action == "upload":
                filepath = self.kwargs["file_path"]
                fname = client.upload_to_library(filepath, status_callback=self.status_updated.emit)
                self.upload_done.emit(fname)
            elif self.action == "download":
                fname = self.kwargs["filename"]
                dest = self.kwargs["dest_folder"]
                saved_path = client.download_from_library(fname, dest, status_callback=self.status_updated.emit)
                self.download_done.emit(str(saved_path))
        except Exception as exc:
            self.failed.emit(str(exc))


class VideoPlayerWidget(QWidget):
    """Componente de reproducción de video integrado."""

    def __init__(self, title: str):
        super().__init__()
        self.title = title
        self.layout = QVBoxLayout(self)

        self.title_label = QLabel(self.title)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.layout.addWidget(self.title_label)

        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumSize(400, 240)
        self.layout.addWidget(self.video_widget)

        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)

        self.controls_layout = QHBoxLayout()
        self.play_button = QPushButton()
        self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.play_button.clicked.connect(self.toggle_play)
        self.play_button.setEnabled(False)
        self.controls_layout.addWidget(self.play_button)

        self.status_label = QLabel("Sin video cargado")
        self.status_label.setStyleSheet("color: #666; font-size: 11px;")
        self.controls_layout.addWidget(self.status_label)

        self.layout.addLayout(self.controls_layout)

    def load_video(self, file_path: str):
        path = Path(file_path)
        if not path.exists():
            return
        self.player.setSource(QUrl.fromLocalFile(str(path.resolve())))
        self.play_button.setEnabled(True)
        self.status_label.setText(path.name)
        self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        else:
            self.player.play()
            self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))


class MainWindow(QMainWindow):
    """Ventana principal del Cliente con Centro de Control y Biblioteca Compartida."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Clúster de Procesamiento de Video - Centro de Control y Biblioteca Compartida")
        self.resize(1120, 840)

        self.selected_video_path: Optional[Path] = None
        self.worker_thread: Optional[VideoProcessingThread] = None
        self.lib_thread: Optional[LibraryActionThread] = None

        # Procesos locales de servicios
        self.broker_process: Optional[subprocess.Popen] = None
        self.worker_processes: List[subprocess.Popen] = []

        self._build_ui()

    def _build_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # =====================================================================
        # 1. CENTRO DE CONTROL DE SERVICIOS (Ejecución directa desde la GUI)
        # =====================================================================
        control_group = QGroupBox("🎛️ Centro de Control de Servicios (Ejecutar Todo sin Consolas)")
        control_layout = QHBoxLayout(control_group)

        # Botón maestro de 1 Clic
        self.all_services_btn = QPushButton("🚀 Iniciar Clúster (Broker + 1 Worker)")
        self.all_services_btn.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        self.all_services_btn.setStyleSheet("background-color: #0b8043; color: white; padding: 6px 12px; border-radius: 4px;")
        self.all_services_btn.clicked.connect(self.toggle_all_services)
        control_layout.addWidget(self.all_services_btn)

        # Control individual Broker
        self.broker_btn = QPushButton("▶ Iniciar Broker")
        self.broker_btn.clicked.connect(self.toggle_broker)
        control_layout.addWidget(self.broker_btn)

        self.broker_badge = QLabel("Broker: ⚪ Inactivo")
        self.broker_badge.setStyleSheet("font-weight: bold; color: #555;")
        control_layout.addWidget(self.broker_badge)

        # Control individual Worker (1 worker por GUI)
        self.workers_btn = QPushButton("▶ Iniciar 1 Worker")
        self.workers_btn.clicked.connect(self.toggle_workers)
        control_layout.addWidget(self.workers_btn)

        self.workers_badge = QLabel("Worker: ⚪ Inactivo")
        self.workers_badge.setStyleSheet("font-weight: bold; color: #555;")
        control_layout.addWidget(self.workers_badge)

        # Configuración de Red
        control_layout.addSpacing(15)
        control_layout.addWidget(QLabel("IP Broker:"))
        self.host_input = QLineEdit("127.0.0.1")
        self.host_input.setToolTip(f"Usa 127.0.0.1 en esta máquina. Para conectar otra laptop, usa la IP de red de la PC 1: {LOCAL_IP}")
        self.host_input.setMaximumWidth(120)
        control_layout.addWidget(self.host_input)

        control_layout.addWidget(QLabel("Puerto:"))
        self.port_input = QLineEdit(str(BROKER_CLIENT_PORT))
        self.port_input.setMaximumWidth(55)
        control_layout.addWidget(self.port_input)

        self.ip_info_label = QLabel(f"(IP de esta PC en red: {LOCAL_IP})")
        self.ip_info_label.setStyleSheet("color: #666; font-size: 10px;")
        control_layout.addWidget(self.ip_info_label)

        main_layout.addWidget(control_group)

        # =====================================================================
        # 2. PESTAÑAS PRINCIPALES: PROCESAMIENTO vs BIBLIOTECA COMPARTIDA
        # =====================================================================
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # Pestaña 1: Procesamiento y Cámara
        self.tab_process = QWidget()
        self._build_processing_tab(self.tab_process)
        self.tabs.addTab(self.tab_process, "🎬 Procesamiento y Cámara Web")

        # Pestaña 2: Biblioteca Compartida entre Laptops
        self.tab_library = QWidget()
        self._build_library_tab(self.tab_library)
        self.tabs.addTab(self.tab_library, "📚 Biblioteca Compartida de Videos (Transferencia entre PCs)")

        # =====================================================================
        # 3. BITÁCORA Y PROGRESO GENERAL
        # =====================================================================
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(95)
        self.log_text.setPlaceholderText("Bitácora de eventos del clúster...")
        main_layout.addWidget(self.log_text)

        self.log_message(f"Interfaz lista. Puedes iniciar los servicios con el botón 'Iniciar Clúster Completo'.")

    # =========================================================================
    # CONSTRUCCIÓN PESTAÑA 1: PROCESAMIENTO
    # =========================================================================
    def _build_processing_tab(self, parent: QWidget):
        layout = QVBoxLayout(parent)

        # Paneles de video
        players_layout = QHBoxLayout()

        # Izquierda: Original
        left_group = QGroupBox("1. Video de Entrada (Original)")
        left_layout = QVBoxLayout(left_group)
        self.original_player = VideoPlayerWidget("Previsualización Original")
        left_layout.addWidget(self.original_player)

        source_btns = QHBoxLayout()
        self.select_button = QPushButton("📁 Cargar Archivo...")
        self.select_button.clicked.connect(self.select_video_file)
        source_btns.addWidget(self.select_button)

        self.record_button = QPushButton("🎥 Grabar desde Cámara")
        self.record_button.setStyleSheet("font-weight: bold;")
        self.record_button.clicked.connect(self.open_camera_recorder)
        source_btns.addWidget(self.record_button)

        left_layout.addLayout(source_btns)
        players_layout.addWidget(left_group)

        # Derecha: Resultado
        right_group = QGroupBox("2. Video de Salida (Resultado del Clúster)")
        right_layout = QVBoxLayout(right_group)
        self.processed_player = VideoPlayerWidget("Resultado Mejorado")
        right_layout.addWidget(self.processed_player)
        players_layout.addWidget(right_group)

        layout.addLayout(players_layout)

        # Operaciones y Envío
        action_group = QGroupBox("3. Operación de Calidad / Filtro")
        action_layout = QHBoxLayout(action_group)

        action_layout.addWidget(QLabel("Operación:"))
        self.filter_combo = QComboBox()
        self.filter_combo.addItems([
            "💎 Super-Resolución 2X HD + Realce de Detalles (upscale_hd)",
            "✨ Realce Profundo de Texturas y Claridad (detail_enhance)",
            "🔆 Mejora de Contraste y Rango Dinámico CLAHE (contrast)",
            "🧹 Reducción de Ruido y Artefactos (denoise)",
            "🗡️ Enfoque y Nitidez de Contornos (sharpen)",
            "🎨 Escala de Grises (grayscale)",
            "🔲 Detección de Bordes (edge_detection)",
            "💧 Desenfoque Gaussiano (blur)",
            "🎞️ Efecto Sepia (sepia)",
            "🔄 Inversión de Colores (invert)",
        ])
        action_layout.addWidget(self.filter_combo)

        self.send_button = QPushButton("🚀 Enviar al Clúster para Procesar")
        self.send_button.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.send_button.setStyleSheet("background-color: #1a73e8; color: white; padding: 7px 16px; border-radius: 4px;")
        self.send_button.clicked.connect(self.send_to_cluster)
        self.send_button.setEnabled(False)
        action_layout.addWidget(self.send_button)

        layout.addWidget(action_group)

    # =========================================================================
    # CONSTRUCCIÓN PESTAÑA 2: BIBLIOTECA COMPARTIDA
    # =========================================================================
    def _build_library_tab(self, parent: QWidget):
        layout = QVBoxLayout(parent)

        desc = QLabel(
            "📁 Los videos guardados aquí se encuentran centralizados en el Broker y pueden ser transferidos, "
            "descargados o compartidos entre cualquier computadora conectada al clúster."
        )
        desc.setStyleSheet("color: #444; font-size: 11px; margin-bottom: 4px;")
        layout.addWidget(desc)

        # Tabla de archivos
        self.library_table = QTableWidget()
        self.library_table.setColumnCount(4)
        self.library_table.setHorizontalHeaderLabels(["Nombre del Video", "Tamaño (MB)", "Fecha de Modificación", "Tipo"])
        self.library_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.library_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.library_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.library_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.library_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.library_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.library_table)

        # Botones de acción de biblioteca
        lib_btns_layout = QHBoxLayout()

        self.btn_refresh_lib = QPushButton("🔄 Actualizar Catálogo")
        self.btn_refresh_lib.clicked.connect(self.refresh_shared_library)
        lib_btns_layout.addWidget(self.btn_refresh_lib)

        self.btn_download_lib = QPushButton("⬇️ Descargar a mi PC")
        self.btn_download_lib.setStyleSheet("font-weight: bold;")
        self.btn_download_lib.clicked.connect(self.download_selected_from_library)
        lib_btns_layout.addWidget(self.btn_download_lib)

        self.btn_upload_lib = QPushButton("⬆️ Compartir / Subir Video a la Biblioteca")
        self.btn_upload_lib.clicked.connect(self.upload_file_to_library)
        lib_btns_layout.addWidget(self.btn_upload_lib)

        self.btn_play_lib = QPushButton("▶️ Previsualizar Video")
        self.btn_play_lib.clicked.connect(self.preview_selected_library_video)
        lib_btns_layout.addWidget(self.btn_play_lib)

        layout.addLayout(lib_btns_layout)

    # =========================================================================
    # GESTIÓN DE SERVICIOS LOCALES (BROKER Y WORKERS DESDE LA GUI)
    # =========================================================================
    def toggle_all_services(self):
        """Inicia o detiene el clúster (Broker + 1 Worker) con 1 solo clic."""
        if self.broker_process is None and len(self.worker_processes) == 0:
            self.start_broker_process()
            QTimer.singleShot(1500, lambda: self.start_workers_process(count=1))
            self.all_services_btn.setText("⏹ Detener Clúster Completo")
            self.all_services_btn.setStyleSheet("background-color: #d93025; color: white; padding: 6px 12px; border-radius: 4px;")
        else:
            self.stop_all_services()
            self.all_services_btn.setText("🚀 Iniciar Clúster (Broker + 1 Worker)")
            self.all_services_btn.setStyleSheet("background-color: #0b8043; color: white; padding: 6px 12px; border-radius: 4px;")

    def toggle_broker(self):
        if self.broker_process is None:
            self.start_broker_process()
        else:
            self.stop_broker_process()

    def start_broker_process(self):
        if self.broker_process is not None:
            return
        script_path = str((ROOT_DIR / "broker" / "broker_server.py").resolve())
        self.broker_process = subprocess.Popen(
            [PYTHON_EXEC, script_path],
            cwd=str(ROOT_DIR),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        self.broker_badge.setText("Broker: 🟢 Activo (5000/5001)")
        self.broker_badge.setStyleSheet("font-weight: bold; color: #0b8043;")
        self.broker_btn.setText("⏹ Detener Broker")
        self.log_message("Servidor BROKER iniciado con éxito desde la interfaz.")

    def stop_broker_process(self):
        if self.broker_process is not None:
            try:
                self.broker_process.terminate()
            except Exception:
                pass
            self.broker_process = None
        self.broker_badge.setText("Broker: ⚪ Inactivo")
        self.broker_badge.setStyleSheet("font-weight: bold; color: #555;")
        self.broker_btn.setText("▶ Iniciar Broker")
        self.log_message("Servidor BROKER detenido.")

    def toggle_workers(self):
        if len(self.worker_processes) == 0:
            self.start_workers_process(count=1)
        else:
            self.stop_workers_process()

    def start_workers_process(self, count: int = 1):
        if len(self.worker_processes) > 0:
            return
        script_path = str((ROOT_DIR / "worker" / "worker_node.py").resolve())
        host = self.host_input.text().strip() or "127.0.0.1"

        for i in range(1, count + 1):
            worker_id = f"worker_gui_{os.getpid()}_{i}"
            proc = subprocess.Popen(
                [PYTHON_EXEC, script_path, "--id", worker_id, "--host", host],
                cwd=str(ROOT_DIR),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )
            self.worker_processes.append(proc)

        self.workers_badge.setText(f"Worker: 🟢 {len(self.worker_processes)} Activo")
        self.workers_badge.setStyleSheet("font-weight: bold; color: #0b8043;")
        self.workers_btn.setText("⏹ Detener Worker")
        self.log_message("1 Nodo Worker iniciado y conectado al Broker.")

    def stop_workers_process(self):
        for proc in self.worker_processes:
            try:
                proc.terminate()
            except Exception:
                pass
        self.worker_processes.clear()
        self.workers_badge.setText("Worker: ⚪ Inactivo")
        self.workers_badge.setStyleSheet("font-weight: bold; color: #555;")
        self.workers_btn.setText("▶ Iniciar 1 Worker")
        self.log_message("Worker local detenido.")

    def stop_all_services(self):
        self.stop_workers_process()
        self.stop_broker_process()

    # =========================================================================
    # ACCIONES DE BIBLIOTECA COMPARTIDA
    # =========================================================================
    def refresh_shared_library(self):
        host = self.host_input.text().strip() or DEFAULT_BROKER_HOST
        port = int(self.port_input.text().strip() or BROKER_CLIENT_PORT)

        self.btn_refresh_lib.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.log_message("Solicitando catálogo de la biblioteca compartida al Broker...")

        self.lib_thread = LibraryActionThread(action="list", host=host, port=port)
        self.lib_thread.status_updated.connect(self.log_message)
        self.lib_thread.list_ready.connect(self._on_library_list_received)
        self.lib_thread.failed.connect(self._on_library_failed)
        self.lib_thread.start()

    def _on_library_list_received(self, files: List[Dict[str, Any]]):
        self.btn_refresh_lib.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.library_table.setRowCount(0)

        for row_idx, item in enumerate(files):
            self.library_table.insertRow(row_idx)
            self.library_table.setItem(row_idx, 0, QTableWidgetItem(item.get("filename", "")))
            self.library_table.setItem(row_idx, 1, QTableWidgetItem(str(item.get("size_mb", 0))))
            self.library_table.setItem(row_idx, 2, QTableWidgetItem(item.get("modified", "")))
            self.library_table.setItem(row_idx, 3, QTableWidgetItem(item.get("origin", "")))

        self.log_message(f"Biblioteca compartida actualizada: {len(files)} archivo(s) disponibles.")

    def download_selected_from_library(self):
        selected_row = self.library_table.currentRow()
        if selected_row < 0:
            QMessageBox.warning(self, "Aviso", "Selecciona un archivo de la lista para descargarlo.")
            return

        filename = self.library_table.item(selected_row, 0).text()
        dest_folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta para guardar el archivo")
        if not dest_folder:
            return

        host = self.host_input.text().strip() or DEFAULT_BROKER_HOST
        port = int(self.port_input.text().strip() or BROKER_CLIENT_PORT)

        self.btn_download_lib.setEnabled(False)
        self.progress_bar.setVisible(True)

        self.lib_thread = LibraryActionThread(
            action="download",
            host=host,
            port=port,
            filename=filename,
            dest_folder=Path(dest_folder),
        )
        self.lib_thread.status_updated.connect(self.log_message)
        self.lib_thread.download_done.connect(self._on_download_success)
        self.lib_thread.failed.connect(self._on_library_failed)
        self.lib_thread.start()

    def _on_download_success(self, file_path: str):
        self.btn_download_lib.setEnabled(True)
        self.progress_bar.setVisible(False)
        QMessageBox.information(
            self,
            "Transferencia Exitosa",
            f"El archivo fue descargado exitosamente a través del sistema en:\n{file_path}",
        )

    def upload_file_to_library(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar video para compartir en la biblioteca",
            "",
            "Archivos de Video (*.mp4 *.avi *.mov *.mkv *.wmv)",
        )
        if not file_path:
            return

        host = self.host_input.text().strip() or DEFAULT_BROKER_HOST
        port = int(self.port_input.text().strip() or BROKER_CLIENT_PORT)

        self.btn_upload_lib.setEnabled(False)
        self.progress_bar.setVisible(True)

        self.lib_thread = LibraryActionThread(
            action="upload",
            host=host,
            port=port,
            file_path=Path(file_path),
        )
        self.lib_thread.status_updated.connect(self.log_message)
        self.lib_thread.upload_done.connect(self._on_upload_success)
        self.lib_thread.failed.connect(self._on_library_failed)
        self.lib_thread.start()

    def _on_upload_success(self, filename: str):
        self.btn_upload_lib.setEnabled(True)
        self.progress_bar.setVisible(False)
        QMessageBox.information(
            self,
            "Archivo Compartido",
            f"El video '{filename}' se ha subido a la biblioteca compartida del clúster.",
        )
        self.refresh_shared_library()

    def preview_selected_library_video(self):
        selected_row = self.library_table.currentRow()
        if selected_row < 0:
            QMessageBox.warning(self, "Aviso", "Selecciona un video de la tabla para previsualizarlo.")
            return

        filename = self.library_table.item(selected_row, 0).text()

        # Si ya existe en la biblioteca compartida local o procesados, reproducir directamente
        local_path = SHARED_LIBRARY_DIR / filename
        if not local_path.exists():
            local_path = PROCESSED_VIDEOS_DIR / filename

        if local_path.exists():
            self.tabs.setCurrentIndex(0)
            self.processed_player.load_video(str(local_path.resolve()))
            self.log_message(f"Cargado en reproductor: {filename}")
        else:
            # Descargar a carpeta temporal y reproducir
            temp_dir = RAW_VIDEOS_DIR / "cache_preview"
            temp_dir.mkdir(parents=True, exist_ok=True)
            host = self.host_input.text().strip() or DEFAULT_BROKER_HOST
            port = int(self.port_input.text().strip() or BROKER_CLIENT_PORT)

            self.progress_bar.setVisible(True)
            self.lib_thread = LibraryActionThread(action="download", host=host, port=port, filename=filename, dest_folder=temp_dir)
            self.lib_thread.status_updated.connect(self.log_message)
            self.lib_thread.download_done.connect(self._on_preview_downloaded)
            self.lib_thread.failed.connect(self._on_library_failed)
            self.lib_thread.start()

    def _on_preview_downloaded(self, file_path: str):
        self.progress_bar.setVisible(False)
        self.tabs.setCurrentIndex(0)
        self.processed_player.load_video(file_path)
        self.log_message(f"Previsualizando video remoto: {Path(file_path).name}")

    def _on_library_failed(self, error_msg: str):
        self.progress_bar.setVisible(False)
        self.btn_refresh_lib.setEnabled(True)
        self.btn_download_lib.setEnabled(True)
        self.btn_upload_lib.setEnabled(True)
        self.log_message(f"Error en biblioteca compartida: {error_msg}")
        QMessageBox.critical(self, "Error de Biblioteca", f"No se pudo completar la operación:\n\n{error_msg}")

    # =========================================================================
    # ACCIONES DE PROCESAMIENTO
    # =========================================================================
    def log_message(self, message: str):
        self.log_text.append(f"• {message}")

    def select_video_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar video para procesar",
            "",
            "Archivos de Video (*.mp4 *.avi *.mov *.mkv *.wmv)",
        )
        if file_path:
            self._load_selected_video(file_path)

    def open_camera_recorder(self):
        dialog = CameraRecordingDialog(self)
        dialog.video_recorded.connect(self._load_selected_video)
        dialog.exec()

    def _load_selected_video(self, file_path: str):
        self.selected_video_path = Path(file_path)
        self.original_player.load_video(file_path)
        self.send_button.setEnabled(True)
        self.log_message(f"Video cargado listo para enviar: {self.selected_video_path.name}")

    def get_selected_filter_key(self) -> str:
        text = self.filter_combo.currentText()
        if "upscale_hd" in text:
            return "upscale_hd"
        elif "detail_enhance" in text:
            return "detail_enhance"
        elif "contrast" in text:
            return "contrast"
        elif "denoise" in text:
            return "denoise"
        elif "sharpen" in text:
            return "sharpen"
        elif "grayscale" in text:
            return "grayscale"
        elif "edge_detection" in text:
            return "edge_detection"
        elif "blur" in text:
            return "blur"
        elif "sepia" in text:
            return "sepia"
        elif "invert" in text:
            return "invert"
        return "upscale_hd"

    def send_to_cluster(self):
        if not self.selected_video_path:
            QMessageBox.warning(self, "Aviso", "Primero selecciona o graba un archivo de video.")
            return

        broker_host = self.host_input.text().strip() or DEFAULT_BROKER_HOST
        try:
            broker_port = int(self.port_input.text().strip())
        except ValueError:
            QMessageBox.warning(self, "Puerto inválido", "El puerto debe ser un número entero.")
            return

        filter_name = self.get_selected_filter_key()
        self.send_button.setEnabled(False)
        self.select_button.setEnabled(False)
        self.record_button.setEnabled(False)
        self.progress_bar.setVisible(True)

        self.log_message(f"Iniciando envío hacia {broker_host}:{broker_port} con operación '{filter_name}'...")

        self.worker_thread = VideoProcessingThread(
            video_path=self.selected_video_path,
            filter_name=filter_name,
            host=broker_host,
            port=broker_port,
        )
        self.worker_thread.status_updated.connect(self.log_message)
        self.worker_thread.success.connect(self.on_processing_success)
        self.worker_thread.failure.connect(self.on_processing_failure)
        self.worker_thread.start()

    def on_processing_success(self, output_path: str):
        self.progress_bar.setVisible(False)
        self.send_button.setEnabled(True)
        self.select_button.setEnabled(True)
        self.record_button.setEnabled(True)
        self.log_message(f"¡Éxito! Cargando video resultante en el reproductor...")
        self.processed_player.load_video(output_path)
        QMessageBox.information(
            self,
            "Procesamiento Finalizado",
            f"El video ha sido procesado por el clúster y guardado en:\n{output_path}\n\n(También se guardó una copia en la Biblioteca Compartida).",
        )
        # Actualizar automáticamente la biblioteca
        self.refresh_shared_library()

    def on_processing_failure(self, error_message: str):
        self.progress_bar.setVisible(False)
        self.send_button.setEnabled(True)
        self.select_button.setEnabled(True)
        self.record_button.setEnabled(True)
        self.log_message(f"ERROR: {error_message}")
        QMessageBox.critical(
            self,
            "Error de Comunicación",
            f"No se pudo completar el procesamiento:\n\n{error_message}\n\nVerifica que el BROKER y los WORKERS estén iniciados (puedes usar el botón 'Iniciar Clúster Completo' en la parte superior).",
        )

    def closeEvent(self, event):
        """Detiene todos los procesos hijos levantados por la GUI al cerrar la ventana."""
        self.stop_all_services()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
