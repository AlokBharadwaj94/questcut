"""Video-game HUD elements drawn on top of the video.

Every element supports three looks: "retro" (8-bit pixel), "rpg" (fantasy
role-playing game) and "fps" (sci-fi shooter), so they can be mixed freely.
Positions are fractions of the frame (0..1); sizes are in "design pixels"
for a 1080p frame and scale automatically with the export size.
"""
from __future__ import annotations

import math
import random

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QFont, QFontMetricsF, QImage, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPolygonF, QRadialGradient, QTransform)

from . import pixelfont

STYLES = ["retro", "rpg", "fps"]
STYLE_LABELS = {"retro": "Retro pixel", "rpg": "Fantasy RPG", "fps": "Shooter / sci-fi"}
ANIMS = ["none", "fade", "pop", "slide_left", "slide_right", "slide_up", "slide_down"]

# ------------------------------------------------------------------ catalogue
_COMMON = [
    ("style", "Look", "choice", STYLES),
    ("x", "Position X", "float", -0.2, 1.2, 0.005),
    ("y", "Position Y", "float", -0.2, 1.2, 0.005),
    ("scale", "Size", "float", 0.2, 4.0, 0.01),
    ("opacity", "Opacity", "float", 0.0, 1.0, 0.01),
    ("anim_in", "Appear", "choice", ANIMS),
    ("anim_out", "Disappear", "choice", ANIMS),
    ("anim_dur", "Appear time (s)", "float", 0.0, 2.0, 0.05),
]

HUD_TYPES = {
    "bar": {
        "label": "Health / mana / XP bar", "group": "Bars & numbers", "duration": 10.0,
        "defaults": {"bar_kind": "health", "label": "HP", "value": 80.0, "max_value": 100.0, "show_number": True,
                     "color": "", "width": 420.0, "x": 0.03, "y": 0.05, "style": "rpg"},
        "params": [("bar_kind", "Bar type", "choice", ["health", "mana", "xp", "stamina", "shield", "boss", "custom"]),
                   ("label", "Label / boss name", "text"),
                   ("value", "Value", "float", 0.0, 1000.0, 1.0),
                   ("max_value", "Maximum", "float", 1.0, 1000.0, 1.0),
                   ("show_number", "Show numbers", "bool"),
                   ("color", "Colour (empty = automatic)", "color"),
                   ("width", "Length", "float", 60.0, 1800.0, 5.0)],
    },
    "name_tag": {
        "label": "Name tag (NPC / player)", "group": "Characters", "duration": 5.0,
        "defaults": {"name": "NPC", "level": "Lv 12", "show_bar": False, "value": 100.0, "max_value": 100.0,
                     "color": "#ffd54a", "x": 0.5, "y": 0.25, "style": "rpg", "anim_in": "pop"},
        "params": [("name", "Name", "text"), ("level", "Level text", "text"),
                   ("show_bar", "Show small health bar", "bool"),
                   ("value", "Bar value", "float", 0.0, 1000.0, 1.0),
                   ("max_value", "Bar maximum", "float", 1.0, 1000.0, 1.0),
                   ("color", "Accent colour", "color")],
    },
    "dialogue": {
        "label": "Dialogue box", "group": "Characters", "duration": 6.0,
        "defaults": {"speaker": "Supervisor", "text": "Have you finished chapter three yet?", "cps": 28.0,
                     "width": 0.78, "x": 0.5, "y": 0.80, "style": "retro", "color": "#ffd54a"},
        "params": [("speaker", "Who is talking", "text"), ("text", "What they say", "longtext"),
                   ("cps", "Typing speed (letters/s)", "float", 0.0, 200.0, 1.0),
                   ("width", "Box width", "float", 0.2, 1.0, 0.01), ("color", "Name colour", "color")],
    },
    "quest": {
        "label": "Quest pop-up", "group": "Story", "duration": 5.0,
        "defaults": {"header": "NEW QUEST", "title": "The Final Chapter", "objective": "Submit the thesis",
                     "completed": False, "color": "#ffcc33", "x": 0.97, "y": 0.10, "style": "rpg",
                     "anim_in": "slide_left", "anim_out": "fade"},
        "params": [("header", "Header", "text"), ("title", "Quest name", "text"), ("objective", "Objective", "longtext"),
                   ("completed", "Completed (tick)", "bool"), ("color", "Accent colour", "color")],
    },
    "character_card": {
        "label": "Character intro card", "group": "Characters", "duration": 5.0,
        "defaults": {"header": "NEW CHALLENGER", "name": "The Supervisor", "title": "Keeper of Deadlines",
                     "level": "99", "lines": "Class: Professor\nHP: ∞\nWeakness: Unformatted references",
                     "color": "#ff5577", "side": "left", "x": 0.05, "y": 0.22, "style": "rpg",
                     "anim_in": "slide_right", "anim_out": "fade"},
        "params": [("header", "Header", "text"), ("name", "Name", "text"), ("title", "Title", "text"),
                   ("level", "Level", "text"), ("lines", "Stats (one per line)", "longtext"),
                   ("color", "Accent colour", "color")],
    },
    "spell": {
        "label": "Spell / attack event", "group": "Action", "duration": 2.6,
        "defaults": {"spell_name": "FIREBALL!", "color": "#ff7a1a", "caster_x": 0.28, "caster_y": 0.55,
                     "target_x": 0.72, "target_y": 0.50, "hit_time": 1.1, "damage": "", "damage_amount": 35.0,
                     "target_bar": "", "projectile": True,
                     "shake": 0.6, "flash": 0.55, "banner_y": 0.16, "style": "rpg", "x": 0.5, "y": 0.5},
        "params": [("spell_name", "Spell name", "text"), ("color", "Spell colour", "color"),
                   ("caster_x", "Caster X", "float", 0.0, 1.0, 0.005), ("caster_y", "Caster Y", "float", 0.0, 1.0, 0.005),
                   ("target_x", "Target X", "float", 0.0, 1.0, 0.005), ("target_y", "Target Y", "float", 0.0, 1.0, 0.005),
                   ("hit_time", "Hit moment (s after start)", "float", 0.1, 10.0, 0.05),
                   ("target_bar", "Health bar that drops", "target"),
                   ("damage_amount", "Damage amount", "float", 0.0, 1000.0, 1.0),
                   ("damage", "Damage text (empty = automatic)", "text"), ("projectile", "Flying orb", "bool"),
                   ("shake", "Screen shake", "float", 0.0, 1.5, 0.01), ("flash", "Screen flash", "float", 0.0, 1.0, 0.01),
                   ("banner_y", "Spell name height", "float", 0.0, 1.0, 0.01)],
    },
    "damage": {
        "label": "Damage number", "group": "Action", "duration": 1.2,
        "defaults": {"text": "-35", "color": "#ff4040", "critical": False, "x": 0.6, "y": 0.4, "style": "retro"},
        "params": [("text", "Text", "text"), ("color", "Colour", "color"), ("critical", "Critical hit", "bool")],
    },
    "level_up": {
        "label": "Level up!", "group": "Story", "duration": 3.0,
        "defaults": {"text": "LEVEL UP!", "subtext": "+1 Patience", "color": "#ffd23f", "x": 0.5, "y": 0.42,
                     "style": "rpg"},
        "params": [("text", "Text", "text"), ("subtext", "Small text", "text"), ("color", "Colour", "color")],
    },
    "text": {
        "label": "Text / title", "group": "Story", "duration": 4.0,
        "defaults": {"text": "CHAPTER 1", "size": 90.0, "color": "#ffffff", "outline": "#000000",
                     "outline_width": 6.0, "glow": False, "typewriter": False, "x": 0.5, "y": 0.5, "style": "rpg",
                     "anim_in": "fade", "anim_out": "fade"},
        "params": [("text", "Text", "longtext"), ("size", "Text size", "float", 10.0, 400.0, 1.0),
                   ("color", "Colour", "color"), ("outline", "Outline colour", "color"),
                   ("outline_width", "Outline width", "float", 0.0, 30.0, 0.5), ("glow", "Glow", "bool"),
                   ("typewriter", "Type letter by letter", "bool")],
    },
    "crosshair": {
        "label": "Crosshair", "group": "Shooter", "duration": 10.0,
        "defaults": {"variant": "cross", "color": "#7dfcff", "size": 60.0, "x": 0.5, "y": 0.5, "style": "fps"},
        "params": [("variant", "Shape", "choice", ["cross", "circle", "dot", "brackets"]),
                   ("color", "Colour", "color"), ("size", "Size", "float", 10.0, 400.0, 1.0)],
    },
    "ammo": {
        "label": "Ammo counter", "group": "Shooter", "duration": 10.0,
        "defaults": {"value": 30.0, "max_value": 90.0, "label": "AMMO", "weapon": "PIPETTE MK II",
                     "color": "#7dfcff", "x": 0.96, "y": 0.92, "style": "fps"},
        "params": [("value", "Rounds left", "float", 0.0, 999.0, 1.0), ("max_value", "Reserve", "float", 0.0, 999.0, 1.0),
                   ("label", "Label", "text"), ("weapon", "Weapon name", "text"), ("color", "Colour", "color")],
    },
    "score": {
        "label": "Score / coins", "group": "Bars & numbers", "duration": 10.0,
        "defaults": {"label": "COINS", "value": 0.0, "digits": 6, "icon": "coin", "color": "#ffd23f",
                     "x": 0.03, "y": 0.13, "style": "retro"},
        "params": [("label", "Label", "text"), ("value", "Value", "float", 0.0, 9999999.0, 1.0),
                   ("digits", "Digits (0 = no padding)", "int", 0, 9, 1),
                   ("icon", "Icon", "choice", ["coin", "star", "heart", "none"]), ("color", "Colour", "color")],
    },
    "timer": {
        "label": "Timer", "group": "Bars & numbers", "duration": 10.0,
        "defaults": {"label": "TIME", "start_seconds": 300.0, "count": "down", "color": "#ffffff",
                     "x": 0.5, "y": 0.04, "style": "retro"},
        "params": [("label", "Label", "text"), ("start_seconds", "Start at (s)", "float", 0.0, 36000.0, 1.0),
                   ("count", "Count", "choice", ["down", "up"]), ("color", "Colour", "color")],
    },
    "minimap": {
        "label": "Minimap / radar", "group": "Shooter", "duration": 10.0,
        "defaults": {"size": 240.0, "enemies": 3, "color": "#55ff99", "x": 0.88, "y": 0.2, "style": "fps"},
        "params": [("size", "Size", "float", 60.0, 800.0, 1.0), ("enemies", "Enemy dots", "int", 0, 20, 1),
                   ("color", "Colour", "color")],
    },
    "feed": {
        "label": "Kill feed / notifications", "group": "Shooter", "duration": 8.0,
        "defaults": {"lines": "Alok defeated Reviewer 2\nCoffee machine was restored\nPrinter has jammed",
                     "interval": 1.2, "hold": 4.0, "color": "#ff5566", "x": 0.97, "y": 0.06, "style": "fps"},
        "params": [("lines", "Messages (one per line)", "longtext"),
                   ("interval", "Seconds between messages", "float", 0.1, 10.0, 0.1),
                   ("hold", "Seconds each stays", "float", 0.5, 30.0, 0.1), ("color", "Highlight colour", "color")],
    },
    "prompt": {
        "label": "Button prompt", "group": "Story", "duration": 4.0,
        "defaults": {"button": "A", "text": "Talk", "color": "#3ddc84", "x": 0.5, "y": 0.86, "style": "fps"},
        "params": [("button", "Button letter", "text"), ("text", "Action", "text"), ("color", "Button colour", "color")],
    },
    "menu": {
        "label": "Pause menu", "group": "Story", "duration": 4.0,
        "defaults": {"title": "PAUSED", "items": "Resume\nOptions\nAsk supervisor\nQuit PhD", "selected": 0.0,
                     "dim": 0.55, "color": "#ffd54a", "x": 0.5, "y": 0.45, "style": "retro"},
        "params": [("title", "Title", "text"), ("items", "Menu items (one per line)", "longtext"),
                   ("selected", "Selected item (0 = first)", "float", 0.0, 20.0, 1.0),
                   ("dim", "Darken background", "float", 0.0, 1.0, 0.01), ("color", "Highlight colour", "color")],
    },
    "frame": {
        "label": "Screen frame (border)", "group": "Frames", "duration": 30.0,
        "defaults": {"variant": "rpg_ornate", "color": "#d8b45a", "label_left": "PLAYER 1", "label_right": "",
                     "thickness": 1.0, "x": 0.5, "y": 0.5, "style": "rpg"},
        "params": [("variant", "Frame design", "choice", ["rpg_ornate", "retro_tv", "fps_visor", "arcade", "minimal"]),
                   ("color", "Colour", "color"), ("label_left", "Left label", "text"),
                   ("label_right", "Right label", "text"), ("thickness", "Thickness", "float", 0.2, 3.0, 0.01)],
    },
    "sticker": {
        "label": "Image / sticker", "group": "Frames", "duration": 4.0,
        "defaults": {"rotation": 0.0, "x": 0.5, "y": 0.5, "scale": 1.0, "style": "rpg", "anim_in": "pop"},
        "params": [("rotation", "Rotation (°)", "float", -360.0, 360.0, 1.0)],
    },
}

