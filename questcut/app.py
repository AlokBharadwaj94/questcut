"""Start QuestCut."""
import os
import sys


def main():
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    from .ui.main_window import MainWindow
    from .ui.theme import STYLE

    QApplication.setApplicationName("QuestCut")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    f = QFont()
    f.setPointSize(10 if sys.platform != "darwin" else 13)
    app.setFont(f)
    w = MainWindow()
    w.show()
    # open a project given on the command line (or by double-clicking a .questcut file)
    args = [a for a in sys.argv[1:] if a.endswith(".questcut") and os.path.exists(a)]
    if args:
        w.open_project(os.path.abspath(args[0]))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
