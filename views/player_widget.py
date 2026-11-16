from pathlib import Path
import cv2
import datetime
from views.dialogos import JanelaCadastroEspecie, JanelaGerenciarEspecies
from PyQt6.QtCore import Qt, QUrl, pyqtSignal  
from PyQt6.QtSql import QSqlQueryModel, QSqlQuery 
from PyQt6.QtGui import QMouseEvent, QShortcut, QKeySequence
from PyQt6.QtMultimedia import QMediaPlayer  
from PyQt6.QtMultimediaWidgets import QVideoWidget  
from PyQt6.QtWidgets import (  
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
    QFormLayout,
    QLineEdit,
    QMenu,
    QTableView,
    QHeaderView,
    QComboBox,
    QSplitter
)

import database.banco_dados as db
from OCR import extrair_metadados_frame_video
COLUNA_ID_ANOTACAO = 0
COLUNA_FRAME_ANOTACAO = 2
class ClickableSlider(QSlider):
    """QSlider que pula diretamente para o ponto clicado com o botão esquerdo."""
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            # Calcula o novo valor baseado na posição X do clique
            largura = self.width()
            if largura > 0:
                pos_x = event.position().x()
                fracao = max(0.0, min(1.0, pos_x / largura))
                novo_valor = round(self.minimum() + fracao * (self.maximum() - self.minimum()))
                self.setValue(novo_valor)
                self.sliderMoved.emit(novo_valor)
        # Permite que o usuário continue arrastando se mantiver o botão pressionado
        super().mousePressEvent(event)

        
