"""HUD elements in the style of well-known games.

Each element's menu name says which game screen inspired it. Only the look
and layout are borrowed; every shape, icon and pixel is drawn here from
scratch, and no game names, logos or artwork appear in the movie itself.
"""
from __future__ import annotations

import math
import random
import re

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPen,
                           QPolygonF, QRadialGradient)

from . import pixelfont
from .hud import (BAR_TYPES, DRAWERS, FULLSCREEN_TYPES, GROUP_ORDER, HUD_TYPES, PORTRAIT_TYPES, _icon, ease_out,
                  ease_out_back,
                  pixel_text, qc)

# ================================================================== text helpers
FAMILIES = {
    "quill": ["Palatino Linotype", "Book Antiqua", "Palatino", "Georgia", "DejaVu Serif", "Liberation Serif", "serif"],
    "garamond": ["EB Garamond", "Adobe Garamond Pro", "Garamond", "Cormorant Garamond", "Palatino Linotype",
                 "Book Antiqua", "Palatino", "Georgia", "DejaVu Serif", "serif"],
    "futura": ["Futura", "Futura PT", "Century Gothic", "Avenir Next", "Avenir", "Montserrat", "Trebuchet MS",
               "DejaVu Sans", "Liberation Sans", "sans-serif"],
    "round": ["Verdana", "Tahoma", "DejaVu Sans", "Arial", "Liberation Sans", "sans-serif"],
    "bold": ["Arial Black", "Arial", "Helvetica", "DejaVu Sans", "Liberation Sans", "sans-serif"],
}


def F(fam, px, bold=False, italic=False, spacing=100):
    f = QFont()
    f.setFamilies(FAMILIES.get(fam, FAMILIES["round"]))
    f.setPixelSize(max(1, int(px)))
    f.setBold(bold)
    f.setItalic(italic)
    if spacing != 100:
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, spacing)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


def tw(text, fam, size, bold=False, italic=False, spacing=100):
    if fam == "pixel":
        return pixelfont.text_width(text) * max(1, int(round(size / 7)))
    return QFontMetricsF(F(fam, size, bold, italic, spacing)).horizontalAdvance(text)


def _c(v, a=1.0):
    if isinstance(v, QColor):
        c = QColor(v)
        c.setAlphaF(c.alphaF() * a)
        return c
    return qc(v, a)


def T(p, text, x, y, fam, size, color, align="left", valign="top", bold=False, italic=False, spacing=100,
      outline=None, ow=0.0, shadow=None, sd=0.0, soft=0.0, glow=None, gr=0.0, alpha=1.0):
    """Draw one line of text and return its rectangle."""
    if not text:
        return QRectF(x, y, 0, 0)
    if fam == "pixel":
        px = max(1, int(round(size / 7)))
        w, h = pixelfont.text_width(text) * px, 7 * px
        if align == "center":
            x -= w / 2
        elif align == "right":
            x -= w
        if valign == "middle":
            y -= h / 2
        elif valign == "bottom":
            y -= h
        if outline is not None:
            oc = _c(outline, alpha)
            for dx, dy in ((-px, 0), (px, 0), (0, -px), (0, px)):
                pixel_text(p, text, x + dx, y + dy, px, oc)
        return pixel_text(p, text, x, y, px, _c(color, alpha), shadow=_c(shadow, alpha) if shadow else None)
    f = F(fam, size, bold, italic, spacing)
    fm = QFontMetricsF(f)
    w = fm.horizontalAdvance(text)
    asc = fm.ascent()
    h = asc + fm.descent()
    if align == "center":
        x -= w / 2
    elif align == "right":
        x -= w
    if valign == "middle":
        y -= h / 2
    elif valign == "bottom":
        y -= h
    path = QPainterPath()
    path.addText(QPointF(x, y + asc), f, text)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    if soft > 0:
        for i in range(4, 0, -1):
            pen = QPen(QColor(0, 0, 0, int(40 * alpha)), soft * i / 2)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.strokePath(path, pen)
    if glow is not None and gr > 0:
        g = _c(glow, alpha)
        for i in range(5, 0, -1):
            cc = QColor(g)
            cc.setAlphaF(g.alphaF() * 0.12)
            pen = QPen(cc, gr * i / 2.5)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.strokePath(path, pen)
    if shadow is not None and sd:
        p.fillPath(path.translated(sd, sd), _c(shadow, alpha))
    if outline is not None and ow > 0:
        pen = QPen(_c(outline, alpha), ow)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.strokePath(path, pen)
    p.fillPath(path, _c(color, alpha))
    p.restore()
    pad = ow + soft * 2 + gr * 2 + abs(sd)
    return QRectF(x - pad, y - pad, w + 2 * pad, h + 2 * pad)


def wrap(text, fam, size, maxw, bold=False, spacing=100):
    lines = []
    for para in text.split("\n"):
        cur = ""
        for wd in para.split(" "):
            trial = (cur + " " + wd) if cur else wd
            if tw(trial, fam, size, bold, spacing=spacing) <= maxw or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = wd
        lines.append(cur)
    return lines


def lines_of(c, key):
    return [ln for ln in c.text(key).split("\n") if ln.strip()]


# ================================================================== icons (all original simple drawings)
ICONS = ["pipette", "microscope", "flask", "coffee", "book", "sword", "shield", "star", "leaf", "mushroom", "coin",
         "gem", "key", "scroll", "flame", "heart"]


def draw_icon(p, kind, cx, cy, r):
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    dark = QPen(QColor(30, 22, 15), max(1.0, r * 0.07))
    dark.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    if kind in ("coin", "star", "heart"):
        p.restore()
        _icon(p, kind, cx, cy, r * 0.85, "#ffcc33", "rpg")
        return
    p.translate(cx, cy)
    if kind == "pipette":
        p.rotate(-40)
        p.setPen(dark)
        p.setBrush(QColor(220, 235, 245, 230))
        p.drawRoundedRect(QRectF(-0.13 * r, -0.55 * r, 0.26 * r, 1.05 * r), 0.08 * r, 0.08 * r)
        p.setBrush(QColor("#3d8fe0"))
        p.drawRect(QRectF(-0.09 * r, 0.1 * r, 0.18 * r, 0.38 * r))
        p.setBrush(QColor("#e05a3d"))
        p.drawRoundedRect(QRectF(-0.2 * r, -0.92 * r, 0.4 * r, 0.4 * r), 0.12 * r, 0.12 * r)
        p.setBrush(QColor(220, 235, 245, 230))
        p.drawPolygon(QPolygonF([QPointF(-0.13 * r, 0.5 * r), QPointF(0.13 * r, 0.5 * r), QPointF(0, 0.98 * r)]))
    elif kind == "microscope":
        p.setPen(dark)
        p.setBrush(QColor("#3a3f4b"))
        p.drawRoundedRect(QRectF(-0.7 * r, 0.62 * r, 1.4 * r, 0.25 * r), 0.06 * r, 0.06 * r)
        p.setBrush(QColor("#d9dde3"))
        p.drawRect(QRectF(-0.45 * r, 0.15 * r, 0.6 * r, 0.12 * r))
        path = QPainterPath()
        path.moveTo(0.35 * r, 0.62 * r)
        path.quadTo(0.75 * r, 0.0, 0.25 * r, -0.45 * r)
        pen = QPen(QColor("#3a3f4b"), 0.22 * r)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.strokePath(path, pen)
        p.rotate(-25)
        p.setPen(dark)
        p.setBrush(QColor("#e8ecf1"))
        p.drawRoundedRect(QRectF(-0.2 * r, -0.95 * r, 0.32 * r, 1.0 * r), 0.06 * r, 0.06 * r)
        p.setBrush(QColor("#3a3f4b"))
        p.drawRect(QRectF(-0.24 * r, -0.98 * r, 0.4 * r, 0.16 * r))
    elif kind == "flask":
        path = QPainterPath()
        path.moveTo(-0.15 * r, -0.85 * r)
        path.lineTo(0.15 * r, -0.85 * r)
        path.lineTo(0.15 * r, -0.3 * r)
        path.lineTo(0.7 * r, 0.75 * r)
        path.quadTo(0.75 * r, 0.9 * r, 0.6 * r, 0.9 * r)
        path.lineTo(-0.6 * r, 0.9 * r)
        path.quadTo(-0.75 * r, 0.9 * r, -0.7 * r, 0.75 * r)
        path.lineTo(-0.15 * r, -0.3 * r)
        path.closeSubpath()
        p.fillPath(path, QColor(220, 240, 250, 200))
        p.save()
        p.setClipRect(QRectF(-r, 0.2 * r, 2 * r, r))
        p.fillPath(path, QColor("#46d07a"))
        p.restore()
        p.setPen(dark)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.setBrush(QColor(255, 255, 255, 200))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(-0.15 * r, 0.55 * r), 0.08 * r, 0.08 * r)
        p.drawEllipse(QPointF(0.2 * r, 0.4 * r), 0.06 * r, 0.06 * r)
    elif kind == "coffee":
        p.setPen(dark)
        p.setBrush(QColor("#f2efe9"))
        p.drawEllipse(QRectF(-0.85 * r, 0.62 * r, 1.7 * r, 0.3 * r))
        p.drawRoundedRect(QRectF(-0.55 * r, -0.15 * r, 1.0 * r, 0.85 * r), 0.15 * r, 0.15 * r)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(0.35 * r, 0.0, 0.42 * r, 0.42 * r))
        p.setBrush(QColor("#6b3f1d"))
        p.drawEllipse(QRectF(-0.5 * r, -0.22 * r, 0.9 * r, 0.18 * r))
        steam = QPen(QColor(255, 255, 255, 200), 0.08 * r)
        steam.setCapStyle(Qt.PenCapStyle.RoundCap)
        for dx in (-0.25, 0.05):
            path = QPainterPath()
            path.moveTo(dx * r, -0.35 * r)
            path.cubicTo((dx + 0.15) * r, -0.55 * r, (dx - 0.15) * r, -0.7 * r, dx * r, -0.9 * r)
            p.strokePath(path, steam)
    elif kind == "book":
        p.rotate(-8)
        p.setPen(dark)
        p.setBrush(QColor("#f5ecd6"))
        p.drawRect(QRectF(-0.55 * r, -0.72 * r, 1.2 * r, 1.45 * r))
        p.setBrush(QColor("#9c2b23"))
        p.drawRoundedRect(QRectF(-0.65 * r, -0.8 * r, 1.15 * r, 1.5 * r), 0.08 * r, 0.08 * r)
        p.setBrush(QColor("#e1b54a"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(QRectF(-0.4 * r, -0.45 * r, 0.65 * r, 0.12 * r))
        p.drawRect(QRectF(-0.4 * r, -0.25 * r, 0.45 * r, 0.08 * r))
    elif kind == "sword":
        p.rotate(45)
        p.setPen(dark)
        p.setBrush(QColor("#d9dee6"))
        p.drawPolygon(QPolygonF([QPointF(-0.12 * r, 0.3 * r), QPointF(-0.12 * r, -0.8 * r), QPointF(0, -1.0 * r),
                                 QPointF(0.12 * r, -0.8 * r), QPointF(0.12 * r, 0.3 * r)]))
        p.setBrush(QColor("#d4a83a"))
        p.drawRoundedRect(QRectF(-0.42 * r, 0.28 * r, 0.84 * r, 0.14 * r), 0.05 * r, 0.05 * r)
        p.setBrush(QColor("#6b4423"))
        p.drawRect(QRectF(-0.08 * r, 0.42 * r, 0.16 * r, 0.42 * r))
        p.setBrush(QColor("#d4a83a"))
        p.drawEllipse(QPointF(0, 0.9 * r), 0.12 * r, 0.12 * r)
    elif kind == "shield":
        path = QPainterPath()
        path.moveTo(0, -0.85 * r)
        path.quadTo(0.45 * r, -0.65 * r, 0.75 * r, -0.7 * r)
        path.quadTo(0.8 * r, 0.4 * r, 0, 0.9 * r)
        path.quadTo(-0.8 * r, 0.4 * r, -0.75 * r, -0.7 * r)
        path.quadTo(-0.45 * r, -0.65 * r, 0, -0.85 * r)
        g = QLinearGradient(-r, -r, r, r)
        g.setColorAt(0, QColor("#4a78c8"))
        g.setColorAt(1, QColor("#1d3a75"))
        p.fillPath(path, QBrush(g))
        p.setPen(QPen(QColor("#d4a83a"), 0.12 * r))
        p.drawPath(path)
        p.drawLine(QPointF(0, -0.7 * r), QPointF(0, 0.7 * r))
    elif kind == "leaf":
        path = QPainterPath()
        path.moveTo(-0.7 * r, 0.7 * r)
        path.quadTo(-0.8 * r, -0.6 * r, 0.75 * r, -0.75 * r)
        path.quadTo(0.6 * r, 0.75 * r, -0.7 * r, 0.7 * r)
        g = QLinearGradient(-r, r, r, -r)
        g.setColorAt(0, QColor("#2f8a2f"))
        g.setColorAt(1, QColor("#8bd34a"))
        p.fillPath(path, QBrush(g))
        p.setPen(dark)
        p.drawPath(path)
        p.setPen(QPen(QColor("#1f5a1f"), 0.07 * r))
        p.drawLine(QPointF(-0.7 * r, 0.7 * r), QPointF(0.45 * r, -0.45 * r))
    elif kind == "mushroom":
        p.setPen(dark)
        p.setBrush(QColor("#efe2c4"))
        p.drawRoundedRect(QRectF(-0.25 * r, -0.1 * r, 0.5 * r, 0.95 * r), 0.15 * r, 0.15 * r)
        cap = QPainterPath()
        cap.moveTo(-0.85 * r, 0.05 * r)
        cap.cubicTo(-0.85 * r, -0.9 * r, 0.85 * r, -0.9 * r, 0.85 * r, 0.05 * r)
        cap.closeSubpath()
        p.setBrush(QColor("#a5582c"))
        p.drawPath(cap)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#f3e3c2"))
        for dx, dy, rr in ((-0.4, -0.3, 0.12), (0.15, -0.5, 0.1), (0.45, -0.15, 0.09)):
            p.drawEllipse(QPointF(dx * r, dy * r), rr * r, rr * r)
    elif kind == "gem":
        pts = [QPointF(-0.5 * r, -0.6 * r), QPointF(0.5 * r, -0.6 * r), QPointF(0.85 * r, -0.15 * r),
               QPointF(0, 0.9 * r), QPointF(-0.85 * r, -0.15 * r)]
        g = QLinearGradient(-r, -r, r, r)
        g.setColorAt(0, QColor("#9fe8ff"))
        g.setColorAt(1, QColor("#1b6fd1"))
        p.setPen(dark)
        p.setBrush(QBrush(g))
        p.drawPolygon(QPolygonF(pts))
        p.setPen(QPen(QColor(255, 255, 255, 150), 0.05 * r))
        p.drawLine(QPointF(-0.85 * r, -0.15 * r), QPointF(0.85 * r, -0.15 * r))
        p.drawLine(QPointF(-0.25 * r, -0.15 * r), QPointF(0, 0.9 * r))
        p.drawLine(QPointF(0.25 * r, -0.15 * r), QPointF(0, 0.9 * r))
    elif kind == "key":
        p.rotate(-35)
        pen = QPen(QColor("#d4a83a"), 0.18 * r)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(0, -0.55 * r), 0.3 * r, 0.3 * r)
        p.drawLine(QPointF(0, -0.25 * r), QPointF(0, 0.85 * r))
        p.drawLine(QPointF(0, 0.55 * r), QPointF(0.3 * r, 0.55 * r))
        p.drawLine(QPointF(0, 0.8 * r), QPointF(0.25 * r, 0.8 * r))
    elif kind == "scroll":
        p.rotate(-20)
        p.setPen(dark)
        p.setBrush(QColor("#ead9b0"))
        p.drawRect(QRectF(-0.55 * r, -0.5 * r, 1.1 * r, 1.0 * r))
        p.setBrush(QColor("#c9b07a"))
        p.drawRoundedRect(QRectF(-0.7 * r, -0.62 * r, 1.4 * r, 0.22 * r), 0.11 * r, 0.11 * r)
        p.drawRoundedRect(QRectF(-0.7 * r, 0.42 * r, 1.4 * r, 0.22 * r), 0.11 * r, 0.11 * r)
        p.setPen(QPen(QColor("#7a6040"), 0.05 * r))
        for k in range(3):
            y = -0.25 * r + k * 0.22 * r
            p.drawLine(QPointF(-0.38 * r, y), QPointF(0.38 * r, y))
    elif kind == "flame":
        path = QPainterPath()
        path.moveTo(0, -1.0 * r)
        path.cubicTo(0.5 * r, -0.35 * r, 0.75 * r, 0.25 * r, 0, 0.9 * r)
        path.cubicTo(-0.75 * r, 0.25 * r, -0.5 * r, -0.35 * r, 0, -1.0 * r)
        g = QRadialGradient(0, 0.4 * r, r)
        g.setColorAt(0, QColor("#fff6c0"))
        g.setColorAt(0.4, QColor("#ffc844"))
        g.setColorAt(1, QColor("#e0701a"))
        p.fillPath(path, QBrush(g))
    p.restore()


# ================================================================== shared frames
SD_OUT, SD_MID, SD_FILL, SD_LIGHT, SD_TEXT = "#5b2b0a", "#d9761e", "#f9c886", "#ffe4b5", "#3f1d00"


def sd_box(p, r, s, fill=SD_FILL, light=False):
    """Wooden orange panel (Stardew-like)."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(SD_OUT))
    p.drawRoundedRect(r, 7 * s, 7 * s)
    r2 = r.adjusted(3 * s, 3 * s, -3 * s, -3 * s)
    g = QLinearGradient(0, r2.top(), 0, r2.bottom())
    g.setColorAt(0, QColor("#f0a04b"))
    g.setColorAt(1, QColor(SD_MID))
    p.setBrush(QBrush(g))
    p.drawRoundedRect(r2, 5 * s, 5 * s)
    r3 = r2.adjusted(5 * s, 5 * s, -5 * s, -5 * s)
    p.setBrush(QColor(SD_OUT))
    p.drawRect(r3.adjusted(-1.5 * s, -1.5 * s, 1.5 * s, 1.5 * s))
    p.setBrush(QColor(SD_LIGHT if light else fill))
    p.drawRect(r3)
    p.setBrush(QColor(255, 255, 255, 60))
    p.drawRect(QRectF(r3.left(), r3.top(), r3.width(), 3 * s))
    p.restore()


SK_LINE = QColor(210, 210, 210, 235)


def sk_bar(p, cx, cy, w, h, s, frac, color, anchor="center", ghost=None, frame_alpha=1.0):
    """Thin bar with pointed ends and small diamonds (Skyrim-like)."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    x0, x1 = cx - w / 2, cx + w / 2
    tip = h * 0.9
    line = QColor(SK_LINE)
    line.setAlphaF(line.alphaF() * frame_alpha)
    outer = QPolygonF([QPointF(x0 - tip, cy), QPointF(x0, cy - h / 2), QPointF(x1, cy - h / 2), QPointF(x1 + tip, cy),
                       QPointF(x1, cy + h / 2), QPointF(x0, cy + h / 2)])
    p.setPen(QPen(line, 1.3 * s))
    p.setBrush(QColor(0, 0, 0, int(110 * frame_alpha)))
    p.drawPolygon(outer)
    d = h * 0.32
    p.setBrush(Qt.BrushStyle.NoBrush)
    for ex in (x0 - tip - d * 1.7, x1 + tip + d * 1.7):
        p.drawPolygon(QPolygonF([QPointF(ex - d, cy), QPointF(ex, cy - d), QPointF(ex + d, cy), QPointF(ex, cy + d)]))
    ih = h * 0.46
    iw = w - 2 * s

    def fill(fr, col):
        fr = max(0.0, min(1.0, fr))
        fw = iw * fr
        if fw <= 0.5:
            return
        if anchor == "center":
            fx = cx - fw / 2
        elif anchor == "left":
            fx = x0 + s
        else:
            fx = x1 - s - fw
        g = QLinearGradient(0, cy - ih / 2, 0, cy + ih / 2)
        base = _c(col)
        g.setColorAt(0, base.lighter(160))
        g.setColorAt(0.5, base)
        g.setColorAt(1, base.darker(150))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawRect(QRectF(fx, cy - ih / 2, fw, ih))

    if ghost is not None and ghost > frac:
        fill(ghost, QColor(255, 235, 200))
    fill(frac, color)
    p.restore()
    return QRectF(x0 - tip - 4 * d, cy - h, w + 2 * tip + 8 * d, 2 * h)


def gradient_line(p, x0, x1, y, color, width, alpha=1.0):
    g = QLinearGradient(x0, 0, x1, 0)
    c0, c1 = _c(color, 0), _c(color, alpha)
    g.setColorAt(0, c0)
    g.setColorAt(0.2, c1)
    g.setColorAt(0.8, c1)
    g.setColorAt(1, c0)
    p.fillRect(QRectF(x0, y - width / 2, x1 - x0, width), QBrush(g))


def _drop_number(c, window=1.5):
    v = c.bar_value()
    before = c.bar_value(max(0.0, c.t - window))
    return before - v


# ================================================================== RuneScape-inspired
def rs_level(p, c):
    s = c.s
    x, y = c.X(), c.Y()
    bw, bh = 1000 * s, 240 * s
    r = QRectF(x - bw / 2, y - bh / 2, bw, bh)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    g = QLinearGradient(0, r.top(), 0, r.bottom())
    g.setColorAt(0, QColor("#e4d9bc"))
    g.setColorAt(1, QColor("#cdbf9a"))
    p.setPen(QPen(QColor("#2b241b"), 4 * s))
    p.setBrush(QBrush(g))
    p.drawRect(r)
    p.setPen(QPen(QColor("#8a7b5e"), 2 * s))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(r.adjusted(8 * s, 8 * s, -8 * s, -8 * s))
    rnd = random.Random(5)
    p.setPen(Qt.PenStyle.NoPen)
    for _ in range(140):
        p.setBrush(QColor(110, 90, 60, rnd.randint(15, 45)))
        p.drawEllipse(QPointF(r.left() + rnd.random() * bw, r.top() + rnd.random() * bh), rnd.uniform(1, 4) * s,
                      rnd.uniform(1, 3) * s)
    p.restore()
    draw_icon(p, c.text("icon", "pipette"), r.left() + 120 * s, r.center().y(), 72 * s)
    skill, level = c.text("skill", "Pipetting"), c.text("level", "2")
    art = "an" if skill[:1].lower() in "aeiou" else "a"
    tx = (r.left() + 230 * s + r.right() - 40 * s) / 2
    blue = c.text("color", "#1c1ca3")
    line1 = f"Congratulations, you just advanced {art} {skill} level."
    room = r.right() - 40 * s - (r.left() + 230 * s)
    size = 31 * s
    widest = max(tw(line1, "quill", size), tw(f"Your {skill} level is now {level}.", "quill", size))
    if widest > room:
        size *= room / widest
    T(p, line1, tx, r.top() + bh * 0.24, "quill", size, blue,
      "center", "middle")
    T(p, f"Your {skill} level is now {level}.", tx, r.top() + bh * 0.5, "quill", size, "#000000", "center", "middle")
    T(p, c.text("continue", "Click here to continue"), tx, r.top() + bh * 0.78, "quill", size, blue, "center", "middle")
    box = QRectF(r)
    if c.clip.props.get("fireworks", True) and c.t < 2.4:
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        for k, (fx, fy, col) in enumerate(((-0.25, -0.75, "#ffd84a"), (0.05, -1.05, "#ff5a5a"), (0.3, -0.8, "#6ad8ff"))):
            tt = c.t - k * 0.35
            if tt <= 0 or tt > 1.4:
                continue
            q = tt / 1.4
            cx_, cy_ = x + fx * bw, y + fy * bh
            for i in range(24):
                a = i / 24 * 2 * math.pi
                d = 120 * s * ease_out(q)
                p.setBrush(_c(col, 1 - q))
                p.drawEllipse(QPointF(cx_ + math.cos(a) * d, cy_ + math.sin(a) * d + 40 * s * q * q), 5 * s, 5 * s)
        p.restore()
        box = box.united(QRectF(x - bw / 2, y - bh * 1.6, bw, bh))
    return box.adjusted(-6, -6, 6, 6)


SPLAT_COLORS = {"hit": ("#d42424", "#7a0b0b"), "zero": ("#3a78e0", "#163d80"), "poison": ("#3fb53a", "#1a5a18"),
                "heal": ("#d455c8", "#6d2378"), "max": ("#ff8a1a", "#9a3a00")}


def rs_hitsplat(p, c):
    s = c.s
    x, y = c.X(), c.Y()
    key = c.text("target_bar")
    if key and c.clip.props.get("follow_bar", True):
        b = c.links.bar_at(key, c.clip.start + c.t)
        if b is not None and b.hud_type in ("rs_hpbar", "name_tag"):
            bt = c.clip.start + c.t - b.start
            x = (float(b.value("x", bt, 0.5)) + float(c.val("offset_x", 0.0))) * c.W
            y = (float(b.value("y", bt, 0.5)) + float(c.val("offset_y", 0.09))) * c.H
    kind = c.text("kind", "hit")
    col, dark = SPLAT_COLORS.get(kind, SPLAT_COLORS["hit"])
    sc = 1 + 0.5 * max(0.0, 1 - c.t / 0.12)
    R = 44 * s
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.translate(x, y)
    p.scale(sc, sc)
    rnd = random.Random(int(c.clip.start * 100) + 3)
    pts = []
    for i in range(14):
        a = i / 14 * 2 * math.pi
        rr = R * (1.0 if i % 2 == 0 else 0.72) * rnd.uniform(0.92, 1.08)
        pts.append(QPointF(math.cos(a) * rr, math.sin(a) * rr * 0.9))
    g = QRadialGradient(0, -R * 0.2, R * 1.2)
    g.setColorAt(0, _c(col).lighter(140))
    g.setColorAt(0.6, _c(col))
    g.setColorAt(1, _c(dark))
    pen = QPen(QColor(20, 0, 0), 2.5 * s)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(QBrush(g))
    p.drawPolygon(QPolygonF(pts))
    if kind == "max":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 220, 80, 160))
        for i in range(5):
            a = -math.pi / 2 + (i - 2) * 0.35
            p.drawEllipse(QPointF(math.cos(a) * R * 1.05, math.sin(a) * R * 1.05), 7 * s, 11 * s)
    p.restore()
    T(p, c.text("text", "12"), x, y, "bold", 34 * s * sc, "#ffffff", "center", "middle", outline="#000000",
      ow=4 * s)
    return QRectF(x - R * 1.6, y - R * 1.6, R * 3.2, R * 3.2)


