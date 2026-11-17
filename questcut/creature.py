"""More creature-collecting (Pokémon-inspired) pieces: index entry, "Who's that …?",
evolution and badge. All graphics are original drawings; only the idea is borrowed.

Any picture works: a PNG with transparency, a photo, or a frame grabbed from the
video. When a silhouette is needed and the picture has no transparency, the
person is cut out automatically (OpenCV GrabCut), once, and cached."""
from __future__ import annotations

import math
import random

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF, \
    QRadialGradient

from .game_skins import G_PK, SKINS, T, _c, wrap
from .hud import DRAWERS, FULLSCREEN_TYPES, HUD_TYPES, PORTRAIT_TYPES, ease_out, ease_out_back

# ------------------------------------------------------------------ pictures and cut-outs
_PIC_CACHE = {}
_MASK_CACHE = {}
IMAGE_PROPS = ("media2", "shadow_media")      # extra picture slots stored in clip.props


def cut_out_mask(rgba):
    """0..1 mask of the main subject. Uses the picture's own transparency when it has
    some; otherwise separates the subject from the background with GrabCut."""
    import cv2
    h, w = rgba.shape[:2]
    if rgba.shape[2] == 4 and (rgba[..., 3] < 250).mean() > 0.02:
        return rgba[..., 3].astype(np.float32) / 255.0
    sc = min(1.0, 360.0 / max(h, w))
    small = cv2.resize(np.ascontiguousarray(rgba[..., :3]), (max(8, int(w * sc)), max(8, int(h * sc))),
                       interpolation=cv2.INTER_AREA)
    sh, sw = small.shape[:2]
    mask = np.zeros((sh, sw), np.uint8)
    mx, my = max(1, int(sw * 0.05)), max(1, int(sh * 0.04))
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(small, mask, (mx, my, sw - 2 * mx, sh - 2 * my), bgd, fgd, 5, cv2.GC_INIT_WITH_RECT)
    except cv2.error:
        return np.ones((h, w), np.float32)
    fg = ((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD)).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(fg)
    if n > 1:
        big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        fg = (lab == big).astype(np.uint8)
    if fg.sum() < 0.02 * fg.size:              # nothing sensible found: keep the whole picture
        return np.ones((h, w), np.float32)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, k, iterations=2)
    # fill holes (inside the outline everything belongs to the subject)
    flood = fg.copy()
    ff = np.zeros((sh + 2, sw + 2), np.uint8)
    cv2.floodFill(flood, ff, (0, 0), 1)
    fg = fg | (1 - flood)
    m = cv2.resize(fg.astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)
    return np.clip(cv2.GaussianBlur(m, (0, 0), max(1.0, w / 600)), 0, 1)


def _crop(c, arr, media_id):
    """The clip's own picture is cropped with the face dot and zoom; the 'after' picture of an
    evolution with its own dot and zoom (pic2_*); other pictures are used whole."""
    pr = c.clip.props
    if media_id == c.clip.media_id:
        kx, ky, ks = "portrait_x", "portrait_y", "portrait_size"
    elif media_id == pr.get("media2"):
        kx, ky, ks = "pic2_x", "pic2_y", "pic2_size"
    else:
        return arr, None
    h, w = arr.shape[:2]
    fx = float(pr.get(kx, 0.5))
    fy = float(pr.get(ky, 0.5))
    fs = float(pr.get(ks, 1.0))
    if fs >= 0.999 and abs(fx - 0.5) < 1e-3 and abs(fy - 0.5) < 1e-3:
        return arr, None
    side = max(8, min(w, h, int(fs * h)))
    x0 = int(max(0, min(w - side, fx * w - side / 2)))
    y0 = int(max(0, min(h - side, fy * h - side / 2)))
    return arr[y0:y0 + side, x0:x0 + side], (x0, y0, side)


