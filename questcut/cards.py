"""Full-screen cards: title screen, game over, level complete, chapter, credits."""
from __future__ import annotations

import math
import random

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QLinearGradient, QPainter, QPen, QPolygonF, QRadialGradient

from .hud import draw_text, ease_out, ease_out_back, qc, text_size, wrap_text, lighter

CARD_TYPES = {
    "title": {"label": "Title screen", "duration": 5.0,
              "defaults": {"title": "THE PhD QUEST", "subtitle": "A Delft adventure", "body": "PRESS START",
                           "bg": "stars", "color": "#ffd23f", "bg_color": "#05061a", "style": "retro"}},
    "game_over": {"label": "Game over", "duration": 4.0,
                  "defaults": {"title": "GAME OVER", "subtitle": "Continue?  YES / NO", "body": "",
                               "bg": "black", "color": "#ff2a2a", "bg_color": "#000000", "style": "retro"}},
    "level_complete": {"label": "Level complete", "duration": 5.0,
                       "defaults": {"title": "LEVEL COMPLETE!", "subtitle": "Chapter 3: Methods",
                                    "body": "Coffees drunk ........ 412\nPapers read .......... 87\nBugs fixed ........... 9001",
                                    "bg": "gradient", "color": "#3ddc84", "bg_color": "#0b2a1a", "style": "rpg"}},
    "chapter": {"label": "Chapter / world intro", "duration": 4.0,
                "defaults": {"title": "The Cryo Lab", "subtitle": "WORLD 1-2", "body": "",
                             "bg": "gradient", "color": "#7dfcff", "bg_color": "#061620", "style": "fps"}},
    "credits": {"label": "Rolling credits", "duration": 20.0,
                "defaults": {"title": "CREDITS", "subtitle": "Thanks for playing!",
                             "body": "Director\nAlok\n\nStarring\nThe Supervisor\nReviewer 2\n\nSpecial thanks\nThe coffee machine",
                             "bg": "stars", "color": "#ffd23f", "bg_color": "#05061a", "style": "rpg"}},
    "continue": {"label": "Continue? countdown", "duration": 6.0,
                 "defaults": {"title": "CONTINUE?", "subtitle": "Insert coffee to continue", "body": "",
                              "bg": "black", "color": "#ffd23f", "bg_color": "#000000", "style": "retro"}},
}

CARD_PARAMS = [
    ("title", "Title", "text"),
    ("subtitle", "Subtitle", "text"),
    ("body", "More text (one item per line)", "longtext"),
    ("style", "Look", "choice", ["retro", "rpg", "fps"]),
    ("bg", "Background", "choice", ["stars", "gradient", "grid", "black", "scanlines"]),
    ("color", "Accent colour", "color"),
    ("bg_color", "Background colour", "color"),
]


def card_defaults(card_type: str) -> dict:
    d = dict(CARD_TYPES.get(card_type, CARD_TYPES["title"])["defaults"])
    d["card_type"] = card_type
    return d


