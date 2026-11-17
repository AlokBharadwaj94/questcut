"""Inspector: shows the settings of whatever is selected."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QScrollArea, QSlider,
                               QSpinBox, QVBoxLayout, QWidget, QGridLayout)

from ..backend import HW
from ..cards import CARD_PARAMS, CARD_TYPES
from ..effects import EFFECT_SPECS, LOOK_LABELS, TRANSITION_LABELS, TRANSITIONS
from ..hud import ANIMS, BAR_TYPES, FULLSCREEN_TYPES, HUD_TYPES, PORTRAIT_TYPES, STYLE_LABELS, hud_params
from .theme import ACCENT, badge

CHOICE_LABELS = {
    **LOOK_LABELS, **STYLE_LABELS,
    "none": "None", "fade": "Fade", "pop": "Pop", "slide_left": "Slide from right", "slide_right": "Slide from left",
    "slide_up": "Slide up", "slide_down": "Slide down",
    "health": "Health", "mana": "Mana", "xp": "XP / experience", "stamina": "Stamina", "shield": "Shield",
    "boss": "Boss (wide, top)", "custom": "Custom colour",
    "oval": "Oval", "circle": "Circle", "rectangle": "Rectangle", "ellipse": "Ellipse",
    "blur": "Blur it", "pixelate": "Pixelate it", "solid": "Cover with colour", "highlight": "Highlight it",
    "spotlight": "Spotlight (grey out the rest)",
    "cross": "Cross", "dot": "Dot", "brackets": "Brackets",
    "coin": "Coin", "star": "Star", "heart": "Heart", "down": "Down", "up": "Up",
    "rpg_ornate": "Fantasy gold border", "retro_tv": "Old TV", "fps_visor": "Sci-fi visor", "arcade": "Arcade cabinet",
    "minimal": "Minimal corners",
    "stars": "Moving stars", "gradient": "Soft glow", "grid": "Retro grid", "black": "Plain", "scanlines": "Scanlines",
    "fit": "Fit (show everything)", "fill": "Fill (crop edges)",
    "left": "Left", "right": "Right",
}


DEFAULTS = {"x": 0.0, "y": 0.0, "scale": 1.0, "opacity": 1.0, "volume": 1.0, "speed": 1.0, "fade_in": 0.0,
            "fade_out": 0.0, "crop_l": 0.0, "crop_r": 0.0, "crop_t": 0.0, "crop_b": 0.0, "border": 0.0,
            "anim_dur": 0.0, "mask": "none", "fit": "fit", "rotate": 0, "border_color": "#ffffff"}


class KeyButton(QPushButton):
    def __init__(self):
        super().__init__("◇")
        self.setFixedWidth(28)
        self.setToolTip("Keyframe: click to remember this value at the playhead.\n"
                        "Make two or more keyframes at different times and the value will move smoothly between them.")

    def set_state(self, has_keys, at_playhead):
        if at_playhead:
            self.setText("◆")
            self.setStyleSheet(f"color:{ACCENT}; font-size:15px;")
        elif has_keys:
            self.setText("◇")
            self.setStyleSheet(f"color:{ACCENT}; font-size:15px;")
        else:
            self.setText("◇")
            self.setStyleSheet("color:#777; font-size:15px;")


class Inspector(QScrollArea):
    def __init__(self, mw):
        super().__init__()
        self.mw = mw
        self.setWidgetResizable(True)
        self.setMinimumWidth(340)
        self._rows = []           # refresh callbacks
        self._target = None
        self.rebuild()

    # ------------------------------------------------------------ helpers
    @property
    def t_rel(self):
        c = self._clip()
        return 0.0 if c is None else self.mw.playhead - c.start

    def _clip(self):
        if self._target and self._target[0] == "clip":
            return self.mw.project.clip(self._target[1])
        return None

    def _new_page(self):
        self._rows = []
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(8)
        self.setWidget(page)
        return lay

    def section(self, lay, title, badge_kind=None, collapsed=False):
        box = QGroupBox(title.replace("&", "&&"))
        v = QVBoxLayout(box)
        v.setContentsMargins(8, 12, 8, 8)
        if badge_kind:
            hb = QHBoxLayout()
            hb.addStretch(1)
            hb.addWidget(badge(badge_kind))
            v.addLayout(hb)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)
        v.addLayout(form)
        lay.addWidget(box)
        return box, form, v

    def refresh_values(self):
        for fn in self._rows:
            try:
                fn()
            except RuntimeError:
                pass

    # ------------------------------------------------------------ param rows
    def add_param(self, form, clip_getter, key, spec, keyframable=True, label_override=None):
        """spec: (name, label, kind, ...)."""
        kind = spec[2]
        label = label_override or spec[1]
        mw = self.mw

        def cur():
            c = clip_getter()
            return c.value(key, mw.playhead - c.start, DEFAULTS.get(key)) if c else None

        def setv(v, merge=True):
            c = clip_getter()
            if c is None:
                return
            mw.edit(("param", c.id, key) if merge else None, lambda: c.set_value(key, v, mw.playhead - c.start))

        if kind == "float" or kind == "int":
            lo, hi, step = spec[3], spec[4], spec[5]
            row = QHBoxLayout()
            if kind == "int":
                sb = QSpinBox()
                sb.setRange(int(lo), int(hi))
            else:
                sb = QDoubleSpinBox()
                sb.setRange(lo, hi)
                sb.setSingleStep(step)
                sb.setDecimals(3 if step < 0.01 else (2 if step < 1 else 0))
            sb.setKeyboardTracking(False)
            sl = QSlider(Qt.Orientation.Horizontal)
            sl.setRange(0, 1000)
            row.addWidget(sl, 3)
            row.addWidget(sb, 2)
            kb = None
            if keyframable:
                kb = KeyButton()
                row.addWidget(kb)
            busy = [False]

            def to_slider(v):
                return int(round((float(v) - lo) / (hi - lo) * 1000)) if hi > lo else 0

            def refresh():
                v = cur()
                if v is None:
                    v = lo
                busy[0] = True
                sb.setValue(float(v) if kind == "float" else int(round(float(v))))
                sl.setValue(to_slider(v))
                busy[0] = False
                if kb is not None:
                    c = clip_getter()
                    keys = c.keyframes.get(key, []) if c else []
                    tr = mw.playhead - c.start if c else 0
                    kb.set_state(bool(keys), any(abs(k[0] - tr) < 0.02 for k in keys))

            def on_sb(v):
                if busy[0]:
                    return
                setv(float(v) if kind == "float" else int(v))
                busy[0] = True
                sl.setValue(to_slider(v))
                busy[0] = False
                refresh_key()

            def on_sl(iv):
                if busy[0]:
                    return
                v = lo + (hi - lo) * iv / 1000.0
                if kind == "int" or step >= 1:
                    v = round(v)
                setv(v)
                busy[0] = True
                sb.setValue(v)
                busy[0] = False
                refresh_key()

            def refresh_key():
                if kb is not None:
                    c = clip_getter()
                    keys = c.keyframes.get(key, []) if c else []
                    tr = mw.playhead - c.start if c else 0
                    kb.set_state(bool(keys), any(abs(k[0] - tr) < 0.02 for k in keys))

            def on_key():
                c = clip_getter()
                if c is None:
                    return
                t_rel = mw.playhead - c.start
                if t_rel < 0 or t_rel > c.duration:
                    mw.status("Move the playhead inside this clip to add a keyframe.")
                    return

                def do():
                    if not c.remove_keyframe(key, t_rel):
                        c.add_keyframe(key, t_rel, c.value(key, t_rel, lo))
                mw.edit(None, do)
                refresh()
                mw.timeline.update()

            sb.valueChanged.connect(on_sb)
            sl.valueChanged.connect(on_sl)
            if kb is not None:
                kb.clicked.connect(on_key)
            form.addRow(label, row)
            self._rows.append(refresh)
            refresh()
            return
        if kind == "bool":
            cb = QCheckBox()
            busy = [False]

            def refresh():
                busy[0] = True
                cb.setChecked(bool(cur()))
                busy[0] = False
            cb.toggled.connect(lambda v: None if busy[0] else setv(bool(v), merge=False))
            form.addRow(label, cb)
            self._rows.append(refresh)
            refresh()
            return
        if kind == "choice":
            opts = spec[3]
            combo = QComboBox()
            for o in opts:
                combo.addItem(f"{o}°" if isinstance(o, int) else str(CHOICE_LABELS.get(o, o)), o)
            busy = [False]

            def refresh():
                busy[0] = True
                v = cur()
                i = combo.findData(v)
                combo.setCurrentIndex(max(0, i))
                busy[0] = False
            combo.currentIndexChanged.connect(lambda i: None if busy[0] else setv(combo.itemData(i), merge=False))
            form.addRow(label, combo)
            self._rows.append(refresh)
            refresh()
            return
        if kind == "target":
            combo = QComboBox()
            combo.addItem("(none)", "")
            for bc, lab in mw.bar_targets():
                combo.addItem(lab, bc.props["bar_key"])
            busy = [False]

            def refresh():
                busy[0] = True
                i = combo.findData(cur() or "")
                combo.setCurrentIndex(max(0, i))
                busy[0] = False
            combo.currentIndexChanged.connect(lambda i: None if busy[0] else setv(combo.itemData(i), merge=False))
            form.addRow(label, combo)
            self._rows.append(refresh)
            refresh()
            return
        if kind == "image":
            combo = QComboBox()
            combo.addItem("(none)", "")
            for m in mw.project.media.values():
                if m.kind == "image":
                    combo.addItem(m.name, m.id)
            busy = [False]

            def refresh():
                busy[0] = True
                combo.setCurrentIndex(max(0, combo.findData(cur() or "")))
                busy[0] = False
            combo.currentIndexChanged.connect(lambda i: None if busy[0] else setv(combo.itemData(i), merge=False))
            row = QWidget()
            hl = QHBoxLayout(row)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.addWidget(combo, 1)
            bf = QPushButton("File…")
            bf.setToolTip("Choose a picture file (PNG with transparency works best for silhouettes)")
            bf.clicked.connect(lambda: mw.choose_picture(clip_getter().id, key))
            bg = QPushButton("Frame")
            bg.setToolTip("Use the video picture at the red playhead")
            bg.clicked.connect(lambda: mw.grab_portrait(clip_getter().id, key))
            hl.addWidget(bf)
            hl.addWidget(bg)
            form.addRow(label, row)
            self._rows.append(refresh)
            refresh()
            return
        if kind == "text":
            le = QLineEdit()
            le.setText(str(cur() or ""))
            le.textEdited.connect(lambda s: setv(s))
            form.addRow(label, le)
            return
        if kind == "longtext":
            te = QPlainTextEdit()
            te.setPlainText(str(cur() or ""))
            te.setFixedHeight(76)
            te.textChanged.connect(lambda: setv(te.toPlainText()))
            form.addRow(label, te)
            return
        if kind == "color":
            btn = QPushButton()
            btn.setFixedHeight(26)

            def refresh():
                v = cur() or ""
                if v:
                    btn.setText(v)
                    tc = "#000" if QColor(v).lightness() > 140 else "#fff"
                    btn.setStyleSheet(f"background:{v}; color:{tc}; border-radius:5px;")
                else:
                    btn.setText("automatic")
                    btn.setStyleSheet("")

            def pick():
                start = QColor(cur() or "#ffffff")
                col = QColorDialog.getColor(start, self, "Pick a colour")
                if col.isValid():
                    setv(col.name(), merge=False)
                    refresh()
            btn.clicked.connect(pick)
            form.addRow(label, btn)
            self._rows.append(refresh)
            refresh()
            return

    # ------------------------------------------------------------ pages
    def show_nothing(self):
        self._target = None
        self.rebuild()

    def show_clip(self, cid):
        self._target = ("clip", cid)
        self.rebuild()

    def show_track(self, tid):
        self._target = ("track", tid)
        self.rebuild()

    def rebuild(self):
        sb = self.verticalScrollBar().value() if self.widget() else 0
        if self._target is None:
            self._page_project()
        elif self._target[0] == "clip":
            c = self.mw.project.clip(self._target[1])
            if c is None:
                self._target = None
                self._page_project()
            else:
                self._page_clip(c)
        elif self._target[0] == "track":
            t = self.mw.project.track(self._target[1])
            if t is None:
                self._target = None
                self._page_project()
            else:
                self._page_track(t)
        QTimer.singleShot(0, lambda: self.verticalScrollBar().setValue(sb))

    def _title(self, lay, text, sub=""):
        lab = QLabel(f"<span style='font-size:16px; font-weight:bold; color:{ACCENT}'>{text}</span>"
                     + (f"<br><span style='color:#9aa0aa'>{sub}</span>" if sub else ""))
        lab.setWordWrap(True)
        lay.addWidget(lab)

    def _page_project(self):
        lay = self._new_page()
        p = self.mw.project
        self._title(lay, "Movie settings", "Select a clip in the timeline to change it.")
        box, form, _ = self.section(lay, "Movie")
        le = QLineEdit(p.name)
        le.textEdited.connect(lambda s: self.mw.edit(("pname",), lambda: setattr(p, "name", s)))
        form.addRow("Name", le)
        res = QComboBox()
        for w, h in ((1920, 1080), (1280, 720), (3840, 2160), (1080, 1920)):
            res.addItem(f"{w} × {h}" + ("  (phone, vertical)" if h > w else ""), (w, h))
        i = res.findData((p.width, p.height))
        res.setCurrentIndex(max(0, i))

        def set_res(i):
            w, h = res.itemData(i)
            self.mw.edit(None, lambda: (setattr(p, "width", w), setattr(p, "height", h)))
        res.currentIndexChanged.connect(set_res)
        form.addRow("Picture size", res)
        fps = QComboBox()
        for f in (24, 25, 30, 50, 60):
            fps.addItem(f"{f} frames/s", float(f))
        fps.setCurrentIndex(max(0, fps.findData(float(p.fps))))
        fps.currentIndexChanged.connect(lambda i: self.mw.edit(None, lambda: setattr(p, "fps", fps.itemData(i))))
        form.addRow("Frame rate", fps)
        box, form, v = self.section(lay, "This computer")
        lab = QLabel(HW.summary().replace("   |   ", "<br>"))
        lab.setWordWrap(True)
        v.addWidget(lab)
        btn = QPushButton("What does the GPU speed up?")
        btn.clicked.connect(self.mw.show_gpu_info)
        v.addWidget(btn)
        box, form, v = self.section(lay, "Quick start")
        tips = QLabel("• <b>Import</b> your GoPro and camera files (Ctrl+I).<br>"
                      "• <b>Double-click</b> a clip in the Media panel to put it on the timeline.<br>"
                      "• <b>Space</b> plays, <b>S</b> cuts at the red line, <b>Delete</b> removes.<br>"
                      "• Open the <b>Guide</b> tab for step-by-step lessons.")
        tips.setWordWrap(True)
        v.addWidget(tips)
        lay.addStretch(1)

    def _page_track(self, t):
        lay = self._new_page()
        self._title(lay, t.name, {"video": "Video track", "hud": "Game HUD track", "audio": "Sound track"}[t.kind])
        box, form, v = self.section(lay, "Track")
        le = QLineEdit(t.name)
        le.textEdited.connect(lambda s: self.mw.edit(("tname", t.id), lambda: setattr(t, "name", s)))
        form.addRow("Name", le)
        if t.kind == "audio":
            vol = QDoubleSpinBox()
            vol.setRange(0, 3)
            vol.setSingleStep(0.05)
            vol.setValue(t.volume)
            vol.valueChanged.connect(lambda x: self.mw.edit(("tvol", t.id), lambda: setattr(t, "volume", x)))
            form.addRow("Volume", vol)
            voice = QCheckBox("This is the voice-over track")
            voice.setChecked(t.is_voice)
            voice.toggled.connect(lambda x: self.mw.edit(None, lambda: setattr(t, "is_voice", x)))
            form.addRow("", voice)
            duck = QCheckBox("Go quieter while someone talks")
            duck.setChecked(t.duck)
            duck.setToolTip("Called 'ducking': this track gets quieter automatically whenever the voice-over track has sound.")
            duck.toggled.connect(lambda x: self.mw.edit(None, lambda: setattr(t, "duck", x)))
            form.addRow("", duck)
            dd = QDoubleSpinBox()
            dd.setRange(-40, 0)
            dd.setSuffix(" dB")
            dd.setValue(t.duck_db)
            dd.valueChanged.connect(lambda x: self.mw.edit(("tduck", t.id), lambda: setattr(t, "duck_db", x)))
            form.addRow("How much quieter", dd)
        v.addWidget(badge("cpu"))
        row = QHBoxLayout()
        b1 = QPushButton("Add track like this")
        b1.clicked.connect(lambda: self.mw.add_track(t.kind))
        b2 = QPushButton("Remove track")
        b2.clicked.connect(lambda: self.mw.remove_track(t.id))
        row.addWidget(b1)
        row.addWidget(b2)
        v.addLayout(row)
        lay.addStretch(1)

    def _page_clip(self, c):
        lay = self._new_page()
        mw = self.mw
        get = lambda cid=c.id: mw.project.clip(cid)
        kind_name = {"video": "Video clip", "image": "Picture", "card": "Full-screen card", "audio": "Sound clip",
                     "hud": "HUD element", "adjust": "Whole-picture effect layer"}.get(c.kind, c.kind)
        if c.kind == "hud":
            kind_name = HUD_TYPES.get(c.hud_type, {}).get("label", "HUD element")
        if c.kind == "card":
            kind_name = CARD_TYPES.get(c.props.get("card_type"), {}).get("label", "Card")
        sub = ""
        if c.media_id and c.media_id in mw.project.media:
            sub = mw.project.media[c.media_id].name
        self._title(lay, kind_name, sub)
        # timing
        box, form, v = self.section(lay, "Name & timing", "cpu")
        le = QLineEdit(c.name)
        le.textEdited.connect(lambda s: mw.edit(("cname", c.id), lambda: setattr(get(), "name", s)))
        form.addRow("Name", le)
        st = QDoubleSpinBox()
        st.setRange(0, 36000)
        st.setDecimals(2)
        st.setSuffix(" s")
        st.setValue(c.start)
        st.setKeyboardTracking(False)
        st.valueChanged.connect(lambda x: mw.edit(("cstart", c.id), lambda: setattr(get(), "start", x)))
        form.addRow("Starts at", st)
        du = QDoubleSpinBox()
        du.setRange(0.1, 36000)
        du.setDecimals(2)
        du.setSuffix(" s")
        du.setValue(c.duration)
        du.setKeyboardTracking(False)
        du.valueChanged.connect(lambda x: mw.edit(("cdur", c.id), lambda: setattr(get(), "duration", x)))
        form.addRow("Length", du)
        self._rows.append(lambda: (st.blockSignals(True), st.setValue(get().start), st.blockSignals(False),
                                   du.blockSignals(True), du.setValue(get().duration), du.blockSignals(False)))
        if c.keyframes:
            row = QHBoxLayout()
            bp = QPushButton("◀ previous keyframe")
            bn = QPushButton("next keyframe ▶")
            bp.clicked.connect(lambda: mw.jump_keyframe(-1))
            bn.clicked.connect(lambda: mw.jump_keyframe(1))
            row.addWidget(bp)
            row.addWidget(bn)
            v.addLayout(row)

        if c.kind == "hud":
            self._hud_section(lay, c, get)
        if c.kind == "card":
            box, form, v = self.section(lay, "Card", "cpu")
            for spec in CARD_PARAMS:
                self.add_param(form, get, spec[0], spec, keyframable=False)
        if c.kind in ("video", "image", "card"):
            self._transform_section(lay, c, get)
        if c.kind == "video":
            box, form, v = self.section(lay, "Speed & freeze", "cpu")
            self.add_param(form, get, "speed", ("speed", "Speed (1 = normal)", "float", 0.1, 4.0, 0.05),
                           keyframable=False)
            fz = QCheckBox("Freeze on the first frame of this clip")
            fz.setChecked(c.freeze)
            fz.toggled.connect(lambda x: mw.edit(None, lambda: setattr(get(), "freeze", x)))
            form.addRow("", fz)
            row = QHBoxLayout()
            stb = QPushButton("Steady shaky footage…")
            stb.setToolTip("Makes a steadier copy of this video (good for head-mounted GoPro shots).")
            stb.clicked.connect(mw.stabilize_selected)
            row.addWidget(stb)
            row.addWidget(badge("slow"))
            row.addStretch(1)
            v.addLayout(row)
        if c.kind in ("video", "audio"):
            box, form, v = self.section(lay, "Sound", "cpu")
            self.add_param(form, get, "volume", ("volume", "Volume", "float", 0.0, 3.0, 0.01))
            if c.kind == "video":
                self.add_param(form, get, "mute", ("mute", "Mute this clip's sound", "bool"))
            self.add_param(form, get, "fade_in", ("fade_in", "Fade in (s)", "float", 0.0, 10.0, 0.1), keyframable=False)
            self.add_param(form, get, "fade_out", ("fade_out", "Fade out (s)", "float", 0.0, 10.0, 0.1),
                           keyframable=False)
            if c.kind == "audio":
                self.add_param(form, get, "loop", ("loop", "Repeat (loop) to fill the clip", "bool"))
                self.add_param(form, get, "speed", ("speed", "Speed / pitch", "float", 0.25, 4.0, 0.05),
                               keyframable=False)
        if c.kind in ("video", "image", "card"):
            self._transition_section(lay, c, get)
        if c.kind == "adjust":
            box, form, v = self.section(lay, "Layer", "gpu_faster")
            v.addWidget(QLabel("Everything below this layer gets the effects listed here."))
            self.add_param(form, get, "opacity", ("opacity", "Strength", "float", 0.0, 1.0, 0.01))
            self.add_param(form, get, "anim_dur", ("anim_dur", "Fade in/out (s)", "float", 0.0, 5.0, 0.1),
                           keyframable=False)
        if c.kind in ("video", "image", "card", "adjust"):
            self._effects_section(lay, c, get)
        lay.addStretch(1)

    def _hud_section(self, lay, c, get):
        spec = HUD_TYPES.get(c.hud_type, {})
        heavy = c.hud_type in ("spell", "frame", "level_up")
        box, form, v = self.section(lay, spec.get("label", "HUD"), "gpu_faster" if heavy else "cpu")
        if c.hud_type == "spell":
            tip = QLabel("Tip: drag the <b>C</b> (caster) and <b>T</b> (target) dots in the preview. "
                         "The screen shakes and flashes at the hit moment.")
        elif spec.get("skin"):
            tip = QLabel("Look inspired by: " + spec.get("label", "").split("(")[-1].rstrip(")") +
                         ". Drag the yellow dot in the preview to move it; use ◇ to animate numbers.")
        elif c.hud_type == "frame":
            tip = QLabel("A frame usually covers the whole movie: drag its right edge in the timeline to make it longer.")
        else:
            tip = QLabel("Tip: drag the yellow dot in the preview to move it. Use ◇ to animate a value over time.")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#9aa0aa;")
        v.insertWidget(0, tip)
        common_keys = {"style", "x", "y", "scale", "opacity", "anim_in", "anim_out", "anim_dur"}
        params = hud_params(c.hud_type)
        for sp in params:
            if sp[0] in common_keys:
                continue
            kf = sp[2] in ("float", "int")
            self.add_param(form, get, sp[0], sp, keyframable=kf)
        if c.hud_type in BAR_TYPES:
            self._spell_link_section(lay, c)
        if c.hud_type in PORTRAIT_TYPES:
            self._portrait_section(lay, c)
        box, form, v = self.section(lay, "Look, place & animation", "cpu")
        for sp in params:
            if sp[0] not in common_keys:
                continue
            if c.hud_type in FULLSCREEN_TYPES and sp[0] in ("x", "y"):
                continue
            if spec.get("skin") and sp[0] == "style":
                continue
            self.add_param(form, get, sp[0], sp, keyframable=sp[2] == "float" and sp[0] not in ("anim_dur",))

    def _portrait_section(self, lay, c):
        from ..creature import PORTRAIT_TITLES
        mw = self.mw
        box, form, v = self.section(lay, PORTRAIT_TITLES.get(c.hud_type, "Portrait (who is talking)"), "cpu")
        b = QPushButton("Grab picture from the current frame")
        b.setToolTip("Move the red playhead to a moment where the person is clearly visible, then click.")
        b.clicked.connect(lambda: mw.grab_portrait(c.id))
        v.insertWidget(0, b)
        bf = QPushButton("Choose a picture file…")
        bf.setToolTip("Any photo or drawing. A PNG with a transparent background gives the cleanest silhouette.")
        bf.clicked.connect(lambda: mw.choose_picture(c.id, None))
        v.insertWidget(1, bf)
        combo = QComboBox()
        combo.addItem("(no picture)", "")
        for m in mw.project.media.values():
            if m.kind == "image":
                combo.addItem(m.name, m.id)
        combo.setCurrentIndex(max(0, combo.findData(c.media_id or "")))
        combo.currentIndexChanged.connect(lambda i: mw.set_portrait_media(c.id, combo.itemData(i)))
        form.addRow("Picture", combo)
        tip = QLabel("After grabbing: drag the yellow 'face' dot in the preview onto the face, and use 'Face zoom' "
                     "above to frame it. For a different expression per line, cut the box (S) and grab again.")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#9aa0aa;")
        v.addWidget(tip)

    def _spell_link_section(self, lay, c):
        mw = self.mw
        key = c.props.get("bar_key")
        spells = mw.spells()
        linked = [s for s in spells if key and s.props.get("target_bar") == key]
        unlinked = [s for s in spells if not s.props.get("target_bar")]
        box, form, v = self.section(lay, "Spells that hit this bar", "cpu")
        txt = f"{len(linked)} spell(s) lower this bar when they hit."
        if unlinked:
            txt += f" {len(unlinked)} spell(s) have no bar yet."
        if c.hud_type == "zl_hearts":
            txt += " Damage is counted in hearts here (1 = one heart)."
        if c.hud_type == "name_tag" and not c.props.get("show_bar"):
            txt += " Tick 'Show small health bar' to see it."
        lab = QLabel(txt)
        lab.setWordWrap(True)
        v.addWidget(lab)
        b1 = QPushButton(f"Link the {len(unlinked)} spell(s) without a bar")
        b1.setEnabled(bool(unlinked))
        b1.clicked.connect(lambda: mw.link_spells(c.id, only_unlinked=True))
        v.addWidget(b1)
        b2 = QPushButton("Link ALL spells to this bar")
        b2.setEnabled(bool(spells))
        b2.clicked.connect(lambda: mw.link_spells(c.id, only_unlinked=False))
        v.addWidget(b2)
        note = QLabel("'Value' is the health before any spell. Each linked spell takes its damage away at its "
                      "hit moment, so moving a spell moves the drop too.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#9aa0aa;")
        v.addWidget(note)

    def _transform_section(self, lay, c, get):
        mw = self.mw
        box, form, v = self.section(lay, "Position, size & crop", "cpu")
        if c.kind != "card":
            self.add_param(form, get, "fit", ("fit", "Fit to frame", "choice", ["fit", "fill"]), keyframable=False)
        self.add_param(form, get, "x", ("x", "Move left/right", "float", -1.0, 1.0, 0.005))
        self.add_param(form, get, "y", ("y", "Move up/down", "float", -1.0, 1.0, 0.005))
        self.add_param(form, get, "scale", ("scale", "Size (zoom)", "float", 0.05, 4.0, 0.01))
        self.add_param(form, get, "opacity", ("opacity", "Opacity", "float", 0.0, 1.0, 0.01))
        if c.kind != "card":
            self.add_param(form, get, "rotate", ("rotate", "Rotate", "choice", [0, 90, 180, 270]), keyframable=False)
            self.add_param(form, get, "flip_h", ("flip_h", "Mirror left-right", "bool"))
            self.add_param(form, get, "flip_v", ("flip_v", "Flip upside-down", "bool"))
            for k, lab in (("crop_l", "Crop left"), ("crop_r", "Crop right"), ("crop_t", "Crop top"),
                           ("crop_b", "Crop bottom")):
                self.add_param(form, get, k, (k, lab, "float", 0.0, 0.9, 0.005))
        box, form, v = self.section(lay, "Picture-in-picture", "cpu")
        grid = QGridLayout()
        for i, (key, label) in enumerate(mw.PIP_PRESETS):
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, k=key: mw.apply_pip(k))
            grid.addWidget(b, i // 2, i % 2)
        v.insertLayout(0, grid)
        self.add_param(form, get, "mask", ("mask", "Shape", "choice", ["none", "rounded", "circle"]), keyframable=False)
        self.add_param(form, get, "border", ("border", "Border width", "float", 0.0, 40.0, 1.0), keyframable=False)
        self.add_param(form, get, "border_color", ("border_color", "Border colour", "color"), keyframable=False)

    def _transition_section(self, lay, c, get):
        mw = self.mw
        box, form, v = self.section(lay, "Transitions", "cpu")
        for side, label in (("in", "Start"), ("out", "End")):
            row = QHBoxLayout()
            combo = QComboBox()
            for t in TRANSITIONS:
                combo.addItem(TRANSITION_LABELS[t], t)
            td = getattr(c, f"transition_{side}") or {}
            combo.setCurrentIndex(max(0, combo.findData(td.get("type", "none"))))
            dur = QDoubleSpinBox()
            dur.setRange(0.05, 5.0)
            dur.setSingleStep(0.1)
            dur.setSuffix(" s")
            dur.setValue(float(td.get("duration", 0.5)))

            def upd(_=None, side=side, combo=combo, dur=dur):
                def do():
                    setattr(get(), f"transition_{side}", {"type": combo.currentData(), "duration": dur.value()})
                mw.edit(("trans", c.id, side), do)
                mw.timeline.update()
            combo.currentIndexChanged.connect(upd)
            dur.valueChanged.connect(upd)
            row.addWidget(combo, 3)
            row.addWidget(dur, 1)
            form.addRow(label, row)
        note = QLabel("Cross-fade mixes with the clip just before on the same track.")
        note.setStyleSheet("color:#9aa0aa;")
        note.setWordWrap(True)
        v.addWidget(note)

    def _effects_section(self, lay, c, get):
        mw = self.mw
        box, form, v = self.section(lay, "Effects & filters", "gpu_faster")
        grid = QGridLayout()
        for i, (key, label) in enumerate(mw.EFFECT_MENU):
            b = QPushButton("+ " + label)
            b.clicked.connect(lambda _=False, k=key: mw.add_effect(k))
            grid.addWidget(b, i // 2, i % 2)
        v.addLayout(grid)
        for f in c.effects:
            spec = EFFECT_SPECS.get(f["type"], {})
            eb = QGroupBox(spec.get("label", f["type"]).replace("&", "&&"))
            eb.setCheckable(True)
            eb.setChecked(f.get("enabled", True))
            fid = f["id"]

            def toggle(on, fid=fid):
                mw.edit(None, lambda: get().effect(fid).__setitem__("enabled", on))
            eb.toggled.connect(toggle)
            ev = QVBoxLayout(eb)
            ef = QFormLayout()
            ev.addLayout(ef)
            for sp in spec.get("params", []):
                key = f"fx.{fid}.{sp[0]}"
                self.add_param(ef, get, key, sp, keyframable=sp[2] == "float")
            row = QHBoxLayout()
            row.addWidget(badge(spec.get("gpu", "cpu")))
            row.addStretch(1)
            rm = QPushButton("Remove")
            rm.clicked.connect(lambda _=False, fid=fid: mw.remove_effect(fid))
            row.addWidget(rm)
            ev.addLayout(row)
            v.addWidget(eb)
        if not c.effects:
            lab = QLabel("No effects yet. Vignette and touch-up areas get a yellow dot in the preview you can drag; "
                         "use ◇ keyframes to make a blur follow a face.")
            lab.setWordWrap(True)
            lab.setStyleSheet("color:#9aa0aa;")
            v.addWidget(lab)
