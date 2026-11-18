"""Dialogs: spell wizard, export, voice-over recorder, GPU information."""
from __future__ import annotations

import os
import threading
import time
import wave

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QWidget, QPlainTextEdit, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton,
                               QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QHeaderView)

from ..backend import ENCODER_LABELS, HW
from ..export import Exporter, ExportSettings
from ..hud import STYLE_LABELS
from .theme import ACCENT, badge, fmt_time

SPELL_COLORS = [("Fire (orange)", "#ff7a1a"), ("Ice (light blue)", "#6ad8ff"), ("Lightning (yellow)", "#fff35a"),
                ("Poison (green)", "#6aff5a"), ("Arcane (purple)", "#c06aff"), ("Holy (white-gold)", "#fff2b0"),
                ("Blood (red)", "#ff2a3a")]


class SpellDialog(QDialog):
    def __init__(self, mw, targets):
        super().__init__(mw)
        self.setWindowTitle("Spell / attack event")
        self.setMinimumWidth(460)
        v = QVBoxLayout(self)
        intro = QLabel("This places everything at the red playhead in one go: the spell name, the flying spell, "
                       "the sounds, the hit (flash + shake + damage number) and the target's health bar going down.")
        intro.setWordWrap(True)
        v.addWidget(intro)
        f = QFormLayout()
        v.addLayout(f)
        self.name = QLineEdit("FIREBALL!")
        f.addRow("Spell name", self.name)
        self.style = QComboBox()
        for k, lab in STYLE_LABELS.items():
            self.style.addItem(lab, k)
        self.style.setCurrentIndex(max(0, self.style.findData(mw.bin.default_style())))
        f.addRow("Look", self.style)
        self.color = QComboBox()
        for lab, c in SPELL_COLORS:
            self.color.addItem(lab, c)
        f.addRow("Colour", self.color)
        self.cast = QComboBox()
        for k, lab in (("spell_cast", "Magic sweep"), ("fireball", "Fireball roar"), ("ice_spell", "Ice crystals"),
                       ("lightning", "Lightning"), ("laser", "Laser"), ("", "No sound")):
            self.cast.addItem(lab, k)
        f.addRow("Cast sound", self.cast)
        self.hit = QComboBox()
        for k, lab in (("hit", "Hit"), ("critical_hit", "Critical hit"), ("explosion", "Explosion"),
                       ("damage", "Retro damage beep"), ("", "No sound")):
            self.hit.addItem(lab, k)
        f.addRow("Hit sound", self.hit)
        self.hit_time = QDoubleSpinBox()
        self.hit_time.setRange(0.2, 8)
        self.hit_time.setValue(1.1)
        self.hit_time.setSuffix(" s after the cast")
        f.addRow("Hit moment", self.hit_time)
        self.damage = QSpinBox()
        self.damage.setRange(0, 9999)
        self.damage.setValue(35)
        f.addRow("Damage", self.damage)
        self.target = QComboBox()
        self.target.addItem("(no health bar)", "")
        for cid, label in targets:
            self.target.addItem(label, cid)
        if targets:
            self.target.setCurrentIndex(1)
        f.addRow("Health bar that drops", self.target)
        self.shake = QDoubleSpinBox()
        self.shake.setRange(0, 1.5)
        self.shake.setSingleStep(0.1)
        self.shake.setValue(0.6)
        f.addRow("Screen shake", self.shake)
        self.flash = QDoubleSpinBox()
        self.flash.setRange(0, 1)
        self.flash.setSingleStep(0.1)
        self.flash.setValue(0.55)
        f.addRow("Screen flash", self.flash)
        if not targets:
            n = QLabel("Tip: add a health bar (HUD tab) or a name tag with a small bar over the monster first, "
                       "then its bar can drop automatically.")
            n.setWordWrap(True)
            n.setStyleSheet("color:#9aa0aa;")
            v.addWidget(n)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Create spell")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def values(self):
        return {"name": self.name.text(), "style": self.style.currentData(), "color": self.color.currentData(),
                "cast_sound": self.cast.currentData(), "hit_sound": self.hit.currentData(),
                "hit_time": self.hit_time.value(), "damage": self.damage.value(), "target": self.target.currentData(),
                "shake": self.shake.value(), "flash": self.flash.value()}


