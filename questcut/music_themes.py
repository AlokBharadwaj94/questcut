"""Original background music in two moods:
  * medieval quest (in the spirit of RuneScape): lute, harp, flute, frame drum
  * dark fantasy (in the spirit of Elden Ring): choir, strings, brass, timpani, bells
All melodies are new; only the feel is borrowed. Loops repeat seamlessly."""
from __future__ import annotations

from .orchestra import Score, chord, note


def _bars(spec_bars, per_bar):
    """Joins one melody string per bar and checks every bar has the right length."""
    for i, b in enumerate(spec_bars):
        tok = b.split()
        total = sum(float(tok[k + 1]) for k in range(0, len(tok), 2))
        if abs(total - per_bar) > 1e-6:
            raise ValueError(f"bar {i + 1} has {total} beats, not {per_bar}: {b}")
    return " ".join(spec_bars)


def _arp(sc, inst, start, notes, pattern, step, vel, dur=None):
    for k, idx in enumerate(pattern):
        if idx is None:
            continue
        octave, i = divmod(idx, len(notes))
        sc.add(inst, start + k * step, dur or step * 1.6, notes[i] + 12 * octave, vel)


# ====================================================================== medieval quest
def quest_giver():
    """Warm village tune for an NPC giving a quest (D dorian, 3/4)."""
    sc = Score(100, seed=11)
    prog = ["Dm", "C", "G", "Dm", "F", "C", "G", "A", "Dm", "C", "G", "Am", "F", "C", "Gm", "A"]
    for b, ch in enumerate(prog):
        s = b * 3
        n = chord(ch, 3)
        _arp(sc, "lute", s, n, [0, 2, 3, 4, 5, 4], 0.5, 0.42)
        sc.add("harp", s, 2.8, n[0] - 12, 0.5)
        sc.add("strings", s, 3.0, [n[0], n[1] + 12, n[2]], 0.12, attack=0.5)
        sc.add("frame", s, 0.5, None, 0.32, freq=90)
        sc.add("frame", s + 2, 0.5, None, 0.16, freq=110)
    mel = _bars(["A4 1.5 D5 .5 E5 1", "F5 1 E5 1 C5 1", "D5 1.5 B4 .5 G4 1", "A4 3",
                 "A4 1 C5 1 F5 1", "G5 1.5 F5 .5 E5 1", "D5 1 B4 1 D5 1", "E5 2 C#5 1",
                 "D5 1.5 E5 .5 F5 1", "G5 1 E5 1 C5 1", "B4 1 D5 1 G5 1", "A5 2 E5 1",
                 "F5 1 E5 .5 D5 .5 C5 1", "E5 1.5 D5 .5 C5 1", "D5 1 Bb4 1 G4 1", "A4 1.5 C#5 .5 E5 1"], 3)
    sc.melody("flute", 0, mel, 0.42)
    return sc.render(48, rt60=1.8, wet=0.28)


def setting_off():
    """Hopeful travelling music after accepting a quest (C major, 4/4)."""
    sc = Score(92, seed=12)
    prog = ["C", "G", "Am", "F", "C", "G", "F", "G", "Am", "F", "C", "G", "F", "G", "C", "G"]
    for b, ch in enumerate(prog):
        s = b * 4
        n = chord(ch, 3)
        _arp(sc, "harp", s, n, [0, 1, 2, 3, 4, 3, 2, 1], 0.5, 0.36)
        sc.add("strings", s, 4.0, [n[0] - 12, n[0], n[1] + 12, n[2] + 12], 0.13, attack=0.6)
        sc.add("frame", s, 0.5, None, 0.3, freq=85)
        sc.add("frame", s + 2, 0.5, None, 0.22, freq=85)
        for k in range(8):
            sc.add("shaker", s + k * 0.5, 0.1, None, 0.12 if k % 2 else 0.18)
        if b % 4 == 0:
            sc.add("timpani", s, 2, note("C2") if ch == "C" else n[0] - 24, 0.35)
    mel = _bars(["E5 2 G5 1 E5 1", "D5 3 B4 1", "C5 2 E5 1 A5 1", "G5 2 F5 1 E5 1",
                 "E5 1.5 F5 .5 G5 2", "A5 1 G5 1 F5 1 D5 1", "C5 1 D5 1 F5 1 A5 1", "G5 4",
                 "A5 2 G5 1 E5 1", "F5 1.5 E5 .5 C5 2", "E5 1 G5 1 C6 2", "B5 2 G5 1 D5 1",
                 "C6 1.5 A5 .5 F5 2", "B5 1 A5 1 G5 1 D5 1", "E5 3 D5 1", "D5 2 G4 1 B4 1"], 4)
    sc.melody("flute", 0, mel, 0.4)
    return sc.render(64, rt60=2.0, wet=0.3)


