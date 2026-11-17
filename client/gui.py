"""
Interfaz Gráfica de Usuario (Frontend) con PyQt6.
Permite:
1. Cargar un archivo de video desde el sistema de archivos local.
2. Previsualizar y reproducir el video original.
3. Elegir la transformación o filtro de imagen a aplicar.
4. Enviar el video al servidor BROKER en segundo plano (sin congelar la UI).
5. Recibir y reproducir el video procesado resultante.
"""

import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QThread, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
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
from config.settings import BROKER_CLIENT_PORT, BROKER_HOST


class VideoProcessingThread(QThread):
    """
    Hilo en segundo plano para manejar la comunicación de red sin congelar la GUI.
    """
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
    """Componente reutilizable de reproducción de video."""

    def __init__(self, title: str):
        super().__init__()
        self.title = title

        self.layout = QVBoxLayout(self)

        # Encabezado
        self.title_label = QLabel(self.title)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.layout.addWidget(self.title_label)

        # Superficie de video
        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumSize(420, 260)
        self.layout.addWidget(self.video_widget)

        # Reproductor y salida de audio
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)

        # Controles
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
        self.setWindowTitle("Clúster de Procesamiento de Video - Cliente")
        self.resize(960, 680)

        self.selected_video_path: Optional[Path] = None
        self.worker_thread: Optional[VideoProcessingThread] = None

        self._build_ui()

    def _build_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Título superior
        header = QLabel("Sistema Distribuido de Procesamiento de Video")
        header.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(header)

        # Panel de reproductores (Original vs Procesado)
        players_layout = QHBoxLayout()

        # Panel izquierdo: Video original
        left_group = QGroupBox("1. Video de Entrada (Original)")
        left_layout = QVBoxLayout(left_group)
        self.original_player = VideoPlayerWidget("Previsualización Original")
        left_layout.addWidget(self.original_player)

        self.select_button = QPushButton("Seleccionar Video (.mp4, .avi, .mov)...")
        self.select_button.clicked.connect(self.select_video_file)
        left_layout.addWidget(self.select_button)
        players_layout.addWidget(left_group)

        # Panel derecho: Video procesado
        right_group = QGroupBox("2. Video de Salida (Procesado por el Clúster)")
        right_layout = QVBoxLayout(right_group)
        self.processed_player = VideoPlayerWidget("Resultado del Clúster")
        right_layout.addWidget(self.processed_player)
        players_layout.addWidget(right_group)

        main_layout.addLayout(players_layout)

        # Panel de configuración y envío
        action_group = QGroupBox("3. Parámetros y Transmisión")
        action_layout = QHBoxLayout(action_group)

        action_layout.addWidget(QLabel("Filtro a aplicar:"))
        self.filter_combo = QComboBox()
        self.filter_combo.addItems([
            "Escala de Grises (grayscale)",
            "Inversión de Colores (invert)",
            "Detección de Bordes (edge_detection)",
            "Desenfoque Gaussiano (blur)",
            "Efecto Sepia (sepia)"
        ])
        action_layout.addWidget(self.filter_combo)

        self.send_button = QPushButton("Enviar al Clúster (BROKER)")
        self.send_button.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.send_button.setStyleSheet("background-color: #2b78e4; color: white; padding: 6px 14px;")
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
        self.log_text.setMaximumHeight(120)
        self.log_text.setPlaceholderText("Bitácora de eventos y comunicación con el Broker...")
        main_layout.addWidget(self.log_text)

        self.log_message(f"Cliente inicializado. Broker configurado en {BROKER_HOST}:{BROKER_CLIENT_PORT}")

    def log_message(self, message: str):
        self.log_text.append(f"• {message}")

    def select_video_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar video para procesar",
            "",
            "Archivos de Video (*.mp4 *.avi *.mov *.mkv *.wmv)"
        )
        if file_path:
            self.selected_video_path = Path(file_path)
            self.original_player.load_video(file_path)
            self.send_button.setEnabled(True)
            self.log_message(f"Video seleccionado: {self.selected_video_path.name}")

    def get_selected_filter_key(self) -> str:
        text = self.filter_combo.currentText()
        if "grayscale" in text:
            return "grayscale"
        elif "invert" in text:
            return "invert"
        elif "edge_detection" in text:
            return "edge_detection"
        elif "blur" in text:
            return "blur"
        elif "sepia" in text:
            return "sepia"
        return "grayscale"

    def send_to_cluster(self):
        if not self.selected_video_path:
            QMessageBox.warning(self, "Aviso", "Primero selecciona un archivo de video.")
            return

        filter_name = self.get_selected_filter_key()
        self.send_button.setEnabled(False)
        self.select_button.setEnabled(False)
        self.progress_bar.setVisible(True)

        self.log_message(f"Iniciando envío con filtro: '{filter_name}'...")

        self.worker_thread = VideoProcessingThread(
            video_path=self.selected_video_path,
            filter_name=filter_name,
            host=BROKER_HOST,
            port=BROKER_CLIENT_PORT,
        )
        self.worker_thread.status_updated.connect(self.log_message)
        self.worker_thread.success.connect(self.on_processing_success)
        self.worker_thread.failure.connect(self.on_processing_failure)
        self.worker_thread.start()

    def on_processing_success(self, output_path: str):
        self.progress_bar.setVisible(False)
        self.send_button.setEnabled(True)
        self.select_button.setEnabled(True)
        self.log_message(f"¡Éxito! Cargando video resultante en el reproductor...")
        self.processed_player.load_video(output_path)
        QMessageBox.information(
            self,
            "Procesamiento Finalizado",
            f"El video ha sido procesado por el clúster y guardado en:\n{output_path}"
        )

    def on_processing_failure(self, error_message: str):
        self.progress_bar.setVisible(False)
        self.send_button.setEnabled(True)
        self.select_button.setEnabled(True)
        self.log_message(f"ERROR: {error_message}")
        QMessageBox.critical(
            self,
            "Error de Comunicación",
            f"No se pudo completar el procesamiento:\n\n{error_message}\n\nVerifica que el BROKER esté levantado."
        )


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
