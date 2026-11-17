"""Project data model: tracks, clips, keyframes, save/load.

Everything is plain data so a project can be saved as JSON and moved
between Windows, Mac and Linux. Media paths are stored relative to the
project file when possible.
"""
from __future__ import annotations

import copy
import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any

APP_NAME = "QuestCut"
PROJECT_EXT = ".questcut"
FORMAT_VERSION = 1


def new_id(prefix: str = "") -> str:
    return prefix + uuid.uuid4().hex[:8]


# ---------------------------------------------------------------- keyframes
EASINGS = ["smooth", "linear", "hold"]


def _ease(p: float, mode: str) -> float:
    if mode == "hold":
        return 0.0
    if mode == "smooth":
        return p * p * (3 - 2 * p)
    return p


def interp_keys(keys: list, t: float, default: Any) -> Any:
    """keys: sorted list of [t, value, easing]. Easing applies to the segment
    that *starts* at that key."""
    if not keys:
        return default
    if t <= keys[0][0]:
        return keys[0][1]
    if t >= keys[-1][0]:
        return keys[-1][1]
    for i in range(len(keys) - 1):
        t0, v0, e0 = keys[i][0], keys[i][1], keys[i][2] if len(keys[i]) > 2 else "smooth"
        t1, v1 = keys[i + 1][0], keys[i + 1][1]
        if t0 <= t <= t1:
            if not isinstance(v0, (int, float)) or not isinstance(v1, (int, float)) or isinstance(v0, bool):
                return v0 if t < t1 else v1
            p = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            return v0 + (v1 - v0) * _ease(p, e0)
    return keys[-1][1]


# ---------------------------------------------------------------- data classes
@dataclass
class Clip:
    id: str
    kind: str                 # video | image | card | audio | hud | adjust
    start: float              # position on the timeline (seconds)
    duration: float
    name: str = ""
    media_id: str | None = None
    source_in: float = 0.0    # where in the source file this clip starts
    freeze: bool = False      # freeze-frame: always show source_in
    enabled: bool = True
    hud_type: str = ""
    props: dict = field(default_factory=dict)
    effects: list = field(default_factory=list)   # [{id,type,enabled,params}]
    keyframes: dict = field(default_factory=dict)  # key -> [[t_rel, value, easing]]
    transition_in: dict = field(default_factory=lambda: {"type": "none", "duration": 0.5})
    transition_out: dict = field(default_factory=lambda: {"type": "none", "duration": 0.5})

    @property
    def end(self) -> float:
        return self.start + self.duration

    def contains(self, t: float) -> bool:
        return self.start <= t < self.end

    # ---- values that may be keyframed
    def value(self, key: str, t_rel: float, default: Any = None) -> Any:
        """key is a prop name ("value", "x") or "fx.<effect_id>.<param>"."""
        keys = self.keyframes.get(key)
        if keys:
            return interp_keys(keys, t_rel, self.static_value(key, default))
        return self.static_value(key, default)

    def static_value(self, key: str, default: Any = None) -> Any:
        if key.startswith("fx."):
            _, fid, param = key.split(".", 2)
            fx = self.effect(fid)
            if fx is None:
                return default
            return fx["params"].get(param, default)
        return self.props.get(key, default)

    def set_static(self, key: str, val: Any) -> None:
        if key.startswith("fx."):
            _, fid, param = key.split(".", 2)
            fx = self.effect(fid)
            if fx is not None:
                fx["params"][param] = val
        else:
            self.props[key] = val

    def set_value(self, key: str, val: Any, t_rel: float | None = None) -> None:
        """If the key already has keyframes, edit/add a key at t_rel.
        Otherwise set the plain value."""
        keys = self.keyframes.get(key)
        if keys and t_rel is not None:
            self.add_keyframe(key, t_rel, val)
        else:
            self.set_static(key, val)

    def add_keyframe(self, key: str, t_rel: float, val: Any, easing: str = "smooth") -> None:
        t_rel = round(max(0.0, min(self.duration, t_rel)), 4)
        keys = self.keyframes.setdefault(key, [])
        for k in keys:
            if abs(k[0] - t_rel) < 1e-3:
                k[1] = val
                return
        keys.append([t_rel, val, easing])
        keys.sort(key=lambda k: k[0])

    def remove_keyframe(self, key: str, t_rel: float) -> bool:
        keys = self.keyframes.get(key, [])
        for k in list(keys):
            if abs(k[0] - t_rel) < 0.02:
                keys.remove(k)
                if not keys:
                    self.keyframes.pop(key, None)
                return True
        return False

    def keyframe_times(self) -> list[float]:
        ts = set()
        for keys in self.keyframes.values():
            for k in keys:
                ts.add(round(k[0], 3))
        return sorted(ts)

    def effect(self, fid: str):
        for fx in self.effects:
            if fx["id"] == fid:
                return fx
        return None

    def add_effect(self, ftype: str, params: dict | None = None) -> dict:
        from .effects import EFFECT_DEFAULTS
        p = copy.deepcopy(EFFECT_DEFAULTS.get(ftype, {}))
        if params:
            p.update(params)
        fx = {"id": new_id("fx"), "type": ftype, "enabled": True, "params": p}
        self.effects.append(fx)
        return fx

    @property
    def has_audio(self) -> bool:
        return self.kind in ("audio", "video")


