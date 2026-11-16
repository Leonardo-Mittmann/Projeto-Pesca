import sys
import time
from pathlib import Path
import csv
import shutil
from PyQt6.QtCore import QDate, Qt  # type: ignore
from PyQt6.QtSql import QSqlQueryModel  # type: ignore
from PyQt6.QtWidgets import (  # type: ignore
    QHeaderView,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
    QApplication,
    QFileDialog
)
import database.banco_dados as db
from views.dialogos import JanelaCadastroEdicao, DialogoIniciarAnalise
from views.player_widget import VideoPlayerWidget
from workers.yolo_worker import YoloWorker

COLUNA_ID_VIAGEM = 0
COLUNA_DATA_ISO = 1
COLUNA_DATA_FORMATADA = 2
COLUNA_LOCALIZACAO = 3
COLUNA_VIDEO_PROCESSADO = 4
COLUNA_CAMINHO = 5


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Aplicativo de Monitoramento de Pesca")
        self.resize(1200, 800)

        # Conexão com o banco
        try:
            self.db = db.conectar()
        except RuntimeError as erro:
            QMessageBox.critical(self, "Erro de Conexão", str(erro))
            sys.exit(1)

        self.pilha = QStackedWidget()
        self.setCentralWidget(self.pilha)

        # Tela 1: Listagem de Viagens
        self._iniciar_tela_listagem()

        # Tela 2: Player de Vídeo
        self.player_widget = VideoPlayerWidget()
        self.player_widget.voltar_solicitado.connect(self.voltar_interface_principal)
        self.pilha.addWidget(self.player_widget)

    def _iniciar_tela_listagem(self):
        self.tela_1 = QWidget()
        layout_tabela = QVBoxLayout(self.tela_1)

        self.model = QSqlQueryModel()
        self.tabela = QTableView()
        self.tabela.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabela.customContextMenuRequested.connect(self.menu_contexto)
        self.tabela.setAlternatingRowColors(True)
        self.tabela.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.tabela.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabela.clicked.connect(self.abrir_interface_video)

        botao_adicionar = QPushButton(" Adicionar nova viagem...")
        botao_adicionar.clicked.connect(self.adicionar_viagem)

        layout_tabela.addWidget(botao_adicionar)
        layout_tabela.addWidget(self.tabela)

        self.atualiza_tabela()
        self.pilha.addWidget(self.tela_1)

    def voltar_interface_principal(self):
        self.pilha.setCurrentIndex(0)

    def atualiza_tabela(self):
        self.model.setQuery(db.QUERY_LISTAR_VIAGENS, self.db)
        if self.model.lastError().isValid():
            QMessageBox.warning(
                self,
                "Erro na Consulta",
                f"Falha ao carregar os dados:\n{self.model.lastError().text()}",
            )
            return

        self.tabela.setModel(self.model)
        self.tabela.setColumnHidden(COLUNA_ID_VIAGEM, True)
        self.tabela.setColumnHidden(COLUNA_DATA_ISO, True)

    def abrir_interface_video(self, index):
        id_viagem = index.siblingAtColumn(COLUNA_ID_VIAGEM).data()
        caminho_video = index.siblingAtColumn(COLUNA_CAMINHO).data()
        print("ID-CAMINHO:")
        print(id_viagem)
        print(caminho_video)
        if not caminho_video or not Path(caminho_video).is_file():
            QMessageBox.warning(
                self,
                "Vídeo não encontrado",
                f"O arquivo de vídeo original não foi encontrado:\n{caminho_video}",
            )
            return

        # Caminho onde os vídeos processados pelo YOLO são salvos
        pasta_processada = Path(f"runs/detect/videos_processados/{id_viagem}")
        caminho_video_processado = pasta_processada / f"{Path(caminho_video).name}"
        caminho_video_processado = caminho_video_processado.with_suffix(".avi")

        # Se o vídeo processado não existir, pergunta se deseja rodar o YOLO
        if not caminho_video_processado.is_file():
            resposta = QMessageBox.question(
                self,
                "Executar Análise",
                "Nenhuma análise foi encontrada para essa viagem.\nDeseja processar o vídeo com a YOLO agora?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if resposta == QMessageBox.StandardButton.No:
                return

            dialogo_confianca = DialogoIniciarAnalise()
            if dialogo_confianca.exec():
                confianca = dialogo_confianca.confianca()
            else:
                return
            

            self._iniciar_analise_yolo(caminho_video, id_viagem, confianca)
            return

        # Vídeo já processado existente
        frames_deteccoes = db.pesquisar_deteccoes(id_viagem)
        self.player_widget.carregar_video(str(caminho_video_processado),id_viagem, frames_deteccoes)
        self.pilha.setCurrentIndex(1)

    def _iniciar_analise_yolo(self, caminho_video: str, id_viagem: int, confianca_selecionada: float):
        """Dispara a inferência em background sem travar a interface gráfica."""
        progresso_dialog = QProgressDialog(
            "Processando vídeo com YOLO... Por favor, aguarde.",
            "Cancelar",
            0,
            100,
            self,
        )
        progresso_dialog.setWindowTitle("Análise em Andamento")
        progresso_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progresso_dialog.setAutoClose(True)
        progresso_dialog.setValue(0)

        worker = YoloWorker(caminho_video=caminho_video, id_viagem=id_viagem, parent=self, confianca=confianca_selecionada)

        def atualizar_progresso(frame_atual: int, total_frames: int):
            if total_frames > 0:
                progresso_dialog.setMaximum(total_frames)
                progresso_dialog.setValue(frame_atual)
                progresso_dialog.setLabelText(
                    f"Analisando frame {frame_atual} de {total_frames}..."
                )

        def on_concluido(caminho_processado: str, frames_com_deteccao: list):
            progresso_dialog.close()
            try:
                # Salva as detecções no banco em lote
                db.inserir_deteccoes_em_lote(frames_com_deteccao, id_viagem)
            except RuntimeError as err:
                QMessageBox.warning(self, "Aviso", f"Vídeo analisado, mas erro ao salvar detecções:\n{err}")

            QMessageBox.information(
                self,
                "Concluído",
                f"Análise concluída com sucesso!\nDetecções encontradas em {len(frames_com_deteccao)} frames.",
            )
            self.player_widget.carregar_video(caminho_processado,id_viagem, frames_com_deteccao)
            self.pilha.setCurrentIndex(1)
            db.marcar_viagem_processada(id_viagem, True)
            self.atualiza_tabela()

        def on_erro(msg: str):
            progresso_dialog.close()
            QMessageBox.critical(self, "Erro na Análise", f"Falha durante a inferência do YOLO:\n{msg}")

        worker.progresso.connect(atualizar_progresso)
        worker.concluido.connect(on_concluido)
        worker.erro.connect(on_erro)
        progresso_dialog.canceled.connect(worker.cancelar)

        progresso_dialog.show()
        worker.start()

    # --- Operações de Viagem (CRUD) ---
    def adicionar_viagem(self):
        dialogo = JanelaCadastroEdicao(titulo_janela="Registrar viagem")
        if not dialogo.exec():
            return

        nova_viagem = dialogo.get_data()
        if not nova_viagem.localizacao or not nova_viagem.data_viagem:
            QMessageBox.warning(self, "Aviso", "Preencha a localização e a data da viagem!")
            return

        try:
            db.inserir_viagem(nova_viagem.localizacao, nova_viagem.data_viagem, nova_viagem.caminho_video)
        except RuntimeError as erro:
            QMessageBox.critical(self, "Erro ao Salvar", str(erro))
            return

        self.atualiza_tabela()
    def deletar_video(self, id_viagem: int) -> bool:
        """Deleta a pasta de vídeo processado de uma viagem de forma segura."""
        try:
            id_viagem = int(id_viagem)
            if id_viagem <= 0:
                raise ValueError
        except (ValueError, TypeError):
            print(f"[Segurança] ID de viagem inválido fornecido: {id_viagem!r}")
            return False
        diretorio_raiz = Path(__file__).resolve().parent.parent
        pasta_base = (diretorio_raiz / "runs" / "detect" / "videos_processados").resolve()
        pasta_alvo = (pasta_base / str(id_viagem)).resolve()
        if not pasta_alvo.is_relative_to(pasta_base) or pasta_alvo == pasta_base:
            print(f"[Segurança] Tentativa de acesso fora da pasta permitida: {pasta_alvo}")
            return False
        if not pasta_alvo.is_dir():
            return True
        #Libera o arquivo no player caso seja este o vídeo carregado
        if self.player_widget.id_viagem == id_viagem:
            self.player_widget.liberar_video()
            # Dá um ciclo no event loop do Qt para fechar os handles da thread de áudio/vídeo
            QApplication.processEvents()
        # Tentativa de exclusão com retentativa rápida para o Windows
        for tentativa in range(5):  # Tenta até 5 vezes (~0.5s no total)
            try:
                shutil.rmtree(pasta_alvo)
                break  # Apagou com sucesso!
            except PermissionError:
                time.sleep(0.1)  # Aguarda 100ms para o Windows fechar o handle
                QApplication.processEvents()
            except Exception as e:
                print(f"[Erro] Falha ao apagar pasta {pasta_alvo}: {e}")
                return False
        else:
            print(f"[Erro] O vídeo em {pasta_alvo} ainda está travado pelo sistema após várias tentativas.")
            return False
        #Atualiza o status no banco e na interface
        db.marcar_viagem_processada(id_viagem, False)
        self.atualiza_tabela()
        return True

    def editar_viagem(self, indice_registro):
        id_viagem = indice_registro.siblingAtColumn(COLUNA_ID_VIAGEM).data()
        data_iso_atual = indice_registro.siblingAtColumn(COLUNA_DATA_ISO).data()
        local_atual = indice_registro.siblingAtColumn(COLUNA_LOCALIZACAO).data()
        caminho_atual = indice_registro.siblingAtColumn(COLUNA_CAMINHO).data()

        data_atual = QDate.fromString(data_iso_atual, "yyyy-MM-dd")
        janela = JanelaCadastroEdicao(
            data_padrao=data_atual,
            local_padrao=local_atual or "",
            caminho_padrao=caminho_atual or "",
            titulo_janela="Editar viagem",
        )

        if not janela.exec():
            return

        dados_editados = janela.get_data()
        if not dados_editados.localizacao:
            QMessageBox.warning(self, "Aviso", "A localização não pode ficar vazia!")
            return

        try:
            db.atualizar_viagem(
                id_viagem,
                dados_editados.localizacao,
                dados_editados.data_viagem,
                dados_editados.caminho_video,
            )
        except RuntimeError as erro:
            QMessageBox.critical(self, "Erro ao Atualizar", str(erro))
            return

        self.atualiza_tabela()

    def deletar_viagem(self, id_viagem):
        resposta = QMessageBox.question(
            self,
            "Confirmar Exclusão",
            "Tem certeza que deseja deletar essa viagem e todas as suas detecções?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if resposta == QMessageBox.StandardButton.No:
            return
        try:
            db.deletar_viagem(id_viagem)
        except RuntimeError as erro:
            QMessageBox.critical(self, "Erro ao Deletar", str(erro))
            return

        self.atualiza_tabela()
        self.deletar_video(id_viagem)

    def exportar_anotacoes_csv(self,id_viagem):
        try:
            linhas = db.obter_dados_exportacao(id_viagem)
        except RuntimeError as e:
            QMessageBox.critical(self, "Erro", f"Falha ao consultar banco: {e}")
            return
        if not linhas:
            QMessageBox.information(self, "Aviso", "Esta viagem ainda não possui anotações para exportar.")
            return
        sugestao_nome = f"anotacoes_viagem_{id_viagem}.csv"
        caminho_arquivo, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar Anotações",
            sugestao_nome,
            "Arquivo CSV (*.csv);;Todos os Arquivos (*)"
        )
        if not caminho_arquivo:
            return  # Usuário cancelou
        # Gravação do arquivo CSV
        try:
            with open(caminho_arquivo, mode="w", newline="", encoding="utf-8-sig") as arquivo:
                campos = [
                    "ID_Anotacao", "Localizacao", "Data_Viagem", "Especie", 
                    "Frame", "Data_Hora_Frame", "Latitude", "Longitude", "Observacao"
                ]
                escritor = csv.DictWriter(arquivo, fieldnames=campos, delimiter=";")
                escritor.writeheader()
                escritor.writerows(linhas)
            QMessageBox.information(
                self,
                "Sucesso",
                f"Exportação concluída!\n{len(linhas)} anotações salvas em:\n{caminho_arquivo}"
            )
        except Exception as erro:
            QMessageBox.critical(self, "Erro de Gravação", f"Não foi possível salvar o arquivo:\n{erro}")
            


    def menu_contexto(self, pos):
        indice_clicado = self.tabela.indexAt(pos)
        if not indice_clicado.isValid():
            return
        id_viagem = indice_clicado.siblingAtColumn(COLUNA_ID_VIAGEM).data()
       

        status_texto = str(indice_clicado.siblingAtColumn(COLUNA_VIDEO_PROCESSADO).data() or "")
        if "Concluído" in status_texto:
            video_processado = True
        else:
            video_processado = False


        menu = QMenu()
        acao_editar = menu.addAction("Editar Viagem")
        acao_deletar = menu.addAction("Deletar Viagem")
        if video_processado:
            acao_deletar_video = menu.addAction("Deletar vídeo processado")
        acao_exportar = menu.addAction("Exportar anotações para .csv")


        acao_escolhida = menu.exec(self.tabela.viewport().mapToGlobal(pos))

        if acao_escolhida == acao_deletar:
            id_viagem = indice_clicado.siblingAtColumn(COLUNA_ID_VIAGEM).data()
            self.deletar_viagem(id_viagem)
        if acao_escolhida == acao_editar:
            self.editar_viagem(indice_clicado)
        if video_processado:
            if acao_escolhida == acao_deletar_video:
                resposta = QMessageBox.question(
                            self,
                            "Confirmar Exclusão",
                            "Tem certeza que deseja deletar o vídeo procesado? (Isso não afetará o vídeo original).",
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        )
                if resposta == QMessageBox.StandardButton.No:
                    return
                self.deletar_video(id_viagem)
        if acao_escolhida == acao_exportar:
            id_viagem = indice_clicado.siblingAtColumn(COLUNA_ID_VIAGEM).data()
            self.exportar_anotacoes_csv(id_viagem)