CHAT_COLORS = {"yellow": "#ffff00", "red": "#ff2020", "green": "#20ff20", "cyan": "#20ffff", "purple": "#ff40ff",
               "white": "#ffffff"}


def rs_chat(p, c):
    s = c.s
    x, y = c.X(), c.Y()
    text = c.text("text", "Free coffee in the lab!")
    eff = c.text("effect", "wave")
    t = c.t
    base = QColor(CHAT_COLORS.get(c.text("color", "yellow"), "#ffff00"))
    if eff == "flash1":
        base = QColor("#ff2020") if int(t * 4) % 2 else QColor("#ffff00")
    elif eff == "flash2":
        base = QColor("#20ffff") if int(t * 4) % 2 else QColor("#2040ff")
    elif eff == "flash3":
        base = QColor("#20ff20") if int(t * 4) % 2 else QColor("#a0ffa0")
    elif eff == "glow":
        hcycle = (math.sin(t * 2) * 0.5 + 0.5) * 0.33
        base = QColor.fromHsvF(hcycle, 1.0, 1.0)
    f = F("bold", 30 * s)
    fm = QFontMetricsF(f)
    total = fm.horizontalAdvance(text)
    x0 = x - total / 2
    shift_x = 0.0
    if eff == "scroll":
        shift_x = total * (1 - min(1.0, t / 1.5))
    if eff == "slide":
        y -= 40 * s * (1 - ease_out(min(1.0, t / 0.6)))
    main, shadow = QPainterPath(), QPainterPath()
    cx = x0 + shift_x
    for i, ch in enumerate(text):
        dx = dy = 0.0
        if eff == "wave":
            dy = math.sin(i * 0.7 + t * 7) * 6 * s
        elif eff == "wave2":
            dy = math.sin(i * 0.7 + t * 7) * 6 * s
            dx = math.cos(i * 0.7 + t * 7) * 3 * s
        elif eff == "shake":
            dy = (random.Random(int(t * 20) * 97 + i).random() - 0.5) * 10 * s
        main.addText(QPointF(cx + dx, y + dy), f, ch)
        shadow.addText(QPointF(cx + dx + 2 * s, y + dy + 2 * s), f, ch)
        cx += fm.horizontalAdvance(ch)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    if eff == "scroll":
        p.setClipRect(QRectF(x0, y - 60 * s, total, 90 * s))
    p.fillPath(shadow, QColor(0, 0, 0))
    p.fillPath(main, base)
    p.restore()
    return QRectF(x0 - 20 * s, y - 60 * s, total + 40 * s, 90 * s)


def rs_xpdrop(p, c):
    s = c.s
    right, top = c.X(), c.Y()
    amount = float(c.val("amount", 35))
    total = float(c.val("total", 13034404))
    arrive = c.dur * 0.6
    shown = total + (amount if c.t >= arrive else 0)
    label = f"XP: {int(shown):,}"
    w = tw(label, "bold", 24 * s) + 34 * s
    box = QRectF(right - w, top, w, 42 * s)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(QPen(QColor("#1a150f"), 2 * s))
    p.setBrush(QColor(70, 60, 45, 215))
    p.drawRect(box)
    p.setPen(QPen(QColor(130, 115, 85), 1.2 * s))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(box.adjusted(3 * s, 3 * s, -3 * s, -3 * s))
    p.restore()
    T(p, label, right - 17 * s, top + 21 * s, "bold", 24 * s, "#ffffff", "right", "middle", shadow="#000000", sd=2 * s)
    if c.t < arrive + 0.15:
        q = min(1.0, c.t / arrive)
        yy = top + 60 * s + (1 - q) * 240 * s
        a = 1.0 if q < 0.85 else max(0.0, (1 - q) / 0.15)
        r = T(p, f"+{int(amount)}", right - 17 * s, yy, "bold", 26 * s, "#ffffff", "right", "middle", shadow="#000000",
              sd=2 * s, alpha=a)
        p.save()
        p.setOpacity(p.opacity() * a)
        draw_icon(p, c.text("icon", "microscope"), r.left() - 22 * s, yy, 18 * s)
        p.restore()
    return QRectF(right - w - 120 * s, top - 4, w + 124 * s, 340 * s)


# ---------------------------------------------------------------- RuneScape quest pieces
RS_RED, RS_BLUE = "#800000", "#0000ff"


def rs_parchment(p, r, s, seed=5):
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    g = QLinearGradient(0, r.top(), 0, r.bottom())
    g.setColorAt(0, QColor("#e4d9bc"))
    g.setColorAt(1, QColor("#cdbf9a"))
    p.setPen(QPen(QColor("#2b241b"), 4 * s))
    p.setBrush(QBrush(g))
    p.drawRect(r)
    p.setPen(QPen(QColor("#8a7b5e"), 2 * s))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(r.adjusted(8 * s, 8 * s, -8 * s, -8 * s))
    rnd = random.Random(seed)
    p.setPen(Qt.PenStyle.NoPen)
    for _ in range(int(r.width() * r.height() / (7000 * s * s)) + 20):
        p.setBrush(QColor(110, 90, 60, rnd.randint(15, 45)))
        p.drawEllipse(QPointF(r.left() + rnd.random() * r.width(), r.top() + rnd.random() * r.height()),
                      rnd.uniform(1, 4) * s, rnd.uniform(1, 3) * s)
    p.restore()