def picture(c, media_id, cut=False):
    """{'img': QImage (cut out if asked), 'mask': float mask or None, 'sil': {}} or None."""
    if c.pool is None or not media_id:
        return None
    arr = c.pool.image(media_id)
    if arr is None:
        return None
    arr, box = _crop(c, arr, media_id)
    key = (media_id, box, bool(cut))
    info = _PIC_CACHE.get(key)
    if info is not None:
        return info
    rgba = np.ascontiguousarray(arr if arr.shape[2] == 4 else np.dstack([arr, np.full(arr.shape[:2], 255, np.uint8)]))
    mask = None
    if cut:
        mk = (media_id, box)
        mask = _MASK_CACHE.get(mk)
        if mask is None:
            mask = cut_out_mask(rgba)
            _MASK_CACHE[mk] = mask
        rgba = rgba.copy()
        rgba[..., 3] = (mask * 255).astype(np.uint8)
        ys, xs = np.nonzero(mask > 0.15)
        if len(xs):                              # trim to the person so they fill the space
            hh, ww = mask.shape
            pad = int(0.04 * max(hh, ww))
            x0, x1 = max(0, xs.min() - pad), min(ww, xs.max() + pad + 1)
            y0, y1 = max(0, ys.min() - pad), min(hh, ys.max() + pad + 1)
            rgba = np.ascontiguousarray(rgba[y0:y1, x0:x1])
            mask = np.ascontiguousarray(mask[y0:y1, x0:x1])
    h, w = rgba.shape[:2]
    img = QImage(rgba.data, w, h, w * 4, QImage.Format.Format_RGBA8888).copy()
    info = {"img": img, "mask": mask if mask is not None else rgba[..., 3].astype(np.float32) / 255.0, "sil": {}}
    if len(_PIC_CACHE) > 24:
        _PIC_CACHE.clear()
    _PIC_CACHE[key] = info
    return info


def silhouette(info, color):
    img = info["sil"].get(color)
    if img is None:
        m = info["mask"]
        h, w = m.shape
        q = QColor(color)
        out = np.empty((h, w, 4), np.uint8)
        out[..., 0], out[..., 1], out[..., 2] = q.red(), q.green(), q.blue()
        out[..., 3] = (np.clip(m, 0, 1) * 255).astype(np.uint8)
        img = QImage(out.data, w, h, w * 4, QImage.Format.Format_RGBA8888).copy()
        info["sil"][color] = img
    return img


def fit_rect(img, box):
    """Rectangle inside `box` with the picture's shape, centred."""
    iw, ih = max(1, img.width()), max(1, img.height())
    k = min(box.width() / iw, box.height() / ih)
    w, h = iw * k, ih * k
    return QRectF(box.center().x() - w / 2, box.center().y() - h / 2, w, h)


def draw_pic(p, img, box, alpha=1.0, scale=1.0):
    r = fit_rect(img, box)
    if scale != 1.0:
        cx, cy = r.center().x(), r.center().y()
        r = QRectF(cx - r.width() * scale / 2, cy - r.height() * scale / 2, r.width() * scale, r.height() * scale)
    p.save()
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    p.setOpacity(p.opacity() * alpha)
    p.drawImage(r, img)
    p.restore()
    return r