class ExportDialog(QDialog):
    def __init__(self, mw):
        super().__init__(mw)
        self.mw = mw
        self.setWindowTitle("Export movie")
        self.setMinimumWidth(560)
        self.exporter = None
        self.thread = None
        p = mw.project
        v = QVBoxLayout(self)
        f = QFormLayout()
        v.addLayout(f)
        row = QHBoxLayout()
        base = p.folder or os.path.expanduser("~")
        self.path = QLineEdit(os.path.join(base, (p.name or "movie").replace("/", "-") + ".mp4"))
        br = QPushButton("Choose…")
        br.clicked.connect(self._choose)
        row.addWidget(self.path, 1)
        row.addWidget(br)
        f.addRow("Save as", row)
        self.size = QComboBox()
        self.size.addItem(f"Same as movie ({p.width} × {p.height})", (p.width, p.height))
        if (p.width, p.height) != (1920, 1080):
            self.size.addItem("1920 × 1080 (Full HD)", (1920, 1080))
        self.size.addItem("1280 × 720 (smaller file)", (1280, 720))
        f.addRow("Picture size", self.size)
        self.quality = QComboBox()
        for k, lab in (("high", "High (for the big screen)"), ("medium", "Medium"), ("small", "Small file (email/chat)")):
            self.quality.addItem(lab, k)
        f.addRow("Quality", self.quality)
        self.encoder = QComboBox()
        self.encoder.addItem("Automatic (uses the GPU if this computer has one)", "auto")
        for e in HW.encoders:
            self.encoder.addItem(ENCODER_LABELS.get(e, e), e)
        f.addRow("Video encoder", self.encoder)
        self.gpu = QCheckBox("Use the NVIDIA GPU for filters and effects (CuPy)")
        self.gpu.setChecked(HW.cupy_ok)
        self.gpu.setEnabled(HW.cupy_ok)
        if not HW.cupy_ok:
            self.gpu.setToolTip("Not available on this computer. On the lab machine install CuPy (see README).")
        f.addRow("", self.gpu)
        self.test = QCheckBox("Quick test: only 10 seconds from the playhead")
        f.addRow("", self.test)
        hw = QLabel(HW.summary().replace("   |   ", "<br>"))
        hw.setStyleSheet("color:#9aa0aa;")
        v.addWidget(hw)
        compat = QLabel("The file is a standard MP4 (H.264 video + AAC sound). It plays on Mac (QuickTime, Keynote), "
                        "Windows (PowerPoint, Media Player), phones and projectors.")
        compat.setWordWrap(True)
        v.addWidget(compat)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        v.addWidget(self.bar)
        self.info = QLabel("")
        v.addWidget(self.info)
        row = QHBoxLayout()
        self.go = QPushButton("Export")
        self.go.setObjectName("primary")
        self.go.clicked.connect(self.start)
        self.cancel_btn = QPushButton("Close")
        self.cancel_btn.clicked.connect(self._cancel)
        row.addStretch(1)
        row.addWidget(self.cancel_btn)
        row.addWidget(self.go)
        v.addLayout(row)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)

    def _choose(self):
        fn, _ = QFileDialog.getSaveFileName(self, "Save movie as", self.path.text(), "MP4 video (*.mp4)")
        if fn:
            if not fn.lower().endswith(".mp4"):
                fn += ".mp4"
            self.path.setText(fn)

    def start(self):
        p = self.mw.project
        w, h = self.size.currentData()
        start, end = 0.0, -1.0
        if self.test.isChecked():
            start = self.mw.playhead
            end = start + 10.0
        s = ExportSettings(path=self.path.text(), width=w, height=h, fps=p.fps, quality=self.quality.currentData(),
                           encoder=self.encoder.currentData(), gpu_filters=self.gpu.isChecked(), start=start, end=end)
        self.exporter = Exporter(p, s)
        self.t0 = time.time()
        self.result = None

        def work():
            self.result = self.exporter.run()
        self.thread = threading.Thread(target=work, daemon=True)
        self.thread.start()
        self.go.setEnabled(False)
        self.cancel_btn.setText("Cancel")
        self.timer.start(250)

    def _poll(self):
        ex = self.exporter
        if ex is None:
            return
        self.bar.setValue(int(ex.progress * 1000))
        el = time.time() - self.t0
        txt = f"{ex.stage}…  {ex.done_frames}/{ex.total_frames} frames"
        if ex.done_frames > 10:
            fps = ex.done_frames / el
            left = (ex.total_frames - ex.done_frames) / max(0.1, fps)
            txt += f"   ·   {fps:.1f} frames/s   ·   about {int(left // 60)} min {int(left % 60)} s left"
        if ex.encoder:
            txt += f"\nEncoder: {ENCODER_LABELS.get(ex.encoder, ex.encoder)}   ·   Effects on: {ex.backend_name or '…'}"
        self.info.setText(txt)
        if not self.thread.is_alive():
            self.timer.stop()
            self.go.setEnabled(True)
            self.cancel_btn.setText("Close")
            if self.result:
                self.bar.setValue(1000)
                self.info.setText(f"Done in {int(el // 60)} min {int(el % 60)} s.\nSaved: {self.path.text()}")
                self.mw.status("Exported " + self.path.text())
                self.mw.reveal_file(self.path.text())
            elif ex.cancelled:
                self.info.setText("Cancelled.")
            else:
                QMessageBox.warning(self, "Export failed", ex.error or "Unknown error")

    def _cancel(self):
        if self.exporter is not None and self.thread is not None and self.thread.is_alive():
            self.exporter.cancel()
        else:
            self.accept()

    def closeEvent(self, ev):
        if self.exporter is not None and self.thread is not None and self.thread.is_alive():
            self.exporter.cancel()
        super().closeEvent(ev)


