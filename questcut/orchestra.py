"""A small virtual orchestra for QuestCut's background music.

Instruments are made from scratch with numpy (no samples, no copyright):
  pluck  - plucked string (Karplus-Strong): harp, lute, pizzicato
  flute  - soft sine tone with breath and vibrato
  strings- several slightly detuned bowed voices, optional tremolo
  brass  - horn / trombone with a bright attack
  choir  - "aah"/"ooh" voices built from vocal formants
  drums  - timpani, taiko, frame drum, toms, shaker, tambourine, cymbal swell, bell, woodblock
Everything is placed left/right in stereo and sent through a hall echo (reverb).
A Score collects notes in beats and renders a seamless loop (the echo of the
last bar wraps into the first) or a one-shot jingle.
"""
from __future__ import annotations

import re

import numpy as np

from .media import SAMPLE_RATE

SR = SAMPLE_RATE
_RNG = np.random.default_rng(1)


def _n(sec):
    return max(1, int(round(sec * SR)))


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


_NOTE = re.compile(r"^([A-Ga-g])([#b]?)(-?\d)$")
_SEMI = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def note(s):
    """'C#4' -> 61, 'Bb3' -> 58; ints pass through."""
    if isinstance(s, (int, np.integer)):
        return int(s)
    m = _NOTE.match(s.strip())
    if not m:
        raise ValueError(f"not a note: {s}")
    v = _SEMI[m.group(1).upper()] + {"#": 1, "b": -1, "": 0}[m.group(2)]
    return v + 12 * (int(m.group(3)) + 1)


CHORDS = {"": [0, 4, 7], "m": [0, 3, 7], "dim": [0, 3, 6], "7": [0, 4, 7, 10], "m7": [0, 3, 7, 10],
          "sus4": [0, 5, 7], "sus2": [0, 2, 7], "5": [0, 7]}


def chord(name, octave=3):
    """'Dm' -> midi notes of D minor with the root in the given octave."""
    m = re.match(r"^([A-G][#b]?)(.*)$", name)
    root = note(m.group(1) + str(octave))
    return [root + i for i in CHORDS[m.group(2)]]


# ------------------------------------------------------------------ helpers
def _spec_filter(x, gain_fn):
    n = len(x)
    size = 1 << int(np.ceil(np.log2(max(2, n))))
    X = np.fft.rfft(x, size)
    f = np.fft.rfftfreq(size, 1 / SR)
    X *= gain_fn(f)
    return np.fft.irfft(X, size)[:n].astype(np.float32)


def lp(x, fc, order=2):
    return _spec_filter(x, lambda f: 1 / np.sqrt(1 + (f / fc) ** (2 * order)))


def hp(x, fc, order=2):
    return _spec_filter(x, lambda f: 1 / np.sqrt(1 + (fc / np.maximum(f, 1e-3)) ** (2 * order)))


def bp(x, f0, width):
    return _spec_filter(x, lambda f: np.exp(-0.5 * ((f - f0) / width) ** 2))


def env(n_hold, attack=0.01, decay=0.1, sustain=0.8, release=0.2):
    """Attack - decay - sustain for n_hold samples, then release."""
    a, d, r = _n(attack), _n(decay), _n(release)
    e = np.empty(n_hold + r, np.float32)
    a = min(a, n_hold)
    e[:a] = np.linspace(0, 1, a, endpoint=False)
    rest = n_hold - a
    if rest > 0:
        t = np.arange(rest) / max(1, d)
        e[a:n_hold] = sustain + (1 - sustain) * np.exp(-t * 3)
    last = e[n_hold - 1] if n_hold > 0 else 0
    e[n_hold:] = last * np.exp(-np.arange(r) / max(1, r) * 6)
    return e


def _phase(freq, n, vib_rate=0.0, vib_depth=0.0, vib_delay=0.25, start=None):
    t = np.arange(n) / SR
    f = np.full(n, freq, np.float64)
    if vib_depth:
        ramp = np.clip((t - vib_delay) / 0.4, 0, 1)
        f *= 1 + vib_depth * ramp * np.sin(2 * np.pi * vib_rate * t + _RNG.uniform(0, 6.28))
    ph = np.cumsum(f) / SR
    return ph + (_RNG.uniform(0, 1) if start is None else start)


