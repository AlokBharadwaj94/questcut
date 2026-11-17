"""Preview picture + the background thread that draws it."""
from __future__ import annotations

import threading
import time

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QThread, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..media import MediaPool
from ..renderer import Renderer


class RenderWorker(QThread):
    """Draws preview frames in the background so the window never freezes."""
    frameReady = Signal(QImage, float, float)  # image, time, ms

    def __init__(self, project):
        super().__init__()
        self._cv = threading.Condition()
        self._req = None
        self._project = project
        self._new_project = None
        self._stop = False
        self.pool = MediaPool(project, use_proxies=True)
        self.renderer = Renderer(project, self.pool, preview=True)

    def set_project(self, project_clone):
        with self._cv:
            self._new_project = project_clone
            self._cv.notify()

    def set_proxy(self, media_id, path):
        self.pool.proxy_ready[media_id] = path

    def request(self, t, W, H):
        with self._cv:
            self._req = (t, W, H)
            self._cv.notify()

    def stop(self):
        with self._cv:
            self._stop = True
            self._cv.notify()
        self.wait(3000)

    def run(self):
        while True:
            with self._cv:
                while self._req is None and not self._stop and self._new_project is None:
                    self._cv.wait()
                if self._stop:
                    break
                if self._new_project is not None:
                    self._project = self._new_project
                    self._new_project = None
                    self.pool.set_project(self._project)
                    self.renderer.project = self._project
                req = self._req
                self._req = None
            if req is None:
                continue
            t, W, H = req
            t0 = time.perf_counter()
            try:
                arr = self.renderer.render(t, W, H)
                img = QImage(arr.data, W, H, W * 3, QImage.Format.Format_RGB888).copy()
            except Exception as e:  # keep the preview alive
                print("preview error:", e)
                img = QImage(W, H, QImage.Format.Format_RGB888)
                img.fill(QColor("#300"))
            self.frameReady.emit(img, t, (time.perf_counter() - t0) * 1000)
        self.pool.close()


class Viewer(QWidget):
    """Shows the preview. Yellow dots can be dragged to move things."""

    def __init__(self, mw):
        super().__init__()
        self.mw = mw
        self.image = None
        self.setMinimumSize(320, 180)
        self.setMouseTracking(True)
        self._drag = None
        self.overlay_text = ""

    def img_rect(self):
        W, H = self.width(), self.height()
        pw, ph = self.mw.project.width, self.mw.project.height
        s = min(W / pw, H / ph)
        w, h = pw * s, ph * s
        return QRectF((W - w) / 2, (H - h) / 2, w, h)

    def preview_size(self, playing=False):
        r = self.img_rect()
        dpr = self.devicePixelRatioF()
        q = self.mw.preview_quality
        pw, ph = self.mw.project.width, self.mw.project.height
        if q == "full":
            w = pw
        elif q == "half":
            w = pw // 2
        elif q == "quarter":
            w = pw // 4
        else:  # auto
            w = int(r.width() * dpr)
            w = min(w, 960 if playing else pw)
        w = max(160, min(pw, w)) // 2 * 2
        h = max(90, int(round(w * ph / pw))) // 2 * 2
        return w, h

    def set_image(self, img):
        self.image = img
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0c0d10"))
        r = self.img_rect()
        if self.image is not None:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            p.drawImage(r, self.image)
        else:
            p.fillRect(r, QColor("#000"))
        # handles
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        f = QFont(self.font())
        f.setPixelSize(11)
        f.setBold(True)
        p.setFont(f)
        for h in self.mw.viewer_handles():
            pt = QPointF(r.left() + h["x"] * r.width(), r.top() + h["y"] * r.height())
            p.setPen(QPen(QColor(0, 0, 0, 200), 3))
            p.setBrush(QColor("#ffd54a"))
            p.drawEllipse(pt, 7, 7)
            p.setPen(QColor("#ffd54a"))
            p.drawText(pt + QPointF(10, -8), h["label"])
        if self.overlay_text:
            p.setPen(QColor("#ffd54a"))
            p.drawText(QRectF(r.left() + 8, r.top() + 6, r.width() - 16, 20), Qt.AlignmentFlag.AlignLeft,
                       self.overlay_text)
        p.end()

    def _hit(self, pos):
        r = self.img_rect()
        for h in self.mw.viewer_handles():
            pt = QPointF(r.left() + h["x"] * r.width(), r.top() + h["y"] * r.height())
            if (pt - pos).manhattanLength() < 16:
                return h
        return None

    def mousePressEvent(self, ev):
        h = self._hit(ev.position())
        if h is not None:
            self._drag = h
            self.mw.begin_edit()
        else:
            self.mw.toggle_play()

    def mouseMoveEvent(self, ev):
        if self._drag is None:
            self.setCursor(Qt.CursorShape.SizeAllCursor if self._hit(ev.position()) else Qt.CursorShape.ArrowCursor)
            return
        r = self.img_rect()
        nx = (ev.position().x() - r.left()) / max(1, r.width())
        ny = (ev.position().y() - r.top()) / max(1, r.height())
        self.mw.move_handle(self._drag, nx, ny)

    def mouseReleaseEvent(self, ev):
        if self._drag is not None:
            self._drag = None
            self.mw.end_edit()
