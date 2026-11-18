"""Audio: mixing all tracks, ducking music under voice-over, and the
built-in game sound generator (everything is synthesised here, so there are
no copyright issues)."""
from __future__ import annotations

import math
import os

import numpy as np

from .media import SAMPLE_RATE, load_audio, write_wav

SR = SAMPLE_RATE


# ================================================================== mixing
def _soft_limit(x):
    a = np.abs(x)
    over = a > 0.85
    if over.any():
        x = x.copy()
        x[over] = np.sign(x[over]) * (0.85 + 0.15 * np.tanh((a[over] - 0.85) / 0.15))
    return x


def _gain_curve(clip, ov0, n, rate):
    """Per-sample gain for a clip: volume (can be keyframed) and fades."""
    t_rel0 = ov0 - clip.start
    if "volume" in clip.keyframes:
        pts = max(2, int(n / rate * 50) + 2)
        tt = np.linspace(t_rel0, t_rel0 + n / rate, pts)
        vv = np.array([float(clip.value("volume", x, 1.0)) for x in tt], dtype=np.float32)
        g = np.interp(np.arange(n) / rate + t_rel0, tt, vv).astype(np.float32)
    else:
        g = np.full(n, float(clip.props.get("volume", 1.0)), dtype=np.float32)
    fi = float(clip.props.get("fade_in", 0.0) or 0.0)
    fo = float(clip.props.get("fade_out", 0.0) or 0.0)
    if fi > 0 or fo > 0:
        tt = t_rel0 + np.arange(n, dtype=np.float32) / rate
        if fi > 0:
            g *= np.clip(tt / fi, 0, 1)
        if fo > 0:
            g *= np.clip((clip.duration - tt) / fo, 0, 1)
    return g


def _clip_samples(project, clip, ov0, n, rate):
    m = project.media.get(clip.media_id)
    if m is None or clip.freeze:
        return None
    arr = load_audio(project, m)
    if arr is None or len(arr) == 0:
        return None
    speed = float(clip.props.get("speed", 1.0) or 1.0)
    src_t = clip.source_in + (ov0 - clip.start) * speed
    loop = bool(clip.props.get("loop", False))
    L = len(arr)
    if abs(speed - 1.0) < 1e-6:
        s0 = int(round(src_t * rate))
        if loop:
            idx = (s0 + np.arange(n)) % L
            seg = arr[idx]
        else:
            seg = arr[max(0, s0):max(0, s0) + n]
            if len(seg) < n:
                seg = np.concatenate([seg, np.zeros((n - len(seg), 2), arr.dtype)])
        return seg.astype(np.float32) * (1 / 32768.0)
    pos = src_t * rate + np.arange(n) * speed
    if loop:
        pos = pos % L
    i = np.clip(pos.astype(np.int64), 0, L - 1)
    out = arr[i].astype(np.float32) * (1 / 32768.0)
    out[pos >= L] = 0
    return out


def _track_sources(project, track):
    for c in track.clips:
        if not c.enabled:
            continue
        if c.kind == "audio" or (c.kind == "video" and not c.props.get("mute", False)):
            m = project.media.get(c.media_id)
            if m is not None and (m.has_audio or m.kind == "audio"):
                yield c


def _track_mix(project, track, t0, n, rate):
    buf = np.zeros((n, 2), dtype=np.float32)
    any_sound = False
    t1 = t0 + n / rate
    for c in _track_sources(project, track):
        ov0, ov1 = max(t0, c.start), min(t1, c.end)
        if ov1 <= ov0:
            continue
        i0 = int(round((ov0 - t0) * rate))
        k = min(n - i0, int(round((ov1 - ov0) * rate)))
        if k <= 0:
            continue
        seg = _clip_samples(project, c, ov0, k, rate)
        if seg is None:
            continue
        g = _gain_curve(c, ov0, k, rate)
        buf[i0:i0 + k] += seg[:k] * g[:, None]
        any_sound = True
    return buf if any_sound else None


def duck_gain(voice, rate, depth_db, attack=0.05, release=0.35):
    """Gain curve that goes down while the voice track has sound."""
    n = len(voice)
    blk = int(rate * 0.01)
    nb = n // blk + 1
    mono = np.abs(voice).mean(axis=1)
    pad = np.zeros(nb * blk, dtype=np.float32)
    pad[:n] = mono
    lev = pad.reshape(nb, blk).mean(axis=1)
    active = (lev > 0.015).astype(np.float32)
    a_up = 1 - math.exp(-0.01 / attack)
    a_dn = 1 - math.exp(-0.01 / release)
    env = np.empty(nb, dtype=np.float32)
    e = 0.0
    for i in range(nb):
        target = active[i]
        e += (target - e) * (a_up if target > e else a_dn)
        env[i] = e
    floor = 10 ** (depth_db / 20.0)
    g = 1 - (1 - floor) * env
    return np.repeat(g, blk)[:n]


