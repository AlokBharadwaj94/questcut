"""Main window: ties the panels together and holds every editing command."""
from __future__ import annotations

import copy
import os
import queue
import shutil
import sys
import threading
import time
from dataclasses import asdict

import numpy as np
from PySide6.QtCore import QElapsedTimer, QObject, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QImage, QKeySequence, QPixmap
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
                               QProgressDialog, QPushButton, QScrollBar, QSlider, QSplitter, QTabWidget, QToolBar,
                               QVBoxLayout, QWidget)

from .. import audio as audiomod
from .. import edit_ops
from ..backend import AUDIO, HW, detect_hardware, probe_audio_devices
from ..cards import CARD_TYPES, card_defaults
from ..hud import BAR_TYPES, FULLSCREEN_TYPES, HUD_TYPES, PORTRAIT_TYPES, hud_defaults
from ..media import (AUDIO_EXT, IMAGE_EXT, VIDEO_EXT, FrameSource, cache_dir, load_audio, make_proxy, probe)
from ..model import APP_NAME, PROJECT_EXT, Clip, Media, Project, Track, append_project, new_id, relink_media
from .dialogs import ExportDialog, GpuInfoDialog, RecorderDialog, SpellDialog
from .guide import Guide
from .inspector import Inspector
from .mediabin import MediaBin
from .theme import ACCENT, fmt_time
from .timeline import Timeline
from .viewer import RenderWorker, Viewer


class _Bridge(QObject):
    call = Signal(object)


def _snapshot(project):
    return copy.deepcopy(project.to_dict())


