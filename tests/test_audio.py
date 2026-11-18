"""Built-in sounds and sync-by-sound."""
import numpy as np
import pytest

from questcut import audio


@pytest.mark.parametrize("name", sorted(audio.GAME_SOUNDS))
def test_game_sound_is_clean(name):
    x = audio.GAME_SOUNDS[name][2]()
    assert x.ndim in (1, 2) and len(x) > audio.SR * 0.03
    if x.ndim == 2:
        assert x.shape[1] == 2
    assert np.isfinite(x).all() and np.abs(x).max() <= 1.0


def test_sync_finds_the_offset_between_two_cameras():
    rng = np.random.default_rng(0)
    sr = audio.SR
    n = sr * 12
    room = rng.normal(0, 0.01, n)
    for t in (1.0, 2.5, 4.2, 6.0, 8.8, 10.1):        # claps and footsteps
        i = int(t * sr)
        room[i:i + 2000] += rng.normal(0, 0.6, 2000) * np.exp(-np.arange(2000) / 300)
    lag = 1.7
    a = (room * 32767 * 0.5).astype(np.int16)[:, None]
    b = (np.concatenate([room[int(lag * sr):], np.zeros(int(lag * sr))]) * 32767 * 0.4).astype(np.int16)[:, None]
    found, conf = audio.find_offset(a, b, sr)
    assert abs(found - lag) < 0.02 and conf > 0.3


def test_music_loops_join_without_a_jump():
    from questcut.music_themes import THEMES
    for name, (_label, _group, fn) in THEMES.items():
        if not name.startswith("music_"):
            continue
        x = fn()
        typical = np.abs(np.diff(x, axis=0)).max(axis=1)
        # the step from the last sample back to the first is no bigger than the loudest normal step
        assert np.abs(x[0] - x[-1]).max() <= typical.max() + 1e-6, name


def test_melodies_have_whole_bars():
    import pytest as _pt
    from questcut.music_themes import _bars
    assert _bars(["A4 1 B4 2", "C5 3"], 3)
    with _pt.raises(ValueError):
        _bars(["A4 1 B4 1"], 3)