def tavern():
    """Lively tavern jig (G mixolydian, 6/8): fiddle, lute, frame drum, tambourine."""
    sc = Score(336, seed=13)                     # one beat = one eighth note
    prog = ["G", "G", "F", "G", "G", "C", "Dm", "G", "C", "G", "F", "G", "C", "G", "Dm", "G"]
    for b, ch in enumerate(prog):
        s = b * 6
        n = chord(ch, 3)
        sc.add("lute", s, 2.5, n[0] - 12, 0.5)
        sc.add("lute", s + 3, 2.5, n[2] - 12, 0.45)
        for k, v in ((1, 0.32), (4, 0.3)):
            sc.add("lute", s + k, 1.8, [n[0] + 12, n[1] + 12, n[2] + 12], v)
        sc.add("frame", s, 1, None, 0.45, freq=95)
        sc.add("frame", s + 3, 1, None, 0.32, freq=105)
        sc.add("tambourine", s + 3, 1, None, 0.25)
        for k in range(6):
            sc.add("shaker", s + k, 0.5, None, 0.1 if k % 3 else 0.16)
    mel = _bars(["D5 1 B4 1 G4 1 B4 1 D5 1 G5 1", "A5 2 G5 1 F5 1 E5 1 D5 1", "C5 1 F5 1 A5 1 G5 1 F5 1 E5 1",
                 "D5 3 B4 2 G4 1", "G4 1 A4 1 B4 1 C5 1 D5 1 E5 1", "E5 2 C5 1 G5 2 E5 1",
                 "F5 1 E5 1 D5 1 A4 1 D5 1 F5 1", "G5 2 D5 1 B4 2 G4 1",
                 "E5 1 G5 1 C6 1 G5 1 E5 1 C5 1", "D5 1 B4 1 G4 1 B4 1 D5 1 G5 1", "A5 1 G5 1 F5 1 C5 1 F5 1 A5 1",
                 "G5 2 F5 1 D5 2 B4 1", "C5 1 E5 1 G5 1 C6 2 G5 1", "D5 1 G5 1 B5 1 A5 1 G5 1 D5 1",
                 "F5 2 E5 1 D5 2 C5 1", "B4 1 D5 1 G5 1 G5 3"], 6)
    sc.melody("strings", 0, mel, 0.4, legato=0.85, attack=0.02, release=0.12, voices=2, bright=4200, pan=0.3)
    return sc.render(96, rt60=1.1, wet=0.2)


def sneaking():
    """Tiptoe music: pizzicato bass, short flute notes, woodblock (A minor)."""
    sc = Score(104, seed=14)
    prog = ["Am", "Am", "Dm", "E", "Am", "Am", "F", "E"]
    for b, ch in enumerate(prog):
        s = b * 4
        n = chord(ch, 2)
        r = n[0]
        line = [r, None, r + 3 if "m" in ch else r + 4, None, r + 7, None, r + 6, r + 7]
        for k, p in enumerate(line):
            if p is not None:
                sc.add("pizz", s + k * 0.5, 0.3, p, 0.55)
        for k in (1, 3):
            sc.add("pizz", s + k, 0.2, [x + 12 for x in chord(ch, 3)], 0.22)
        sc.add("woodblock", s + 3.5, 0.1, None, 0.25, freq=1100)
        if b % 2 == 0:
            sc.melody("flute", s + 2, "E5 .25 r .25 E5 .25 r .25 G5 .5", 0.3, legato=0.7)
        else:
            sc.melody("flute", s + 2, "F5 .25 r .25 E5 .25 r .25 D#5 .5", 0.3, legato=0.7)
    return sc.render(32, rt60=1.2, wet=0.22)