def _background(p: QPainter, W, H, t, bg, bgc, col, s):
    p.fillRect(QRectF(0, 0, W, H), qc(bgc))
    if bg == "gradient":
        g = QRadialGradient(W / 2, H * 0.45, W * 0.7)
        g.setColorAt(0, lighter(bgc, 2.6))
        g.setColorAt(1, qc(bgc))
        p.fillRect(QRectF(0, 0, W, H), QBrush(g))
    elif bg == "stars":
        rnd = random.Random(7)
        p.setPen(Qt.PenStyle.NoPen)
        for _ in range(220):
            x0, y0, sp, sz = rnd.random(), rnd.random(), rnd.uniform(0.01, 0.06), rnd.uniform(1, 3.5)
            x = ((x0 - t * sp) % 1.0) * W
            tw = 0.5 + 0.5 * math.sin(t * 3 + x0 * 40)
            p.setBrush(QColor(255, 255, 255, int(90 + 160 * tw)))
            p.drawEllipse(QPointF(x, y0 * H), sz * s, sz * s)
    elif bg == "grid":
        horizon = H * 0.55
        g = QLinearGradient(0, 0, 0, horizon)
        g.setColorAt(0, qc(bgc))
        g.setColorAt(1, lighter(bgc, 3.0))
        p.fillRect(QRectF(0, 0, W, horizon), QBrush(g))
        p.setPen(QPen(qc(col, 0.6), 2 * s))
        for i in range(-20, 21):
            p.drawLine(QPointF(W / 2 + i * 30 * s, horizon), QPointF(W / 2 + i * 220 * s, H))
        off = (t * 0.5) % 1.0
        for j in range(12):
            k = ((j + off) / 12) ** 2
            y = horizon + (H - horizon) * k
            p.drawLine(QPointF(0, y), QPointF(W, y))
    elif bg == "scanlines":
        step = max(2, int(4 * s))
        for y in range(0, H, step * 2):
            p.fillRect(QRectF(0, y, W, step), QColor(255, 255, 255, 12))


