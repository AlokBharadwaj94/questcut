"""Every HUD element, card and look draws without errors."""
import numpy as np
import pytest

from questcut.cards import CARD_TYPES, card_defaults
from questcut.hud import HUD_TYPES, hud_defaults
from questcut.model import Clip, Project, new_id
from questcut.renderer import Renderer


class NoMedia:
    def image(self, media_id):
        return None

    def frame(self, *a, **k):
        return None

    def close(self):
        pass


def render_one(clip, t, track_kind="hud"):
    p = Project.new_default()
    tr = [t_ for t_ in p.tracks if t_.kind == track_kind][0]
    tr.clips = [clip]
    return Renderer(p, NoMedia()).render(t, 480, 270)


@pytest.mark.parametrize("kind", sorted(HUD_TYPES))
def test_hud_element_draws(kind):
    spec = HUD_TYPES[kind]
    c = Clip(new_id("c"), "hud", 0, spec["duration"], kind, hud_type=kind, props=hud_defaults(kind))
    for t in (0.05, spec["duration"] * 0.5, spec["duration"] * 0.95):
        img = render_one(c, t)
        assert img.shape == (270, 480, 3) and np.isfinite(img).all()


@pytest.mark.parametrize("kind", sorted(CARD_TYPES))
def test_card_draws(kind):
    c = Clip(new_id("c"), "card", 0, CARD_TYPES[kind]["duration"], kind, props=card_defaults(kind))
    img = render_one(c, 1.0, "video")
    assert img.shape == (270, 480, 3) and img.max() > 0


def test_cut_out_finds_a_shape_on_plain_background():
    from questcut.creature import cut_out_mask
    img = np.full((200, 160, 4), 255, np.uint8)
    img[..., :3] = (70, 140, 230)                     # blue background
    yy, xx = np.mgrid[:200, :160]
    person = ((xx - 80) ** 2 / 40 ** 2 + (yy - 110) ** 2 / 70 ** 2) < 1
    img[person, :3] = (230, 180, 150)
    mask = cut_out_mask(img)
    inside, outside = mask[person].mean(), mask[~person].mean()
    assert inside > 0.8 and outside < 0.2