def medieval_battle():
    """Fight music with a medieval feel: drums, string ostinato, horn tune (A minor)."""
    sc = Score(132, seed=15)
    prog = ["Am", "Am", "G", "G", "F", "F", "E", "E", "Am", "Am", "G", "G", "F", "G", "E", "E"]
    for b, ch in enumerate(prog):
        s = b * 4
        n = chord(ch, 2)
        r = n[0]
        for k, p in enumerate([r, r + 12, r + 7, r + 12, r, r + 12, r + 7, r + 12]):
            sc.add("strings", s + k * 0.5, 0.35, p + 12, 0.32, attack=0.01, release=0.08, voices=3, bright=3200)
        for k, (fr, v) in enumerate([(95, .5), (0, 0), (150, .3), (95, .35), (95, .45), (0, 0), (150, .35), (180, .3)]):
            if v:
                sc.add("tom", s + k * 0.5, 0.5, None, v, freq=fr)
        sc.add("tambourine", s + 1, 0.3, None, 0.18)
        sc.add("tambourine", s + 3, 0.3, None, 0.18)
        sc.add("strings", s, 4, [n[0] + 12, n[1] + 12, n[2] + 12], 0.1, attack=0.3)
        if b % 4 == 0:
            sc.add("timpani", s, 2, r - 12 if r > 40 else r, 0.45)
    mel = _bars(["A4 1 C5 1 E5 2", "D5 1 C5 1 B4 2", "G4 1 B4 1 D5 2", "D5 1 B4 1 G4 2",
                 "A4 1 C5 1 F5 2", "E5 1 D5 1 C5 2", "B4 1 G#4 1 E5 2", "E5 4",
                 "E5 2 A5 2", "G5 1 F5 1 E5 2", "D5 2 G5 2", "F5 1 E5 1 D5 2",
                 "C5 2 F5 2", "G5 1 F5 1 D5 2", "E5 1 D5 1 B4 2", "G#4 2 B4 2"], 4)
    sc.melody("brass", 0, mel, 0.42, shift=-12)
    sc.add("swell", 60, 4, None, 0.3)
    return sc.render(64, rt60=1.6, wet=0.25)


def quest_accepted():
    """Short bright jingle: 'quest accepted'."""
    sc = Score(100, seed=16)
    gliss = ["G3", "A3", "B3", "D4", "E4", "G4", "A4", "B4", "D5", "E5", "G5"]
    for i, nm in enumerate(gliss):
        sc.add("harp", i * 0.09, 1.5, nm, 0.32)
    sc.melody("brass", 1.0, "D4 .25 G4 .25 B4 .5 D5 2.5", 0.55)
    sc.add("strings", 1.0, 3.5, chord("G", 3) + [note("D4"), note("G4"), note("B4")], 0.2, attack=0.15)
    sc.add("timpani", 1.0, 2, "G2", 0.55)
    sc.add("bell", 2.0, 2, "G5", 0.4)
    return sc.render(6, loop=False, rt60=2.0, wet=0.3)


def quest_complete_fanfare():
    """Big orchestral fanfare for finishing a quest."""
    sc = Score(100, seed=17)
    sc.melody("brass", 0, "C4 .33 E4 .33 G4 .34 C5 1.5 A4 .5 C5 .5 F5 1 E5 .5 D5 .5 G5 1", 0.55)
    sc.add("brass", 6.0, 3.5, ["C4", "E4", "G4", "C5"], 0.5)
    sc.add("strings", 1.0, 2.0, chord("C", 3), 0.2)
    sc.add("strings", 3.0, 1.0, chord("F", 3), 0.2)
    sc.add("strings", 4.0, 2.0, chord("G", 3), 0.22)
    sc.add("strings", 6.0, 4.0, chord("C", 3) + [note("C5"), note("E5"), note("G5")], 0.25)
    sc.add("choir", 6.0, 4.0, ["C4", "E4", "G4", "C5"], 0.3)
    for k in range(10):
        sc.add("timpani", 4.5 + k * 0.15, 1, "G2", 0.15 + k * 0.03)
    sc.add("timpani", 6.0, 2, "C2", 0.7)
    sc.add("swell", 3.5, 2.5, None, 0.35)
    sc.add("bell", 6.0, 3, "C6", 0.35)
    return sc.render(10, loop=False, rt60=2.2, wet=0.32)


