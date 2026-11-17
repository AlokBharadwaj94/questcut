"""Timeline edits that act on the whole movie: split, insert time, remove time, groups.

Two kinds of pieces behave differently when time is inserted or removed in the middle of them:
  * "cut" pieces (camera clips, pictures, cards, normal sounds) are cut there, like scissors;
  * "stretch" pieces (HUD elements, effect layers, looping music) simply get longer or shorter,
    so a frame, a health bar or the music keeps going over the new part.
"""
from __future__ import annotations

import copy
from dataclasses import asdict

from .model import Clip, new_id

EPS = 1e-4


def is_stretch(c):
    return c.kind in ("hud", "adjust") or bool(c.kind == "audio" and c.props.get("loop"))


def _resampled(c, key, t0, t1, step=0.1, shift=0.0, ease="smooth"):
    """Sample points of a curved stretch. Straight or stepped stretches need none,
    and points that lie on a straight line between their neighbours are dropped."""
    if ease in ("linear", "hold"):
        return []
    pts, t = [], t0
    while t < t1 - 1e-6:
        pts.append((t, c.value(key, t)))
        t += step
    pts.append((t1, c.value(key, t1)))
    if len(pts) < 3 or not all(isinstance(v, (int, float)) for _, v in pts):
        return [[round(t - shift, 4), v, "linear"] for t, v in pts[1:-1]]
    span = (max(v for _, v in pts) - min(v for _, v in pts)) or 1.0
    tol = 0.001 * span
    keep_idx = {0, len(pts) - 1}

    def rdp(i, j):                      # Ramer-Douglas-Peucker: keep the point that strays most
        (ta, va), (tb, vb) = pts[i], pts[j]
        worst, wi = 0.0, None
        for k in range(i + 1, j):
            tk, vk = pts[k]
            d = abs(va + (vb - va) * (tk - ta) / max(1e-9, tb - ta) - vk)
            if d > worst:
                worst, wi = d, k
        if wi is not None and worst > tol:
            keep_idx.add(wi)
            rdp(i, wi)
            rdp(wi, j)
    rdp(0, len(pts) - 1)
    keep = [pts[i] for i in sorted(keep_idx) if 0 < i < len(pts) - 1]
    return [[round(t - shift, 4), v, "linear"] for t, v in keep]


def cut_keys(c, key, a, b, end=None):
    """Keyframes of `key` with the time a..b taken out (later keys move back by b-a).
    The animation before a and after b stays as it was: the stretches next to the cut
    are sampled every 0.1 s. With end set, everything after `end` is dropped instead."""
    keys = sorted(c.keyframes.get(key, []), key=lambda k: k[0])
    if not keys:
        return []
    gap = b - a
    prev = [list(k) for k in keys if k[0] < a - 1e-6]
    nxt = [k for k in keys if k[0] > b + 1e-6]
    out = prev
    if prev:
        ease = prev[-1][2] if len(prev[-1]) > 2 else "smooth"
        if ease != "hold":
            out[-1] = [prev[-1][0], prev[-1][1], "linear"]
        out += _resampled(c, key, prev[-1][0], a, ease=ease)
    va, vb = c.value(key, a), c.value(key, b)
    if a > 1e-6:
        out.append([round(a - 0.001, 4), va, "hold"])
    out.append([round(a, 4), vb, "linear"])
    if nxt:
        before_b = [k for k in keys if k[0] <= b + 1e-6]
        ease = (before_b[-1][2] if len(before_b[-1]) > 2 else "smooth") if before_b else "hold"
        out[-1][2] = "hold" if ease == "hold" else "linear"
        out += _resampled(c, key, b, nxt[0][0], shift=gap, ease=ease)
        out += [[round(k[0] - gap, 4), k[1], k[2] if len(k) > 2 else "smooth"] for k in nxt]
    return out


def keys_until(c, key, rel):
    keys = sorted(c.keyframes.get(key, []), key=lambda k: k[0])
    prev = [list(k) for k in keys if k[0] < rel - 1e-3]
    out = prev
    if prev:
        ease = prev[-1][2] if len(prev[-1]) > 2 else "smooth"
        if ease != "hold":
            out[-1] = [prev[-1][0], prev[-1][1], "linear"]
        out += _resampled(c, key, prev[-1][0], rel, ease=ease)
    return out + [[round(rel, 4), c.value(key, rel), "linear"]]