GPU_TABLE = [
    ("Cutting, trimming, moving clips", "cpu", "Instant on any computer."),
    ("Live preview while editing", "cpu", "Uses small 'proxy' copies of your videos so it stays smooth."),
    ("Sound: volume, fades, ducking, game sounds", "cpu", "Light work."),
    ("Syncing two cameras by sound", "cpu", "A few seconds per clip."),
    ("Transitions", "cpu", "Fine on a CPU."),
    ("HUD elements, cards, spell events", "cpu", "Drawn by Qt; fast. Many at once make export a bit slower."),
    ("Filters, looks, vignettes, touch-ups", "gpu_faster",
     "Preview is fine. Exporting is faster with an NVIDIA GPU + CuPy."),
    ("Steadying shaky GoPro footage", "slow",
     "Runs on the CPU (the GPU does not help this step). About real-time or slower; runs in the background."),
    ("Final export (video encoding)", "gpu_faster",
     "NVIDIA (NVENC), Apple (VideoToolbox) or Intel (QuickSync) chips encode several times faster."),
]


class GpuInfoDialog(QDialog):
    def __init__(self, mw):
        super().__init__(mw)
        self.setWindowTitle("What does the GPU speed up?")
        self.resize(760, 420)
        v = QVBoxLayout(self)
        lab = QLabel(f"<b>This computer:</b> {HW.summary()}")
        lab.setWordWrap(True)
        v.addWidget(lab)
        t = QTableWidget(len(GPU_TABLE), 3)
        t.setHorizontalHeaderLabels(["Task", "Needs", "Notes"])
        t.verticalHeader().setVisible(False)
        for i, (task, kind, note) in enumerate(GPU_TABLE):
            t.setItem(i, 0, QTableWidgetItem(task))
            t.setCellWidget(i, 1, badge(kind))
            t.setItem(i, 2, QTableWidgetItem(note))
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        t.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        t.setWordWrap(True)
        t.resizeRowsToContents()
        v.addWidget(t)
        tip = QLabel("Workflow: edit on your laptop or Mac. For the final export, copy the project folder to the lab "
                     "Linux machine, open it there and export — QuestCut finds the GPU automatically.")
        tip.setWordWrap(True)
        v.addWidget(tip)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)