# ====================================================================== dark fantasy
def monster_steals():
    """Danger music: something precious is being stolen (C minor, driving)."""
    sc = Score(138, seed=21)
    prog = ["Cm", "Cm", "Ab", "Ab", "Fm", "Fm", "G", "G", "Cm", "Cm", "Ab", "Ab", "Db", "Db", "G", "G"]
    for b, ch in enumerate(prog):
        s = b * 4
        n = chord(ch, 2)
        r = n[0]
        for k, p in enumerate([r, r, r + 12, r, r + 3 if ch != "G" else r + 4, r, r + 2 if ch != "Db" else r + 1, r]):
            sc.add("strings", s + k * 0.5, 0.4, p, 0.42, attack=0.01, release=0.06, voices=3, bright=2200)
        hi = [x + 12 for x in chord(ch, 3)]
        sc.add("brass", s, 0.45, hi, 0.4 if b < 8 else 0.5)
        sc.add("brass", s + 1.5, 0.45, hi, 0.35 if b < 8 else 0.45)
        sc.add("strings", s, 4, hi + [hi[0] + 12], 0.12, attack=0.1, tremolo=0.8)
        sc.add("timpani", s, 1.5, r if r < 45 else r - 12, 0.55)
        sc.add("timpani", s + 2.5, 1.0, r + 7 - 12 if r > 40 else r + 7, 0.3)
        if b >= 8:
            sc.add("choir", s, 4, [x + 12 for x in chord(ch, 3)], 0.2)
    for start in (28, 60):
        for k in range(8):
            sc.add("timpani", start + k * 0.5, 0.5, "G2", 0.2 + k * 0.05)
        sc.add("swell", start, 4, None, 0.35)
    sc.add("taiko", 0, 1, None, 0.8)
    sc.add("taiko", 32, 1, None, 0.8)
    mel = _bars(["G4 2 C5 2", "Eb5 2 D5 1 C5 1", "Eb5 3 C5 1", "Ab4 4",
                 "Ab4 2 Db5 2", "F5 3 Eb5 1", "D5 2 B4 2", "G4 4"], 4)
    sc.melody("brass", 32, mel, 0.55, shift=-12)
    return sc.render(64, rt60=2.2, wet=0.28)


def dark_boss():
    """Boss fight with choir, pounding drums and low brass (D minor with a dark Eb)."""
    sc = Score(112, seed=22)
    prog = ["Dm", "Dm", "Eb", "Dm", "Dm", "Bb", "Eb", "A", "Dm", "Dm", "Eb", "Dm", "Bb", "Gm", "Eb", "A"]
    for b, ch in enumerate(prog):
        s = b * 4
        n = chord(ch, 2)
        r = n[0]
        for k, p in enumerate([r, r, r + 12, r, r, r + 12, r + 1, r]):
            sc.add("strings", s + k * 0.5, 0.4, p, 0.4, attack=0.01, release=0.06, voices=3, bright=2000)
        for pos, v in ((0, 0.6), (1.5, 0.35), (2, 0.5), (3.5, 0.4)):
            sc.add("timpani", s + pos, 1, "D2" if pos != 1.5 else "A2", v * 0.85)
        sc.add("taiko", s, 1, None, 0.5)
        sc.add("taiko", s + 2, 1, None, 0.3)
        sc.add("choir", s, 4, [x + 12 for x in chord(ch, 3)], 0.3 if b >= 4 else 0.2, vowel="a")
        if b % 4 == 0:
            sc.add("bell", s, 3, "D5", 0.35)
    mel = _bars(["D4 2 F4 1 A4 1", "Bb4 3 A4 1", "G4 2 F4 1 Eb4 1", "E4 2 C#4 2",
                 "D5 2 A4 2", "F5 2 E5 1 D5 1", "Eb5 3 D5 1", "D5 4",
                 "F5 2 D5 2", "D5 2 Bb4 2", "Eb5 3 D5 1", "E5 2 C#5 2"], 4)
    sc.melody("brass", 16, mel, 0.55, shift=-12)
    sc.add("swell", 28, 4, None, 0.4)
    sc.add("swell", 60, 4, None, 0.4)
    return sc.render(64, rt60=2.6, wet=0.3)


def site_of_rest():
    """Quiet, melancholic resting music: harp, soft strings, distant voices (E minor, 3/4)."""
    sc = Score(66, seed=23)
    prog = ["Em", "C", "G", "D", "Em", "C", "Am", "B", "Am", "Em", "C", "B"]
    for b, ch in enumerate(prog):
        s = b * 3
        n = chord(ch, 3)
        _arp(sc, "harp", s, n, [0, 1, 2, 4, 2, 1], 0.5, 0.33, dur=1.4)
        sc.add("strings", s, 3, [n[0] - 12, n[1], n[2]], 0.09, attack=1.0, release=1.2)
        if b >= 4:
            sc.add("choir", s, 3, [x + 12 for x in n], 0.08, vowel="o")
    mel = _bars(["B4 2 G4 1", "E5 3", "D5 2 B4 1", "A4 3", "G4 1 A4 1 B4 1", "C5 2 E5 1",
                 "E5 1.5 D5 .5 C5 1", "B4 2 D#5 1", "E5 2 C5 1", "B4 3", "C5 1 B4 1 A4 1", "B4 2 F#4 1"], 3)
    sc.melody("flute", 0, mel, 0.28)
    sc.add("bell", 0, 3, "E5", 0.25)
    sc.add("bell", 18, 3, "B4", 0.2)
    return sc.render(36, rt60=3.2, wet=0.42)