def placeholder(p, box, s, color="#202040", alpha=1.0):
    """A plain figure shown until a picture is chosen."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_c(color, alpha))
    cx, top, h = box.center().x(), box.top(), box.height()
    p.drawEllipse(QPointF(cx, top + h * 0.25), h * 0.16, h * 0.16)
    path = QPainterPath()
    path.addRoundedRect(QRectF(cx - h * 0.25, top + h * 0.44, h * 0.5, h * 0.52), h * 0.18, h * 0.18)
    p.drawPath(path)
    p.restore()


def msg_box(p, c, text, since, cps=32.0):
    """Creature-battle style message box along the bottom, typed out."""
    s = c.s
    W, H = c.W, c.H
    r = QRectF(W * 0.05, H - 236 * s, W * 0.9, 200 * s)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(QPen(QColor("#384850"), 10 * s))
    p.setBrush(QColor("#f8f8f8"))
    p.drawRoundedRect(r, 18 * s, 18 * s)
    p.setPen(QPen(QColor("#68a0c0"), 5 * s))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(r.adjusted(9 * s, 9 * s, -9 * s, -9 * s), 12 * s, 12 * s)
    p.restore()
    shown = int(max(0.0, since) * cps) if cps > 0 else len(text)
    for i, ln in enumerate(wrap(text, "round", 40 * s, r.width() - 120 * s, bold=True)[:2]):
        T(p, ln[:max(0, shown)], r.left() + 50 * s, r.top() + 40 * s + i * 62 * s, "round", 40 * s, "#404040",
          bold=True, shadow="#d0d0d0", sd=3 * s)
        shown -= len(ln) + 1
    return r


def sparkles(p, cx, cy, radius, t, s, n=18, color="#ffffff", seed=3, alpha=1.0):
    rnd = random.Random(seed)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(n):
        a0 = rnd.random() * 2 * math.pi
        sp = rnd.uniform(0.4, 1.0)
        ph = (t * sp + rnd.random()) % 1.0
        d = radius * (0.35 + 0.75 * ph)
        x, y = cx + math.cos(a0) * d, cy + math.sin(a0) * d - 60 * s * ph
        k = (1 - ph) * alpha
        size = rnd.uniform(6, 14) * s * (0.6 + 0.4 * math.sin(t * 9 + i))
        p.setBrush(_c(color, k))
        star = QPolygonF([QPointF(x, y - size), QPointF(x + size * 0.25, y - size * 0.25), QPointF(x + size, y),
                          QPointF(x + size * 0.25, y + size * 0.25), QPointF(x, y + size),
                          QPointF(x - size * 0.25, y + size * 0.25), QPointF(x - size, y),
                          QPointF(x - size * 0.25, y - size * 0.25)])
        p.drawPolygon(star)
    p.restore()


# ------------------------------------------------------------------ "Who's that …?"
def rays(p, W, H, cx, cy, t, inner="#4f9bff", outer="#0b2a74", ray="#7fc0ff", n=22):
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    g = QRadialGradient(cx, cy, max(W, H) * 0.8)
    g.setColorAt(0, QColor(inner))
    g.setColorAt(1, QColor(outer))
    p.fillRect(QRectF(0, 0, W, H), QBrush(g))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_c(ray, 0.35))
    R = max(W, H) * 1.5
    rot = t * 0.25
    for i in range(n):
        a = rot + i * 2 * math.pi / n
        da = math.pi / n * 0.55
        p.drawPolygon(QPolygonF([QPointF(cx, cy), QPointF(cx + R * math.cos(a - da), cy + R * math.sin(a - da)),
                                 QPointF(cx + R * math.cos(a + da), cy + R * math.sin(a + da))]))
    p.restore()


def pk_whos(p, c):
    s = c.base_s
    W, H, t = c.W, c.H, c.t
    rv = float(c.val("reveal_time", 4.0))
    revealed = t >= rv
    px, py = W * float(c.val("pic_x", 0.32)), H * float(c.val("pic_y", 0.5))
    if c.text("background", "rays") == "rays":
        rays(p, W, H, px, py, t)
    size = H * float(c.val("pic_size", 0.78))
    slide = ease_out_back(min(1.0, t / 0.5))
    box = QRectF(px - size / 2 - (1 - slide) * W * 0.6, py - size / 2, size, size)
    info = picture(c, c.clip.media_id, cut=c.text("cutout", "auto") == "auto")
    shadow = picture(c, c.clip.props.get("shadow_media"), cut=False)
    if not revealed:
        if shadow is not None:
            draw_pic(p, shadow["img"], box)
        elif info is not None:
            draw_pic(p, silhouette(info, c.text("shadow_color", "#0d0d26")), box)
        else:
            placeholder(p, box, s, c.text("shadow_color", "#0d0d26"))
    else:
        pop = 1 + 0.12 * max(0.0, 1 - (t - rv) / 0.35)
        if info is not None:
            draw_pic(p, info["img"], box, scale=pop)
        else:
            placeholder(p, box, s, "#e8a040")
        sparkles(p, box.center().x(), box.center().y(), size * 0.55, t - rv, s, 16, "#fff6b0", alpha=0.9)
    tx = W * float(c.val("text_x", 0.7))
    if not revealed:
        q = c.text("question", "Who's that NPC?")
        k = min(1.0, max(0.0, (t - 0.35) / 0.3))
        wob = 1 + 0.03 * math.sin(t * 5)
        lines = wrap(q, "round", 110 * s, W * 0.5, bold=True)[:3]
        for i, ln in enumerate(lines):
            y = H * 0.5 + (i - (len(lines) - 1) / 2) * 125 * s
            p.save()
            p.translate(tx, y)
            p.scale(wob * (0.4 + 0.6 * ease_out_back(k)), wob * (0.4 + 0.6 * ease_out_back(k)))
            T(p, ln, 0, 0, "round", 110 * s, "#ffd23a", "center", "middle", bold=True, outline="#1d4fa0",
              ow=12 * s, alpha=k)
            p.restore()
    else:
        a = c.text("answer", "It's {name}!").replace("{name}", c.text("name", "PROFESSOR GRID"))
        k = min(1.0, (t - rv) / 0.3)
        lines = wrap(a, "round", 110 * s, W * 0.5, bold=True)[:3]
        for i, ln in enumerate(lines):
            y = H * 0.5 + (i - (len(lines) - 1) / 2) * 125 * s
            p.save()
            p.translate(tx, y)
            p.scale(0.5 + 0.5 * ease_out_back(k), 0.5 + 0.5 * ease_out_back(k))
            T(p, ln, 0, 0, "round", 110 * s, "#ffd23a", "center", "middle", bold=True, outline="#1d4fa0", ow=12 * s)
            p.restore()
        fl = max(0.0, 1 - (t - rv) / 0.35)
        if fl > 0:
            p.fillRect(QRectF(0, 0, W, H), _c("#ffffff", fl))
    return QRectF(0, 0, W, H)


# ------------------------------------------------------------------ creature index entry
TYPE_COLORS = {"normal": "#a8a878", "fire": "#f08030", "water": "#6890f0", "grass": "#78c850", "electric": "#f8d030",
               "ice": "#98d8d8", "fighting": "#c03028", "poison": "#a040a0", "ground": "#e0c068",
               "flying": "#a890f0", "psychic": "#f85888", "bug": "#a8b820", "rock": "#b8a038", "ghost": "#705898",
               "dragon": "#7038f8", "dark": "#705848", "steel": "#b8b8d0", "fairy": "#ee99ac", "coffee": "#7a4a2a",
               "science": "#2fa8a0", "none": ""}


def _pill(p, x, y, text, color, s):
    w = 150 * s
    r = QRectF(x, y, w, 44 * s)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(QPen(QColor(color).darker(140), 3 * s))
    p.setBrush(QColor(color))
    p.drawRoundedRect(r, 22 * s, 22 * s)
    p.restore()
    T(p, text.upper(), r.center().x(), r.center().y(), "round", 24 * s, "#ffffff", "center", "middle", bold=True,
      outline=QColor(color).darker(160).name(), ow=3 * s)
    return w + 14 * s


def pk_dex(p, c):
    s = c.s
    cx, cy = c.X(), c.Y()
    w, h = 1560 * s, 830 * s
    r = QRectF(cx - w / 2, cy - h / 2, w, h)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    g = QLinearGradient(0, r.top(), 0, r.bottom())
    g.setColorAt(0, QColor("#e2424b"))
    g.setColorAt(1, QColor("#a8202a"))
    p.setPen(QPen(QColor("#3a0a0e"), 8 * s))
    p.setBrush(QBrush(g))
    p.drawRoundedRect(r, 44 * s, 44 * s)
    # hinge line and lens
    p.setPen(QPen(QColor("#6a1218"), 5 * s))
    p.drawLine(QPointF(r.left() + 30 * s, r.top() + 118 * s), QPointF(r.right() - 30 * s, r.top() + 118 * s))
    lx, ly = r.left() + 80 * s, r.top() + 60 * s
    p.setPen(QPen(QColor("#ffffff"), 6 * s))
    lg = QRadialGradient(lx - 10 * s, ly - 10 * s, 40 * s)
    lg.setColorAt(0, QColor("#bfe8ff"))
    lg.setColorAt(1, QColor("#1a78d0"))
    p.setBrush(QBrush(lg))
    p.drawEllipse(QPointF(lx, ly), 36 * s, 36 * s)
    p.setPen(QPen(QColor("#3a0a0e"), 2 * s))
    for i, col in enumerate(("#ff4040", "#ffd040", "#40d060")):
        on = int(c.t * 4 + i) % 3 != 0
        p.setBrush(QColor(col) if on else QColor(col).darker(200))
        p.drawEllipse(QPointF(lx + (75 + i * 34) * s, ly - 14 * s), 10 * s, 10 * s)
    # picture screen
    scr = QRectF(r.left() + 60 * s, r.top() + 150 * s, 640 * s, 460 * s)
    p.setPen(QPen(QColor("#4a4a52"), 4 * s))
    p.setBrush(QColor("#dcdce4"))
    p.drawRoundedRect(scr, 20 * s, 20 * s)
    inner = scr.adjusted(26 * s, 26 * s, -26 * s, -26 * s)
    sg = QLinearGradient(0, inner.top(), 0, inner.bottom())
    sg.setColorAt(0, QColor("#d6f2e4"))
    sg.setColorAt(1, QColor("#8fc7b0"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(sg))
    p.drawRect(inner)
    p.setPen(QPen(_c("#5aa088", 0.35), 1.5 * s))
    step = 32 * s
    x = inner.left()
    while x < inner.right():
        p.drawLine(QPointF(x, inner.top()), QPointF(x, inner.bottom()))
        x += step
    y = inner.top()
    while y < inner.bottom():
        p.drawLine(QPointF(inner.left(), y), QPointF(inner.right(), y))
        y += step
    p.restore()
    info = picture(c, c.clip.media_id, cut=c.text("cutout", "none") == "auto")
    scan = min(1.0, c.t / 1.2)
    p.save()
    p.setClipRect(QRectF(inner.left(), inner.top(), inner.width(), inner.height() * scan))
    if info is not None:
        draw_pic(p, info["img"], inner.adjusted(10 * s, 10 * s, -10 * s, -10 * s))
    else:
        placeholder(p, inner.adjusted(40 * s, 30 * s, -40 * s, -10 * s), s, "#2a5a48")
    p.restore()
    if scan < 1.0:
        yy = inner.top() + inner.height() * scan
        p.fillRect(QRectF(inner.left(), yy - 3 * s, inner.width(), 6 * s), _c("#ffffff", 0.9))
    # data panel
    dp = QRectF(r.left() + 740 * s, r.top() + 150 * s, 760 * s, 460 * s)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(QPen(QColor("#4a4a52"), 4 * s))
    p.setBrush(QColor("#f4f4f0"))
    p.drawRoundedRect(dp, 20 * s, 20 * s)
    p.restore()
    x0 = dp.left() + 36 * s
    T(p, f"No. {c.text('number', '042')}", x0, dp.top() + 52 * s, "round", 30 * s, "#808088", "left", "middle",
      bold=True)
    T(p, c.text("name", "PROFESSOR GRID").upper(), x0, dp.top() + 110 * s, "round", 54 * s, "#202028", "left",
      "middle", bold=True)
    T(p, c.text("species", "The Cryo-EM Creature"), x0, dp.top() + 168 * s, "round", 32 * s, "#505058", "left",
      "middle")
    xx = x0
    for k in ("type1", "type2"):
        ty = c.text(k, "none")
        if ty and ty != "none":
            xx += _pill(p, xx, dp.top() + 210 * s, ty, TYPE_COLORS.get(ty, "#888888"), s)
    p.save()
    p.setPen(QPen(QColor("#c8c8cc"), 2 * s))
    p.drawLine(QPointF(x0, dp.top() + 290 * s), QPointF(dp.right() - 36 * s, dp.top() + 290 * s))
    p.restore()
    for i, (lab, key, dflt) in enumerate((("HT", "height", "1.78 m"), ("WT", "weight", "70.0 kg"))):
        y = dp.top() + 340 * s + i * 62 * s
        T(p, lab, x0, y, "round", 32 * s, "#c03030", "left", "middle", bold=True)
        T(p, c.text(key, dflt), x0 + 90 * s, y, "round", 34 * s, "#202028", "left", "middle", bold=True)
    # description
    db = QRectF(r.left() + 60 * s, r.top() + 640 * s, w - 120 * s, 150 * s)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(QPen(QColor("#4a4a52"), 4 * s))
    p.setBrush(QColor("#22323c"))
    p.drawRoundedRect(db, 16 * s, 16 * s)
    p.restore()
    text = c.text("text")
    cps = float(c.val("cps", 35))
    shown = len(text) if cps <= 0 else int(max(0.0, c.t - 1.2) * cps)
    for i, ln in enumerate(wrap(text, "round", 30 * s, db.width() - 60 * s)[:3]):
        T(p, ln[:max(0, shown)], db.left() + 30 * s, db.top() + 22 * s + i * 40 * s, "round", 30 * s, "#e8f4ff")
        shown -= len(ln) + 1
    return r.adjusted(-8, -8, 8, 8)


# ------------------------------------------------------------------ evolution
def pk_evolve(p, c):
    s = c.base_s
    W, H, t = c.W, c.H, c.t
    m0 = float(c.val("morph_start", 2.0))
    m1 = float(c.val("evolve_time", 7.0))
    stopped = c.text("result", "evolves") == "stops"
    name_a = c.text("name", "PHD STUDENT")
    name_b = c.text("name2", "DOCTOR")
    cx, cy = W / 2, H * 0.42
    if c.text("background", "glow") == "glow":
        p.save()
        g = QRadialGradient(cx, cy, max(W, H) * 0.7)
        g.setColorAt(0, QColor("#40507a"))
        g.setColorAt(1, QColor("#0a0e1c"))
        p.fillRect(QRectF(0, 0, W, H), QBrush(g))
        p.restore()
    size = H * float(c.val("pic_size", 0.6))
    box = QRectF(cx - size / 2, cy - size / 2, size, size)
    cut = c.text("cutout", "auto") == "auto"
    a = picture(c, c.clip.media_id, cut=cut)
    b = picture(c, c.clip.props.get("media2"), cut=cut)

    def show(info, white=0.0, glow=0.0, fallback="#e8a040"):
        if glow > 0 and info is not None:
            sil = silhouette(info, "#ffffff")
            for k in (1.10, 1.05):
                draw_pic(p, sil, box, alpha=glow * 0.35, scale=k)
        if info is None:
            placeholder(p, box, s, "#ffffff" if white > 0.5 else fallback)
            return
        draw_pic(p, info["img"], box)
        if white > 0:
            draw_pic(p, silhouette(info, "#ffffff"), box, alpha=white)

    end = m1 if not stopped else m1 - 0.6
    if t < m0:
        show(a)
    elif t < end:
        d = max(0.1, m1 - m0)
        tp = t - m0
        phase = 2 * math.pi * (1.2 * tp + 12 * tp ** 3 / (3 * d * d))
        white = min(1.0, tp / 0.6)
        glow = min(1.0, tp / 1.0)
        show(b if (math.sin(phase) < 0 and not stopped) or (stopped and math.sin(phase) < 0 and tp > d * 0.5)
             else a, white, glow)
        sparkles(p, cx, cy, size * 0.6, tp * 0.7, s, 22, "#cfe8ff", seed=8, alpha=glow)
    else:
        since = t - end
        if stopped:
            show(a, max(0.0, 1 - since / 0.4))
        else:
            show(b if b is not None else a, max(0.0, 1 - since / 0.6))
            sparkles(p, cx, cy, size * 0.6, since, s, 16, "#fff6b0", seed=5, alpha=max(0.0, 1 - since / 2.5))
        fl = max(0.0, 1 - since / 0.4) if not stopped else 0.0
        if fl > 0:
            p.fillRect(QRectF(0, 0, W, H), _c("#ffffff", fl))
    if t < end:
        msg_box(p, c, c.text("text", "What? {name} is evolving!").replace("{name}", name_a), t - 0.2)
    elif stopped:
        msg_box(p, c, c.text("text_stop", "Huh? {name} stopped evolving!").replace("{name}", name_a), t - end - 0.3)
    else:
        msg = c.text("text_done", "Congratulations! Your {name} evolved into {name2}!")
        msg_box(p, c, msg.replace("{name2}", name_b).replace("{name}", name_a), t - end - 0.5)
    return QRectF(0, 0, W, H)


# ------------------------------------------------------------------ badge
BADGE_SHAPES = ["star", "drop", "hexagon", "bolt", "shield", "octagon", "leaf"]


def _badge_poly(shape, cx, cy, R):
    pts = []
    if shape == "star":
        for i in range(10):
            a = -math.pi / 2 + i * math.pi / 5
            rr = R if i % 2 == 0 else R * 0.48
            pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    elif shape in ("hexagon", "octagon"):
        n = 6 if shape == "hexagon" else 8
        for i in range(n):
            a = -math.pi / 2 + i * 2 * math.pi / n + (math.pi / n if n == 8 else 0)
            pts.append((cx + R * math.cos(a), cy + R * math.sin(a)))
    elif shape == "drop":
        for i in range(40):
            a = i / 40 * 2 * math.pi
            k = 1 - 0.55 * max(0.0, -math.sin(a)) ** 3
            pts.append((cx + R * 0.8 * math.cos(a) * k, cy - R * 0.15 + R * 0.85 * math.sin(a) * (1.25 if math.sin(a) < 0 else 1)))
    elif shape == "bolt":
        for x, y in ((0.15, -1), (-0.55, 0.12), (-0.05, 0.12), (-0.25, 1), (0.6, -0.2), (0.08, -0.2), (0.4, -1)):
            pts.append((cx + x * R, cy + y * R))
    elif shape == "shield":
        for x, y in ((-0.8, -0.85), (0.8, -0.85), (0.8, 0.05), (0.0, 1.0), (-0.8, 0.05)):
            pts.append((cx + x * R, cy + y * R))
    else:   # leaf
        for i in range(40):
            a = i / 40 * 2 * math.pi
            pts.append((cx + R * 0.55 * math.sin(a) * abs(math.sin(a)) ** 0.2,
                        cy - R * math.cos(a)))
    return QPolygonF([QPointF(x, y) for x, y in pts])


def pk_badge(p, c):
    s = c.base_s
    W, H, t = c.W, c.H, c.t
    cx, cy = W * float(c.val("x", 0.5)), H * 0.4
    R = 170 * s * ease_out_back(min(1.0, t / 0.45))
    col = QColor(c.text("color", "#d0a030"))
    poly = _badge_poly(c.text("shape", "star"), cx, cy, R)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    glow = QRadialGradient(cx, cy, R * 1.8)
    glow.setColorAt(0, _c("#fff2b0", 0.55))
    glow.setColorAt(1, _c("#fff2b0", 0.0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(glow))
    p.drawEllipse(QPointF(cx, cy), R * 1.8, R * 1.8)
    g = QLinearGradient(cx - R, cy - R, cx + R, cy + R)
    g.setColorAt(0, col.lighter(170))
    g.setColorAt(0.45, col)
    g.setColorAt(1, col.darker(170))
    p.setPen(QPen(col.darker(250), 8 * s))
    p.setBrush(QBrush(g))
    p.drawPolygon(poly)
    # moving shine
    path = QPainterPath()
    path.addPolygon(poly)
    p.setClipPath(path)
    sx = cx - 2 * R + ((t * 0.8) % 1.6) * 3 * R
    sh = QLinearGradient(sx - 40 * s, 0, sx + 40 * s, 0)
    sh.setColorAt(0, _c("#ffffff", 0))
    sh.setColorAt(0.5, _c("#ffffff", 0.75))
    sh.setColorAt(1, _c("#ffffff", 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(sh))
    p.drawRect(QRectF(cx - 2 * R, cy - 2 * R, 4 * R, 4 * R))
    p.restore()
    sparkles(p, cx, cy, R * 1.2, t * 0.6, s, 12, "#fffbe0", seed=11)
    msg = c.text("text", "{player} received the {badge}!")
    msg_box(p, c, msg.replace("{player}", c.text("player", "ALOK")).replace("{badge}", c.text("badge", "Thesis Badge")),
            t - 0.5)
    return QRectF(0, 0, W, H)


# ------------------------------------------------------------------ catalogue
_PIC_P = [("cutout", "Cut the person out of the picture", "choice", ["auto", "none"]),
          ("portrait_size", "Picture zoom (smaller = closer)", "float", 0.05, 1.0, 0.01)]
_PIC_D = {"portrait_x": 0.5, "portrait_y": 0.5, "portrait_size": 1.0}

NEW = {
    "pk_whos": ("Who's that …? guess sequence (Pokémon 'Who's that Pokémon?')", G_PK, 8.0, pk_whos,
                {**_PIC_D, "name": "PROFESSOR GRID", "question": "Who's that NPC?", "answer": "It's {name}!",
                 "reveal_time": 4.0, "background": "rays", "cutout": "auto", "shadow_color": "#0d0d26",
                 "shadow_media": "", "pic_x": 0.32, "pic_y": 0.5, "pic_size": 0.78, "text_x": 0.7,
                 "anim_in": "none", "anim_out": "none"},
                [("name", "Name", "text"), ("question", "Question", "text"),
                 ("answer", "Answer ({name} = the name)", "text"),
                 ("reveal_time", "Reveal after (s)", "float", 0.5, 60.0, 0.1),
                 ("background", "Background", "choice", ["rays", "none"]),
                 ("shadow_color", "Silhouette colour", "color"),
                 ("shadow_media", "Own shadow picture (optional)", "image"),
                 *_PIC_P, ("pic_x", "Picture left/right", "float", 0.0, 1.0, 0.005),
                 ("pic_y", "Picture up/down", "float", 0.0, 1.0, 0.005),
                 ("pic_size", "Picture size", "float", 0.1, 1.5, 0.01),
                 ("text_x", "Text left/right", "float", 0.0, 1.0, 0.005)]),
    "pk_dex": ("Creature index entry (Pokédex entry)", G_PK, 9.0, pk_dex,
               {**_PIC_D, "number": "042", "name": "PROFESSOR GRID", "species": "The Cryo-EM Creature",
                "type1": "science", "type2": "coffee", "height": "1.78 m", "weight": "70.0 kg",
                "text": "It lives in the cold room. When a grid cracks, it lets out a cry that can be heard "
                        "three floors up. Powered entirely by espresso.",
                "cps": 35.0, "cutout": "none", "x": 0.5, "y": 0.47, "anim_in": "pop", "anim_dur": 0.35,
                "anim_out": "fade"},
               [("number", "Number", "text"), ("name", "Name", "text"), ("species", "Kind (The … Creature)", "text"),
                ("type1", "Type 1", "choice", list(TYPE_COLORS)), ("type2", "Type 2", "choice", list(TYPE_COLORS)),
                ("height", "Height", "text"), ("weight", "Weight", "text"), ("text", "Description", "longtext"),
                ("cps", "Typing speed (letters/s)", "float", 0.0, 200.0, 1.0), *_PIC_P]),
    "pk_evolve": ("Evolution sequence (Pokémon evolution)", G_PK, 11.0, pk_evolve,
                  {**_PIC_D, "name": "PHD STUDENT", "name2": "DOCTOR", "media2": "", "pic2_x": 0.5, "pic2_y": 0.5,
                   "pic2_size": 1.0, "result": "evolves",
                   "morph_start": 2.0, "evolve_time": 7.0, "text": "What? {name} is evolving!",
                   "text_done": "Congratulations! Your {name} evolved into {name2}!",
                   "text_stop": "Huh? {name} stopped evolving!", "background": "glow", "cutout": "auto",
                   "pic_size": 0.6, "anim_in": "none", "anim_out": "fade"},
                  [("name", "Before: name", "text"), ("name2", "After: name", "text"),
                   ("media2", "After: picture", "image"),
                   ("pic2_size", "After: picture zoom (smaller = closer)", "float", 0.05, 1.0, 0.01),
                   ("result", "Ending", "choice", ["evolves", "stops"]),
                   ("morph_start", "Flashing starts at (s)", "float", 0.0, 60.0, 0.1),
                   ("evolve_time", "Changes at (s)", "float", 0.5, 60.0, 0.1),
                   ("text", "First message", "text"), ("text_done", "Message after", "text"),
                   ("text_stop", "Message if it stops", "text"),
                   ("background", "Background", "choice", ["glow", "none"]), *_PIC_P,
                   ("pic_size", "Picture size", "float", 0.1, 1.2, 0.01)]),
    "pk_badge": ("Badge received (Pokémon gym badge)", G_PK, 5.0, pk_badge,
                 {"player": "ALOK", "badge": "Thesis Badge", "shape": "star", "color": "#d0a030",
                  "text": "{player} received the {badge}!", "x": 0.5, "anim_in": "none", "anim_out": "fade"},
                 [("player", "Who receives it", "text"), ("badge", "Badge name", "text"),
                  ("shape", "Shape", "choice", BADGE_SHAPES), ("color", "Colour", "color"),
                  ("text", "Message", "text")]),
}

SKINS.update(NEW)
for _key, (_label, _group, _dur, _fn, _defaults, _params) in NEW.items():
    HUD_TYPES[_key] = {"label": _label, "group": _group, "duration": _dur, "defaults": dict(_defaults),
                       "params": list(_params), "skin": True}
    DRAWERS[_key] = _fn
PORTRAIT_TYPES.update({"pk_whos", "pk_dex", "pk_evolve"})
FULLSCREEN_TYPES.update({"pk_whos", "pk_evolve", "pk_badge"})
PORTRAIT_TITLES = {"pk_whos": "Picture to guess", "pk_dex": "Picture", "pk_evolve": "Before: picture"}
