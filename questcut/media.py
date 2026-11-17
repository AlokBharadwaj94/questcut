"""Reading media files: probing, decoding video frames, audio, images, proxies."""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import threading
from collections import OrderedDict

import av
import cv2
import numpy as np

from .backend import ffmpeg_exe
from .model import Media, new_id

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".mts", ".m2ts", ".webm", ".lrv", ".mpg", ".mpeg", ".wmv", ".3gp"}
AUDIO_EXT = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma", ".aif", ".aiff"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"}

PROXY_HEIGHT = 540
SAMPLE_RATE = 48000


# ------------------------------------------------------------------ cache folder
def cache_dir(project) -> str:
    if project is not None and project.path:
        d = os.path.join(project.folder, "QuestCut_cache")
    else:
        d = os.path.join(tempfile.gettempdir(), "QuestCut_cache")
    os.makedirs(d, exist_ok=True)
    return d


def file_key(path: str) -> str:
    try:
        st = os.stat(path)
        s = f"{os.path.abspath(path)}|{st.st_size}|{int(st.st_mtime)}"
    except OSError:
        s = os.path.abspath(path)
    return hashlib.sha1(s.encode("utf-8", "ignore")).hexdigest()[:16]


# ------------------------------------------------------------------ probing
def _rotation_of(stream) -> int:
    try:
        r = stream.metadata.get("rotate")
        if r:
            return int(float(r)) % 360
    except Exception:
        pass
    return 0


def probe(path: str) -> Media:
    ext = os.path.splitext(path)[1].lower()
    name = os.path.basename(path)
    if ext in IMAGE_EXT:
        img = imread_any(path)
        if img is None:
            raise ValueError(f"Cannot read image {name}")
        return Media(new_id("m"), os.path.abspath(path), "image", name, 0.0, img.shape[1], img.shape[0])
    with av.open(path) as c:
        has_v = len(c.streams.video) > 0 and ext not in AUDIO_EXT
        has_a = len(c.streams.audio) > 0
        dur = float(c.duration) / av.time_base if c.duration else 0.0
        if has_v:
            vs = c.streams.video[0]
            w, h = vs.codec_context.width, vs.codec_context.height
            fps = float(vs.average_rate) if vs.average_rate else 30.0
            if not dur and vs.duration:
                dur = float(vs.duration * vs.time_base)
            rot = _rotation_of(vs)
            # newer PyAV reports rotation on decoded frames
            try:
                for fr in c.decode(vs):
                    rot = int(getattr(fr, "rotation", rot) or rot) % 360
                    break
            except Exception:
                pass
            if rot in (90, 270, -90):
                w, h = h, w
            return Media(new_id("m"), os.path.abspath(path), "video", name, dur, w, h, fps, has_a, rot)
        if has_a:
            if not dur:
                a = c.streams.audio[0]
                if a.duration:
                    dur = float(a.duration * a.time_base)
            return Media(new_id("m"), os.path.abspath(path), "audio", name, dur, 0, 0, 0, True)
    raise ValueError(f"{name}: no video or audio found")


def imread_any(path: str):
    """cv2.imread that also works with non-ASCII paths on Windows. Returns RGBA uint8."""
    try:
        data = np.fromfile(path, dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    except Exception:
        return None
    if img is None:
        return None
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGBA)
    elif img.shape[2] == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGBA)
    else:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
    if img.dtype != np.uint8:
        img = (img / (img.max() or 1) * 255).astype(np.uint8)
    return img