class RecorderDialog(QDialog):
    """Record a voice-over with the computer's microphone."""

    def __init__(self, mw):
        super().__init__(mw)
        self.mw = mw
        self.setWindowTitle("Record voice-over")
        self.setMinimumWidth(460)
        self.chunks = []
        self.source = None
        self.io = None
        self.start_t = mw.playhead
        v = QVBoxLayout(self)
        v.addWidget(QLabel(f"Recording starts at <b>{fmt_time(self.start_t)}</b> (the red playhead)."))
        f = QFormLayout()
        v.addLayout(f)
        self.dev = QComboBox()
        try:
            from PySide6.QtMultimedia import QMediaDevices
            for d in QMediaDevices.audioInputs():
                self.dev.addItem(d.description(), d)
            dflt = QMediaDevices.defaultAudioInput()
            i = self.dev.findText(dflt.description())
            if i >= 0:
                self.dev.setCurrentIndex(i)
        except Exception as e:
            self.dev.addItem(f"(microphone not available: {e})", None)
        f.addRow("Microphone", self.dev)
        self.play_along = QCheckBox("Play the movie while I record (sound off, so it isn't recorded)")
        self.play_along.setChecked(True)
        f.addRow("", self.play_along)
        self.level = QProgressBar()
        self.level.setRange(0, 100)
        self.level.setTextVisible(False)
        f.addRow("Level", self.level)
        self.info = QLabel("Use headphones if you want to hear the movie.")
        self.info.setStyleSheet("color:#9aa0aa;")
        v.addWidget(self.info)
        row = QHBoxLayout()
        self.rec = QPushButton("● Record")
        self.rec.setObjectName("primary")
        self.rec.clicked.connect(self.toggle)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        row.addStretch(1)
        row.addWidget(close)
        row.addWidget(self.rec)
        v.addLayout(row)
        self.count = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.rate = 48000

    def toggle(self):
        if self.source is None and self.count == 0:
            self.count = 3
            self.rec.setText("3…")
            self.timer.start(1000)
        elif self.source is not None:
            self.stop()

    def _tick(self):
        if self.count > 0:
            self.count -= 1
            if self.count > 0:
                self.rec.setText(f"{self.count}…")
                return
            self.timer.stop()
            self._begin()

    def _begin(self):
        try:
            from PySide6.QtMultimedia import QAudioFormat, QAudioSource
            dev = self.dev.currentData()
            if dev is None:
                raise RuntimeError("no microphone")
            fmt = QAudioFormat()
            fmt.setSampleRate(48000)
            fmt.setChannelCount(1)
            fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
            if not dev.isFormatSupported(fmt):
                fmt = dev.preferredFormat()
                fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
            self.fmt = fmt
            self.rate = fmt.sampleRate()
            self.channels = fmt.channelCount()
            self.source = QAudioSource(dev, fmt, self)
            self.io = self.source.start()
            self.io.readyRead.connect(self._read)
        except Exception as e:
            QMessageBox.warning(self, "Microphone", f"Could not start the microphone:\n{e}\n\n"
                                "On a Mac, allow microphone access for Terminal/Python in System Settings → Privacy.")
            self.rec.setText("● Record")
            return
        self.rec.setText("■ Stop")
        self.info.setText("Recording… speak now.")
        self.mw.set_playhead(self.start_t)
        if self.play_along.isChecked():
            self.mw.play(mute=True)

    def _read(self):
        data = bytes(self.io.readAll())
        if not data:
            return
        self.chunks.append(data)
        a = np.frombuffer(data, dtype=np.int16)
        if len(a):
            self.level.setValue(int(min(100, np.sqrt(np.mean((a / 32768.0) ** 2)) * 400)))

    def stop(self):
        if self.source is not None:
            self._read()
            self.source.stop()
            self.source = None
        self.mw.stop_playback()
        raw = b"".join(self.chunks)
        self.chunks = []
        self.rec.setText("● Record")
        if len(raw) < self.rate // 2:
            self.info.setText("Nothing was recorded.")
            return
        path = self.mw.new_voice_path()
        with wave.open(path, "wb") as w:
            w.setnchannels(self.channels)
            w.setsampwidth(2)
            w.setframerate(self.rate)
            w.writeframes(raw)
        self.mw.add_voice_clip(path, self.start_t)
        secs = len(raw) / 2 / self.channels / self.rate
        self.info.setText(f"Saved {secs:.1f} s. It's on the voice-over track. Record again for another take.")
        self.start_t = self.mw.playhead

    def reject(self):
        if self.source is not None:
            self.stop()
        super().reject()


