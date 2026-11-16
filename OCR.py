import os
import re
import shutil
from pathlib import Path
import cv2
import numpy as np
import pytesseract


# No início do OCR.py:
diretorio_raiz = Path(__file__).resolve().parent
tesseract_local = diretorio_raiz / "bin" / "tesseract" / "tesseract.exe"
if tesseract_local.is_file():
    pytesseract.pytesseract.tesseract_cmd = str(tesseract_local)
elif not shutil.which("tesseract"):
    # Fallback caso encontre no sistema
    caminho_padrao = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.path.isfile(caminho_padrao):
        pytesseract.pytesseract.tesseract_cmd = caminho_padrao



def extrair_metadados_imagem(imagem_ou_caminho, mostrar_debug: bool = False) -> dict | None:
    """Extrai metadados (latitude, longitude, data_hora) a partir de uma imagem ou caminho de arquivo.

    Parâmetros:
        imagem_ou_caminho: Pode ser uma imagem OpenCV (np.ndarray) ou uma string/Path para o arquivo.
        mostrar_debug: Se True, exibe a imagem binarizada usando matplotlib (útil para testes manuais).
    """
    if isinstance(imagem_ou_caminho, (str, Path)):
        caminho_str = str(imagem_ou_caminho)
        if not os.path.exists(caminho_str):
            print(f"Erro: Arquivo não encontrado no caminho: {caminho_str}")
            return None
        img = cv2.imread(caminho_str)
        origem = caminho_str
    elif isinstance(imagem_ou_caminho, np.ndarray):
        img = imagem_ou_caminho
        origem = "frame_memoria"
    else:
        print("Erro: Tipo de entrada inválido para extração de metadados.")
        return None

    if img is None:
        print("Erro: Imagem inválida ou vazia.")
        return None

    # Recorte e processamento da faixa superior
    altura_corte = 25
    limite_largura = int(img.shape[1] * 0.60)

    roi = img[0:altura_corte, 0:limite_largura]
    roi_ampliada = cv2.resize(roi, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(roi_ampliada, cv2.COLOR_BGR2GRAY)
    _, binarizada = cv2.threshold(gray, 130, 255, cv2.THRESH_BINARY)
    imagem_final = cv2.bitwise_not(binarizada)

    if mostrar_debug:
        import matplotlib.pyplot as plt

        plt.imshow(imagem_final, cmap="gray")
        plt.title("ROI Binarizada para OCR")
        plt.show()

    # Extração de texto via Tesseract
    config_tesseract = r"--psm 7 -c tessedit_char_whitelist=0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-./:,()_ "
    texto = pytesseract.image_to_string(imagem_final, config=config_tesseract).strip()

    # Regex para Coordenadas
    texto_limpo = texto.replace(" ", "")
    coords = re.findall(r"-?\d{2}[\.,]\d+", texto_limpo)

    if len(coords) >= 2:
        try:
            lat = float(coords[-2].replace(",", "."))
            lon = float(coords[-1].replace(",", "."))
        except ValueError:
            lat, lon = None, None
    else:
        lat, lon = None, None

    # Regex para Data e Hora
    data_hora_match = re.search(r"(\d{4}-\d{2}-\d{2})\s*(\d{2})[:\s]+(\d{2})[:\s]+(\d{2})", texto)
    if data_hora_match:
        data = data_hora_match.group(1)
        hora = data_hora_match.group(2)
        minuto = data_hora_match.group(3)
        segundo = data_hora_match.group(4)
        data_hora = f"{data} {hora}:{minuto}:{segundo}"
    else:
        data_hora = None

    return {
        "origem": origem,
        "texto_bruto": texto,
        "latitude": lat,
        "longitude": lon,
        "data_hora": data_hora,
    }


def extrair_metadados_frame_video(caminho_video: str, pos_ms: int = 0) -> dict | None:
    """Abre o vídeo, localiza a posição em milissegundos indicada e extrai os metadados do frame."""
    if not caminho_video or not os.path.exists(caminho_video):
        print(f"Erro: Vídeo não encontrado em: {caminho_video}")
        return None

    cap = cv2.VideoCapture(str(caminho_video))
    if not cap.isOpened():
        print("Erro: Não foi possível abrir o arquivo de vídeo para leitura.")
        return None

    if pos_ms > 0:
        cap.set(cv2.CAP_PROP_POS_MSEC, pos_ms)

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        print(f"Erro: Falha ao capturar o frame do vídeo na posição {pos_ms}ms.")
        return None

    return extrair_metadados_imagem(frame)


if __name__ == "__main__":
    import sys

    caminho_teste = sys.argv[1] if len(sys.argv) > 1 else "video_teste.mp4"
    print(f"Testando extração no arquivo: {caminho_teste}")

    if caminho_teste.lower().endswith((".mp4", ".avi", ".mkv", ".mov")):
        resultado = extrair_metadados_frame_video(caminho_teste, pos_ms=1000)
    else:
        resultado = extrair_metadados_imagem(caminho_teste, mostrar_debug=True)

    if resultado:
        print("-" * 50)
        print(f"Texto bruto lido: {resultado['texto_bruto']}")
        print(f"Latitude:         {resultado['latitude']}")
        print(f"Longitude:        {resultado['longitude']}")
        print(f"Data e Hora:      {resultado['data_hora']}")
        print("-" * 50)
    else:
        print("Nenhum metadado extraído.")