# ------------------------------------------------------------------ video frames
class FrameSource:
    """Decodes frames from one video file, fast for both playing forward and
    jumping around."""

    def __init__(self, path: str, rotation: int = 0):
        self.path = path
        self.rotation = rotation
        self.c = av.open(path)
        self.vs = self.c.streams.video[0]
        self.vs.thread_type = "AUTO"
        self.tb = float(self.vs.time_base)
        self.fps = float(self.vs.average_rate) if self.vs.average_rate else 30.0
        self.start_time = float(self.vs.start_time * self.vs.time_base) if self.vs.start_time else 0.0
        self._it = None
        self._prev = None      # (time, frame)
        self._next = None
        self._cache: OrderedDict = OrderedDict()
        self.lock = threading.Lock()

    def close(self):
        try:
            self.c.close()
        except Exception:
            pass

    def _seek(self, t):
        target = int((t + self.start_time) / self.tb)
        self.c.seek(max(0, target), stream=self.vs, backward=True, any_frame=False)
        self._it = self.c.decode(self.vs)
        self._prev = None
        self._next = None

    def _pull(self):
        try:
            fr = next(self._it)
        except (StopIteration, av.error.EOFError):
            return None
        except Exception:
            return None
        ft = (float(fr.pts * self.tb) if fr.pts is not None else 0.0) - self.start_time
        return (ft, fr)

    def _frame_at(self, t):
        half = 0.5 / self.fps
        if self._prev is not None and self._prev[0] - half <= t:
            if self._next is not None and t < self._next[0] - half:
                return self._prev[1]
            if t - self._prev[0] < 2.5:   # play forward
                return self._advance(t)
        self._seek(t)
        return self._advance(t)

    def _advance(self, t):
        half = 0.5 / self.fps
        if self._it is None:
            self._seek(t)
        guard = 0
        while True:
            if self._next is None:
                self._next = self._pull()
                if self._next is None:          # end of file: keep last frame
                    return self._prev[1] if self._prev else None
            if self._next[0] - half <= t:
                self._prev, self._next = self._next, None
                guard += 1
                if guard > 2000:
                    break
                continue
            break
        if self._prev is None:
            self._prev, self._next = self._next, None
        return self._prev[1] if self._prev else None

    def get(self, t: float, max_h: int = 0):
        """RGB uint8 frame at time t (seconds from file start). If max_h is
        set, the frame is shrunk so its height is at most max_h."""
        with self.lock:
            fr = self._frame_at(max(0.0, t))
            if fr is None:
                return None
            key = (fr.pts, max_h)
            hit = self._cache.get(key)
            if hit is not None:
                return hit
            w, h = fr.width, fr.height
            if self.rotation in (90, 270):
                w, h = h, w
            if max_h and h > max_h:
                s = max_h / h
                tw, th = max(2, int(w * s) // 2 * 2), max(2, int(max_h) // 2 * 2)
            else:
                tw, th = w, h
            if self.rotation in (90, 270):
                img = fr.reformat(width=th, height=tw, format="rgb24").to_ndarray()
            else:
                img = fr.reformat(width=tw, height=th, format="rgb24").to_ndarray()
            if self.rotation == 90:
                img = np.ascontiguousarray(np.rot90(img, -1))
            elif self.rotation == 270:
                img = np.ascontiguousarray(np.rot90(img, 1))
            elif self.rotation == 180:
                img = np.ascontiguousarray(img[::-1, ::-1])
            self._cache[key] = img
            if len(self._cache) > 6:
                self._cache.popitem(last=False)
            return img


class MediaPool:
    """Keeps decoders open. Preview uses proxies (small copies) when ready;
    export uses the original files."""

    def __init__(self, project, use_proxies: bool = True):
        self.project = project
        self.use_proxies = use_proxies
        self.sources: dict = {}
        self.images: dict = {}
        self.proxy_ready: dict = {}   # media_id -> path
        self.lock = threading.Lock()

    def set_project(self, project):
        self.project = project

    def close(self):
        for s in self.sources.values():
            s.close()
        self.sources.clear()

    def _source(self, media):
        path, rot = media.path, media.rotation
        if self.use_proxies and media.id in self.proxy_ready:
            path, rot = self.proxy_ready[media.id], 0
        key = (media.id, path)
        src = self.sources.get(key)
        if src is None:
            with self.lock:
                src = self.sources.get(key)
                if src is None:
                    old = [k for k in self.sources if k[0] == media.id]
                    for k in old:
                        self.sources.pop(k).close()
                    src = FrameSource(path, rot)
                    self.sources[key] = src
        return src

    def frame(self, media_id: str, t: float, max_h: int = 0):
        m = self.project.media.get(media_id)
        if m is None or not os.path.exists(m.path):
            return None
        if m.kind == "image":
            return self.image(media_id)
        try:
            return self._source(m).get(t, max_h)
        except Exception:
            return None

    def image(self, media_id: str):
        img = self.images.get(media_id)
        if img is None:
            m = self.project.media.get(media_id)
            if m is None:
                return None
            img = imread_any(m.path)
            if img is not None:
                self.images[media_id] = img
        return img


# ------------------------------------------------------------------ proxies
def proxy_path_for(project, media) -> str:
    return os.path.join(cache_dir(project), "proxies", file_key(media.path) + ".mp4")


def make_proxy(project, media, progress=None) -> str | None:
    """Small 540p copy that is quick to scrub through. Returns its path."""
    if media.kind != "video" or media.height <= PROXY_HEIGHT + 60:
        return None
    out = proxy_path_for(project, media)
    if os.path.exists(out) and os.path.getsize(out) > 1000:
        return out
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".part.mp4"
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-i", media.path,
           "-vf", f"scale=-2:{PROXY_HEIGHT}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
           "-g", "15", "-pix_fmt", "yuv420p", "-an", tmp]
    kw = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, **kw)
    if r.returncode != 0 or not os.path.exists(tmp):
        return None
    os.replace(tmp, out)
    return out


# ------------------------------------------------------------------ audio
_AUDIO_MEM: dict = {}
_audio_lock = threading.Lock()