class BattleDialog(QDialog):
    """Creature battle start (Pokémon style)."""

    def __init__(self, mw):
        super().__init__(mw)
        self.setWindowTitle("Creature battle start")
        self.setMinimumWidth(460)
        v = QVBoxLayout(self)
        lab = QLabel("Places at the playhead: the battle-start transition and jingle, both HP boxes sliding in, "
                     "'A wild … appeared!', the FIGHT/BAG menu and battle music.")
        lab.setWordWrap(True)
        v.addWidget(lab)
        f = QFormLayout()
        v.addLayout(f)
        self.enemy = QLineEdit("Reviewer 2")
        self.enemy_level = QLineEdit("50")
        self.player = QLineEdit("PhD Student")
        self.player_level = QLineEdit("27")
        self.intro = QLineEdit("A wild {enemy} appeared!")
        self.wipe = QComboBox()
        for k, lab_ in (("spiral", "Spiral (wild battle)"), ("stripes", "Stripes"), ("blocks", "Blocks"),
                        ("bars", "Closing bars"), ("vs", "VS bands with names (trainer battle)")):
            self.wipe.addItem(lab_, k)
        self.length = QDoubleSpinBox()
        self.length.setRange(3, 600)
        self.length.setValue(20)
        self.length.setSuffix(" s")
        self.music = QCheckBox("Add battle music")
        self.music.setChecked(True)
        f.addRow("Opponent", self.enemy)
        f.addRow("Opponent level", self.enemy_level)
        f.addRow("Your fighter", self.player)
        f.addRow("Your level", self.player_level)
        f.addRow("First message", self.intro)
        f.addRow("Transition", self.wipe)
        f.addRow("Battle length", self.length)
        f.addRow("", self.music)
        tip = QLabel("Tip: film it from behind your fighter, with the opponent facing the camera.")
        tip.setStyleSheet("color:#9aa0aa;")
        v.addWidget(tip)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def values(self):
        return {"enemy": self.enemy.text(), "enemy_level": self.enemy_level.text(), "player": self.player.text(),
                "player_level": self.player_level.text(), "intro": self.intro.text(), "wipe": self.wipe.currentData(),
                "length": self.length.value(), "music": self.music.isChecked()}


def _spin(lo, hi, val, step=1.0, suffix="", dec=0):
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(dec)
    s.setSingleStep(step)
    s.setValue(val)
    if suffix:
        s.setSuffix(suffix)
    return s


class QuestTalkDialog(QDialog):
    """RuneScape-style quest conversation."""

    def __init__(self, mw):
        super().__init__(mw)
        self.setWindowTitle("Quest conversation (RuneScape style)")
        self.setMinimumWidth(520)
        v = QVBoxLayout(self)
        lab = QLabel("Places at the playhead: one chat box per NPC line (with blip sound), the 'Select an Option' "
                     "list where your answer lights up, your reply, and the red 'You have started a new quest' "
                     "message. Each box stays up long enough to read.")
        lab.setWordWrap(True)
        v.addWidget(lab)
        f = QFormLayout()
        v.addLayout(f)
        self.npc = QLineEdit("Professor Grid")
        self.player = QLineEdit("Alok")
        self.npc_lines = QPlainTextEdit("Ah, adventurer! Thank goodness you're here.\n"
                                        "Someone has stolen my cryo-EM grids. Without them, no structures!\n"
                                        "Could you get them back from the cold room?")
        self.npc_lines.setFixedHeight(90)
        self.options = QPlainTextEdit("Yes, I'll help you.\nWhat's in it for me?\nSorry, I'm busy.")
        self.options.setFixedHeight(70)
        self.pick = QComboBox()
        self.quest = QLineEdit("The Missing Grids")
        self.music = QCheckBox("Add the warm 'Quest giver' music under it")
        self.music.setChecked(True)
        self.options.textChanged.connect(self._fill_pick)
        self._fill_pick()
        f.addRow("NPC name", self.npc)
        f.addRow("Your name", self.player)
        f.addRow("NPC says (one box per line)", self.npc_lines)
        f.addRow("Answers to choose from", self.options)
        f.addRow("Answer you pick", self.pick)
        f.addRow("Quest name (blank = no message)", self.quest)
        f.addRow("", self.music)
        tip = QLabel("Afterwards: select an NPC box and use 'Face picture' in the right panel to grab the NPC's "
                     "face from the video.")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#9aa0aa;")
        v.addWidget(tip)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _fill_pick(self):
        cur = self.pick.currentIndex()
        self.pick.clear()
        for o in [o.strip() for o in self.options.toPlainText().splitlines() if o.strip()][:5]:
            self.pick.addItem(o)
        self.pick.setCurrentIndex(max(0, min(cur, self.pick.count() - 1)))

    def values(self):
        return {"npc": self.npc.text(), "player": self.player.text(), "npc_lines": self.npc_lines.toPlainText(),
                "options": self.options.toPlainText(), "pick": max(0, self.pick.currentIndex()),
                "quest": self.quest.text().strip(), "music": self.music.isChecked()}