def mix(project, t0: float, duration: float, rate: int = SR) -> np.ndarray:
    """Final stereo mix (float32, shape (N, 2)) for [t0, t0 + duration)."""
    n = max(0, int(round(duration * rate)))
    out = np.zeros((n, 2), dtype=np.float32)
    if n == 0:
        return out
    sources = [tr for tr in project.tracks if tr.kind in ("audio", "video") and not tr.muted]
    voice = None
    bufs = []
    for tr in sources:
        b = _track_mix(project, tr, t0, n, rate)
        if b is None:
            continue
        b *= tr.volume
        if tr.is_voice:
            voice = b if voice is None else voice + b
        bufs.append((tr, b))
    for tr, b in bufs:
        if tr.duck and voice is not None and not tr.is_voice:
            b *= duck_gain(voice, rate, tr.duck_db)[:, None]
        out += b
    return _soft_limit(out)


def mix_to_wav(project, path, t0, duration, rate=SR, progress=None):
    """Mix in 20 s pieces (with overlap for smooth ducking) and write a WAV."""
    import wave
    total = int(round(duration * rate))
    step = 20.0
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        done = 0
        t = t0
        while done < total:
            n = min(int(step * rate), total - done)
            pre = min(1.0, t - t0)
            chunk = mix(project, t - pre, n / rate + pre, rate)[int(round(pre * rate)):][:n]
            w.writeframes((np.clip(chunk, -1, 1) * 32767).astype(np.int16).tobytes())
            done += n
            t += n / rate
            if progress:
                progress(done / max(1, total))


# ================================================================== sync
def _envelope(arr, rate, out_rate=1000):
    mono = arr.astype(np.float32).mean(axis=1) / 32768.0
    hp = np.diff(mono, prepend=mono[:1])           # keep sharp sounds (claps, talking)
    blk = rate // out_rate
    n = len(hp) // blk
    env = np.abs(hp[:n * blk]).reshape(n, blk).mean(axis=1)
    env = np.log1p(env * 200)
    k = out_rate // 2
    if n > k * 2:
        kern = np.ones(k, dtype=np.float32) / k
        env = env - np.convolve(env, kern, mode="same")
    return env.astype(np.float32)