GROUP_ORDER = ["Bars & numbers", "Characters", "Action", "Story", "Shooter", "Frames"]
BAR_TYPES = {"bar", "name_tag"}               # elements that spells can damage (they have a 'value')
FULLSCREEN_TYPES = {"frame", "menu", "spell"}  # no position dot in the preview
PORTRAIT_TYPES = set()                         # dialogue boxes that show a face picture


def hud_params(hud_type: str):
    spec = HUD_TYPES.get(hud_type, {})
    return list(spec.get("params", [])) + _COMMON


def hud_defaults(hud_type: str) -> dict:
    base = {"style": "rpg", "x": 0.5, "y": 0.5, "scale": 1.0, "opacity": 1.0,
            "anim_in": "fade", "anim_out": "fade", "anim_dur": 0.3}
    base.update(HUD_TYPES.get(hud_type, {}).get("defaults", {}))
    return dict(base)


BAR_COLORS = {"health": "#e8343a", "mana": "#3a7bff", "xp": "#f5c542", "stamina": "#3ad16b",
              "shield": "#5ad1ff", "boss": "#c21f4a", "custom": "#e8343a"}


# ------------------------------------------------------------------ helpers
def qc(hexstr: str, alpha: float = 1.0) -> QColor:
    c = QColor(hexstr if hexstr else "#ffffff")
    if not c.isValid():
        c = QColor("#ffffff")
    c.setAlphaF(max(0.0, min(1.0, alpha)) * c.alphaF())
    return c


def lighter(hexstr, f=1.4):
    return QColor(hexstr or "#ffffff").lighter(int(f * 100))


def darker(hexstr, f=2.0):
    return QColor(hexstr or "#000000").darker(int(f * 100))


def font_for(style: str, px: float, bold: bool = True, italic: bool = False) -> QFont:
    f = QFont()
    if style == "fps":
        f.setFamilies(["Bahnschrift", "Rajdhani", "Orbitron", "DIN Alternate", "Consolas", "Menlo",
                       "DejaVu Sans Mono", "Liberation Mono", "Courier New", "monospace"])
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 108)
    elif style == "rpg":
        f.setFamilies(["Cinzel", "Trajan Pro", "Palatino Linotype", "Book Antiqua", "Palatino", "Georgia",
                       "DejaVu Serif", "Liberation Serif", "Times New Roman", "serif"])
    else:
        f.setFamilies(["Arial Black", "Helvetica Neue", "Arial", "DejaVu Sans", "sans-serif"])
    f.setPixelSize(max(1, int(px)))
    f.setBold(bold)
    f.setItalic(italic)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


_PIX_CACHE: dict = {}


