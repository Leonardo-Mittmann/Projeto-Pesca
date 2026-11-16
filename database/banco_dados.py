from dataclasses import dataclass
from pathlib import Path
from PyQt6.QtSql import QSqlDatabase, QSqlQuery  # type: ignore


# Caminho padrão apontando para a raiz do projeto
DIRETORIO_RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_BANCO_PADRAO = str(DIRETORIO_RAIZ / "banco.db")


@dataclass
class DadosViagem:
    localizacao: str
    data_viagem: str
    caminho_video: str


def conectar(caminho_banco: str = CAMINHO_BANCO_PADRAO) -> QSqlDatabase:
    """Conecta ao banco SQLite e inicializa o esquema de tabelas e índices."""
    db = QSqlDatabase.addDatabase("QSQLITE")
    db.setDatabaseName(caminho_banco)

    if not db.open():
        raise RuntimeError(f"Não foi possível abrir o banco: {db.lastError().text()}")

    # Ativa suporte a chaves estrangeiras no SQLite
    query_pragma = QSqlQuery(db)
    query_pragma.exec("PRAGMA foreign_keys = ON;")

    # Tabela de viagens
    query_viagens = QSqlQuery(db)
    if not query_viagens.exec(
        """
        CREATE TABLE IF NOT EXISTS viagens (
            ID_viagem INTEGER PRIMARY KEY AUTOINCREMENT,
            data_viagem TEXT NOT NULL,
            localizacao TEXT NOT NULL,
            caminho_video TEXT,
            processado INTEGER DEFAULT 0  -- 0 = Pendente, 1 = Processado
        )
        """
    ):
        raise RuntimeError(f"Erro ao criar tabela 'viagens': {query_viagens.lastError().text()}")

    # Tabela de detecções 
    query_deteccoes = QSqlQuery(db)
    if not query_deteccoes.exec(
        """
        CREATE TABLE IF NOT EXISTS deteccoes (
            ID_deteccao INTEGER PRIMARY KEY AUTOINCREMENT,
            frame INTEGER NOT NULL,
            viagem_deteccao INTEGER NOT NULL,
            FOREIGN KEY (viagem_deteccao) REFERENCES viagens(ID_viagem) ON DELETE CASCADE
        )
        """
    ):
        raise RuntimeError(f"Erro ao criar tabela 'deteccoes': {query_deteccoes.lastError().text()}")

    # Índice para busca rápida de frames por viagem
    query_indice = QSqlQuery(db)
    query_indice.exec("CREATE INDEX IF NOT EXISTS idx_deteccoes_viagem ON deteccoes(viagem_deteccao, frame);")

    # Tabela de anotações 
    query_anotacoes = QSqlQuery(db)
    if not query_anotacoes.exec(
        """
        CREATE TABLE IF NOT EXISTS anotacoes (
            ID_anotacao INTEGER PRIMARY KEY AUTOINCREMENT,
            viagem INTEGER NOT NULL,
            frame INTEGER NOT NULL,
            data_hora TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            especie TEXT NOT NULL,
            observacao TEXT,
            FOREIGN KEY (especie) REFERENCES especies(ID_especie) ON DELETE CASCADE,
            FOREIGN KEY (viagem) REFERENCES viagens(ID_viagem) ON DELETE CASCADE
        )
        """
    ):
        raise RuntimeError(f"Erro ao criar tabela 'anotacoes': {query_anotacoes.lastError().text()}")

    # Migração retroativa caso a coluna tempo_video ainda exista
    query_check = QSqlQuery(db)
    if query_check.exec("PRAGMA table_info(anotacoes)"):
        colunas = []
        while query_check.next():
            colunas.append(query_check.value(1))
        if "tempo_video" in colunas and "frame" not in colunas:
            query_check.exec("ALTER TABLE anotacoes RENAME COLUMN tempo_video TO frame")

    # Tabela de especies 
    query_especies = QSqlQuery(db)
    if not query_especies.exec(
        """
        CREATE TABLE IF NOT EXISTS especies (
            ID_especie INTEGER PRIMARY KEY AUTOINCREMENT,
            nome_especie TEXT NOT NULL

        )
        """
    ):
        raise RuntimeError(f"Erro ao criar tabela 'especies': {query_especies.lastError().text()}")

    return db


