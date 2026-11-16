from PyQt6.QtWidgets import (  # type: ignore
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLineEdit,
    QDateEdit,
    QDialogButtonBox,
    QPushButton,
    QFileDialog,
    QLabel,
    QSlider
)

from PyQt6.QtCore import Qt,QDate, QLocale  # type: ignore
from database.banco_dados import DadosViagem


class JanelaCadastroEdicao(QDialog):
    def __init__(self,data_padrao: QDate | None = None,local_padrao: str = "",titulo_janela: str = "Registrar/Editar viagem",caminho_padrao: str = "",):
        super().__init__()
        self.setWindowTitle(titulo_janela)
        self.resize(600, 300)

        data_padrao = data_padrao if data_padrao and data_padrao.isValid() else QDate.currentDate()

        layout_principal = QVBoxLayout()
        layout_formulario = QFormLayout()

        # Localização
        self.campo_localizacao = QLineEdit(local_padrao)
        # Data
        self.campo_data = QDateEdit(data_padrao)
        #   Formatar para o formato correto
        self.campo_data.setLocale(QLocale(QLocale.Language.Portuguese, QLocale.Country.Brazil))
        self.campo_data.setDisplayFormat("ddd, dd 'de' MMM 'de' yyyy")
        self.campo_data.setCalendarPopup(True)

        # Seleção do vídeo
        self.layout_arquivo = QHBoxLayout()
        texto_arquivo = caminho_padrao if caminho_padrao else ""
        self.campo_arquivo = QLineEdit(texto_arquivo)
        self.campo_arquivo.setPlaceholderText("Nenhum arquivo selecionado...")
        botao_procurar = QPushButton("Adicionar vídeo...")
        botao_procurar.clicked.connect(self.abrir_dialogo_arquivo)
        self.layout_arquivo.addWidget(self.campo_arquivo)
        self.layout_arquivo.addWidget(botao_procurar)

        layout_formulario.addRow("Localização:", self.campo_localizacao)
        layout_formulario.addRow("Data da viagem:", self.campo_data)
        layout_formulario.addRow("Caminho do arquivo:", self.layout_arquivo)

        # Botões Ok / Cancelar
        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)

        layout_principal.addLayout(layout_formulario)
        layout_principal.addWidget(botoes)
        self.setLayout(layout_principal)

    def get_data(self) -> DadosViagem:
        return DadosViagem(
            localizacao=self.campo_localizacao.text().strip(),
            data_viagem=self.campo_data.date().toString("yyyy-MM-dd"),
            caminho_video=self.campo_arquivo.text().strip(),
        )

    def abrir_dialogo_arquivo(self) -> str:
        caminho, _ = QFileDialog.getOpenFileName(
            self,
            "Selecione o vídeo",
            "",
            "Vídeos (*.mp4 *.avi *.mkv *.mov);;Todos os arquivos (*)",
        )
        if caminho:
            self.campo_arquivo.setText(caminho)
        return caminho


class JanelaCadastroEspecie(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cadastrar espécie")
        self.resize(600, 300)

        layout_principal = QVBoxLayout()
        layout_formulario = QFormLayout()

        self.campo_nome_especie = QLineEdit()
        layout_formulario.addRow("Nome da espécie:", self.campo_nome_especie)
        # Botões Ok / Cancelar
        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)

        layout_principal.addLayout(layout_formulario)
        layout_principal.addWidget(botoes)
        self.setLayout(layout_principal)

    def get_data(self) -> str:
        return self.campo_nome_especie.text()

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, 
    QLineEdit, QPushButton, QMessageBox
)
import database.banco_dados as db

class JanelaGerenciarEspecies(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gerenciar Espécies")
        self.resize(350, 400)

        layout = QVBoxLayout(self)

        # Lista de espécies
        self.lista = QListWidget()
        layout.addWidget(self.lista)

        # Linha para cadastrar nova espécie
        layout_novo = QHBoxLayout()
        self.campo_nova = QLineEdit()
        self.campo_nova.setPlaceholderText("Nova espécie...")
        botao_adicionar = QPushButton("Adicionar")
        botao_adicionar.clicked.connect(self._adicionar)
        layout_novo.addWidget(self.campo_nova)
        layout_novo.addWidget(botao_adicionar)
        layout.addLayout(layout_novo)

        # Botão para excluir selecionada
        self.botao_excluir = QPushButton("Excluir Espécie Selecionada")
        self.botao_excluir.clicked.connect(self._excluir)
        layout.addWidget(self.botao_excluir)

        self._carregar_lista()

    def _carregar_lista(self):
        self.lista.clear()
        especies = db.pesquisar_especies()
        for esp in especies:
            self.lista.addItem(esp)

    def _adicionar(self):
        nome = self.campo_nova.text().strip()
        if not nome:
            return
        try:
            db.inserir_especie(nome)
            self.campo_nova.clear()
            self._carregar_lista()
        except RuntimeError as e:
            QMessageBox.critical(self, "Erro", str(e))

    def _excluir(self):
        item = self.lista.currentItem()
        if not item:
            QMessageBox.information(self, "Aviso", "Selecione uma espécie para excluir.")
            return

        
        nome_especie = item.text()
        id_especie = db.pesquisar_especie_por_nome(nome_especie)

        em_uso = db.especie_em_uso(id_especie)

        if em_uso:
            resp = QMessageBox.question(
                self, "Alerta",
                f"A espécie'{nome_especie}' possui anotações regisradas. Deletar essa espécie excluirá todas as anotações associadas a ela (isso não pode ser desfeito). Deseja excluir mesmo assim?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
            if resp != QMessageBox.StandardButton.Yes:
                return
        # Confirmação do usuário
        else:
            resp = QMessageBox.question(
                self, "Confirmar exclusão",
                f"Tem certeza que deseja excluir a espécie '{nome_especie}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if resp != QMessageBox.StandardButton.Yes:
                return

        try:
            db.deletar_especie(id_especie)
            self._carregar_lista()
        except RuntimeError as e:
            QMessageBox.critical(self, "Erro ao excluir", str(e))

class DialogoIniciarAnalise(QDialog):
    def __init__(self, parent = None):
        super().__init__(parent)
        self.setWindowTitle("Iniciar Análise")
        self.resize(420, 180)
        layout_principal = QVBoxLayout()
        layout_slider = QHBoxLayout()
        layout_botoes = QHBoxLayout()
        label = QLabel("Insira a confiança que o modelo deve possuir para marcar um peixe.\nValores mais altos diminuem os falsos positivos, mas podem fazer com que o modelo deixe alguns peixes não marcados ")
        label.setWordWrap(True)
        self.valor_slider = QLabel("25%")
        self.setLayout(layout_principal)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(5, 95)
        self.slider.setValue(25)
        self.slider.valueChanged.connect(self.atualiza_label)

        layout_slider.addWidget(self.slider)
        layout_slider.addWidget(self.valor_slider)

        layout_principal.addWidget(label)
        layout_principal.addLayout(layout_slider)

        botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout_principal.addWidget(botoes)

    def atualiza_label(self, valor):
        self.valor_slider.setText(f"{valor}%")

    def confianca(self):
        return self.slider.value()/100

        