def _pixel_image(text: str, color: QColor) -> QImage:
    key = (text, color.rgba())
    img = _PIX_CACHE.get(key)
    if img is None:
        m = pixelfont.text_mask(text)
        h, w = m.shape
        arr = np.zeros((h, w, 4), dtype=np.uint8)
        a = color.alpha()
        # premultiplied BGRA
        arr[m] = (color.blue() * a // 255, color.green() * a // 255, color.red() * a // 255, a)
        img = QImage(arr.data, w, h, w * 4, QImage.Format.Format_ARGB32_Premultiplied).copy()
        if len(_PIX_CACHE) > 400:
            _PIX_CACHE.clear()
        _PIX_CACHE[key] = img
    return img


def pixel_text(p: QPainter, text: str, x: float, y: float, px: float, color: QColor,
               align: str = "left", valign: str = "top", shadow: QColor | None = None) -> QRectF:
    """Draw text with the built-in pixel font. px = size of one font pixel."""
    px = max(1, int(round(px)))
    w = pixelfont.text_width(text) * px
    h = pixelfont.GH * px
    if align == "center":
        x -= w / 2
    elif align == "right":
        x -= w
    if valign == "middle":
        y -= h / 2
    elif valign == "bottom":
        y -= h
    x, y = int(round(x)), int(round(y))
    p.save()
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
    if shadow is not None:
        p.drawImage(QRectF(x + px, y + px, w, h), _pixel_image(text, shadow))
    p.drawImage(QRectF(x, y, w, h), _pixel_image(text, color))
    p.restore()
    return QRectF(x, y, w + px, h + px)


def text_size(text: str, style: str, size: float) -> tuple:
    if style == "retro":
        px = max(1, int(round(size / 7)))
        return pixelfont.text_width(text) * px, 7 * px
    fm = QFontMetricsF(font_for(style, size))
    return fm.horizontalAdvance(text), fm.ascent() + fm.descent()


def draw_text(p: QPainter, text: str, x: float, y: float, style: str, size: float, color,
              align="left", valign="top", outline=None, outline_w=0.0, glow=None, glow_r=0.0,
              bold=True, italic=False) -> QRectF:
    """Draw one line of text. size = text height in pixels."""
    if not text:
        return QRectF(x, y, 0, 0)
    if not isinstance(color, QColor):
        color = qc(color)
    if style == "retro":
        px = max(1, int(round(size / 7)))
        sh = None
        if outline is not None and outline_w > 0:
            sh = outline if isinstance(outline, QColor) else qc(outline)
        return pixel_text(p, text, x, y, px, color, align, valign, sh)
    f = font_for(style, size, bold, italic)
    fm = QFontMetricsF(f)
    w = fm.horizontalAdvance(text)
    asc, desc = fm.ascent(), fm.descent()
    h = asc + desc
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
    if glow is not None and glow_r > 0:
        gc = glow if isinstance(glow, QColor) else qc(glow)
        for i in range(5, 0, -1):
            c = QColor(gc)
            c.setAlphaF(gc.alphaF() * 0.12)
            pen = QPen(c, glow_r * i / 2.5)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.strokePath(path, pen)
    if outline is not None and outline_w > 0:
        oc = outline if isinstance(outline, QColor) else qc(outline)
        pen = QPen(oc, outline_w)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.strokePath(path, pen)
    p.fillPath(path, color)
    p.restore()
    pad = outline_w + glow_r * 2
    return QRectF(x - pad, y - pad, w + 2 * pad, h + 2 * pad)


def wrap_text(text: str, style: str, size: float, max_w: float) -> list:
    lines = []
    for para in text.split("\n"):
        words = para.split(" ")
        cur = ""
        for wd in words:
            trial = (cur + " " + wd).strip() if cur else wd
            if text_size(trial, style, size)[0] <= max_w or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = wd
        lines.append(cur)
    return lines


def ease_out(p):
    p = max(0.0, min(1.0, p))
    return 1 - (1 - p) ** 3


def ease_out_back(p):
    p = max(0.0, min(1.0, p))
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2


def ease_drop(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


class SpellLinks:
    """Which spells hit which health bar. Bars are found by their 'bar_key',
    so a bar can be added, cut or moved after the spells were made."""

    def __init__(self, project=None):
        self.hits = {}
        self.bars = {}
        if project is None:
            return
        for c in project.all_clips():
            if c.kind != "hud" or not c.enabled:
                continue
            key = c.props.get("target_bar") or ""
            if c.hud_type == "spell":
                amount = float(c.props.get("damage_amount", 0) or 0)
                if key and amount:
                    self.hits.setdefault(key, []).append((c.start + float(c.props.get("hit_time", 1.1)), amount))
            elif c.hud_type == "rs_hitsplat" and key:
                txt = str(c.props.get("text", "")).strip()
                if txt.lstrip("-").isdigit():
                    amount = float(txt)
                    if c.props.get("kind") == "heal":
                        amount = -abs(amount)
                    if amount:
                        self.hits.setdefault(key, []).append((c.start, amount))
            if c.props.get("bar_key"):
                self.bars.setdefault(c.props["bar_key"], []).append(c)

    def bar_at(self, bar_key, t_abs):
        """The health-bar clip with this key that is on screen at t_abs."""
        clips = self.bars.get(bar_key or "", [])
        for c in clips:
            if c.start <= t_abs < c.end:
                return c
        return None

    def damage(self, bar_key, t_abs):
        total = 0.0
        for hit, amount in self.hits.get(bar_key or "", ()):
            if t_abs > hit:
                total += amount * ease_drop((t_abs - hit) / 0.25)
        return total

    def count(self, bar_key):
        return len(self.hits.get(bar_key or "", ()))


NO_LINKS = SpellLinks()


class Ctx:
    """Everything an element needs to draw itself at one moment."""

    def __init__(self, clip, t_rel, W, H, pool=None, links=None):
        self.links = links or NO_LINKS
        self.clip = clip
        self.t = t_rel
        self.W, self.H = W, H
        self.dur = clip.duration
        self.style = clip.props.get("style", "rpg")
        self.pool = pool
        self.s = H / 1080.0 * float(self.val("scale", 1.0))
        self.base_s = H / 1080.0

    def val(self, key, default=None):
        return self.clip.value(key, self.t, default)

    def val_at(self, key, t, default=None):
        return self.clip.value(key, t, default)

    def bar_value(self, t_rel=None):
        """Health value after the damage from linked spells."""
        t_rel = self.t if t_rel is None else t_rel
        v = float(self.clip.value("value", t_rel, 100.0))
        v -= self.links.damage(self.clip.props.get("bar_key"), self.clip.start + t_rel)
        if "max_value" in self.clip.props:      # heals can't overfill the bar
            v = min(v, float(self.clip.value("max_value", t_rel, v)))
        return max(0.0, v)

    def text(self, key, default=""):
        v = self.clip.props.get(key, default)
        return "" if v is None else str(v)

    def X(self, key="x"):
        return float(self.val(key, 0.5)) * self.W

    def Y(self, key="y"):
        return float(self.val(key, 0.5)) * self.H


# ------------------------------------------------------------------ animation in/out
def anim_transform(c: Ctx):
    """Returns (alpha, dx, dy, scale) for appear/disappear animations."""
    d = max(0.001, float(c.clip.props.get("anim_dur", 0.3)))
    a_in = c.clip.props.get("anim_in", "fade")
    a_out = c.clip.props.get("anim_out", "fade")
    alpha, dx, dy, sc = 1.0, 0.0, 0.0, 1.0
    t, T = c.t, c.dur
    dist = 0.25 * c.W
    if a_in != "none" and t < d:
        p = t / d
        e = ease_out(p)
        if a_in == "fade":
            alpha *= p
        elif a_in == "pop":
            sc *= max(0.01, ease_out_back(p))
            alpha *= min(1.0, p * 3)
        elif a_in == "slide_left":
            dx += (1 - e) * dist
            alpha *= min(1, p * 2)
        elif a_in == "slide_right":
            dx -= (1 - e) * dist
            alpha *= min(1, p * 2)
        elif a_in == "slide_up":
            dy += (1 - e) * dist * 0.6
            alpha *= min(1, p * 2)
        elif a_in == "slide_down":
            dy -= (1 - e) * dist * 0.6
            alpha *= min(1, p * 2)
    if a_out != "none" and t > T - d:
        p = max(0.0, (T - t) / d)
        e = ease_out(p)
        if a_out == "fade":
            alpha *= p
        elif a_out == "pop":
            sc *= max(0.01, e)
            alpha *= p
        elif a_out == "slide_left":
            dx -= (1 - e) * dist
            alpha *= p
        elif a_out == "slide_right":
            dx += (1 - e) * dist
            alpha *= p
        elif a_out == "slide_up":
            dy -= (1 - e) * dist * 0.6
            alpha *= p
        elif a_out == "slide_down":
            dy += (1 - e) * dist * 0.6
            alpha *= p
    return alpha, dx, dy, sc


# ------------------------------------------------------------------ elements
def _bar_color(c: Ctx):
    col = c.text("color")
    return col if col else BAR_COLORS.get(c.text("bar_kind", "health"), "#e8343a")


def draw_bar(p: QPainter, c: Ctx) -> QRectF:
    s = c.s
    kind = c.text("bar_kind", "health")
    mx = max(1e-6, float(c.val("max_value", 100)))
    v = c.bar_value()
    frac = max(0.0, min(1.0, v / mx))
    ghost = max(0.0, min(1.0, c.bar_value(max(0.0, c.t - 0.45)) / mx))
    col = _bar_color(c)
    label = c.text("label")
    x0, y0 = c.X(), c.Y()
    bw = float(c.val("width", 420)) * s
    low_blink = frac < 0.25 and (math.sin(c.t * 14) > 0) and kind in ("health", "boss")
    fillc = lighter(col, 1.5) if low_blink else qc(col)
    num = f"{int(round(v))}/{int(round(mx))}"
    style = c.style
    if kind == "boss":
        # name centred above the bar
        draw_text(p, label, x0 + bw / 2, y0, style, 34 * s, "#ffffff", "center", "top", "#000000", 5 * s)
        y0 += 46 * s
        label = ""
    if style == "retro":
        u = max(2, int(round(4 * s)))
        lx = x0
        if label:
            pixel_text(p, label, lx, y0 + u, u, qc("#ffffff"), shadow=qc("#000000"))
            lx += pixelfont.text_width(label) * u + 3 * u
        bh = 5 * u
        bx = int(lx)
        by = int(y0)
        bwi = int(bw // u * u)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.fillRect(QRectF(bx - u, by - u, bwi + 2 * u, bh + 2 * u), qc("#000000"))
        p.fillRect(QRectF(bx, by, bwi, bh), qc("#ffffff"))
        p.fillRect(QRectF(bx + u, by + u, bwi - 2 * u, bh - 2 * u), qc("#202020"))
        inner = bwi - 2 * u
        if ghost > frac:
            p.fillRect(QRectF(bx + u, by + u, int(inner * ghost / u) * u, bh - 2 * u), qc("#ffffff"))
        fw = int(inner * frac / u) * u
        p.fillRect(QRectF(bx + u, by + u, fw, bh - 2 * u), fillc)
        p.fillRect(QRectF(bx + u, by + u, fw, u), lighter(col, 1.6))
        for sx in range(bx + u + 4 * u, bx + u + fw, 4 * u):
            p.fillRect(QRectF(sx, by + u, u // 2 or 1, bh - 2 * u), darker(col, 1.4))
        p.restore()
        r = QRectF(x0 - u, y0 - u, bx - x0 + bwi + 3 * u, bh + 3 * u)
        if c.clip.props.get("show_number", True):
            rr = pixel_text(p, num, bx + bwi + 3 * u, by + u // 2, u, qc("#ffffff"), shadow=qc("#000000"))
            r = r.united(rr)
        return r
    if style == "rpg":
        bh = 30 * s
        lx = x0
        if label:
            tr = draw_text(p, label, x0, y0 + bh / 2, "rpg", 30 * s, "#fff4d6", "left", "middle", "#2a1608", 5 * s)
            lx = tr.right() + bh * 0.62 + 4 * s
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        outer = QRectF(lx, y0, bw, bh)
        rad = bh / 2
        g = QLinearGradient(0, y0, 0, y0 + bh)
        g.setColorAt(0, QColor("#fbe7a1"))
        g.setColorAt(0.5, QColor("#c8963e"))
        g.setColorAt(1, QColor("#7a4f1c"))
        p.setPen(QPen(QColor("#2a1608"), 2.5 * s))
        p.setBrush(QBrush(g))
        p.drawRoundedRect(outer, rad, rad)
        inner = outer.adjusted(4 * s, 4 * s, -4 * s, -4 * s)
        ir = inner.height() / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(20, 10, 14, 230))
        p.drawRoundedRect(inner, ir, ir)
        clip_path = QPainterPath()
        clip_path.addRoundedRect(inner, ir, ir)
        p.setClipPath(clip_path)
        if ghost > frac:
            p.fillRect(QRectF(inner.left(), inner.top(), inner.width() * ghost, inner.height()), QColor(255, 240, 180, 220))
        fg = QLinearGradient(0, inner.top(), 0, inner.bottom())
        fg.setColorAt(0, lighter(col, 1.7) if not low_blink else QColor("#ffffff"))
        fg.setColorAt(0.45, fillc)
        fg.setColorAt(1, darker(col, 1.6))
        p.fillRect(QRectF(inner.left(), inner.top(), inner.width() * frac, inner.height()), QBrush(fg))
        p.fillRect(QRectF(inner.left(), inner.top(), inner.width(), inner.height() * 0.38), QColor(255, 255, 255, 45))
        p.setClipping(False)
        # gem at the start
        gem_r = bh * 0.62
        gc = QPointF(lx, y0 + bh / 2)
        rg = QRadialGradient(gc.x() - gem_r * 0.3, gc.y() - gem_r * 0.3, gem_r * 1.3)
        rg.setColorAt(0, lighter(col, 2.0))
        rg.setColorAt(0.5, qc(col))
        rg.setColorAt(1, darker(col, 2.2))
        p.setPen(QPen(QColor("#e9c56b"), 3 * s))
        p.setBrush(QBrush(rg))
        p.drawEllipse(gc, gem_r, gem_r)
        p.restore()
        if c.clip.props.get("show_number", True):
            draw_text(p, num, lx + bw / 2, y0 + bh / 2, "rpg", 19 * s, "#ffffff", "center", "middle", "#000000", 3 * s)
        return QRectF(x0 - gem_r, y0 - 6 * s, lx - x0 + bw + gem_r + 10 * s, bh + 12 * s)
    # fps: segmented skewed bar
    bh = 20 * s
    big = None
    lx = x0
    if c.clip.props.get("show_number", True):
        big = draw_text(p, str(int(round(v))), x0, y0 + bh, "fps", 54 * s, col if not low_blink else "#ffffff",
                        "left", "bottom", "#000000", 2 * s)
        lx = big.right() + 12 * s
    if label:
        draw_text(p, label.upper(), lx, y0 - 4 * s, "fps", 17 * s, "#e8ffff", "left", "bottom", "#000000", 2 * s)
    n = 20
    gap = 4 * s
    segw = (bw - gap * (n - 1)) / n
    skew = bh * 0.45
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(n):
        sx = lx + i * (segw + gap)
        poly = QPolygonF([QPointF(sx + skew, y0), QPointF(sx + segw + skew, y0),
                          QPointF(sx + segw, y0 + bh), QPointF(sx, y0 + bh)])
        f0 = i / n
        if f0 < frac:
            cc = qc(col if not low_blink else "#ffffff", 0.92)
        elif f0 < ghost:
            cc = QColor(255, 255, 255, 170)
        else:
            cc = QColor(255, 255, 255, 38)
        p.setBrush(cc)
        p.drawPolygon(poly)
    p.setPen(QPen(qc(col, 0.8), 1.5 * s))
    p.drawLine(QPointF(lx, y0 + bh + 6 * s), QPointF(lx + bw * 0.35, y0 + bh + 6 * s))
    p.restore()
    r = QRectF(x0, y0 - 30 * s, lx - x0 + bw + skew + 6 * s, bh + 44 * s)
    if big is not None:
        r = r.united(big)
    return r


def draw_mini_bar(p, x, y, w, h, frac, col, s):
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    p.fillRect(QRectF(x - 2 * s, y - 2 * s, w + 4 * s, h + 4 * s), QColor(0, 0, 0, 200))
    p.fillRect(QRectF(x, y, w * max(0, min(1, frac)), h), qc(col))
    p.restore()


def draw_name_tag(p: QPainter, c: Ctx) -> QRectF:
    s = c.s
    x, y = c.X(), c.Y()
    name, lvl = c.text("name"), c.text("level")
    col = c.text("color", "#ffd54a")
    show_bar = bool(c.clip.props.get("show_bar", False))
    frac = c.bar_value() / max(1e-6, float(c.val("max_value", 100)))
    style = c.style
    if style == "retro":
        u = max(2, int(round(4 * s)))
        txt = f"{name}  {lvl}".strip()
        tw = pixelfont.text_width(txt) * u
        bw, bh = tw + 6 * u, 7 * u + 6 * u + (4 * u if show_bar else 0)
        bx, by = x - bw / 2, y - bh - 4 * u
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.fillRect(QRectF(bx, by, bw, bh), qc("#000000", 0.85))
        pen = QPen(qc("#ffffff"), u)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(bx + u / 2, by + u / 2, bw - u, bh - u))
        p.restore()
        pixel_text(p, name, bx + 3 * u, by + 3 * u, u, qc("#ffffff"))
        if lvl:
            pixel_text(p, lvl, bx + bw - 3 * u, by + 3 * u, u, qc(col), align="right")
        if show_bar:
            draw_mini_bar(p, bx + 3 * u, by + 11 * u, bw - 6 * u, 2 * u, frac, "#e8343a", 1)
        bob = int(math.sin(c.t * 6) * u)
        pixel_text(p, "▼", x, by + bh + u + bob, u, qc(col), align="center")
        return QRectF(bx - u, by - u, bw + 2 * u, bh + 12 * u)
    if style == "rpg":
        nr = draw_text(p, name, x, y - 40 * s, "rpg", 34 * s, "#ffffff", "center", "bottom", "#1a0f05", 6 * s,
                       glow=qc(col, 0.6), glow_r=6 * s)
        rect = QRectF(nr)
        if lvl:
            br = 20 * s
            cx_ = nr.left() - br * 0.6
            cy_ = nr.center().y()
            p.save()
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setPen(QPen(QColor("#2a1608"), 2 * s))
            g = QRadialGradient(cx_, cy_ - br * 0.3, br * 1.4)
            g.setColorAt(0, lighter(col, 1.6))
            g.setColorAt(1, darker(col, 1.8))
            p.setBrush(QBrush(g))
            p.drawEllipse(QPointF(cx_, cy_), br, br)
            p.restore()
            digits = "".join(ch for ch in lvl if ch.isdigit()) or lvl[:3]
            draw_text(p, digits, cx_, cy_, "rpg", 20 * s, "#ffffff", "center", "middle", "#000000", 3 * s)
            rect = rect.united(QRectF(cx_ - br, cy_ - br, 2 * br, 2 * br))
        if show_bar:
            draw_mini_bar(p, x - 90 * s, y - 34 * s, 180 * s, 10 * s, frac, "#e8343a", s)
        # chevron
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        bob = math.sin(c.t * 5) * 4 * s
        p.setPen(QPen(QColor("#1a0f05"), 2 * s))
        p.setBrush(qc(col))
        tri = QPolygonF([QPointF(x - 12 * s, y - 18 * s + bob), QPointF(x + 12 * s, y - 18 * s + bob),
                         QPointF(x, y - 2 * s + bob)])
        p.drawPolygon(tri)
        p.restore()
        return rect.united(QRectF(x - 100 * s, y - 40 * s, 200 * s, 44 * s))
    # fps
    txt = name.upper()
    tw, th = text_size(txt, "fps", 24 * s)
    pad = 10 * s
    bx, by = x - tw / 2 - pad, y - th - 2 * pad - 30 * s
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.fillRect(QRectF(bx, by, tw + 2 * pad, th + 2 * pad), QColor(0, 20, 30, 150))
    pen = QPen(qc(col), 2 * s)
    p.setPen(pen)
    L = 12 * s
    for (cx_, cy_, sx, sy) in ((bx, by, 1, 1), (bx + tw + 2 * pad, by, -1, 1), (bx, by + th + 2 * pad, 1, -1),
                               (bx + tw + 2 * pad, by + th + 2 * pad, -1, -1)):
        p.drawLine(QPointF(cx_, cy_), QPointF(cx_ + L * sx, cy_))
        p.drawLine(QPointF(cx_, cy_), QPointF(cx_, cy_ + L * sy))
    d = 9 * s
    p.setBrush(qc(col, 0.85))
    p.drawPolygon(QPolygonF([QPointF(x, y - 18 * s - d), QPointF(x + d, y - 18 * s), QPointF(x, y - 18 * s + d),
                             QPointF(x - d, y - 18 * s)]))
    p.restore()
    draw_text(p, txt, x, by + pad, "fps", 24 * s, "#ffffff", "center", "top")
    if lvl:
        draw_text(p, lvl.upper(), bx + tw + 2 * pad + 6 * s, by, "fps", 15 * s, col, "left", "top")
    if show_bar:
        draw_mini_bar(p, bx, by + th + 2 * pad + 4 * s, tw + 2 * pad, 5 * s, frac, col, s)
    return QRectF(bx - 4 * s, by - 4 * s, tw + 2 * pad + 120 * s, th + 2 * pad + 60 * s)


def draw_dialogue(p: QPainter, c: Ctx) -> QRectF:
    s = c.s
    style = c.style
    text = c.text("text")
    speaker = c.text("speaker")
    cps = float(c.val("cps", 28))
    shown = len(text) if cps <= 0 else int(max(0.0, c.t - 0.15) * cps)
    done = shown >= len(text)
    bw = float(c.val("width", 0.78)) * c.W
    cx, cy = c.X(), c.Y()
    col = c.text("color", "#ffd54a")
    if style == "retro":
        u = max(2, int(round(4 * s)))
        size = 7 * u
        line_h = 11 * u
        lines = wrap_text(text, "retro", size, bw - 10 * u)[:4]
        bh = 8 * u + line_h * max(2, len(lines))
        bx, by = int(cx - bw / 2), int(cy - bh / 2)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.fillRect(QRectF(bx, by, bw, bh), qc("#000000", 0.92))
        p.fillRect(QRectF(bx + u, by + u, bw - 2 * u, u), qc("#ffffff"))
        p.fillRect(QRectF(bx + u, by + bh - 2 * u, bw - 2 * u, u), qc("#ffffff"))
        p.fillRect(QRectF(bx + u, by + u, u, bh - 2 * u), qc("#ffffff"))
        p.fillRect(QRectF(bx + bw - 2 * u, by + u, u, bh - 2 * u), qc("#ffffff"))
        p.restore()
        if speaker:
            sw = pixelfont.text_width(speaker) * u
            p.fillRect(QRectF(bx + 4 * u, by - 6 * u, sw + 6 * u, 10 * u), qc("#000000"))
            p.fillRect(QRectF(bx + 4 * u, by - 6 * u, sw + 6 * u, u), qc(col))
            pixel_text(p, speaker, bx + 7 * u, by - 4 * u, u, qc(col))
        remaining = shown
        for i, ln in enumerate(lines):
            part = ln[:max(0, remaining)]
            remaining -= len(ln) + 1
            pixel_text(p, part, bx + 5 * u, by + 5 * u + i * line_h, u, qc("#ffffff"))
        if done and int(c.t * 3) % 2 == 0:
            pixel_text(p, "▼", bx + bw - 6 * u, by + bh - 9 * u, u, qc("#ffffff"))
        return QRectF(bx - u, by - 8 * u, bw + 2 * u, bh + 9 * u)
    if style == "rpg":
        size = 30 * s
        line_h = 42 * s
        lines = wrap_text(text, "rpg", size, bw - 70 * s)[:4]
        bh = 50 * s + line_h * max(2, len(lines))
        bx, by = cx - bw / 2, cy - bh / 2
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        g = QLinearGradient(0, by, 0, by + bh)
        g.setColorAt(0, QColor(32, 46, 110, 235))
        g.setColorAt(1, QColor(10, 14, 48, 235))
        p.setBrush(QBrush(g))
        p.setPen(QPen(QColor("#e7c86e"), 4 * s))
        p.drawRoundedRect(QRectF(bx, by, bw, bh), 14 * s, 14 * s)
        p.setPen(QPen(QColor(231, 200, 110, 120), 1.5 * s))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(bx + 9 * s, by + 9 * s, bw - 18 * s, bh - 18 * s), 9 * s, 9 * s)
        if speaker:
            nw, nh = text_size(speaker, "rpg", 28 * s)
            plate = QRectF(bx + 30 * s, by - nh * 0.75, nw + 40 * s, nh + 14 * s)
            pg = QLinearGradient(0, plate.top(), 0, plate.bottom())
            pg.setColorAt(0, QColor("#fbe7a1"))
            pg.setColorAt(1, QColor("#b07f2f"))
            p.setBrush(QBrush(pg))
            p.setPen(QPen(QColor("#3a2410"), 2.5 * s))
            p.drawRoundedRect(plate, 8 * s, 8 * s)
        p.restore()
        if speaker:
            draw_text(p, speaker, bx + 50 * s, by - nh * 0.75 + 7 * s, "rpg", 28 * s, "#2a1608", "left", "top")
        remaining = shown
        for i, ln in enumerate(lines):
            part = ln[:max(0, remaining)]
            remaining -= len(ln) + 1
            draw_text(p, part, bx + 35 * s, by + 30 * s + i * line_h, "rpg", size, "#ffffff", "left", "top",
                      "#000000", 3 * s, bold=False)
        if done:
            bob = math.sin(c.t * 6) * 4 * s
            p.save()
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#e7c86e"))
            tx, ty = bx + bw - 40 * s, by + bh - 34 * s + bob
            p.drawPolygon(QPolygonF([QPointF(tx - 10 * s, ty), QPointF(tx + 10 * s, ty), QPointF(tx, ty + 12 * s)]))
            p.restore()
        return QRectF(bx - 6 * s, by - 60 * s, bw + 12 * s, bh + 70 * s)
    # fps transmission
    size = 26 * s
    line_h = 36 * s
    lines = wrap_text(text, "fps", size, bw - 160 * s)[:4]
    bh = 70 * s + line_h * max(2, len(lines))
    bx, by = cx - bw / 2, cy - bh / 2
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    poly = QPolygonF([QPointF(bx, by), QPointF(bx + bw - 30 * s, by), QPointF(bx + bw, by + 30 * s),
                      QPointF(bx + bw, by + bh), QPointF(bx + 30 * s, by + bh), QPointF(bx, by + bh - 30 * s)])
    p.setBrush(QColor(0, 18, 26, 190))
    p.setPen(QPen(qc("#7dfcff", 0.9), 2 * s))
    p.drawPolygon(poly)
    # waveform
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(qc("#7dfcff", 0.85))
    talking = not done
    for i in range(9):
        amp = (0.25 + 0.75 * abs(math.sin(c.t * 9 + i * 1.7))) if talking else 0.15
        hh = 50 * s * amp
        p.drawRect(QRectF(bx + 28 * s + i * 10 * s, by + bh / 2 + 10 * s - hh / 2, 6 * s, hh))
    p.restore()
    draw_text(p, ("INCOMING TRANSMISSION  //  " + speaker).upper(), bx + 28 * s, by + 14 * s, "fps", 17 * s,
              "#7dfcff", "left", "top")
    remaining = shown
    for i, ln in enumerate(lines):
        part = ln[:max(0, remaining)]
        remaining -= len(ln) + 1
        draw_text(p, part, bx + 140 * s, by + 50 * s + i * line_h, "fps", size, "#ffffff", "left", "top", bold=False)
    if talking and int(c.t * 4) % 2 == 0:
        draw_text(p, "●REC", bx + bw - 30 * s, by + 14 * s, "fps", 15 * s, "#ff4455", "right", "top")
    return QRectF(bx - 4 * s, by - 4 * s, bw + 8 * s, bh + 8 * s)


def draw_quest(p: QPainter, c: Ctx) -> QRectF:
    s = c.s
    style = c.style
    right, top = c.X(), c.Y()
    col = c.text("color", "#ffcc33")
    done = bool(c.clip.props.get("completed", False))
    header = c.text("header") or ("QUEST COMPLETE" if done else "NEW QUEST")
    title, obj = c.text("title"), c.text("objective")
    bw = 560 * s
    bx = right - bw
    if style == "retro":
        u = max(2, int(round(4 * s)))
        olines = wrap_text(obj, "retro", 7 * u, bw - 18 * u)[:3]
        bh = 30 * u + len(olines) * 10 * u
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.fillRect(QRectF(bx, top, bw, bh), qc("#000000", 0.9))
        p.fillRect(QRectF(bx, top, bw, 12 * u), qc(col) if int(c.t * 4) % 2 == 0 or c.t > 1.5 else qc("#ffffff"))
        p.restore()
        pixel_text(p, "! " + header, bx + 4 * u, top + 3 * u, u, qc("#000000"))
        pixel_text(p, title, bx + 4 * u, top + 15 * u, u, qc(col))
        for i, ln in enumerate(olines):
            box = "[X] " if done and i == 0 else ("[ ] " if i == 0 else "    ")
            pixel_text(p, box + ln, bx + 4 * u, top + 26 * u + i * 10 * u, u, qc("#ffffff"))
        return QRectF(bx - u, top - u, bw + 2 * u, bh + 2 * u)
    if style == "rpg":
        olines = wrap_text(obj, "rpg", 24 * s, bw - 110 * s)[:3]
        bh = 112 * s + len(olines) * 32 * s
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        g = QLinearGradient(bx, 0, bx + bw, 0)
        g.setColorAt(0, QColor(40, 24, 8, 0))
        g.setColorAt(0.18, QColor(40, 24, 8, 215))
        g.setColorAt(1, QColor(40, 24, 8, 235))
        p.fillRect(QRectF(bx, top, bw, bh), QBrush(g))
        lg = QLinearGradient(bx, 0, bx + bw, 0)
        lg.setColorAt(0, QColor(231, 200, 110, 0))
        lg.setColorAt(0.3, QColor("#e7c86e"))
        lg.setColorAt(1, QColor("#e7c86e"))
        p.fillRect(QRectF(bx, top, bw, 3 * s), QBrush(lg))
        p.fillRect(QRectF(bx, top + bh - 3 * s, bw, 3 * s), QBrush(lg))
        # icon
        ic = QPointF(bx + 70 * s, top + 52 * s)
        p.setPen(QPen(QColor("#2a1608"), 3 * s))
        p.setBrush(qc(col))
        dd = 28 * s
        p.drawPolygon(QPolygonF([QPointF(ic.x(), ic.y() - dd), QPointF(ic.x() + dd, ic.y()),
                                 QPointF(ic.x(), ic.y() + dd), QPointF(ic.x() - dd, ic.y())]))
        p.restore()
        draw_text(p, "✓" if done else "!", ic.x(), ic.y(), "rpg", 34 * s, "#2a1608", "center", "middle")
        draw_text(p, header, bx + 115 * s, top + 14 * s, "rpg", 22 * s, col, "left", "top", "#000000", 3 * s)
        draw_text(p, title, bx + 115 * s, top + 42 * s, "rpg", 34 * s, "#ffffff", "left", "top", "#000000", 4 * s)
        for i, ln in enumerate(olines):
            pre = ("☑ " if done else "☐ ") if i == 0 else "   "
            draw_text(p, pre + ln, bx + 115 * s, top + 92 * s + i * 32 * s, "rpg", 24 * s, "#f3e6c4", "left", "top",
                      "#000000", 2 * s, bold=False)
        return QRectF(bx, top - 4 * s, bw + 4 * s, bh + 8 * s)
    # fps objective
    olines = wrap_text(obj, "fps", 22 * s, bw - 60 * s)[:3]
    bh = 90 * s + len(olines) * 30 * s
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.fillRect(QRectF(bx, top, bw, bh), QColor(0, 16, 24, 165))
    p.fillRect(QRectF(right - 5 * s, top, 5 * s, bh), qc(col))
    p.restore()
    draw_text(p, ("■ " + header).upper(), bx + 18 * s, top + 12 * s, "fps", 18 * s, col, "left", "top")
    draw_text(p, title.upper(), bx + 18 * s, top + 38 * s, "fps", 28 * s, "#ffffff", "left", "top")
    for i, ln in enumerate(olines):
        pre = ("[✓] " if done else "[ ] ") if i == 0 else "    "
        draw_text(p, pre + ln, bx + 18 * s, top + 78 * s + i * 30 * s, "fps", 22 * s, "#d9f7ff", "left", "top",
                  bold=False)
    return QRectF(bx, top, bw, bh)


def draw_character_card(p: QPainter, c: Ctx) -> QRectF:
    s = c.s
    style = c.style
    x0, y0 = c.X(), c.Y()
    col = c.text("color", "#ff5577")
    header, name, title, lvl = c.text("header"), c.text("name"), c.text("title"), c.text("level")
    lines = [ln for ln in c.text("lines").split("\n") if ln.strip()]
    per = 0.35
    vis = int(max(0.0, c.t - 0.5) / per) + 1 if c.t > 0.5 else 0
    if style == "retro":
        u = max(2, int(round(4 * s)))
        widest = max([pixelfont.text_width("> " + ln) * u for ln in lines] +
                     [pixelfont.text_width(name) * int(u * 1.5) + pixelfont.text_width("LV " + lvl) * u + 4 * u,
                      pixelfont.text_width(header) * u, pixelfont.text_width(title) * u])
        bw = max(640 * s, widest + 8 * u)
    elif style == "rpg":
        widest = max([text_size("◆ " + ln, "rpg", 27 * s)[0] for ln in lines] +
                     [text_size(name, "rpg", 56 * s)[0] + 120 * s])
        bw = max(640 * s, widest + 70 * s)
    else:
        widest = max([text_size("> " + ln, "fps", 24 * s)[0] for ln in lines] +
                     [text_size(name.upper(), "fps", 52 * s)[0] + 40 * s])
        bw = max(640 * s, widest + 60 * s)
    if style == "retro":
        bh = 44 * u + len(lines) * 11 * u
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.fillRect(QRectF(x0, y0, bw, bh), qc("#000000", 0.9))
        p.fillRect(QRectF(x0, y0, bw, 11 * u), qc(col))
        pen = QPen(qc("#ffffff"), u)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(x0 + u / 2, y0 + u / 2, bw - u, bh - u))
        p.restore()
        pixel_text(p, header, x0 + 4 * u, y0 + 2 * u, u, qc("#000000"))
        pixel_text(p, name, x0 + 4 * u, y0 + 15 * u, int(u * 1.5), qc("#ffffff"), shadow=qc(col))
        pixel_text(p, title, x0 + 4 * u, y0 + 29 * u, u, qc(col))
        if lvl:
            pixel_text(p, "LV " + lvl, x0 + bw - 4 * u, y0 + 15 * u, u, qc("#ffff66"), align="right")
        for i, ln in enumerate(lines[:vis]):
            pixel_text(p, "► " + ln, x0 + 4 * u, y0 + 40 * u + i * 11 * u, u, qc("#ffffff"))
        return QRectF(x0 - u, y0 - u, bw + 2 * u, bh + 2 * u)
    if style == "rpg":
        bh = 210 * s + len(lines) * 40 * s
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        g = QLinearGradient(0, y0, 0, y0 + bh)
        g.setColorAt(0, QColor(28, 18, 34, 235))
        g.setColorAt(1, QColor(12, 8, 18, 235))
        p.setBrush(QBrush(g))
        p.setPen(QPen(QColor("#e7c86e"), 4 * s))
        p.drawRoundedRect(QRectF(x0, y0, bw, bh), 18 * s, 18 * s)
        p.setPen(QPen(qc(col, 0.8), 2 * s))
        p.drawLine(QPointF(x0 + 30 * s, y0 + 160 * s), QPointF(x0 + bw - 30 * s, y0 + 160 * s))
        if lvl:
            cc = QPointF(x0 + bw - 70 * s, y0 + 86 * s)
            rg = QRadialGradient(cc, 50 * s)
            rg.setColorAt(0, lighter(col, 1.5))
            rg.setColorAt(1, darker(col, 2))
            p.setBrush(QBrush(rg))
            p.setPen(QPen(QColor("#e7c86e"), 4 * s))
            p.drawEllipse(cc, 44 * s, 44 * s)
        p.restore()
        draw_text(p, header, x0 + 30 * s, y0 + 22 * s, "rpg", 22 * s, col, "left", "top", "#000000", 3 * s)
        draw_text(p, name, x0 + 30 * s, y0 + 52 * s, "rpg", 56 * s, "#ffffff", "left", "top", "#000000", 5 * s,
                  glow=qc(col, 0.5), glow_r=5 * s)
        draw_text(p, title, x0 + 32 * s, y0 + 116 * s, "rpg", 26 * s, "#e7c86e", "left", "top", italic=True, bold=False)
        if lvl:
            draw_text(p, "LV", x0 + bw - 70 * s, y0 + 66 * s, "rpg", 16 * s, "#ffffff", "center", "middle")
            draw_text(p, lvl, x0 + bw - 70 * s, y0 + 94 * s, "rpg", 32 * s, "#ffffff", "center", "middle",
                      "#000000", 3 * s)
        for i, ln in enumerate(lines[:vis]):
            draw_text(p, "◆ " + ln, x0 + 34 * s, y0 + 180 * s + i * 40 * s, "rpg", 27 * s, "#f3e6c4", "left", "top",
                      "#000000", 2 * s, bold=False)
        return QRectF(x0 - 4 * s, y0 - 4 * s, bw + 8 * s, bh + 8 * s)
    # fps dossier
    bh = 190 * s + len(lines) * 36 * s
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    poly = QPolygonF([QPointF(x0, y0), QPointF(x0 + bw - 40 * s, y0), QPointF(x0 + bw, y0 + 40 * s),
                      QPointF(x0 + bw, y0 + bh), QPointF(x0, y0 + bh)])
    p.setBrush(QColor(0, 14, 22, 200))
    p.setPen(QPen(qc(col, 0.9), 2 * s))
    p.drawPolygon(poly)
    p.fillRect(QRectF(x0, y0, 8 * s, bh), qc(col))
    # scanning line
    sy = y0 + (c.t * 0.6 % 1.0) * bh
    p.fillRect(QRectF(x0, sy, bw, 2 * s), qc(col, 0.35))
    p.restore()
    draw_text(p, ("◢ " + header + "  //  TARGET IDENTIFIED").upper(), x0 + 26 * s, y0 + 16 * s, "fps", 17 * s, col,
              "left", "top")
    draw_text(p, name.upper(), x0 + 26 * s, y0 + 44 * s, "fps", 52 * s, "#ffffff", "left", "top")
    draw_text(p, title.upper(), x0 + 28 * s, y0 + 108 * s, "fps", 22 * s, "#9fefff", "left", "top", bold=False)
    if lvl:
        draw_text(p, "THREAT LVL " + lvl, x0 + bw - 24 * s, y0 + 60 * s, "fps", 22 * s, col, "right", "top")
    for i, ln in enumerate(lines[:vis]):
        draw_text(p, "> " + ln, x0 + 28 * s, y0 + 160 * s + i * 36 * s, "fps", 24 * s, "#ffffff", "left", "top",
                  bold=False)
    return QRectF(x0 - 4 * s, y0 - 4 * s, bw + 8 * s, bh + 8 * s)


def _burst_particles(seed, n):
    rnd = random.Random(seed)
    return [(rnd.uniform(0, 2 * math.pi), rnd.uniform(0.4, 1.0), rnd.uniform(3, 9), rnd.random()) for _ in range(n)]


def spell_shake(clip, t_rel, W, H):
    """Pixel offset to shake the whole picture for a spell hit."""
    hit = float(clip.value("hit_time", t_rel, 1.1))
    amt = float(clip.value("shake", t_rel, 0.6))
    dt = t_rel - hit
    if amt <= 0 or dt < 0 or dt > 0.5:
        return 0, 0
    decay = (1 - dt / 0.5) ** 2
    mag = amt * 28 * H / 1080 * decay
    return int(math.sin(dt * 90) * mag), int(math.cos(dt * 73) * mag * 0.7)


def draw_spell(p: QPainter, c: Ctx) -> QRectF:
    s = c.base_s * float(c.val("scale", 1.0))
    style = c.style
    W, H = c.W, c.H
    col = c.text("color", "#ff7a1a")
    hit = float(c.val("hit_time", 1.1))
    t = c.t
    cx, cy = float(c.val("caster_x", 0.28)) * W, float(c.val("caster_y", 0.55)) * H
    tx, ty = float(c.val("target_x", 0.72)) * W, float(c.val("target_y", 0.5)) * H
    full = QRectF(0, 0, W, H)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(Qt.PenStyle.NoPen)
    charge_end = hit * 0.4
    # charging swirl around caster
    if t < charge_end + 0.1:
        k = min(1.0, t / max(0.01, charge_end))
        for i in range(14):
            ang = i / 14 * 2 * math.pi + t * 7
            rad = (90 - 70 * k) * s * (1 + 0.3 * math.sin(i * 3.1))
            px_, py_ = cx + math.cos(ang) * rad, cy + math.sin(ang) * rad
            p.setBrush(qc(col, 0.85))
            p.drawEllipse(QPointF(px_, py_), 5 * s, 5 * s)
        rg = QRadialGradient(cx, cy, 70 * s * k + 1)
        rg.setColorAt(0, QColor(255, 255, 255, int(220 * k)))
        rg.setColorAt(0.3, qc(col, 0.8 * k))
        rg.setColorAt(1, qc(col, 0))
        p.setBrush(QBrush(rg))
        p.drawEllipse(QPointF(cx, cy), 70 * s * k + 1, 70 * s * k + 1)
    # projectile
    if c.clip.props.get("projectile", True) and charge_end <= t < hit:
        q = (t - charge_end) / max(0.01, hit - charge_end)
        e = q * q
        ox = cx + (tx - cx) * e
        oy = cy + (ty - cy) * e - math.sin(e * math.pi) * 0.12 * H
        for j in range(10, 0, -1):
            qq = max(0.0, e - j * 0.025)
            jx = cx + (tx - cx) * qq
            jy = cy + (ty - cy) * qq - math.sin(qq * math.pi) * 0.12 * H
            p.setBrush(qc(col, 0.5 * (1 - j / 11)))
            r = (26 - j * 1.8) * s
            p.drawEllipse(QPointF(jx, jy), r, r)
        rg = QRadialGradient(ox, oy, 60 * s)
        rg.setColorAt(0, QColor(255, 255, 255, 255))
        rg.setColorAt(0.25, lighter(col, 1.5))
        rg.setColorAt(0.6, qc(col, 0.6))
        rg.setColorAt(1, qc(col, 0))
        p.setBrush(QBrush(rg))
        p.drawEllipse(QPointF(ox, oy), 60 * s, 60 * s)
    # impact
    dt = t - hit
    if dt >= 0:
        if dt < 0.7:
            k = dt / 0.7
            ring = 40 * s + 260 * s * ease_out(k)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(qc(col, 1 - k), 18 * s * (1 - k) + 1))
            p.drawEllipse(QPointF(tx, ty), ring, ring)
            p.setPen(QPen(QColor(255, 255, 255, int(255 * (1 - k))), 5 * s * (1 - k) + 0.5))
            p.drawEllipse(QPointF(tx, ty), ring * 0.7, ring * 0.7)
            p.setPen(Qt.PenStyle.NoPen)
            for ang, sp, size, rr in _burst_particles(int(hit * 1000) + 7, 36):
                d = 320 * s * sp * ease_out(k)
                p.setBrush(qc(col if rr > 0.4 else "#ffffff", 1 - k))
                p.drawEllipse(QPointF(tx + math.cos(ang) * d, ty + math.sin(ang) * d + 120 * s * k * k),
                              size * s * (1 - k * 0.5), size * s * (1 - k * 0.5))
            rg = QRadialGradient(tx, ty, 150 * s)
            rg.setColorAt(0, QColor(255, 255, 255, int(255 * (1 - k))))
            rg.setColorAt(0.4, qc(col, 0.8 * (1 - k)))
            rg.setColorAt(1, qc(col, 0))
            p.setBrush(QBrush(rg))
            p.drawEllipse(QPointF(tx, ty), 150 * s, 150 * s)
        fl = float(c.val("flash", 0.55))
        if fl > 0 and dt < 0.35:
            fc = lighter(col, 1.8)
            fc.setAlphaF(min(1.0, fl * (1 - dt / 0.35) ** 2))
            p.fillRect(full, fc)
    p.restore()
    # damage number
    dmg = c.text("damage")
    amount = float(c.val("damage_amount", 0) or 0)
    if not dmg and amount > 0:
        dmg = f"-{int(round(amount))}"
    if dmg and 0 <= dt < 1.3:
        k = dt / 1.3
        sc = 1.0 + 0.8 * max(0.0, 1 - dt / 0.15)
        alpha = 1.0 if k < 0.6 else (1 - k) / 0.4
        dy = -110 * s * ease_out(k)
        draw_text(p, dmg, tx + 60 * s, ty - 80 * s + dy, style, 70 * s * sc, qc("#ffffff", alpha), "center",
                  "middle", qc(col, alpha), 8 * s)
    # banner with the spell name
    name = c.text("spell_name")
    by = float(c.val("banner_y", 0.16)) * H
    end_t = hit + 0.9
    if name and t < end_t:
        k_in = min(1.0, t / 0.3)
        sc = 1.0 + 1.6 * (1 - ease_out(k_in))
        alpha = k_in if t < end_t - 0.4 else max(0.0, (end_t - t) / 0.4)
        pulse = 1 + 0.06 * math.sin(t * 18)
        size = 96 * s * sc * pulse
        if style == "retro":
            blink = qc("#ffffff", alpha) if int(t * 10) % 2 == 0 else qc(col, alpha)
            draw_text(p, name, W / 2, by, "retro", size, blink, "center", "middle", qc("#000000", alpha), 1)
        elif style == "fps":
            jx = (random.Random(int(t * 30)).random() - 0.5) * 10 * s if t < 0.4 else 0
            draw_text(p, "<< " + name.upper() + " >>", W / 2 + jx, by, "fps", size * 0.8, qc("#ffffff", alpha),
                      "center", "middle", qc(col, alpha), 4 * s, glow=qc(col, alpha), glow_r=10 * s)
        else:
            draw_text(p, name, W / 2, by, "rpg", size, qc("#fffbe8", alpha), "center", "middle",
                      qc(darker(col, 2.2).name(), alpha), 7 * s, glow=qc(col, alpha * 0.9), glow_r=14 * s)
    return full


def draw_damage(p: QPainter, c: Ctx) -> QRectF:
    s = c.s
    k = c.t / max(0.01, c.dur)
    crit = bool(c.clip.props.get("critical", False))
    sc = 1.0 + (0.9 if crit else 0.6) * max(0.0, 1 - c.t / 0.15)
    alpha = 1.0 if k < 0.6 else max(0.0, (1 - k) / 0.4)
    x, y = c.X(), c.Y() - 120 * s * ease_out(k)
    col = c.text("color", "#ff4040")
    size = (90 if crit else 64) * s * sc
    r = draw_text(p, c.text("text"), x, y, c.style, size, qc("#ffffff", alpha), "center", "middle",
                  qc(col, alpha), 8 * s)
    if crit:
        r = r.united(draw_text(p, "CRITICAL!", x, y - size * 0.8, c.style, 34 * s, qc("#ffe14a", alpha), "center",
                               "middle", qc("#000000", alpha), 4 * s))
    return r.adjusted(-10, -10, 10, 10)


def draw_level_up(p: QPainter, c: Ctx) -> QRectF:
    s = c.s
    x, y = c.X(), c.Y()
    col = c.text("color", "#ffd23f")
    k = min(1.0, c.t / 0.5)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.translate(x, y)
    p.rotate(c.t * 25)
    rays = 16
    R = 420 * s * ease_out(k)
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(rays):
        a0 = i / rays * 2 * math.pi
        a1 = a0 + math.pi / rays * 0.6
        g = QRadialGradient(0, 0, R + 1)
        g.setColorAt(0, qc(col, 0.55))
        g.setColorAt(1, qc(col, 0))
        p.setBrush(QBrush(g))
        p.drawPolygon(QPolygonF([QPointF(0, 0), QPointF(math.cos(a0) * R, math.sin(a0) * R),
                                 QPointF(math.cos(a1) * R, math.sin(a1) * R)]))
    p.restore()
    sc = max(0.01, ease_out_back(min(1.0, c.t / 0.45)))
    r = draw_text(p, c.text("text"), x, y, c.style, 120 * s * sc, "#ffffff", "center", "middle", darker(col, 1.8),
                  9 * s, glow=qc(col, 0.8), glow_r=12 * s)
    if c.t > 0.6:
        a = min(1.0, (c.t - 0.6) / 0.3)
        draw_text(p, c.text("subtext"), x, y + 100 * s, c.style, 44 * s, qc(col, a), "center", "middle",
                  qc("#000000", a), 4 * s)
    # sparkles
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(Qt.PenStyle.NoPen)
    for ang, sp, size, rr in _burst_particles(42, 24):
        tw = 0.5 + 0.5 * math.sin(c.t * 8 + rr * 20)
        d = 300 * s * sp
        p.setBrush(QColor(255, 255, 255, int(220 * tw * k)))
        p.drawEllipse(QPointF(x + math.cos(ang) * d * 1.4, y + math.sin(ang) * d * 0.7), size * s * 0.7,
                      size * s * 0.7)
    p.restore()
    return QRectF(x - 600 * s, y - 450 * s, 1200 * s, 900 * s).united(r)


def draw_text_el(p: QPainter, c: Ctx) -> QRectF:
    s = c.s
    text = c.text("text")
    if c.clip.props.get("typewriter"):
        text = text[:int(max(0.0, c.t) * 22)]
    size = float(c.val("size", 90)) * s
    lines = text.split("\n")
    lh = size * 1.25
    y0 = c.Y() - lh * (len(lines) - 1) / 2
    r = QRectF(c.X(), c.Y(), 1, 1)
    glow = bool(c.clip.props.get("glow", False))
    col = c.text("color", "#ffffff")
    for i, ln in enumerate(lines):
        rr = draw_text(p, ln, c.X(), y0 + i * lh, c.style, size, col, "center", "middle",
                       c.text("outline", "#000000"), float(c.val("outline_width", 6)) * s,
                       glow=qc(col, 0.7) if glow else None, glow_r=size * 0.12 if glow else 0)
        r = r.united(rr)
    return r


def draw_crosshair(p: QPainter, c: Ctx) -> QRectF:
    s = c.s
    x, y = c.X(), c.Y()
    col = c.text("color", "#7dfcff")
    sz = float(c.val("size", 60)) * s
    var = c.text("variant", "cross")
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    for pass_ in (0, 1):
        pen = QPen(QColor(0, 0, 0, 160) if pass_ == 0 else qc(col), (5 if pass_ == 0 else 2.5) * s)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        g = sz * 0.25
        if var == "cross":
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                p.drawLine(QPointF(x + dx * g, y + dy * g), QPointF(x + dx * sz / 2, y + dy * sz / 2))
        elif var == "circle":
            p.drawEllipse(QPointF(x, y), sz / 2, sz / 2)
            p.drawPoint(QPointF(x, y))
        elif var == "brackets":
            r = sz / 2
            L = r * 0.45
            for sx in (-1, 1):
                for sy in (-1, 1):
                    p.drawLine(QPointF(x + sx * r, y + sy * r), QPointF(x + sx * (r - L), y + sy * r))
                    p.drawLine(QPointF(x + sx * r, y + sy * r), QPointF(x + sx * r, y + sy * (r - L)))
        if var in ("dot", "cross", "brackets"):
            p.setBrush(QColor(0, 0, 0, 160) if pass_ == 0 else qc(col))
            p.drawEllipse(QPointF(x, y), 2.5 * s, 2.5 * s)
    p.restore()
    return QRectF(x - sz, y - sz, 2 * sz, 2 * sz)


def draw_ammo(p: QPainter, c: Ctx) -> QRectF:
    s = c.s
    right, bottom = c.X(), c.Y()
    v, mx = int(round(float(c.val("value", 30)))), int(round(float(c.val("max_value", 90))))
    col = c.text("color", "#7dfcff")
    style = c.style
    if style == "retro":
        u = max(2, int(round(4 * s)))
        txt = f"x{v:02d}"
        r = pixel_text(p, txt, right, bottom - 9 * u, u * 2, qc("#ffffff"), "right", "bottom", qc("#000000"))
        n = min(v, 12)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        for i in range(n):
            bx = right - (i + 1) * 4 * u
            p.fillRect(QRectF(bx, bottom - 6 * u, 2 * u, 5 * u), qc("#ffd23f"))
            p.fillRect(QRectF(bx, bottom - 6 * u, 2 * u, u), qc("#ffffff"))
        p.restore()
        pixel_text(p, c.text("label"), r.left() - 2 * u, r.top() + 2 * u, u, qc(col), "right", "top", qc("#000000"))
        return QRectF(right - 70 * u, bottom - 40 * u, 72 * u, 42 * u)
    if style == "rpg":
        r = draw_text(p, f"{v}", right, bottom, "rpg", 64 * s, "#ffffff", "right", "bottom", "#2a1608", 6 * s)
        draw_text(p, c.text("label") + f"  ({mx})", r.left() - 10 * s, bottom - 12 * s, "rpg", 26 * s, "#e7c86e",
                  "right", "bottom", "#000000", 3 * s)
        return QRectF(right - 500 * s, bottom - 90 * s, 510 * s, 100 * s)
    big = draw_text(p, f"{v}", right - 120 * s, bottom, "fps", 86 * s, "#ffffff", "right", "bottom", "#000000", 2 * s)
    draw_text(p, f"/ {mx}", right, bottom - 10 * s, "fps", 40 * s, col, "right", "bottom")
    draw_text(p, c.text("weapon").upper(), right, big.top() - 2 * s, "fps", 20 * s, "#d9f7ff", "right", "bottom")
    draw_text(p, c.text("label").upper(), big.left() - 12 * s, bottom - 14 * s, "fps", 18 * s, col, "right", "bottom")
    p.fillRect(QRectF(right - 360 * s, bottom + 6 * s, 360 * s, 3 * s), qc(col, 0.8))
    return QRectF(right - 520 * s, bottom - 150 * s, 530 * s, 165 * s)


def _icon(p, kind, x, y, r, col, style):
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, style != "retro")
    if kind == "coin":
        g = QRadialGradient(x - r * 0.3, y - r * 0.3, r * 1.4)
        g.setColorAt(0, QColor("#fff7b0"))
        g.setColorAt(0.6, qc(col))
        g.setColorAt(1, darker(col, 1.6))
        p.setBrush(QBrush(g))
        p.setPen(QPen(darker(col, 2.2), max(1.0, r * 0.12)))
        p.drawEllipse(QPointF(x, y), r * 0.8, r)
        p.setPen(QPen(darker(col, 1.5), max(1.0, r * 0.12)))
        p.drawLine(QPointF(x, y - r * 0.5), QPointF(x, y + r * 0.5))
    elif kind == "star":
        pts = []
        for i in range(10):
            a = -math.pi / 2 + i * math.pi / 5
            rr = r if i % 2 == 0 else r * 0.45
            pts.append(QPointF(x + math.cos(a) * rr, y + math.sin(a) * rr))
        p.setBrush(qc(col))
        p.setPen(QPen(darker(col, 2), max(1.0, r * 0.1)))
        p.drawPolygon(QPolygonF(pts))
    elif kind == "heart":
        path = QPainterPath()
        path.moveTo(x, y + r * 0.9)
        path.cubicTo(x - r * 1.3, y - r * 0.1, x - r * 0.6, y - r * 1.1, x, y - r * 0.4)
        path.cubicTo(x + r * 0.6, y - r * 1.1, x + r * 1.3, y - r * 0.1, x, y + r * 0.9)
        p.fillPath(path, qc("#ff3355"))
    p.restore()