def split_clip(track, c, t):
    """Cut clip c at movie time t. Returns the new right-hand piece (or None)."""
    if not (c.start + 0.01 < t < c.end - 0.01):
        return None
    rel = t - c.start
    right = Clip(**copy.deepcopy(asdict(c)))
    right.id = new_id("c")
    right.start = round(t, 4)
    right.duration = round(c.end - t, 4)
    if not c.freeze and c.media_id and c.kind in ("video", "audio"):
        speed = float(c.props.get("speed", 1.0) or 1.0)
        right.source_in = c.source_in + rel * speed
    left_k = {k: keys_until(c, k, rel) for k in c.keyframes}
    right_k = {k: cut_keys(c, k, 0.0, rel) for k in c.keyframes}
    c.keyframes, right.keyframes = left_k, right_k
    c.duration = round(rel, 4)
    c.transition_out = {"type": "none", "duration": 0.5}
    right.transition_in = {"type": "none", "duration": 0.5}
    c.props.pop("fade_out", None)
    right.props.pop("fade_in", None)
    track.clips.append(right)
    track.sort()
    return right


def trim_left(c, new_start):
    """Move the start of c later to new_start, keeping the rest exactly where it was."""
    delta = new_start - c.start
    if delta <= 0:
        return
    if not c.freeze and c.media_id and c.kind in ("video", "audio"):
        speed = float(c.props.get("speed", 1.0) or 1.0)
        c.source_in = round(c.source_in + delta * speed, 4)
    c.keyframes = {k: cut_keys(c, k, 0.0, delta) for k in c.keyframes}
    c.start = round(new_start, 4)
    c.duration = round(c.duration - delta, 4)
    c.transition_in = {"type": "none", "duration": 0.5}


def _shift_keys_after(c, rel, amount):
    for key, keys in c.keyframes.items():
        c.keyframes[key] = [[k[0] + amount if k[0] >= rel else k[0], k[1], k[2] if len(k) > 2 else "smooth"]
                            for k in keys]


def insert_time(project, t, dur, skip=()):
    """Push everything at or after t later by dur, on every unlocked track.
    Returns the number of pieces that moved, were cut or got longer."""
    if dur <= 0:
        return 0
    n = 0
    for tr in project.tracks:
        if tr.locked:
            continue
        for c in list(tr.clips):
            if c.id in skip:
                continue
            if c.start >= t - EPS:
                c.start = round(c.start + dur, 4)
                n += 1
            elif c.end > t + 0.01:                       # t is inside this piece
                if is_stretch(c):
                    _shift_keys_after(c, t - c.start, dur)
                    c.duration = round(c.duration + dur, 4)
                else:
                    right = split_clip(tr, c, t)
                    if right is not None:
                        right.start = round(right.start + dur, 4)
                n += 1
        tr.sort()
    return n


def remove_time(project, a, b):
    """Cut the stretch a..b out of the whole movie (every unlocked track) and close it up.
    Returns the number of pieces changed."""
    a, b = max(0.0, min(a, b)), max(a, b)
    gap = b - a
    if gap <= 0.005:
        return 0
    n = 0
    for tr in project.tracks:
        if tr.locked:
            continue
        for c in list(tr.clips):
            s, e = c.start, c.end
            if e <= a + EPS:                              # before: untouched
                continue
            if s >= b - EPS:                              # after: slides left
                c.start = round(s - gap, 4)
                n += 1
            elif s >= a - EPS and e <= b + EPS:           # completely inside: removed
                tr.clips.remove(c)
                n += 1
            elif s < a and e > b:                         # covers the whole stretch
                if is_stretch(c):
                    rel_a, rel_b = a - s, b - s
                    c.keyframes = {k: cut_keys(c, k, rel_a, rel_b) for k in c.keyframes}
                    c.duration = round(c.duration - gap, 4)
                else:
                    right = split_clip(tr, c, b)
                    c.duration = round(a - s, 4)
                    if right is not None:
                        right.start = round(a, 4)
                n += 1
            elif s < a:                                   # sticks into the stretch from the left
                c.duration = round(a - s, 4)
                c.props.pop("fade_out", None)
                n += 1
            else:                                         # starts inside, ends after
                trim_left(c, b)
                c.start = round(a, 4)
                n += 1
        tr.sort()
    return n


# ------------------------------------------------------------------ groups
def group_of(c):
    return c.props.get("group") or None


def group_members(project, gid):
    return [c for c in project.all_clips() if gid and c.props.get("group") == gid]


def make_group(clips):
    gid = new_id("g")
    for c in clips:
        c.props["group"] = gid
    return gid


def ungroup(clips):
    for c in clips:
        c.props.pop("group", None)


def renew_groups(clips):
    """Copies get their own new groups (so a pasted fight is not tied to the original)."""
    remap = {}
    for c in clips:
        g = c.props.get("group")
        if g:
            c.props["group"] = remap.setdefault(g, new_id("g"))
