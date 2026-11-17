"""Makes a small practice project: two fake 'camera' videos of the same
scene (a main camera and a first-person 'GoPro'), whose sound matches but
starts 1.7 s apart, so every lesson in the Guide can be tried safely."""
from __future__ import annotations

import math
import os
import subprocess
import sys

import cv2
import numpy as np

from .backend import ffmpeg_exe
from .media import probe, write_wav
from .model import Clip, Project, new_id

W, H, FPS, DUR = 1280, 720, 30, 24
OFFSET = 1.7
_NOWIN = {"creationflags": 0x08000000} if sys.platform == "win32" else {}


def _scene_positions(t):
    hero_x = 0.15 + 0.25 * (0.5 - 0.5 * math.cos(t * 0.35))
    monster_x = 0.78 + 0.03 * math.sin(t * 2.0)
    return hero_x, monster_x


def _draw_main(t):
    img = np.zeros((H, W, 3), np.uint8)
    for y in range(H):
        k = y / H
        img[y] = (int(120 + 80 * k), int(70 + 60 * k), int(30 + 40 * k))   # BGR: dusk sky
    cv2.rectangle(img, (0, int(H * 0.72)), (W, H), (40, 90, 50), -1)       # ground
    for i in range(8):                                                       # lab benches
        x = int((i * 190 - t * 20) % (W + 200)) - 100
        cv2.rectangle(img, (x, int(H * 0.6)), (x + 120, int(H * 0.72)), (90, 90, 110), -1)
    hx, mx = _scene_positions(t)
    hx, mx = int(hx * W), int(mx * W)
    gy = int(H * 0.72)
    cv2.circle(img, (hx, gy - 150), 32, (180, 210, 255), -1)                 # hero head
    cv2.rectangle(img, (hx - 30, gy - 118), (hx + 30, gy - 30), (200, 120, 40), -1)
    cv2.line(img, (hx - 20, gy - 30), (hx - 25, gy), (60, 60, 60), 10)
    cv2.line(img, (hx + 20, gy - 30), (hx + 25, gy), (60, 60, 60), 10)
    wave = int(25 * math.sin(t * 6))
    cv2.line(img, (hx + 30, gy - 100), (hx + 75, gy - 130 + wave), (180, 210, 255), 10)
    cv2.ellipse(img, (mx, gy - 90), (90, 95), 0, 0, 360, (60, 40, 170), -1)  # monster
    cv2.circle(img, (mx - 30, gy - 120), 14, (255, 255, 255), -1)
    cv2.circle(img, (mx + 30, gy - 120), 14, (255, 255, 255), -1)
    cv2.circle(img, (mx - 30, gy - 120), 6, (0, 0, 0), -1)
    cv2.circle(img, (mx + 30, gy - 120), 6, (0, 0, 0), -1)
    cv2.putText(img, "MAIN CAMERA", (24, 48), cv2.FONT_HERSHEY_DUPLEX, 1.1, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(img, f"t = {t:5.2f} s", (24, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
    return img


def _draw_gopro(t):
    """First-person view: the monster seen from the hero's eyes, wobbling."""
    img = np.zeros((H, W, 3), np.uint8)
    img[:] = (70, 50, 40)
    wob_x = int(18 * math.sin(t * 3.1))
    wob_y = int(12 * math.sin(t * 4.3))
    cv2.rectangle(img, (0, int(H * 0.65) + wob_y), (W, H), (50, 80, 60), -1)
    hx, mx = _scene_positions(t)
    dist = mx - hx
    size = int(120 + 220 * (1 - dist))
    cx, cy = W // 2 + wob_x, int(H * 0.5) + wob_y
    cv2.ellipse(img, (cx, cy), (size, int(size * 1.05)), 0, 0, 360, (60, 40, 170), -1)
    for dx in (-0.35, 0.35):
        ex = int(cx + dx * size)
        cv2.circle(img, (ex, cy - int(size * 0.3)), int(size * 0.16), (255, 255, 255), -1)
        cv2.circle(img, (ex, cy - int(size * 0.3)), int(size * 0.07), (0, 0, 0), -1)
    hand = int(40 * math.sin(t * 6))
    cv2.ellipse(img, (W - 220, H - 60 + hand), (90, 160), -25, 0, 360, (150, 190, 240), -1)
    # fisheye-ish darkening
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    img = (img * np.clip(1.25 - 0.55 * d, 0, 1)[..., None]).astype(np.uint8)
    cv2.putText(img, "GOPRO (first person)", (24, 48), cv2.FONT_HERSHEY_DUPLEX, 1.1, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(img, f"t = {t:5.2f} s", (24, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
    return img


def _sound(offset, rng_seed, hum):
    sr = 48000
    n = int(DUR * sr)
    rng = np.random.default_rng(7)
    events = np.sort(rng.uniform(0.3, DUR + OFFSET - 0.5, 30))
    rng2 = np.random.default_rng(rng_seed)
    x = rng2.normal(0, 0.008, n).astype(np.float32)
    tt = np.arange(n) / sr
    x += hum * np.sin(2 * np.pi * 110 * tt).astype(np.float32)
    for i, e in enumerate(events):
        k = int((e - offset) * sr)
        if 0 <= k < n - 6000:
            if i % 3 == 0:   # clap
                burst = np.random.default_rng(i).normal(0, 0.5, 6000) * np.exp(-np.arange(6000) / 700)
            else:            # short "voice-like" chirp
                ts = np.arange(6000) / sr
                burst = 0.35 * np.sin(2 * np.pi * (220 + 300 * ts) * ts) * np.sin(np.pi * ts / ts[-1])
            x[k:k + 6000] += burst.astype(np.float32)
    return np.stack([x, x], axis=1)


def _encode(path, draw, t0, wav, progress, p0, p1):
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "veryfast",
           "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, **_NOWIN)
    n = DUR * FPS
    for i in range(n):
        proc.stdin.write(draw(t0 + i / FPS).tobytes())
        if progress and i % 15 == 0:
            progress(p0 + (p1 - p0) * i / n)
    proc.stdin.close()
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.read().decode(errors="ignore")[-500:])


def make_practice_project(folder, progress=None) -> str:
    media = os.path.join(folder, "media")
    os.makedirs(media, exist_ok=True)
    wa, wb = os.path.join(media, "_a.wav"), os.path.join(media, "_b.wav")
    write_wav(wa, _sound(0.0, 1, 0.01))
    write_wav(wb, _sound(OFFSET, 2, 0.03))      # GoPro started 1.7 s later
    pa, pb = os.path.join(media, "MainCamera_scene1.mp4"), os.path.join(media, "GoPro_scene1.mp4")
    _encode(pa, _draw_main, 0.0, wa, progress, 0.0, 0.5)
    _encode(pb, _draw_gopro, OFFSET, wb, progress, 0.5, 1.0)
    for f in (wa, wb):
        try:
            os.remove(f)
        except OSError:
            pass
    p = Project.new_default()
    p.name = "Practice"
    ma, mb = p.add_media(probe(pa)), p.add_media(probe(pb))
    vids = [t for t in p.tracks if t.kind == "video"]
    vids[-1].clips.append(Clip(new_id("c"), "video", 0.0, ma.duration, "Main camera", ma.id))
    vids[0].clips.append(Clip(new_id("c"), "video", 0.0, mb.duration, "GoPro", mb.id))
    path = os.path.join(folder, "Practice.questcut")
    p.save(path)
    if progress:
        progress(1.0)
    return path