def draw_score(p: QPainter, c: Ctx) -> QRectF:
    s = c.s
    x, y = c.X(), c.Y()
    v = int(round(float(c.val("value", 0))))
    digits = int(c.clip.props.get("digits", 6) or 0)
    num = str(v).zfill(digits) if digits else str(v)
    col = c.text("color", "#ffd23f")
    icon = c.text("icon", "coin")
    style = c.style
    size = 40 * s
    lx = x
    if icon != "none":
        _icon(p, icon, x + size * 0.5, y + size * 0.5, size * 0.5, col, style)
        lx += size * 1.2
    label = c.text("label")
    if style == "retro":
        r = draw_text(p, f"{label} {num}".strip(), lx, y + size * 0.1, "retro", size * 0.8, "#ffffff", "left", "top",
                      "#000000", 1)
    elif style == "rpg":
        r = draw_text(p, f"{num}", lx, y, "rpg", size, "#ffffff", "left", "top", "#2a1608", 5 * s)
        if label:
            r = r.united(draw_text(p, label, r.right() + 8 * s, y + 10 * s, "rpg", 22 * s, col, "left", "top",
                                   "#000000", 3 * s))
    else:
        r = draw_text(p, f"{label.upper()}  {num}".strip(), lx, y, "fps", size * 0.9, "#ffffff", "left", "top",
                      "#000000", 2 * s)
    return QRectF(x - 4, y - 4, r.right() - x + 20 * s, size + 20 * s)