# ------------------------------------------------------------------ instruments
def pluck(freq, dur, vel=0.6, bright=0.5, t60=1.5):
    """Plucked string (harp, lute, pizzicato)."""
    N = max(2, int(round(SR / freq)))
    ring = dur + min(1.2, 0.5 * t60)
    total = _n(ring)
    init = _RNG.uniform(-1, 1, N)
    for _ in range(int(1 + (1 - bright) * 6)):
        init = 0.5 * (init + np.roll(init, 1))
    init -= init.mean()
    g = 10 ** (-3 * (N / SR) / t60)
    out = np.empty(total + N, np.float64)
    buf = init
    out[:N] = buf
    before_last = 0.0
    pos = N
    while pos < total:
        shifted = np.empty(N)
        shifted[0] = before_last
        shifted[1:] = buf[:-1]
        before_last = buf[-1]
        buf = g * 0.5 * (buf + shifted)
        out[pos:pos + N] = buf
        pos += N
    out = out[:total].astype(np.float32)
    damp = np.ones(total, np.float32)
    h = _n(dur)
    if h < total:
        damp[h:] = np.exp(-np.arange(total - h) / max(1, total - h) * 5)
    out *= damp
    out = lp(out, 1500 + 6000 * bright)
    return out * vel * 1.7 / (np.abs(out).max() + 1e-9)


def harp(freq, dur, vel=0.6):
    return pluck(freq, dur, vel, bright=0.62, t60=2.6)


def lute(freq, dur, vel=0.6):
    return pluck(freq, dur, vel, bright=0.48, t60=1.3)


def pizz(freq, dur, vel=0.6):
    return pluck(freq, min(dur, 0.25), vel, bright=0.35, t60=0.4)


def flute(freq, dur, vel=0.5):
    n = _n(dur)
    e = env(n, 0.06, 0.15, 0.85, 0.15)
    ph = _phase(freq, len(e), 5.2, 0.006, 0.25)
    s = (np.sin(2 * np.pi * ph) + 0.32 * np.sin(4 * np.pi * ph) + 0.1 * np.sin(6 * np.pi * ph)
         + 0.04 * np.sin(8 * np.pi * ph))
    breath = bp(_RNG.normal(0, 1, len(e)).astype(np.float32), freq * 2, freq * 0.6) * 0.05
    chiff = hp(_RNG.normal(0, 1, len(e)).astype(np.float32), 2000) * np.exp(-np.arange(len(e)) / (0.03 * SR)) * 0.08
    return ((s * 0.7 + breath) * e + chiff).astype(np.float32) * vel


def strings(freq, dur, vel=0.4, attack=0.25, release=0.45, tremolo=0.0, voices=5, bright=2600.0):
    n = _n(dur)
    e = env(n, attack, 0.3, 0.9, release)
    m = len(e)
    s = np.zeros(m, np.float64)
    for cents in np.linspace(-9, 9, voices):
        ph = _phase(freq * 2 ** (cents / 1200), m, 5.5, 0.004, 0.3)
        s += 2 * (ph % 1.0) - 1
    s /= voices
    s = lp(s.astype(np.float32), min(bright, 700 + freq * 10))
    s = hp(s, 60)
    if tremolo:
        t = np.arange(m) / SR
        s *= 1 - tremolo * 0.5 * (1 + np.sin(2 * np.pi * 12 * t))
    return (s * e * vel * 1.6).astype(np.float32)


def brass(freq, dur, vel=0.5):
    n = _n(dur)
    e = env(n, 0.05, 0.2, 0.8, 0.18)
    m = len(e)
    t = np.arange(m) / SR
    s = np.zeros(m, np.float64)
    for cents in (-4, 3):
        f = freq * 2 ** (cents / 1200) * (1 - 0.025 * np.exp(-t / 0.04))
        ph = np.cumsum(f) / SR + _RNG.uniform(0, 1)
        s += 2 * (ph % 1.0) - 1
    s = (s / 2).astype(np.float32)
    dark = lp(s, 500 + freq * 1.5)
    bright = lp(s, 2600 + freq * 5 * (0.5 + vel))
    b = (0.25 + 0.75 * np.exp(-t / 0.12)) * (0.4 + 0.6 * vel)
    out = dark * (1 - b) + bright * b
    return (out * e * vel * 1.5).astype(np.float32)