def render_card(clip, t: float, W: int, H: int) -> np.ndarray:
    pr = clip.props
    ctype = pr.get("card_type", "title")
    style = pr.get("style", "retro")
    col = pr.get("color", "#ffd23f")
    bgc = pr.get("bg_color", "#000000")
    title, sub, body = pr.get("title", ""), pr.get("subtitle", ""), pr.get("body", "")
    s = H / 1080.0
    img = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor(0, 0, 0))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    _background(p, W, H, t, pr.get("bg", "black"), bgc, col, s)
    dur = clip.duration
    glow = qc(col, 0.7) if style != "retro" else None
    if ctype == "title":
        k = ease_out_back(min(1.0, t / 0.8))
        bob = math.sin(t * 2) * 8 * s
        draw_text(p, title, W / 2, H * 0.38 + bob, style, 150 * s * max(0.01, k), "#ffffff", "center", "middle",
                  col, 10 * s, glow=glow, glow_r=16 * s)
        if t > 0.6:
            draw_text(p, sub, W / 2, H * 0.53, style, 46 * s, col, "center", "middle", "#000000", 4 * s)
        if t > 1.2 and int(t * 2) % 2 == 0:
            draw_text(p, body.split("\n")[0] if body else "PRESS START", W / 2, H * 0.78, style, 44 * s, "#ffffff",
                      "center", "middle", "#000000", 3 * s)
        draw_text(p, "(C) THE LAB", W / 2, H * 0.93, "retro", 20 * s, "#888888", "center", "middle")
    elif ctype == "game_over":
        n = len(title)
        tw, _ = text_size(title, style, 150 * s)
        x0 = W / 2 - tw / 2
        cw = tw / max(1, n)
        for i, ch in enumerate(title):
            ti = t - i * 0.09
            if ti <= 0:
                continue
            drop = (1 - ease_out_back(min(1.0, ti / 0.5))) * -H * 0.4
            draw_text(p, ch, x0 + cw * (i + 0.5), H * 0.42 + drop, style, 150 * s, col, "center", "middle",
                      "#000000", 8 * s, glow=glow, glow_r=12 * s)
        if t > n * 0.09 + 0.6:
            a = min(1.0, (t - n * 0.09 - 0.6) / 0.4)
            draw_text(p, sub, W / 2, H * 0.62, style, 46 * s, qc("#ffffff", a), "center", "middle")
    elif ctype == "level_complete":
        k = ease_out_back(min(1.0, t / 0.6))
        draw_text(p, title, W / 2, H * 0.2, style, 110 * s * max(0.01, k), "#ffffff", "center", "middle", col,
                  9 * s, glow=glow, glow_r=14 * s)
        draw_text(p, sub, W / 2, H * 0.31, style, 40 * s, col, "center", "middle", "#000000", 3 * s)
        for i in range(3):
            ts = t - 0.8 - i * 0.3
            if ts < 0:
                continue
            sc = ease_out_back(min(1.0, ts / 0.35))
            cx, cy, r = W / 2 + (i - 1) * 150 * s, H * 0.45 - (30 * s if i == 1 else 0), 60 * s * sc
            pts = [QPointF(cx + math.cos(-math.pi / 2 + j * math.pi / 5) * (r if j % 2 == 0 else r * 0.45),
                           cy + math.sin(-math.pi / 2 + j * math.pi / 5) * (r if j % 2 == 0 else r * 0.45))
                   for j in range(10)]
            p.setPen(QPen(QColor("#5a3a00"), 4 * s))
            p.setBrush(QColor("#ffd23f"))
            p.drawPolygon(QPolygonF(pts))
        lines = [ln for ln in body.split("\n")]
        for i, ln in enumerate(lines):
            ts = t - 1.8 - i * 0.4
            if ts < 0:
                continue
            a = min(1.0, ts / 0.25)
            draw_text(p, ln, W / 2, H * 0.6 + i * 56 * s, style, 38 * s, qc("#ffffff", a), "center", "middle",
                      qc("#000000", a), 3 * s, bold=False)
    elif ctype == "chapter":
        k = ease_out(min(1.0, t / 0.6))
        a_out = 1.0 if t < dur - 0.5 else max(0.0, (dur - t) / 0.5)
        line_w = W * 0.5 * k
        p.setPen(QPen(qc(col, a_out), 3 * s))
        p.drawLine(QPointF(W / 2 - line_w / 2, H * 0.43), QPointF(W / 2 + line_w / 2, H * 0.43))
        p.drawLine(QPointF(W / 2 - line_w / 2, H * 0.62), QPointF(W / 2 + line_w / 2, H * 0.62))
        draw_text(p, sub, W / 2, H * 0.38, style, 40 * s, qc(col, k * a_out), "center", "middle")
        draw_text(p, title, W / 2 + (1 - k) * 200 * s, H * 0.525, style, 100 * s, qc("#ffffff", k * a_out), "center",
                  "middle", qc("#000000", a_out), 5 * s, glow=qc(col, 0.5 * a_out) if glow else None, glow_r=12 * s)
        if body:
            draw_text(p, body.split("\n")[0], W / 2, H * 0.7, style, 32 * s, qc("#cccccc", k * a_out), "center",
                      "middle", bold=False)
    elif ctype == "credits":
        lines = [title, ""] + body.split("\n") + ["", "", sub]
        lh = 64 * s
        total = len(lines) * lh + H
        y0 = H - (t / max(0.1, dur)) * total
        for i, ln in enumerate(lines):
            y = y0 + i * lh
            if -lh < y < H + lh:
                is_head = i == 0 or (i > 0 and lines[i - 1] == "" and i + 1 < len(lines) and lines[i + 1] != "")
                draw_text(p, ln, W / 2, y, style, (54 if i == 0 else 40) * s, col if is_head else "#ffffff",
                          "center", "middle", "#000000", 3 * s, bold=is_head)
    elif ctype == "continue":
        draw_text(p, title, W / 2, H * 0.32, style, 120 * s, col, "center", "middle", "#000000", 6 * s,
                  glow=glow, glow_r=10 * s)
        n = max(0, 9 - int(t / max(0.1, dur) * 10))
        frac = (t / max(0.1, dur) * 10) % 1.0
        sc = 1.0 + 0.4 * (1 - ease_out(min(1.0, frac * 3)))
        draw_text(p, str(n), W / 2, H * 0.56, style, 220 * s * sc, "#ffffff", "center", "middle", col, 8 * s)
        draw_text(p, sub, W / 2, H * 0.8, style, 40 * s, "#cccccc", "center", "middle")
    p.end()
    arr = np.frombuffer(img.constBits(), np.uint8).reshape(H, img.bytesPerLine() // 4, 4)[:, :W]
    return np.ascontiguousarray(arr[..., [2, 1, 0]])