def find_offset(a_arr, b_arr, rate=SR, max_seconds=None):
    """How many seconds later a moment appears in A than in B.
    Returns (lag_seconds, confidence 0..1)."""
    ea, eb = _envelope(a_arr, rate), _envelope(b_arr, rate)
    if len(ea) < 50 or len(eb) < 50:
        return 0.0, 0.0
    n = 1
    while n < len(ea) + len(eb):
        n *= 2
    A = np.fft.rfft(ea, n)
    B = np.fft.rfft(eb, n)
    c = np.fft.irfft(A * np.conj(B), n)
    lags = np.arange(n)
    lags[lags > n // 2] -= n
    valid = (lags > -len(eb)) & (lags < len(ea))
    if max_seconds:
        valid &= np.abs(lags) <= max_seconds * 1000
    c = np.where(valid, c, -np.inf)
    i = int(np.argmax(c))
    peak = c[i]
    finite = c[np.isfinite(c)]
    z = (peak - finite.mean()) / (finite.std() + 1e-9)
    conf = float(max(0.0, min(1.0, (z - 4) / 10)))
    return lags[i] / 1000.0, conf


def sync_clips(project, clip_a, clip_b):
    """Moves clip_b on the timeline so it lines up with clip_a by sound.
    Returns (ok, confidence, message)."""
    ma, mb = project.media.get(clip_a.media_id), project.media.get(clip_b.media_id)
    aa, ab = load_audio(project, ma), load_audio(project, mb)
    if aa is None or ab is None:
        return False, 0.0, "Both clips need sound to sync (one of them has no audio track)."
    lag, conf = find_offset(np.asarray(aa), np.asarray(ab))
    # moment at source time ta in A equals tb in B, with lag = ta - tb
    new_start = clip_a.start - clip_a.source_in + clip_b.source_in + lag
    if new_start < 0:
        cut = -new_start
        clip_b.source_in += cut
        clip_b.duration = max(0.1, clip_b.duration - cut)
        new_start = 0.0
    clip_b.start = round(new_start, 4)
    word = "good" if conf > 0.5 else ("fair" if conf > 0.2 else "weak — please check by eye/ear")
    return True, conf, f"Synced: camera B moved by {lag:+.3f} s (match quality: {word})."


# ================================================================== game sound synthesiser
def _t(dur):
    return np.arange(int(dur * SR), dtype=np.float32) / SR


def _phase(freq):
    """freq can be a number or an array (for sweeps)."""
    if np.isscalar(freq):
        return None
    return np.cumsum(freq) * (2 * np.pi / SR)


def osc(kind, freq, dur, duty=0.5):
    t = _t(dur)
    if np.isscalar(freq):
        ph = 2 * np.pi * freq * t
    else:
        ph = _phase(np.asarray(freq, dtype=np.float32)[:len(t)])
    if kind == "sine":
        return np.sin(ph)
    if kind == "square":
        return np.where((ph / (2 * np.pi)) % 1.0 < duty, 0.6, -0.6).astype(np.float32)
    if kind == "saw":
        return (((ph / (2 * np.pi)) % 1.0) * 2 - 1) * 0.6
    if kind == "triangle":
        x = (ph / (2 * np.pi)) % 1.0
        return (np.abs(x * 4 - 2) - 1) * 0.9
    if kind == "noise":
        return np.random.default_rng(int(dur * 1000)).uniform(-1, 1, len(t)).astype(np.float32)
    raise ValueError(kind)


def env_exp(n, decay):
    return np.exp(-np.arange(n, dtype=np.float32) / (decay * SR))


def env_adsr(n, a=0.01, d=0.05, s=0.7, r=0.1):
    e = np.full(n, s, dtype=np.float32)
    na, nd, nr = int(a * SR), int(d * SR), int(r * SR)
    na = min(na, n)
    e[:na] = np.linspace(0, 1, na, dtype=np.float32) if na else e[:na]
    nd = min(nd, n - na)
    e[na:na + nd] = np.linspace(1, s, nd, dtype=np.float32)
    if nr and nr < n:
        e[-nr:] *= np.linspace(1, 0, nr, dtype=np.float32)
    return e


def lowpass(x, cutoff):
    """Windowed-sinc low-pass filter."""
    fc = min(0.49, cutoff / SR)
    N = 101
    k = np.arange(N) - (N - 1) / 2
    h = np.sinc(2 * fc * k) * np.hamming(N)
    h /= h.sum()
    return np.convolve(x, h.astype(np.float32), mode="same")


def sweep_lowpass(x, c0, c1, pieces=24):
    out = np.zeros_like(x)
    n = len(x)
    edges = np.linspace(0, n, pieces + 1).astype(int)
    for i in range(pieces):
        a, b = edges[i], edges[i + 1]
        pad = 200
        seg = x[max(0, a - pad):min(n, b + pad)]
        f = c0 + (c1 - c0) * (i + 0.5) / pieces
        y = lowpass(seg, f)
        off = a - max(0, a - pad)
        out[a:b] = y[off:off + (b - a)]
    return out


def notes(seq, wave="square", tempo=0.12, duty=0.5, decay=0.15, gap=0.0):
    parts = []
    for f in seq:
        dur = tempo
        if f <= 0:
            parts.append(np.zeros(int(dur * SR), np.float32))
            continue
        tone = osc(wave, f, dur, duty)
        tone = tone * env_exp(len(tone), decay) * env_adsr(len(tone), 0.003, 0.0, 1.0, 0.01)
        parts.append(tone)
        if gap:
            parts.append(np.zeros(int(gap * SR), np.float32))
    return np.concatenate(parts)


def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def _norm(x, peak=0.8):
    m = np.abs(x).max() or 1
    return (x / m * peak).astype(np.float32)


def _pad(x, extra=0.15):
    return np.concatenate([x, np.zeros(int(extra * SR), np.float32)])


def sfx_spell_cast():
    d = 1.1
    t = _t(d)
    f = 300 * (2 ** (t / d * 3))
    shimmer = osc("sine", f, d) * 0.4 + osc("sine", f * 1.5, d) * 0.25 + osc("triangle", f * 2.01, d) * 0.15
    trem = 0.6 + 0.4 * np.sin(2 * np.pi * 18 * t)
    whoosh = sweep_lowpass(osc("noise", 0, d), 400, 6000) * 0.7
    e = env_adsr(len(t), 0.25, 0.3, 0.8, 0.35)
    return _norm((shimmer * trem + whoosh) * e)


def sfx_fireball():
    d = 1.3
    t = _t(d)
    roar = sweep_lowpass(osc("noise", 0, d), 3000, 500) * env_adsr(len(t), 0.05, 0.3, 0.6, 0.6)
    rumble = osc("sine", 60 + 30 * np.sin(2 * np.pi * 3 * t), d) * env_exp(len(t), 0.6) * 0.8
    crackle = (np.random.default_rng(3).random(len(t)) > 0.997).astype(np.float32) * env_exp(len(t), 0.5)
    return _norm(roar + rumble + crackle * 0.8)


def sfx_ice_spell():
    rng = np.random.default_rng(5)
    d = 1.4
    out = np.zeros(int(d * SR), np.float32)
    for i in range(14):
        st = int(rng.uniform(0, 0.8) * SR)
        f = rng.uniform(1800, 4200)
        tone = osc("sine", f, 0.5) * env_exp(int(0.5 * SR), 0.12)
        out[st:st + len(tone)] += tone[:len(out) - st] * rng.uniform(0.3, 0.8)
    out += sweep_lowpass(osc("noise", 0, d), 8000, 2000) * env_exp(len(out), 0.4) * 0.3
    return _norm(out)


def sfx_lightning():
    d = 1.4
    rng = np.random.default_rng(9)
    out = np.zeros(int(d * SR), np.float32)
    for i in range(6):
        st = int(rng.uniform(0, 0.3) * SR)
        burst = osc("noise", 0, 0.08) * env_exp(int(0.08 * SR), 0.02)
        out[st:st + len(burst)] += burst
    boom = lowpass(osc("noise", 0, d), 200) * env_exp(len(out), 0.45) * 4
    return _norm(out + boom)


def sfx_hit():
    d = 0.35
    t = _t(d)
    thump = osc("sine", 160 * np.exp(-t * 12) + 45, d) * env_exp(len(t), 0.12)
    crack = lowpass(osc("noise", 0, d), 3500) * env_exp(len(t), 0.03) * 1.2
    return _norm(_pad(thump + crack))


def sfx_critical_hit():
    h = sfx_hit()
    ding = osc("sine", 2093, 0.6) * env_exp(int(0.6 * SR), 0.2) * 0.5 + osc("sine", 3136, 0.6) * env_exp(int(0.6 * SR), 0.15) * 0.3
    out = np.zeros(max(len(h), len(ding) + 2000), np.float32)
    out[:len(h)] += h
    out[2000:2000 + len(ding)] += ding
    return _norm(out)


def sfx_explosion():
    d = 1.8
    t = _t(d)
    body = sweep_lowpass(osc("noise", 0, d), 2500, 150) * env_exp(len(t), 0.5) * 1.5
    sub = osc("sine", 50 * np.exp(-t * 2) + 30, d) * env_exp(len(t), 0.6)
    return _norm(body + sub)


def sfx_coin():
    return _norm(_pad(np.concatenate([osc("square", 988, 0.07, 0.5) * 0.8,
                                      osc("square", 1319, 0.35, 0.5) * env_exp(int(0.35 * SR), 0.12)])), 0.6)


def sfx_jump():
    d = 0.25
    t = _t(d)
    return _norm(_pad(osc("square", 280 + 600 * t / d, d, 0.25) * env_adsr(len(t), 0.005, 0.05, 0.8, 0.08)), 0.55)


def sfx_powerup():
    seq = [midi(n) for n in (60, 64, 67, 72, 64, 67, 72, 76, 67, 72, 76, 79)]
    return _norm(_pad(notes(seq, "square", 0.045, 0.25, 0.3)), 0.55)


def sfx_level_up():
    mel = notes([midi(n) for n in (67, 72, 76, 79)], "square", 0.11, 0.5, 0.3)
    hold = osc("square", midi(84), 0.6, 0.5) * env_exp(int(0.6 * SR), 0.35)
    harm = osc("triangle", midi(72), 0.6) * env_exp(int(0.6 * SR), 0.4) * 0.7
    return _norm(_pad(np.concatenate([mel, hold + harm])), 0.6)


def sfx_damage():
    d = 0.4
    t = _t(d)
    f = 700 * np.exp(-t * 5) + 120
    x = osc("square", f, d, 0.5) * (0.6 + 0.4 * np.sign(np.sin(2 * np.pi * 30 * t))) * env_adsr(len(t), 0.002, 0.05, 0.8, 0.1)
    return _norm(_pad(x), 0.55)


def sfx_heal():
    seq = [midi(n) for n in (72, 76, 79, 84, 88, 91)]
    a = notes(seq, "sine", 0.09, 0.5, 0.4)
    sh = osc("sine", 2600, len(a) / SR) * 0.15 * (0.5 + 0.5 * np.sin(2 * np.pi * 9 * _t(len(a) / SR)))
    return _norm(_pad(a + sh[:len(a)], 0.4), 0.6)


def sfx_game_over():
    seq = [midi(n) for n in (67, 66, 65, 64)]
    a = notes(seq, "triangle", 0.35, 0.5, 0.5)
    low = osc("square", midi(48), 0.9, 0.5) * env_exp(int(0.9 * SR), 0.5) * 0.5
    return _norm(_pad(np.concatenate([a, low]), 0.3), 0.6)


def sfx_quest_complete():
    mel = notes([midi(n) for n in (72, 72, 72, 76, 74, 76, 79)], "square", 0.1, 0.5, 0.25)
    hold = osc("square", midi(84), 0.7, 0.5) * env_exp(int(0.7 * SR), 0.4)
    bass = osc("triangle", midi(48), len(mel) / SR + 0.7) * 0.6
    x = np.concatenate([mel, hold])
    return _norm(_pad(x + bass[:len(x)]), 0.6)


def sfx_menu_select():
    return _norm(_pad(osc("square", 1568, 0.06, 0.25) * env_exp(int(0.06 * SR), 0.03), 0.05), 0.5)


def sfx_menu_move():
    return _norm(_pad(osc("square", 784, 0.03, 0.5) * env_exp(int(0.03 * SR), 0.02), 0.05), 0.4)


def sfx_text_blip():
    return _norm(_pad(osc("square", 620, 0.025, 0.5), 0.02), 0.35)


def sfx_laser():
    d = 0.35
    t = _t(d)
    return _norm(_pad(osc("saw", 1800 * np.exp(-t * 9) + 150, d) * env_exp(len(t), 0.15)), 0.6)


def sfx_boss_appear():
    d = 3.0
    t = _t(d)
    drone = osc("saw", 55 + 20 * t / d, d) * 0.5 + osc("saw", 55.7 + 20 * t / d, d) * 0.5
    drone = lowpass(drone, 600) * env_adsr(len(t), 0.8, 0.2, 1.0, 0.8)
    hits = np.zeros_like(drone)
    for k in (0.0, 0.9, 1.8):
        st = int(k * SR)
        b = lowpass(osc("noise", 0, 0.8), 180) * env_exp(int(0.8 * SR), 0.3) * 3
        hits[st:st + len(b)] += b[:len(hits) - st]
    return _norm(drone + hits)


def sfx_whoosh():
    d = 0.7
    t = _t(d)
    x = sweep_lowpass(osc("noise", 0, d), 300, 5000)
    e = np.sin(np.pi * t / d) ** 2
    return _norm(x * e)


def sfx_door():
    d = 0.9
    t = _t(d)
    creak = osc("saw", 90 + 40 * np.sin(2 * np.pi * 1.7 * t), d) * 0.4
    creak = lowpass(creak, 1200) * env_adsr(len(t), 0.05, 0.1, 0.8, 0.2)
    thud = lowpass(osc("noise", 0, 0.3), 150) * env_exp(int(0.3 * SR), 0.08) * 3
    out = np.concatenate([creak, thud])
    return _norm(out)


def sfx_battle_start():
    seq = []
    for k in range(4):
        seq += [midi(n) for n in (76 + k, 72 + k, 69 + k, 72 + k)]
    a = notes(seq, "square", 0.045, 0.5, 0.2)
    b = notes([midi(n) for n in (64, 67, 71, 76)], "square", 0.09, 0.25, 0.3)
    return _norm(_pad(np.concatenate([a, b]), 0.2), 0.6)


def sfx_tube_wobble():
    d = 0.18
    t = _t(d)
    knock = lowpass(osc("noise", 0, d), 1800) * env_exp(len(t), 0.02) * 2
    tone = osc("sine", 300 * np.exp(-t * 8) + 120, d) * env_exp(len(t), 0.05)
    return _norm(_pad(knock + tone, 0.1), 0.55)


def sfx_whos_question():
    """Quick rising 'guess!' sting."""
    lead = notes([midi(n) for n in (67, 71, 74, 79, 0, 79)], "square", 0.085, 0.25, 0.2)
    bass = notes([midi(n) for n in (43, 0, 50, 0, 0, 55)], "triangle", 0.085, 0.5, 0.25)
    m = min(len(lead), len(bass))
    hold = osc("square", midi(83), 0.45, 0.25) * env_exp(int(0.45 * SR), 0.25) * 0.8
    return _norm(_pad(np.concatenate([lead[:m] + bass[:m], hold]), 0.2), 0.6)


def sfx_whos_reveal():
    """Bright 'it's …!' fanfare."""
    a = notes([midi(n) for n in (72, 72, 72, 76, 79)], "square", 0.1, 0.5, 0.22, gap=0.01)
    b = notes([midi(n) for n in (48, 48, 48, 52, 55)], "triangle", 0.1, 0.5, 0.3, gap=0.01)
    chord = sum(osc("square", midi(n), 0.7, 0.5) * 0.4 for n in (72, 76, 79, 84)) * env_exp(int(0.7 * SR), 0.35)
    m = min(len(a), len(b))
    return _norm(_pad(np.concatenate([a[:m] + b[:m] * 0.8, chord]), 0.2), 0.62)


def sfx_evolve():
    """Five seconds of rising shimmer with faster and faster pulses."""
    d = 5.0
    t = _t(d)
    f = 300 * 2 ** (t / d * 2)
    rate = 2 + 14 * (t / d) ** 2
    puls = 0.5 + 0.5 * np.sign(np.sin(2 * np.pi * np.cumsum(rate) / SR))
    tone = (osc("square", f, d, 0.3) * 0.35 + osc("sine", f * 2, d) * 0.3) * (0.4 + 0.6 * puls)
    tone *= np.linspace(0.4, 1.0, len(t), dtype=np.float32)
    return _norm(_pad(tone.astype(np.float32), 0.1), 0.5)


def sfx_evolve_done():
    """Short victory tune for 'evolved into …!'."""
    a = notes([midi(n) for n in (67, 72, 76, 79, 76, 79, 84)], "square", 0.11, 0.5, 0.2)
    b = notes([midi(n) for n in (48, 52, 55, 60, 55, 60, 64)], "triangle", 0.11, 0.5, 0.3)
    m = min(len(a), len(b))
    hold = sum(osc("square", midi(n), 0.9, 0.5) * 0.35 for n in (72, 76, 79, 84)) * env_exp(int(0.9 * SR), 0.45)
    return _norm(_pad(np.concatenate([a[:m] + b[:m] * 0.8, hold]), 0.2), 0.62)


def sfx_badge():
    """Jingle for receiving a badge."""
    a = notes([midi(n) for n in (72, 74, 76, 77, 79, 0, 84)], "square", 0.12, 0.5, 0.2)
    b = notes([midi(n) for n in (60, 62, 64, 65, 67, 0, 72)], "triangle", 0.12, 0.5, 0.3)
    m = min(len(a), len(b))
    return _norm(_pad(a[:m] + b[:m] * 0.7, 0.4), 0.6)


def sfx_dex_beep():
    """Index device opening: two beeps and a scan whirr."""
    beeps = notes([midi(88), 0, midi(93)], "square", 0.07, 0.5, 0.06)
    d = 1.0
    t = _t(d)
    whirr = osc("triangle", 600 + 500 * np.sin(2 * np.pi * 3 * t), d) * 0.3 * np.linspace(1, 0, len(t))
    return _norm(_pad(np.concatenate([beeps, whirr.astype(np.float32)]), 0.1), 0.5)


def sfx_catch_success():
    a = notes([midi(n) for n in (72, 76, 79, 84, 79, 84)], "square", 0.09, 0.5, 0.25)
    hold = osc("square", midi(88), 0.5, 0.5) * env_exp(int(0.5 * SR), 0.3)
    return _norm(_pad(np.concatenate([a, hold]), 0.2), 0.6)


def sfx_catch_fail():
    d = 0.5
    t = _t(d)
    pop = osc("noise", 0, 0.08) * env_exp(int(0.08 * SR), 0.015) * 1.5
    fall = osc("square", 900 * np.exp(-t * 6) + 150, d, 0.5) * env_exp(len(t), 0.18) * 0.6
    out = fall.copy()
    out[:len(pop)] += pop
    return _norm(_pad(out), 0.6)


def sfx_tube_throw():
    d = 0.6
    t = _t(d)
    x = sweep_lowpass(osc("noise", 0, d), 3000, 800) * np.sin(np.pi * t / d) ** 2
    return _norm(x, 0.5)


# ------------------------------------------------------------- music loops
DRUM_CACHE = {}


def _kick():
    if "k" not in DRUM_CACHE:
        t = _t(0.25)
        DRUM_CACHE["k"] = osc("sine", 140 * np.exp(-t * 25) + 45, 0.25) * env_exp(len(t), 0.09)
    return DRUM_CACHE["k"]


def _snare():
    if "s" not in DRUM_CACHE:
        n = osc("noise", 0, 0.18)
        DRUM_CACHE["s"] = lowpass(n, 6000) * env_exp(len(n), 0.05) * 0.7
    return DRUM_CACHE["s"]


def _hat():
    if "h" not in DRUM_CACHE:
        n = osc("noise", 0, 0.05)
        DRUM_CACHE["h"] = (n - lowpass(n, 7000)) * env_exp(len(n), 0.012) * 0.6
    return DRUM_CACHE["h"]


def _sequence(bpm, bars, chords, melody_fn, bass_wave="triangle", lead_wave="square", drums="rock", duty=0.25):
    beat = 60.0 / bpm
    step = beat / 4  # 16th notes
    steps = bars * 16
    total = int(steps * step * SR) + SR
    out = np.zeros(total, np.float32)
    rng = np.random.default_rng(bpm * 7 + bars)

    def put(sig, st, gain):
        i = int(st * SR)
        j = min(total, i + len(sig))
        out[i:j] += sig[:j - i] * gain

    for bar in range(bars):
        root, quality = chords[bar % len(chords)]
        scale_notes = [root, root + (3 if quality == "m" else 4), root + 7]
        for s16 in range(16):
            t = (bar * 16 + s16) * step
            # bass on 8ths
            if s16 % 2 == 0:
                bn = scale_notes[0] - 12 if s16 % 8 != 6 else scale_notes[2] - 12
                b = osc(bass_wave, midi(bn), step * 1.8) * env_adsr(int(step * 1.8 * SR), 0.005, 0.05, 0.7, 0.03)
                put(b, t, 0.45)
            # arpeggio
            if drums != "calm" and s16 % 2 == 1:
                an = scale_notes[(s16 // 2) % 3] + 12
                a = osc("square", midi(an), step * 0.9, 0.125) * env_exp(int(step * 0.9 * SR), 0.05)
                put(a, t, 0.1)
            # drums
            if drums in ("rock", "fast"):
                if s16 in (0, 8) or (drums == "fast" and s16 in (4, 12, 10)):
                    put(_kick(), t, 0.9)
                if s16 in (4, 12):
                    put(_snare(), t, 0.6)
                if s16 % 2 == 0:
                    put(_hat(), t, 0.35)
            elif drums == "calm":
                if s16 == 0:
                    put(_kick(), t, 0.4)
                if s16 % 4 == 2:
                    put(_hat(), t, 0.15)
        # melody
        for (pos, length, note) in melody_fn(bar, scale_notes, rng):
            st = (bar * 16 + pos) * step
            dur = length * step
            m = osc(lead_wave, midi(note), dur, duty) * env_adsr(int(dur * SR), 0.005, 0.08, 0.6, 0.04)
            put(m, st, 0.28)
    return _norm(out[:int(steps * step * SR)], 0.7)


def _melody_major(bar, ch, rng):
    pat = [(0, 2), (2, 2), (4, 4), (8, 2), (10, 2), (12, 4)]
    scale = [0, 2, 4, 7, 9, 12]
    out = []
    for pos, ln in pat:
        if rng.random() < 0.15:
            continue
        out.append((pos, ln, ch[0] + 12 + int(rng.choice(scale))))
    return out


def _melody_minor(bar, ch, rng):
    out = []
    scale = [0, 3, 5, 7, 10, 12]
    for pos in range(0, 16, 2):
        if rng.random() < 0.3:
            continue
        out.append((pos, 2, ch[0] + 12 + int(rng.choice(scale))))
    return out


def _melody_calm(bar, ch, rng):
    return [(0, 6, ch[1] + 12), (8, 6, ch[2] + 12)] if bar % 2 == 0 else [(0, 12, ch[0] + 24)]


def music_adventure():
    chords = [(60, ""), (55, ""), (57, "m"), (53, "")]
    return _sequence(140, 16, chords, _melody_major)


def music_boss_battle():
    chords = [(57, "m"), (57, "m"), (53, ""), (55, "")]
    return _sequence(165, 16, chords, _melody_minor, bass_wave="saw", drums="fast", duty=0.5)


def music_village():
    chords = [(65, ""), (62, "m"), (60, ""), (67, "")]
    return _sequence(90, 12, chords, _melody_calm, lead_wave="triangle", drums="calm")


def music_suspense():
    chords = [(57, "m"), (58, ""), (57, "m"), (56, "")]
    return _sequence(80, 8, chords, lambda b, c, r: [(0, 14, c[0] + 12)] if b % 2 else [], lead_wave="sine",
                     bass_wave="triangle", drums="calm")


def music_victory():
    mel = [(0, 2, 72), (2, 2, 72), (4, 2, 72), (6, 6, 76), (12, 2, 74), (14, 2, 76), (16, 12, 79)]
    beat = 60 / 150 / 4
    total = int(32 * beat * SR) + SR
    out = np.zeros(total, np.float32)
    for pos, ln, n in mel:
        sig = osc("square", midi(n), ln * beat, 0.5) * env_adsr(int(ln * beat * SR), 0.005, 0.05, 0.7, 0.05)
        i = int(pos * beat * SR)
        out[i:i + len(sig)] += sig * 0.5
        b = osc("triangle", midi(n - 24), ln * beat) * 0.5
        out[i:i + len(b)] += b * 0.5
    return _norm(out)


GAME_SOUNDS = {
    # name: (label, group, function)
    "spell_cast": ("Spell cast (magic sweep)", "Magic & combat", sfx_spell_cast),
    "fireball": ("Fireball", "Magic & combat", sfx_fireball),
    "ice_spell": ("Ice spell", "Magic & combat", sfx_ice_spell),
    "lightning": ("Lightning", "Magic & combat", sfx_lightning),
    "hit": ("Hit", "Magic & combat", sfx_hit),
    "critical_hit": ("Critical hit", "Magic & combat", sfx_critical_hit),
    "explosion": ("Explosion", "Magic & combat", sfx_explosion),
    "laser": ("Laser", "Magic & combat", sfx_laser),
    "damage": ("Player takes damage", "Magic & combat", sfx_damage),
    "heal": ("Heal", "Magic & combat", sfx_heal),
    "boss_appear": ("Boss appears", "Magic & combat", sfx_boss_appear),
    "coin": ("Coin", "Retro game", sfx_coin),
    "jump": ("Jump", "Retro game", sfx_jump),
    "powerup": ("Power-up", "Retro game", sfx_powerup),
    "level_up": ("Level up", "Retro game", sfx_level_up),
    "quest_complete": ("Quest complete", "Retro game", sfx_quest_complete),
    "game_over": ("Game over", "Retro game", sfx_game_over),
    "menu_select": ("Menu select", "Menus & text", sfx_menu_select),
    "menu_move": ("Menu move", "Menus & text", sfx_menu_move),
    "text_blip": ("Text blip", "Menus & text", sfx_text_blip),
    "whoosh": ("Whoosh (transitions)", "Menus & text", sfx_whoosh),
    "door": ("Door", "Menus & text", sfx_door),
    "battle_start": ("Battle start jingle", "Creature battle", sfx_battle_start),
    "tube_throw": ("Throw (whoosh)", "Creature battle", sfx_tube_throw),
    "tube_wobble": ("Catch: wobble click", "Creature battle", sfx_tube_wobble),
    "catch_success": ("Catch: success jingle", "Creature battle", sfx_catch_success),
    "catch_fail": ("Catch: broke free", "Creature battle", sfx_catch_fail),
    "whos_question": ("Who's that …? question sting", "Creature battle", sfx_whos_question),
    "whos_reveal": ("Who's that …? reveal fanfare", "Creature battle", sfx_whos_reveal),
    "evolve": ("Evolution: rising shimmer", "Creature battle", sfx_evolve),
    "evolve_done": ("Evolution: evolved jingle", "Creature battle", sfx_evolve_done),
    "badge": ("Badge received jingle", "Creature battle", sfx_badge),
    "dex_beep": ("Index entry: beep and scan", "Creature battle", sfx_dex_beep),
    "music_adventure": ("Adventure (loop)", "Music: retro 8-bit", music_adventure),
    "music_boss_battle": ("Boss battle (loop)", "Music: retro 8-bit", music_boss_battle),
    "music_village": ("Calm village (loop)", "Music: retro 8-bit", music_village),
    "music_suspense": ("Suspense (loop)", "Music: retro 8-bit", music_suspense),
    "music_victory": ("Victory jingle", "Music: retro 8-bit", music_victory),
}


# Orchestral music (medieval quest / dark fantasy), stereo. Listed before the retro music.
from .music_themes import THEMES  # noqa: E402

_retro = {k: v for k, v in GAME_SOUNDS.items() if v[1] == "Music: retro 8-bit"}
for _k in _retro:
    GAME_SOUNDS.pop(_k)
GAME_SOUNDS.update(THEMES)
GAME_SOUNDS.update(_retro)
SOUND_VERSIONS = {k: 1 for k in THEMES}

def game_sound_file(folder: str, name: str) -> str:
    """Creates (once) and returns the WAV file for a built-in game sound.
    A version number in the file name makes improved sounds replace old copies."""
    os.makedirs(folder, exist_ok=True)
    ver = SOUND_VERSIONS.get(name)
    path = os.path.join(folder, f"{name}_v{ver}.wav" if ver else f"{name}.wav")
    if not os.path.exists(path):
        sig = GAME_SOUNDS[name][2]()
        stereo = sig if sig.ndim == 2 else np.stack([sig, sig], axis=1)
        write_wav(path, stereo)
    return path