class FightDialog(QDialog):
    """RuneScape-style fight."""

    def __init__(self, mw):
        super().__init__(mw)
        self.setWindowTitle("Fight (RuneScape style)")
        self.setMinimumWidth(500)
        v = QVBoxLayout(self)
        lab = QLabel("Places at the playhead: a small green/red health bar over each fighter, then turns of "
                     "attacks — red damage splats (blue 0 = miss) that sit on the bar and make it drop — with hit "
                     "sounds and XP drops for your hits. The opponent loses, you survive. Press OK again for a "
                     "different random fight.")
        lab.setWordWrap(True)
        v.addWidget(lab)
        f = QFormLayout()
        v.addLayout(f)
        self.player = QLineEdit("Alok")
        self.enemy = QLineEdit("Grid Thief")
        self.player_hp = _spin(1, 9999, 99)
        self.enemy_hp = _spin(1, 9999, 40)
        self.player_max = _spin(1, 999, 13)
        self.enemy_max = _spin(1, 999, 8)
        self.speed = _spin(0.8, 6.0, 2.0, 0.1, " s", 1)
        self.icon = QComboBox()
        for k in ("sword", "pipette", "flask", "microscope", "book", "shield", "flame", "star"):
            self.icon.addItem(k)
        self.xp = QCheckBox("XP drops for your hits")
        self.xp.setChecked(True)
        self.music = QCheckBox("Add 'Battle: drums and horns' music under the fight")
        self.music.setChecked(True)
        f.addRow("You", self.player)
        f.addRow("Opponent", self.enemy)
        f.addRow("Your health", self.player_hp)
        f.addRow("Opponent health", self.enemy_hp)
        f.addRow("Your biggest hit", self.player_max)
        f.addRow("Opponent's biggest hit", self.enemy_max)
        f.addRow("Time between your attacks", self.speed)
        f.addRow("XP drop icon", self.icon)
        f.addRow("", self.xp)
        f.addRow("", self.music)
        self.estimate = QLabel()
        self.estimate.setStyleSheet("color:#9aa0aa;")
        v.addWidget(self.estimate)
        for w in (self.enemy_hp, self.player_max, self.speed):
            w.valueChanged.connect(self._est)
        self._est()
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _est(self):
        avg = 0.75 * (self.player_max.value() + 1) / 2
        turns = max(1, round(self.enemy_hp.value() / max(0.5, avg)))
        self.estimate.setText(f"About {turns} attacks, roughly {turns * self.speed.value() + 3:.0f} s. "
                              "Fewer opponent health or a bigger hit = shorter fight.")

    def values(self):
        return {"player": self.player.text(), "enemy": self.enemy.text(), "player_hp": self.player_hp.value(),
                "enemy_hp": self.enemy_hp.value(), "player_max": self.player_max.value(),
                "enemy_max": self.enemy_max.value(), "speed": self.speed.value(), "icon": self.icon.currentText(),
                "xp": self.xp.isChecked(), "music": self.music.isChecked()}



class PicturePicker(QWidget):
    """'Use the video frame at the playhead' or 'a picture file'."""

    def __init__(self, parent, allow_later=False):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        self.mode = QComboBox()
        self.mode.addItem("Video frame at the red playhead", "frame")
        self.mode.addItem("A picture file…", "file")
        if allow_later:
            self.mode.addItem("Choose later", "later")
        self.path = ""
        self.label = QLabel("")
        self.label.setStyleSheet("color:#9aa0aa;")
        self.mode.activated.connect(self._pick)
        h.addWidget(self.mode)
        h.addWidget(self.label, 1)

    def _pick(self, _i=None):
        if self.mode.currentData() != "file":
            return
        path, _ = QFileDialog.getOpenFileName(self, "Choose a picture", "",
                                              "Pictures (*.png *.jpg *.jpeg *.webp *.bmp *.PNG *.JPG *.JPEG)")
        if path:
            self.path = path
            self.label.setText(os.path.basename(path))
        else:
            self.mode.setCurrentIndex(0)

    def value(self):
        m = self.mode.currentData()
        if m == "file" and not self.path:
            m = "frame"
        return {"mode": m, "path": self.path}