def lament():
    """Sad music for a loss: a slow cello-like line over soft strings (A minor)."""
    sc = Score(60, seed=24)
    prog = ["Am", "F", "C", "G", "Am", "F", "E", "E"]
    for b, ch in enumerate(prog):
        s = b * 4
        n = chord(ch, 3)
        sc.add("strings", s, 4, [n[0] - 12, n[1], n[2], n[0] + 12], 0.1, attack=1.2, release=1.5)
        _arp(sc, "harp", s, n, [0, 2, 4, 2], 1.0, 0.22, dur=2.0)
    mel = _bars(["E4 2 A4 2", "C5 3 B4 1", "G4 2 E4 2", "D4 2 G4 2", "A4 3 B4 1", "C5 2 A4 2",
                 "G#4 2 B4 2", "E4 4"], 4)
    sc.melody("strings", 0, mel, 0.45, shift=-12, attack=0.35, release=0.8, voices=2, bright=1800, pan=-0.15)
    return sc.render(32, rt60=3.0, wet=0.38)


def dread():
    """Short shock: something terrible has happened."""
    sc = Score(60, seed=25)
    sc.add("boom", 0, 3, None, 1.0)
    sc.add("taiko", 0, 1, None, 0.9)
    sc.add("timpani", 0, 2, "C2", 0.8)
    sc.add("brass", 0, 1.4, ["C3", "Db3", "G3", "C4"], 0.7)
    sc.add("strings", 0.1, 4.5, ["C2", "C3", "Db3"], 0.35, attack=0.05, release=1.5, tremolo=0.9)
    sc.add("choir", 0.6, 4.0, ["C4", "Db4", "Gb4"], 0.35, vowel="a")
    sc.add("bell", 0, 3, "C4", 0.3)
    return sc.render(6, loop=False, rt60=3.0, wet=0.38)


def enemy_felled():
    """Golden swell after a big enemy falls: choir, strings and bells rise and glow."""
    sc = Score(60, seed=26)
    sc.add("swell", 0, 1.2, None, 0.3)
    sc.add("choir", 0.8, 3.5, ["D4", "F#4", "A4", "D5"], 0.38, vowel="a")
    sc.add("strings", 0.8, 3.5, ["D3", "A3", "F#4", "D5"], 0.25, attack=0.4, release=1.5)
    sc.add("brass", 1.0, 2.5, ["D3", "A3", "D4"], 0.35)
    sc.add("timpani", 0.8, 2, "D2", 0.55)
    sc.add("bell", 1.2, 3, "A5", 0.3)
    sc.add("bell", 1.6, 3, "D6", 0.25)
    return sc.render(6, loop=False, rt60=3.0, wet=0.4)


# ====================================================================== catalogue
#  name: (label, group, function)  -  names starting with "music_" loop on the timeline
G_MED = "Music: medieval quest (RuneScape-like)"
G_DARK = "Music: dark fantasy (Elden Ring-like)"
THEMES = {
    "music_quest_giver": ("Quest giver: warm village tune (loop)", G_MED, quest_giver),
    "jingle_quest_accepted": ("Quest accepted (short jingle)", G_MED, quest_accepted),
    "music_setting_off": ("Setting off on the quest (loop)", G_MED, setting_off),
    "music_tavern": ("Tavern jig (loop)", G_MED, tavern),
    "music_sneaking": ("Sneaking (loop)", G_MED, sneaking),
    "music_medieval_battle": ("Battle: drums and horns (loop)", G_MED, medieval_battle),
    "jingle_quest_complete_epic": ("Quest complete: big fanfare", G_MED, quest_complete_fanfare),
    "music_monster_steals": ("Monster steals the treasure: danger (loop)", G_DARK, monster_steals),
    "sting_dread": ("Dread: something terrible happens (short)", G_DARK, dread),
    "music_dark_boss": ("Dark boss: choir and war drums (loop)", G_DARK, dark_boss),
    "sting_enemy_felled": ("Enemy felled: golden swell (short)", G_DARK, enemy_felled),
    "music_site_of_rest": ("Resting place: calm and sad (loop)", G_DARK, site_of_rest),
    "music_lament": ("Lament: loss and sorrow (loop)", G_DARK, lament),
}
