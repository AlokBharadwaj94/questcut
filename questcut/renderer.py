"""Builds one finished picture of the movie at a given time.

Order: video tracks bottom to top (with transitions, picture-in-picture,
effects) -> screen shake from spells -> HUD tracks (overlays, adjustment
layers). The same code is used for the live preview and the final export,
so what you see is what you get.
"""
from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtGui import QImage, QPainter

from . import effects as fx
from .backend import CPU, ArrayBackend
from .cards import render_card
from .hud import SpellLinks, draw_hud_clip, spell_shake


def clip_effect_params(clip, f, t_rel):
    return {k: clip.value(f"fx.{f['id']}.{k}", t_rel, v) for k, v in f["params"].items()}


def source_time(clip, t_rel: float) -> float:
    if clip.freeze:
        return clip.source_in
    speed = float(clip.props.get("speed", 1.0) or 1.0)
    return clip.source_in + max(0.0, t_rel) * speed


class Renderer:
    def __init__(self, project, pool, backend: ArrayBackend = CPU, preview: bool = True):
        self.project = project
        self.pool = pool
        self.be = backend
        self.preview = preview

    # ------------------------------------------------------------- public
    def render(self, t: float, W: int, H: int) -> np.ndarray:
        xp = self.be.xp
        canvas = xp.zeros((H, W, 3), dtype=xp.float32)
        tracks = self.project.visual_tracks_bottom_up()
        vids = [tr for tr in tracks if tr.kind == "video"]
        huds = [tr for tr in tracks if tr.kind == "hud"]
        for tr in vids:
            if tr.hidden:
                continue
            clip = tr.clip_at(t)
            if clip is None:
                # still draw the tail of a clip that is fading out into nothing? (handled by transition_out)
                continue
            canvas = self._clip_with_transitions(tr, clip, t, canvas, W, H)
        # screen shake from spells
        sx = sy = 0
        for tr in huds:
            if tr.hidden:
                continue
            for c in tr.clips_at(t):
                if c.kind == "hud" and c.hud_type == "spell":
                    dx, dy = spell_shake(c, t - c.start, W, H)
                    sx += dx
                    sy += dy
        if sx or sy:
            canvas = self._shift(canvas, sx, sy)
        active_hud = any(c.kind in ("hud", "adjust") for tr in huds if not tr.hidden for c in tr.clips_at(t))
        if not active_hud:
            return self._to_uint8(canvas)
        return self._huds(huds, t, canvas, W, H)

    def _to_uint8(self, canvas):
        xp = self.be.xp
        if self.be.is_gpu:
            out = xp.clip(canvas * 255.0 + 0.5, 0, 255).astype(xp.uint8)
            return self.be.to_numpy(out)
        np.maximum(canvas, 0, out=canvas)
        return cv2.convertScaleAbs(canvas, alpha=255.0)

    # ------------------------------------------------------------- video layers
    def _clip_with_transitions(self, track, clip, t, canvas, W, H):
        t_rel = t - clip.start
        tin, tout = clip.transition_in or {}, clip.transition_out or {}
        din = float(tin.get("duration", 0.5) or 0)
        dout = float(tout.get("duration", 0.5) or 0)
        if tin.get("type", "none") != "none" and din > 0 and t_rel < din:
            lower = canvas
            prev = self._prev_adjacent(track, clip)
            if prev is not None:
                lower = self._composite(prev, t - prev.start, canvas.copy(), W, H)
            upper = self._composite(clip, t_rel, canvas.copy(), W, H)
            return fx.transition_mix(lower, upper, t_rel / din, tin["type"], t)
        if tout.get("type", "none") != "none" and dout > 0 and t_rel > clip.duration - dout:
            nxt = self._next_adjacent(track, clip)
            if nxt is not None and (nxt.transition_in or {}).get("type", "none") != "none":
                return self._composite(clip, t_rel, canvas, W, H)
            upper = self._composite(clip, t_rel, canvas.copy(), W, H)
            q = 1 - (clip.duration - t_rel) / dout
            return fx.transition_mix(upper, canvas, q, tout["type"], t)
        return self._composite(clip, t_rel, canvas, W, H)

    def _prev_adjacent(self, track, clip):
        best = None
        for c in track.clips:
            if c is clip or not c.enabled:
                continue
            if abs(c.end - clip.start) < 0.05 and (best is None or c.start > best.start):
                best = c
        return best

    def _next_adjacent(self, track, clip):
        for c in track.clips:
            if c is not clip and c.enabled and abs(c.start - clip.end) < 0.05:
                return c
        return None

    def _frame_for(self, clip, t_rel, W, H):
        """Returns (rgb uint8/float numpy, alpha numpy|None)."""
        if clip.kind == "card":
            return render_card(clip, max(0.0, t_rel), W, H), None
        if clip.kind == "image":
            img = self.pool.image(clip.media_id)
            if img is None:
                return None, None
            return img[..., :3], (img[..., 3] if img.shape[2] == 4 and img[..., 3].min() < 255 else None)
        scale = float(clip.value("scale", t_rel, 1.0))
        max_h = int(H * max(1.0, scale) * 1.05) if self.preview else 0
        frame = self.pool.frame(clip.media_id, source_time(clip, t_rel), max_h)
        return frame, None

    def _composite(self, clip, t_rel, canvas, W, H):
        xp = self.be.xp
        rgb, alpha = self._frame_for(clip, t_rel, W, H)
        if rgb is None:
            return canvas
        pr = clip.props
        # rotate / flip / crop on the source picture
        rot = int(pr.get("rotate", 0) or 0) % 360
        if rot:
            k = {90: -1, 180: 2, 270: 1}.get(rot, 0)
            rgb = np.rot90(rgb, k)
            if alpha is not None:
                alpha = np.rot90(alpha, k)
        if pr.get("flip_h"):
            rgb = rgb[:, ::-1]
            alpha = alpha[:, ::-1] if alpha is not None else None
        if pr.get("flip_v"):
            rgb = rgb[::-1]
            alpha = alpha[::-1] if alpha is not None else None
        fh, fw = rgb.shape[:2]
        cl, cr = float(clip.value("crop_l", t_rel, 0)), float(clip.value("crop_r", t_rel, 0))
        ct, cb = float(clip.value("crop_t", t_rel, 0)), float(clip.value("crop_b", t_rel, 0))
        if cl or cr or ct or cb:
            x0, x1 = int(fw * cl), max(int(fw * cl) + 2, int(fw * (1 - cr)))
            y0, y1 = int(fh * ct), max(int(fh * ct) + 2, int(fh * (1 - cb)))
            rgb = rgb[y0:y1, x0:x1]
            alpha = alpha[y0:y1, x0:x1] if alpha is not None else None
            fh, fw = rgb.shape[:2]
        mask_kind = pr.get("mask", "none")
        if mask_kind == "circle":
            side = min(fh, fw)
            oy, ox = (fh - side) // 2, (fw - side) // 2
            rgb = rgb[oy:oy + side, ox:ox + side]
            alpha = alpha[oy:oy + side, ox:ox + side] if alpha is not None else None
            fh, fw = side, side
        # size and position
        fit = pr.get("fit", "fit")
        base = max(W / fw, H / fh) if fit == "fill" else min(W / fw, H / fh)
        scale = float(clip.value("scale", t_rel, 1.0))
        lw, lh = max(2, int(round(fw * base * scale))), max(2, int(round(fh * base * scale)))
        cx = W / 2 + float(clip.value("x", t_rel, 0.0)) * W
        cy = H / 2 + float(clip.value("y", t_rel, 0.0)) * H
        dx0, dy0 = int(round(cx - lw / 2)), int(round(cy - lh / 2))
        vx0, vy0 = max(0, dx0), max(0, dy0)
        vx1, vy1 = min(W, dx0 + lw), min(H, dy0 + lh)
        if vx1 <= vx0 or vy1 <= vy0:
            return canvas
        sx0 = (vx0 - dx0) / lw * fw
        sx1 = (vx1 - dx0) / lw * fw
        sy0 = (vy0 - dy0) / lh * fh
        sy1 = (vy1 - dy0) / lh * fh
        src = rgb[int(sy0):max(int(sy0) + 1, int(np.ceil(sy1))), int(sx0):max(int(sx0) + 1, int(np.ceil(sx1)))]
        tw, th = vx1 - vx0, vy1 - vy0
        if src.shape[1] != tw or src.shape[0] != th:
            src = fx.resize(np.ascontiguousarray(src), tw, th)
        layer = xp.asarray(np.ascontiguousarray(src)).astype(xp.float32) * (1.0 / 255.0)
        a = None
        if alpha is not None:
            asrc = alpha[int(sy0):max(int(sy0) + 1, int(np.ceil(sy1))), int(sx0):max(int(sx0) + 1, int(np.ceil(sx1)))]
            if asrc.shape[1] != tw or asrc.shape[0] != th:
                asrc = fx.resize(np.ascontiguousarray(asrc), tw, th)
            a = xp.asarray(asrc).astype(xp.float32)[..., None] * (1.0 / 255.0)
        # effects
        for f in clip.effects:
            if not f.get("enabled", True):
                continue
            try:
                layer = fx.apply_effect(layer, f["type"], clip_effect_params(clip, f, t_rel), t_rel + clip.start)
            except Exception as e:  # never let one effect break the whole picture
                print("effect error", f["type"], e)
        # picture-in-picture shape and border
        if mask_kind in ("circle", "rounded"):
            shape = "ellipse" if mask_kind == "circle" else "rectangle"
            m = fx.shape_mask(th, tw, xp, shape, 0.5, 0.5, 1.0, 1.0, 0.01)[..., None]
            bw = float(pr.get("border", 0) or 0) * H / 1080
            if bw > 0:
                inner = fx.shape_mask(th, tw, xp, shape, 0.5, 0.5, 1 - 2 * bw / tw, 1 - 2 * bw / th, 0.01)[..., None]
                col = xp.asarray(np.array(fx.hex_to_rgb(pr.get("border_color", "#ffffff")), dtype=np.float32))
                ring = m - inner
                layer = layer * (1 - ring) + col * ring
            a = m if a is None else a * m
        elif float(pr.get("border", 0) or 0) > 0:
            b = max(1, int(float(pr["border"]) * H / 1080))
            col = xp.asarray(np.array(fx.hex_to_rgb(pr.get("border_color", "#ffffff")), dtype=np.float32))
            layer = layer.copy()
            layer[:b] = col
            layer[-b:] = col
            layer[:, :b] = col
            layer[:, -b:] = col
        opacity = float(clip.value("opacity", t_rel, 1.0))
        if a is None and opacity >= 0.999 and tw == W and th == H:
            return layer
        region = canvas[vy0:vy1, vx0:vx1]
        if a is None:
            if opacity >= 0.999:
                canvas[vy0:vy1, vx0:vx1] = layer
            else:
                canvas[vy0:vy1, vx0:vx1] = region * (1 - opacity) + layer * opacity
        else:
            aa = a * opacity
            canvas[vy0:vy1, vx0:vx1] = region * (1 - aa) + layer * aa
        return canvas

    def _shift(self, canvas, sx, sy):
        xp = self.be.xp
        out = xp.zeros_like(canvas)
        H, W = canvas.shape[:2]
        sx, sy = max(-W + 1, min(W - 1, sx)), max(-H + 1, min(H - 1, sy))
        ys, yd = (slice(0, H - sy), slice(sy, H)) if sy >= 0 else (slice(-sy, H), slice(0, H + sy))
        xs, xd = (slice(0, W - sx), slice(sx, W)) if sx >= 0 else (slice(-sx, W), slice(0, W + sx))
        out[yd, xd] = canvas[ys, xs]
        return out

    # ------------------------------------------------------------- HUD
    # HUD elements are painted straight onto an 8-bit copy of the picture with
    # QPainter (fast, done in C++). Adjustment layers switch back to float.
    def _huds(self, huds, t, canvas, W, H):
        links = SpellLinks(self.project)
        rgb8 = self._to_uint8(canvas)
        buf = cv2.cvtColor(rgb8, cv2.COLOR_RGB2BGRA)
        img = QImage(buf.data, W, H, W * 4, QImage.Format.Format_RGB32)
        painter = None
        for tr in huds:
            if tr.hidden:
                continue
            for c in sorted(tr.clips_at(t), key=lambda c: c.start):
                t_rel = t - c.start
                if c.kind == "adjust":
                    if painter is not None:
                        painter.end()
                        painter = None
                    fl = self.be.asarray(cv2.cvtColor(buf, cv2.COLOR_BGRA2RGB)).astype(self.be.xp.float32) * (1 / 255.0)
                    fl = self._adjust(c, t_rel, fl)
                    buf = cv2.cvtColor(self._to_uint8(fl), cv2.COLOR_RGB2BGRA)
                    img = QImage(buf.data, W, H, W * 4, QImage.Format.Format_RGB32)
                    continue
                if c.kind != "hud":
                    continue
                if painter is None:
                    painter = QPainter(img)
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
                try:
                    draw_hud_clip(painter, c, t_rel, W, H, self.pool, links)
                except Exception as e:
                    print("HUD error", c.hud_type, e)
        if painter is not None:
            painter.end()
        del img
        return cv2.cvtColor(buf, cv2.COLOR_BGRA2RGB)

    def _adjust(self, clip, t_rel, canvas):
        before = canvas
        out = canvas
        for f in clip.effects:
            if not f.get("enabled", True):
                continue
            try:
                out = fx.apply_effect(out, f["type"], clip_effect_params(clip, f, t_rel), t_rel + clip.start)
            except Exception as e:
                print("effect error", f["type"], e)
        op = float(clip.value("opacity", t_rel, 1.0))
        # fade adjustment layers in/out a little so they don't pop
        d = float(clip.props.get("anim_dur", 0.0) or 0.0)
        if d > 0:
            op *= min(1.0, t_rel / d, (clip.duration - t_rel) / d)
        if op < 0.999:
            out = before * (1 - op) + out * op
        return out