# -------- OPERAÇÕES DE VIAGEM --------
def inserir_viagem(local: str, data_iso: str, caminho_video: str = "") -> None:
    query = QSqlQuery()
    query.prepare("INSERT INTO viagens (localizacao, data_viagem, caminho_video) VALUES (?, ?, ?)")
    query.addBindValue(local)
    query.addBindValue(data_iso)
    query.addBindValue(caminho_video)
    if not query.exec():
        raise RuntimeError(query.lastError().text())


def atualizar_viagem(id_viagem: int, local: str, data_iso: str, caminho_video: str = "") -> None:
    query = QSqlQuery()
    query.prepare("UPDATE viagens SET data_viagem = ?, localizacao = ?, caminho_video = ? WHERE ID_viagem = ?")
    query.addBindValue(data_iso)
    query.addBindValue(local)
    query.addBindValue(caminho_video)
    query.addBindValue(id_viagem)
    if not query.exec():
        raise RuntimeError(query.lastError().text())


def deletar_viagem(id_viagem: int) -> None:
    query = QSqlQuery()
    query.prepare("DELETE FROM viagens WHERE ID_viagem = ?")
    query.addBindValue(id_viagem)
    if not query.exec():
        raise RuntimeError(query.lastError().text())

def marcar_viagem_processada(id_viagem: int, processado: bool = True) -> None:
    query = QSqlQuery()
    query.prepare("UPDATE viagens SET processado = ? WHERE ID_viagem = ?")
    query.addBindValue(1 if processado else 0)
    query.addBindValue(id_viagem)
    if not query.exec():
        raise RuntimeError(query.lastError().text())
# -------- OPERAÇÕES DE DETECÇÃO --------
def inserir_deteccao(frame: int, viagem_deteccao: int) -> None:
    query = QSqlQuery()
    query.prepare("INSERT INTO deteccoes (frame, viagem_deteccao) VALUES (?, ?)")
    query.addBindValue(frame)
    query.addBindValue(viagem_deteccao)
    if not query.exec():
        raise RuntimeError(query.lastError().text())


def inserir_deteccoes_em_lote(frames: list[int], viagem_deteccao: int) -> None:
    """Insere múltiplos frames detectados dentro de uma única transação rápida."""
    if not frames:
        return

    db = QSqlDatabase.database()
    db.transaction()
    query = QSqlQuery()
    query.prepare("INSERT INTO deteccoes (frame, viagem_deteccao) VALUES (?, ?)")

    for frame in frames:
        query.addBindValue(frame)
        query.addBindValue(viagem_deteccao)
        if not query.exec():
            db.rollback()
            raise RuntimeError(query.lastError().text())

    db.commit()


def atualizar_deteccao(id_deteccao: int, frame: int, viagem_deteccao: int) -> None:
    query = QSqlQuery()
    query.prepare("UPDATE deteccoes SET frame = ?, viagem_deteccao = ? WHERE ID_deteccao = ?")
    query.addBindValue(frame)
    query.addBindValue(viagem_deteccao)
    query.addBindValue(id_deteccao)
    if not query.exec():
        raise RuntimeError(query.lastError().text())


def deletar_deteccao(id_deteccao: int) -> None:
    query = QSqlQuery()
    query.prepare("DELETE FROM deteccoes WHERE ID_deteccao = ?")
    query.addBindValue(id_deteccao)
    if not query.exec():
        raise RuntimeError(query.lastError().text())