def draw_timer(p: QPainter, c: Ctx) -> QRectF:
    s = c.s
    start = float(c.val("start_seconds", 300))
    sec = start - c.t if c.text("count", "down") == "down" else start + c.t
    sec = max(0.0, sec)
    txt = f"{int(sec // 60):02d}:{int(sec % 60):02d}"
    col = c.text("color", "#ffffff")
    if c.text("count", "down") == "down" and sec < 10 and int(c.t * 4) % 2 == 0:
        col = "#ff4040"
    x, y = c.X(), c.Y()
    r = draw_text(p, c.text("label"), x, y, c.style, 22 * s, "#ffd54a", "center", "top", "#000000", 3 * s)
    r = r.united(draw_text(p, txt, x, y + 30 * s, c.style, 52 * s, col, "center", "top", "#000000", 5 * s))
    return r.adjusted(-6, -6, 6, 6)


def draw_minimap(p: QPainter, c: Ctx) -> QRectF:
    s = c.s
    x, y = c.X(), c.Y()
    R = float(c.val("size", 240)) * s / 2
    col = c.text("color", "#55ff99")
    n = int(c.clip.props.get("enemies", 3))
    style = c.style
    rnd = random.Random(int(c.clip.id[-4:], 16) if c.clip.id[-4:].isalnum() else 3)
    blips = [(rnd.uniform(0, 2 * math.pi), rnd.uniform(0.3, 0.9), rnd.uniform(-0.2, 0.2)) for _ in range(n)]
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, style != "retro")
    if style == "retro":
        u = max(2, int(round(4 * s)))
        p.fillRect(QRectF(x - R, y - R, 2 * R, 2 * R), qc("#000000", 0.8))
        p.setPen(QPen(qc("#ffffff"), u))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(x - R, y - R, 2 * R, 2 * R))
        step = int(R / 4) or 1
        for gx in range(int(x - R) + step, int(x + R), step):
            for gy in range(int(y - R) + step, int(y + R), step):
                p.fillRect(QRectF(gx, gy, u / 2 + 1, u / 2 + 1), qc(col, 0.4))
        for a, d, drift in blips:
            aa = a + c.t * drift
            if int(c.t * 3 + a * 3) % 3:
                p.fillRect(QRectF(x + math.cos(aa) * d * R - u, y + math.sin(aa) * d * R - u, 2 * u, 2 * u),
                           qc("#ff4040"))
        p.fillRect(QRectF(x - u, y - u, 2 * u, 2 * u), qc(col))
        p.restore()
        return QRectF(x - R - u, y - R - u, 2 * R + 2 * u, 2 * R + 2 * u)
    if style == "rpg":
        g = QRadialGradient(x, y, R)
        g.setColorAt(0, QColor("#f3e2b3"))
        g.setColorAt(1, QColor("#c7a467"))
        p.setBrush(QBrush(g))
        p.setPen(QPen(QColor("#5a3a14"), 5 * s))
        p.drawEllipse(QPointF(x, y), R, R)
        p.setPen(QPen(QColor(90, 58, 20, 120), 1.5 * s, Qt.PenStyle.DashLine))
        p.drawEllipse(QPointF(x, y), R * 0.6, R * 0.6)
        p.setPen(Qt.PenStyle.NoPen)
        for a, d, drift in blips:
            aa = a + c.t * drift
            p.setBrush(QColor("#a01818"))
            p.drawEllipse(QPointF(x + math.cos(aa) * d * R, y + math.sin(aa) * d * R), 6 * s, 6 * s)
        p.setBrush(QColor("#1f4fd1"))
        p.drawPolygon(QPolygonF([QPointF(x, y - 12 * s), QPointF(x + 8 * s, y + 8 * s), QPointF(x - 8 * s, y + 8 * s)]))
        p.restore()
        draw_text(p, "N", x, y - R - 4 * s, "rpg", 26 * s, "#fff4d6", "center", "bottom", "#2a1608", 4 * s)
        return QRectF(x - R - 8 * s, y - R - 40 * s, 2 * R + 16 * s, 2 * R + 50 * s)
    # fps radar
    p.setBrush(QColor(0, 20, 12, 170))
    p.setPen(QPen(qc(col, 0.9), 2 * s))
    p.drawEllipse(QPointF(x, y), R, R)
    p.setPen(QPen(qc(col, 0.35), 1 * s))
    p.drawEllipse(QPointF(x, y), R * 0.66, R * 0.66)
    p.drawEllipse(QPointF(x, y), R * 0.33, R * 0.33)
    p.drawLine(QPointF(x - R, y), QPointF(x + R, y))
    p.drawLine(QPointF(x, y - R), QPointF(x, y + R))
    sweep = (c.t * 120) % 360
    cg = QConicalGradient(x, y, -sweep)
    cg.setColorAt(0, qc(col, 0.55))
    cg.setColorAt(0.15, qc(col, 0.0))
    cg.setColorAt(1, qc(col, 0.0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(cg))
    p.drawEllipse(QPointF(x, y), R, R)
    for a, d, drift in blips:
        aa = a + c.t * drift
        ang_deg = (-math.degrees(aa)) % 360
        since = (sweep - ang_deg) % 360
        alpha = max(0.15, 1 - since / 300)
        p.setBrush(QColor(255, 60, 60, int(255 * alpha)))
        p.drawEllipse(QPointF(x + math.cos(aa) * d * R, y + math.sin(aa) * d * R), 6 * s, 6 * s)
    p.setBrush(qc(col))
    p.drawPolygon(QPolygonF([QPointF(x, y - 10 * s), QPointF(x + 7 * s, y + 7 * s), QPointF(x - 7 * s, y + 7 * s)]))
    p.restore()
    return QRectF(x - R - 4, y - R - 4, 2 * R + 8, 2 * R + 8)


def draw_feed(p: QPainter, c: Ctx) -> QRectF:
    s = c.s
    right, top = c.X(), c.Y()
    lines = [ln for ln in c.text("lines").split("\n") if ln.strip()]
    iv = float(c.val("interval", 1.2))
    hold = float(c.val("hold", 4.0))
    col = c.text("color", "#ff5566")
    style = c.style
    row = 0
    r = QRectF(right, top, 1, 1)
    lh = 46 * s
    for i, ln in enumerate(lines):
        t0 = i * iv
        if not (t0 <= c.t < t0 + hold):
            continue
        age = c.t - t0
        a = min(1.0, age / 0.2) * (1.0 if age < hold - 0.4 else max(0.0, (hold - age) / 0.4))
        slide = (1 - ease_out(min(1.0, age / 0.25))) * 80 * s
        y = top + row * lh
        tw, th = text_size(ln, style, 24 * s)
        bx = right - tw - 30 * s + slide
        p.save()
        p.setOpacity(p.opacity() * a)
        p.fillRect(QRectF(bx, y, tw + 30 * s, lh - 6 * s), QColor(0, 0, 0, 150))
        p.fillRect(QRectF(bx, y, 5 * s, lh - 6 * s), qc(col))
        draw_text(p, ln, bx + 16 * s, y + (lh - 6 * s) / 2, style, 24 * s, "#ffffff", "left", "middle", bold=False)
        p.restore()
        r = r.united(QRectF(bx - 4, y - 4, tw + 40 * s + slide, lh + 4))
        row += 1
    return r


def draw_prompt(p: QPainter, c: Ctx) -> QRectF:
    s = c.s
    x, y = c.X(), c.Y()
    col = c.text("color", "#3ddc84")
    btn = c.text("button", "A")[:3]
    pulse = 1 + 0.08 * math.sin(c.t * 6)
    R = 30 * s * pulse
    tw, th = text_size(c.text("text"), c.style, 34 * s)
    total = 2 * R + 16 * s + tw
    bx = x - total / 2
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(QPen(QColor(0, 0, 0, 200), 3 * s))
    g = QRadialGradient(bx + R - R * 0.3, y - R * 0.3, R * 1.4)
    g.setColorAt(0, lighter(col, 1.5))
    g.setColorAt(1, darker(col, 1.5))
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(bx + R, y), R, R)
    p.restore()
    draw_text(p, btn, bx + R, y, "fps" if c.style == "fps" else c.style, 34 * s, "#ffffff", "center", "middle",
              "#000000", 3 * s)
    draw_text(p, c.text("text"), bx + 2 * R + 16 * s, y, c.style, 34 * s, "#ffffff", "left", "middle", "#000000", 4 * s)
    return QRectF(bx - 10 * s, y - R - 10 * s, total + 30 * s, 2 * R + 20 * s)


