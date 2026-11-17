"""Built-in sounds and sync-by-sound."""
import numpy as np
import pytest

from questcut import audio


@pytest.mark.parametrize("name", sorted(audio.GAME_SOUNDS))
def test_game_sound_is_clean(name):
    x = audio.GAME_SOUNDS[name][2]()
    assert x.ndim == 1 and len(x) > audio.SR * 0.03
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