def pesquisar_deteccoes(id_viagem: int) -> list[int]:
    """Retorna os frames únicos onde houve detecção para uma viagem, ordenados crescentemente."""
    query = QSqlQuery()
    query.prepare("SELECT DISTINCT frame FROM deteccoes WHERE viagem_deteccao = ? ORDER BY frame ASC")
    query.addBindValue(id_viagem)
    if not query.exec():
        raise RuntimeError(query.lastError().text())

    lista_frames: list[int] = []
    while query.next():
        lista_frames.append(query.value(0))

    return lista_frames
# -------- OPERAÇÕES DE ESPÉCIES --------
def inserir_especie(nome_especie: str) -> None:
    query = QSqlQuery()
    print(f"Preparando {nome_especie}")
    query.prepare("INSERT INTO especies (nome_especie) VALUES (?)")
    query.addBindValue(nome_especie)
    if not query.exec():
        raise RuntimeError(query.lastError().text())
    print("Retornando!")


def atualizar_especie(id_especie: int, nome_especie: str) -> None:
    query = QSqlQuery()
    query.prepare("UPDATE especies SET nome_especie = ? WHERE ID_especie = ?")
    query.addBindValue(nome_especie)
    query.addBindValue(id_especie)
    if not query.exec():
        raise RuntimeError(query.lastError().text())


def deletar_especie(id_especie: int) -> None:
    query = QSqlQuery()
    query.prepare("DELETE FROM especies WHERE ID_especie = ?")
    query.addBindValue(id_especie)
    if not query.exec():
        raise RuntimeError(query.lastError().text())

def pesquisar_especies() -> list:
    """Retorna todas as espécies cadastradas"""
    query = QSqlQuery()
    query.prepare("SELECT nome_especie FROM especies")
    if not query.exec():
        raise RuntimeError(query.lastError().text())
    resultados = []
    while query.next():
        nomes_especies = query.value(0)
        resultados.append(nomes_especies)
    return resultados

def pesquisar_especie_por_nome(nome_especie: str) -> int:
    """Retorna o id de o nome de uma espécie"""
    query = QSqlQuery()
    query.prepare("SELECT ID_especie FROM especies WHERE nome_especie = (?)")
    query.addBindValue(nome_especie)
    if not query.exec():
            raise RuntimeError(query.lastError().text())
    if query.next():
        return query.value(0)
    return None

# -------- OPERAÇÕES DE ANOTAÇÕES --------
def inserir_anotacao(
    viagem: int,
    frame: int,
    data_hora: str,
    latitude: float,
    longitude: float,
    especie: int,
    observacao: str = "",
) -> None:
    query = QSqlQuery()
    query.prepare(
        """
        INSERT INTO anotacoes (
            viagem, frame, data_hora, latitude, longitude, especie, observacao
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """
    )
    query.addBindValue(viagem)
    query.addBindValue(frame)
    query.addBindValue(data_hora)
    query.addBindValue(latitude)
    query.addBindValue(longitude)
    query.addBindValue(especie)
    query.addBindValue(observacao)
    if not query.exec():
        raise RuntimeError(query.lastError().text())


def atualizar_anotacao(
    id_anotacao: int,
    viagem: int,
    frame: int,
    data_hora: str,
    latitude: float,
    longitude: float,
    especie: int,
    observacao: str = "",
) -> None:
    query = QSqlQuery()
    query.prepare(
        """
        UPDATE anotacoes
        SET viagem = ?, frame = ?, data_hora = ?, latitude = ?, longitude = ?,
            especie = ?, observacao = ?
        WHERE ID_anotacao = ?
        """
    )
    query.addBindValue(viagem)
    query.addBindValue(frame)
    query.addBindValue(data_hora)
    query.addBindValue(latitude)
    query.addBindValue(longitude)
    query.addBindValue(especie)
    query.addBindValue(observacao)
    query.addBindValue(id_anotacao)
    if not query.exec():
        raise RuntimeError(query.lastError().text())