def draw_menu(p: QPainter, c: Ctx) -> QRectF:
    s = c.s
    W, H = c.W, c.H
    dim = float(c.val("dim", 0.55))
    p.fillRect(QRectF(0, 0, W, H), QColor(0, 0, 0, int(255 * dim)))
    x, y = c.X(), c.Y()
    col = c.text("color", "#ffd54a")
    items = [ln for ln in c.text("items").split("\n") if ln.strip()]
    sel = int(round(float(c.val("selected", 0))))
    draw_text(p, c.text("title"), x, y - 70 * s - len(items) * 30 * s, c.style, 96 * s, "#ffffff", "center", "middle",
              "#000000", 6 * s, glow=qc(col, 0.5) if c.style != "retro" else None, glow_r=10 * s)
    for i, it in enumerate(items):
        yy = y + (i - (len(items) - 1) / 2) * 64 * s + 40 * s
        on = i == sel
        draw_text(p, it, x, yy, c.style, 44 * s, col if on else "#d0d0d0", "center", "middle", "#000000", 4 * s)
        if on:
            tw, _ = text_size(it, c.style, 44 * s)
            bob = math.sin(c.t * 8) * 6 * s
            draw_text(p, "►", x - tw / 2 - 40 * s + bob, yy, "retro", 40 * s, col, "center", "middle")
    return QRectF(0, 0, W, H)


