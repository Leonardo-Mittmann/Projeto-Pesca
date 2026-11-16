import sys
from PyQt6.QtWidgets import QApplication  # type: ignore
from qt_material import apply_stylesheet
from PyQt6.QtCore import QTranslator, QLocale, QLibraryInfo  # <-- Importar estes
from views.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    tradutor = QTranslator(app)
    caminho_traducoes = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if tradutor.load(QLocale(QLocale.Language.Portuguese, QLocale.Country.Brazil), "qtbase", "_", caminho_traducoes):
        app.installTranslator(tradutor)
    apply_stylesheet(app, theme="dark_blue.xml")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()