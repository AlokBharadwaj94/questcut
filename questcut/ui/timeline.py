"""The timeline: tracks, clips, playhead. Drag to move, drag edges to trim."""
from __future__ import annotations

import json
import math
import zlib

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QMenu, QWidget

from ..media import load_audio
from .theme import CLIP_COLORS, fmt_time

HEADER_W = 190
RULER_H = 30
ROW_H = {"video": 58, "hud": 40, "audio": 50}
EDGE = 7
MIME = "application/x-questcut"


class Timeline(QWidget):
    playheadMoved = Signal(float)
    selectionChanged = Signal()
    trackSelected = Signal(str)

    def __init__(self, mw):
        super().__init__()
        self.mw = mw
        self.pps = 60.0          # pixels per second
        self.scroll_x = 0.0      # seconds at the left edge
        self.scroll_y = 0
        self.playhead = 0.0
        self.selected: list = []
        self.current_track = None
        self._drag = None
        self._peaks: dict = {}
        self.mark_in = None      # start of the marked stretch of time (I)
        self.mark_out = None     # end of it (O)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(220)

    # ------------------------------------------------------------ geometry
    @property
    def project(self):
        return self.mw.project

    def rows(self):
        y = RULER_H - self.scroll_y
        out = []
        for tr in self.project.tracks:
            h = ROW_H[tr.kind]
            out.append((tr, y, h))
            y += h + 2
        return out

    def content_height(self):
        return RULER_H + sum(ROW_H[t.kind] + 2 for t in self.project.tracks) + 20

    def x_of(self, t):
        return HEADER_W + (t - self.scroll_x) * self.pps

    def t_of(self, x):
        return self.scroll_x + (x - HEADER_W) / self.pps

    def clip_rect(self, clip, y, h):
        x0 = self.x_of(clip.start)
        return QRectF(x0, y + 3, max(2.0, clip.duration * self.pps), h - 6)

    def row_at(self, y):
        for tr, ry, h in self.rows():
            if ry <= y < ry + h + 2:
                return tr, ry, h
        return None, 0, 0

    def clip_at(self, pos):
        tr, ry, h = self.row_at(pos.y())
        if tr is None:
            return None, None
        for c in sorted(tr.clips, key=lambda c: c.start, reverse=True):
            if self.clip_rect(c, ry, h).contains(pos):
                return tr, c
        return tr, None

    def zoom_to_fit(self):
        dur = max(10.0, self.project.duration)
        w = max(200, self.width() - HEADER_W - 30)
        self.pps = max(2.0, min(400.0, w / dur))
        self.scroll_x = 0
        self.update()

    def set_zoom(self, pps, anchor_x=None):
        if anchor_x is None:
            anchor_x = self.x_of(self.playhead)
        t_anchor = self.t_of(anchor_x)
        self.pps = max(1.0, min(800.0, pps))
        self.scroll_x = max(0.0, t_anchor - (anchor_x - HEADER_W) / self.pps)
        self.update()

    def ensure_visible(self, t):
        w = self.width() - HEADER_W
        if self.x_of(t) > self.width() - 30:
            self.scroll_x = t - w * 0.25 / self.pps
        elif self.x_of(t) < HEADER_W:
            self.scroll_x = max(0.0, t - w * 0.1 / self.pps)

    def set_playhead(self, t, emit=True, follow=False):
        self.playhead = max(0.0, t)
        if follow:
            self.ensure_visible(self.playhead)
        self.update()
        if emit:
            self.playheadMoved.emit(self.playhead)

    def marked_range(self):
        if self.mark_in is None or self.mark_out is None:
            return None
        a, b = sorted((self.mark_in, self.mark_out))
        return (a, b) if b - a > 0.005 else None

    def _with_groups(self, ids):
        """Selecting one piece of a group selects the whole group."""
        out = list(ids)
        seen = set(out)
        for cid in list(ids):
            c = self.project.clip(cid)
            g = c.props.get("group") if c is not None else None
            if g:
                for o in self.project.all_clips():
                    if o.props.get("group") == g and o.id not in seen:
                        out.append(o.id)
                        seen.add(o.id)
        return out

    # ------------------------------------------------------------ waveform peaks
    def peaks(self, media_id):
        if media_id in self._peaks:
            return self._peaks[media_id]
        m = self.project.media.get(media_id)
        self._peaks[media_id] = None
        if m is None:
            return None

        def work():
            arr = load_audio(self.project, m)
            if arr is None:
                return
            a = np.abs(np.asarray(arr[:, 0], dtype=np.float32)) / 32768.0
            blk = 480  # 100 per second
            n = len(a) // blk
            if n == 0:
                return
            pk = a[:n * blk].reshape(n, blk).max(axis=1)
            self._peaks[media_id] = pk
            self.mw.call_in_gui(self.update)

        self.mw.run_bg(work)
        return None

    # ------------------------------------------------------------ painting
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        W, H = self.width(), self.height()
        p.fillRect(0, 0, W, H, QColor("#16181d"))
        rows = self.rows()
        sel_ids = set(self.selected)
        small = QFont(self.font())
        small.setPixelSize(11)
        bold = QFont(self.font())
        bold.setPixelSize(12)
        bold.setBold(True)
        t_left, t_right = self.t_of(HEADER_W), self.t_of(W)
        # rows
        for tr, y, h in rows:
            if y + h < RULER_H or y > H:
                continue
            bg = {"video": "#1e2230", "hud": "#262019", "audio": "#1b2620"}[tr.kind]
            if tr.id == self.current_track:
                bg = QColor(bg).lighter(125).name()
            p.fillRect(QRectF(HEADER_W, y, W - HEADER_W, h), QColor(bg))
            p.save()
            p.setClipRect(QRectF(HEADER_W, max(y, RULER_H), W - HEADER_W, h))
            for c in tr.clips:
                if c.end < t_left or c.start > t_right:
                    continue
                self._paint_clip(p, tr, c, y, h, c.id in sel_ids, small, bold)
            p.restore()
        # marked stretch of time (I ... O)
        rng = self.marked_range()
        if rng is not None:
            xa, xb = max(HEADER_W, self.x_of(rng[0])), self.x_of(rng[1])
            if xb > HEADER_W:
                p.fillRect(QRectF(xa, RULER_H, xb - xa, H - RULER_H), QColor(90, 170, 255, 40))
                p.setPen(QPen(QColor("#5aaaff"), 1, Qt.PenStyle.DashLine))
                p.drawLine(QPointF(xa, RULER_H), QPointF(xa, H))
                p.drawLine(QPointF(xb, RULER_H), QPointF(xb, H))
        # selection box
        if self._drag and self._drag.get("mode") == "box" and self._drag.get("started"):
            r = self._drag["rect"]
            p.setPen(QPen(QColor("#ffd54a"), 1, Qt.PenStyle.DashLine))
            p.setBrush(QColor(255, 213, 74, 35))
            p.drawRect(r)
        # headers
        for tr, y, h in rows:
            if y + h < RULER_H or y > H:
                continue
            self._paint_header(p, tr, y, h, bold, small)
        # ruler
        p.fillRect(0, 0, W, RULER_H, QColor("#20232b"))
        p.fillRect(0, 0, HEADER_W, RULER_H, QColor("#20232b"))
        p.setPen(QColor("#888"))
        p.setFont(small)
        step = self._tick_step()
        t = math.floor(t_left / step) * step
        while t <= t_right:
            x = self.x_of(t)
            if x >= HEADER_W:
                p.drawLine(QPointF(x, RULER_H - 9), QPointF(x, RULER_H))
                p.drawText(QPointF(x + 3, RULER_H - 12), fmt_time(t, self.project.fps)[:-3] if step >= 1 else
                           fmt_time(t, self.project.fps))
                sub = step / 5
                for k in range(1, 5):
                    xs = self.x_of(t + sub * k)
                    p.drawLine(QPointF(xs, RULER_H - 4), QPointF(xs, RULER_H))
            t += step
        if rng is not None:
            xa, xb = self.x_of(rng[0]), self.x_of(rng[1])
            p.fillRect(QRectF(max(HEADER_W, xa), RULER_H - 8, max(0.0, xb - max(HEADER_W, xa)), 8),
                       QColor("#5aaaff"))
            p.setPen(QColor("#9fd0ff"))
            p.setFont(small)
            if xb > HEADER_W:
                p.drawText(QPointF(max(HEADER_W, xa) + 3, 11), f"marked {rng[1] - rng[0]:.2f} s")
        elif self.mark_in is not None or self.mark_out is not None:
            m = self.mark_in if self.mark_in is not None else self.mark_out
            x = self.x_of(m)
            if x >= HEADER_W:
                p.setPen(QPen(QColor("#5aaaff"), 2))
                p.drawLine(QPointF(x, 0), QPointF(x, RULER_H))
        p.setPen(QColor("#bbb"))
        p.setFont(bold)
        p.drawText(QRectF(10, 0, HEADER_W - 10, RULER_H), Qt.AlignmentFlag.AlignVCenter, "TRACKS")
        # playhead
        x = self.x_of(self.playhead)
        if x >= HEADER_W:
            p.setPen(QPen(QColor("#ff4d4d"), 2))
            p.drawLine(QPointF(x, 0), QPointF(x, H))
            p.setBrush(QColor("#ff4d4d"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPolygon(QPolygonF([QPointF(x - 7, 0), QPointF(x + 7, 0), QPointF(x, 12)]))
        # snap line
        if self._drag and self._drag.get("snap_x") is not None:
            p.setPen(QPen(QColor("#ffd54a"), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(self._drag["snap_x"], RULER_H), QPointF(self._drag["snap_x"], H))
        if not any(True for _ in self.project.all_clips()):
            p.setPen(QColor("#777"))
            f = QFont(self.font())
            f.setPixelSize(15)
            p.setFont(f)
            p.drawText(QRectF(HEADER_W, RULER_H, W - HEADER_W, H - RULER_H), Qt.AlignmentFlag.AlignCenter,
                       "Drag clips here from the Media panel (or double-click them).\n"
                       "New here? Open the Guide tab on the right, or Help → Create practice project.")
        p.end()
        sync = getattr(self.mw, "sync_scrollbars", None)
        if sync is not None and hasattr(self.mw, "vscroll"):
            sync()

    def _tick_step(self):
        for s in (0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300):
            if s * self.pps >= 70:
                return s
        return 600

    def _paint_header(self, p, tr, y, h, bold, small):
        p.fillRect(QRectF(0, y, HEADER_W, h), QColor("#262a33" if tr.id != self.current_track else "#323745"))
        stripe = {"video": "#3d6fd8", "hud": "#c98a1f", "audio": "#2e9e5b"}[tr.kind]
        p.fillRect(QRectF(0, y, 4, h), QColor(stripe))
        p.setPen(QColor("#e6e6e6"))
        p.setFont(bold)
        p.drawText(QRectF(10, y + 3, HEADER_W - 70, h / 2), Qt.AlignmentFlag.AlignVCenter, tr.name)
        p.setFont(small)
        p.setPen(QColor("#9aa0aa"))
        info = {"video": "video", "hud": "game HUD", "audio": "sound"}[tr.kind]
        if tr.kind == "audio":
            if tr.is_voice:
                info = "voice (ducks music)"
            elif tr.duck:
                info = f"sound · ducks {tr.duck_db:.0f} dB"
        p.drawText(QRectF(10, y + h / 2, HEADER_W - 70, h / 2 - 2), Qt.AlignmentFlag.AlignVCenter, info)
        for name, r in self._header_buttons(y, h).items():
            if name == "hide":
                on = tr.muted if tr.kind == "audio" else tr.hidden
                if tr.kind == "audio":
                    label = "🔇" if on else "🔊"
                else:
                    label = "🚫" if on else "👁"
            else:
                on = tr.locked
                label = "🔒" if on else "🔓"
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#a33" if on else "#3a3f4b"))
            p.drawRoundedRect(r, 4, 4)
            p.setPen(QColor("#fff"))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, label)

    def _header_buttons(self, y, h):
        tr_w = 24
        x = HEADER_W - 2 * (tr_w + 4) - 2
        r1 = QRectF(x, y + h / 2 - 11, tr_w, 22)
        r2 = QRectF(x + tr_w + 4, y + h / 2 - 11, tr_w, 22)
        return {"hide": r1, "lock": r2}

    def _clip_color(self, tr, c):
        if c.kind == "hud":
            if c.hud_type == "spell":
                return CLIP_COLORS["spell"]
            if c.hud_type == "frame":
                return CLIP_COLORS["frame"]
            return CLIP_COLORS["hud"]
        if c.kind == "audio" and tr.is_voice:
            return CLIP_COLORS["voice"]
        return CLIP_COLORS.get(c.kind, "#666")

    def _paint_clip(self, p, tr, c, y, h, selected, small, bold):
        r = self.clip_rect(c, y, h)
        col = QColor(self._clip_color(tr, c))
        if not c.enabled:
            col.setAlpha(70)
        path = QPainterPath()
        path.addRoundedRect(r, 5, 5)
        p.fillPath(path, col.darker(130) if c.freeze else col)
        if not c.enabled:
            p.save()
            p.setClipPath(path)
            p.fillRect(r, QBrush(QColor(255, 255, 255, 30), Qt.BrushStyle.BDiagPattern))
            p.restore()
        # thumbnail
        thumb = self.mw.thumbs.get(c.media_id) if c.media_id else None
        if thumb is not None and c.kind in ("video", "image") and r.width() > 60:
            th = r.height() - 4
            tw = th * 16 / 9
            p.save()
            p.setClipPath(path)
            p.drawPixmap(QRectF(r.left() + 2, r.top() + 2, tw, th).toRect(), thumb)
            p.restore()
            text_x = r.left() + tw + 6
        else:
            text_x = r.left() + 6
        # waveform
        if c.kind in ("audio", "video") and c.media_id and r.width() > 8:
            m = self.project.media.get(c.media_id)
            if m is not None and (m.has_audio or m.kind == "audio"):
                pk = self.peaks(c.media_id)
                if pk is not None:
                    self._paint_wave(p, c, r, pk, text_x if c.kind == "video" else r.left())
        # transitions
        p.setPen(Qt.PenStyle.NoPen)
        for side, tdef in (("in", c.transition_in), ("out", c.transition_out)):
            if tdef and tdef.get("type", "none") != "none":
                w = min(r.width() / 2, float(tdef.get("duration", 0.5)) * self.pps)
                p.setBrush(QColor(255, 255, 255, 70))
                if side == "in":
                    p.drawPolygon(QPolygonF([r.topLeft(), QPointF(r.left() + w, r.top()), r.bottomLeft()]))
                else:
                    p.drawPolygon(QPolygonF([QPointF(r.right() - w, r.top()), r.topRight(), r.bottomRight()]))
        # fades on audio
        fi = float(c.props.get("fade_in", 0) or 0)
        fo = float(c.props.get("fade_out", 0) or 0)
        if fi or fo:
            p.setPen(QPen(QColor(255, 255, 255, 180), 1.5))
            if fi:
                p.drawLine(QPointF(r.left(), r.bottom()), QPointF(r.left() + fi * self.pps, r.top()))
            if fo:
                p.drawLine(QPointF(r.right() - fo * self.pps, r.top()), QPointF(r.right(), r.bottom()))
        # label
        p.setPen(QColor("#ffffff"))
        p.setFont(bold)
        label = c.name or c.hud_type or c.kind
        if c.freeze:
            label = "❄ " + label
        if c.effects:
            label += "  ✨" + str(len(c.effects))
        if c.props.get("mute"):
            label += "  🔇"
        p.drawText(QRectF(text_x, r.top() + 1, max(0, r.right() - text_x - 4), 16),
                   Qt.AlignmentFlag.AlignVCenter, label)
        # keyframes
        if c.keyframes:
            p.setPen(QPen(QColor("#000"), 1))
            p.setBrush(QColor("#ffd54a") if selected else QColor(255, 213, 74, 150))
            ky = r.bottom() - 7
            for kt in c.keyframe_times():
                kx = r.left() + kt * self.pps
                p.drawPolygon(QPolygonF([QPointF(kx, ky - 5), QPointF(kx + 5, ky), QPointF(kx, ky + 5),
                                         QPointF(kx - 5, ky)]))
        gid = c.props.get("group")
        if gid:
            gcol = QColor.fromHsv(zlib.crc32(gid.encode()) % 360, 160, 255)
            p.save()
            p.setClipPath(path)
            p.fillRect(QRectF(r.left(), r.bottom() - 4, r.width(), 4), gcol)
            p.restore()
            if r.width() > 26:
                p.setPen(gcol)
                p.setFont(small)
                p.drawText(QRectF(r.right() - 20, r.top() + 1, 18, 14), Qt.AlignmentFlag.AlignCenter, "⛓")
        if selected:
            p.setPen(QPen(QColor("#ffd54a"), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 5, 5)
        else:
            p.setPen(QPen(QColor(0, 0, 0, 120), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r, 5, 5)

    def _paint_wave(self, p, c, r, pk, x_start):
        x0 = max(x_start, HEADER_W, r.left())
        x1 = min(r.right(), self.width())
        if x1 - x0 < 2:
            return
        xs = np.arange(int(x0), int(x1), 2, dtype=np.float32)
        speed = float(c.props.get("speed", 1.0) or 1.0)
        ts = c.source_in + (self.t_of(xs) - c.start) * speed
        if c.freeze:
            return
        if c.props.get("loop") and len(pk):
            idx = (ts * 100).astype(np.int64) % len(pk)
        else:
            idx = np.clip((ts * 100).astype(np.int64), 0, len(pk) - 1)
        vals = pk[idx]
        vals[(ts * 100) >= len(pk)] = 0
        vol = float(c.props.get("volume", 1.0))
        mid = r.center().y() + 4
        amp = (r.height() / 2 - 6) * np.clip(vals * vol, 0, 1)
        top = [QPointF(float(x), float(mid - a)) for x, a in zip(xs, amp)]
        bot = [QPointF(float(x), float(mid + a)) for x, a in zip(xs[::-1], amp[::-1])]
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 80 if c.kind == "video" else 120))
        p.drawPolygon(QPolygonF(top + bot))

    # ------------------------------------------------------------ mouse
    def mousePressEvent(self, ev):
        self.setFocus()
        pos = ev.position()
        if pos.y() < RULER_H and pos.x() > HEADER_W:
            if ev.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                t0 = max(0.0, self.t_of(pos.x()))
                self.mark_in, self.mark_out = t0, t0
                self._drag = {"mode": "mark"}
                self.update()
                return
            self._drag = {"mode": "scrub"}
            self.set_playhead(self.t_of(pos.x()))
            return
        if pos.x() < HEADER_W:
            tr, y, h = self.row_at(pos.y())
            if tr is None:
                return
            for name, r in self._header_buttons(y, h).items():
                if r.contains(pos):
                    self.mw.begin_edit()
                    if name == "hide":
                        if tr.kind == "audio":
                            tr.muted = not tr.muted
                        else:
                            tr.hidden = not tr.hidden
                    elif name == "lock":
                        tr.locked = not tr.locked
                    self.mw.end_edit()
                    return
            self.current_track = tr.id
            self.trackSelected.emit(tr.id)
            self.selected = []
            self.selectionChanged.emit()
            self.update()
            return
        tr, c = self.clip_at(pos)
        if tr is not None:
            self.current_track = tr.id
        if ev.button() == Qt.MouseButton.RightButton:
            if c is not None and c.id not in self.selected:
                self.selected = [c.id]
                self.selectionChanged.emit()
            self.update()
            self._context_menu(ev.globalPosition().toPoint(), tr, c, self.t_of(pos.x()))
            return
        if c is None:
            add = bool(ev.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))
            # click = move the playhead (on release); drag = draw a box to select pieces
            self._drag = {"mode": "box", "x0": pos.x(), "y0": pos.y(), "started": False, "add": add,
                          "base": list(self.selected) if add else [], "rect": QRectF(pos, pos), "track": tr}
            return
        mods = ev.modifiers()
        single = bool(mods & Qt.KeyboardModifier.AltModifier)      # Alt: just this piece, even in a group
        one = [c.id] if single else self._with_groups([c.id])
        if mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            if c.id in self.selected:
                self.selected = [i for i in self.selected if i not in one]
            else:
                self.selected += [i for i in one if i not in self.selected]
        elif c.id not in self.selected or single:
            self.selected = one
        else:   # clicked piece goes first so the right panel shows it
            self.selected = [c.id] + [i for i in self.selected if i != c.id]
        self.selectionChanged.emit()
        if tr.locked:
            self.update()
            return
        _, ry, h = self.row_at(pos.y())
        r = self.clip_rect(c, ry, h)
        mode = "move"
        if pos.x() - r.left() <= EDGE and r.width() > 3 * EDGE:
            mode = "trim_l"
        elif r.right() - pos.x() <= EDGE and r.width() > 3 * EDGE:
            mode = "trim_r"
        origs = {}
        for cid in self.selected:
            cc = self.project.clip(cid)
            if cc is not None:
                origs[cid] = (cc.start, cc.duration, cc.source_in, self.project.track_of(cid).id)
        self._drag = {"mode": mode, "x0": pos.x(), "clip": c.id, "track": tr.id, "origs": origs,
                      "started": False, "snap_x": None}
        self.update()

    def _snap_points(self, exclude):
        pts = [0.0, self.playhead]
        for c in self.project.all_clips():
            if c.id in exclude:
                continue
            pts += [c.start, c.end]
        return pts

    def _snap(self, t, pts):
        best, bd = None, 9 / self.pps
        for s in pts:
            d = abs(s - t)
            if d < bd:
                best, bd = s, d
        return best

    def mouseMoveEvent(self, ev):
        pos = ev.position()
        d = self._drag
        if d is None:
            tr, c = self.clip_at(pos)
            cursor = Qt.CursorShape.ArrowCursor
            if c is not None and pos.x() > HEADER_W:
                _, ry, h = self.row_at(pos.y())
                r = self.clip_rect(c, ry, h)
                if pos.x() - r.left() <= EDGE or r.right() - pos.x() <= EDGE:
                    cursor = Qt.CursorShape.SizeHorCursor
                else:
                    cursor = Qt.CursorShape.OpenHandCursor
            self.setCursor(cursor)
            return
        if d["mode"] == "scrub":
            self.set_playhead(self.t_of(pos.x()))
            return
        if d["mode"] == "mark":
            self.mark_out = max(0.0, self.t_of(pos.x()))
            self.update()
            return
        if d["mode"] == "box":
            if not d["started"] and abs(pos.x() - d["x0"]) + abs(pos.y() - d["y0"]) < 6:
                return
            d["started"] = True
            r = QRectF(QPointF(min(d["x0"], pos.x()), min(d["y0"], pos.y())),
                       QPointF(max(d["x0"], pos.x()), max(d["y0"], pos.y())))
            d["rect"] = r
            hit = []
            for tr, y, h in self.rows():
                for cc in tr.clips:
                    if self.clip_rect(cc, y, h).intersects(r):
                        hit.append(cc.id)
            ids = list(d["base"]) + [i for i in self._with_groups(hit) if i not in d["base"]]
            if ids != self.selected:
                self.selected = ids
                self.selectionChanged.emit()
            self.update()
            return
        dx = pos.x() - d["x0"]
        if not d["started"]:
            if abs(dx) < 3 and d["mode"] != "move":
                return
            if abs(dx) < 3 and abs(pos.y() - 0) < 0:
                return
            d["started"] = True
            self.mw.begin_edit()
        dt = dx / self.pps
        main = self.project.clip(d["clip"])
        if main is None:
            return
        o_start, o_dur, o_in, o_tid = d["origs"][d["clip"]]
        pts = self._snap_points(set(d["origs"].keys()))
        d["snap_x"] = None
        if d["mode"] == "move":
            new_start = max(0.0, o_start + dt)
            s1 = self._snap(new_start, pts)
            s2 = self._snap(new_start + o_dur, pts)
            if s1 is not None:
                new_start = s1
                d["snap_x"] = self.x_of(s1)
            elif s2 is not None:
                new_start = s2 - o_dur
                d["snap_x"] = self.x_of(s2)
            shift = new_start - o_start
            # don't let any selected clip go before 0
            min_start = min(v[0] for v in d["origs"].values())
            shift = max(shift, -min_start)
            for cid, (s0, du, si, tid) in d["origs"].items():
                cc = self.project.clip(cid)
                if cc:
                    cc.start = round(s0 + shift, 4)
            # move to another track of the same kind (single clip)
            if len(d["origs"]) == 1:
                tr_new, _, _ = self.row_at(pos.y())
                tr_old = self.project.track_of(main.id)
                if tr_new is not None and tr_old is not None and tr_new is not tr_old and not tr_new.locked:
                    ok = tr_new.kind == tr_old.kind or (main.kind in ("hud", "adjust") and tr_new.kind == "hud")
                    if ok:
                        tr_old.clips.remove(main)
                        tr_new.clips.append(main)
                        self.current_track = tr_new.id
        elif d["mode"] == "trim_l":
            speed = float(main.props.get("speed", 1.0) or 1.0)
            new_start = o_start + dt
            s = self._snap(new_start, pts)
            if s is not None:
                new_start = s
                d["snap_x"] = self.x_of(s)
            new_start = max(0.0, min(new_start, o_start + o_dur - 0.1))
            delta = new_start - o_start
            if main.media_id and main.kind in ("video", "audio") and not main.freeze and not main.props.get("loop"):
                delta = max(delta, -o_in / speed)
                main.source_in = round(o_in + delta * speed, 4)
            main.start = round(o_start + delta, 4)
            main.duration = round(o_dur - delta, 4)
            self._shift_keyframes(main, -delta, d)
        elif d["mode"] == "trim_r":
            new_end = o_start + o_dur + dt
            s = self._snap(new_end, pts)
            if s is not None:
                new_end = s
                d["snap_x"] = self.x_of(s)
            dur = max(0.1, new_end - o_start)
            m = self.project.media.get(main.media_id) if main.media_id else None
            if m is not None and main.kind in ("video", "audio") and not main.freeze and not main.props.get("loop") \
                    and m.duration > 0:
                speed = float(main.props.get("speed", 1.0) or 1.0)
                dur = min(dur, (m.duration - main.source_in) / speed)
            main.duration = round(dur, 4)
        self.mw.live_changed()
        self.update()

    def _shift_keyframes(self, clip, offset, d):
        """Keep keyframes at the same movie time when the start is trimmed."""
        base = d.setdefault("kf_orig", {k: [list(x) for x in v] for k, v in clip.keyframes.items()})
        total = clip.start - d["origs"][clip.id][0]
        for k, keys in base.items():
            clip.keyframes[k] = [[kt - total, v, e] for kt, v, e in keys]

    def mouseReleaseEvent(self, ev):
        d = self._drag
        self._drag = None
        if d and d.get("mode") == "box" and not d.get("started"):
            if not d["add"] and self.selected:
                self.selected = []
                self.selectionChanged.emit()
            self.set_playhead(self.t_of(d["x0"]))
            if d.get("track") is not None:
                self.trackSelected.emit(d["track"].id)
            self.update()
            return
        if d and d.get("mode") == "box":
            n = len(self.selected)
            self.mw.status(f"{n} piece(s) selected. Drag one to move them all; Del deletes them; G groups them.")
            self.update()
            return
        if d and d.get("mode") == "mark":
            rng = self.marked_range()
            if rng:
                self.mw.status(f"Marked {rng[1] - rng[0]:.2f} s. Ctrl+Shift+Delete removes this time from every "
                               "track and closes it up.", 12000)
            self.update()
            return
        if d and d.get("started"):
            for tr in self.project.tracks:
                tr.sort()
            self.mw.end_edit()
        self.update()

    def mouseDoubleClickEvent(self, ev):
        tr, c = self.clip_at(ev.position())
        if c is not None:
            self.mw.focus_inspector()

    def wheelEvent(self, ev):
        dy = ev.angleDelta().y()
        dx = ev.angleDelta().x()
        mods = ev.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            f = 1.15 if dy > 0 else 1 / 1.15
            self.set_zoom(self.pps * f, ev.position().x())
        elif mods & Qt.KeyboardModifier.ShiftModifier:
            maxy = max(0, self.content_height() - self.height())
            self.scroll_y = int(max(0, min(maxy, self.scroll_y - dy / 2)))
        else:
            delta = (dx if abs(dx) > abs(dy) else dy)
            self.scroll_x = max(0.0, self.scroll_x - delta / self.pps / 2)
        self.update()

    def resizeEvent(self, ev):
        maxy = max(0, self.content_height() - self.height())
        self.scroll_y = min(self.scroll_y, maxy)
        super().resizeEvent(ev)

    # ------------------------------------------------------------ drag & drop from the panels
    def dragEnterEvent(self, ev):
        if ev.mimeData().hasFormat(MIME):
            ev.acceptProposedAction()

    def dragMoveEvent(self, ev):
        if ev.mimeData().hasFormat(MIME):
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        data = json.loads(bytes(ev.mimeData().data(MIME)).decode())
        pos = ev.position()
        tr, _, _ = self.row_at(pos.y())
        t = max(0.0, self.t_of(pos.x()))
        self.mw.add_item(data, t, tr)
        ev.acceptProposedAction()

    # ------------------------------------------------------------ context menu
    def _context_menu(self, gpos, tr, c, t):
        mw = self.mw
        m = QMenu(self)
        if c is None and tr is not None:
            g_all = mw.find_gap(t)
            g_one = mw.find_gap(t, tr)
            if g_all:
                a = m.addAction(f"Close this gap  ({g_all[1] - g_all[0]:.1f} s, all tracks move together)",
                                lambda: mw.close_gap(t))
                f = a.font()
                f.setBold(True)
                a.setFont(f)
            if g_one and (not g_all or abs((g_one[1] - g_one[0]) - (g_all[1] - g_all[0])) > 0.01):
                m.addAction(f"Close this gap on '{tr.name}' only  ({g_one[1] - g_one[0]:.1f} s)",
                            lambda: mw.close_gap(t, tr))
            if g_all or g_one:
                m.addSeparator()
        if c is not None:
            m.addAction("Split at playhead  (S)", mw.split_at_playhead)
            m.addAction("Delete  (Del)", mw.delete_selected)
            m.addAction("Delete and close the gap  (Shift+Del)", lambda: mw.delete_selected(ripple=True))
            m.addAction("Duplicate  (Ctrl+D)", mw.duplicate_selected)
            m.addAction("Copy  (Ctrl+C)", mw.copy_selected)
            m.addSeparator()
            m.addAction("Hide this piece" if c.enabled else "Show this piece", mw.toggle_enabled)
            if c.kind == "video":
                m.addAction("Freeze frame + character card  (F)", mw.freeze_frame)
                m.addAction("Switch camera here  (A)", mw.switch_angle)
                m.addAction("Sync selected clips by sound  (Y)", mw.sync_selected)
                m.addAction("Mute this clip's own sound" if not c.props.get("mute") else "Unmute this clip's sound",
                            mw.toggle_clip_mute)
            if c.kind in ("video", "image", "card"):
                pip = m.addMenu("Picture-in-picture")
                for key, label in mw.PIP_PRESETS:
                    pip.addAction(label, lambda k=key: mw.apply_pip(k))
            if c.kind in ("video", "image", "card", "adjust"):
                fxm = m.addMenu("Add effect")
                for key, label in mw.EFFECT_MENU:
                    fxm.addAction(label, lambda k=key: mw.add_effect(k))
            if c.kind in ("video", "image", "card"):
                tin = m.addMenu("Transition in")
                tout = m.addMenu("Transition out")
                from ..effects import TRANSITIONS, TRANSITION_LABELS
                for tt in TRANSITIONS:
                    tin.addAction(TRANSITION_LABELS[tt], lambda x=tt: mw.set_transition("in", x))
                    tout.addAction(TRANSITION_LABELS[tt], lambda x=tt: mw.set_transition("out", x))
        m.addSeparator()
        rng = self.marked_range()
        if rng:
            m.addAction(f"Remove the marked {rng[1] - rng[0]:.2f} s from every track  (Ctrl+Shift+Del)",
                        mw.remove_marked_time)
        m.addAction("Insert empty time at the playhead…  (Ctrl+Shift+T)", mw.insert_time_dialog)
        if len(self.selected) > 1:
            m.addAction("Group the selected pieces  (G)", mw.group_selected)
        if any((self.project.clip(i) or c).props.get("group") for i in self.selected if self.project.clip(i)):
            m.addAction("Ungroup  (Shift+G)", mw.ungroup_selected)
        m.addSeparator()
        if mw.clipboard:
            m.addAction("Paste at playhead  (Ctrl+V)", mw.paste)
        if tr is not None and tr.kind == "hud":
            m.addAction("Add whole-picture effect layer here", lambda: mw.add_adjustment(tr))
        m.addAction("Zoom to fit  (Z)", self.zoom_to_fit)
        m.exec(gpos)