def obter_dados_exportacao(id_viagem: int) -> list[dict]:
    """Retorna todas as anotações de uma viagem em formato de dicionário pronto para CSV."""
    query = QSqlQuery()
    query.prepare("""
        SELECT 
            a.ID_anotacao,
            v.localizacao AS local_viagem,
            v.data_viagem,
            e.nome_especie,
            a.frame,
            a.data_hora,
            a.latitude,
            a.longitude,
            a.observacao
        FROM anotacoes a
        JOIN viagens v ON a.viagem = v.ID_viagem
        LEFT JOIN especies e ON a.especie = e.ID_especie
        WHERE a.viagem = ?
        ORDER BY a.frame ASC
    """)
    query.addBindValue(id_viagem)
    
    if not query.exec():
        raise RuntimeError(query.lastError().text())

    dados = []
    while query.next():
        dados.append({
            "ID_Anotacao": query.value("ID_anotacao"),
            "Localizacao": query.value("local_viagem"),
            "Data_Viagem": query.value("data_viagem"),
            "Especie": query.value("nome_especie"),
            "Frame": query.value("frame"),
            "Data_Hora_Frame": query.value("data_hora"),
            "Latitude": query.value("latitude"),
            "Longitude": query.value("longitude"),
            "Observacao": query.value("observacao") or ""
        })
    return dados


def deletar_anotacao(id_anotacao: int) -> None:
    query = QSqlQuery()
    query.prepare("DELETE FROM anotacoes WHERE ID_anotacao = ?")
    query.addBindValue(id_anotacao)
    if not query.exec():
        raise RuntimeError(query.lastError().text())


def pesquisar_anotacoes(id_viagem: int, frame: int | None = None) -> list:
    """Retorna todas as anotações de uma certa viagem (opcionalmente filtradas por frame)."""
    query = QSqlQuery()
    if frame is not None:
        query.prepare("SELECT * FROM anotacoes WHERE viagem = ? AND frame = ?")
        query.addBindValue(id_viagem)
        query.addBindValue(frame)
    else:
        query.prepare("SELECT * FROM anotacoes WHERE viagem = ? ORDER BY frame ASC")
        query.addBindValue(id_viagem)

    if not query.exec():
        raise RuntimeError(query.lastError().text())
    resultados = []
    while query.next():
        record = query.record()
        dado = [query.value(i) for i in range(record.count())]
        resultados.append(dado)
    return resultados

def especie_em_uso(id_especie: int) -> bool:
    query = QSqlQuery()
    query.prepare("SELECT 1 FROM anotacoes WHERE especie = ? LIMIT 1")
    query.addBindValue(id_especie)
    query.exec()
    return query.next()


def existe_video(id_viagem: int) -> bool:
    """Retorna true se uma viagem possuir video processado"""
    query = QSqlQuery()
    query.prepare("SELECT processado FROM viagens WHERE ID_viagem = ?")
    query.addBindValue(id_viagem)
    if not query.exec():
        raise RuntimeError(f"Erro ao consultar viagem: {query.lastError().text()}")

    if query.next():
        return bool(query.value(0))
    return False  # Viagem com esse ID não existe no banco
    
# Data ISO (yyyy-MM-dd) vem escondida na 2ª coluna para evitar problemas de
# parse de formato quando formos reabrir a data para edição.
QUERY_LISTAR_VIAGENS = """
    SELECT
        ID_viagem,
        data_viagem AS "Data ISO",
        strftime('%d/%m/%Y', data_viagem) AS "Data da Viagem",
        localizacao AS "Localização",
        CASE 
            WHEN processado = 1 THEN '✅ Concluído'
            ELSE '❌ Não realizada'
        END AS "Status da Análise",
        caminho_video AS "Caminho do Vídeo"
    FROM viagens
    ORDER BY data_viagem DESC
"""