VOWELS = {"a": [(800, 1.0, 90), (1150, 0.55, 110), (2900, 0.22, 170)],
          "o": [(450, 1.0, 70), (800, 0.45, 90), (2830, 0.1, 150)],
          "u": [(325, 1.0, 60), (700, 0.25, 80), (2530, 0.06, 150)]}


def choir(freq, dur, vel=0.35, vowel="a", voices=3):
    n = _n(dur)
    e = env(n, 0.35, 0.4, 0.9, 0.7)
    m = len(e)
    form = VOWELS[vowel]
    s = np.zeros(m, np.float64)
    kmax = int(min(5000, SR / 2.2) / freq)
    amps = []
    for k in range(1, kmax + 1):
        fk = k * freq
        a = sum(g * np.exp(-0.5 * ((fk - F) / bw) ** 2) for F, g, bw in form) + 0.02 / k
        amps.append(a)
    amps = np.array(amps)
    amps /= amps.max() + 1e-9
    for v in range(voices):
        ph = _phase(freq * 2 ** (_RNG.uniform(-7, 7) / 1200), m, 5.3 + v * 0.3, 0.007, 0.2)
        two_pi_ph = 2 * np.pi * ph
        for k, a in enumerate(amps, 1):
            if a > 0.02:
                s += a * np.sin(k * two_pi_ph)
    s /= voices * 3
    air = bp(_RNG.normal(0, 1, m).astype(np.float32), form[0][0], 300) * 0.02
    return ((s + air) * e * vel * 1.4).astype(np.float32)


def _decay(n, t):
    return np.exp(-np.arange(n) / (t * SR)).astype(np.float32)


def timpani(freq, dur=1.5, vel=0.6):
    m = _n(max(dur, 1.6))
    t = np.arange(m) / SR
    f = freq * (1 + 0.012 * np.exp(-t / 0.05))
    ph = np.cumsum(f) / SR
    s = np.zeros(m)
    for r, a, d in ((1, 1, 1.4), (1.5, 0.5, 0.9), (1.99, 0.3, 0.7), (2.44, 0.15, 0.5)):
        s += a * np.sin(2 * np.pi * r * ph) * np.exp(-t / d)
    thump = lp(_RNG.normal(0, 1, m).astype(np.float32), 400) * np.exp(-t / 0.03) * 0.6
    return ((s * 0.55 + thump) * vel).astype(np.float32)


def taiko(freq=55.0, dur=1.0, vel=0.8):
    m = _n(1.2)
    t = np.arange(m) / SR
    f = freq * (1 + 0.6 * np.exp(-t / 0.03))
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.35)
    skin = lp(_RNG.normal(0, 1, m).astype(np.float32), 900) * np.exp(-t / 0.05) * 0.5
    return ((s + skin) * vel).astype(np.float32)


def frame_drum(freq=95.0, dur=0.4, vel=0.5):
    m = _n(0.45)
    t = np.arange(m) / SR
    s = np.sin(2 * np.pi * np.cumsum(freq * (1 + 0.3 * np.exp(-t / 0.02))) / SR) * np.exp(-t / 0.14)
    skin = bp(_RNG.normal(0, 1, m).astype(np.float32), 1800, 900) * np.exp(-t / 0.03) * 0.35
    return ((s + skin) * vel).astype(np.float32)


def tom(freq=110.0, dur=0.6, vel=0.5):
    m = _n(0.7)
    t = np.arange(m) / SR
    s = np.sin(2 * np.pi * np.cumsum(freq * (1 + 0.25 * np.exp(-t / 0.03))) / SR) * np.exp(-t / 0.25)
    skin = lp(_RNG.normal(0, 1, m).astype(np.float32), 2500) * np.exp(-t / 0.025) * 0.3
    return ((s + skin) * vel).astype(np.float32)