class MainWindow(QMainWindow):
    PIP_PRESETS = [("full", "Full screen"), ("tr", "Top-right corner"), ("tl", "Top-left corner"),
                   ("br", "Bottom-right corner"), ("bl", "Bottom-left corner"), ("minimap", "Minimap circle"),
                   ("side_l", "Side by side: left"), ("side_r", "Side by side: right")]
    EFFECT_MENU = [("color", "Colour & light"), ("look", "Game look"), ("vignette", "Vignette"),
                   ("region", "Touch-up area"), ("blur", "Blur"), ("sharpen", "Sharpen")]

    def __init__(self):
        super().__init__()
        self.project = Project.new_default()
        self.playhead = 0.0
        self.playing = False
        self.dirty = False
        self.undo_stack, self.redo_stack = [], []
        self._last_edit = (None, 0.0)
        self.clipboard = []
        self.insert_mode = False
        self.thumbs = {}
        self.proxy_jobs = set()
        self.preview_quality = "auto"
        self._bridge = _Bridge()
        self._bridge.call.connect(lambda fn: fn())
        self._proxy_q = queue.Queue()
        threading.Thread(target=self._proxy_loop, daemon=True).start()

        self.worker = RenderWorker(self.project.clone())
        self.worker.frameReady.connect(self._on_frame)
        self.worker.start()

        self._build_ui()
        self.resize(1500, 920)
        self._update_title()
        self.play_timer = QTimer(self)
        self.play_timer.setInterval(15)
        self.play_timer.timeout.connect(self._play_tick)
        self.clock = QElapsedTimer()
        self.sink = None
        self.audio_io = None
        self.autosave = QTimer(self)
        self.autosave.timeout.connect(self._autosave)
        self.autosave.start(120_000)
        self.run_bg(self._detect_hw)
        QTimer.singleShot(50, self.request_frame)

    # ================================================================ infrastructure
    def run_bg(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def call_in_gui(self, fn):
        self._bridge.call.emit(fn)

    def status(self, msg, ms=8000):
        self.statusBar().showMessage(msg, ms)

    def _detect_hw(self):
        probe_audio_devices()
        if AUDIO["outputs"] == 0:
            self.call_in_gui(lambda: self.status("No sound output found: the preview will play without sound "
                                                 "(the exported movie still has sound).", 15000))
        detect_hardware()
        self.call_in_gui(lambda: self.hw_label.setText(HW.summary()))

    # ================================================================ UI
    def _build_ui(self):
        self.bin = MediaBin(self)
        self.viewer = Viewer(self)
        self.inspector = Inspector(self)
        self.guide = Guide(self)
        self.timeline = Timeline(self)
        self.timeline.playheadMoved.connect(self._on_timeline_playhead)
        self.timeline.selectionChanged.connect(self._on_selection)
        self.timeline.trackSelected.connect(lambda tid: self.inspector.show_track(tid) if not self.timeline.selected else None)

        # transport under the viewer
        tw = QWidget()
        tl = QHBoxLayout(tw)
        tl.setContentsMargins(4, 2, 4, 2)

        def tbtn(text, fn, tip):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.setFixedHeight(30)
            b.clicked.connect(fn)
            tl.addWidget(b)
            return b
        tbtn("⏮", lambda: self.set_playhead(0), "Go to start (Home)")
        tbtn("◀|", lambda: self.step(-1), "One frame back (←)")
        self.play_btn = tbtn("▶  Play", self.toggle_play, "Play / pause (Space)")
        self.play_btn.setObjectName("primary")
        self.play_btn.setMinimumWidth(90)
        tbtn("|▶", lambda: self.step(1), "One frame forward (→)")
        tbtn("⏭", lambda: self.set_playhead(self.project.duration), "Go to end (End)")
        self.time_label = QLabel("00:00.00 / 00:00.00")
        self.time_label.setStyleSheet(f"font-family: monospace; font-size: 15px; color: {ACCENT}; padding-left: 10px;")
        tl.addWidget(self.time_label)
        tl.addStretch(1)
        self.render_label = QLabel("")
        self.render_label.setStyleSheet("color:#9aa0aa;")
        tl.addWidget(self.render_label)
        tl.addWidget(QLabel("Preview:"))
        self.quality_combo = QComboBox()
        for k, lab in (("auto", "Auto"), ("full", "Full"), ("half", "Half"), ("quarter", "Quarter (fastest)")):
            self.quality_combo.addItem(lab, k)
        self.quality_combo.currentIndexChanged.connect(self._set_quality)
        tl.addWidget(self.quality_combo)

        center = QWidget()
        cl = QVBoxLayout(center)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(self.viewer, 1)
        cl.addWidget(tw)

        self.right_tabs = QTabWidget()
        self.right_tabs.addTab(self.inspector, "Inspector")
        self.right_tabs.addTab(self.guide, "Guide")

        top = QSplitter(Qt.Orientation.Horizontal)
        top.addWidget(self.bin)
        top.addWidget(center)
        top.addWidget(self.right_tabs)
        top.setStretchFactor(0, 0)
        top.setStretchFactor(1, 1)
        top.setStretchFactor(2, 0)
        top.setSizes([300, 800, 390])

        # timeline + zoom bar
        tlw = QWidget()
        tv = QVBoxLayout(tlw)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.setSpacing(0)
        zb = QHBoxLayout()
        zb.setContentsMargins(6, 2, 6, 2)
        lab = QLabel("Timeline  ·  wheel = scroll, Ctrl+wheel = zoom, Shift+wheel = up/down")
        lab.setStyleSheet("color:#9aa0aa;")
        zb.addWidget(lab)
        zb.addStretch(1)
        fit = QPushButton("Zoom to fit")
        fit.clicked.connect(self.timeline.zoom_to_fit)
        zb.addWidget(fit)
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(0, 1000)
        self.zoom_slider.setFixedWidth(180)
        self.zoom_slider.setValue(500)
        self.zoom_slider.valueChanged.connect(lambda v: self.timeline.set_zoom(2 * (400 / 2) ** (v / 1000)))
        zb.addWidget(self.zoom_slider)
        tv.addLayout(zb)
        mid = QHBoxLayout()
        mid.setSpacing(0)
        mid.addWidget(self.timeline, 1)
        self.vscroll = QScrollBar(Qt.Orientation.Vertical)
        self.vscroll.valueChanged.connect(self._vscroll)
        mid.addWidget(self.vscroll)
        tv.addLayout(mid, 1)
        self.hscroll = QScrollBar(Qt.Orientation.Horizontal)
        self.hscroll.valueChanged.connect(self._hscroll)
        tv.addWidget(self.hscroll)
        self._sync_guard = False

        main = QSplitter(Qt.Orientation.Vertical)
        main.addWidget(top)
        main.addWidget(tlw)
        main.setSizes([520, 430])
        self.setCentralWidget(main)
        self.right_tabs.setCurrentIndex(1)

        self.hw_label = QLabel(HW.summary())
        self.statusBar().addPermanentWidget(self.hw_label)
        self._build_actions()

    def sync_scrollbars(self):
        """Keep the timeline scrollbars in step with the timeline view."""
        if self._sync_guard:
            return
        self._sync_guard = True
        tl = self.timeline
        vis = max(1, tl.height())
        total = tl.content_height()
        self.vscroll.setRange(0, max(0, total - vis))
        self.vscroll.setPageStep(vis)
        self.vscroll.setValue(int(tl.scroll_y))
        self.vscroll.setVisible(total > vis)
        span = max(1.0, (tl.width() - 190) / tl.pps)
        end = max(self.project.duration + span * 0.5, span)
        self.hscroll.setRange(0, int(max(0.0, end - span) * 100))
        self.hscroll.setPageStep(int(span * 100))
        self.hscroll.setValue(int(tl.scroll_x * 100))
        self._sync_guard = False

    def _vscroll(self, v):
        if not self._sync_guard:
            self.timeline.scroll_y = v
            self.timeline.update()

    def _hscroll(self, v):
        if not self._sync_guard:
            self.timeline.scroll_x = v / 100.0
            self.timeline.update()

    def _act(self, text, fn, shortcut=None, tip=None, menu=None, toolbar=None):
        a = QAction(text, self)
        a.triggered.connect(lambda checked=False: fn())
        if shortcut:
            if isinstance(shortcut, (list, tuple)):
                a.setShortcuts([QKeySequence(s) for s in shortcut])
            else:
                a.setShortcut(QKeySequence(shortcut))
        if tip:
            a.setToolTip(tip)
            a.setStatusTip(tip)
        self.addAction(a)
        if menu is not None:
            menu.addAction(a)
        if toolbar is not None:
            toolbar.addAction(a)
        return a

    def _build_actions(self):
        mb = self.menuBar()
        tb = QToolBar("Main")
        tb.setIconSize(QSize(18, 18))
        tb.setMovable(False)
        self.addToolBar(tb)
        f = mb.addMenu("&File")
        self._act("New project", self.new_project, QKeySequence.StandardKey.New, menu=f)
        self._act("Open project…", self.open_project, QKeySequence.StandardKey.Open, menu=f)
        self._act("💾 Save", self.save, QKeySequence.StandardKey.Save, "Save the project (Ctrl+S)", f, tb)
        self._act("Save as…", self.save_as, QKeySequence.StandardKey.SaveAs, menu=f)
        self._act("Combine projects…", self.combine_projects,
                  tip="Join several .questcut projects one after another into this project", menu=f)
        self._act("Pack project for another computer…", self.pack_project,
                  tip="Copy the project and all its files into one folder (for the Mac or the lab computer)", menu=f)
        f.addSeparator()
        self._act("📥 Import", self.import_files, "Ctrl+I", "Import videos, sounds and pictures (Ctrl+I)", f, tb)
        self._act("🎬 Export movie…", self.export, "Ctrl+E", "Export the finished movie as MP4 (Ctrl+E)", f)
        self._act("Export still picture…", self.export_still, tip="Save the current frame as PNG", menu=f)
        f.addSeparator()
        self._act("Quit", self.close, QKeySequence.StandardKey.Quit, menu=f)
        tb.addSeparator()
        e = mb.addMenu("&Edit")
        self._act("↶ Undo", self.undo, QKeySequence.StandardKey.Undo, "Undo (Ctrl+Z)", e, tb)
        self._act("↷ Redo", self.redo, ["Ctrl+Shift+Z", "Ctrl+Y"], "Redo (Ctrl+Shift+Z)", e, tb)
        e.addSeparator()
        tb.addSeparator()
        self._act("✂ Split", self.split_at_playhead, "S", "Cut at the red playhead (S)", e, tb)
        self._act("🗑 Delete", self.delete_selected, ["Delete", "Backspace"], "Delete selected (Del)", e, tb)
        self._act("Delete and close gap", lambda: self.delete_selected(ripple=True), "Shift+Delete", menu=e)
        self._act("Copy", self.copy_selected, QKeySequence.StandardKey.Copy, menu=e)
        self._act("Paste", self.paste, QKeySequence.StandardKey.Paste, menu=e)
        self._act("Duplicate", self.duplicate_selected, "Ctrl+D", menu=e)
        self._act("Select all clips", self.select_all, QKeySequence.StandardKey.SelectAll, menu=e)
        self._act("Close gap at playhead (all tracks)", lambda: self.close_gap(self.playhead), "Ctrl+G", menu=e)
        e.addSeparator()
        self.insert_action = self._act("⇥ Insert mode", self.toggle_insert_mode, "Ins",
                                       "Insert mode: a clip added in the middle pushes everything after it "
                                       "(all tracks) later, instead of covering what is there (Ins)", e, tb)
        self.insert_action.setCheckable(True)
        self._act("Insert empty time at playhead (all tracks)…", self.insert_time_dialog, "Ctrl+Shift+T", menu=e)
        self._act("Mark start of a stretch of time", self.set_mark_in, "I", menu=e)
        self._act("Mark end of a stretch of time", self.set_mark_out, "O", menu=e)
        self._act("Remove marked time from all tracks (close it up)", self.remove_marked_time,
                  "Ctrl+Shift+Delete", menu=e)
        self._act("Clear the marks", self.clear_marks, "Alt+X", menu=e)
        e.addSeparator()
        self._act("Group selected pieces", self.group_selected, "G", menu=e)
        self._act("Ungroup", self.ungroup_selected, "Shift+G", menu=e)
        self._act("Hide / show piece", self.toggle_enabled, "H", menu=e)
        tb.addSeparator()
        c = mb.addMenu("&Camera")
        self._act("🔗 Sync by sound", self.sync_selected, "Y", "Line up two selected clips by their sound (Y)", c, tb)
        self._act("🔀 Switch camera", self.switch_angle, "A", "Switch to the other camera from the playhead (A)", c, tb)
        self._act("❄ Freeze + card", self.freeze_frame, "F", "Freeze-frame character intro (F)", c, tb)
        self._act("Steady shaky footage (GoPro)…", self.stabilize_selected,
                  tip="Make a steadier copy of the selected video clip (slow, runs in the background)", menu=c)
        pip = c.addMenu("Picture-in-picture")
        for key, label in self.PIP_PRESETS:
            self._act(label, lambda k=key: self.apply_pip(k), menu=pip)
        g = mb.addMenu("&Game")
        self._act("⚡ Spell event", self.spell_wizard, "E", "Spell / attack: text + sound + hit together (E)", g, tb)
        g.addSeparator()
        self._act("Creature battle start here… (Pokémon style)", self.battle_combo, "B",
                  tip="Transition + HP boxes + 'A wild … appeared!' + menu + music, all at the playhead", menu=g)
        self._act("Catch sequence here… (Pokémon style)", self.capture_combo, "C",
                  tip="Throw, wobbles, caught or broke free, with sounds and message", menu=g)
        self._act("Who's that …? here (Pokémon style)", self.whos_combo, "W",
                  tip="Silhouette + question, then flash + reveal, with sounds", menu=g)
        self._act("Evolution here… (Pokémon style)", self.evolve_combo, "V",
                  tip="Before picture flickers into the after picture, with messages and sounds", menu=g)
        g.addSeparator()
        self._act("Quest conversation here… (RuneScape style)", self.quest_talk_combo, "Q",
                  tip="NPC chat boxes + 'Select an Option' + your reply + 'quest started' message", menu=g)
        self._act("Fight here… (RuneScape style)", self.fight_combo, "K",
                  tip="Overhead health bars, damage splats, hit sounds, XP drops, music", menu=g)
        g.addSeparator()
        self._act("🎙 Record voice", self.record_voice, "R", "Record a voice-over (R)", g, tb)
        tb.addSeparator()
        self._act("🎬 Export", self.export, None, "Export the finished movie (Ctrl+E)", None, tb)
        v = mb.addMenu("&View")
        self._act("Play / pause", self.toggle_play, "Space", menu=v)
        self._act("Frame back", lambda: self.step(-1), "Left", menu=v)
        self._act("Frame forward", lambda: self.step(1), "Right", menu=v)
        self._act("1 s back", lambda: self.set_playhead(self.playhead - 1), "Shift+Left", menu=v)
        self._act("1 s forward", lambda: self.set_playhead(self.playhead + 1), "Shift+Right", menu=v)
        self._act("Go to start", lambda: self.set_playhead(0), "Home", menu=v)
        self._act("Go to end", lambda: self.set_playhead(self.project.duration), "End", menu=v)
        self._act("Zoom timeline to fit", self.timeline.zoom_to_fit, "Z", menu=v)
        self._act("Zoom in", lambda: self.timeline.set_zoom(self.timeline.pps * 1.3), ["Ctrl+=", "Ctrl++"], menu=v)
        self._act("Zoom out", lambda: self.timeline.set_zoom(self.timeline.pps / 1.3), "Ctrl+-", menu=v)
        h = mb.addMenu("&Help")
        self._act("Guide (lessons)", lambda: self.right_tabs.setCurrentIndex(1), "F1", menu=h)
        self._act("Create practice project", self.create_practice_project, menu=h)
        self._act("What does the GPU speed up?", self.show_gpu_info, menu=h)
        self._act("About QuestCut", lambda: QMessageBox.about(
            self, "About QuestCut", "<b>QuestCut</b><br>A small video editor for video-game style movies.<br>"
            "Made with Python, Qt (PySide6), PyAV/FFmpeg, NumPy and OpenCV."), menu=h)

    # ================================================================ title / dirty
    def _update_title(self):
        name = os.path.basename(self.project.path) if self.project.path else "Unsaved project"
        self.setWindowTitle(f"{APP_NAME} — {name}{' *' if self.dirty else ''}")

    # ================================================================ editing core
    def push_undo(self):
        self.undo_stack.append(_snapshot(self.project))
        if len(self.undo_stack) > 200:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def begin_edit(self):
        self.push_undo()
        self._last_edit = (None, 0.0)

    def end_edit(self):
        self.refresh_all()

    def edit(self, key, fn):
        """Apply a change. Quick repeated changes of the same thing (dragging a
        slider) become one undo step."""
        now = time.time()
        if key is None or key != self._last_edit[0] or now - self._last_edit[1] > 1.2:
            self.push_undo()
        self._last_edit = (key, now)
        fn()
        self.live_changed()

    def live_changed(self):
        self.dirty = True
        self._update_title()
        self.worker.set_project(self.project.clone())
        self.request_frame()
        self.timeline.update()
        self.viewer.update()

    def refresh_all(self):
        self.live_changed()
        sel = [cid for cid in self.timeline.selected if self.project.clip(cid) is not None]
        self.timeline.selected = sel
        if sel:
            self.inspector.show_clip(sel[0])
        else:
            self.inspector.rebuild()
        self.bin.refresh_media()
        self._update_time_label()

    def _restore(self, d):
        path = self.project.path
        self.project = Project.from_dict(copy.deepcopy(d))
        self.project.path = path
        self.refresh_all()

    def undo(self):
        if not self.undo_stack:
            self.status("Nothing to undo.")
            return
        self.redo_stack.append(_snapshot(self.project))
        self._restore(self.undo_stack.pop())
        self.status("Undone.", 2000)

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append(_snapshot(self.project))
        self._restore(self.redo_stack.pop())
        self.status("Redone.", 2000)

    # ================================================================ preview & playback
    def _set_quality(self, i):
        self.preview_quality = self.quality_combo.itemData(i)
        self.request_frame()

    def request_frame(self):
        w, h = self.viewer.preview_size(self.playing)
        self.worker.request(self.playhead, w, h)

    def _on_frame(self, img, t, ms):
        self.viewer.set_image(img)
        self.render_label.setText(f"{img.width()}×{img.height()} · {ms:.0f} ms/frame")

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        QTimer.singleShot(0, self.request_frame)

    def _update_time_label(self):
        fps = self.project.fps
        self.time_label.setText(f"{fmt_time(self.playhead, fps)} / {fmt_time(self.project.duration, fps)}")

    def set_playhead(self, t, from_timeline=False):
        self.playhead = max(0.0, float(t))
        if not from_timeline:
            self.timeline.set_playhead(self.playhead, emit=False, follow=self.playing)
        self.inspector.refresh_values()
        self.viewer.update()
        self._update_time_label()
        self.request_frame()

    def _on_timeline_playhead(self, t):
        if self.playing:
            self.stop_playback()
        self.set_playhead(t, from_timeline=True)

    def step(self, n):
        if self.playing:
            self.stop_playback()
        fps = self.project.fps
        f = round(self.playhead * fps) + n
        self.set_playhead(max(0, f) / fps)

    def toggle_play(self):
        if self.playing:
            self.stop_playback()
        else:
            self.play()

    def play(self, mute=False):
        if self.playing:
            return
        if self.playhead >= self.project.duration - 0.05:
            self.playhead = 0.0
        self.playing = True
        self.play_btn.setText("❚❚  Pause")
        self.play_t0 = self.playhead
        self.clock.start()
        self.audio_pos = self.playhead
        if not mute:
            self._start_audio()
        self.play_timer.start()

    def _start_audio(self):
        if not AUDIO["checked"] or AUDIO["outputs"] == 0:
            return
        try:
            from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices
            fmt = QAudioFormat()
            fmt.setSampleRate(48000)
            fmt.setChannelCount(2)
            fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
            dev = QMediaDevices.defaultAudioOutput()
            self.sink = QAudioSink(dev, fmt, self)
            self.sink.setBufferSize(48000 * 4 // 4)   # 0.25 s
            self.audio_io = self.sink.start()
        except Exception as e:
            self.sink = None
            self.audio_io = None
            self.status(f"No sound output: {e}")

    def _feed_audio(self, now):
        if self.audio_io is None or self.sink is None:
            return
        ahead = 0.2
        if self.audio_pos < now:
            self.audio_pos = now
        while self.audio_pos < now + ahead:
            free = self.sink.bytesFree()
            n = min(int(0.05 * 48000), free // 4)
            if n < 480:
                break
            chunk = audiomod.mix(self.project, self.audio_pos, n / 48000)
            data = (np.clip(chunk, -1, 1) * 32767).astype(np.int16).tobytes()
            self.audio_io.write(data)
            self.audio_pos += n / 48000

    def _play_tick(self):
        t = self.play_t0 + self.clock.elapsed() / 1000.0
        if t >= self.project.duration:
            self.stop_playback()
            self.set_playhead(self.project.duration)
            return
        self._feed_audio(t)
        self.playhead = t
        self.timeline.set_playhead(t, emit=False, follow=True)
        self._update_time_label()
        self.request_frame()

    def stop_playback(self):
        if not self.playing:
            return
        self.playing = False
        self.play_timer.stop()
        self.play_btn.setText("▶  Play")
        if self.sink is not None:
            try:
                self.sink.stop()
            except Exception:
                pass
        self.sink = None
        self.audio_io = None
        self.inspector.refresh_values()
        self.viewer.update()
        self.request_frame()

    # ================================================================ selection & handles
    def selected_clips(self):
        return [c for c in (self.project.clip(cid) for cid in self.timeline.selected) if c is not None]

    def _on_selection(self):
        sel = self.selected_clips()
        if sel:
            self.inspector.show_clip(sel[0].id)
            self.right_tabs.setCurrentIndex(0)
        else:
            self.inspector.show_nothing()
        self.viewer.update()

    def focus_inspector(self):
        self.right_tabs.setCurrentIndex(0)

    def viewer_handles(self):
        sel = self.selected_clips()
        if len(sel) != 1 and not (sel and sel[0].props.get("group") and
                                  all(c.props.get("group") == sel[0].props.get("group") for c in sel)):
            return []
        c = sel[0]
        t_rel = self.playhead - c.start
        if not (0 <= t_rel <= c.duration):
            return []
        hs = []

        def add(label, kx, ky, mode, dx=0.5, dy=0.5):
            x = float(c.value(kx, t_rel, 0.0 if mode == "center" else dx))
            y = float(c.value(ky, t_rel, 0.0 if mode == "center" else dy))
            if mode == "center":
                x, y = x + 0.5, y + 0.5
            hs.append({"label": label, "kx": kx, "ky": ky, "mode": mode, "x": x, "y": y, "clip": c.id})

        if c.kind == "hud":
            if c.hud_type in PORTRAIT_TYPES:
                if c.media_id:
                    add("face (portrait)" if c.hud_type in ("sv_dialogue", "rs_dialogue") else "person",
                        "portrait_x", "portrait_y", "abs")
                if c.hud_type == "pk_evolve" and c.props.get("media2"):
                    add("after (person)", "pic2_x", "pic2_y", "abs")
            elif c.hud_type == "pk_capture":
                add("T  target", "target_x", "target_y", "abs")
                add("throw from", "from_x", "from_y", "abs")
            elif c.hud_type == "spell":
                add("C  caster", "caster_x", "caster_y", "abs")
                add("T  target", "target_x", "target_y", "abs")
            elif c.hud_type not in FULLSCREEN_TYPES:
                add(c.name or "move", "x", "y", "abs")
        elif c.kind in ("video", "image", "card"):
            if float(c.value("scale", t_rel, 1.0)) < 0.98 or c.value("x", t_rel, 0) or c.value("y", t_rel, 0):
                add("move", "x", "y", "center")
        for f in c.effects:
            if f["type"] in ("vignette", "region") and f.get("enabled", True):
                add("vignette" if f["type"] == "vignette" else f["params"].get("mode", "area"),
                    f"fx.{f['id']}.cx", f"fx.{f['id']}.cy", "abs")
        return hs

    def move_handle(self, h, nx, ny):
        c = self.project.clip(h["clip"])
        if c is None:
            return
        t_rel = self.playhead - c.start
        if h["mode"] == "center":
            vx, vy = nx - 0.5, ny - 0.5
        else:
            vx, vy = nx, ny
        vx = round(max(-0.5, min(1.5, vx)), 4)
        vy = round(max(-0.5, min(1.5, vy)), 4)
        c.set_value(h["kx"], vx, t_rel)
        c.set_value(h["ky"], vy, t_rel)
        self.live_changed()
        self.inspector.refresh_values()

    def jump_keyframe(self, direction):
        sel = self.selected_clips()
        if not sel:
            return
        c = sel[0]
        times = [c.start + k for k in c.keyframe_times()]
        if direction > 0:
            nxt = [t for t in times if t > self.playhead + 0.01]
            if nxt:
                self.set_playhead(min(nxt))
        else:
            prv = [t for t in times if t < self.playhead - 0.01]
            if prv:
                self.set_playhead(max(prv))

    # ================================================================ helpers for tracks
    def tracks_of(self, kind):
        return [t for t in self.project.tracks if t.kind == kind]

    def _free(self, track, t0, t1, ignore=()):
        return all(c.end <= t0 + 1e-6 or c.start >= t1 - 1e-6 for c in track.clips if c.id not in ignore)

    def find_track(self, kind, t0, t1, preferred=None, avoid_voice=True, create_name=None):
        """First track of this kind that is free between t0 and t1."""
        cands = self.tracks_of(kind)
        if kind == "video":
            cands = list(reversed(cands))      # V1 first
        if kind == "audio" and avoid_voice:
            cands = [t for t in cands if not t.is_voice]
        if preferred is not None and preferred in cands:
            cands.remove(preferred)
            cands.insert(0, preferred)
        for tr in cands:
            if not tr.locked and self._free(tr, t0, t1):
                return tr
        if create_name:
            return self.add_track(kind, create_name, refresh=False)
        return cands[0] if cands else None

    def add_track(self, kind, name=None, refresh=True):
        n = len(self.tracks_of(kind)) + 1
        name = name or {"video": f"V{n}", "hud": f"HUD {n}", "audio": f"A{n}"}[kind]
        tr = Track(new_id("t"), kind, name)
        if refresh:
            self.push_undo()
        # insert at the top of its group
        idx = next((i for i, t in enumerate(self.project.tracks) if t.kind == kind), len(self.project.tracks))
        if kind == "audio":
            idx = len(self.project.tracks)
        self.project.tracks.insert(idx, tr)
        if refresh:
            self.refresh_all()
        return tr

    def remove_track(self, tid):
        tr = self.project.track(tid)
        if tr is None:
            return
        if len(self.tracks_of(tr.kind)) <= 1:
            self.status("Keep at least one track of each kind.")
            return
        if tr.clips and QMessageBox.question(self, "Remove track",
                                             f"'{tr.name}' has {len(tr.clips)} clips. Remove it anyway?") != \
                QMessageBox.StandardButton.Yes:
            return
        self.push_undo()
        self.project.tracks.remove(tr)
        self.inspector.show_nothing()
        self.refresh_all()

    def music_track(self):
        for t in self.tracks_of("audio"):
            if "music" in t.name.lower():
                return t
        return self.tracks_of("audio")[-1]

    def sfx_track(self):
        for t in self.tracks_of("audio"):
            if "sound" in t.name.lower() and not t.is_voice:
                return t
        return self.find_track("audio", 0, 0)

    def voice_track(self):
        for t in self.tracks_of("audio"):
            if t.is_voice:
                return t
        return self.add_track("audio", "A  Voice-over", refresh=False)

    def _select(self, clips):
        self.timeline.selected = [c.id for c in clips]
        self._on_selection()

    # ================================================================ media
    def import_files(self):
        exts = " ".join("*" + e for e in sorted(VIDEO_EXT | AUDIO_EXT | IMAGE_EXT))
        exts_upper = " ".join("*" + e.upper() for e in sorted(VIDEO_EXT | AUDIO_EXT | IMAGE_EXT))
        files, _ = QFileDialog.getOpenFileNames(self, "Import videos, sounds and pictures", self.project.folder,
                                                f"Media ({exts} {exts_upper});;All files (*)")
        if files:
            self.import_paths(files)

    def import_paths(self, files, then=None):
        self.status(f"Importing {len(files)} file(s)…")

        def work():
            added, errors = [], []
            for f in files:
                try:
                    added.append(probe(f))
                except Exception as e:
                    errors.append(f"{os.path.basename(f)}: {e}")

            def done():
                new = [self.project.add_media(m) for m in added]
                for m in new:
                    self._post_import(m)
                self.bin.refresh_media()
                self.bin.setCurrentIndex(0)
                self.dirty = True
                self._update_title()
                self.worker.set_project(self.project.clone())
                msg = f"Imported {len(new)} file(s). Double-click one to put it on the timeline."
                if errors:
                    QMessageBox.warning(self, "Some files could not be read", "\n".join(errors))
                self.status(msg)
                if then:
                    then(new)
            self.call_in_gui(done)
        self.run_bg(work)

    def _post_import(self, m):
        if m.kind in ("video", "image"):
            self.run_bg(lambda: self._make_thumb(m))
        if m.kind == "video" and m.height > 600:
            self.proxy_jobs.add(m.id)
            self._proxy_q.put(m)
        if m.has_audio or m.kind == "audio":
            proj = self.project
            self.run_bg(lambda: load_audio(proj, m))

    def _make_thumb(self, m):
        try:
            if m.kind == "image":
                from ..media import imread_any
                import cv2
                arr = imread_any(m.path)
                arr = cv2.resize(arr[..., :3], (160, max(1, int(160 * arr.shape[0] / arr.shape[1]))))
            else:
                src = FrameSource(m.path, m.rotation)
                arr = src.get(min(1.0, m.duration / 2), 90)
                src.close()
            arr = np.ascontiguousarray(arr)
            h, w = arr.shape[:2]
            img = QImage(arr.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()

            def done():
                self.thumbs[m.id] = QPixmap.fromImage(img)
                self.bin.refresh_media()
                self.timeline.update()
            self.call_in_gui(done)
        except Exception as e:
            print("thumb error", e)

    def _proxy_loop(self):
        while True:
            m = self._proxy_q.get()
            try:
                path = make_proxy(self.project, m)
            except Exception as e:
                print("proxy error", e)
                path = None

            def done(m=m, path=path):
                self.proxy_jobs.discard(m.id)
                if path:
                    self.worker.set_proxy(m.id, path)
                self.bin.refresh_media()
            self.call_in_gui(done)

    def remove_media(self, mid):
        users = [c for c in self.project.all_clips() if c.media_id == mid]
        if users and QMessageBox.question(self, "Remove", f"This file is used by {len(users)} clip(s) in the timeline. "
                                          "Remove those clips too?") != QMessageBox.StandardButton.Yes:
            return
        self.push_undo()
        for tr in self.project.tracks:
            tr.clips = [c for c in tr.clips if c.media_id != mid]
            for c in tr.clips:
                for k, v in c.picture_refs().items():
                    if v == mid:
                        c.props[k] = ""
        self.project.media.pop(mid, None)
        self.refresh_all()

    def game_sound_path(self, name):
        folder = os.path.join(self.project.folder, "game_sounds") if self.project.path else \
            os.path.join(cache_dir(None), "game_sounds")
        return audiomod.game_sound_file(folder, name)

    def _game_sound_media(self, name):
        tag = f"sfx:{name}"
        for m in self.project.media.values():
            if m.generated == tag and os.path.exists(m.path):
                return m
        path = self.game_sound_path(name)
        m = probe(path)
        m.generated = tag
        m.name = audiomod.GAME_SOUNDS[name][0]
        return self.project.add_media(m)

    def _regenerate_sounds(self):
        for m in self.project.media.values():
            if m.generated.startswith("sfx:") and not os.path.exists(m.path):
                m.path = self.game_sound_path(m.generated[4:])

    # ================================================================ adding things
    def add_item(self, payload, t, track):
        kind = payload.get("type")
        t = max(0.0, t)
        if kind == "effect":
            target = None
            if track is not None and track.kind in ("video", "hud"):
                c = track.clip_at(t)
                if c is not None and c.kind in ("video", "image", "card", "adjust"):
                    target = c
            if target is not None:
                self._select([target])
            self.apply_look_payload(payload)
            return
        self.push_undo()
        if self.insert_mode:
            ins = self._insert_length(payload, track)
            if ins > 0:
                edit_ops.insert_time(self.project, t, ins)
        new = None
        if kind == "media":
            m = self.project.media.get(payload["id"])
            if m is None:
                return
            if m.kind == "video":
                pref = track if track is not None and track.kind == "video" else None
                tr = self.find_track("video", t, t + m.duration, pref, create_name=None)
                new = Clip(new_id("c"), "video", t, m.duration, os.path.splitext(m.name)[0], m.id)
            elif m.kind == "audio":
                pref = track if track is not None and track.kind == "audio" else None
                if pref is None:
                    pref = self.music_track() if m.duration > 30 else self.sfx_track()
                tr = self.find_track("audio", t, t + m.duration, pref, avoid_voice=False, create_name="A  Sounds")
                new = Clip(new_id("c"), "audio", t, m.duration, os.path.splitext(m.name)[0], m.id)
            else:  # picture
                if track is not None and track.kind == "video":
                    tr = track
                    new = Clip(new_id("c"), "image", t, 5.0, os.path.splitext(m.name)[0], m.id)
                else:
                    tr = track if track is not None and track.kind == "hud" else self.tracks_of("hud")[-1]
                    pr = hud_defaults("sticker")
                    new = Clip(new_id("c"), "hud", t, 4.0, os.path.splitext(m.name)[0], m.id, hud_type="sticker",
                               props=pr)
        elif kind == "sound":
            name = payload["name"]
            m = self._game_sound_media(name)
            is_music = name.startswith("music_")
            pref = self.music_track() if is_music else (track if track is not None and track.kind == "audio"
                                                        else self.sfx_track())
            dur = m.duration
            tr = self.find_track("audio", t, t + dur, pref, avoid_voice=True, create_name="A  Game sounds 2")
            new = Clip(new_id("c"), "audio", t, dur, m.name, m.id)
            if is_music:
                new.props.update({"loop": True, "fade_out": 1.5, "volume": 0.7})
        elif kind == "hud":
            name = payload["name"]
            spec = HUD_TYPES[name]
            pr = hud_defaults(name)
            style = self.bin.default_style()
            pr["style"] = style
            if name == "frame":
                pr["variant"] = {"retro": "retro_tv", "rpg": "rpg_ornate", "fps": "fps_visor"}[style]
                pr["color"] = {"retro": "#ffffff", "rpg": "#d8b45a", "fps": "#7dfcff"}[style]
            dur = spec["duration"]
            if name == "frame":
                dur = max(10.0, self.project.duration - t) if self.project.duration > t + 1 else 30.0
            huds = self.tracks_of("hud")
            if track is not None and track.kind == "hud":
                tr = track
            elif name == "frame":
                tr = huds[0]
            else:
                # bottom HUD track that is free at this time; make a new HUD track if all are busy
                tr = next((h for h in reversed(huds) if not h.locked and self._free(h, t, t + dur)), None)
                if tr is None:
                    tr = self.add_track("hud", f"HUD {len(huds) + 1}", refresh=False)
            new = Clip(new_id("c"), "hud", t, dur, spec["label"].split(" (")[0], hud_type=name, props=pr)
        elif kind == "card":
            name = payload["name"]
            vids = self.tracks_of("video")
            tr = track if track is not None and track.kind == "video" else vids[0]
            new = Clip(new_id("c"), "card", t, CARD_TYPES[name]["duration"], CARD_TYPES[name]["label"],
                       props=card_defaults(name))
            new.transition_in = {"type": "fade", "duration": 0.5}
        if new is None or tr is None:
            return
        tr.clips.append(new)
        tr.sort()
        self._select([new])
        self.refresh_all()
        self.status(f"Added '{new.name}' at {fmt_time(t)} on {tr.name}. Click it to change its settings.")

    def add_adjustment(self, track=None, effects=()):
        t = self.playhead
        dur = max(5.0, self.project.duration - t) if self.project.duration > t + 1 else 10.0
        tr = track if track is not None else self.tracks_of("hud")[-1]
        c = Clip(new_id("c"), "adjust", t, dur, "Effect layer", props={"opacity": 1.0, "anim_dur": 0.3})
        for ftype, params in effects:
            c.add_effect(ftype, params)
        tr.clips.append(c)
        tr.sort()
        return c

    def apply_look_payload(self, payload, whole=False):
        ftype = payload["name"]
        params = {"preset": payload["preset"]} if ftype == "look" and payload.get("preset") else None
        sel = [c for c in self.selected_clips() if c.kind in ("video", "image", "card", "adjust")]
        self.push_undo()
        if whole or not sel:
            c = self.add_adjustment(effects=[(ftype, params)])
            self._select([c])
            self.refresh_all()
            self.status("Added an effect layer: it changes everything below it from the playhead on. "
                        "Drag its edges to set when it starts and ends.")
            return
        for c in sel:
            c.add_effect(ftype, params)
        self.refresh_all()
        self.status(f"Added to {len(sel)} clip(s). Settings are in the Inspector.")

    def add_effect(self, ftype):
        sel = [c for c in self.selected_clips() if c.kind in ("video", "image", "card", "adjust")]
        if not sel:
            self.status("Select a video clip first (or use Looks → Apply to the whole picture).")
            return
        self.push_undo()
        for c in sel:
            c.add_effect(ftype)
        self.refresh_all()

    def remove_effect(self, fid):
        self.push_undo()
        for c in self.selected_clips():
            c.effects = [f for f in c.effects if f["id"] != fid]
            for k in [k for k in c.keyframes if k.startswith(f"fx.{fid}.")]:
                c.keyframes.pop(k)
        self.refresh_all()

    def set_transition(self, side, ttype):
        self.push_undo()
        for c in self.selected_clips():
            td = dict(getattr(c, f"transition_{side}") or {"duration": 0.5})
            td["type"] = ttype
            setattr(c, f"transition_{side}", td)
        self.refresh_all()

    def apply_pip(self, key):
        sel = [c for c in self.selected_clips() if c.kind in ("video", "image", "card")]
        if not sel:
            self.status("Select the clip that should become small (usually the GoPro on V2).")
            return
        presets = {
            "full": {"scale": 1.0, "x": 0.0, "y": 0.0, "mask": "none", "border": 0.0},
            "tr": {"scale": 0.32, "x": 0.31, "y": -0.3, "mask": "rounded", "border": 6.0, "border_color": "#ffffff"},
            "tl": {"scale": 0.32, "x": -0.31, "y": -0.3, "mask": "rounded", "border": 6.0, "border_color": "#ffffff"},
            "br": {"scale": 0.32, "x": 0.31, "y": 0.3, "mask": "rounded", "border": 6.0, "border_color": "#ffffff"},
            "bl": {"scale": 0.32, "x": -0.31, "y": 0.3, "mask": "rounded", "border": 6.0, "border_color": "#ffffff"},
            "minimap": {"scale": 0.34, "x": 0.37, "y": -0.29, "mask": "circle", "border": 8.0,
                        "border_color": "#55ff99"},
            "side_l": {"scale": 0.5, "x": -0.25, "y": 0.0, "mask": "none", "border": 0.0},
            "side_r": {"scale": 0.5, "x": 0.25, "y": 0.0, "mask": "none", "border": 0.0},
        }[key]
        self.push_undo()
        for c in sel:
            for k in ("scale", "x", "y"):
                c.keyframes.pop(k, None)
            c.props.update(presets)
        self.refresh_all()

    # ================================================================ cutting
    # ================================================================ whole-movie edits
    def toggle_insert_mode(self):
        self.insert_mode = self.insert_action.isChecked()
        self.status("Insert mode ON: a clip you add in the middle pushes everything after it later, on all tracks "
                    "(sounds, spells, HUD too)." if self.insert_mode else
                    "Insert mode OFF: added clips go on top / beside what is there.", 10000)

    def _insert_length(self, payload, track):
        kind = payload.get("type")
        if kind == "media":
            m = self.project.media.get(payload.get("id"))
            if m is None:
                return 0.0
            if m.kind == "video":
                return m.duration
            if m.kind == "image" and track is not None and track.kind == "video":
                return 5.0
        if kind == "card":
            return CARD_TYPES[payload["name"]]["duration"]
        return 0.0

    def set_mark_in(self):
        self.timeline.mark_in = self.playhead
        if self.timeline.mark_out is None or self.timeline.mark_out <= self.playhead:
            self.timeline.mark_out = None
        self.timeline.update()
        self.status("Start marked. Move to the end of the stretch and press O.")

    def set_mark_out(self):
        self.timeline.mark_out = self.playhead
        self.timeline.update()
        rng = self.timeline.marked_range()
        if rng:
            self.status(f"Marked {rng[1] - rng[0]:.2f} s. Ctrl+Shift+Delete removes it from every track.", 12000)
        else:
            self.status("End marked. Now mark the start with I.")

    def clear_marks(self):
        self.timeline.mark_in = self.timeline.mark_out = None
        self.timeline.update()

    def remove_marked_time(self):
        rng = self.timeline.marked_range()
        how = "marked"
        if rng is None:
            sel = self.selected_clips()
            if not sel:
                self.status("Mark a stretch first (I at the start, O at the end, or Shift+drag on the time ruler), "
                            "or select the pieces whose time you want to remove.", 12000)
                return
            rng = (min(c.start for c in sel), max(c.end for c in sel))
            how = "selected"
        a, b = rng
        self.push_undo()
        n = edit_ops.remove_time(self.project, a, b)
        locked = [t.name for t in self.project.tracks if t.locked]
        self.clear_marks()
        self.timeline.selected = []
        if self.playhead > b:
            self.playhead -= b - a
        elif self.playhead > a:
            self.playhead = a
        self.refresh_all()
        self.set_playhead(self.playhead)
        msg = f"Removed the {how} {b - a:.2f} s from every track and closed it up ({n} piece(s) changed)."
        if locked:
            msg += f" Locked tracks were left alone: {', '.join(locked)}."
        self.status(msg + " Ctrl+Z undoes it.", 15000)

    def insert_time_dialog(self):
        from PySide6.QtWidgets import QInputDialog
        rng = self.timeline.marked_range()
        dflt = round(rng[1] - rng[0], 2) if rng else 2.0
        sec, ok = QInputDialog.getDouble(self, "Insert empty time",
                                         "Seconds of empty time to insert at the red playhead.\n"
                                         "Everything after it, on every track, moves later:", dflt, 0.1, 600, 2)
        if ok:
            self.insert_time_at(self.playhead, sec)

    def insert_time_at(self, t, sec):
        self.push_undo()
        n = edit_ops.insert_time(self.project, t, sec)
        self.refresh_all()
        self.status(f"Inserted {sec:.2f} s at {fmt_time(t)}: {n} piece(s) moved or got longer. HUD elements and "
                    "looping music that were running there now run {sec:.2f} s longer.".replace("{sec:.2f}",
                                                                                                f"{sec:.2f}"), 12000)

    def group_selected(self):
        sel = self.selected_clips()
        if len(sel) < 2:
            self.status("Select two or more pieces first (Ctrl+click, or drag a box around them).")
            return
        self.push_undo()
        edit_ops.make_group(sel)
        self.refresh_all()
        self.status(f"Grouped {len(sel)} pieces: clicking one selects all, dragging moves them together. "
                    "Alt+click picks just one.", 12000)

    def ungroup_selected(self):
        sel = [c for c in self.selected_clips() if c.props.get("group")]
        if not sel:
            return
        self.push_undo()
        edit_ops.ungroup(sel)
        self.refresh_all()
        self.status(f"Ungrouped {len(sel)} pieces.")

    def _group_new(self, before_ids):
        """Pieces made by a one-click sequence stay together as a group."""
        new = [c for c in self.project.all_clips() if c.id not in before_ids]
        if len(new) > 1:
            edit_ops.make_group(new)

    def _split_clip(self, tr, c, t):
        """Cut clip c at movie time t. Returns the new right-hand piece."""
        return edit_ops.split_clip(tr, c, t)

    def split_at_playhead(self):
        t = round(self.playhead * self.project.fps) / self.project.fps
        sel = self.selected_clips()
        targets = []
        for tr in self.project.tracks:
            if tr.locked:
                continue
            for c in list(tr.clips):
                if c.start + 0.01 < t < c.end - 0.01 and (not sel or c in sel):
                    targets.append((tr, c))
        if not targets:
            self.status("Nothing under the red playhead to cut.")
            return
        self.push_undo()
        rights = [self._split_clip(tr, c, t) for tr, c in targets]
        self.timeline.selected = [r.id for r in rights if r is not None][:1]
        self.refresh_all()
        self.status(f"Cut {len(targets)} clip(s) at {fmt_time(t)}.")

    def delete_selected(self, ripple=False):
        sel = self.selected_clips()
        if not sel:
            return
        self.push_undo()
        for c in sel:
            tr = self.project.track_of(c.id)
            if tr is None:
                continue
            tr.clips.remove(c)
            if ripple:
                for o in tr.clips:
                    if o.start >= c.end - 1e-3:
                        o.start = round(o.start - c.duration, 4)
        self.timeline.selected = []
        self.refresh_all()

    def copy_selected(self):
        sel = self.selected_clips()
        if not sel:
            return
        t0 = min(c.start for c in sel)
        self.clipboard = [(self.project.track_of(c.id).id, c.start - t0, copy.deepcopy(asdict(c))) for c in sel]
        self.status(f"Copied {len(sel)} clip(s). Move the playhead and press Ctrl+V.")

    def paste(self, at=None):
        if not self.clipboard:
            return
        t = self.playhead if at is None else at
        self.push_undo()
        if self.insert_mode and any(d["kind"] in ("video", "image", "card") for _, _, d in self.clipboard):
            span = max(off + d["duration"] for _, off, d in self.clipboard)
            edit_ops.insert_time(self.project, t, span)
        new = []
        for tid, off, d in self.clipboard:
            c = Clip(**copy.deepcopy(d))
            c.id = new_id("c")
            c.start = round(t + off, 4)
            tr = self.project.track(tid)
            if tr is None:
                kind = {"audio": "audio", "hud": "hud", "adjust": "hud"}.get(c.kind, "video")
                tr = self.tracks_of(kind)[0]
            tr.clips.append(c)
            tr.sort()
            new.append(c)
        edit_ops.renew_groups(new)
        self._select(new)
        self.refresh_all()

    def select_all(self):
        self.timeline.selected = [c.id for c in self.project.all_clips()]
        self._on_selection()
        self.timeline.update()
        self.status(f"Selected all {len(self.timeline.selected)} clips. Drag one of them to move everything.")

    def find_gap(self, t, track=None):
        """Empty stretch around time t: (start, end), or None. With a track,
        only that track counts; otherwise it must be empty on every track."""
        clips = list(track.clips) if track is not None else list(self.project.all_clips())
        if not clips or any(c.start - 1e-4 <= t < c.end - 1e-4 for c in clips):
            return None
        after = [c.start for c in clips if c.start >= t - 1e-4]
        if not after:
            return None                     # nothing after it: not a gap, just the end
        before = [c.end for c in clips if c.end <= t + 1e-4]
        g0, g1 = (max(before) if before else 0.0), min(after)
        return (g0, g1) if g1 - g0 > 0.01 else None

    def close_gap(self, t, track=None):
        g = self.find_gap(t, track)
        if g is None:
            self.status("No empty gap here (something is on a track at this moment)." if track is None else
                        "No empty gap on this track here.")
            return
        g0, g1 = g
        shift = g1 - g0
        self.push_undo()
        tracks = [track] if track is not None else self.project.tracks
        n = 0
        for tr in tracks:
            for c in tr.clips:
                if c.start >= g1 - 1e-4:
                    c.start = round(c.start - shift, 4)
                    n += 1
        if self.playhead >= g1:
            self.playhead = max(0.0, self.playhead - shift)
        self.refresh_all()
        self.set_playhead(self.playhead)
        where = "on all tracks" if track is None else f"on '{track.name}'"
        self.status(f"Closed a {shift:.2f} s gap {where}: {n} clip(s) moved left. Ctrl+Z undoes it.", 10000)

    def duplicate_selected(self):
        sel = self.selected_clips()
        if not sel:
            return
        self.copy_selected()
        self.paste(at=max(c.end for c in sel))

    def toggle_enabled(self):
        sel = self.selected_clips()
        if not sel:
            return
        self.push_undo()
        for c in sel:
            c.enabled = not c.enabled
        self.refresh_all()

    def toggle_clip_mute(self):
        sel = [c for c in self.selected_clips() if c.kind == "video"]
        if not sel:
            return
        self.push_undo()
        for c in sel:
            c.props["mute"] = not c.props.get("mute", False)
        self.refresh_all()

    # ================================================================ cameras
    def switch_angle(self):
        t = round(self.playhead * self.project.fps) / self.project.fps
        vids = self.tracks_of("video")      # top first
        upper = None
        for i, tr in enumerate(vids):
            cands = [c for c in tr.clips if c.start - 1e-3 <= t < c.end]
            if not cands:
                continue
            lower_has = any(any(c.start <= t < c.end and c.enabled for c in tr2.clips) for tr2 in vids[i + 1:])
            if lower_has:
                upper = (tr, max(cands, key=lambda c: c.start))
                break
        if upper is None:
            self.status("Switching needs two cameras stacked at the playhead (one on V1, one on V2).")
            return
        tr, c = upper
        self.push_undo()
        piece = c if abs(c.start - t) < 0.02 else self._split_clip(tr, c, t)
        if piece is None:
            piece = c
        piece.enabled = not piece.enabled
        self.refresh_all()
        shown = "the lower camera" if not piece.enabled else f"'{piece.name}'"
        self.status(f"From {fmt_time(t)} you now see {shown}. Press A again later to switch back.")

    def sync_selected(self):
        sel = [c for c in self.selected_clips() if c.kind in ("video", "audio")]
        if len(sel) != 2:
            self.status("Select exactly two clips first: click one, then Ctrl+click the other (they need sound).")
            return

        def depth(c):
            tr = self.project.track_of(c.id)
            return self.project.tracks.index(tr)
        a, b = sorted(sel, key=depth, reverse=True)    # a = lower track (reference)
        ma, mb = self.project.media.get(a.media_id), self.project.media.get(b.media_id)
        self.status("Listening to both clips to line them up…", 30000)
        proj = self.project

        def work():
            aa, ab = load_audio(proj, ma), load_audio(proj, mb)
            if aa is None or ab is None:
                self.call_in_gui(lambda: QMessageBox.information(
                    self, "Sync", "Both clips need sound. One of them has no audio track."))
                return
            lag, conf = audiomod.find_offset(np.asarray(aa), np.asarray(ab))

            def apply():
                if self.project.clip(a.id) is None or self.project.clip(b.id) is None:
                    return
                aa_, bb_ = self.project.clip(a.id), self.project.clip(b.id)
                self.push_undo()
                new_start = aa_.start - aa_.source_in + bb_.source_in + lag
                if new_start < 0:
                    cut = -new_start
                    bb_.source_in += cut
                    bb_.duration = max(0.1, bb_.duration - cut)
                    new_start = 0.0
                bb_.start = round(new_start, 4)
                if bb_.kind == "video" and aa_.kind == "video":
                    bb_.props["mute"] = True
                self.refresh_all()
                word = "good" if conf > 0.5 else ("fair" if conf > 0.2 else "weak — please check")
                msg = (f"Synced '{bb_.name}' to '{aa_.name}' (moved {lag:+.2f} s, match: {word}). "
                       f"Its own sound was muted to avoid an echo.")
                self.status(msg, 15000)
                if conf <= 0.2:
                    QMessageBox.information(self, "Sync", msg + "\n\nThe sounds didn't match clearly. Play it and "
                                            "nudge the clip by dragging if needed. A clap at the start of each take helps.")
            self.call_in_gui(apply)
        self.run_bg(work)

    def freeze_frame(self, length=3.0):
        t = round(self.playhead * self.project.fps) / self.project.fps
        target = None
        sel = [c for c in self.selected_clips() if c.kind == "video" and c.start <= t < c.end]
        if sel:
            target = sel[0]
        else:
            for tr in self.tracks_of("video"):
                c = tr.clip_at(t)
                if c is not None and c.kind == "video":
                    target = c
                    break
        if target is None:
            self.status("Put the red playhead over a video clip first.")
            return
        self.push_undo()
        ttr = self.project.track_of(target.id)
        src_t = target.source_in + (t - target.start) * float(target.props.get("speed", 1.0) or 1.0)
        # make room: everything after t moves later
        for tr in self.project.tracks:
            for c in list(tr.clips):
                if c.start >= t - 1e-4:
                    c.start = round(c.start + length, 4)
                elif c.end > t + 1e-4:
                    if tr.kind == "hud":
                        rel = t - c.start
                        c.duration = round(c.duration + length, 4)
                        for keys in c.keyframes.values():
                            for k in keys:
                                if k[0] > rel:
                                    k[0] += length
                    else:
                        r = self._split_clip(tr, c, t)
                        if r is not None:
                            r.start = round(r.start + length, 4)
        fz = Clip(new_id("c"), "video", t, length, "Freeze: " + target.name, target.media_id, source_in=src_t,
                  freeze=True, props=copy.deepcopy(target.props))
        fz.keyframes = {}
        fz.add_effect("color", {"saturation": 0.55, "brightness": -0.06, "contrast": 1.1})
        fz.add_effect("vignette", {"strength": 0.75, "size": 0.75})
        fz.transition_in = {"type": "dip_white", "duration": 0.2}
        ttr.clips.append(fz)
        ttr.sort()
        pr = hud_defaults("character_card")
        pr["style"] = self.bin.default_style()
        card = Clip(new_id("c"), "hud", t, length, "Character card", hud_type="character_card", props=pr)
        self.tracks_of("hud")[-1].clips.append(card)
        sfx = self._game_sound_media("menu_select")
        str_ = self.find_track("audio", t, t + sfx.duration, self.sfx_track(), create_name="A  Game sounds 2")
        str_.clips.append(Clip(new_id("c"), "audio", t, sfx.duration, sfx.name, sfx.id))
        self._select([card])
        self.refresh_all()
        self.status("Frozen for 3 s with a character card. Type the name and stats in the Inspector.")

    def stabilize_selected(self):
        from ..media import stabilize
        sel = [c for c in self.selected_clips() if c.kind == "video" and c.media_id]
        if not sel:
            self.status("Select a video clip first (usually the GoPro).")
            return
        m = self.project.media.get(sel[0].media_id)
        if m is None:
            return
        if QMessageBox.question(self, "Steady shaky footage",
                                f"Make a steadier copy of '{m.name}'?\n\nThis runs in the background on the CPU and "
                                f"takes roughly {int(m.duration // 60) + 1} min or more. You can keep editing. "
                                "When it's done, every clip that uses this file switches to the steady copy "
                                "(Undo switches back).") != QMessageBox.StandardButton.Yes:
            return
        proj = self.project
        state = {"p": 0.0}

        def prog(f):
            state["p"] = f
            self.call_in_gui(lambda: self.status(f"Steadying '{m.name}'… {int(f * 100)}%", 5000))

        def work():
            out = stabilize(proj, m, prog)

            def done():
                if not out:
                    QMessageBox.warning(self, "Steady footage", "Stabilising failed.")
                    return
                nm = probe(out)
                nm = self.project.add_media(nm)
                self._post_import(nm)
                self.push_undo()
                n = 0
                for c in self.project.all_clips():
                    if c.media_id == m.id:
                        c.media_id = nm.id
                        n += 1
                self.refresh_all()
                self.status(f"Done: {n} clip(s) now use the steady copy '{nm.name}'.", 15000)
            self.call_in_gui(done)
        self.run_bg(work)

    # ================================================================ spell event
    def bar_targets(self):
        """Health bars (and name tags) that spells can hit. Gives each one a
        permanent 'bar_key' so links survive cutting, moving and copying."""
        out = []
        for tr in self.tracks_of("hud"):
            for c in sorted(tr.clips, key=lambda c: c.start):
                if c.hud_type not in BAR_TYPES:
                    continue
                if not c.props.get("bar_key"):
                    c.props["bar_key"] = new_id("bar")
                who = (c.props.get("label") or c.props.get("name") or c.props.get("enemy") or
                       c.props.get("name_right") or "")
                kind = HUD_TYPES.get(c.hud_type, {}).get("label", c.hud_type).split(" (")[0]
                lab = f"{kind} '{who}'" if who else f"{kind} ({c.name})"
                out.append((c, f"{lab}  ({fmt_time(c.start)}–{fmt_time(c.end)})"))
        # one entry per bar_key (cut pieces of the same bar share a key)
        seen, uniq = set(), []
        for c, lab in out:
            if c.props["bar_key"] not in seen:
                seen.add(c.props["bar_key"])
                uniq.append((c, lab))
        return uniq

    def spells(self):
        return [c for c in self.project.all_clips() if c.kind == "hud" and c.hud_type == "spell"]

    def link_spells(self, bar_clip_id, only_unlinked=True):
        bar = self.project.clip(bar_clip_id)
        if bar is None:
            return
        self.push_undo()
        if not bar.props.get("bar_key"):
            bar.props["bar_key"] = new_id("bar")
        n = 0
        for sp in self.spells():
            if only_unlinked and sp.props.get("target_bar"):
                continue
            sp.props["target_bar"] = bar.props["bar_key"]
            if not float(sp.props.get("damage_amount", 0) or 0):
                sp.props["damage_amount"] = 35.0
            n += 1
        self.refresh_all()
        self.status(f"{n} spell(s) now hit this bar. Change each spell's damage in its own settings.", 10000)

    def spell_wizard(self):
        targets = self.bar_targets()
        targets.sort(key=lambda x: (not x[0].contains(self.playhead), x[0].start))
        dlg = SpellDialog(self, [(c.id, lab) for c, lab in targets])
        if dlg.exec():
            self.create_spell(dlg.values())

    def create_spell(self, v):
        t = self.playhead
        self.push_undo()
        before = {c.id for c in self.project.all_clips()}
        pr = hud_defaults("spell")
        pr.update({"spell_name": v["name"], "style": v["style"], "color": v["color"], "hit_time": v["hit_time"],
                   "damage_amount": float(v["damage"]), "damage": "", "shake": v["shake"], "flash": v["flash"]})
        target = self.project.clip(v["target"]) if v["target"] else None
        if target is not None:
            if not target.props.get("bar_key"):
                target.props["bar_key"] = new_id("bar")
            pr["target_bar"] = target.props["bar_key"]
            if target.hud_type == "name_tag":
                rel = t - target.start
                pr["target_x"] = float(target.value("x", rel, 0.7))
                pr["target_y"] = min(0.95, float(target.value("y", rel, 0.4)) + 0.12)
        dur = v["hit_time"] + 1.6
        huds = self.tracks_of("hud")
        tr = self.find_track("hud", t, t + dur, huds[0]) or huds[0]
        spell = Clip(new_id("c"), "hud", t, dur, "Spell: " + v["name"], hud_type="spell", props=pr)
        tr.clips.append(spell)
        tr.sort()
        for name, at in ((v["cast_sound"], t), (v["hit_sound"], t + v["hit_time"])):
            if not name:
                continue
            m = self._game_sound_media(name)
            atr = self.find_track("audio", at, at + m.duration, self.sfx_track(), create_name="A  Game sounds 2")
            atr.clips.append(Clip(new_id("c"), "audio", round(at, 4), m.duration, m.name, m.id))
            atr.sort()
        self._select([spell])
        self._group_new(before)
        self.refresh_all()
        tip = "" if target is not None else " No health bar yet? Add one later and click 'Link spells' in its settings."
        self.status("Spell created. Drag the C (caster) and T (target) dots in the preview into place." + tip, 15000)

    def snapshot_media(self, t=None):
        """Saves the video picture at time t (no HUD) as a PNG in the project and returns its media id."""
        import cv2
        from ..media import MediaPool
        from ..renderer import Renderer
        snap = self.project.clone()
        for tr in snap.tracks:
            if tr.kind == "hud":
                tr.hidden = True
        pool = MediaPool(snap, use_proxies=False)
        try:
            img = Renderer(snap, pool, preview=False).render(self.playhead if t is None else t,
                                                             self.project.width, self.project.height)
        finally:
            pool.close()
        folder = os.path.join(self.project.folder or cache_dir(None), "portraits")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, time.strftime("portrait_%Y%m%d_%H%M%S") + f"_{int(time.time() * 1000) % 1000:03d}.png")
        ok, data = cv2.imencode(".png", img[..., ::-1])
        if not ok:
            return None
        data.tofile(path)
        m = self.project.add_media(probe(path))
        self._post_import(m)
        return m.id

    def grab_portrait(self, clip_id, prop=None):
        """Uses the current video picture as the clip's portrait (or as the picture in props[prop]);
        the yellow 'face' dot then picks the face."""
        c = self.project.clip(clip_id)
        if c is None:
            return
        self.push_undo()
        mid = self.snapshot_media()
        if mid is None:
            return
        if prop:
            c.props[prop] = mid
            if prop == "media2":
                c.props.update({"pic2_x": 0.5, "pic2_y": 0.45, "pic2_size": 0.8})
            self.refresh_all()
            self.status("Picture taken from this frame. Drag its yellow dot onto the person.", 8000)
            return
        c.media_id = mid
        c.props.update({"portrait_x": 0.5, "portrait_y": 0.4, "portrait_size": 0.35})
        self.refresh_all()
        self.status("Picture taken from this frame. Drag the yellow 'face' dot onto the person; "
                    "use the zoom setting to frame them.", 15000)

    def add_picture_file(self, path):
        """Imports one picture now (not in the background) and returns its media id."""
        m = self.project.add_media(probe(path))
        self._post_import(m)
        return m.id

    def choose_picture(self, clip_id, prop=None):
        exts = " ".join("*" + e for e in sorted(IMAGE_EXT)) + " " + " ".join("*" + e.upper() for e in sorted(IMAGE_EXT))
        path, _ = QFileDialog.getOpenFileName(self, "Choose a picture", self.project.folder, f"Pictures ({exts})")
        if not path:
            return
        c = self.project.clip(clip_id)
        if c is None:
            return
        mid = self.add_picture_file(path)
        self.push_undo()
        if prop:
            c.props[prop] = mid
        else:
            c.media_id = mid
            c.props.update({"portrait_x": 0.5, "portrait_y": 0.5, "portrait_size": 1.0})
        self.refresh_all()

    def set_portrait_media(self, clip_id, media_id):
        c = self.project.clip(clip_id)
        if c is None:
            return
        self.push_undo()
        c.media_id = media_id or None
        if media_id:
            c.props.update({"portrait_x": 0.5, "portrait_y": 0.5, "portrait_size": 1.0})
        self.refresh_all()

    # ================================================================ creature battles (Pokémon style)
    def _hud_at(self, hud_type, t, dur, props, name=None, top=False):
        pr = hud_defaults(hud_type)
        pr.update(props)
        huds = self.tracks_of("hud")
        pref = huds[0] if top else None
        tr = self.find_track("hud", t, t + dur, pref)
        if tr is None:
            tr = self.add_track("hud", f"HUD {len(huds) + 1}", refresh=False)
        c = Clip(new_id("c"), "hud", round(t, 4), dur, name or HUD_TYPES[hud_type]["label"].split(" (")[0],
                 hud_type=hud_type, props=pr)
        tr.clips.append(c)
        tr.sort()
        return c

    def _sound_at(self, name, t, loop_dur=None):
        m = self._game_sound_media(name)
        pref = self.music_track() if name.startswith("music_") else self.sfx_track()
        dur = loop_dur or m.duration
        tr = self.find_track("audio", t, t + dur, pref, create_name="A  Game sounds 2")
        c = Clip(new_id("c"), "audio", round(t, 4), dur, m.name, m.id)
        if loop_dur:
            c.props.update({"loop": True, "fade_out": 1.5, "volume": 0.6})
        tr.clips.append(c)
        tr.sort()
        return c

    def battle_combo(self):
        from .dialogs import BattleDialog
        dlg = BattleDialog(self)
        if not dlg.exec():
            return
        v = dlg.values()
        t = self.playhead
        self.push_undo()
        before = {c.id for c in self.project.all_clips()}
        enc = 3.4 if v["wipe"] == "vs" else 2.2
        self._hud_at("pk_encounter", t, enc, {"wipe": v["wipe"], "left_name": v["player"], "right_name": v["enemy"]},
                     top=True)
        self._sound_at("battle_start", t)
        b = t + enc - 0.5
        length = v["length"]
        enemy = self._hud_at("pk_hpbox", b, length, {"side": "enemy", "name": v["enemy"].upper(),
                                                     "level": v["enemy_level"], "x": 0.25, "y": 0.14,
                                                     "anim_in": "slide_right", "anim_dur": 0.5})
        self._hud_at("pk_hpbox", b + 0.4, length - 0.4, {"side": "player", "name": v["player"].upper(),
                                                         "level": v["player_level"], "x": 0.72, "y": 0.6,
                                                         "anim_in": "slide_left", "anim_dur": 0.5})
        intro = v["intro"].replace("{enemy}", v["enemy"].upper())
        self._hud_at("pk_text", b + 0.3, 3.0, {"text": intro})
        self._hud_at("pk_menu", b + 3.4, 4.0, {"mode": "commands",
                                               "prompt": f"What will {v['player'].upper()} do?"})
        if v["music"]:
            self._sound_at("music_boss_battle", b, loop_dur=length)
        enemy.props["bar_key"] = new_id("bar")
        self._select([enemy])
        self._group_new(before)
        self.refresh_all()
        self.status("Battle placed. Spells (E) can now target the enemy's HP box. Move the boxes by dragging their "
                    "yellow dots.", 15000)

    def _place_plan(self, plan, t):
        """Turn a plan from rs_combos into clips; '@tag' bar targets become real bar keys."""
        keys, made = {}, {}
        for item in plan:
            if item[0] == "hud" and item[1] in BAR_TYPES:
                keys.setdefault(item[5], new_id("bar"))
        for item in plan:
            if item[0] == "sound":
                _, name, st, loop = item
                self._sound_at(name, t + st, loop_dur=loop)
                continue
            _, ht, st, dur, props, tag = item
            props = dict(props)
            kf = props.pop("_keys", None)
            if ht in BAR_TYPES:
                props["bar_key"] = keys[tag]
            tb = props.get("target_bar", "")
            if isinstance(tb, str) and tb.startswith("@"):
                props["target_bar"] = keys.get(tb[1:], "")
            c = self._hud_at(ht, t + st, dur, props, name=props.get("label") or props.get("name") or None,
                             top=ht in ("rs_hitsplat", "rs_xpdrop"))
            if kf:
                c.keyframes.update({k: [list(x) for x in v] for k, v in kf.items()})
            made.setdefault(tag, []).append(c)
        return made

    def quest_talk_combo(self):
        from ..rs_combos import plan_quest_talk
        from .dialogs import QuestTalkDialog
        dlg = QuestTalkDialog(self)
        if not dlg.exec():
            return
        plan, length = plan_quest_talk(dlg.values())
        self.push_undo()
        before = {c.id for c in self.project.all_clips()}
        made = self._place_plan(plan, self.playhead)
        first = (made.get("npc") or [None])[0]
        if first:
            self._select([first])
        self._group_new(before)
        self.refresh_all()
        self.status(f"Quest conversation placed ({length:.0f} s). Select an NPC box and use 'Face picture' to add "
                    "the NPC's face. Change any text in the right panel.", 15000)

    def fight_combo(self):
        from ..rs_combos import plan_fight
        from .dialogs import FightDialog
        dlg = FightDialog(self)
        if not dlg.exec():
            return
        plan, st = plan_fight(dlg.values())
        self.push_undo()
        before = {c.id for c in self.project.all_clips()}
        made = self._place_plan(plan, self.playhead)
        self._select(made.get("enemy_bar", []) + made.get("player_bar", []))
        self._group_new(before)
        self.refresh_all()
        self.status(f"Fight placed: {st['rounds']} attacks, {st['length']:.0f} s. Drag each health bar's yellow dot "
                    "over a fighter's head (keyframe it if they move); the damage splats follow the bars.", 20000)

    def _picture_from(self, choice):
        if choice["mode"] == "file" and choice["path"]:
            return self.add_picture_file(choice["path"])
        if choice["mode"] == "frame":
            return self.snapshot_media()
        return ""

    def whos_combo(self):
        from .dialogs import WhosDialog
        dlg = WhosDialog(self)
        if not dlg.exec():
            return
        v = dlg.values()
        t = self.playhead
        self.push_undo()
        before = {c.id for c in self.project.all_clips()}
        mid = self._picture_from(v["pic"])
        dur = v["reveal"] + v["after"]
        c = self._hud_at("pk_whos", t, dur, {"name": v["name"], "question": v["question"], "answer": v["answer"],
                                             "reveal_time": v["reveal"],
                                             "background": "rays" if v["rays"] else "none"}, top=True)
        c.media_id = mid or None
        if v["pic"]["mode"] == "frame":
            c.props.update({"portrait_x": 0.5, "portrait_y": 0.45, "portrait_size": 0.8})
        self._sound_at("whos_question", t + 0.3)
        self._sound_at("whos_reveal", t + v["reveal"])
        self._select([c])
        self._group_new(before)
        self.refresh_all()
        self.status("'Who's that …?' placed. Drag the yellow 'face' dot onto the person and set 'Picture zoom' so "
                    "only they are in the square; the silhouette updates by itself.", 20000)

    def evolve_combo(self):
        from .dialogs import EvolveDialog
        dlg = EvolveDialog(self)
        if not dlg.exec():
            return
        v = dlg.values()
        t = self.playhead
        self.push_undo()
        before = {c.id for c in self.project.all_clips()}
        mid_a = self._picture_from(v["pic_a"])
        mid_b = self._picture_from(v["pic_b"])
        c = self._hud_at("pk_evolve", t, 11.0, {"name": v["name_a"], "name2": v["name_b"], "result": v["result"],
                                                "media2": mid_b or ""}, top=True)
        if v["pic_b"]["mode"] == "frame":
            c.props.update({"pic2_x": 0.5, "pic2_y": 0.45, "pic2_size": 0.8})
        c.media_id = mid_a or None
        if v["pic_a"]["mode"] == "frame":
            c.props.update({"portrait_x": 0.5, "portrait_y": 0.45, "portrait_size": 0.8})
        self._sound_at("text_blip", t + 0.2)
        self._sound_at("evolve", t + 2.0)
        self._sound_at("evolve_done" if v["result"] == "evolves" else "catch_fail", t + 7.0)
        self._select([c])
        self._group_new(before)
        self.refresh_all()
        self.status("Evolution placed. Drag the yellow 'face' dot onto the person; set the 'After: picture' in the "
                    "right panel if you chose 'later'.", 20000)

    def capture_combo(self):
        from .dialogs import CaptureDialog
        dlg = CaptureDialog(self)
        if not dlg.exec():
            return
        v = dlg.values()
        t = self.playhead
        self.push_undo()
        before = {c.id for c in self.project.all_clips()}
        shakes = v["shakes"]
        dur = 0.8 + 0.9 + 0.5 + shakes * 0.9 + 1.6
        cap = self._hud_at("pk_capture", t, dur, {"shakes": float(shakes), "result": v["result"],
                                                  "target_x": v["tx"], "target_y": v["ty"]}, top=True)
        self._sound_at("tube_throw", t)
        self._sound_at("spell_cast", t + 0.8)
        for k in range(shakes):
            self._sound_at("tube_wobble", t + 2.2 + k * 0.9)
        end = t + 2.2 + shakes * 0.9
        if v["result"] == "caught":
            self._sound_at("catch_success", end)
            msg = v["caught_text"].replace("{name}", v["name"].upper())
        else:
            self._sound_at("catch_fail", end)
            msg = v["fail_text"].replace("{name}", v["name"].upper())
        self._hud_at("pk_text", end + 0.1, 3.0, {"text": msg})
        self._select([cap])
        self._group_new(before)
        self.refresh_all()
        self.status("Catch placed. Drag the T dot onto the person being caught, and 'throw from' onto the thrower.",
                    15000)

    # ================================================================ voice-over
    def record_voice(self):
        if AUDIO["checked"] and AUDIO["inputs"] == 0:
            QMessageBox.information(self, "Record voice-over", "No microphone was found on this computer.\n\n"
                                    "You can record on your phone or laptop and import the file instead "
                                    "(it goes on the voice-over track).")
            return
        if not self.project.path:
            if QMessageBox.question(self, "Save first", "Recordings are kept next to the project file. "
                                    "Save the project now?") != QMessageBox.StandardButton.Yes:
                return
            if not self.save_as():
                return
        self.stop_playback()
        RecorderDialog(self).exec()

    def new_voice_path(self):
        folder = os.path.join(self.project.folder or cache_dir(None), "voiceovers")
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, time.strftime("voice_%Y%m%d_%H%M%S.wav"))

    def add_voice_clip(self, path, t):
        m = self.project.add_media(probe(path))
        self.push_undo()
        tr = self.voice_track()
        if not self._free(tr, t, t + m.duration):
            tr = self.add_track("audio", "A  Voice-over 2", refresh=False)
            tr.is_voice = True
        c = Clip(new_id("c"), "audio", t, m.duration, "Voice-over", m.id)
        tr.clips.append(c)
        tr.sort()
        self.refresh_all()

    # ================================================================ files
    def _confirm_discard(self):
        if not self.dirty:
            return True
        r = QMessageBox.question(self, "Unsaved changes", "Save changes to the current project?",
                                 QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard |
                                 QMessageBox.StandardButton.Cancel)
        if r == QMessageBox.StandardButton.Save:
            return self.save()
        return r == QMessageBox.StandardButton.Discard

    def _set_project(self, p):
        self.stop_playback()
        self.project = p
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.thumbs.clear()
        self.timeline.selected = []
        self.timeline._peaks.clear()
        self.playhead = 0.0
        self.timeline.set_playhead(0.0, emit=False)
        self.inspector.show_nothing()
        self.worker.pool.proxy_ready.clear()
        self.worker.set_project(p.clone())
        self.dirty = False
        for m in p.media.values():
            if os.path.exists(m.path) and not m.generated:
                self._post_import(m)
        self.refresh_all()
        self.dirty = False
        self._update_title()
        QTimer.singleShot(100, self.timeline.zoom_to_fit)

    def new_project(self):
        if not self._confirm_discard():
            return
        self._set_project(Project.new_default())

    def open_project(self, path=None):
        if path is None:
            if not self._confirm_discard():
                return
            path, _ = QFileDialog.getOpenFileName(self, "Open project", self.project.folder,
                                                  f"QuestCut project (*{PROJECT_EXT})")
            if not path:
                return
        try:
            p = Project.load(path)
        except Exception as e:
            QMessageBox.warning(self, "Open", f"Could not open the project:\n{e}")
            return
        self.project = p
        self._regenerate_sounds()
        missing = p.missing_media()
        if missing:
            names = "\n".join(os.path.basename(m.path.replace("\\", "/")) for m in missing[:12])
            QMessageBox.information(self, "Find missing files",
                                    f"{len(missing)} file(s) are not where they used to be:\n\n{names}\n\n"
                                    "Pick the folder that contains them (subfolders are searched too).")
            folder = QFileDialog.getExistingDirectory(self, "Folder with the missing files", p.folder)
            if folder:
                n = relink_media(p, folder)
                self.status(f"Found {n} of {len(missing)} missing file(s).")
        self._set_project(p)
        if p.missing_media():
            self.dirty = True
            self._update_title()

    def save(self):
        if not self.project.path:
            return self.save_as()
        try:
            self.project.save()
        except Exception as e:
            QMessageBox.warning(self, "Save", f"Could not save:\n{e}")
            return False
        self.dirty = False
        self._update_title()
        self.status("Saved " + self.project.path, 3000)
        return True

    def save_as(self):
        start = self.project.path or os.path.join(os.path.expanduser("~"), "My PhD Movie" + PROJECT_EXT)
        path, _ = QFileDialog.getSaveFileName(self, "Save project as", start, f"QuestCut project (*{PROJECT_EXT})")
        if not path:
            return False
        if not path.endswith(PROJECT_EXT):
            path += PROJECT_EXT
        old_has_path = bool(self.project.path)
        self.project.path = os.path.abspath(path)
        if not old_has_path:
            # game sounds made before the first save live in a temp folder: move them next to the project
            for m in self.project.media.values():
                if m.generated.startswith("sfx:"):
                    m.path = self.game_sound_path(m.generated[4:])
            self.worker.set_project(self.project.clone())
        return self.save()

    def combine_projects(self):
        from .dialogs import CombineDialog
        dlg = CombineDialog(self)
        if not dlg.exec():
            return
        v = dlg.values()
        if not v["paths"]:
            return
        loaded, problems = [], []
        for path in v["paths"]:
            try:
                p = Project.load(path)
            except Exception as e:
                problems.append(f"{os.path.basename(path)}: could not open ({e})")
                continue
            loaded.append((path, p))
        if not loaded:
            QMessageBox.warning(self, "Combine", "\n".join(problems) or "Nothing to add.")
            return
        self.push_undo()
        if not v["keep"]:
            for tr in self.project.tracks:
                tr.clips = []
        offset = self.project.duration + (v["gap"] if self.project.duration > 0 else 0.0)
        report = []
        for path, p in loaded:
            for m in p.media.values():
                if m.generated.startswith("sfx:") and not os.path.exists(m.path):
                    m.path = self.game_sound_path(m.generated[4:])
            missing = p.missing_media()
            if missing:
                problems.append(f"{os.path.basename(path)}: {len(missing)} file(s) not found "
                                "(use Open on that project once to relink them)")
            if (p.width, p.height, p.fps) != (self.project.width, self.project.height, self.project.fps):
                problems.append(f"{os.path.basename(path)}: made at {p.width}×{p.height}, {p.fps:g} fps; "
                                f"it now uses this project's {self.project.width}×{self.project.height}, "
                                f"{self.project.fps:g} fps")
            dur = p.duration
            r = append_project(self.project, p, offset)
            report.append(f"• {os.path.basename(path)}: starts at {offset:.1f} s, {dur:.1f} s long, "
                          f"{r['clips']} clips")
            offset += dur + v["gap"]
        for m in self.project.media.values():
            if os.path.exists(m.path) and not m.generated and m.id not in self.thumbs:
                self._post_import(m)
        self.refresh_all()
        self.timeline.zoom_to_fit()
        msg = "Combined:\n" + "\n".join(report)
        if problems:
            msg += "\n\nPlease check:\n" + "\n".join("• " + x for x in problems)
        msg += "\n\nSave the result with File → Save as… (Ctrl+Z undoes the whole combine)."
        QMessageBox.information(self, "Combine projects", msg)

    def pack_project(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose an EMPTY folder to pack the project into")
        if not folder:
            return
        if os.listdir(folder) and QMessageBox.question(
                self, "Folder not empty", "The folder is not empty. Use it anyway?") != QMessageBox.StandardButton.Yes:
            return
        p = self.project.clone()
        media_dir = os.path.join(folder, "media")
        os.makedirs(media_dir, exist_ok=True)
        files = [m for m in p.media.values() if os.path.exists(m.path)]
        dlg = QProgressDialog("Copying files…", "Cancel", 0, len(files), self)
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.show()
        used = set()
        for i, m in enumerate(files):
            if dlg.wasCanceled():
                return
            dlg.setValue(i)
            dlg.setLabelText(f"Copying {os.path.basename(m.path)}…")
            QApplication.processEvents()
            sub = "game_sounds" if m.generated else ("voiceovers" if "voiceovers" in m.path else "media")
            dst_dir = os.path.join(folder, sub)
            os.makedirs(dst_dir, exist_ok=True)
            base = os.path.basename(m.path)
            name, ext = os.path.splitext(base)
            k = 1
            while (sub, base.lower()) in used:
                base = f"{name}_{k}{ext}"
                k += 1
            used.add((sub, base.lower()))
            dst = os.path.join(dst_dir, base)
            if os.path.abspath(dst) != os.path.abspath(m.path):
                shutil.copy2(m.path, dst)
            m.path = dst
        dlg.setValue(len(files))
        name = os.path.splitext(os.path.basename(self.project.path or "My PhD Movie"))[0]
        p.save(os.path.join(folder, name + PROJECT_EXT))
        if QMessageBox.question(self, "Packed", f"Everything is in:\n{folder}\n\nCopy this whole folder to the other "
                                "computer and open the .questcut file there.\n\nSwitch to the packed copy now?") == \
                QMessageBox.StandardButton.Yes:
            self.open_project(p.path)

    def _autosave(self):
        if self.dirty and self.project.path:
            try:
                d = Project.from_dict(self.project.to_dict())
                d.path = self.project.path
                tmp = d.path
                d.path = tmp.replace(PROJECT_EXT, ".autosave" + PROJECT_EXT)
                d.save()
            except Exception as e:
                print("autosave failed", e)

    def export(self):
        self.stop_playback()
        if self.project.duration <= 0:
            QMessageBox.information(self, "Export", "The timeline is empty.")
            return
        ExportDialog(self).exec()

    def export_still(self):
        from ..export import export_still
        base = os.path.join(self.project.folder or os.path.expanduser("~"), f"frame_{fmt_time(self.playhead).replace(':', '-')}.png")
        path, _ = QFileDialog.getSaveFileName(self, "Save picture", base, "PNG picture (*.png);;JPEG picture (*.jpg)")
        if path:
            ok = export_still(self.project, self.playhead, path, self.project.width, self.project.height)
            self.status(("Saved " + path) if ok else "Could not save the picture.")

    def reveal_file(self, path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(os.path.abspath(path))))

    def show_gpu_info(self):
        GpuInfoDialog(self).exec()

    def create_practice_project(self):
        if not self._confirm_discard():
            return
        base = os.path.join(os.path.expanduser("~"), "QuestCut Practice")
        folder = QFileDialog.getExistingDirectory(self, "Where should the practice project go?",
                                                  os.path.expanduser("~")) or ""
        if not folder:
            return
        folder = os.path.join(folder, "QuestCut Practice")
        dlg = QProgressDialog("Making two practice 'camera' videos…", None, 0, 100, self)
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.show()
        result = {}

        def work():
            from ..demo import make_practice_project
            try:
                result["path"] = make_practice_project(folder, lambda f: self.call_in_gui(lambda: dlg.setValue(int(f * 100))))
            except Exception as e:
                result["error"] = str(e)
            self.call_in_gui(finish)

        def finish():
            dlg.close()
            if "error" in result:
                QMessageBox.warning(self, "Practice project", result["error"])
                return
            self.open_project(result["path"])
            self.right_tabs.setCurrentIndex(1)
            self.guide.combo.setCurrentIndex(1)
            self.status("Practice project ready. Follow the lessons in the Guide tab.")
        self.run_bg(work)

    def closeEvent(self, ev):
        if not self._confirm_discard():
            ev.ignore()
            return
        self.stop_playback()
        self.worker.stop()
        ev.accept()