def _chathead(p, c, hr):
    img = _portrait_image(c, float(c.val("pixel_size", 64)) if c.clip.props.get("pixel_portrait", False) else 0)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    clip = QPainterPath()
    clip.addRoundedRect(hr, hr.width() * 0.18, hr.width() * 0.18)
    p.setClipPath(clip)
    if img is not None:
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, not c.clip.props.get("pixel_portrait", False))
        p.drawImage(hr, img)
    else:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(90, 70, 45, 150))
        p.drawEllipse(QPointF(hr.center().x(), hr.top() + hr.height() * 0.42), hr.width() * 0.24, hr.width() * 0.27)
        p.drawEllipse(QPointF(hr.center().x(), hr.bottom() + hr.height() * 0.12), hr.width() * 0.42, hr.height() * 0.4)
    p.restore()
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(QPen(QColor(60, 45, 30, 160), 2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(hr, hr.width() * 0.18, hr.width() * 0.18)
    p.restore()


def rs_dialogue(p, c):
    s = c.s
    cx, bottom = c.X(), c.Y()
    w, h = 1060 * s, 300 * s
    r = QRectF(cx - w / 2, bottom - h, w, h)
    rs_parchment(p, r, s, 9)
    left = c.text("side", "left") == "left"
    hs = 230 * s
    hr = QRectF(r.left() + 30 * s if left else r.right() - 30 * s - hs, r.center().y() - hs / 2, hs, hs)
    _chathead(p, c, hr)
    tx0 = r.left() + (hs + 60 * s if left else 40 * s)
    tx1 = r.right() - (40 * s if left else hs + 60 * s)
    mid = (tx0 + tx1) / 2
    T(p, c.text("name", "Professor Grid"), mid, r.top() + 42 * s, "quill", 32 * s, RS_RED, "center", "middle")
    text = c.text("text")
    cps = float(c.val("cps", 0))
    shown = len(text) if cps <= 0 else int(max(0.0, c.t - 0.1) * cps)
    rem = shown
    for i, ln in enumerate(wrap(text, "quill", 30 * s, tx1 - tx0)[:4]):
        T(p, ln[:max(0, rem)], mid, r.top() + 92 * s + i * 40 * s, "quill", 30 * s, "#000000", "center", "middle")
        rem -= len(ln) + 1
    if shown >= len(text):
        T(p, c.text("continue", "Click here to continue"), mid, r.bottom() - 36 * s, "quill", 30 * s, RS_BLUE,
          "center", "middle")
    return r.adjusted(-6, -6, 6, 6)


def rs_options(p, c):
    s = c.s
    cx, bottom = c.X(), c.Y()
    w, h = 1060 * s, 300 * s
    r = QRectF(cx - w / 2, bottom - h, w, h)
    rs_parchment(p, r, s, 11)
    T(p, c.text("title", "Select an Option"), cx, r.top() + 42 * s, "quill", 32 * s, RS_RED, "center", "middle")
    opts = lines_of(c, "options")[:5]
    sel = int(round(float(c.val("selected", -1))))
    step = min(48 * s, (h - 100 * s) / max(1, len(opts)))
    numbered = bool(c.clip.props.get("numbered", False))
    for i, op in enumerate(opts):
        y = r.top() + 96 * s + i * step
        T(p, (f"{i + 1}. " if numbered else "") + op, cx, y, "quill", 30 * s, "#ffffff" if i == sel else "#000000",
          "center", "middle", shadow="#000000" if i == sel else None, sd=1.5 * s if i == sel else 0)
    return r.adjusted(-6, -6, 6, 6)


def rs_hpbar(p, c):
    s = c.s
    cx, cy = c.X(), c.Y()
    w, h = float(c.val("width", 150)) * s, 16 * s
    r = QRectF(cx - w / 2, cy - h / 2, w, h)
    mx = max(1e-6, float(c.val("max_value", 100)))
    frac = max(0.0, min(1.0, c.bar_value() / mx))
    p.fillRect(r.adjusted(-2 * s, -2 * s, 2 * s, 2 * s), QColor("#000000"))
    p.fillRect(r, QColor("#ff0000"))
    p.fillRect(QRectF(r.left(), r.top(), r.width() * frac, r.height()), QColor("#00ff00"))
    label = c.text("label")
    if label:
        T(p, label, cx, r.top() - 6 * s, "bold", 22 * s, "#ffff00", "center", "bottom", shadow="#000000", sd=2 * s)
    return r.adjusted(-6 * s, -40 * s, 6 * s, 6 * s)


def rs_questdone(p, c):
    s = c.s
    cx, cy = c.X(), c.Y()
    w, h = 980 * s, 620 * s
    body = QRectF(cx - w / 2, cy - h / 2 + 40 * s, w, h - 80 * s)
    rs_parchment(p, body, s, 13)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    for ry in (body.top() - 30 * s, body.bottom() - 26 * s):
        roll = QRectF(body.left() - 34 * s, ry, w + 68 * s, 56 * s)
        g = QLinearGradient(0, roll.top(), 0, roll.bottom())
        g.setColorAt(0, QColor("#b9a477"))
        g.setColorAt(0.5, QColor("#efe3c2"))
        g.setColorAt(1, QColor("#8f7a4f"))
        p.setPen(QPen(QColor("#2b241b"), 3 * s))
        p.setBrush(QBrush(g))
        p.drawRoundedRect(roll, 28 * s, 28 * s)
    p.restore()
    top = body.top() + 40 * s
    T(p, f"You have completed {c.text('quest', 'The Missing Grids')}!", cx, top + 22 * s, "quill", 40 * s, RS_RED,
      "center", "middle")
    ix, iy = body.left() + 190 * s, body.center().y() + 20 * s
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    rg = QRadialGradient(ix, iy, 130 * s)
    rg.setColorAt(0, QColor(255, 240, 180, 160))
    rg.setColorAt(1, QColor(255, 240, 180, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(rg))
    p.drawEllipse(QPointF(ix, iy), 130 * s, 130 * s)
    p.restore()
    draw_icon(p, c.text("icon", "pipette"), ix, iy, 90 * s)
    colx = body.left() + w * 0.63
    T(p, "You are awarded:", colx, top + 100 * s, "quill", 32 * s, RS_RED, "center", "middle")
    for i, ln in enumerate(lines_of(c, "rewards")[:7]):
        if c.t > 0.35 + i * 0.25:
            T(p, ln, colx, top + 150 * s + i * 42 * s, "quill", 30 * s, "#000000", "center", "middle")
    T(p, "Quest Points:", body.left() + 50 * s, body.bottom() - 70 * s, "quill", 28 * s, RS_RED, "left", "middle")
    T(p, c.text("points", "42"), body.left() + 50 * s + tw("Quest Points: ", "quill", 28 * s), body.bottom() - 70 * s,
      "quill", 28 * s, "#000000", "left", "middle")
    xb = QRectF(body.right() - 64 * s, body.top() + 18 * s, 38 * s, 38 * s)
    p.fillRect(xb, QColor("#5a4a32"))
    T(p, "X", xb.center().x(), xb.center().y(), "bold", 24 * s, "#e8dcc0", "center", "middle")
    box = QRectF(body.left() - 40 * s, body.top() - 40 * s, w + 80 * s, h)
    if c.clip.props.get("fireworks", True) and c.t < 2.4:
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        for k, (fx, fy, col) in enumerate(((-0.42, -0.62, "#ffd84a"), (0.0, -0.75, "#ff5a5a"), (0.42, -0.62, "#6ad8ff"))):
            tt = c.t - k * 0.3
            if tt <= 0 or tt > 1.4:
                continue
            q = tt / 1.4
            fxp, fyp = cx + fx * w, cy + fy * h
            for i in range(24):
                a = i / 24 * 2 * math.pi
                d = 130 * s * ease_out(q)
                p.setBrush(_c(col, 1 - q))
                p.drawEllipse(QPointF(fxp + math.cos(a) * d, fyp + math.sin(a) * d + 40 * s * q * q), 5 * s, 5 * s)
        p.restore()
        box = box.united(QRectF(cx - w, cy - h, 2 * w, h))
    return box


RS_MSG_COLORS = {"red": "#c00000", "blue": "#0000ff", "green": "#007f00", "purple": "#800080", "orange": "#c06000",
                 "black": "#000000", "white": "#ffffff"}


def _rs_segments(line):
    parts = re.split(r"\[(red|blue|green|purple|orange|black|white)\]", line)
    col = "#000000"
    out = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            col = RS_MSG_COLORS[part]
        elif part:
            out.append((part, col))
    return out


def rs_gamemsg(p, c):
    s = c.s
    x0, yb = c.X(), c.Y()
    lines = lines_of(c, "lines")
    iv = float(c.val("interval", 1.2))
    shown = [ln for i, ln in enumerate(lines) if c.t >= i * iv][-int(c.val("max_lines", 5)):]
    if not shown:
        return QRectF()
    size, lh = 28 * s, 40 * s
    w = 980 * s
    h = 24 * s + len(shown) * lh
    r = QRectF(x0, yb - h, w, h)
    if c.clip.props.get("box", True):
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(QPen(QColor(43, 36, 27, 200), 3 * s))
        p.setBrush(QColor(214, 200, 165, 200))
        p.drawRect(r)
        p.restore()
    for i, ln in enumerate(shown):
        x = r.left() + 18 * s
        y = r.top() + 12 * s + i * lh + lh / 2
        for txt, col in _rs_segments(ln):
            rr = T(p, txt, x, y, "quill", size, col, "left", "middle")
            x += tw(txt, "quill", size)
    return r.adjusted(-6, -6, 6, 6)


# ================================================================== Stardew-inspired
def sv_levelup(p, c):
    s = c.s
    cx, cy = c.X(), c.Y()
    pw, ph = 880 * s, 400 * s
    top = cy - ph / 2 + 30 * s
    left = cx - pw / 2
    T(p, c.text("title", "Level Up"), cx, top - 18 * s, "quill", 70 * s, "#f39a3c", "center", "bottom", bold=True,
      italic=True, outline="#3f1d00", ow=7 * s, shadow="#3f1d00", sd=4 * s)
    hdr = QRectF(left, top, pw, 120 * s)
    sd_box(p, hdr, s)
    for ix in (hdr.left() + 22 * s, hdr.right() - 22 * s - 60 * s):
        ib = QRectF(ix, hdr.top() + 30 * s, 60 * s, 60 * s)
        sd_box(p, ib, s * 0.6, light=True)
        draw_icon(p, c.text("icon", "leaf"), ib.center().x(), ib.center().y(), 20 * s)
    T(p, f"Level {c.text('level', '10')} {c.text('skill', 'Pipetting')}", cx, hdr.top() + 44 * s, "round", 32 * s,
      SD_TEXT, "center", "middle")
    T(p, c.text("subtitle", "Choose a profession:"), cx, hdr.top() + 82 * s, "round", 20 * s, SD_TEXT, "center",
      "middle")
    sel = int(round(float(c.val("selected", -1))))
    for i in range(2):
        r = QRectF(left + i * pw / 2, hdr.bottom() - 4 * s, pw / 2, ph - 116 * s)
        sd_box(p, r, s, light=(sel == i))
        if sel == i:
            p.save()
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setPen(QPen(QColor(255, 255, 255, 200), 3 * s))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r.adjusted(12 * s, 12 * s, -12 * s, -12 * s))
            p.restore()
        name = c.text(f"option{i + 1}")
        T(p, name, r.left() + 30 * s, r.top() + 34 * s, "round", 28 * s, SD_TEXT)
        draw_icon(p, c.text(f"icon{i + 1}", ["flask", "microscope"][i]), r.right() - 50 * s, r.top() + 52 * s, 22 * s)
        for k, ln in enumerate(wrap(c.text(f"desc{i + 1}"), "round", 19 * s, r.width() - 60 * s)[:5]):
            T(p, ln, r.left() + 30 * s, r.top() + 110 * s + k * 28 * s, "round", 19 * s, "#5b3a1a")
    return QRectF(left - 10 * s, top - 110 * s, pw + 20 * s, ph + 120 * s)


def sv_item(p, c):
    s = c.s
    x0, yb = c.X(), c.Y()
    box = 78 * s
    ri = QRectF(x0, yb - box, box, box)
    sd_box(p, ri, s, light=True)
    draw_icon(p, c.text("icon", "coffee"), ri.center().x(), ri.center().y(), 24 * s)
    n = int(float(c.val("count", 1)))
    if n > 1:
        T(p, str(n), ri.right() - 10 * s, ri.bottom() - 8 * s, "pixel", 18 * s, "#ffffff", "right", "bottom",
          outline="#3f1d00")
    name = c.text("name", "Lukewarm Coffee")
    nw = tw(name, "round", 25 * s) + 44 * s
    rn = QRectF(ri.right() - 4 * s, yb - box + 12 * s, nw, box - 24 * s)
    sd_box(p, rn, s)
    T(p, name, rn.left() + 22 * s, rn.center().y(), "round", 25 * s, SD_TEXT, "left", "middle")
    return QRectF(x0 - 4, yb - box - 4, box + nw + 10 * s, box + 8)


def sv_note(p, c):
    s = c.s
    x0, yb = c.X(), c.Y()
    lines = wrap(c.text("text"), "round", 22 * s, 330 * s)[:4]
    h = 30 * s + len(lines) * 30 * s
    w = max(tw(ln, "round", 22 * s) for ln in lines) + 44 * s
    r = QRectF(x0, yb - h, w, h)
    sd_box(p, r, s)
    for i, ln in enumerate(lines):
        T(p, ln, r.left() + 22 * s, r.top() + 15 * s + i * 30 * s, "round", 22 * s, SD_TEXT)
    return r.adjusted(-4, -4, 4, 4)


def sv_clock(p, c):
    s = c.s
    right, top = c.X(), c.Y()
    w = 330 * s
    left = right - w
    try:
        hh, mm = [int(v) for v in c.text("start", "07:30").split(":")[:2]]
    except ValueError:
        hh, mm = 7, 30
    minutes = hh * 60 + mm + int(c.t * float(c.val("speed", 1.43)))
    minutes = (minutes // 10) * 10
    h24 = (minutes // 60) % 24
    ampm = "am" if h24 < 12 else "pm"
    h12 = h24 % 12 or 12
    dayfrac = ((minutes / 60) - 6) / 20
    # top panel with dial
    tp = QRectF(left + 70 * s, top, w - 70 * s, 104 * s)
    sd_box(p, tp, s)
    dial_c = QPointF(left + 70 * s, top + 62 * s)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(QPen(QColor(SD_OUT), 4 * s))
    p.setBrush(QColor(SD_MID))
    p.drawEllipse(dial_c, 62 * s, 62 * s)
    sky = QRadialGradient(dial_c, 54 * s)
    day = max(0.0, min(1.0, 1 - abs(dayfrac - 0.4) * 1.6))
    sky.setColorAt(0, QColor.fromHsvF(0.58, 0.6, 0.35 + 0.6 * day))
    sky.setColorAt(1, QColor.fromHsvF(0.6, 0.7, 0.25 + 0.5 * day))
    p.setBrush(QBrush(sky))
    p.setPen(QPen(QColor(SD_OUT), 2 * s))
    p.drawEllipse(dial_c, 52 * s, 52 * s)
    ang = math.pi + max(0.0, min(1.0, dayfrac)) * math.pi
    sx, sy = dial_c.x() + math.cos(ang) * 32 * s, dial_c.y() + math.sin(ang) * 32 * s
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#ffd23f") if day > 0.25 else QColor("#e8ecf5"))
    p.drawEllipse(QPointF(sx, sy), 12 * s, 12 * s)
    hand = QPen(QColor(SD_OUT), 4 * s)
    hand.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(hand)
    p.drawLine(dial_c, QPointF(dial_c.x() + math.cos(ang) * 48 * s, dial_c.y() + math.sin(ang) * 48 * s))
    p.restore()
    T(p, c.text("day", "Tue. 2"), tp.right() - 24 * s, tp.top() + 34 * s, "round", 26 * s, SD_TEXT, "right", "middle")
    for k, ic in enumerate(("leaf", "star")):
        b = QRectF(tp.left() + 66 * s + k * 52 * s, tp.top() + 60 * s, 40 * s, 32 * s)
        p.fillRect(b, QColor(SD_OUT))
        p.fillRect(b.adjusted(2 * s, 2 * s, -2 * s, -2 * s), QColor("#8fc8f0" if k == 0 else "#f9e0a0"))
        draw_icon(p, ic, b.center().x(), b.center().y(), 12 * s)
    tbox = QRectF(left + 70 * s, top + 98 * s, w - 70 * s, 54 * s)
    sd_box(p, tbox, s)
    T(p, f"{h12}:{minutes % 60:02d} {ampm}", tbox.center().x() + 10 * s, tbox.center().y(), "round", 27 * s, SD_TEXT,
      "center", "middle")
    gbox = QRectF(left + 70 * s, top + 148 * s, w - 70 * s, 52 * s)
    sd_box(p, gbox, s, fill="#f2b56b")
    gold = int(round(float(c.val("gold", 85773))))
    T(p, f"{gold}", gbox.right() - 22 * s, gbox.center().y(), "pixel", 24 * s, "#a8270f", "right", "middle")
    draw_icon(p, "coin", gbox.left() + 30 * s, gbox.center().y(), 15 * s)
    return QRectF(left - 4, top - 4, w + 8, 210 * s)


def sv_energy(p, c):
    s = c.s
    right, bottom = c.X(), c.Y()
    bw, bh = 52 * s, 300 * s
    r = QRectF(right - bw, bottom - bh, bw, bh)
    sd_box(p, r, s)
    T(p, c.text("label", "E"), r.center().x(), r.top() + 26 * s, "pixel", 24 * s, SD_TEXT, "center", "middle")
    ch = QRectF(r.left() + 14 * s, r.top() + 50 * s, bw - 28 * s, bh - 66 * s)
    p.fillRect(ch, QColor("#3a1a05"))
    frac = max(0.0, min(1.0, float(c.val("value", 80)) / max(1e-6, float(c.val("max_value", 100)))))
    col = QColor("#3ad13a") if frac > 0.5 else (QColor("#f0d020") if frac > 0.25 else QColor("#e02a1a"))
    fh = ch.height() * frac
    fr = QRectF(ch.left(), ch.bottom() - fh, ch.width(), fh)
    g = QLinearGradient(fr.left(), 0, fr.right(), 0)
    g.setColorAt(0, col.lighter(140))
    g.setColorAt(1, col.darker(130))
    p.fillRect(fr, QBrush(g))
    return r.adjusted(-4, -4, 4, 4)


_PORTRAIT_CACHE: dict = {}


def _portrait_image(c, px):
    """The speaker's picture as a QImage, optionally turned into chunky pixels."""
    from PySide6.QtGui import QImage
    if c.pool is None or not c.clip.media_id:
        return None
    arr = c.pool.image(c.clip.media_id)
    if arr is None:
        return None
    fx = float(c.clip.props.get("portrait_x", 0.5))
    fy = float(c.clip.props.get("portrait_y", 0.5))
    fs = float(c.clip.props.get("portrait_size", 1.0))
    key = (c.clip.media_id, int(px), round(fx, 3), round(fy, 3), round(fs, 3))
    img = _PORTRAIT_CACHE.get(key)
    if img is None:
        import numpy as np
        h, w = arr.shape[:2]
        rgba = np.ascontiguousarray(arr)
        img = QImage(rgba.data, w, h, w * 4, QImage.Format.Format_RGBA8888).copy()
        side = max(8, min(w, h, int(fs * h)))
        x0 = int(max(0, min(w - side, fx * w - side / 2)))
        y0 = int(max(0, min(h - side, fy * h - side / 2)))
        img = img.copy(x0, y0, side, side)
        if px > 0:
            small = img.scaled(int(px), int(px), Qt.AspectRatioMode.IgnoreAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
            img = small.scaled(512, 512, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
        if len(_PORTRAIT_CACHE) > 32:
            _PORTRAIT_CACHE.clear()
        _PORTRAIT_CACHE[key] = img
    return img


def sv_dialogue(p, c):
    s = c.s
    W = c.W
    cx, bottom = c.X(), c.Y()
    bw, bh = 1500 * s, 330 * s
    r = QRectF(cx - bw / 2, bottom - bh, bw, bh)
    pw = bh                                   # portrait panel is square-ish
    text_r = QRectF(r.left(), r.top(), bw - pw + 6 * s, bh)
    port_r = QRectF(r.right() - pw, r.top(), pw, bh)
    sd_box(p, text_r, s, fill="#fbd9a6")
    sd_box(p, port_r, s, fill="#e8b678")
    # portrait
    frame = QRectF(port_r.left() + 30 * s, port_r.top() + 22 * s, pw - 60 * s, pw - 112 * s)
    p.fillRect(frame.adjusted(-5 * s, -5 * s, 5 * s, 5 * s), QColor(SD_OUT))
    p.fillRect(frame, QColor("#a7d0e8"))
    img = _portrait_image(c, float(c.val("pixel_size", 64)) if c.clip.props.get("pixel_portrait", True) else 0)
    if img is not None:
        p.save()
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, not c.clip.props.get("pixel_portrait", True))
        p.drawImage(frame, img)
        p.restore()
    else:
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(90, 60, 40, 160))
        p.drawEllipse(QPointF(frame.center().x(), frame.top() + frame.height() * 0.4), frame.width() * 0.2,
                      frame.width() * 0.22)
        p.drawEllipse(QPointF(frame.center().x(), frame.bottom() + frame.height() * 0.1), frame.width() * 0.38,
                      frame.height() * 0.4)
        p.restore()
    plate = QRectF(port_r.left() + 26 * s, port_r.bottom() - 82 * s, pw - 52 * s, 56 * s)
    sd_box(p, plate, s * 0.7, fill="#f6c27a")
    T(p, c.text("speaker", "Lab Mate"), plate.center().x(), plate.center().y(), "round", 27 * s, SD_TEXT, "center",
      "middle", bold=True)
    # typed text
    text = c.text("text")
    cps = float(c.val("cps", 32))
    shown = len(text) if cps <= 0 else int(max(0.0, c.t - 0.2) * cps)
    size = 37 * s
    lines = wrap(text, "round", size, text_r.width() - 90 * s)[:4]
    rem = shown
    for i, ln in enumerate(lines):
        T(p, ln[:max(0, rem)], text_r.left() + 45 * s, text_r.top() + 40 * s + i * 60 * s, "round", size, SD_TEXT)
        rem -= len(ln) + 1
    if shown >= len(text) and int(c.t * 2.5) % 2 == 0:
        ax, ay = text_r.right() - 52 * s, text_r.bottom() - 46 * s
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(QPen(QColor(SD_OUT), 2 * s))
        p.setBrush(QColor("#e8762a"))
        p.drawPolygon(QPolygonF([QPointF(ax - 14 * s, ay - 9 * s), QPointF(ax + 14 * s, ay - 9 * s),
                                 QPointF(ax, ay + 11 * s)]))
        p.restore()
    return r.adjusted(-6, -6, 6, 6)


# ================================================================== Skyrim-inspired
def sk_skillup(p, c):
    s = c.s
    cx, cy = c.X(), c.Y()
    txt = f"{c.text('skill', 'Pipetting').upper()} INCREASED TO {c.text('level', '47')}"
    r = T(p, txt, cx, cy, "futura", 44 * s, "#f2f2f2", "center", "middle", spacing=118, soft=6 * s)
    by = cy + 72 * s
    T(p, c.text("label", "Level Progress"), cx - 190 * s, by, "futura", 17 * s, "#d0d0d0", "right", "middle",
      soft=3 * s)
    p0, p1 = float(c.val("progress_from", 40)) / 100, float(c.val("progress_to", 70)) / 100
    k = ease_out(max(0.0, min(1.0, (c.t - 0.5) / 1.2)))
    sk_bar(p, cx + 20 * s, by, 300 * s, 20 * s, s, p0 + (p1 - p0) * k, "#c9d6e8", "left")
    T(p, c.text("char_level", "35"), cx + 230 * s, by, "futura", 22 * s, "#e8e8e8", "left", "middle", soft=3 * s)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(QPen(SK_LINE, 1.3 * s))
    p.setBrush(Qt.BrushStyle.NoBrush)
    mx, my, d = cx - 150 * s + 300 * s * (p0 + (p1 - p0) * k), by + 26 * s, 7 * s
    p.drawPolygon(QPolygonF([QPointF(mx, my - d), QPointF(mx + d * 0.7, my), QPointF(mx, my + d * 1.6),
                             QPointF(mx - d * 0.7, my)]))
    p.restore()
    return r.united(QRectF(cx - 420 * s, by - 30 * s, 840 * s, 80 * s))


def sk_bars(p, c):
    s = c.s
    W = c.W
    y = c.Y()
    mx = max(1e-6, float(c.val("max_value", 100)))
    hide = bool(c.clip.props.get("hide_full", False))
    hv = c.bar_value()
    ghost = c.bar_value(max(0.0, c.t - 0.6)) / mx
    items = [(W * 0.5, hv / mx, "#b3201b", "center", ghost),
             (W * 0.18, float(c.val("magicka", 100)) / mx, "#2f5bb8", "right", None),
             (W * 0.82, float(c.val("stamina", 100)) / mx, "#2f9e4a", "left", None)]
    for x, frac, col, anchor, gh in items:
        if hide and frac >= 0.999:
            continue
        sk_bar(p, x, y, 290 * s, 17 * s, s, frac, col, anchor, gh)
    return QRectF(0, y - 30 * s, W, 60 * s)


def sk_compass(p, c):
    s = c.s
    cx, y = c.X(), c.Y()
    w, h = 760 * s, 30 * s
    x0, x1 = cx - w / 2, cx + w / 2
    tip = h * 0.8
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    outer = QPolygonF([QPointF(x0 - tip, y), QPointF(x0, y - h / 2), QPointF(x1, y - h / 2), QPointF(x1 + tip, y),
                       QPointF(x1, y + h / 2), QPointF(x0, y + h / 2)])
    p.setPen(QPen(SK_LINE, 1.4 * s))
    p.setBrush(QColor(0, 0, 0, 120))
    p.drawPolygon(outer)
    inner = QPolygonF([QPointF(x0 - tip + 8 * s, y), QPointF(x0 + 4 * s, y - h / 2 + 4 * s),
                       QPointF(x1 - 4 * s, y - h / 2 + 4 * s), QPointF(x1 + tip - 8 * s, y),
                       QPointF(x1 - 4 * s, y + h / 2 - 4 * s), QPointF(x0 + 4 * s, y + h / 2 - 4 * s)])
    p.setPen(QPen(QColor(210, 210, 210, 110), 1 * s))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPolygon(inner)
    p.restore()
    heading = float(c.val("heading", 0))
    span = 100.0
    for deg, lab in ((0, "N"), (90, "E"), (180, "S"), (270, "W")):
        rel = ((deg - heading + 180) % 360) - 180
        if abs(rel) <= span:
            a = 1 - (abs(rel) / span) ** 2
            T(p, lab, cx + rel / span * (w / 2 - 24 * s), y, "futura", 22 * s, "#ffffff", "center", "middle", alpha=a,
              soft=2 * s)
    for tok in c.text("markers", "35, -60").replace(";", ",").split(","):
        try:
            deg = float(tok)
        except ValueError:
            continue
        rel = ((deg - heading + 180) % 360) - 180
        if abs(rel) <= span:
            mx_ = cx + rel / span * (w / 2 - 24 * s)
            p.save()
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setPen(QPen(QColor(255, 255, 255, 230), 1.5 * s))
            p.setBrush(QColor(0, 0, 0, 120))
            p.drawPolygon(QPolygonF([QPointF(mx_ - 7 * s, y - 9 * s), QPointF(mx_ + 7 * s, y - 9 * s),
                                     QPointF(mx_, y + 8 * s)]))
            p.restore()
    box = QRectF(x0 - 60 * s, y - h, w + 120 * s, 2 * h)
    enemy = c.text("enemy", "Reviewer 2")
    if enemy and c.clip.props.get("show_enemy", True):
        mx = max(1e-6, float(c.val("max_value", 100)))
        v = c.bar_value()
        by = y + h / 2 + 20 * s
        sk_bar(p, cx, by, 330 * s, 13 * s, s, v / mx, "#b3201b", "center", c.bar_value(max(0.0, c.t - 0.6)) / mx)
        ny = by + 30 * s
        nw = tw(enemy, "futura", 20 * s) + 60 * s
        sk_bar(p, cx, ny, nw, 26 * s, s, 0, "#000000", "center")
        T(p, enemy, cx, ny, "futura", 20 * s, "#e8e8e8", "center", "middle")
        box = box.united(QRectF(cx - 260 * s, by - 20 * s, 520 * s, 80 * s))
    return box


def sk_note(p, c):
    s = c.s
    x, y = c.X(), c.Y()
    iv, hold = float(c.val("interval", 1.0)), float(c.val("hold", 4.0))
    r = QRectF(x, y, 1, 1)
    row = 0
    for i, ln in enumerate(lines_of(c, "lines")):
        t0 = i * iv
        if not (t0 <= c.t < t0 + hold):
            continue
        age = c.t - t0
        a = min(1.0, age / 0.3) * (1.0 if age < hold - 0.6 else max(0.0, (hold - age) / 0.6))
        r = r.united(T(p, ln, x, y + row * 40 * s, "futura", 25 * s, "#ffffff", soft=4 * s, alpha=a))
        row += 1
    return r


def sk_subtitle(p, c):
    s = c.s
    cx, y = c.X(), c.Y()
    speaker, text = c.text("speaker", "Supervisor"), c.text("text")
    full = f"{speaker}: {text}" if speaker else text
    size = 30 * s
    lines = wrap(full, "futura", size, 1200 * s)[:3]
    r = QRectF(cx, y, 1, 1)
    for i, ln in enumerate(lines):
        yy = y + i * 42 * s
        if i == 0 and speaker and ln.startswith(speaker + ":"):
            head = speaker + ": "
            rest = ln[len(head):]
            wtot = tw(ln, "futura", size)
            x0 = cx - wtot / 2
            r = r.united(T(p, head, x0, yy, "futura", size, "#b9b9b9", soft=4 * s))
            r = r.united(T(p, rest, x0 + tw(head, "futura", size), yy, "futura", size, "#ffffff", soft=4 * s))
        else:
            r = r.united(T(p, ln, cx, yy, "futura", size, "#ffffff", "center", soft=4 * s))
    return r


def _constellation(seed, cx, cy, s, n=11):
    rr = random.Random(seed)
    pts = [(cx + rr.uniform(-170, 170) * s, cy + rr.uniform(-180, 150) * s) for _ in range(n)]
    edges = []
    for i in range(1, n):
        j = min(range(i), key=lambda k: (pts[k][0] - pts[i][0]) ** 2 + (pts[k][1] - pts[i][1]) ** 2)
        edges.append((i, j))
    return pts, edges


def sk_skills(p, c):
    W, H = c.W, c.H
    s = c.base_s
    full = QRectF(0, 0, W, H)
    op = float(c.val("bg_opacity", 0.9))
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.fillRect(full, QColor(4, 10, 22, int(255 * op)))
    rnd = random.Random(11)
    p.setPen(Qt.PenStyle.NoPen)
    for _ in range(10):
        x, y, rad = rnd.random() * W, rnd.random() * H * 0.8, rnd.uniform(250, 620) * s
        col = rnd.choice([(40, 140, 160), (90, 60, 150), (30, 80, 160), (150, 70, 120)])
        g = QRadialGradient(x, y, rad)
        g.setColorAt(0, QColor(*col, int(90 * op)))
        g.setColorAt(1, QColor(*col, 0))
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(x, y), rad, rad)
    for i in range(180):
        x, y = rnd.random() * W, rnd.random() * H
        tw_ = 0.5 + 0.5 * math.sin(c.t * 2 + i)
        p.setBrush(QColor(255, 255, 255, int(160 * tw_ * op)))
        p.drawEllipse(QPointF(x, y), rnd.uniform(0.6, 1.8) * s, rnd.uniform(0.6, 1.8) * s)
    for k, cxn in enumerate((0.22, 0.5, 0.78)):
        pts, edges = _constellation(100 + k * 7 + int(c.val("pattern", 0)), cxn * W, H * 0.37, s)
        a = max(0.0, min(1.0, (c.t - 0.2 - k * 0.15) / 0.8))
        bright = 1.0 if k == 1 else 0.55
        p.setPen(QPen(QColor(200, 235, 255, int(200 * a * bright)), 2 * s))
        for i, j in edges:
            p.drawLine(QPointF(*pts[i]), QPointF(*pts[j]))
        p.setPen(Qt.PenStyle.NoPen)
        for (x, y) in pts:
            rad = (14 if k == 1 else 9) * s
            g = QRadialGradient(x, y, rad)
            g.setColorAt(0, QColor(255, 255, 255, int(255 * a)))
            g.setColorAt(0.3, QColor(255, 230, 170, int(200 * a * bright)))
            g.setColorAt(1, QColor(255, 230, 170, 0))
            p.setBrush(QBrush(g))
            p.drawEllipse(QPointF(x, y), rad, rad)
    p.restore()
    # top bar
    ty = 46 * s
    gradient_line(p, W * 0.04, W * 0.96, ty + 22 * s, QColor(220, 220, 220), 1.5 * s, 0.8)
    T(p, c.text("left_label", "NAME"), W * 0.08, ty, "futura", 15 * s, "#b0b0b0", "left", "middle", soft=2 * s)
    T(p, c.text("left_value", "PhD Student"), W * 0.08 + 70 * s, ty, "futura", 22 * s, "#ffffff", "left", "middle",
      soft=2 * s)
    T(p, "LEVEL " + c.text("level", "27"), W * 0.42, ty, "futura", 20 * s, "#ffffff", "right", "middle", soft=2 * s)
    sk_bar(p, W * 0.52, ty, 220 * s, 14 * s, s, float(c.val("level_progress", 60)) / 100, "#c9d6e8", "left")
    T(p, c.text("right_label", "RACE"), W * 0.74, ty, "futura", 15 * s, "#b0b0b0", "left", "middle", soft=2 * s)
    T(p, c.text("right_value", "Caffeinated"), W * 0.74 + 60 * s, ty, "futura", 22 * s, "#ffffff", "left", "middle",
      soft=2 * s)
    perks = c.text("perks", "Perks to increase: 3")
    if perks:
        pw = tw(perks, "futura", 22 * s) + 70 * s
        sk_bar(p, W / 2, ty + 56 * s, pw, 36 * s, s, 0, "#000000")
        T(p, perks, W / 2, ty + 56 * s, "futura", 22 * s, "#ffffff", "center", "middle")
    # skill band
    band = H * 0.75
    gradient_line(p, W * 0.02, W * 0.98, band - 44 * s, QColor(220, 220, 220), 1.2 * s, 0.6)
    gradient_line(p, W * 0.02, W * 0.98, band + 40 * s, QColor(220, 220, 220), 1.2 * s, 0.6)
    skills = lines_of(c, "skills")
    sel = float(c.val("selected", 2))
    for i, ln in enumerate(skills):
        parts = ln.rsplit(" ", 1)
        name, num = (parts[0], parts[1]) if len(parts) == 2 and parts[1].isdigit() else (ln, "")
        d = i - sel
        if abs(d) > 3.2:
            continue
        x = W / 2 + d * 330 * s
        near = max(0.0, 1 - abs(d))
        size = (24 + 22 * near) * s
        a = max(0.0, 1 - abs(d) / 3.4)
        nm = name.upper()
        wn = tw(nm, "futura", size, spacing=105)
        wnum = tw(num, "futura", size * 1.15, bold=True)
        x0 = x - (wn + 10 * s + wnum) / 2
        T(p, nm, x0, band, "futura", size, "#ffffff", "left", "middle", spacing=105, soft=3 * s, alpha=a)
        T(p, num, x0 + wn + 10 * s, band, "futura", size * 1.15, "#ffffff", "left", "middle", bold=True, soft=3 * s,
          alpha=a)
    for i, ln in enumerate(wrap(c.text("description"), "futura", 21 * s, 1250 * s)[:3]):
        T(p, ln, W / 2, band + 72 * s + i * 30 * s, "futura", 21 * s, "#dcdcdc", "center", "middle", soft=3 * s)
    if c.clip.props.get("bottom_bars", True):
        by = H - 44 * s
        for x, lab, col, anchor in ((W * 0.2, "MAGICKA", "#2f5bb8", "right"), (W * 0.5, "HEALTH", "#b3201b", "center"),
                                    (W * 0.8, "STAMINA", "#2f9e4a", "left")):
            T(p, lab, x - 160 * s, by, "futura", 15 * s, "#cfcfcf", "right", "middle", soft=2 * s)
            sk_bar(p, x + 10 * s, by, 220 * s, 14 * s, s, 1.0, col, anchor)
    return full


def sk_inventory(p, c):
    W, H = c.W, c.H
    s = c.base_s
    full = QRectF(0, 0, W, H)
    g = QLinearGradient(0, 0, W * 0.62, 0)
    g.setColorAt(0, QColor(0, 0, 0, 225))
    g.setColorAt(0.55, QColor(0, 0, 0, 190))
    g.setColorAt(1, QColor(0, 0, 0, 0))
    p.fillRect(full, QBrush(g))
    l1, l2 = W * 0.165, W * 0.375
    for lx in (l1, l2):
        p.fillRect(QRectF(lx, 0, 1.5 * s, H), QColor(255, 255, 255, 70))
    cats = lines_of(c, "categories")
    sc = int(round(float(c.val("selected_category", 1))))
    cy0 = H * 0.5
    for i, cat in enumerate(cats):
        on = i == sc
        T(p, cat.upper(), W * 0.025, cy0 + (i - 1) * 56 * s, "futura", (34 if on else 24) * s,
          "#ffffff" if on else "#9a9a9a", "left", "middle", bold=on, spacing=104)
    items = lines_of(c, "items")
    si = float(c.val("selected_item", 4))
    for i, it in enumerate(items):
        d = i - si
        yy = H * 0.59 + d * 52 * s
        if yy < 30 * s or yy > H - 20 * s:
            continue
        on = abs(d) < 0.5
        a = max(0.25, 1 - abs(d) * 0.08)
        T(p, it, l1 + 50 * s, yy, "futura", (28 if on else 24) * s, "#ffffff" if on else "#a0a0a0", "left", "middle",
          bold=on, alpha=a)
    knot_ys = []
    if 0 <= sc < len(cats):
        knot_ys.append((l1, cy0 + (sc - 1) * 56 * s))
    knot_ys.append((l2, H * 0.59))
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    for kx, ky in knot_ys:
        p.setPen(QPen(QColor(235, 235, 235), 2 * s))
        p.setBrush(QColor(0, 0, 0, 200))
        p.drawEllipse(QPointF(kx - 6 * s, ky), 13 * s, 13 * s)
        p.drawEllipse(QPointF(kx + 6 * s, ky), 13 * s, 13 * s)
        d = 9 * s
        p.drawPolygon(QPolygonF([QPointF(kx + 20 * s, ky - d), QPointF(kx + 20 * s + d, ky),
                                 QPointF(kx + 20 * s, ky + d), QPointF(kx + 20 * s - d, ky)]))
    p.restore()
    # item card
    title = c.text("card_title") or (items[int(round(si))] if 0 <= int(round(si)) < len(items) else "")
    title = title.split(" (")[0].upper()
    r = QRectF(W * 0.51, H * 0.63, W * 0.34, H * 0.16)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(QPen(QColor(230, 230, 230, 200), 1.5 * s))
    p.setBrush(QColor(0, 0, 0, 165))
    p.drawRect(r)
    L = 22 * s
    for (cx_, cy_, sx, sy) in ((r.left(), r.top(), 1, 1), (r.right(), r.top(), -1, 1), (r.left(), r.bottom(), 1, -1),
                               (r.right(), r.bottom(), -1, -1)):
        p.drawLine(QPointF(cx_ + 6 * s * sx, cy_ + 6 * s * sy), QPointF(cx_ + L * sx, cy_ + 6 * s * sy))
        p.drawLine(QPointF(cx_ + 6 * s * sx, cy_ + 6 * s * sy), QPointF(cx_ + 6 * s * sx, cy_ + L * sy))
    p.restore()
    T(p, title, r.center().x(), r.top() + 32 * s, "futura", 30 * s, "#ffffff", "center", "middle", spacing=106)
    gradient_line(p, r.left() + 30 * s, r.right() - 30 * s, r.top() + 60 * s, QColor(220, 220, 220), 1.2 * s, 0.8)
    stats = [x.strip() for x in c.text("stats").split("|") if x.strip()]
    for i, st in enumerate(stats):
        parts = st.rsplit(" ", 1)
        lab, val = (parts[0], parts[1]) if len(parts) == 2 else (st, "")
        sx = r.left() + r.width() * (i + 0.5) / max(1, len(stats))
        wl = tw(lab.upper(), "futura", 16 * s)
        wv = tw(val, "futura", 28 * s)
        x0 = sx - (wl + 10 * s + wv) / 2
        T(p, lab.upper(), x0, r.top() + 100 * s, "futura", 16 * s, "#bdbdbd", "left", "middle")
        T(p, val, x0 + wl + 10 * s, r.top() + 98 * s, "futura", 28 * s, "#ffffff", "left", "middle")
    return full


def sk_menu(p, c):
    s = c.s
    cx, cy = c.X(), c.Y()
    hl = c.text("highlight", "top")
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    rg = QRadialGradient(cx, cy, 520 * s)
    rg.setColorAt(0, QColor(0, 0, 0, 120))
    rg.setColorAt(1, QColor(0, 0, 0, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(rg))
    p.drawEllipse(QPointF(cx, cy), 520 * s, 520 * s)

    def spike(dx, dy, length, width):
        tip = QPointF(cx + dx * length, cy + dy * length)
        nx, ny = -dy, dx
        base1 = QPointF(cx + nx * width, cy + ny * width)
        base2 = QPointF(cx - nx * width, cy - ny * width)
        mid = QPointF(cx + dx * length * 0.18, cy + dy * length * 0.18)
        g = QLinearGradient(base1, base2)
        g.setColorAt(0, QColor("#f2f2f2"))
        g.setColorAt(0.5, QColor("#9aa0a8"))
        g.setColorAt(1, QColor("#5a5f66"))
        p.setPen(QPen(QColor(20, 20, 20, 200), 1.2 * s))
        p.setBrush(QBrush(g))
        p.drawPolygon(QPolygonF([base1, mid, tip, mid, base2, tip]))
        p.drawPolygon(QPolygonF([base1, tip, base2]))

    spike(0, -1, 210 * s, 13 * s)
    spike(0, 1, 160 * s, 11 * s)
    spike(-1, 0, 300 * s, 6 * s)
    spike(1, 0, 300 * s, 6 * s)
    p.setPen(QPen(QColor("#d8dce0"), 3 * s))
    p.setBrush(QColor(20, 24, 30, 230))
    p.drawEllipse(QPointF(cx, cy), 30 * s, 30 * s)
    p.setPen(QPen(QColor("#d8dce0"), 2 * s))
    p.setBrush(Qt.BrushStyle.NoBrush)
    for ang in (0, 60, 120):
        p.save()
        p.translate(cx, cy)
        p.rotate(ang)
        p.drawEllipse(QPointF(0, 0), 22 * s, 9 * s)
        p.restore()
    p.restore()
    words = {"top": (c.text("top", "SKILLS"), cx, cy - 250 * s, "center"),
             "left": (c.text("left", "MAGIC"), cx - 330 * s, cy, "right"),
             "right": (c.text("right", "ITEMS"), cx + 330 * s, cy, "left"),
             "bottom": (c.text("bottom", "MAP"), cx, cy + 205 * s, "center")}
    for key, (wd, x, y, al) in words.items():
        on = key == hl
        T(p, wd.upper(), x, y, "futura", (36 if on else 30) * s, "#ffffff" if on else "#aeb4ba", al, "middle",
          spacing=135, soft=4 * s, bold=on)
    return QRectF(cx - 560 * s, cy - 330 * s, 1120 * s, 620 * s)


# ================================================================== Elden Ring-inspired
ER_TEXT = "#e9e2cf"


def er_grace(p, c):
    W, H = c.W, c.H
    s = c.base_s
    full = QRectF(0, 0, W, H)
    g = QLinearGradient(0, 0, W * 0.5, 0)
    g.setColorAt(0, QColor(10, 10, 8, 215))
    g.setColorAt(0.7, QColor(10, 10, 8, 170))
    g.setColorAt(1, QColor(10, 10, 8, 0))
    p.fillRect(full, QBrush(g))
    x0, y0 = W * 0.035, H * 0.06
    ib = QRectF(x0, y0, 64 * s, 64 * s)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(QPen(QColor(168, 148, 106), 1.5 * s))
    p.setBrush(QColor(20, 18, 14, 230))
    p.drawRect(ib)
    p.restore()
    draw_icon(p, "flame", ib.center().x(), ib.center().y(), 22 * s)
    T(p, c.text("location", "Faculty Coffee Corner"), ib.right() + 20 * s, ib.center().y(), "garamond", 40 * s, ER_TEXT,
      "left", "middle")
    gradient_line(p, x0, W * 0.42, ib.bottom() + 16 * s, QColor(190, 170, 120), 1.4 * s, 0.9)
    sub = c.text("sublabel", "Early Day")
    if sub:
        sb = QRectF(x0 + 10 * s, ib.bottom() + 40 * s, W * 0.34, 54 * s)
        p.fillRect(sb, QColor(255, 255, 255, 18))
        p.fillRect(QRectF(sb.left(), sb.bottom(), sb.width(), 1.2 * s), QColor(190, 170, 120, 120))
        T(p, sub, sb.left() + 22 * s, sb.center().y(), "garamond", 27 * s, "#d6cfbd", "left", "middle")
    items = lines_of(c, "items")
    sel = float(c.val("selected", 1))
    ystart = ib.bottom() + 130 * s
    step = 64 * s
    band_y = ystart + sel * step
    bg = QLinearGradient(x0, 0, W * 0.42, 0)
    bg.setColorAt(0, QColor(255, 250, 230, 85))
    bg.setColorAt(1, QColor(255, 250, 230, 0))
    p.fillRect(QRectF(x0, band_y - step / 2 + 4 * s, W * 0.39, step - 8 * s), QBrush(bg))
    for i, it in enumerate(items):
        yy = ystart + i * step
        on = abs(i - sel) < 0.5
        T(p, it, x0 + 28 * s, yy, "garamond", 30 * s, "#ffffff" if on else "#cfc8b4", "left", "middle")
        p.fillRect(QRectF(x0 + 10 * s, yy + step / 2 - 1, W * 0.36, 1 * s), QColor(200, 190, 160, 45))
    hx = x0 + 10 * s
    hy = H - 54 * s
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    for tok in c.text("hints", "A:OK B:Close X:Map").split():
        btn, _, lab = tok.partition(":")
        p.setPen(QPen(QColor("#d6cfbd"), 1.6 * s))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(hx + 13 * s, hy), 13 * s, 13 * s)
        T(p, btn[:1], hx + 13 * s, hy, "round", 15 * s, "#d6cfbd", "center", "middle", bold=True)
        r = T(p, ":" + lab, hx + 28 * s, hy, "garamond", 22 * s, "#d6cfbd", "left", "middle")
        hx = r.right() + 22 * s
    p.restore()
    return full


BANNER_COLORS = {"gold": "#dcbb5a", "red": "#a8201a", "white": "#f0ead6", "blue": "#7aa8e0"}


def er_banner(p, c):
    W = c.W
    s = c.base_s
    cy = c.Y()
    band = 270 * s
    g = QLinearGradient(0, cy - band / 2, 0, cy + band / 2)
    g.setColorAt(0, QColor(0, 0, 0, 0))
    g.setColorAt(0.3, QColor(0, 0, 0, 185))
    g.setColorAt(0.7, QColor(0, 0, 0, 185))
    g.setColorAt(1, QColor(0, 0, 0, 0))
    p.fillRect(QRectF(0, cy - band / 2, W, band), QBrush(g))
    col = BANNER_COLORS.get(c.text("color", "gold"), "#dcbb5a")
    sc = 1 + 0.07 * min(1.0, c.t / max(0.1, c.dur))
    T(p, c.text("text", "THESIS DEFENDED"), W / 2, cy, "garamond", 128 * s * sc * float(c.val("scale", 1.0)), col,
      "center", "middle", spacing=110, glow=_c(col, 0.35), gr=8 * s)
    return QRectF(0, cy - band / 2, W, band)


def er_boss(p, c):
    s = c.s
    cx, y = c.X(), c.Y()
    w, h = 1150 * s, 13 * s
    x0 = cx - w / 2
    T(p, c.text("name", "Reviewer 2, the Unrelenting"), x0, y - 10 * s, "garamond", 30 * s, "#f0ead6", "left", "bottom",
      soft=3 * s)
    mx = max(1e-6, float(c.val("max_value", 100)))
    v = c.bar_value()
    ghost = c.bar_value(max(0.0, c.t - 0.8))
    frame = QRectF(x0, y, w, h)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(QPen(QColor(125, 107, 74), 1.3 * s))
    p.setBrush(QColor(18, 13, 10, 235))
    p.drawRect(frame)
    inner = frame.adjusted(2 * s, 2 * s, -2 * s, -2 * s)
    if ghost > v:
        p.fillRect(QRectF(inner.left(), inner.top(), inner.width() * ghost / mx, inner.height()), QColor("#d8b04a"))
    rg = QLinearGradient(0, inner.top(), 0, inner.bottom())
    rg.setColorAt(0, QColor("#c8291c"))
    rg.setColorAt(1, QColor("#6e0d08"))
    p.fillRect(QRectF(inner.left(), inner.top(), inner.width() * max(0.0, v) / mx, inner.height()), QBrush(rg))
    p.restore()
    drop = _drop_number(c)
    if drop > 0.5:
        T(p, str(int(round(drop))), x0 + w, y - 10 * s, "garamond", 28 * s, "#ffffff", "right", "bottom", soft=3 * s)
    return QRectF(x0 - 10 * s, y - 60 * s, w + 20 * s, 80 * s)


def er_compass(p, c):
    s = c.s
    cx, y = c.X(), c.Y()
    w = 660 * s
    x0, x1 = cx - w / 2, cx + w / 2
    gradient_line(p, x0, x1, y, QColor(235, 228, 205), 1.6 * s, 0.9)
    heading = float(c.val("heading", 0))
    span = 90.0
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    for deg in range(0, 360, 15):
        rel = ((deg - heading + 180) % 360) - 180
        if abs(rel) > span:
            continue
        a = 1 - (abs(rel) / span) ** 2
        x = cx + rel / span * w / 2
        tick = 9 * s if deg % 45 == 0 else 5 * s
        p.setPen(QPen(QColor(235, 228, 205, int(220 * a)), 1.3 * s))
        p.drawLine(QPointF(x, y - tick), QPointF(x, y))
    p.restore()
    for deg, lab in ((0, "N"), (90, "E"), (180, "S"), (270, "W")):
        rel = ((deg - heading + 180) % 360) - 180
        if abs(rel) <= span:
            a = 1 - (abs(rel) / span) ** 2
            T(p, lab, cx + rel / span * w / 2, y - 14 * s, "garamond", 22 * s, "#ede6d2", "center", "bottom", alpha=a,
              soft=2 * s)
    for tok in c.text("markers", "15").replace(";", ",").split(","):
        try:
            deg = float(tok)
        except ValueError:
            continue
        rel = ((deg - heading + 180) % 360) - 180
        if abs(rel) <= span:
            x = cx + rel / span * w / 2
            d = 7 * s
            p.save()
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setPen(QPen(QColor(30, 30, 30), 1 * s))
            p.setBrush(QColor("#f2ecd8"))
            p.drawPolygon(QPolygonF([QPointF(x, y - d), QPointF(x + d, y), QPointF(x, y + d), QPointF(x - d, y)]))
            p.restore()
    return QRectF(x0 - 10, y - 50 * s, w + 20, 70 * s)


def er_loot(p, c):
    s = c.s
    right, cy = c.X(), c.Y()
    w, h = 600 * s, 78 * s
    r = QRectF(right - w, cy - h / 2, w, h)
    g = QLinearGradient(r.left(), 0, r.right(), 0)
    g.setColorAt(0, QColor(8, 8, 6, 0))
    g.setColorAt(0.25, QColor(8, 8, 6, 210))
    g.setColorAt(1, QColor(8, 8, 6, 210))
    p.fillRect(r, QBrush(g))
    gradient_line(p, r.left(), r.right(), r.top(), QColor(190, 170, 120), 1.2 * s, 0.8)
    gradient_line(p, r.left(), r.right(), r.bottom(), QColor(190, 170, 120), 1.2 * s, 0.8)
    ib = QRectF(r.left() + 110 * s, cy - 28 * s, 56 * s, 56 * s)
    p.fillRect(ib, QColor(30, 26, 20, 230))
    draw_icon(p, c.text("icon", "pipette"), ib.center().x(), ib.center().y(), 20 * s)
    T(p, c.text("name", "Golden Pipette"), ib.right() + 20 * s, cy, "garamond", 28 * s, ER_TEXT, "left", "middle")
    T(p, str(int(float(c.val("count", 1)))), r.right() - 30 * s, cy, "garamond", 28 * s, ER_TEXT, "right", "middle")
    return r.adjusted(-4, -4, 4, 4)


# ================================================================== other classics
def _heart_path(cx, cy, r):
    path = QPainterPath()
    path.moveTo(cx, cy + r * 0.85)
    path.cubicTo(cx - r * 1.35, cy - r * 0.05, cx - r * 0.65, cy - r * 1.15, cx, cy - r * 0.42)
    path.cubicTo(cx + r * 0.65, cy - r * 1.15, cx + r * 1.35, cy - r * 0.05, cx, cy + r * 0.85)
    return path


def zl_hearts(p, c):
    s = c.s
    x0, y0 = c.X(), c.Y()
    maxh = max(1, int(round(float(c.val("max_hearts", 10)))))
    v = c.bar_value()
    r = 20 * s
    step = 2.3 * r
    low = v <= 1.0 and int(c.t * 3) % 2 == 0
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    for i in range(maxh):
        cx = x0 + r + (i % 10) * step
        cy = y0 + r + (i // 10) * step
        hp = _heart_path(cx, cy, r)
        p.setPen(QPen(QColor(25, 10, 10), 3 * s))
        p.setBrush(QColor(70, 20, 20, 200))
        p.drawPath(hp)
        f = max(0.0, min(1.0, v - i))
        q = math.floor(f * 4 + 1e-6) / 4
        if q > 0:
            pie = QPainterPath()
            pie.moveTo(cx, cy)
            pie.arcTo(QRectF(cx - 2 * r, cy - 2 * r, 4 * r, 4 * r), 90, -360 * q)
            pie.closeSubpath()
            g = QLinearGradient(0, cy - r, 0, cy + r)
            g.setColorAt(0, QColor("#ff6a6a") if not low else QColor("#ffffff"))
            g.setColorAt(1, QColor("#c40d0d"))
            p.save()
            if q < 1:
                p.setClipPath(pie)
            p.fillPath(hp, QBrush(g))
            p.restore()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 150))
            p.drawEllipse(QPointF(cx - r * 0.4, cy - r * 0.35), r * 0.16, r * 0.12)
    p.restore()
    rows = (maxh - 1) // 10 + 1
    return QRectF(x0 - 6, y0 - 6, min(maxh, 10) * step + 12, rows * step + 12)


STATUS_COLORS = {"PSN": "#a040a0", "PAR": "#c8a000", "SLP": "#8c8c8c", "BRN": "#e05030", "FRZ": "#58b0e0",
                 "TIRED": "#7a7aa0"}


def pk_hpbox(p, c):
    s = c.s
    cx, cy = c.X(), c.Y()
    player = c.text("side", "enemy") == "player"
    w, h = 500 * s, (182 if player else 132) * s
    r = QRectF(cx - w / 2, cy - h / 2, w, h)
    mx = max(1e-6, float(c.val("max_value", 100)))
    v = c.bar_value()
    frac = max(0.0, min(1.0, v / mx))
    box = QPainterPath()
    box.addRoundedRect(r, 16 * s, 16 * s)
    tail = QPainterPath()
    if player:
        tail.addPolygon(QPolygonF([QPointF(r.left() + 30 * s, r.bottom() - 40 * s), QPointF(r.left() - 34 * s, r.bottom()),
                                   QPointF(r.left() + 60 * s, r.bottom())]))
    else:
        tail.addPolygon(QPolygonF([QPointF(r.right() - 30 * s, r.bottom() - 40 * s), QPointF(r.right() + 34 * s, r.bottom()),
                                   QPointF(r.right() - 60 * s, r.bottom())]))
    # fill the two shapes separately (a merged path can come out "hollow"); only the
    # border uses the merged outline
    outline = box.united(tail)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    for part in (box, tail):
        p.fillPath(part.translated(7 * s, 7 * s), QColor(0, 0, 0, 90))
    pen = QPen(QColor("#404040"), 5 * s)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.strokePath(outline, pen)
    for part in (box, tail):
        p.fillPath(part, QColor("#f8f8d8"))
    p.restore()
    nr = T(p, c.text("name", "REVIEWER 2").upper(), r.left() + 26 * s, r.top() + 18 * s, "round", 32 * s, "#383838",
           bold=True, shadow="#d0d0b8", sd=2 * s)
    st = c.text("status", "none")
    if st in STATUS_COLORS:
        pill = QRectF(nr.right() + 10 * s, r.top() + 22 * s, 66 * s, 30 * s)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(STATUS_COLORS[st]))
        p.drawRoundedRect(pill, 8 * s, 8 * s)
        p.restore()
        T(p, st, pill.center().x(), pill.center().y(), "round", 18 * s, "#ffffff", "center", "middle", bold=True)
    T(p, "Lv" + c.text("level", "50"), r.right() - 26 * s, r.top() + 18 * s, "round", 30 * s, "#383838", "right",
      bold=True, shadow="#d0d0b8", sd=2 * s)
    yb = r.top() + 84 * s
    tag = QRectF(r.left() + 90 * s, yb - 12 * s, 54 * s, 24 * s)
    bar = QRectF(tag.right() - 2 * s, yb - 9 * s, 300 * s, 18 * s)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#505050"))
    p.drawRoundedRect(QRectF(tag.left(), tag.top(), tag.width() + bar.width(), tag.height()), 9 * s, 9 * s)
    p.setBrush(QColor("#f8f8f8"))
    p.drawRoundedRect(bar.adjusted(3 * s, 3 * s, -3 * s, -3 * s), 5 * s, 5 * s)
    col = QColor("#48c848") if frac > 0.5 else (QColor("#f0c020") if frac > 0.2 else QColor("#e83030"))
    fill = bar.adjusted(3 * s, 3 * s, -3 * s, -3 * s)
    fill.setWidth(fill.width() * frac)
    p.setBrush(col)
    p.drawRoundedRect(fill, 5 * s, 5 * s)
    p.setBrush(col.lighter(140))
    p.drawRect(QRectF(fill.left() + 4 * s, fill.top() + 2 * s, max(0.0, fill.width() - 8 * s), 3 * s))
    p.restore()
    T(p, "HP", tag.center().x(), tag.center().y(), "round", 17 * s, "#f8b800", "center", "middle", bold=True)
    if player or c.clip.props.get("show_numbers", True):
        T(p, f"{int(round(v))}/{int(round(mx))}", bar.right(), yb + 16 * s, "round", (30 if player else 24) * s,
          "#383838", "right", bold=True, shadow="#d0d0b8", sd=2 * s)
    if player:
        ex = max(0.0, min(1.0, float(c.val("exp", 0.4))))
        eb = QRectF(r.left() + 110 * s, r.bottom() - 30 * s, w - 140 * s, 12 * s)
        p.fillRect(eb.adjusted(-2 * s, -2 * s, 2 * s, 2 * s), QColor("#404040"))
        p.fillRect(eb, QColor("#606060"))
        g = QLinearGradient(0, eb.top(), 0, eb.bottom())
        g.setColorAt(0, QColor("#80d0ff"))
        g.setColorAt(1, QColor("#2878d0"))
        p.fillRect(QRectF(eb.left(), eb.top(), eb.width() * ex, eb.height()), QBrush(g))
        T(p, "EXP", eb.left() - 12 * s, eb.center().y(), "round", 15 * s, "#f8b800", "right", "middle", bold=True)
    return r.adjusted(-44 * s, -6, 44 * s, 14 * s)


def pk_white_box(p, r, s):
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(QPen(QColor("#384850"), 10 * s))
    p.setBrush(QColor("#f8f8f8"))
    p.drawRoundedRect(r, 18 * s, 18 * s)
    p.setPen(QPen(QColor("#68a0c0"), 5 * s))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(r.adjusted(9 * s, 9 * s, -9 * s, -9 * s), 12 * s, 12 * s)
    p.restore()


def pk_dark_box(p, r, s):
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(QPen(QColor("#d8b860"), 7 * s))
    p.setBrush(QColor(40, 56, 82, 245))
    p.drawRoundedRect(r, 16 * s, 16 * s)
    p.setPen(QPen(QColor(255, 255, 255, 60), 2 * s))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(r.adjusted(8 * s, 8 * s, -8 * s, -8 * s), 10 * s, 10 * s)
    p.restore()


def pk_cursor(p, x, y, s, t):
    bob = math.sin(t * 8) * 4 * s
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(QPen(QColor("#202020"), 1.5 * s))
    p.setBrush(QColor("#404040"))
    p.drawPolygon(QPolygonF([QPointF(x - 14 * s + bob, y - 13 * s), QPointF(x + 6 * s + bob, y),
                             QPointF(x - 14 * s + bob, y + 13 * s)]))
    p.restore()


def pk_menu(p, c):
    s = c.base_s * float(c.val("scale", 1.0))
    W = c.W
    bottom = c.Y()
    h = 210 * s
    top = bottom - h
    sel = int(round(float(c.val("selected", 0))))
    items = (lines_of(c, "items") + ["-"] * 4)[:4]
    if c.text("mode", "commands") == "commands":
        r = QRectF(W * 0.53, top, W * 0.45, h)
        prompt = c.text("prompt", "What will PhD STUDENT do?")
        if prompt:
            pr = QRectF(W * 0.02, top, W * 0.505, h)
            pk_dark_box(p, pr, s)
            for i, ln in enumerate(wrap(prompt, "round", 38 * s, pr.width() - 80 * s, bold=True)[:2]):
                T(p, ln, pr.left() + 40 * s, pr.top() + 40 * s + i * 62 * s, "round", 38 * s, "#ffffff", bold=True,
                  shadow="#203040", sd=3 * s)
        pk_white_box(p, r, s)
    else:
        r = QRectF(W * 0.02, top, W * 0.64, h)
        pk_white_box(p, r, s)
        info = QRectF(W * 0.67, top, W * 0.31, h)
        pk_white_box(p, info, s)
        T(p, "PP", info.left() + 40 * s, info.top() + 62 * s, "round", 36 * s, "#404040", "left", "middle", bold=True,
          shadow="#d0d0d0", sd=2 * s)
        T(p, c.text("pp", "10/15"), info.right() - 40 * s, info.top() + 62 * s, "round", 36 * s, "#404040", "right",
          "middle", bold=True, shadow="#d0d0d0", sd=2 * s)
        T(p, "TYPE/" + c.text("move_type", "SCIENCE").upper(), info.left() + 40 * s, info.top() + 142 * s, "round",
          32 * s, "#404040", "left", "middle", bold=True, shadow="#d0d0d0", sd=2 * s)
    for i, it in enumerate(items):
        col, row = i % 2, i // 2
        x = r.left() + 80 * s + col * (r.width() - 100 * s) / 2
        y = r.top() + 70 * s + row * 76 * s
        T(p, it.upper(), x, y, "round", 38 * s, "#404040", "left", "middle", bold=True, shadow="#d0d0d0", sd=3 * s)
        if i == sel:
            pk_cursor(p, x - 22 * s, y, s, c.t)
    return QRectF(0, top - 10 * s, W, h + 20 * s)


def pk_encounter(p, c):
    W, H = c.W, c.H
    s = c.base_s
    t = c.t
    full = QRectF(0, 0, W, H)
    style = c.text("wipe", "spiral")
    flash_end, wipe_end = 0.55, 1.35
    open_start = max(wipe_end, c.dur - 0.5)
    black = QColor(c.text("color", "#000000"))
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    if t < flash_end:
        if int(t / 0.1375) % 2 == 0:
            p.fillRect(full, QColor(255, 255, 255, 225))
        p.restore()
        return full
    if t < wipe_end:
        q = (t - flash_end) / (wipe_end - flash_end)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(black)
        if style == "spiral":
            R = math.hypot(W, H)
            for start_ang in (90, 270):
                path = QPainterPath()
                path.moveTo(W / 2, H / 2)
                path.arcTo(QRectF(W / 2 - R, H / 2 - R, 2 * R, 2 * R), start_ang, -180 * q)
                path.closeSubpath()
                p.drawPath(path)
        elif style == "stripes":
            n = 10
            bh = H / n
            for i in range(n):
                w = W * min(1.0, q * 1.15)
                x = 0 if i % 2 == 0 else W - w
                p.drawRect(QRectF(x, i * bh, w, bh + 1))
        elif style == "blocks":
            cols, rows = 16, 9
            order = list(range(cols * rows))
            random.Random(3).shuffle(order)
            bw, bh = W / cols, H / rows
            for k in order[:int(q * len(order))]:
                p.drawRect(QRectF((k % cols) * bw, (k // cols) * bh, bw + 1, bh + 1))
        else:  # bars / vs
            p.drawRect(QRectF(0, 0, W, H / 2 * q))
            p.drawRect(QRectF(0, H - H / 2 * q, W, H / 2 * q))
    elif t < open_start:
        p.fillRect(full, black)
    else:
        q = ease_out(min(1.0, (t - open_start) / 0.5))
        hh = H / 2 * (1 - q)
        p.fillRect(QRectF(0, 0, W, hh), black)
        p.fillRect(QRectF(0, H - hh, W, hh), black)
    if style == "vs" and wipe_end - 0.2 <= t < open_start:
        k = ease_out(min(1.0, (t - wipe_end + 0.2) / 0.4))
        bh = H * 0.24
        for top, col, sign, name in ((H * 0.2, "#c02828", -1, c.text("left_name", "PhD STUDENT")),
                                     (H * 0.56, "#2850c0", 1, c.text("right_name", "REVIEWER 2"))):
            off = sign * (1 - k) * W
            band = QPolygonF([QPointF(off, top + bh * 0.25), QPointF(W + off, top), QPointF(W + off, top + bh * 0.75),
                              QPointF(off, top + bh)])
            g = QLinearGradient(0, top, 0, top + bh)
            g.setColorAt(0, QColor(col).lighter(130))
            g.setColorAt(1, QColor(col).darker(140))
            p.setPen(QPen(QColor(255, 255, 255), 4 * s))
            p.setBrush(QBrush(g))
            p.drawPolygon(band)
            T(p, name.upper(), W * (0.3 if sign < 0 else 0.7) + off, top + bh / 2, "bold", 64 * s, "#ffffff",
              "center", "middle", italic=True, outline="#000000", ow=6 * s)
        if k >= 1:
            sc = 1 + 0.5 * max(0.0, 1 - (t - wipe_end - 0.2) / 0.2)
            T(p, "VS", W / 2, H / 2, "bold", 150 * s * sc, "#ffd21f", "center", "middle", italic=True,
              outline="#6a2a00", ow=10 * s)
    p.restore()
    return full


def draw_tube(p, x, y, r, angle=0.0, lift=0.0, cap="#e04848", alpha=1.0):
    """Original catching device: a lab sample tube with a coloured cap."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setOpacity(p.opacity() * alpha)
    p.translate(x, y)
    p.rotate(angle)
    dark = QPen(QColor(30, 30, 40), 0.09 * r)
    dark.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    tube = QPainterPath()
    tube.addRoundedRect(QRectF(-0.45 * r, -0.8 * r, 0.9 * r, 1.6 * r), 0.1 * r, 0.1 * r)
    bulb = QPainterPath()
    bulb.addEllipse(QRectF(-0.45 * r, 0.35 * r, 0.9 * r, 0.9 * r))
    body = tube.united(bulb)          # used only for the outline
    for part in (tube, bulb):
        p.fillPath(part, QColor(215, 240, 255, 230))
    p.save()
    p.setClipRect(QRectF(-r, 0.1 * r, 2 * r, 2 * r))
    for part in (tube, bulb):
        p.fillPath(part, QColor("#3cc8b4"))
    p.restore()
    p.fillRect(QRectF(-0.45 * r, -0.45 * r, 0.9 * r, 0.32 * r), QColor("#ffffff"))
    p.setPen(QPen(QColor(120, 120, 140), 0.05 * r))
    p.drawLine(QPointF(-0.28 * r, -0.29 * r), QPointF(0.28 * r, -0.29 * r))
    p.setPen(dark)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(body)
    p.setBrush(QColor(255, 255, 255, 140))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(-0.32 * r, -0.7 * r, 0.12 * r, 1.5 * r), 0.06 * r, 0.06 * r)
    p.translate(0, -lift * r)
    p.rotate(-lift * 25)
    g = QLinearGradient(-0.6 * r, 0, 0.6 * r, 0)
    g.setColorAt(0, QColor(cap).lighter(150))
    g.setColorAt(1, QColor(cap).darker(140))
    p.setPen(dark)
    p.setBrush(QBrush(g))
    p.drawRoundedRect(QRectF(-0.58 * r, -1.25 * r, 1.16 * r, 0.5 * r), 0.12 * r, 0.12 * r)
    p.restore()


def _bounce(q):
    q = max(0.0, min(1.0, q))
    if q < 0.6:
        return (q / 0.6) ** 2
    k = (q - 0.6) / 0.4
    return 1 - 0.12 * math.sin(k * math.pi)


def pk_capture(p, c):
    W, H = c.W, c.H
    s = c.s
    t = c.t
    fx, fy = float(c.val("from_x", 0.15)) * W, float(c.val("from_y", 0.85)) * H
    tx, ty = float(c.val("target_x", 0.7)) * W, float(c.val("target_y", 0.42)) * H
    gy = ty + float(c.val("ground", 0.18)) * H
    hy = ty - 0.06 * H
    r = 48 * s
    cap = c.text("color", "#e04848")
    shakes = max(0, min(3, int(round(float(c.val("shakes", 3))))))
    caught = c.text("result", "caught") == "caught"
    T_THROW, T_OPEN, T_DROP, T_SHAKE = 0.8, 0.9, 0.5, 0.9
    full = QRectF(0, 0, W, H)
    if t < T_THROW:
        q = t / T_THROW
        x = fx + (tx - fx) * q
        y = fy + (hy - fy) * q - math.sin(math.pi * q) * 0.28 * H
        draw_tube(p, x, y, r, q * 900, 0, cap)
        return full
    t -= T_THROW
    if t < T_OPEN:
        q = t / T_OPEN
        lift = min(1.0, q * 4) if q < 0.75 else max(0.0, 1 - (q - 0.75) * 4)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        if q < 0.45:
            k = q / 0.45
            R = 170 * s * ease_out(k)
            gx, gy_ = tx, ty
            a = k
        else:
            k = (q - 0.45) / 0.55
            R = 170 * s * (1 - k) + 20 * s
            gx, gy_ = tx, ty + (hy - ty) * k
            a = 1 - k * 0.6
        g = QRadialGradient(gx, gy_, R)
        g.setColorAt(0, QColor(255, 255, 255, int(255 * a)))
        g.setColorAt(0.5, QColor(255, 170, 220, int(200 * a)))
        g.setColorAt(1, QColor(255, 120, 200, 0))
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(gx, gy_), R, R)
        p.setPen(QPen(QColor(255, 200, 235, int(200 * a)), 10 * s))
        p.drawLine(QPointF(tx, hy - r), QPointF(gx, gy_))
        p.restore()
        draw_tube(p, tx, hy, r, 0, lift, cap)
        return full
    t -= T_OPEN
    if t < T_DROP:
        y = hy + (gy - hy) * _bounce(t / T_DROP)
        draw_tube(p, tx, y, r, 0, 0, cap)
        return full
    t -= T_DROP
    i = int(t // T_SHAKE)
    if i < shakes:
        local = t % T_SHAKE
        ang = math.sin(local / 0.5 * 2 * math.pi) * 24 if local < 0.5 else 0.0
        draw_tube(p, tx, gy, r, ang, 0, cap)
        return full
    post = t - shakes * T_SHAKE
    if caught:
        draw_tube(p, tx, gy, r, 0, 0, cap, alpha=1.0 if post > 0.15 else 0.6)
        if post < 1.4:
            k = post / 1.4
            for j in range(3):
                sx = tx + (j - 1) * 70 * s * (0.3 + k)
                sy = gy - r * 1.5 - 120 * s * ease_out(k) + abs(j - 1) * 20 * s
                p.save()
                p.setOpacity(p.opacity() * (1 - k))
                _icon(p, "star", sx, sy, 28 * s, "#ffe14a", "rpg")
                p.restore()
    else:
        if post < 0.6:
            k = post / 0.6
            p.save()
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setPen(Qt.PenStyle.NoPen)
            g = QRadialGradient(tx, gy, 220 * s * ease_out(k) + 1)
            g.setColorAt(0, QColor(255, 255, 255, int(255 * (1 - k))))
            g.setColorAt(1, QColor(255, 180, 230, 0))
            p.setBrush(QBrush(g))
            p.drawEllipse(QPointF(tx, gy), 220 * s * ease_out(k) + 1, 220 * s * ease_out(k) + 1)
            for j in range(14):
                a = j / 14 * 2 * math.pi
                d = 160 * s * ease_out(k)
                p.setBrush(QColor(255, 255, 255, int(230 * (1 - k))))
                p.drawEllipse(QPointF(tx + math.cos(a) * d, gy + math.sin(a) * d), 6 * s, 6 * s)
            p.restore()
            if post < 0.08:
                draw_tube(p, tx, gy, r, 0, 1.0, cap)
    return full


def pk_levelup(p, c):
    s = c.s
    right, top = c.X(), c.Y()
    rows = []
    for ln in lines_of(c, "stats"):
        parts = ln.split()
        nums = [x for x in parts if x.lstrip("+-").isdigit()]
        name = " ".join(x for x in parts if not x.lstrip("+-").isdigit())
        inc = nums[0] if nums else ""
        tot = nums[1] if len(nums) > 1 else ""
        rows.append((name, inc, tot))
    w = 470 * s
    h = 60 * s + len(rows) * 54 * s
    r = QRectF(right - w, top, w, h)
    pk_white_box(p, r, s)
    phase2 = c.t >= float(c.val("switch_time", 2.0))
    for i, (name, inc, tot) in enumerate(rows):
        y = r.top() + 50 * s + i * 54 * s
        T(p, name.upper(), r.left() + 40 * s, y, "round", 32 * s, "#404040", "left", "middle", bold=True,
          shadow="#d0d0d0", sd=2 * s)
        val = tot if phase2 and tot else ("+" + inc.lstrip("+") if inc else "")
        T(p, val, r.right() - 40 * s, y, "round", 32 * s, "#404040", "right", "middle", bold=True,
          shadow="#d0d0d0", sd=2 * s)
    return r.adjusted(-6, -6, 6, 6)


def pk_text(p, c):
    s = c.s
    cx, cy = c.X(), c.Y()
    w, h = c.W * 0.9, 200 * s
    r = QRectF(cx - w / 2, cy - h / 2, w, h)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(QPen(QColor("#384850"), 10 * s))
    p.setBrush(QColor("#f8f8f8"))
    p.drawRoundedRect(r, 18 * s, 18 * s)
    p.setPen(QPen(QColor("#68a0c0"), 5 * s))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(r.adjusted(9 * s, 9 * s, -9 * s, -9 * s), 12 * s, 12 * s)
    p.restore()
    text = c.text("text", "REVIEWER 2 used MAJOR REVISIONS!")
    cps = float(c.val("cps", 30))
    shown = len(text) if cps <= 0 else int(max(0.0, c.t - 0.1) * cps)
    lines = wrap(text, "round", 40 * s, w - 120 * s, bold=True)[:2]
    rem = shown
    for i, ln in enumerate(lines):
        T(p, ln[:max(0, rem)], r.left() + 50 * s, r.top() + 40 * s + i * 62 * s, "round", 40 * s, "#404040", bold=True,
          shadow="#d0d0d0", sd=3 * s)
        rem -= len(ln) + 1
    if shown >= len(text) and int(c.t * 3) % 2 == 0:
        x, y = r.right() - 60 * s, r.bottom() - 52 * s
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#e03030"))
        p.drawPolygon(QPolygonF([QPointF(x - 14 * s, y), QPointF(x + 14 * s, y), QPointF(x, y + 16 * s)]))
        p.restore()
    return r.adjusted(-8, -8, 8, 8)


def sf_versus(p, c):
    s = c.base_s
    W, H = c.W, c.H
    y = c.Y()
    bw, bh = W * 0.385, 34 * s
    L = QRectF(W / 2 - 60 * s - bw, y, bw, bh)
    R = QRectF(W / 2 + 60 * s, y, bw, bh)
    mx = max(1e-6, float(c.val("max_value", 100)))
    vr = c.bar_value()
    gr_ = c.bar_value(max(0.0, c.t - 0.6))
    vl = float(c.val("value_left", 100))
    gl = float(c.val_at("value_left", max(0.0, c.t - 0.6), vl))
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    for rect, v, gv, left in ((L, vl, gl, True), (R, vr, gr_, False)):
        g = QLinearGradient(0, rect.top(), 0, rect.bottom())
        g.setColorAt(0, QColor("#f4f4f4"))
        g.setColorAt(0.5, QColor("#8a8a8a"))
        g.setColorAt(1, QColor("#d0d0d0"))
        p.setPen(QPen(QColor(20, 20, 20), 2 * s))
        p.setBrush(QBrush(g))
        p.drawRect(rect.adjusted(-5 * s, -5 * s, 5 * s, 5 * s))
        inner = rect
        p.fillRect(inner, QColor("#2a0606"))

        def bar(frac, col, inner=inner, left=left):
            frac = max(0.0, min(1.0, frac))
            fw = inner.width() * frac
            x = inner.right() - fw if left else inner.left()
            gg = QLinearGradient(0, inner.top(), 0, inner.bottom())
            gg.setColorAt(0, QColor(col).lighter(130))
            gg.setColorAt(1, QColor(col).darker(120))
            p.fillRect(QRectF(x, inner.top(), fw, inner.height()), QBrush(gg))
        if gv > v:
            bar(gv / mx, "#e01818")
        bar(v / mx, "#ffd21f")
    p.restore()
    T(p, c.text("name_left", "PhD Student").upper(), L.left(), L.bottom() + 10 * s, "bold", 28 * s, "#ffffff",
      italic=True, outline="#000000", ow=5 * s)
    T(p, c.text("name_right", "Reviewer 2").upper(), R.right(), R.bottom() + 10 * s, "bold", 28 * s, "#ffffff", "right",
      italic=True, outline="#000000", ow=5 * s)
    timer = max(0, int(float(c.val("timer", 99)) - c.t))
    T(p, f"{timer:02d}", W / 2, y + bh / 2 + 6 * s, "bold", 60 * s, "#ffd21f", "center", "middle", outline="#6a2a00",
      ow=6 * s)
    rt = c.text("round_text", "ROUND 1")
    big = None
    if rt and c.t < 2.3:
        if c.t < 1.2:
            big, col, k = rt.upper(), "#ffd21f", c.t / 1.2
        else:
            big, col, k = "FIGHT!", "#ff3a1a", (c.t - 1.2) / 1.1
    if (vr <= 0 or vl <= 0) and int(c.t * 4) % 2 == 0:
        big, col, k = "K.O.", "#ff3a1a", 1.0
    if big:
        sc = 1 + 0.6 * max(0.0, 1 - k * 4)
        T(p, big, W / 2, H * 0.45, "bold", 150 * s * sc, col, "center", "middle", italic=True, outline="#3a0a00",
          ow=10 * s)
    return QRectF(0, 0, W, H) if big else QRectF(0, y - 20 * s, W, 140 * s)


def mc_toast(p, c):
    s = c.s
    right, top = c.X(), c.Y()
    w, h = 580 * s, 112 * s
    r = QRectF(right - w, top, w, h)
    p.fillRect(r, QColor("#1a1a1a"))
    p.fillRect(r.adjusted(4 * s, 4 * s, -4 * s, -4 * s), QColor("#555555"))
    p.fillRect(r.adjusted(8 * s, 8 * s, -8 * s, -8 * s), QColor("#212121"))
    ib = QRectF(r.left() + 22 * s, r.top() + 20 * s, 72 * s, 72 * s)
    p.fillRect(ib, QColor("#8b8b8b"))
    p.fillRect(ib.adjusted(4 * s, 4 * s, -4 * s, -4 * s), QColor("#c6c6c6"))
    draw_icon(p, c.text("icon", "book"), ib.center().x(), ib.center().y(), 24 * s)
    px = max(1, int(round(3.2 * s)))
    pixel_text(p, c.text("header", "Advancement Made!"), ib.right() + 22 * s, r.top() + 30 * s, px, QColor("#ffff55"),
               shadow=QColor("#3f3f15"))
    pixel_text(p, c.text("text", "First Draft Submitted"), ib.right() + 22 * s, r.top() + 64 * s, px, QColor("#ffffff"),
               shadow=QColor("#3f3f3f"))
    return r.adjusted(-4, -4, 4, 4)


def mc_xp(p, c):
    s = c.s
    cx, y = c.X(), c.Y()
    w, h = 728 * s, 14 * s
    r = QRectF(cx - w / 2, y, w, h)
    prog = max(0.0, min(1.0, float(c.val("progress", 0.4))))
    p.fillRect(r.adjusted(-2 * s, -2 * s, 2 * s, 2 * s), QColor("#000000"))
    p.fillRect(r, QColor("#2c2c2c"))
    g = QLinearGradient(0, r.top(), 0, r.bottom())
    g.setColorAt(0, QColor("#b8ff60"))
    g.setColorAt(1, QColor("#5aa818"))
    p.fillRect(QRectF(r.left(), r.top(), r.width() * prog, r.height()), QBrush(g))
    for i in range(1, 18):
        x = r.left() + r.width() * i / 18
        p.fillRect(QRectF(x - 1 * s, r.top(), 2 * s, r.height()), QColor(0, 0, 0, 170))
    lvl = str(int(round(float(c.val("level", 30)))))
    T(p, lvl, cx, y - 6 * s, "pixel", 34 * s, "#80ff20", "center", "bottom", outline="#000000")
    return QRectF(cx - w / 2 - 6, y - 60 * s, w + 12, 80 * s)


# ================================================================== catalogue
G_RS, G_SV, G_SK, G_ER, G_PK, G_MORE = ("Inspired by RuneScape", "Inspired by Stardew Valley", "Inspired by Skyrim",
                                        "Inspired by Elden Ring", "Inspired by Pokémon", "Inspired by other classics")
ICON_P = ("icon", "Icon", "choice", ICONS)

SKINS = {
    "rs_level": ("Parchment level-up box (RuneScape level-up message)", G_RS, 4.0, rs_level,
                 {"skill": "Pipetting", "level": "2", "icon": "pipette", "color": "#1c1ca3",
                  "continue": "Click here to continue", "fireworks": True, "x": 0.5, "y": 0.82, "anim_in": "pop"},
                 [("skill", "Skill name", "text"), ("level", "New level", "text"), ICON_P,
                  ("color", "Blue text colour", "color"), ("continue", "Last line", "text"),
                  ("fireworks", "Fireworks", "bool")]),
    "rs_hitsplat": ("Damage splat (RuneScape hitsplat)", G_RS, 1.2, rs_hitsplat,
                    {"text": "12", "kind": "hit", "x": 0.6, "y": 0.45, "anim_in": "none", "anim_out": "fade",
                     "target_bar": "", "follow_bar": True, "offset_x": 0.0, "offset_y": 0.09},
                    [("text", "Number", "text"), ("kind", "Kind", "choice", list(SPLAT_COLORS)),
                     ("target_bar", "Health bar it lowers", "target"),
                     ("follow_bar", "Sit under that overhead bar", "bool"),
                     ("offset_x", "Offset X from the bar", "float", -0.5, 0.5, 0.005),
                     ("offset_y", "Offset Y from the bar", "float", -0.5, 0.5, 0.005)]),
    "rs_dialogue": ("NPC chat box with talking head (RuneScape quest dialogue)", G_RS, 5.0, rs_dialogue,
                    {"name": "Professor Grid",
                     "text": "Ah, adventurer! My cryo-EM grids have gone missing from the lab. Could you find them "
                             "for me?", "side": "left", "cps": 0.0, "continue": "Click here to continue",
                     "pixel_portrait": False, "pixel_size": 64.0, "portrait_x": 0.5, "portrait_y": 0.5,
                     "portrait_size": 1.0, "x": 0.5, "y": 0.98, "anim_in": "none", "anim_out": "none"},
                    [("name", "Who is talking", "text"), ("text", "What they say", "longtext"),
                     ("side", "Talking head on the", "choice", ["left", "right"]),
                     ("cps", "Typing speed (0 = all at once, like the game)", "float", 0.0, 200.0, 1.0),
                     ("continue", "Blue last line", "text"), ("pixel_portrait", "Pixel-art head", "bool"),
                     ("pixel_size", "Head pixels across", "float", 16.0, 256.0, 1.0),
                     ("portrait_size", "Face zoom (smaller = closer)", "float", 0.05, 1.0, 0.01)]),
    "rs_options": ("Select an Option reply list (RuneScape dialogue choices)", G_RS, 3.0, rs_options,
                   {"title": "Select an Option", "options": "Yes, I'll help you.\nWhat's in it for me?\nSorry, I'm busy.",
                    "selected": 0.0, "numbered": False, "x": 0.5, "y": 0.98, "anim_in": "none", "anim_out": "none"},
                   [("title", "Title", "text"), ("options", "Replies (one per line)", "longtext"),
                    ("selected", "Highlighted reply (-1 none, 0 first)", "float", -1.0, 4.0, 1.0),
                    ("numbered", "Number the replies", "bool")]),
    "rs_hpbar": ("Overhead health bar (RuneScape combat bar)", G_RS, 15.0, rs_hpbar,
                 {"value": 100.0, "max_value": 100.0, "width": 150.0, "label": "", "x": 0.5, "y": 0.3,
                  "anim_in": "none", "anim_out": "fade"},
                 [("value", "Health", "float", 0.0, 10000.0, 1.0), ("max_value", "Maximum", "float", 1.0, 10000.0, 1.0),
                  ("width", "Bar length", "float", 40.0, 600.0, 1.0), ("label", "Name above (optional)", "text")]),
    "rs_questdone": ("Quest complete scroll (RuneScape quest complete)", G_RS, 6.0, rs_questdone,
                     {"quest": "The Missing Grids", "rewards": "1 Quest Point\n2,500 Pipetting XP\n1,000 Coffee XP\n"
                                                            "A Golden Pipette", "points": "42", "icon": "pipette",
                      "fireworks": True, "x": 0.5, "y": 0.47, "anim_in": "pop", "anim_dur": 0.35},
                     [("quest", "Quest name", "text"), ("rewards", "Rewards (one per line)", "longtext"),
                      ("points", "Quest points total", "text"), ICON_P, ("fireworks", "Fireworks", "bool")]),
    "rs_gamemsg": ("Chat-box game messages (RuneScape game text)", G_RS, 6.0, rs_gamemsg,
                   {"lines": "Welcome to the Lab.\n[red]You have started a new quest: [blue]The Missing Grids\n"
                             "[purple]You feel a little more confident.", "interval": 1.2, "max_lines": 5.0, "box": True,
                    "x": 0.01, "y": 0.985, "anim_in": "none", "anim_out": "fade"},
                   [("lines", "Messages (one per line; colours: [red] [blue] [green] [purple] [orange])", "longtext"),
                    ("interval", "Seconds between messages", "float", 0.0, 10.0, 0.1),
                    ("max_lines", "Lines shown at once", "float", 1.0, 10.0, 1.0), ("box", "Parchment background", "bool")]),
    "rs_chat": ("Overhead chat text (RuneScape public chat effects)", G_RS, 4.0, rs_chat,
                {"text": "Free coffee in the lab!", "effect": "wave", "color": "yellow", "x": 0.5, "y": 0.3,
                 "anim_in": "none", "anim_out": "none"},
                [("text", "Text", "text"),
                 ("effect", "Effect", "choice", ["none", "wave", "wave2", "shake", "scroll", "slide", "flash1",
                                                  "flash2", "flash3", "glow"]),
                 ("color", "Colour", "choice", list(CHAT_COLORS))]),
    "rs_xpdrop": ("XP drop + counter (RuneScape XP drops)", G_RS, 2.0, rs_xpdrop,
                  {"amount": 35.0, "total": 13034404.0, "icon": "microscope", "x": 0.97, "y": 0.04, "anim_in": "none"},
                  [("amount", "XP gained", "float", 0.0, 100000.0, 1.0),
                   ("total", "Total XP before", "float", 0.0, 200000000.0, 1.0), ICON_P]),
    "sv_levelup": ("Level-up profession choice (Stardew Valley level-up screen)", G_SV, 5.0, sv_levelup,
                   {"title": "Level Up", "level": "10", "skill": "Pipetting", "subtitle": "Choose a profession:",
                    "option1": "Theorist", "desc1": "Equations always work on the first try.", "icon1": "book",
                    "option2": "Experimentalist", "desc2": "Location of working pipettes revealed.",
                    "icon2": "microscope", "icon": "leaf", "selected": -1.0, "x": 0.5, "y": 0.5, "anim_in": "pop"},
                   [("title", "Title", "text"), ("level", "Level", "text"), ("skill", "Skill", "text"),
                    ("subtitle", "Subtitle", "text"), ("option1", "Choice 1", "text"),
                    ("desc1", "Choice 1 text", "longtext"), ("icon1", "Choice 1 icon", "choice", ICONS),
                    ("option2", "Choice 2", "text"), ("desc2", "Choice 2 text", "longtext"),
                    ("icon2", "Choice 2 icon", "choice", ICONS), ("icon", "Header icon", "choice", ICONS),
                    ("selected", "Picked (-1 none, 0 left, 1 right)", "float", -1.0, 1.0, 1.0)]),
    "sv_item": ("Item found pop-up (Stardew Valley item pickup)", G_SV, 3.0, sv_item,
                {"name": "Lukewarm Coffee", "icon": "coffee", "count": 1.0, "x": 0.01, "y": 0.985,
                 "anim_in": "slide_up", "anim_out": "fade"},
                [("name", "Item name", "text"), ICON_P, ("count", "How many", "float", 1.0, 999.0, 1.0)]),
    "sv_note": ("Little message box (Stardew Valley HUD message)", G_SV, 4.0, sv_note,
                {"text": "You've got some new ideas for chapter 4...", "x": 0.01, "y": 0.985, "anim_in": "slide_up"},
                [("text", "Message", "longtext")]),
    "sv_clock": ("Day, time & gold box (Stardew Valley clock)", G_SV, 20.0, sv_clock,
                 {"day": "Tue. 2", "start": "07:30", "speed": 1.43, "gold": 85773.0, "x": 0.985, "y": 0.02,
                  "anim_in": "fade"},
                 [("day", "Day", "text"), ("start", "Start time (hh:mm)", "text"),
                  ("speed", "Game minutes per second", "float", 0.0, 60.0, 0.1),
                  ("gold", "Gold", "float", 0.0, 9999999.0, 1.0)]),
    "sv_dialogue": ("Dialogue box with portrait (Stardew Valley conversation)", G_SV, 6.0, sv_dialogue,
                    {"speaker": "Lab Mate", "text": "Hey! The ice on your grids looks perfect today. Want to collect "
                                                    "data before lunch?", "cps": 32.0, "pixel_portrait": True,
                     "pixel_size": 64.0, "portrait_x": 0.5, "portrait_y": 0.5, "portrait_size": 1.0,
                     "x": 0.5, "y": 0.97, "anim_in": "fade", "anim_dur": 0.15},
                    [("speaker", "Name on the plate", "text"), ("text", "What they say", "longtext"),
                     ("cps", "Typing speed (letters/s, 0 = all at once)", "float", 0.0, 200.0, 1.0),
                     ("pixel_portrait", "Pixel-art portrait", "bool"),
                     ("pixel_size", "Portrait pixels across", "float", 16.0, 256.0, 1.0),
                     ("portrait_size", "Face zoom (smaller = closer)", "float", 0.05, 1.0, 0.01)]),
    "sv_energy": ("Energy bar (Stardew Valley energy meter)", G_SV, 20.0, sv_energy,
                  {"label": "E", "value": 80.0, "max_value": 100.0, "x": 0.985, "y": 0.97, "anim_in": "fade"},
                  [("label", "Letter", "text"), ("value", "Energy", "float", 0.0, 1000.0, 1.0),
                   ("max_value", "Maximum", "float", 1.0, 1000.0, 1.0)]),
    "sk_skillup": ("Skill increased + level progress (Skyrim skill-up message)", G_SK, 4.0, sk_skillup,
                   {"skill": "Pipetting", "level": "47", "label": "Level Progress", "progress_from": 40.0,
                    "progress_to": 70.0, "char_level": "35", "x": 0.5, "y": 0.2, "anim_dur": 0.6},
                   [("skill", "Skill", "text"), ("level", "New skill level", "text"), ("label", "Bar label", "text"),
                    ("progress_from", "Bar from (%)", "float", 0.0, 100.0, 1.0),
                    ("progress_to", "Bar to (%)", "float", 0.0, 100.0, 1.0), ("char_level", "Number at right", "text")]),
    "sk_bars": ("Health / magicka / stamina bars (Skyrim bottom bars)", G_SK, 20.0, sk_bars,
                {"value": 100.0, "magicka": 100.0, "stamina": 100.0, "max_value": 100.0, "hide_full": False,
                 "x": 0.5, "y": 0.95},
                [("value", "Health (centre)", "float", 0.0, 1000.0, 1.0),
                 ("magicka", "Magicka (left)", "float", 0.0, 1000.0, 1.0),
                 ("stamina", "Stamina (right)", "float", 0.0, 1000.0, 1.0),
                 ("max_value", "Maximum", "float", 1.0, 1000.0, 1.0), ("hide_full", "Hide bars that are full", "bool")]),
    "sk_compass": ("Compass + enemy health (Skyrim compass)", G_SK, 20.0, sk_compass,
                   {"heading": 0.0, "markers": "35, -60", "enemy": "Reviewer 2", "show_enemy": True, "value": 100.0,
                    "max_value": 100.0, "x": 0.5, "y": 0.045},
                   [("heading", "Facing (degrees)", "float", -720.0, 720.0, 1.0),
                    ("markers", "Markers (degrees, comma separated)", "text"), ("enemy", "Enemy name", "text"),
                    ("show_enemy", "Show enemy health", "bool"), ("value", "Enemy health", "float", 0.0, 1000.0, 1.0),
                    ("max_value", "Maximum", "float", 1.0, 1000.0, 1.0)]),
    "sk_note": ("Corner messages (Skyrim top-left notifications)", G_SK, 6.0, sk_note,
                {"lines": "Critical strike on Reviewer 2\nCoffee added", "interval": 1.0, "hold": 4.0,
                 "x": 0.02, "y": 0.03, "anim_in": "none", "anim_out": "none"},
                [("lines", "Messages (one per line)", "longtext"),
                 ("interval", "Seconds between", "float", 0.1, 10.0, 0.1),
                 ("hold", "Seconds each stays", "float", 0.5, 30.0, 0.1)]),
    "sk_subtitle": ("Speaker subtitle (Skyrim subtitles)", G_SK, 4.0, sk_subtitle,
                    {"speaker": "Supervisor", "text": "Nargh! Another revision?", "x": 0.5, "y": 0.86},
                    [("speaker", "Speaker", "text"), ("text", "Line", "longtext")]),
    "sk_skills": ("Starry skills screen (Skyrim skills constellations)", G_SK, 6.0, sk_skills,
                  {"left_label": "NAME", "left_value": "PhD Student", "level": "27", "level_progress": 60.0,
                   "right_label": "RACE", "right_value": "Caffeinated", "perks": "Perks to increase: 3",
                   "skills": "Pipetting 15\nCoding 59\nWriting 15\nPresenting 42\nCoffee Brewing 100\nProcrastination 87",
                   "selected": 2.0, "pattern": 0.0, "bg_opacity": 0.9, "bottom_bars": True,
                   "description": "The School of Writing governs turning results into chapters. This skill makes it "
                                  "easier to meet deadlines.", "anim_dur": 0.5},
                  [("left_label", "Top-left label", "text"), ("left_value", "Top-left value", "text"),
                   ("level", "Level", "text"), ("level_progress", "Level bar (%)", "float", 0.0, 100.0, 1.0),
                   ("right_label", "Top-right label", "text"), ("right_value", "Top-right value", "text"),
                   ("perks", "Middle text", "text"), ("skills", "Skills ('Name number', one per line)", "longtext"),
                   ("selected", "Selected skill (0 = first)", "float", 0.0, 30.0, 0.05),
                   ("description", "Description", "longtext"), ("pattern", "Star pattern", "float", 0.0, 50.0, 1.0),
                   ("bg_opacity", "Background darkness", "float", 0.0, 1.0, 0.01),
                   ("bottom_bars", "Bars at the bottom", "bool")]),
    "sk_inventory": ("Inventory list + item card (Skyrim inventory)", G_SK, 6.0, sk_inventory,
                     {"categories": "Favorites\nAll\nWeapons\nApparel\nPotions\nFood\nIngredients",
                      "selected_category": 1.0,
                      "items": "Coffee Beans (5)\nCryo Grids (14)\nLab Coat\nLiquid Nitrogen\nPipette\n"
                               "Pipette Tips (96)\nSample Tubes (12)\nThesis Draft v17\nUSB Stick",
                      "selected_item": 4.0, "card_title": "", "stats": "ARMOR 0 | WEIGHT 0.2 | VALUE 0",
                      "anim_dur": 0.4},
                     [("categories", "Categories (one per line)", "longtext"),
                      ("selected_category", "Selected category", "float", 0.0, 20.0, 1.0),
                      ("items", "Items (one per line)", "longtext"),
                      ("selected_item", "Selected item (keyframe it to scroll)", "float", 0.0, 50.0, 0.05),
                      ("card_title", "Card title (empty = selected item)", "text"),
                      ("stats", "Card stats ('LABEL value | ...')", "text")]),
    "sk_menu": ("Four-way menu (Skyrim Skills/Magic/Items/Map menu)", G_SK, 4.0, sk_menu,
                {"top": "Skills", "left": "Magic", "right": "Items", "bottom": "Map", "highlight": "top",
                 "x": 0.5, "y": 0.5, "anim_in": "fade"},
                [("top", "Top word", "text"), ("left", "Left word", "text"), ("right", "Right word", "text"),
                 ("bottom", "Bottom word", "text"),
                 ("highlight", "Highlighted", "choice", ["none", "top", "left", "right", "bottom"])]),
    "er_grace": ("Rest menu (Elden Ring site-of-grace menu)", G_ER, 5.0, er_grace,
                 {"location": "Faculty Coffee Corner", "sublabel": "Early Day",
                  "items": "Pass time\nLevel Up\nFlasks\nMemorize spell\nSort chest\nLeave", "selected": 1.0,
                  "hints": "A:OK B:Close X:Map", "anim_dur": 0.5},
                 [("location", "Place name", "text"), ("sublabel", "Small box text", "text"),
                  ("items", "Menu items (one per line)", "longtext"),
                  ("selected", "Selected item (0 = first)", "float", 0.0, 20.0, 0.05),
                  ("hints", "Button hints ('A:OK B:Close')", "text")]),
    "er_banner": ("Big gold/red banner (Elden Ring 'ENEMY FELLED' / 'YOU DIED')", G_ER, 4.0, er_banner,
                  {"text": "THESIS DEFENDED", "color": "gold", "x": 0.5, "y": 0.5, "anim_dur": 0.9},
                  [("text", "Text", "text"), ("color", "Colour", "choice", list(BANNER_COLORS))]),
    "er_boss": ("Boss health bar (Elden Ring boss bar)", G_ER, 20.0, er_boss,
                {"name": "Reviewer 2, the Unrelenting", "value": 100.0, "max_value": 100.0, "x": 0.5, "y": 0.86},
                [("name", "Boss name", "text"), ("value", "Health", "float", 0.0, 10000.0, 1.0),
                 ("max_value", "Maximum", "float", 1.0, 10000.0, 1.0)]),
    "er_compass": ("Thin compass line (Elden Ring compass)", G_ER, 20.0, er_compass,
                   {"heading": 0.0, "markers": "15", "x": 0.5, "y": 0.06},
                   [("heading", "Facing (degrees)", "float", -720.0, 720.0, 1.0),
                    ("markers", "Markers (degrees, comma separated)", "text")]),
    "er_loot": ("Item obtained (Elden Ring pickup message)", G_ER, 3.0, er_loot,
                {"name": "Golden Pipette", "count": 1.0, "icon": "pipette", "x": 0.98, "y": 0.8,
                 "anim_in": "fade"},
                [("name", "Item", "text"), ("count", "Count", "float", 1.0, 999.0, 1.0), ICON_P]),
    "zl_hearts": ("Heart containers (Zelda hearts)", G_MORE, 20.0, zl_hearts,
                  {"value": 7.5, "max_hearts": 10.0, "x": 0.03, "y": 0.04},
                  [("value", "Hearts filled (quarters work)", "float", 0.0, 30.0, 0.25),
                   ("max_hearts", "Heart containers", "float", 1.0, 30.0, 1.0)]),
    "pk_hpbox": ("Battle HP box, enemy or player (Pokémon battle status)", G_PK, 20.0, pk_hpbox,
                 {"name": "REVIEWER 2", "level": "50", "value": 100.0, "max_value": 100.0, "show_numbers": False,
                  "side": "enemy", "status": "none", "exp": 0.4, "x": 0.25, "y": 0.14, "anim_in": "slide_right"},
                 [("side", "Whose box", "choice", ["enemy", "player"]), ("name", "Name", "text"),
                  ("level", "Level", "text"), ("value", "HP", "float", 0.0, 9999.0, 1.0),
                  ("max_value", "Max HP", "float", 1.0, 9999.0, 1.0),
                  ("status", "Status tag", "choice", ["none"] + list(STATUS_COLORS)),
                  ("exp", "EXP bar, player only (0–1)", "float", 0.0, 1.0, 0.01),
                  ("show_numbers", "Show HP numbers (enemy)", "bool")]),
    "pk_text": ("Battle message box (Pokémon battle text)", G_PK, 4.0, pk_text,
                {"text": "REVIEWER 2 used MAJOR REVISIONS!", "cps": 30.0, "x": 0.5, "y": 0.87, "anim_in": "none",
                 "anim_out": "none"},
                [("text", "Message", "longtext"), ("cps", "Typing speed (letters/s)", "float", 0.0, 200.0, 1.0)]),
    "pk_encounter": ("Battle start transition (Pokémon wild-battle / trainer-battle intro)", G_PK, 2.2, pk_encounter,
                     {"wipe": "spiral", "color": "#000000", "left_name": "PhD Student", "right_name": "Reviewer 2",
                      "x": 0.5, "y": 0.5, "anim_in": "none", "anim_out": "none"},
                     [("wipe", "Wipe pattern ('vs' looks best at 3.5 s long)", "choice",
                       ["spiral", "stripes", "blocks", "bars", "vs"]),
                      ("color", "Wipe colour", "color"), ("left_name", "VS: top name", "text"),
                      ("right_name", "VS: bottom name", "text")]),
    "pk_menu": ("Battle menu: FIGHT/BAG or 4 moves (Pokémon battle menus)", G_PK, 4.0, pk_menu,
                {"mode": "commands", "items": "Fight\nBag\nTeam\nRun", "selected": 0.0,
                 "prompt": "What will PhD STUDENT do?", "pp": "10/15", "move_type": "Science", "x": 0.5, "y": 0.985,
                 "anim_in": "none", "anim_out": "none"},
                [("mode", "Menu", "choice", ["commands", "moves"]), ("items", "4 items (one per line)", "longtext"),
                 ("selected", "Cursor on (0–3)", "float", 0.0, 3.0, 1.0), ("prompt", "Left text (commands)", "text"),
                 ("pp", "PP (moves)", "text"), ("move_type", "Type (moves)", "text")]),
    "pk_capture": ("Catch sequence with a sample tube (Pokémon catch animation)", G_PK, 6.5, pk_capture,
                   {"from_x": 0.15, "from_y": 0.85, "target_x": 0.7, "target_y": 0.42, "ground": 0.18, "shakes": 3.0,
                    "result": "caught", "color": "#e04848", "x": 0.7, "y": 0.42, "anim_in": "none", "anim_out": "none"},
                   [("target_x", "Target X", "float", 0.0, 1.0, 0.005), ("target_y", "Target Y", "float", 0.0, 1.0, 0.005),
                    ("from_x", "Thrown from X", "float", 0.0, 1.0, 0.005),
                    ("from_y", "Thrown from Y", "float", 0.0, 1.0, 0.005),
                    ("ground", "Drop distance", "float", 0.0, 0.6, 0.01), ("shakes", "Wobbles (0–3)", "float", 0.0, 3.0, 1.0),
                    ("result", "Result", "choice", ["caught", "escaped"]), ("color", "Cap colour", "color")]),
    "pk_levelup": ("Level-up stats window (Pokémon level-up stats)", G_PK, 4.5, pk_levelup,
                   {"stats": "Max HP +4 52\nCaffeine +3 61\nPatience +1 12\nFocus +5 48\nWriting +2 37\nSpeed +3 44",
                    "switch_time": 2.0, "x": 0.97, "y": 0.05, "anim_in": "none"},
                   [("stats", "Stats ('Name +gain total', one per line)", "longtext"),
                    ("switch_time", "Show totals after (s)", "float", 0.0, 20.0, 0.1)]),
    "sf_versus": ("Versus health bars + ROUND/FIGHT (Street Fighter HUD)", G_MORE, 20.0, sf_versus,
                  {"name_left": "PhD Student", "name_right": "Reviewer 2", "value_left": 100.0, "value": 100.0,
                   "max_value": 100.0, "timer": 99.0, "round_text": "ROUND 1", "x": 0.5, "y": 0.05},
                  [("name_left", "Left fighter", "text"), ("name_right", "Right fighter", "text"),
                   ("value_left", "Left health", "float", 0.0, 1000.0, 1.0),
                   ("value", "Right health", "float", 0.0, 1000.0, 1.0),
                   ("max_value", "Maximum", "float", 1.0, 1000.0, 1.0), ("timer", "Timer starts at", "float", 0.0, 999.0, 1.0),
                   ("round_text", "Round text (empty = none)", "text")]),
    "mc_toast": ("Achievement toast (Minecraft 'Advancement Made!')", G_MORE, 4.0, mc_toast,
                 {"header": "Advancement Made!", "text": "First Draft Submitted", "icon": "book", "x": 0.985, "y": 0.02,
                  "anim_in": "slide_left", "anim_out": "slide_right"},
                 [("header", "Header", "text"), ("text", "Achievement", "text"), ICON_P]),
    "mc_xp": ("XP level bar (Minecraft experience bar)", G_MORE, 20.0, mc_xp,
              {"level": 30.0, "progress": 0.4, "x": 0.5, "y": 0.93},
              [("level", "Level", "float", 0.0, 9999.0, 1.0), ("progress", "Bar (0–1)", "float", 0.0, 1.0, 0.01)]),
}

for _key, (_label, _group, _dur, _fn, _defaults, _params) in SKINS.items():
    HUD_TYPES[_key] = {"label": _label, "group": _group, "duration": _dur, "defaults": dict(_defaults),
                       "params": list(_params), "skin": True}
    DRAWERS[_key] = _fn
for _g in (G_RS, G_SV, G_SK, G_ER, G_PK, G_MORE):
    if _g not in GROUP_ORDER:
        GROUP_ORDER.append(_g)
BAR_TYPES.update({"rs_hpbar", "sk_bars", "sk_compass", "er_boss", "zl_hearts", "pk_hpbox", "sf_versus"})
PORTRAIT_TYPES.update({"sv_dialogue", "rs_dialogue"})
FULLSCREEN_TYPES.update({"sk_skills", "sk_inventory", "er_grace", "pk_encounter", "pk_menu", "pk_capture"})
