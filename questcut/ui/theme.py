"""Colours, style sheet and the small CPU/GPU badges."""
from PySide6.QtWidgets import QLabel

ACCENT = "#ffb648"
BG = "#1b1d23"
PANEL = "#23262e"
PANEL2 = "#2b2f39"
TEXT = "#e6e6e6"
MUTED = "#9aa0aa"

CLIP_COLORS = {
    "video": "#3d6fd8", "image": "#2aa198", "card": "#8e44ad", "audio": "#2e9e5b", "voice": "#c0662b",
    "hud": "#c98a1f", "spell": "#d0413a", "adjust": "#6c7a89", "frame": "#9a7a1a",
}

STYLE = f"""
QWidget {{ background: {BG}; color: {TEXT}; font-size: 13px; }}
QMainWindow::separator {{ background: #111; width: 4px; height: 4px; }}
QDockWidget::title {{ background: {PANEL2}; padding: 5px; font-weight: bold; }}
QToolBar {{ background: {PANEL}; border: none; spacing: 4px; padding: 3px; }}
QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 4px 7px; }}
QToolButton:hover {{ background: {PANEL2}; border-color: #3a3f4b; }}
QToolButton:checked {{ background: #3a3f4b; }}
QPushButton {{ background: {PANEL2}; border: 1px solid #3a3f4b; border-radius: 6px; padding: 5px 10px; }}
QPushButton:hover {{ background: #353a46; }}
QPushButton:pressed {{ background: #2a2e37; }}
QPushButton#primary {{ background: {ACCENT}; color: #1b1d23; font-weight: bold; border: none; }}
QPushButton#primary:hover {{ background: #ffc768; }}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: #15171c; border: 1px solid #3a3f4b; border-radius: 5px; padding: 3px 5px; }}
QComboBox QAbstractItemView {{ background: #15171c; selection-background-color: #3a3f4b; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: {PANEL}; padding: 6px 12px; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }}
QTabBar::tab:selected {{ background: {PANEL2}; color: {ACCENT}; }}
QGroupBox {{ border: 1px solid #343843; border-radius: 8px; margin-top: 14px; padding: 8px 6px 6px 6px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {ACCENT}; font-weight: bold; }}
QListWidget, QTreeWidget {{ background: #15171c; border: 1px solid #2f333d; border-radius: 6px; }}
QListWidget::item:selected, QTreeWidget::item:selected {{ background: #3a3f4b; }}
QSlider::groove:horizontal {{ height: 4px; background: #3a3f4b; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {ACCENT}; width: 12px; margin: -5px 0; border-radius: 6px; }}
QScrollBar:vertical, QScrollBar:horizontal {{ background: #15171c; width: 10px; height: 10px; }}
QScrollBar::handle {{ background: #3a3f4b; border-radius: 5px; min-height: 20px; min-width: 20px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QStatusBar {{ background: {PANEL}; color: {MUTED}; }}
QMenu {{ background: {PANEL}; border: 1px solid #3a3f4b; }}
QMenu::item:selected {{ background: #3a3f4b; }}
QMenuBar {{ background: {PANEL}; }}
QMenuBar::item:selected {{ background: #3a3f4b; }}
QProgressBar {{ background: #15171c; border: 1px solid #3a3f4b; border-radius: 5px; text-align: center; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
QCheckBox::indicator {{ width: 15px; height: 15px; }}
QToolTip {{ background: #111; color: {TEXT}; border: 1px solid #444; padding: 4px; }}
"""

BADGES = {
    "cpu": ("CPU ✓", "#2e7d4f", "Runs fine on a normal laptop CPU."),
    "gpu_faster": ("GPU ⚡ faster export", "#9a6a12",
                   "Fine for preview on a CPU. Exporting with many of these is faster on a computer with a GPU."),
    "gpu_needed": ("Heavy — use GPU machine", "#9b2d2d",
                   "Slow on a normal CPU. Best done on the lab computer with the GPU."),
    "slow": ("Slow — runs in the background", "#7a3b8f",
             "CPU work that takes about as long as the clip (or longer) on a laptop. A machine with more CPU "
             "cores finishes sooner. You can keep editing meanwhile."),
}


def badge(kind: str) -> QLabel:
    text, color, tip = BADGES.get(kind, BADGES["cpu"])
    lab = QLabel(text)
    lab.setToolTip(tip)
    lab.setStyleSheet(f"background:{color}; color:white; border-radius:8px; padding:1px 7px; font-size:11px;")
    return lab


def fmt_time(t: float, fps: float = 30.0) -> str:
    t = max(0.0, t)
    m = int(t // 60)
    s = int(t % 60)
    f = int(round((t - int(t)) * fps)) % int(fps)
    return f"{m:02d}:{s:02d}.{f:02d}"