def shaker(freq=0.0, dur=0.1, vel=0.2):
    m = _n(0.09)
    t = np.arange(m) / SR
    e = np.minimum(1, t / 0.012) * np.exp(-t / 0.03)
    return (hp(_RNG.normal(0, 1, m).astype(np.float32), 5000) * e * vel * 0.5).astype(np.float32)


def tambourine(freq=0.0, dur=0.2, vel=0.3):
    m = _n(0.25)
    t = np.arange(m) / SR
    jingle = sum(np.sin(2 * np.pi * f * t + _RNG.uniform(0, 6)) for f in (5200, 6900, 8800, 10400)) / 4
    s = (hp(_RNG.normal(0, 1, m).astype(np.float32), 6000) * 0.6 + jingle * 0.5) * np.exp(-t / 0.07)
    return (s * vel * 0.5).astype(np.float32)


def cymbal_swell(freq=0.0, dur=2.0, vel=0.35):
    m = _n(dur + 0.4)
    t = np.arange(m) / SR
    e = np.where(t < dur, (t / dur) ** 2.5, np.exp(-(t - dur) / 0.12))
    s = hp(_RNG.normal(0, 1, m).astype(np.float32), 3500)
    return (lp(s, 11000) * e * vel * 0.6).astype(np.float32)


def bell(freq, dur=3.0, vel=0.4):
    m = _n(3.5)
    t = np.arange(m) / SR
    s = np.zeros(m)
    for r, a, d in ((0.5, 0.3, 3.0), (1, 1, 2.6), (1.19, 0.35, 1.6), (1.56, 0.3, 1.3), (2, 0.4, 1.1),
                    (2.51, 0.2, 0.8), (2.66, 0.15, 0.7), (3.01, 0.1, 0.55), (4.1, 0.08, 0.4)):
        if r * freq < SR / 2.2:
            s += a * np.sin(2 * np.pi * r * freq * t + _RNG.uniform(0, 6)) * np.exp(-t / d)
    s *= np.minimum(1, t / 0.002)
    return (s * vel * 0.35).astype(np.float32)


def woodblock(freq=900.0, dur=0.1, vel=0.4):
    m = _n(0.12)
    t = np.arange(m) / SR
    s = np.sin(2 * np.pi * freq * t) * np.exp(-t / 0.025) + np.sin(2 * np.pi * freq * 2.3 * t) * np.exp(-t / 0.01) * 0.4
    return (s * vel * 0.6).astype(np.float32)


def boom(freq=40.0, dur=2.5, vel=0.9):
    """Deep cinematic hit."""
    m = _n(dur)
    t = np.arange(m) / SR
    s = np.sin(2 * np.pi * np.cumsum(freq * (1 + 1.5 * np.exp(-t / 0.05))) / SR) * np.exp(-t / 0.8)
    rumble = lp(_RNG.normal(0, 1, m).astype(np.float32), 150) * np.exp(-t / 0.6) * 0.5
    return ((s + rumble) * vel).astype(np.float32)


INSTRUMENTS = {"harp": harp, "lute": lute, "pizz": pizz, "flute": flute, "strings": strings, "brass": brass,
               "choir": choir, "timpani": timpani, "taiko": taiko, "frame": frame_drum, "tom": tom,
               "shaker": shaker, "tambourine": tambourine, "swell": cymbal_swell, "bell": bell,
               "woodblock": woodblock, "boom": boom}
DEFAULT_PAN = {"harp": -0.35, "lute": -0.3, "pizz": -0.2, "flute": 0.25, "strings": 0.0, "brass": 0.3,
               "choir": 0.0, "timpani": -0.1, "taiko": 0.0, "frame": 0.15, "tom": 0.1, "shaker": 0.45,
               "tambourine": 0.4, "swell": 0.0, "bell": 0.35, "woodblock": 0.3, "boom": 0.0}


