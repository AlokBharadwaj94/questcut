"""Export the finished movie as an MP4 that plays everywhere
(Windows, Mac/QuickTime, phones, PowerPoint/Keynote, projectors).

The timeline is split into pieces that are drawn in parallel; each piece is
encoded by its own ffmpeg, then the pieces are joined and the sound added.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass

from .audio import mix_to_wav
from .backend import HW, ArrayBackend, ffmpeg_exe
from .media import MediaPool
from .renderer import Renderer

_NOWIN = {"creationflags": 0x08000000} if sys.platform == "win32" else {}

QUALITY = {"high": 0, "medium": 1, "small": 2}


@dataclass
class ExportSettings:
    path: str
    width: int = 1920
    height: int = 1080
    fps: float = 30.0
    quality: str = "high"           # high | medium | small
    encoder: str = "auto"           # auto | libx264 | h264_nvenc | h264_videotoolbox | h264_qsv | h264_amf
    gpu_filters: bool = True        # use CuPy if available
    start: float = 0.0
    end: float = -1.0               # -1 = end of movie
    workers: int = 0                # 0 = automatic


def encoder_args(enc: str, quality: str, threads: int):
    q = QUALITY.get(quality, 0)
    if enc == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-tune", "hq", "-rc", "vbr", "-cq", str([19, 23, 28][q]),
                "-b:v", "0", "-profile:v", "high", "-pix_fmt", "yuv420p"]
    if enc == "h264_videotoolbox":
        return ["-c:v", "h264_videotoolbox", "-b:v", ["16M", "10M", "5M"][q], "-profile:v", "high",
                "-allow_sw", "1", "-pix_fmt", "yuv420p"]
    if enc == "h264_qsv":
        return ["-c:v", "h264_qsv", "-global_quality", str([20, 24, 28][q]), "-pix_fmt", "nv12"]
    if enc == "h264_amf":
        return ["-c:v", "h264_amf", "-quality", "quality", "-rc", "cqp", "-qp_i", str([18, 22, 26][q]),
                "-qp_p", str([20, 24, 28][q]), "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", ["medium", "fast", "fast"][q], "-crf", str([18, 21, 25][q]),
            "-profile:v", "high", "-pix_fmt", "yuv420p", "-threads", str(max(1, threads))]


class Exporter:
    def __init__(self, project, settings: ExportSettings):
        self.project = project.clone()     # work on a frozen copy
        self.s = settings
        self.cancelled = False
        self.error = ""
        self.done_frames = 0
        self.total_frames = 1
        self.stage = "Starting"
        self.backend_name = ""
        self.encoder = ""
        self._procs = []
        self._lock = threading.Lock()

    def cancel(self):
        self.cancelled = True
        for p in list(self._procs):
            try:
                p.kill()
            except Exception:
                pass

    @property
    def progress(self) -> float:
        return min(1.0, self.done_frames / max(1, self.total_frames))

    # ----------------------------------------------------------------
    def run(self) -> bool:
        s = self.s
        try:
            end = self.project.duration if s.end < 0 else min(s.end, self.project.duration)
            start = max(0.0, s.start)
            if end - start <= 0.05:
                self.error = "The timeline is empty — add some clips first."
                return False
            enc = s.encoder
            if enc == "auto":
                enc = HW.best_encoder if HW.checked else "libx264"
            self.encoder = enc
            n_frames = int(round((end - start) * s.fps))
            self.total_frames = n_frames
            tmp = tempfile.mkdtemp(prefix="questcut_export_")
            try:
                # 1. sound
                self.stage = "Mixing sound"
                wav = os.path.join(tmp, "sound.wav")
                mix_to_wav(self.project, wav, start, n_frames / s.fps)
                if self.cancelled:
                    return False
                # 2. pictures, in parallel pieces
                cores = os.cpu_count() or 2
                use_gpu = s.gpu_filters and HW.cupy_ok
                if s.workers > 0:
                    nw = s.workers
                elif use_gpu:
                    nw = 2
                else:
                    nw = max(1, min(4, cores // 2))
                nw = max(1, min(nw, max(1, n_frames // 30)))
                if enc == "h264_nvenc":
                    nw = min(nw, 3)
                self.stage = "Drawing frames"
                bounds = [int(round(i * n_frames / nw)) for i in range(nw + 1)]
                parts = [os.path.join(tmp, f"part{i:02d}.ts") for i in range(nw)]
                threads = []
                errors = []
                for i in range(nw):
                    th = threading.Thread(target=self._render_part, daemon=True,
                                          args=(start, bounds[i], bounds[i + 1], parts[i], enc,
                                                max(1, cores // nw), use_gpu, errors))
                    th.start()
                    threads.append(th)
                for th in threads:
                    th.join()
                if self.cancelled:
                    return False
                if errors:
                    # hardware encoder failed? try again once on the CPU
                    if enc != "libx264" and not self.cancelled:
                        self.done_frames = 0
                        self.encoder = enc = "libx264"
                        errors.clear()
                        self._render_part(start, 0, n_frames, parts[0], enc, cores, use_gpu, errors)
                        parts = parts[:1]
                    if errors:
                        self.error = errors[0]
                        return False
                # 3. join + sound
                self.stage = "Finishing file"
                lst = os.path.join(tmp, "list.txt")
                with open(lst, "w", encoding="utf-8") as f:
                    for p in parts:
                        f.write("file '" + p.replace("\\", "/").replace("'", "'\\''") + "'\n")
                out = s.path
                os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
                cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
                       "-i", lst, "-i", wav, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
                       "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "-shortest", out]
                r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, **_NOWIN)
                if r.returncode != 0:
                    self.error = "Joining the pieces failed:\n" + r.stderr.decode(errors="ignore")[-800:]
                    return False
                self.stage = "Done"
                return True
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        except Exception as e:  # pragma: no cover
            import traceback
            self.error = f"{e}\n{traceback.format_exc()[-1500:]}"
            return False

    def _render_part(self, start, f0, f1, out, enc, threads, use_gpu, errors):
        s = self.s
        if f1 <= f0:
            return
        pool = MediaPool(self.project, use_proxies=False)
        be = ArrayBackend(use_gpu)
        self.backend_name = be.name
        rend = Renderer(self.project, pool, be, preview=False)
        cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{s.width}x{s.height}", "-r", f"{s.fps}", "-i", "-", "-an"]
        cmd += encoder_args(enc, s.quality, threads)
        cmd += ["-g", str(int(s.fps * 2)), "-f", "mpegts", out]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, **_NOWIN)
        with self._lock:
            self._procs.append(proc)
        err_buf = []
        t_err = threading.Thread(target=lambda: err_buf.append(proc.stderr.read()), daemon=True)
        t_err.start()
        try:
            for i in range(f0, f1):
                if self.cancelled:
                    break
                t = start + i / s.fps
                try:
                    frame = rend.render(t, s.width, s.height)
                except Exception as e:
                    if be.is_gpu:      # GPU trouble: carry on with the CPU
                        be = ArrayBackend(False)
                        rend = Renderer(self.project, pool, be, preview=False)
                        self.backend_name = be.name + " (GPU failed: " + str(e)[:60] + ")"
                        frame = rend.render(t, s.width, s.height)
                    else:
                        raise
                proc.stdin.write(frame.tobytes())
                with self._lock:
                    self.done_frames += 1
            proc.stdin.close()
            proc.wait()
            t_err.join(timeout=2)
            if proc.returncode != 0 and not self.cancelled:
                msg = (err_buf[0] if err_buf else b"").decode(errors="ignore")[-600:]
                errors.append(f"Video encoder ({enc}) failed: {msg}")
        except (BrokenPipeError, OSError) as e:
            if not self.cancelled:
                t_err.join(timeout=2)
                msg = (err_buf[0] if err_buf else b"").decode(errors="ignore")[-600:]
                errors.append(f"Video encoder ({enc}) stopped: {e} {msg}")
        except Exception as e:
            import traceback
            errors.append(f"Drawing frames failed: {e}\n{traceback.format_exc()[-1200:]}")
            try:
                proc.kill()
            except Exception:
                pass
        finally:
            pool.close()


def export_still(project, t, path, width=1920, height=1080):
    """Save the picture at time t as a PNG/JPG (for posters, thumbnails)."""
    import cv2
    pool = MediaPool(project, use_proxies=False)
    try:
        img = Renderer(project, pool, preview=False).render(t, width, height)
    finally:
        pool.close()
    ext = os.path.splitext(path)[1].lower() or ".png"
    ok, data = cv2.imencode(ext, img[..., ::-1])
    if ok:
        data.tofile(path)
    return ok
