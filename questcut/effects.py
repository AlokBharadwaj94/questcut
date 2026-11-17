"""Image filters, looks, vignettes, local touch-ups and transitions.

All functions take float32 RGB images (H, W, 3) with values 0..1.
They work on numpy arrays (CPU) and on CuPy arrays (NVIDIA GPU).
"""
from __future__ import annotations

import math

import cv2
import numpy as np

# ------------------------------------------------------------------ helpers


def xp_of(a):
    if type(a).__module__.startswith("cupy"):
        import cupy
        return cupy
    return np


def _is_gpu(a) -> bool:
    return xp_of(a) is not np


def resize(a, w: int, h: int, nearest: bool = False):
    w, h = max(1, int(w)), max(1, int(h))
    interp = cv2.INTER_NEAREST if nearest else (cv2.INTER_AREA if w < a.shape[1] else cv2.INTER_LINEAR)
    if _is_gpu(a):
        cp = xp_of(a)
        return cp.asarray(cv2.resize(cp.asnumpy(a), (w, h), interpolation=interp))
    return cv2.resize(a, (w, h), interpolation=interp)


def gblur(a, sigma: float, horizontal_only: bool = False):
    if sigma <= 0.3:
        return a
    if _is_gpu(a):
        from cupyx.scipy.ndimage import gaussian_filter
        sig = (0, sigma, 0) if horizontal_only else (sigma, sigma, 0)
        return gaussian_filter(a, sigma=sig)
    if horizontal_only:
        out = cv2.GaussianBlur(a, (0, 0), sigmaX=sigma, sigmaY=0.01)
    else:
        out = cv2.GaussianBlur(a, (0, 0), sigma)
    if out.ndim < a.ndim:
        out = out[..., None]
    return out


def hex_to_rgb(h: str):
    h = (h or "#000000").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return (0.0, 0.0, 0.0)


_GRID_CACHE: dict = {}


def grid(h: int, w: int, xp):
    """Normalised pixel coordinates: x and y in 0..1."""
    key = (h, w, xp.__name__)
    g = _GRID_CACHE.get(key)
    if g is None:
        ys = (xp.arange(h, dtype=xp.float32) + 0.5) / h
        xs = (xp.arange(w, dtype=xp.float32) + 0.5) / w
        g = (xs[None, :], ys[:, None])
        if len(_GRID_CACHE) > 16:
            _GRID_CACHE.clear()
        _GRID_CACHE[key] = g
    return g


def smoothstep(e0, e1, x, xp):
    t = xp.clip((x - e0) / max(1e-6, (e1 - e0)), 0.0, 1.0)
    return t * t * (3 - 2 * t)


_MASK_CACHE: dict = {}


def shape_mask(h, w, xp, shape, cx, cy, sw, sh, feather):
    """1 inside the shape, 0 outside, with a soft edge. Sizes are fractions of
    the image width/height (sw, sh are full width/height of the shape).
    Results are cached, because most masks stay the same from frame to frame."""
    key = (h, w, xp.__name__, shape, round(float(cx), 4), round(float(cy), 4), round(float(sw), 4),
           round(float(sh), 4), round(float(feather), 4))
    m = _MASK_CACHE.get(key)
    if m is None:
        m = _shape_mask(h, w, xp, shape, cx, cy, sw, sh, feather)
        if len(_MASK_CACHE) > 24:
            _MASK_CACHE.pop(next(iter(_MASK_CACHE)))
        _MASK_CACHE[key] = m
    return m


def _shape_mask(h, w, xp, shape, cx, cy, sw, sh, feather):
    xs, ys = grid(h, w, xp)
    dx = (xs - cx) / max(1e-4, sw / 2)
    dy = (ys - cy) / max(1e-4, sh / 2)
    if shape in ("rectangle", "rect"):
        d = xp.maximum(xp.abs(dx), xp.abs(dy))
        # soften corners slightly (superellipse)
        d = (xp.abs(dx) ** 8 + xp.abs(dy) ** 8) ** (1 / 8.0) * 0.5 + d * 0.5
    else:
        d = xp.sqrt(dx * dx + dy * dy)
    f = max(0.002, feather)
    return 1.0 - smoothstep(1.0 - f, 1.0 + f * 0.25, d, xp)