def _corner_brackets(p, rect, L, pen):
    p.setPen(pen)
    for (cx_, cy_, sx, sy) in ((rect.left(), rect.top(), 1, 1), (rect.right(), rect.top(), -1, 1),
                               (rect.left(), rect.bottom(), 1, -1), (rect.right(), rect.bottom(), -1, -1)):
        p.drawLine(QPointF(cx_, cy_), QPointF(cx_ + L * sx, cy_))
        p.drawLine(QPointF(cx_, cy_), QPointF(cx_, cy_ + L * sy))


def draw_frame(p: QPainter, c: Ctx) -> QRectF:
    W, H = c.W, c.H
    s = c.base_s
    th = float(c.val("thickness", 1.0))
    col = c.text("color", "#d8b45a")
    var = c.text("variant", "rpg_ornate")
    ll, lr = c.text("label_left"), c.text("label_right")
    full = QRectF(0, 0, W, H)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    if var == "retro_tv":
        m = 70 * s * th
        screen = QPainterPath()
        screen.addRoundedRect(QRectF(m, m * 0.8, W - 2 * m, H - 1.6 * m), 60 * s, 60 * s)
        bezel = QPainterPath()
        bezel.setFillRule(Qt.FillRule.OddEvenFill)   # frame with a hole: robust at every size
        bezel.addRect(full)
        bezel.addPath(screen)
        g = QLinearGradient(0, 0, 0, H)
        g.setColorAt(0, QColor("#3b3b3f"))
        g.setColorAt(1, QColor("#16161a"))
        p.fillPath(bezel, QBrush(g))
        p.setPen(QPen(QColor(0, 0, 0, 220), 6 * s))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(screen)
        rg = QRadialGradient(W / 2, H / 2, W * 0.62)
        rg.setColorAt(0.75, QColor(0, 0, 0, 0))
        rg.setColorAt(1, QColor(0, 0, 0, 140))
        p.setClipPath(screen)
        p.fillRect(full, QBrush(rg))
        p.setClipping(False)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#ff3030") if int(c.t * 2) % 2 == 0 else QColor("#601010"))
        p.drawEllipse(QPointF(W - m * 1.2, H - m * 0.4), 6 * s, 6 * s)
        p.restore()
        if ll:
            draw_text(p, ll, m, H - m * 0.4, "retro", 22 * s, "#bbbbbb", "left", "middle")
        if lr:
            draw_text(p, lr, W - m * 1.6, H - m * 0.4, "retro", 22 * s, "#bbbbbb", "right", "middle")
        return full
    if var == "arcade":
        p.fillRect(QRectF(0, 0, W, 70 * s * th), QColor(0, 0, 0, 220))
        p.fillRect(QRectF(0, H - 56 * s * th, W, 56 * s * th), QColor(0, 0, 0, 220))
        p.restore()
        y0 = 18 * s * th
        draw_text(p, ll or "1UP", 60 * s, y0, "retro", 22 * s, "#ff4040", "left", "top")
        draw_text(p, "HI-SCORE", W / 2, y0, "retro", 22 * s, "#ff4040", "center", "top")
        draw_text(p, lr or "2UP", W - 60 * s, y0, "retro", 22 * s, "#ff4040", "right", "top")
        hs = f"{int(c.t * 37) * 10:06d}"
        draw_text(p, hs, 60 * s, y0 + 28 * s, "retro", 22 * s, "#ffffff", "left", "top")
        draw_text(p, "999999", W / 2, y0 + 28 * s, "retro", 22 * s, "#ffffff", "center", "top")
        if int(c.t * 2) % 2 == 0:
            draw_text(p, "INSERT COIN", W / 2, H - 28 * s * th, "retro", 22 * s, col, "center", "middle")
        draw_text(p, "CREDIT 01", W - 60 * s, H - 28 * s * th, "retro", 18 * s, "#ffffff", "right", "middle")
        return full
    if var == "fps_visor":
        rg = QRadialGradient(W / 2, H / 2, W * 0.7)
        rg.setColorAt(0.6, QColor(0, 0, 0, 0))
        rg.setColorAt(1, QColor(0, 20, 30, 170))
        p.fillRect(full, QBrush(rg))
        m = 40 * s
        _corner_brackets(p, QRectF(m, m, W - 2 * m, H - 2 * m), 90 * s * th, QPen(qc(col, 0.9), 3 * s * th))
        # compass strip
        cx = W / 2
        p.setPen(QPen(qc(col, 0.8), 2 * s))
        heading = (c.t * 8) % 360
        for d in range(-60, 61, 5):
            deg = (heading + d) % 360
            xx = cx + d * 6 * s
            tall = 14 * s if round(deg) % 15 == 0 else 7 * s
            p.drawLine(QPointF(xx, 52 * s), QPointF(xx, 52 * s + tall))
        p.restore()
        for d in range(-60, 61, 5):
            deg = int(round(heading + d)) % 360
            if deg % 45 == 0:
                lab = {0: "N", 45: "NE", 90: "E", 135: "SE", 180: "S", 225: "SW", 270: "W", 315: "NW"}[deg]
                draw_text(p, lab, cx + d * 6 * s, 72 * s, "fps", 18 * s, col, "center", "top")
        draw_text(p, "▼", cx, 36 * s, "retro", 16 * s, col, "center", "middle")
        if int(c.t * 2) % 2 == 0:
            draw_text(p, "● REC", 80 * s, 80 * s, "fps", 24 * s, "#ff4455", "left", "top")
        if ll:
            draw_text(p, ll.upper(), 80 * s, H - 80 * s, "fps", 22 * s, col, "left", "bottom")
        if lr:
            draw_text(p, lr.upper(), W - 80 * s, H - 80 * s, "fps", 22 * s, col, "right", "bottom")
        return full
    if var == "minimal":
        m = 30 * s
        _corner_brackets(p, QRectF(m, m, W - 2 * m, H - 2 * m), 70 * s * th, QPen(qc(col), 4 * s * th))
        p.restore()
        if ll:
            draw_text(p, ll, m + 10 * s, m + 10 * s, c.style, 24 * s, col, "left", "top", "#000000", 3 * s)
        if lr:
            draw_text(p, lr, W - m - 10 * s, m + 10 * s, c.style, 24 * s, col, "right", "top", "#000000", 3 * s)
        return full
    # rpg ornate
    m = 22 * s * th
    rg = QRadialGradient(W / 2, H / 2, W * 0.66)
    rg.setColorAt(0.7, QColor(0, 0, 0, 0))
    rg.setColorAt(1, QColor(20, 8, 0, 150))
    p.fillRect(full, QBrush(rg))
    g = QLinearGradient(0, 0, W, H)
    g.setColorAt(0, QColor("#fbe7a1"))
    g.setColorAt(0.5, qc(col))
    g.setColorAt(1, QColor("#7a4f1c"))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QBrush(g), 8 * s * th))
    p.drawRect(QRectF(m, m, W - 2 * m, H - 2 * m))
    p.setPen(QPen(qc(col, 0.7), 2 * s * th))
    p.drawRect(QRectF(m + 14 * s * th, m + 14 * s * th, W - 2 * m - 28 * s * th, H - 2 * m - 28 * s * th))
    for (cx_, cy_) in ((m, m), (W - m, m), (m, H - m), (W - m, H - m)):
        d = 26 * s * th
        p.setPen(QPen(QColor("#2a1608"), 3 * s))
        p.setBrush(QBrush(g))
        p.drawPolygon(QPolygonF([QPointF(cx_, cy_ - d), QPointF(cx_ + d, cy_), QPointF(cx_, cy_ + d),
                                 QPointF(cx_ - d, cy_)]))
        p.setBrush(QColor("#b0203a"))
        p.drawEllipse(QPointF(cx_, cy_), d * 0.35, d * 0.35)
    p.restore()
    if ll:
        tw, thh = text_size(ll, "rpg", 30 * s)
        p.fillRect(QRectF(W / 2 - tw / 2 - 30 * s, m - thh / 2 - 6 * s, tw + 60 * s, thh + 12 * s), QColor(30, 16, 4, 230))
        draw_text(p, ll, W / 2, m, "rpg", 30 * s, col, "center", "middle", "#000000", 3 * s)
    if lr:
        draw_text(p, lr, W - m - 40 * s, H - m - 30 * s, "rpg", 24 * s, col, "right", "bottom", "#000000", 3 * s)
    return full


