from pathlib import Path
import torch
import cv2
from PyQt6.QtCore import QThread, pyqtSignal  # type: ignore
from ultralytics import YOLO

DIRETORIO_RAIZ = Path(__file__).resolve().parent.parent


class YoloWorker(QThread):
    """Worker em segundo plano para inferência do modelo YOLO em vídeos."""

    # Sinais emitidos para a interface gráfica
    progresso = pyqtSignal(int, int)  # (frame_atual, total_frames)
    concluido = pyqtSignal(str, list)  # (caminho_video_processado, lista_frames_deteccoes)
    erro = pyqtSignal(str)

    def __init__(
        self,
        caminho_video: str,
        id_viagem: int,
        caminho_modelo: str = str(DIRETORIO_RAIZ / "best.pt"),
        confianca: float = 0.25,
        parent=None,
    ):
        super().__init__(parent)
        self.caminho_video = caminho_video
        self.id_viagem = id_viagem
        self.caminho_modelo = caminho_modelo
        self.confianca = confianca
        self._cancelado = False

    def cancelar(self):
        """Sinaliza para interromper o processamento."""
        self._cancelado = True

    def run(self):
        try:
            # 1. Abre o vídeo original para estimar a quantidade total de frames
            cap = cv2.VideoCapture(self.caminho_video)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) if cap.isOpened() else 0
            cap.release()

            # 2. Carrega o modelo YOLO
            if not Path(self.caminho_modelo).is_file():
                self.erro.emit(f"Arquivo do modelo não encontrado: {self.caminho_modelo}")
                return

            modelo = YOLO(self.caminho_modelo)
            dispositivo = 0 if torch.cuda.is_available() else "cpu"
            # 3. Executa a inferência
            results = modelo.predict(
                source=self.caminho_video,
                save=True,
                stream=True,
                project="videos_processados",
                name=str(self.id_viagem),
                conf=self.confianca,
                show=False,
                device=dispositivo,
            )

            frames_com_deteccoes: list[int] = []

            for numero_frame, result in enumerate(results):
                if self._cancelado:
                    return

                if len(result.boxes) > 0:
                    frames_com_deteccoes.append(numero_frame)

                # Notifica a interface do progresso
                self.progresso.emit(numero_frame + 1, total_frames)

            # 4. Localiza o vídeo processado gerado
            pasta_destino = DIRETORIO_RAIZ / "runs" / "detect" / "videos_processados" / str(self.id_viagem)
            nome_base = Path(self.caminho_video).stem
            candidato_avi = pasta_destino / f"{nome_base}.avi"
            candidato_mp4 = pasta_destino / f"{nome_base}.mp4"

            if candidato_avi.is_file():
                caminho_final = str(candidato_avi)
            elif candidato_mp4.is_file():
                caminho_final = str(candidato_mp4)
            else:
                # Procura qualquer vídeo gerado na pasta
                arquivos = list(pasta_destino.glob("*.*"))
                videos = [f for f in arquivos if f.suffix.lower() in [".avi", ".mp4", ".mkv"]]
                if videos:
                    caminho_final = str(videos[0])
                else:
                    self.erro.emit("Vídeo processado não foi encontrado na pasta de saída.")
                    return

            self.concluido.emit(caminho_final, frames_com_deteccoes)

        except Exception as e:
            self.erro.emit(str(e))