@dataclass
class Track:
    id: str
    kind: str          # video | hud | audio
    name: str
    clips: list = field(default_factory=list)
    hidden: bool = False
    muted: bool = False
    locked: bool = False
    volume: float = 1.0
    duck: bool = False          # audio: lower this track while voice-over plays
    duck_db: float = -12.0
    is_voice: bool = False      # audio: this track triggers ducking

    def clip_at(self, t: float):
        best = None
        for c in self.clips:
            if c.enabled and c.contains(t):
                if best is None or c.start >= best.start:
                    best = c
        return best

    def clips_at(self, t: float):
        return [c for c in self.clips if c.enabled and c.contains(t)]

    def sort(self):
        self.clips.sort(key=lambda c: c.start)


@dataclass
class Media:
    id: str
    path: str                 # absolute at runtime
    kind: str                 # video | audio | image
    name: str = ""
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 30.0
    has_audio: bool = False
    rotation: int = 0
    generated: str = ""       # e.g. "sfx:coin" for built-in game sounds


@dataclass
class Project:
    name: str = "My PhD Movie"
    fps: float = 30.0
    width: int = 1920
    height: int = 1080
    sample_rate: int = 48000
    media: dict = field(default_factory=dict)
    tracks: list = field(default_factory=list)   # display order, top to bottom
    path: str = ""                               # file path (not saved)

    # ---- construction
    @classmethod
    def new_default(cls) -> "Project":
        p = cls()
        p.tracks = [
            Track(new_id("t"), "hud", "HUD 2"),
            Track(new_id("t"), "hud", "HUD 1"),
            Track(new_id("t"), "video", "V2  Camera B / PiP"),
            Track(new_id("t"), "video", "V1  Camera A"),
            Track(new_id("t"), "audio", "A1  Voice-over", is_voice=True),
            Track(new_id("t"), "audio", "A2  Game sounds"),
            Track(new_id("t"), "audio", "A3  Music", duck=True),
        ]
        return p

    # ---- lookup helpers
    @property
    def folder(self) -> str:
        return os.path.dirname(self.path) if self.path else ""

    def track(self, tid: str):
        for t in self.tracks:
            if t.id == tid:
                return t
        return None

    def track_of(self, clip_id: str):
        for t in self.tracks:
            for c in t.clips:
                if c.id == clip_id:
                    return t
        return None

    def clip(self, cid: str):
        for t in self.tracks:
            for c in t.clips:
                if c.id == cid:
                    return c
        return None

    def all_clips(self):
        for t in self.tracks:
            yield from t.clips

    def visual_tracks_bottom_up(self):
        """Video tracks first (bottom to top), then HUD tracks (bottom to top)."""
        vids = [t for t in self.tracks if t.kind == "video"]
        huds = [t for t in self.tracks if t.kind == "hud"]
        return list(reversed(vids)) + list(reversed(huds))

    def tracks_of(self, kind: str):
        return [t for t in self.tracks if t.kind == kind]

    @property
    def duration(self) -> float:
        end = 0.0
        for c in self.all_clips():
            end = max(end, c.end)
        return end

    def add_media(self, m: Media) -> Media:
        for existing in self.media.values():
            if os.path.normcase(os.path.abspath(existing.path)) == os.path.normcase(os.path.abspath(m.path)):
                return existing
        self.media[m.id] = m
        return m

    # ---- serialisation
    def to_dict(self) -> dict:
        d = {
            "format": APP_NAME, "version": FORMAT_VERSION,
            "name": self.name, "fps": self.fps, "width": self.width, "height": self.height,
            "sample_rate": self.sample_rate,
            "media": {k: asdict(v) for k, v in self.media.items()},
            "tracks": [],
        }
        for t in self.tracks:
            td = asdict(t)
            d["tracks"].append(td)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        p = cls(name=d.get("name", "Untitled"), fps=d.get("fps", 30.0),
                width=d.get("width", 1920), height=d.get("height", 1080),
                sample_rate=d.get("sample_rate", 48000))
        for k, v in d.get("media", {}).items():
            p.media[k] = Media(**v)
        for td in d.get("tracks", []):
            clips = [Clip(**c) for c in td.pop("clips", [])]
            t = Track(**td)
            t.clips = clips
            p.tracks.append(t)
        return p

    def save(self, path: str | None = None) -> None:
        if path:
            self.path = path
        assert self.path
        d = self.to_dict()
        base = self.folder
        for m in d["media"].values():
            m["path"] = _portable_path(m["path"], base)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=1)
        os.replace(tmp, self.path)

    @classmethod
    def load(cls, path: str) -> "Project":
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        p = cls.from_dict(d)
        p.path = os.path.abspath(path)
        base = p.folder
        for m in p.media.values():
            m.path = _resolve_path(m.path, base)
        return p

    def missing_media(self) -> list:
        return [m for m in self.media.values() if not m.generated and not os.path.exists(m.path)]

    def clone(self) -> "Project":
        p = Project.from_dict(copy.deepcopy(self.to_dict()))
        p.path = self.path
        return p