class WhosDialog(QDialog):
    """'Who's that …?' guessing sequence."""

    def __init__(self, mw):
        super().__init__(mw)
        self.setWindowTitle("Who's that …? (Pokémon style)")
        self.setMinimumWidth(520)
        v = QVBoxLayout(self)
        lab = QLabel("Places at the playhead: blue rays, the person as a black silhouette with your question and a "
                     "sting, then a flash and the real picture with the answer and a fanfare. Any picture works: the "
                     "person is cut out of the background automatically.")
        lab.setWordWrap(True)
        v.addWidget(lab)
        f = QFormLayout()
        v.addLayout(f)
        self.pic = PicturePicker(self)
        self.name = QLineEdit("PROFESSOR GRID")
        self.question = QLineEdit("Who's that NPC?")
        self.answer = QLineEdit("It's {name}!")
        self.reveal = _spin(0.5, 60, 4.0, 0.5, " s", 1)
        self.after = _spin(1, 60, 4.0, 0.5, " s", 1)
        self.bg = QCheckBox("Blue rays background (untick to keep the video behind)")
        self.bg.setChecked(True)
        f.addRow("Picture", self.pic)
        f.addRow("Name", self.name)
        f.addRow("Question", self.question)
        f.addRow("Answer", self.answer)
        f.addRow("Silhouette shown for", self.reveal)
        f.addRow("Answer shown for", self.after)
        f.addRow("", self.bg)
        tip = QLabel("Tip: for 'Video frame', first move the red playhead to a moment where the person is clearly "
                     "visible against a plain background. Then drag the yellow 'face' dot onto them and use "
                     "'Picture zoom' in the right panel.")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#9aa0aa;")
        v.addWidget(tip)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def values(self):
        return {"pic": self.pic.value(), "name": self.name.text(), "question": self.question.text(),
                "answer": self.answer.text(), "reveal": self.reveal.value(), "after": self.after.value(),
                "rays": self.bg.isChecked()}


class EvolveDialog(QDialog):
    """Evolution sequence."""

    def __init__(self, mw):
        super().__init__(mw)
        self.setWindowTitle("Evolution (Pokémon style)")
        self.setMinimumWidth(520)
        v = QVBoxLayout(self)
        lab = QLabel("Places at the playhead: 'What? … is evolving!', the person glowing white and flickering "
                     "between the before and after pictures faster and faster, a flash, the new form and "
                     "'Congratulations!'. Or it stops at the last moment.")
        lab.setWordWrap(True)
        v.addWidget(lab)
        f = QFormLayout()
        v.addLayout(f)
        self.name_a = QLineEdit("PHD STUDENT")
        self.pic_a = PicturePicker(self)
        self.name_b = QLineEdit("DOCTOR")
        self.pic_b = PicturePicker(self, allow_later=True)
        self.pic_b.mode.setCurrentIndex(2)
        self.result = QComboBox()
        self.result.addItem("Evolves", "evolves")
        self.result.addItem("Stops at the last moment (someone pressed B!)", "stops")
        f.addRow("Before: name", self.name_a)
        f.addRow("Before: picture", self.pic_a)
        f.addRow("After: name", self.name_b)
        f.addRow("After: picture", self.pic_b)
        f.addRow("Ending", self.result)
        tip = QLabel("Fun idea: 'before' = a photo from the first year, 'after' = in the graduation gown. "
                     "You can change either picture later in the right panel.")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#9aa0aa;")
        v.addWidget(tip)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def values(self):
        return {"name_a": self.name_a.text(), "pic_a": self.pic_a.value(), "name_b": self.name_b.text(),
                "pic_b": self.pic_b.value(), "result": self.result.currentData()}