# ------------------------------------------------------------------ echo of a hall
def reverb(st, rt60=2.0, wet=0.3, damp=4500.0, predelay=0.025):
    """Stereo hall echo by convolution with a decaying-noise impulse response."""
    n = _n(rt60 * 1.1)
    t = np.arange(n) / SR
    out = []
    for ch in range(2):
        ir = _RNG.normal(0, 1, n).astype(np.float32) * (10 ** (-3 * t / rt60)).astype(np.float32)
        ir = lp(ir, damp)
        ir[:_n(predelay)] = 0
        ir /= np.sqrt((ir ** 2).sum()) + 1e-9
        x = st[:, ch]
        size = 1 << int(np.ceil(np.log2(len(x) + n)))
        y = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[:len(x) + n]
        dry = np.zeros(len(x) + n, np.float32)
        dry[:len(x)] = x
        out.append(dry * (1 - wet * 0.5) + y.astype(np.float32) * wet)
    return np.stack(out, axis=1)


# ------------------------------------------------------------------ score
class Score:
    """Notes placed in beats; render() makes the stereo audio."""

    def __init__(self, bpm, seed=1):
        self.spb = 60.0 / bpm
        self.events = []
        global _RNG
        _RNG = np.random.default_rng(seed)

    def add(self, inst, beat, dur, pitch=None, vel=0.5, pan=None, **kw):
        if isinstance(pitch, (list, tuple)):
            for p in pitch:
                self.add(inst, beat, dur, p, vel, pan, **kw)
            return
        self.events.append((inst, beat, dur, pitch, vel, DEFAULT_PAN.get(inst, 0) if pan is None else pan, kw))

    def melody(self, inst, start, spec, vel=0.5, shift=0, pan=None, legato=0.95, **kw):
        """spec: 'A4 1.5 D5 .5 r 1 E5 1' (note, beats; r = rest). Returns the end beat."""
        tok = spec.split()
        b = start
        for i in range(0, len(tok), 2):
            nm, ln = tok[i], float(tok[i + 1])
            if nm != "r":
                self.add(inst, b, ln * legato, note(nm) + shift, vel, pan, **kw)
            b += ln
        return b

    def render(self, total_beats, loop=True, rt60=2.0, wet=0.3, level=0.85, tail=4.0):
        L = _n(total_beats * self.spb)
        T = _n(tail)
        buf = np.zeros((L + T, 2), np.float32)
        cache = {}
        for inst, beat, dur, pitch, vel, pan, kw in self.events:
            f = hz(note(pitch)) if pitch is not None else kw.pop("freq", None)
            key = (inst, round(f or 0, 3), round(dur, 3), round(vel, 3), tuple(sorted(kw.items())))
            sig = cache.get(key)
            if sig is None:
                fn = INSTRUMENTS[inst]
                sig = fn(f, dur * self.spb, vel, **kw) if f is not None else fn(dur=dur * self.spb, vel=vel, **kw)
                cache[key] = sig
            i = _n(beat * self.spb)
            if i >= len(buf):
                continue
            seg = sig[:len(buf) - i]
            gl, gr = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
            buf[i:i + len(seg), 0] += seg * gl
            buf[i:i + len(seg), 1] += seg * gr
        wetbuf = reverb(buf, rt60, wet)
        if loop:
            out = wetbuf[:L].copy()
            spill = wetbuf[L:]
            k = min(len(spill), L)
            out[:k] += spill[:k]                 # the echo of the end flows into the start: seamless loop
        else:
            out = wetbuf
            loud = np.where(np.abs(out).max(axis=1) > 1e-4 * (np.abs(out).max() + 1e-9))[0]
            out = out[:(loud[-1] + _n(0.05)) if len(loud) else len(out)]
            fade = _n(0.05)
            out[-fade:] *= np.linspace(1, 0, fade)[:, None]
        out = np.stack([hp(out[:, 0], 38), hp(out[:, 1], 38)], axis=1)
        peak = np.abs(out).max() + 1e-9
        out = np.tanh(1.3 * out / peak) / np.tanh(1.3)       # gentle limiter
        return (out * level).astype(np.float32)