def _portable_path(path: str, base: str) -> str:
    """Store paths relative to the project folder (with / separators) when the
    file lives inside it, so the project works after copying to another OS."""
    if base:
        try:
            rel = os.path.relpath(path, base)
            if not rel.startswith(".."):
                return "./" + rel.replace(os.sep, "/")
        except ValueError:   # different drive on Windows
            pass
    return path


def _resolve_path(path: str, base: str) -> str:
    if path.startswith("./"):
        return os.path.normpath(os.path.join(base, *path[2:].split("/")))
    return path


def relink_media(project: Project, search_folder: str) -> int:
    """Find missing media by file name inside search_folder (recursive)."""
    missing = {os.path.basename(m.path.replace("\\", "/")).lower(): m for m in project.missing_media()}
    found = 0
    for root, _dirs, files in os.walk(search_folder):
        for fn in files:
            m = missing.get(fn.lower())
            if m is not None:
                m.path = os.path.join(root, fn)
                found += 1
                missing.pop(fn.lower())
        if not missing:
            break
    return found


# ---------------------------------------------------------------- combining projects
def append_project(dst: Project, src: Project, offset: float) -> dict:
    """Adds every clip of `src` to `dst`, starting at time `offset`.
    Tracks are matched by kind and position (V1 with V1, HUD 1 with HUD 1,
    first sound track with first sound track); missing tracks are created.
    Returns a small report."""
    import copy as _copy
    # media: reuse the same file if it is already in dst
    media_map = {}
    for mid, m in src.media.items():
        same = None
        for dm in dst.media.values():
            if (m.generated and dm.generated == m.generated) or \
                    os.path.normcase(os.path.abspath(dm.path)) == os.path.normcase(os.path.abspath(m.path)):
                same = dm
                break
        if same is None:
            nm = Media(**{**m.__dict__})
            nm.id = new_id("m")
            dst.media[nm.id] = nm
            same = nm
        media_map[mid] = same.id

    def ordered(project, kind):
        ts = [t for t in project.tracks if t.kind == kind]
        return list(reversed(ts)) if kind in ("video", "hud") else ts   # V1 / HUD 1 first

    added_tracks, n_clips = 0, 0
    for kind in ("video", "hud", "audio"):
        s_tracks, d_tracks = ordered(src, kind), ordered(dst, kind)
        for i, st in enumerate(s_tracks):
            if not st.clips:
                continue
            if i < len(d_tracks):
                dt = d_tracks[i]
            else:
                dt = Track(new_id("t"), kind, st.name, volume=st.volume, duck=st.duck, duck_db=st.duck_db,
                           is_voice=st.is_voice)
                if kind == "audio":
                    dst.tracks.append(dt)
                else:   # put it on top of its group
                    first = next(j for j, t in enumerate(dst.tracks) if t.kind == kind)
                    dst.tracks.insert(first, dt)
                d_tracks.append(dt)
                added_tracks += 1
            for c in st.clips:
                nc = Clip(**_copy.deepcopy(asdict(c)))
                nc.id = new_id("c")
                nc.start = round(c.start + offset, 4)
                if nc.media_id:
                    nc.media_id = media_map.get(nc.media_id, nc.media_id)
                dt.clips.append(nc)
                n_clips += 1
            dt.sort()
    return {"clips": n_clips, "tracks": added_tracks}