class CaptureDialog(QDialog):
    """Catch sequence (Pokémon style), with an original sample-tube design."""

    def __init__(self, mw):
        super().__init__(mw)
        self.setWindowTitle("Catch sequence")
        self.setMinimumWidth(460)
        v = QVBoxLayout(self)
        lab = QLabel("Throw → flash → the tube drops and wobbles → caught (stars) or broke free (burst). "
                     "Sounds and the message are added too.")
        lab.setWordWrap(True)
        v.addWidget(lab)
        f = QFormLayout()
        v.addLayout(f)
        self.name = QLineEdit("Reviewer 2")
        self.shakes = QSpinBox()
        self.shakes.setRange(0, 3)
        self.shakes.setValue(3)
        self.result = QComboBox()
        self.result.addItem("Caught!", "caught")
        self.result.addItem("Broke free", "escaped")
        self.caught_text = QLineEdit("Gotcha! {name} was caught!")
        self.fail_text = QLineEdit("Oh no! {name} broke free!")
        self.tx = QDoubleSpinBox()
        self.tx.setRange(0, 1)
        self.tx.setSingleStep(0.05)
        self.tx.setValue(0.7)
        self.ty = QDoubleSpinBox()
        self.ty.setRange(0, 1)
        self.ty.setSingleStep(0.05)
        self.ty.setValue(0.42)
        f.addRow("Who is caught", self.name)
        f.addRow("Wobbles", self.shakes)
        f.addRow("Result", self.result)
        f.addRow("Caught message", self.caught_text)
        f.addRow("Escape message", self.fail_text)
        f.addRow("Target X (0 left – 1 right)", self.tx)
        f.addRow("Target Y (0 top – 1 bottom)", self.ty)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def values(self):
        return {"name": self.name.text(), "shakes": self.shakes.value(), "result": self.result.currentData(),
                "caught_text": self.caught_text.text(), "fail_text": self.fail_text.text(), "tx": self.tx.value(),
                "ty": self.ty.value()}


class CombineDialog(QDialog):
    """Pick projects and their order; they are joined one after another."""

    def __init__(self, mw):
        super().__init__(mw)
        from PySide6.QtWidgets import QListWidget
        self.mw = mw
        self.setWindowTitle("Combine projects")
        self.setMinimumSize(560, 420)
        v = QVBoxLayout(self)
        lab = QLabel("Add the .questcut files in the order they should play. Each one starts where the previous "
                     "one ends. Tracks are matched (V1 with V1, HUD 1 with HUD 1, …); spells keep hitting their "
                     "own health bars.")
        lab.setWordWrap(True)
        v.addWidget(lab)
        self.keep = QCheckBox("Start with what is already in the current project")
        self.keep.setChecked(mw.project.duration > 0)
        self.keep.setEnabled(mw.project.duration > 0)
        v.addWidget(self.keep)
        row = QHBoxLayout()
        self.list = QListWidget()
        row.addWidget(self.list, 1)
        col = QVBoxLayout()
        for text, fn in (("Add…", self._add), ("Move up", lambda: self._move(-1)), ("Move down", lambda: self._move(1)),
                         ("Remove", self._remove)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            col.addWidget(b)
        col.addStretch(1)
        row.addLayout(col)
        v.addLayout(row, 1)
        f = QFormLayout()
        self.gap = QDoubleSpinBox()
        self.gap.setRange(0, 60)
        self.gap.setSingleStep(0.5)
        self.gap.setSuffix(" s")
        self.gap.setValue(0.0)
        f.addRow("Gap between parts", self.gap)
        v.addLayout(f)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Combine")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _add(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Projects to add", self.mw.project.folder,
                                                "QuestCut project (*.questcut)")
        for f in sorted(files):
            if ".autosave." not in f:
                self.list.addItem(f)

    def _move(self, d):
        i = self.list.currentRow()
        j = i + d
        if i < 0 or not (0 <= j < self.list.count()):
            return
        it = self.list.takeItem(i)
        self.list.insertItem(j, it)
        self.list.setCurrentRow(j)

    def _remove(self):
        i = self.list.currentRow()
        if i >= 0:
            self.list.takeItem(i)

    def values(self):
        return {"paths": [self.list.item(i).text() for i in range(self.list.count())],
                "gap": self.gap.value(), "keep": self.keep.isChecked()}