def load_audio(project, media) -> np.ndarray | None:
    """Whole audio track as int16 stereo (N, 2) at 48 kHz. Decoded once and
    cached on disk."""
    if media is None or not media.has_audio and media.kind != "audio":
        return None
    key = file_key(media.path)
    with _audio_lock:
        if key in _AUDIO_MEM:
            return _AUDIO_MEM[key]
    path = os.path.join(cache_dir(project), "audio", key + ".npy")
    arr = None
    if os.path.exists(path):
        try:
            arr = np.load(path, mmap_mode="r")
        except Exception:
            arr = None
    if arr is None:
        arr = decode_audio(media.path)
        if arr is None:
            return None
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            np.save(path + ".tmp.npy", arr)
            os.replace(path + ".tmp.npy", path)
        except Exception:
            pass
    with _audio_lock:
        _AUDIO_MEM[key] = arr
    return arr


def decode_audio(path: str, rate: int = SAMPLE_RATE) -> np.ndarray | None:
    try:
        c = av.open(path)
    except Exception:
        return None
    try:
        if not c.streams.audio:
            return None
        st = c.streams.audio[0]
        res = av.AudioResampler(format="s16", layout="stereo", rate=rate)
        chunks = []
        for fr in c.decode(st):
            for o in res.resample(fr):
                chunks.append(o.to_ndarray().reshape(-1, 2))
        for o in res.resample(None):
            chunks.append(o.to_ndarray().reshape(-1, 2))
        if not chunks:
            return None
        return np.ascontiguousarray(np.concatenate(chunks, axis=0).astype(np.int16))
    except Exception:
        return None
    finally:
        c.close()


def forget_audio(path: str):
    with _audio_lock:
        _AUDIO_MEM.pop(file_key(path), None)


def write_wav(path: str, data: np.ndarray, rate: int = SAMPLE_RATE):
    """data float (-1..1) or int16, shape (N,) or (N, ch)."""
    import wave
    if data.dtype != np.int16:
        data = (np.clip(data, -1, 1) * 32767).astype(np.int16)
    if data.ndim == 1:
        data = data[:, None]
    with wave.open(path, "wb") as w:
        w.setnchannels(data.shape[1])
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.ascontiguousarray(data).tobytes())


# ------------------------------------------------------------------ stabilisation
def _has_filter(name: str) -> bool:
    try:
        kw = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
        r = subprocess.run([ffmpeg_exe(), "-hide_banner", "-filters"], stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, timeout=10, **kw)
        return f" {name} " in r.stdout.decode(errors="ignore")
    except Exception:
        return False


def stabilize(project, media, progress=None, cancelled=lambda: False) -> str | None:
    """Makes a steadier copy of shaky footage (e.g. a head-mounted GoPro).
    Uses ffmpeg's two-pass 'vidstab' when available, otherwise 'deshake'.
    Runs on the CPU; it takes roughly as long as the clip, or longer."""
    base = os.path.join(project.folder, "stabilized") if project.path else os.path.join(cache_dir(project), "stabilized")
    os.makedirs(base, exist_ok=True)
    name = os.path.splitext(os.path.basename(media.path))[0]
    out = os.path.join(base, f"{name}_steady.mp4")
    kw = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
    dur = max(0.1, media.duration)

    def run(cmd, p0, p1):
        proc = subprocess.Popen(cmd, cwd=base, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **kw)
        for line in proc.stdout:
            if cancelled():
                proc.kill()
                return False
            line = line.decode(errors="ignore").strip()
            if line.startswith("out_time_ms=") and progress:
                try:
                    progress(p0 + (p1 - p0) * min(1.0, int(line.split("=")[1]) / 1e6 / dur))
                except ValueError:
                    pass
        proc.wait()
        return proc.returncode == 0

    common = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-progress", "pipe:1", "-i", media.path]
    enc = ["-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy",
           "-movflags", "+faststart", out]
    if _has_filter("vidstabdetect"):
        trf = "transforms_" + file_key(media.path) + ".trf"   # relative path: avoids escaping problems
        ok = run(common + ["-vf", f"vidstabdetect=shakiness=7:accuracy=12:result={trf}", "-f", "null", "-"], 0, 0.45)
        if ok:
            ok = run(common + ["-vf", f"vidstabtransform=input={trf}:smoothing=18:zoom=4:optzoom=0,"
                               "unsharp=5:5:0.6:3:3:0.3"] + enc, 0.45, 1.0)
        try:
            os.remove(os.path.join(base, trf))
        except OSError:
            pass
    else:
        ok = run(common + ["-vf", "deshake=rx=48:ry=48:edge=mirror"] + enc, 0, 1.0)
    return out if ok and os.path.exists(out) else None