def luminance(img):
    return img[..., 0] * 0.299 + img[..., 1] * 0.587 + img[..., 2] * 0.114


def _noise(h, w, seed, xp, amount):
    rng = np.random.default_rng(int(seed) & 0xFFFFFFFF)
    n = rng.standard_normal((h // 2 + 1, w // 2 + 1)).astype(np.float32)
    n = cv2.resize(n, (w, h), interpolation=cv2.INTER_NEAREST)
    return xp.asarray(n) * amount


# ------------------------------------------------------------------ effect catalogue
# kind: float(min,max,step) | choice(options) | color | bool
EFFECT_SPECS = {
    "color": {
        "label": "Colour & light",
        "gpu": "gpu_faster",
        "params": [
            ("brightness", "Brightness", "float", -1.0, 1.0, 0.01),
            ("contrast", "Contrast", "float", 0.0, 3.0, 0.01),
            ("saturation", "Saturation", "float", 0.0, 3.0, 0.01),
            ("temperature", "Warm / cool", "float", -1.0, 1.0, 0.01),
            ("tint", "Green / pink", "float", -1.0, 1.0, 0.01),
            ("gamma", "Midtones", "float", 0.3, 3.0, 0.01),
        ],
    },
    "look": {
        "label": "Game look",
        "gpu": "gpu_faster",
        "params": [
            ("preset", "Look", "choice", ["retro_pixel", "sepia_flashback", "night_vision", "glitch",
                                          "crt", "vhs", "black_white", "comic", "thermal", "dream"]),
            ("strength", "Strength", "float", 0.0, 1.0, 0.01),
            ("amount", "Amount", "float", 0.0, 1.0, 0.01),
        ],
    },
    "vignette": {
        "label": "Vignette",
        "gpu": "gpu_faster",
        "params": [
            ("shape", "Shape", "choice", ["oval", "circle", "rectangle"]),
            ("cx", "Centre X", "float", 0.0, 1.0, 0.005),
            ("cy", "Centre Y", "float", 0.0, 1.0, 0.005),
            ("size", "Size", "float", 0.05, 2.0, 0.01),
            ("aspect", "Width / height", "float", 0.3, 3.0, 0.01),
            ("softness", "Softness", "float", 0.0, 1.0, 0.01),
            ("strength", "Strength", "float", 0.0, 1.0, 0.01),
            ("color", "Colour", "color"),
        ],
    },
    "region": {
        "label": "Touch-up area (blur / hide / highlight)",
        "gpu": "gpu_faster",
        "params": [
            ("mode", "What to do", "choice", ["blur", "pixelate", "solid", "highlight", "spotlight"]),
            ("shape", "Shape", "choice", ["ellipse", "rectangle"]),
            ("cx", "Centre X", "float", 0.0, 1.0, 0.005),
            ("cy", "Centre Y", "float", 0.0, 1.0, 0.005),
            ("w", "Width", "float", 0.01, 1.5, 0.005),
            ("h", "Height", "float", 0.01, 1.5, 0.005),
            ("strength", "Strength", "float", 0.0, 1.0, 0.01),
            ("feather", "Soft edge", "float", 0.0, 1.0, 0.01),
            ("color", "Colour (solid)", "color"),
        ],
    },
    "blur": {
        "label": "Blur whole picture",
        "gpu": "gpu_faster",
        "params": [("amount", "Amount", "float", 0.0, 1.0, 0.01)],
    },
    "sharpen": {
        "label": "Sharpen",
        "gpu": "gpu_faster",
        "params": [("amount", "Amount", "float", 0.0, 2.0, 0.01)],
    },
}

EFFECT_DEFAULTS = {
    "color": {"brightness": 0.0, "contrast": 1.0, "saturation": 1.0, "temperature": 0.0, "tint": 0.0, "gamma": 1.0},
    "look": {"preset": "retro_pixel", "strength": 1.0, "amount": 0.5},
    "vignette": {"shape": "oval", "cx": 0.5, "cy": 0.5, "size": 0.85, "aspect": 1.0,
                 "softness": 0.6, "strength": 0.85, "color": "#000000"},
    "region": {"mode": "blur", "shape": "ellipse", "cx": 0.5, "cy": 0.4, "w": 0.15, "h": 0.25,
               "strength": 1.0, "feather": 0.15, "color": "#000000"},
    "blur": {"amount": 0.3},
    "sharpen": {"amount": 0.5},
}

LOOK_LABELS = {
    "retro_pixel": "Retro pixel (8-bit)", "sepia_flashback": "Sepia flashback", "night_vision": "Night vision",
    "glitch": "Glitch", "crt": "Old CRT screen", "vhs": "VHS tape", "black_white": "Black & white",
    "comic": "Comic / cel-shaded", "thermal": "Thermal camera", "dream": "Dreamy glow",
}


# ------------------------------------------------------------------ effects
def color_adjust(img, p):
    xp = xp_of(img)
    b, c, s = p.get("brightness", 0), p.get("contrast", 1), p.get("saturation", 1)
    temp, tint, gamma = p.get("temperature", 0), p.get("tint", 0), p.get("gamma", 1)
    out = img
    if gamma != 1:
        out = xp.clip(out, 0, 1) ** (1.0 / gamma)
    if c != 1 or b != 0:
        out = (out - 0.5) * c + 0.5 + b * 0.5
    if s != 1:
        lum = luminance(out)[..., None]
        out = lum + (out - lum) * s
    if temp or tint:
        m = xp.asarray(np.array([1 + 0.25 * temp - 0.05 * tint, 1 - 0.18 * tint, 1 - 0.25 * temp - 0.05 * tint],
                                dtype=np.float32))
        out = out * m
    return xp.clip(out, 0, 1).astype(xp.float32)


_THERMAL_LUT = None


def _thermal_lut():
    global _THERMAL_LUT
    if _THERMAL_LUT is None:
        g = np.arange(256, dtype=np.uint8).reshape(-1, 1)
        lut = cv2.applyColorMap(g, cv2.COLORMAP_INFERNO)[:, 0, ::-1].astype(np.float32) / 255
        _THERMAL_LUT = lut
    return _THERMAL_LUT


def look(img, p, t: float = 0.0):
    xp = xp_of(img)
    preset = p.get("preset", "retro_pixel")
    strength = float(p.get("strength", 1.0))
    amount = float(p.get("amount", 0.5))
    if strength <= 0:
        return img
    h, w = img.shape[:2]
    scale = h / 1080.0
    out = img
    if preset == "retro_pixel":
        block = max(2, int((3 + amount * 18) * scale))
        small = resize(img, w // block, h // block)
        levels = int(3 + (1 - amount) * 6)
        small = xp.floor(small * levels + 0.5) / levels
        out = resize(small, w, h, nearest=True)
    elif preset == "sepia_flashback":
        lum = luminance(img)
        sep = xp.stack([lum * 1.07 + 0.08, lum * 0.92 + 0.04, lum * 0.70], axis=-1)
        sep = sep + _noise(h, w, int(t * 24), xp, 0.04 * (0.5 + amount))[..., None]
        xs, ys = grid(h, w, xp)
        d = xp.sqrt((xs - 0.5) ** 2 + (ys - 0.5) ** 2)
        vig = 1 - smoothstep(0.35, 0.85, d, xp) * 0.7
        soft = gblur(sep, 3 * scale + amount * 6 * scale)
        edge = smoothstep(0.25, 0.6, d, xp)[..., None]
        out = (sep * (1 - edge) + soft * edge) * vig[..., None]
    elif preset == "night_vision":
        lum = luminance(img)
        lum = xp.clip(lum * (1.6 + amount * 1.5), 0, 1)
        lum = lum + _noise(h, w, int(t * 30), xp, 0.07 + 0.08 * amount)
        rows = (xp.arange(h) // max(1, int(3 * scale))) % 2
        lum = lum * (1 - 0.18 * rows[:, None])
        out = xp.stack([lum * 0.25, lum * 1.0, lum * 0.3], axis=-1)
        xs, ys = grid(h, w, xp)
        d = xp.sqrt(((xs - 0.5) * w / h) ** 2 + (ys - 0.5) ** 2)
        out = out * (1 - smoothstep(0.45, 0.75, d, xp))[..., None]
    elif preset == "glitch":
        bucket = int(t * 12)
        rng = np.random.default_rng(bucket * 7919 + 13)
        burst = rng.random() < (0.25 + 0.6 * amount)
        dx = int((0.004 + 0.02 * amount * (2.5 if burst else 0.5)) * w)
        out = img.copy()
        out[..., 0] = xp.roll(img[..., 0], dx, axis=1)
        out[..., 2] = xp.roll(img[..., 2], -dx, axis=1)
        if burst:
            for _ in range(int(3 + 10 * amount)):
                y0 = int(rng.integers(0, h - 2))
                bh = int(rng.integers(2, max(3, int(h * 0.08))))
                shift = int(rng.integers(-int(w * 0.12), int(w * 0.12) + 1))
                out[y0:y0 + bh] = xp.roll(out[y0:y0 + bh], shift, axis=1)
                if rng.random() < 0.25:
                    out[y0:y0 + bh] = 1 - out[y0:y0 + bh]
        rows = (xp.arange(h) % max(2, int(4 * scale))) == 0
        out = out * (1 - 0.15 * rows[:, None, None])
    elif preset == "crt":
        rows = (xp.arange(h) % max(2, int(3 * scale))) == 0
        out = img * (1 - (0.35 + 0.3 * amount) * rows[:, None, None])
        cols = xp.arange(w) % 3
        mask = xp.stack([(cols == 0), (cols == 1), (cols == 2)], axis=-1).astype(xp.float32)
        out = out * (0.82 + 0.18 * mask[None, :, :]) * 1.12
        out = out + gblur(img, 6 * scale) * 0.18
        xs, ys = grid(h, w, xp)
        d = xp.sqrt((xs - 0.5) ** 2 + (ys - 0.5) ** 2)
        out = out * (1 - smoothstep(0.4, 0.8, d, xp) * 0.6)[..., None]
    elif preset == "vhs":
        r = gblur(xp.roll(img[..., 0:1], int(3 * scale), axis=1), 3 * scale, horizontal_only=True)
        g = img[..., 1:2]
        b = gblur(xp.roll(img[..., 2:3], -int(2 * scale), axis=1), 5 * scale, horizontal_only=True)
        out = xp.concatenate([r, g, b], axis=-1)
        lum = luminance(out)[..., None]
        out = lum + (out - lum) * 0.8
        out = out + _noise(h, w, int(t * 30), xp, 0.035 + 0.05 * amount)[..., None]
        band_y = int(((t * 0.37) % 1.0) * h)
        bh = max(2, int(h * 0.02 * (0.5 + amount)))
        out[band_y:band_y + bh] = out[band_y:band_y + bh] * 0.6 + 0.35
        out = (out - 0.5) * 0.9 + 0.52
    elif preset == "black_white":
        lum = luminance(img)
        lum = xp.clip((lum - 0.5) * (1 + amount) + 0.5, 0, 1)
        out = xp.stack([lum, lum, lum], axis=-1)
    elif preset == "comic":
        levels = int(3 + (1 - amount) * 4)
        sm = gblur(img, 1.5 * scale)
        post = xp.floor(sm * levels + 0.5) / levels
        lum8 = (xp_to_np(luminance(sm)) * 255).astype(np.uint8)
        edges = cv2.Canny(lum8, 60, 140)
        edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=max(1, int(scale)))
        e = xp.asarray(edges.astype(np.float32) / 255.0)
        out = post * (1 - e[..., None])
        lum = luminance(out)[..., None]
        out = lum + (out - lum) * 1.4
    elif preset == "thermal":
        lum = xp.clip(luminance(gblur(img, 2 * scale)) * (0.8 + amount * 0.6), 0, 1)
        lut = xp.asarray(_thermal_lut())
        idx = (lum * 255).astype(xp.int32)
        out = lut[idx]
    elif preset == "dream":
        glow = gblur(img, (8 + 20 * amount) * scale)
        out = 1 - (1 - img) * (1 - glow * 0.6)
        out = color_adjust(out, {"saturation": 1.15, "temperature": 0.2, "brightness": 0.03})
    out = xp.clip(out, 0, 1).astype(xp.float32)
    if strength < 1:
        out = img * (1 - strength) + out * strength
    return out


def xp_to_np(a):
    if _is_gpu(a):
        return xp_of(a).asnumpy(a)
    return a


def vignette(img, p):
    xp = xp_of(img)
    h, w = img.shape[:2]
    shape = p.get("shape", "oval")
    size = float(p.get("size", 0.85))
    aspect = float(p.get("aspect", 1.0))
    soft = float(p.get("softness", 0.6))
    strength = float(p.get("strength", 0.85))
    if strength <= 0:
        return img
    cx, cy = float(p.get("cx", 0.5)), float(p.get("cy", 0.5))
    if shape == "circle":
        sh = size
        sw = size * h / w * aspect
    elif shape == "rectangle":
        sw, sh = size * aspect, size
    else:  # oval follows picture shape
        sw, sh = size * 1.25 * aspect, size * 1.25
    inside = shape_mask(h, w, xp, "rectangle" if shape == "rectangle" else "ellipse",
                        cx, cy, sw, sh, 0.02 + soft * 0.9)
    keep = (1.0 - (1.0 - inside) * strength)[..., None]
    col = hex_to_rgb(p.get("color", "#000000"))
    if col == (0.0, 0.0, 0.0):
        return img * keep
    colv = xp.asarray(np.array(col, dtype=np.float32))
    return img * keep + colv * (1.0 - keep)


def region(img, p):
    xp = xp_of(img)
    h, w = img.shape[:2]
    mode = p.get("mode", "blur")
    strength = float(p.get("strength", 1.0))
    m = shape_mask(h, w, xp, p.get("shape", "ellipse"), float(p.get("cx", 0.5)), float(p.get("cy", 0.5)),
                   float(p.get("w", 0.15)), float(p.get("h", 0.25)), float(p.get("feather", 0.15)) * 0.5)
    m = m[..., None]
    if mode == "blur":
        alt = gblur(img, (6 + 40 * strength) * h / 1080)
        return img * (1 - m) + alt * m
    if mode == "pixelate":
        b = max(2, int((6 + 40 * strength) * h / 1080))
        alt = resize(resize(img, w // b, h // b), w, h, nearest=True)
        return img * (1 - m) + alt * m
    if mode == "solid":
        col = xp.asarray(np.array(hex_to_rgb(p.get("color", "#000000")), dtype=np.float32))
        mm = m * strength
        return img * (1 - mm) + col * mm
    if mode == "highlight":
        bright = xp.clip(img * (1 + 0.35 * strength) + 0.05 * strength, 0, 1)
        dark = img * (1 - 0.55 * strength)
        return dark * (1 - m) + bright * m
    if mode == "spotlight":
        lum = luminance(img)[..., None]
        outside = (lum * 0.6 + img * 0.4) * (1 - 0.6 * strength)
        return outside * (1 - m) + img * m
    return img


def blur_all(img, p):
    a = float(p.get("amount", 0.3))
    return gblur(img, a * 30 * img.shape[0] / 1080)


def sharpen(img, p):
    xp = xp_of(img)
    a = float(p.get("amount", 0.5))
    soft = gblur(img, 2.0 * img.shape[0] / 1080)
    return xp.clip(img + (img - soft) * a, 0, 1)


def apply_effect(img, fx_type, params, t=0.0):
    if fx_type == "color":
        return color_adjust(img, params)
    if fx_type == "look":
        return look(img, params, t)
    if fx_type == "vignette":
        return vignette(img, params)
    if fx_type == "region":
        return region(img, params)
    if fx_type == "blur":
        return blur_all(img, params)
    if fx_type == "sharpen":
        return sharpen(img, params)
    return img


# ------------------------------------------------------------------ transitions
TRANSITIONS = ["none", "fade", "dip_black", "dip_white", "wipe_left", "wipe_right", "wipe_up", "wipe_down",
               "iris", "pixelate", "glitch", "zoom", "slide_left", "slide_right"]
TRANSITION_LABELS = {
    "none": "None", "fade": "Cross-fade", "dip_black": "Dip to black", "dip_white": "Flash (dip to white)",
    "wipe_left": "Wipe ←", "wipe_right": "Wipe →", "wipe_up": "Wipe ↑", "wipe_down": "Wipe ↓",
    "iris": "Iris circle (retro)", "pixelate": "Pixel dissolve", "glitch": "Glitch", "zoom": "Zoom in",
    "slide_left": "Slide in ←", "slide_right": "Slide in →",
}


def transition_mix(a, b, p: float, ttype: str, t: float = 0.0):
    """a = picture before, b = picture after, p goes 0 -> 1."""
    xp = xp_of(a)
    p = float(max(0.0, min(1.0, p)))
    h, w = a.shape[:2]
    if ttype in ("fade", "none"):
        return a * (1 - p) + b * p
    if ttype in ("dip_black", "dip_white"):
        c = 0.0 if ttype == "dip_black" else 1.0
        if p < 0.5:
            q = p * 2
            return a * (1 - q) + c * q
        q = (p - 0.5) * 2
        return b * q + c * (1 - q)
    if ttype.startswith("wipe"):
        xs, ys = grid(h, w, xp)
        soft = 0.04
        if ttype == "wipe_left":
            m = smoothstep(-soft, soft, p * (1 + 2 * soft) - soft - (1 - xs), xp)
        elif ttype == "wipe_right":
            m = smoothstep(-soft, soft, p * (1 + 2 * soft) - soft - xs, xp)
        elif ttype == "wipe_up":
            m = smoothstep(-soft, soft, p * (1 + 2 * soft) - soft - (1 - ys), xp)
        else:
            m = smoothstep(-soft, soft, p * (1 + 2 * soft) - soft - ys, xp)
        m = xp.broadcast_to(m, (h, w))[..., None]
        return a * (1 - m) + b * m
    if ttype == "iris":
        xs, ys = grid(h, w, xp)
        d = xp.sqrt(((xs - 0.5) * w / h) ** 2 + (ys - 0.5) ** 2)
        r = p * 1.05
        m = (1 - smoothstep(r - 0.01, r + 0.01, d, xp))[..., None]
        return a * (1 - m) + b * m
    if ttype == "pixelate":
        k = 1 - abs(p - 0.5) * 2
        block = max(1, int(k * 60 * h / 1080))
        src = a if p < 0.5 else b
        if block > 1:
            src = resize(resize(src, max(1, w // block), max(1, h // block)), w, h, nearest=True)
        return src
    if ttype == "glitch":
        k = 1 - abs(p - 0.5) * 2
        src = a if p < 0.5 else b
        return look(src, {"preset": "glitch", "strength": 1.0, "amount": min(1.0, k * 1.5)}, t * 3)
    if ttype == "zoom":
        s = 1.0 + (1 - p) * 0.35
        zw, zh = int(w / s), int(h / s)
        x0, y0 = (w - zw) // 2, (h - zh) // 2
        zb = resize(b[y0:y0 + zh, x0:x0 + zw], w, h)
        return a * (1 - p) + zb * p
    if ttype in ("slide_left", "slide_right"):
        e = 1 - (1 - p) ** 3
        off = int((1 - e) * w)
        out = a.copy()
        if ttype == "slide_left":
            if off < w:
                out[:, off:] = b[:, :w - off]
        else:
            if off < w:
                out[:, :w - off] = b[:, off:]
        return out
    return a * (1 - p) + b * p