_STICKER_CACHE: dict = {}


def draw_sticker(p: QPainter, c: Ctx) -> QRectF:
    if c.pool is None or not c.clip.media_id:
        return QRectF()
    arr = c.pool.image(c.clip.media_id)
    if arr is None:
        return QRectF()
    key = c.clip.media_id
    img = _STICKER_CACHE.get(key)
    if img is None:
        h, w = arr.shape[:2]
        rgba = np.ascontiguousarray(arr)
        img = QImage(rgba.data, w, h, w * 4, QImage.Format.Format_RGBA8888).copy()
        _STICKER_CACHE[key] = img
    s = c.s
    w, h = img.width() * s, img.height() * s
    # images bigger than the frame start at frame size
    fit = min(1.0, c.W * 0.9 / max(1, w), c.H * 0.9 / max(1, h))
    w, h = w * fit, h * fit
    x, y = c.X(), c.Y()
    p.save()
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    p.translate(x, y)
    p.rotate(float(c.val("rotation", 0)))
    p.drawImage(QRectF(-w / 2, -h / 2, w, h), img)
    p.restore()
    R = math.hypot(w, h) / 2
    return QRectF(x - R, y - R, 2 * R, 2 * R)


DRAWERS = {
    "bar": draw_bar, "name_tag": draw_name_tag, "dialogue": draw_dialogue, "quest": draw_quest,
    "character_card": draw_character_card, "spell": draw_spell, "damage": draw_damage, "level_up": draw_level_up,
    "text": draw_text_el, "crosshair": draw_crosshair, "ammo": draw_ammo, "score": draw_score, "timer": draw_timer,
    "minimap": draw_minimap, "feed": draw_feed, "prompt": draw_prompt, "menu": draw_menu, "frame": draw_frame,
    "sticker": draw_sticker,
}


def draw_hud_clip(p: QPainter, clip, t_rel: float, W: int, H: int, pool=None, links=None) -> QRectF:
    fn = DRAWERS.get(clip.hud_type)
    if fn is None:
        return QRectF()
    c = Ctx(clip, t_rel, W, H, pool, links)
    alpha, dx, dy, sc = anim_transform(c)
    alpha *= float(c.val("opacity", 1.0))
    if alpha <= 0.002:
        return QRectF()
    p.save()
    p.setOpacity(alpha)
    ax, ay = c.X(), c.Y()
    tr = QTransform()
    tr.translate(dx, dy)
    if abs(sc - 1.0) > 1e-3:
        tr.translate(ax, ay)
        tr.scale(sc, sc)
        tr.translate(-ax, -ay)
    p.setTransform(tr, True)
    try:
        r = fn(p, c)
    finally:
        p.restore()
    if r is None:
        return QRectF(0, 0, W, H)
    return tr.mapRect(r).adjusted(-4, -4, 4, 4)


# game-inspired elements register themselves into the tables above
from . import game_skins  # noqa: E402,F401
