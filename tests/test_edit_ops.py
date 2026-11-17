"""Whole-movie edits: insert time, remove time, split, groups."""
import random

from questcut.edit_ops import group_members, insert_time, make_group, remove_time, renew_groups, split_clip
from questcut.model import Clip, Project, new_id


def small_project():
    p = Project.new_default()
    v1 = [t for t in p.tracks if t.kind == "video"][-1]
    hud = [t for t in p.tracks if t.kind == "hud"][-1]
    sfx, music = [t for t in p.tracks if t.kind == "audio"][1:3]
    cam = Clip(new_id("c"), "video", 0, 20, "camA", "m1")
    bar = Clip(new_id("c"), "hud", 2, 15, "bar", hud_type="bar", props={"value": 100.0})
    spell = Clip(new_id("c"), "hud", 12, 2, "spell", hud_type="spell")
    hit = Clip(new_id("c"), "audio", 12.2, 1, "hit", "m2")
    loop = Clip(new_id("c"), "audio", 0, 20, "music", "m3", props={"loop": True})
    v1.clips, hud.clips, sfx.clips, music.clips = [cam], [bar, spell], [hit], [loop]
    return p, cam, bar, spell, hit, loop, v1


def test_insert_time_cuts_camera_and_stretches_hud_and_music():
    p, cam, bar, spell, hit, loop, v1 = small_project()
    insert_time(p, 5.0, 3.0)
    assert [(c.start, c.end, c.source_in) for c in v1.clips] == [(0, 5.0, 0), (8.0, 23.0, 5.0)]
    assert (bar.start, bar.end) == (2, 20.0)          # HUD runs over the new part
    assert (spell.start, hit.start) == (15.0, 15.2)   # later things move together
    assert loop.end == 23.0                           # looping music keeps going


def test_remove_time_is_the_opposite_of_insert():
    p, cam, bar, spell, hit, loop, v1 = small_project()
    before = {c.id: (c.start, c.end) for c in p.all_clips() if c.kind != "video"}
    insert_time(p, 5.0, 3.0)
    remove_time(p, 5.0, 8.0)
    assert {c.id: (c.start, c.end) for c in p.all_clips() if c.kind != "video"} == before
    # the camera stays cut in two, but covers the same time
    assert [(c.start, c.end) for c in v1.clips] == [(0, 5.0), (5.0, 20.0)]


def test_remove_time_drops_what_is_inside_and_trims_edges():
    p, cam, bar, spell, hit, loop, v1 = small_project()
    remove_time(p, 11.0, 13.5)
    assert hit not in p.all_clips()                    # 12.2..13.2 was inside
    assert (spell.start, spell.end) == (11.0, 11.5)    # started inside: trimmed, moved
    assert [(c.start, c.end, c.source_in) for c in v1.clips] == [(0, 11.0, 0), (11.0, 17.5, 13.5)]


def test_locked_tracks_are_left_alone():
    p, cam, bar, spell, hit, loop, v1 = small_project()
    v1.locked = True
    remove_time(p, 5, 8)
    assert (cam.start, cam.end) == (0, 20)


def test_animations_survive_cuts_exactly():
    rnd = random.Random(1)
    for _ in range(150):
        p = Project.new_default()
        hud = [t for t in p.tracks if t.kind == "hud"][-1]
        c = Clip(new_id("c"), "hud", 0, 20, "x", hud_type="bar")
        for _k in range(rnd.randint(1, 5)):
            c.add_keyframe("value", rnd.uniform(0, 20), rnd.uniform(0, 100), rnd.choice(["smooth", "linear", "hold"]))
        hud.clips = [c]
        orig = Clip(**{**c.__dict__, "keyframes": {k: [list(x) for x in v] for k, v in c.keyframes.items()}})
        a = rnd.uniform(1, 15)
        b = a + rnd.uniform(0.2, 4)
        remove_time(p, a, b)
        for i in range(400):
            t = i * 0.05
            if a - 0.01 < t < b + 0.01:
                continue
            tn = t if t < a else t - (b - a)
            assert abs(orig.value("value", t) - c.value("value", tn)) < 0.5


def test_split_keeps_values_on_both_sides():
    p = Project.new_default()
    hud = [t for t in p.tracks if t.kind == "hud"][-1]
    c = Clip(new_id("c"), "hud", 0, 10, "x", hud_type="bar")
    c.add_keyframe("value", 0, 0.0)
    c.add_keyframe("value", 10, 100.0)
    hud.clips = [c]
    ref = {t: c.value("value", t) for t in (1, 3, 6, 9)}
    right = split_clip(hud, c, 4.0)
    assert abs(c.value("value", 3) - ref[3]) < 0.3
    assert abs(right.value("value", 2) - ref[6]) < 0.3


def test_groups_and_pasted_copies_get_new_groups():
    p, cam, bar, spell, hit, loop, v1 = small_project()
    g = make_group([spell, hit])
    assert {c.id for c in group_members(p, g)} == {spell.id, hit.id}
    copies = [Clip(**{**spell.__dict__, "props": dict(spell.props)}), Clip(**{**hit.__dict__, "props": dict(hit.props)})]
    renew_groups(copies)
    assert copies[0].props["group"] == copies[1].props["group"] != g
