"""Projects: saving, combining, spell/hitsplat links, the one-click fight and quest plans."""
import os

from questcut.hud import SpellLinks, hud_defaults
from questcut.model import Clip, Media, Project, append_project, new_id
from questcut.rs_combos import plan_fight, plan_quest_talk


def hud(htype, start, dur, **props):
    pr = hud_defaults(htype)
    pr.update(props)
    return Clip(new_id("c"), "hud", start, dur, htype, hud_type=htype, props=pr)


def test_save_and_load_roundtrip(tmp_path):
    p = Project.new_default()
    c = hud("rs_hpbar", 1.0, 5.0, bar_key="b1")
    c.add_keyframe("value", 1.0, 50.0)
    [t for t in p.tracks if t.kind == "hud"][0].clips.append(c)
    path = os.path.join(tmp_path, "scene.questcut")
    p.save(path)
    q = Project.load(path)
    c2 = q.clip(c.id)
    assert c2 is not None and c2.props["bar_key"] == "b1" and c2.keyframes == c.keyframes


def test_combine_remaps_extra_pictures(tmp_path):
    a, b = Project.new_default(), Project.new_default()
    pic = os.path.join(tmp_path, "after.png")
    open(pic, "wb").close()
    m = Media(new_id("m"), pic, "image", "after.png")
    b.media[m.id] = m
    ev = hud("pk_evolve", 0, 11, media2=m.id)
    [t for t in b.tracks if t.kind == "hud"][0].clips.append(ev)
    append_project(a, b, 30.0)
    placed = [c for c in a.all_clips() if c.hud_type == "pk_evolve"][0]
    assert placed.start == 30.0
    assert placed.props["media2"] in a.media


def test_hitsplats_lower_their_bar():
    p = Project.new_default()
    h1, h2 = [t for t in p.tracks if t.kind == "hud"][:2]
    bar = hud("rs_hpbar", 0, 10, value=40.0, max_value=40.0, bar_key="enemy")
    h1.clips = [bar]
    h2.clips = [hud("rs_hitsplat", 2, 1.2, text="12", target_bar="enemy"),
                hud("rs_hitsplat", 4, 1.2, text="5", kind="heal", target_bar="enemy")]
    links = SpellLinks(p)
    assert links.damage("enemy", 1.0) == 0
    assert abs(links.damage("enemy", 3.0) - 12) < 1e-6
    assert abs(links.damage("enemy", 5.0) - 7) < 1e-6          # healed 5


def test_fight_plan_enemy_loses_player_survives():
    for seed in range(30):
        plan, st = plan_fight({"player": "A", "enemy": "B", "player_hp": 30, "enemy_hp": 50, "player_max": 9,
                               "enemy_max": 12}, seed=seed)
        hits = {"enemy_bar": 0, "player_bar": 0}
        for item in plan:
            if item[0] == "hud" and item[1] == "rs_hitsplat":
                hits[item[4]["target_bar"][1:]] += int(item[4]["text"])
        assert hits["enemy_bar"] == 50
        assert hits["player_bar"] < 30 and st["player_left"] > 0


def test_quest_talk_plan_is_in_order():
    plan, length = plan_quest_talk({"npc": "Prof", "player": "Me", "npc_lines": "Hello!\nHelp me?",
                                    "options": "Yes\nNo", "pick": 1, "quest": "Q", "music": True})
    huds = [x for x in plan if x[0] == "hud"]
    assert [h[1] for h in huds] == ["rs_dialogue", "rs_dialogue", "rs_options", "rs_dialogue", "rs_gamemsg"]
    assert huds[3][4]["text"] == "No"
    starts = [h[2] for h in huds]
    assert starts == sorted(starts) and length > starts[-1]
