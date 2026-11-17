"""
Interfaz Gráfica de Usuario (Frontend) con PyQt6.
Permite:
1. Cargar videos locales O grabar directamente con la cámara web (sin límites de tiempo).
2. Conectarse a Brokers en esta u otras máquinas de la red local (IP configurable).
3. Aplicar filtros artísticos O mejoras de calidad de imagen (nitidez, contraste, reducción de ruido).
4. Enviar el video al servidor BROKER en segundo plano sin congelar la UI.
5. Recibir y reproducir el video resultante procesado por el clúster.
"""

import sys
import time
from pathlib import Path
from typing import Optional

# Asegurar que la raíz del proyecto esté en sys.path para ejecuciones directas
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import cv2
import numpy as np
from PyQt6.QtCore import QThread, QTimer, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QFont, QImage, QPixmap
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStyle,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from client.client_app import VideoClient
from config.settings import (
    BROKER_CLIENT_PORT,
    DEFAULT_BROKER_HOST,
    RAW_VIDEOS_DIR,
)


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

        # Layout
        layout = QVBoxLayout(self)

        # Superficie de video en vivo
        self.video_surface = QLabel("Iniciando cámara web...")
        self.video_surface.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_surface.setStyleSheet("background-color: black; border-radius: 6px;")
        self.video_surface.setMinimumSize(640, 420)
        layout.addWidget(self.video_surface)

        # Barra de estado y contador
        self.status_label = QLabel("Cámara lista. Presiona 'Iniciar Grabación'.")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        layout.addWidget(self.status_label)

        # Botones de control
        btn_layout = QHBoxLayout()

        self.rec_button = QPushButton("🔴 Iniciar Grabación")
        self.rec_button.setStyleSheet("background-color: #d93025; color: white; font-weight: bold; padding: 8px;")
        self.rec_button.clicked.connect(self.toggle_recording)
        btn_layout.addWidget(self.rec_button)

        self.cancel_button = QPushButton("Cerrar")
        self.cancel_button.clicked.connect(self.close)
        btn_layout.addWidget(self.cancel_button)

        layout.addLayout(btn_layout)

        # Timer para capturar frames de la cámara a ~30 FPS
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._next_frame)

        self._start_camera()

    def _start_camera(self):
        self.cap = cv2.VideoCapture(0)
        if not self.cap or not self.cap.isOpened():
            self.video_surface.setText("No se pudo acceder a ninguna cámara web conectada.")
            self.rec_button.setEnabled(False)
            return

        # Configurar cámara en alta resolución (HD 720p) si el hardware lo soporta
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        self.timer.start(30)

    def _next_frame(self):
        if not self.cap or not self.cap.isOpened():
            return

        ret, frame = self.cap.read()
        if not ret or frame is None:
            return

        # Si se está grabando, escribir en el archivo de video
        if self.is_recording and self.writer:
            self.writer.write(frame)
            elapsed = time.time() - self.start_record_time
            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            self.status_label.setText(f"🔴 Grabando: {mins:02d}:{secs:02d} (Presiona 'Detener' al finalizar)")

        # Convertir frame BGR de OpenCV a QImage para visualizar en Qt
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
            # Iniciar grabación
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
            # Detener grabación y guardar
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
    """Hilo en segundo plano para manejar la comunicación de red sin congelar la GUI."""

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


class VideoPlayerWidget(QWidget):
    """Componente de reproducción de video integrado."""

    def __init__(self, title: str):
        super().__init__()
        self.title = title
        self.layout = QVBoxLayout(self)

        self.title_label = QLabel(self.title)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.layout.addWidget(self.title_label)

        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumSize(420, 260)
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
    """Ventana principal del Cliente."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Clúster de Procesamiento de Video - Cliente Distribuido")
        self.resize(1020, 720)

        self.selected_video_path: Optional[Path] = None
        self.worker_thread: Optional[VideoProcessingThread] = None

        self._build_ui()

    def _build_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Barra superior de conexión de red (permite conectar con otros dispositivos)
        net_group = QGroupBox("Configuración de Conexión al Clúster (Soporte Multi-dispositivo)")
        net_layout = QHBoxLayout(net_group)

        net_layout.addWidget(QLabel("IP del Broker:"))
        self.host_input = QLineEdit(DEFAULT_BROKER_HOST)
        self.host_input.setPlaceholderText("Ej: 192.168.1.50 o 127.0.0.1")
        net_layout.addWidget(self.host_input)

        net_layout.addWidget(QLabel("Puerto:"))
        self.port_input = QLineEdit(str(BROKER_CLIENT_PORT))
        self.port_input.setMaximumWidth(70)
        net_layout.addWidget(self.port_input)

        main_layout.addWidget(net_group)

        # Panel de reproductores (Original vs Procesado)
        players_layout = QHBoxLayout()

        # Panel izquierdo: Video original
        left_group = QGroupBox("1. Video de Entrada (Original)")
        left_layout = QVBoxLayout(left_group)
        self.original_player = VideoPlayerWidget("Previsualización Original")
        left_layout.addWidget(self.original_player)

        # Botones de selección / grabación
        source_btns_layout = QHBoxLayout()

        self.select_button = QPushButton("📁 Cargar Archivo...")
        self.select_button.clicked.connect(self.select_video_file)
        source_btns_layout.addWidget(self.select_button)

        self.record_button = QPushButton("🎥 Grabar desde Cámara")
        self.record_button.setStyleSheet("font-weight: bold;")
        self.record_button.clicked.connect(self.open_camera_recorder)
        source_btns_layout.addWidget(self.record_button)

        left_layout.addLayout(source_btns_layout)
        players_layout.addWidget(left_group)

        # Panel derecho: Video procesado
        right_group = QGroupBox("2. Video de Salida (Procesado por el Clúster)")
        right_layout = QVBoxLayout(right_group)
        self.processed_player = VideoPlayerWidget("Resultado del Clúster")
        right_layout.addWidget(self.processed_player)
        players_layout.addWidget(right_group)

        main_layout.addLayout(players_layout)

        # Panel de configuración y envío
        action_group = QGroupBox("3. Filtro / Mejora y Procesamiento Distribuido")
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

        self.send_button = QPushButton("🚀 Enviar al Clúster (BROKER)")
        self.send_button.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.send_button.setStyleSheet("background-color: #1a73e8; color: white; padding: 7px 16px; border-radius: 4px;")
        self.send_button.clicked.connect(self.send_to_cluster)
        self.send_button.setEnabled(False)
        action_layout.addWidget(self.send_button)

        main_layout.addWidget(action_group)

        # Registro de eventos / logs
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(110)
        self.log_text.setPlaceholderText("Bitácora de eventos y comunicación en red...")
        main_layout.addWidget(self.log_text)

        self.log_message(f"Cliente iniciado. Listo para conectarse al Broker en {DEFAULT_BROKER_HOST}:{BROKER_CLIENT_PORT}")

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
            f"El video ha sido procesado por el clúster y guardado en:\n{output_path}",
        )

    def on_processing_failure(self, error_message: str):
        self.progress_bar.setVisible(False)
        self.send_button.setEnabled(True)
        self.select_button.setEnabled(True)
        self.record_button.setEnabled(True)
        self.log_message(f"ERROR: {error_message}")
        QMessageBox.critical(
            self,
            "Error de Comunicación",
            f"No se pudo completar el procesamiento:\n\n{error_message}\n\nVerifica que el BROKER esté activo y accesible en esa IP/Puerto.",
        )


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