def formatar_tempo(ms: int) -> str:
    """Formata milissegundos para string mm:ss."""
    segundos = max(0, ms // 1000)
    minutos = segundos // 60
    segundos = segundos % 60
    return f"{minutos:02d}:{segundos:02d}"


class VideoPlayerWidget(QWidget):
    """Widget para exibição e controle de reprodução de vídeo com detecções."""

    voltar_solicitado = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.fps = 30.0
        self.frames_deteccoes: list[int] = []
        self.id_viagem: int | None = None
        self.caminho_video: str | None = None
        self._iniciar_ui()

    def _iniciar_ui(self):
        layout_base = QHBoxLayout(self)


        self.divisor = QSplitter(Qt.Orientation.Horizontal)

        # ----------------- Container da Esquerda: Vídeo e Controles -----------------
        widget_video = QWidget()
        layout_principal = QVBoxLayout(widget_video)

        # Tela de Vídeo
        self.tela_video = QVideoWidget()
        self.player = QMediaPlayer()
        self.player.setVideoOutput(self.tela_video)
        layout_principal.addWidget(self.tela_video, stretch=1)

        # Timeline (Slider de tempo)
        layout_timeline = QHBoxLayout()
        self.label_tempo_atual = QLabel("00:00")
        self.slider_posicao = ClickableSlider(Qt.Orientation.Horizontal)
        self.slider_posicao.setRange(0, 0)
        self.slider_posicao.sliderMoved.connect(self._slider_movido)

        self.label_tempo_total = QLabel("00:00")
        layout_timeline.addWidget(self.label_tempo_atual)
        layout_timeline.addWidget(self.slider_posicao)
        layout_timeline.addWidget(self.label_tempo_total)
        layout_principal.addLayout(layout_timeline)

        # Sinais do QMediaPlayer para o slider
        self.player.positionChanged.connect(self._posicao_alterada)
        self.player.durationChanged.connect(self._duracao_alterada)

        # Botões de controle
        layout_botoes = QHBoxLayout()

        self.botao_ultimo_frame_deteccao = QPushButton("⏮️ Detecção Anterior")
        self.botao_ultimo_frame_deteccao.setToolTip("Pular para a detecção anterior")
        self.botao_ultimo_frame_deteccao.clicked.connect(self.ultimo_frame_deteccao)

        self.botao_ultimo_frame = QPushButton("⏪ Frame Anterior")
        self.botao_ultimo_frame.setToolTip("Retroceder 1 frame")
        self.botao_ultimo_frame.clicked.connect(self.ultimo_frame)

        self.botao_play_pause = QPushButton("▶️ Play")
        self.botao_play_pause.setToolTip("Play/Pause")
        self.botao_play_pause.clicked.connect(self.play_pause)

        self.atalho_play_pause = QShortcut(QKeySequence("Space"), self)
        self.atalho_play_pause.activated.connect(self.play_pause)

        self.botao_proximo_frame = QPushButton("⏩ Próximo Frame")
        self.botao_proximo_frame.setToolTip("Avançar 1 frame")
        self.botao_proximo_frame.clicked.connect(self.prox_frame)

        self.botao_proximo_frame_deteccao = QPushButton("⏭️ Próxima Detecção")
        self.botao_proximo_frame_deteccao.setToolTip("Pular para a próxima detecção")
        self.botao_proximo_frame_deteccao.clicked.connect(self.prox_frame_deteccao)

        layout_botoes.addWidget(self.botao_ultimo_frame_deteccao)
        layout_botoes.addWidget(self.botao_ultimo_frame)
        layout_botoes.addWidget(self.botao_play_pause)
        layout_botoes.addWidget(self.botao_proximo_frame)
        layout_botoes.addWidget(self.botao_proximo_frame_deteccao)

        layout_principal.addLayout(layout_botoes)

        # Botão Voltar
        self.botao_voltar = QPushButton("Voltar para a lista de viagens")
        self.botao_voltar.clicked.connect(self._ao_clicar_voltar)
        layout_principal.addWidget(self.botao_voltar)

        # ----------------- Container da Direita: Anotações -----------------
        widget_painel = QWidget()
        layout_painel = QVBoxLayout(widget_painel)
        layout_especies = QHBoxLayout()
        self.caixa_especie = QComboBox()
        self.atualizar_lista_especies()
        
        self.botao_gerenciar_especies = QPushButton("Gerenciar espécies...")
        self.botao_gerenciar_especies.clicked.connect(self.gerenciar_especie)
        layout_especies.addWidget(self.caixa_especie)
        layout_especies.addWidget(self.botao_gerenciar_especies)
        self.campo_observacao = QLineEdit()
        self.campo_observacao.setPlaceholderText("Digite observação aqui...")
        confirma_anotacao = QPushButton("Registrar anotação")
        confirma_anotacao.clicked.connect(self.registrar_anotacao)

        # Tabela de Anotações
        self.tabela_anotacoes = QTableView()
        self.model_anotacoes = QSqlQueryModel()
        self.tabela_anotacoes.setModel(self.model_anotacoes)
        self.tabela_anotacoes.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabela_anotacoes.customContextMenuRequested.connect(self.menu_contexto_anotacoes)
        self.tabela_anotacoes.setAlternatingRowColors(True)
        self.tabela_anotacoes.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.tabela_anotacoes.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tabela_anotacoes.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        layout_painel.addLayout(layout_especies)
        self.campo_observacao = QLineEdit()
        self.campo_observacao.setPlaceholderText("Digite observação aqui...")
        layout_painel.addWidget(self.campo_observacao)
        layout_painel.addWidget(confirma_anotacao)
        layout_painel.addWidget(self.tabela_anotacoes)

        self.divisor.addWidget(widget_video)
        self.divisor.addWidget(widget_painel)
        self.divisor.setStretchFactor(0, 3)
        self.divisor.setStretchFactor(1, 1)
        self.divisor.setSizes([750, 450])

        layout_base.addWidget(self.divisor)

    def menu_contexto_anotacoes(self,pos):
        indice_clicado = self.tabela_anotacoes.indexAt(pos)
        if not indice_clicado.isValid():
            return

        menu = QMenu()
        acao_deletar = menu.addAction("Deletar Anotação")
        acao_ir_para_frame = menu.addAction("Ir para frame da anotação")
        acao_escolhida = menu.exec(self.tabela_anotacoes.viewport().mapToGlobal(pos))
        
        if acao_escolhida == acao_deletar:
            id_viagem = indice_clicado.siblingAtColumn(COLUNA_ID_ANOTACAO).data()
            db.deletar_anotacao(id_viagem)
            self.atualizar_tabela_anotacao()
        if acao_escolhida == acao_ir_para_frame:
            frame = indice_clicado.siblingAtColumn(COLUNA_FRAME_ANOTACAO).data()
            duracao_frame_ms = 1000 / self.fps
            pos_destino_ms = int((frame * duracao_frame_ms) + (duracao_frame_ms / 2))            
            self.player.setPosition(pos_destino_ms)
        
        
    def atualizar_tabela_anotacao(self):
        if not hasattr(self, 'id_viagem') or self.id_viagem is None:
            return
        query = QSqlQuery()
        query.prepare("""
            SELECT 
                a.ID_anotacao,
                e.nome_especie AS "Espécie",
                a.frame AS "Frame",
                a.data_hora AS "Data/Hora",
                PRINTF('%.6f', a.latitude) AS "LAT.",
                PRINTF('%.6f', a.longitude) AS "LONG.",
                a.observacao AS "Observação"
            FROM anotacoes a
            LEFT JOIN especies e ON a.especie = e.ID_especie
            WHERE a.viagem = ?
            ORDER BY a.ID_anotacao DESC
        """)
        query.addBindValue(self.id_viagem)
    
        if query.exec():
            self.model_anotacoes.setQuery(query)
            # Oculta a coluna do ID interno e a coluna Observação (vazia) para a tabela ficar mais limpa
            self.tabela_anotacoes.setColumnHidden(0, True)
            self.tabela_anotacoes.setColumnHidden(3, True)

            # Preenchimento total e inteligente do espaço da tabela:
            header = self.tabela_anotacoes.horizontalHeader()
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)           # Espécie
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Frame
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Data/Hora
            header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)           # Latitude
            header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)           # Longitude
        else:
            print("Erro ao listar anotações:", query.lastError().text())

    def registrar_anotacao(self):
        self.parar()

        especie_selecionada = self.caixa_especie.currentText().strip()
        if not especie_selecionada:
            QMessageBox.warning(self, "Erro", "Selecione ou cadastre uma espécie antes de registrar a anotação!")
            return

        id_especie = db.pesquisar_especie_por_nome(especie_selecionada)
        if id_especie is None:
            QMessageBox.warning(self, "Erro", f"A espécie '{especie_selecionada}' não foi encontrada no banco!")
            return

        tempo_ms = self.player.position()
        frame_atual = round((tempo_ms / 1000) * self.fps)

        # Valores padrão de fallback
        latitude = 0.0
        longitude = 0.0
        data_hora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        observacao = self.campo_observacao.text()
        # Executa OCR no frame atual do vídeo
        if self.caminho_video:
            metadados = extrair_metadados_frame_video(self.caminho_video, tempo_ms)
            if metadados:
                if metadados.get("latitude") is not None:
                    latitude = metadados["latitude"]
                if metadados.get("longitude") is not None:
                    longitude = metadados["longitude"]
                if metadados.get("data_hora"):
                    data_hora = metadados["data_hora"]

        print(f"Salvando anotação: Viagem={self.id_viagem}, Frame={frame_atual}, DataHora={data_hora}, Lat={latitude}, Lon={longitude}, Espécie={id_especie}")
        try:
            db.inserir_anotacao(self.id_viagem, frame_atual, data_hora, latitude, longitude, id_especie, observacao)
        except RuntimeError as erro:
            QMessageBox.critical(self, "Erro ao Salvar", str(erro))
            return

        self.atualizar_tabela_anotacao()
        self.campo_observacao.clear()

  

    def atualizar_lista_especies(self):
        especies = db.pesquisar_especies()
        self.caixa_especie.clear() 
        if especies:
            self.caixa_especie.addItems(especies)
    
    def gerenciar_especie(self):
        dialogo = JanelaGerenciarEspecies()
        if not dialogo.exec():
            self.atualizar_lista_especies()
            self.atualizar_tabela_anotacao() #Caso o usuário exclua espécies com anotações presentes
            return


    def carregar_video(self, caminho_video: str, id_viagem: int, frames_deteccoes: list[int] | None = None, ):
        """Carrega o vídeo processado e extrai o FPS correto."""
        self.id_viagem = id_viagem 
        self.caminho_video = str(caminho_video)
        print(f"ID viagem inicial {self.id_viagem}")
        self.frames_deteccoes = sorted(frames_deteccoes or [])

        # Extrai FPS usando OpenCV
        cap = cv2.VideoCapture(str(caminho_video))
        if cap.isOpened():
            video_fps = cap.get(cv2.CAP_PROP_FPS)
            self.fps = float(video_fps) if video_fps > 0 else 30.0
            cap.release()
        else:
            self.fps = 30.0

        self.player.setSource(QUrl.fromLocalFile(str(caminho_video)))
        self.player.setPosition(0)
        self.botao_play_pause.setText("▶️ Play")
        self.atualizar_tabela_anotacao()

    def liberar_video(self):
        """Para a reprodução e descarrega completamente o arquivo de vídeo da memória."""
        self.player.stop()
        self.player.setSource(QUrl())
        self.id_viagem = None
        self.caminho_video = None
        self.frames_deteccoes = []
        self.botao_play_pause.setText("▶️ Play")

    def _ao_clicar_voltar(self):
        self.parar()
        self.liberar_video()
        self.voltar_solicitado.emit()

    # --- Sincronização do Slider ---
    def _posicao_alterada(self, posicao: int):
        if not self.slider_posicao.isSliderDown():
            self.slider_posicao.setValue(posicao)
        self.label_tempo_atual.setText(formatar_tempo(posicao))

    def _duracao_alterada(self, duracao: int):
        self.slider_posicao.setRange(0, duracao)
        self.label_tempo_total.setText(formatar_tempo(duracao))

    def _slider_movido(self, posicao: int):
        self.player.setPosition(posicao)
        self.label_tempo_atual.setText(formatar_tempo(posicao))

    # --- Controles de Reprodução e Frames ---
    def parar(self):
            self.player.pause()
            self.botao_play_pause.setText("▶️ Play")

    def play_pause(self):
        if self.player.isPlaying():
            self.player.pause()
            self.botao_play_pause.setText("▶️ Play")
        else:
            self.player.play()
            self.botao_play_pause.setText("⏸️ Pause")

    def prox_frame(self):
        ms_por_frame = int(1000 / self.fps)
        pos_atual = self.player.position()
        self.player.setPosition(pos_atual + ms_por_frame)

    def ultimo_frame(self):
        ms_por_frame = int(1000 / self.fps)
        pos_atual = self.player.position()
        self.player.setPosition(max(0, pos_atual - ms_por_frame))

    def prox_frame_deteccao(self):
        # Converte de numero de frames para ms pois QMediaPlayer não trabalha com número de frames ¯\_(ツ)_/¯
        pos_atual_ms = self.player.position()
        frame_atual = round((pos_atual_ms / 1000) * self.fps)

        proximo = min((f for f in self.frames_deteccoes if f > frame_atual), default=None)
        if proximo is None:
            QMessageBox.information(self, "Fim das detecções", "Não há mais detecções à frente neste vídeo!")
            return
        
        # Converte de volta para ms
        duracao_frame_ms = 1000 / self.fps
        pos_destino_ms = int((proximo * duracao_frame_ms) + (duracao_frame_ms / 2))
        self.player.setPosition(pos_destino_ms)

    def ultimo_frame_deteccao(self):
        # Converte de numero de frames para ms pois QMediaPlayer não trabalha com número de frames ¯\_(ツ)_/¯
        pos_atual_ms = self.player.position()
        frame_atual = round((pos_atual_ms / 1000) * self.fps)

        anterior = max((f for f in self.frames_deteccoes if f < frame_atual), default=None)
        if anterior is None:
            QMessageBox.information(self, "Início das detecções", "Não há detecções anteriores neste vídeo!")
            return

        # Converte de volta para ms
        duracao_frame_ms = 1000 / self.fps
        pos_destino_ms = int((anterior * duracao_frame_ms) + (duracao_frame_ms / 2))
        self.player.setPosition(pos_destino_ms)
