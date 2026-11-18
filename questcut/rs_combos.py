"""RuneScape-style one-click sequences: a quest conversation and a fight.

Each plan_* function returns a list of things to place:
    ("hud", hud_type, start, duration, props, tag)   or   ("sound", name, start, loop_seconds_or_None)
The main window turns them into clips. Times are relative to the playhead."""
from __future__ import annotations

import random


def read_time(text, cps=15.0, least=2.6):
    """How long a box should stay up so people can read it."""
    return max(least, round(len(text) / cps + 1.2, 1))


def plan_quest_talk(v):
    """NPC lines -> reply list (one gets picked) -> your reply -> 'quest started' message."""
    out, t = [], 0.0
    npc_lines = [ln.strip() for ln in v["npc_lines"].splitlines() if ln.strip()]
    for ln in npc_lines:
        d = read_time(ln)
        out.append(("hud", "rs_dialogue", t, d, {"name": v["npc"], "text": ln, "side": "left"}, "npc"))
        out.append(("sound", "text_blip", t, None))
        t += d
    opts = [o.strip() for o in v["options"].splitlines() if o.strip()][:5]
    if opts:
        pick = max(0, min(len(opts) - 1, int(v.get("pick", 0))))
        d = 3.0
        out.append(("hud", "rs_options", t, d, {"options": "\n".join(opts), "selected": -1.0,
                                                "_keys": {"selected": [[0.0, -1.0, "hold"], [1.6, float(pick), "hold"]]}},
                    "options"))
        out.append(("sound", "menu_select", t + 1.6, None))
        t += d
        reply = opts[pick]
        d = read_time(reply)
        out.append(("hud", "rs_dialogue", t, d, {"name": v["player"], "text": reply, "side": "right"}, "player"))
        t += d
    if v.get("quest"):
        out.append(("hud", "rs_gamemsg", t, 5.0,
                    {"lines": f"[red]You have started a new quest: [blue]{v['quest']}", "interval": 0.0}, "msg"))
        out.append(("sound", "jingle_quest_accepted", t, None))
        t += 5.0
    if v.get("music"):
        out.append(("sound", "music_quest_giver", 0.0, t))
    return out, t


def plan_fight(v, seed=None):
    """Two overhead bars, alternating attacks every `speed` seconds, red and blue splats,
    XP drops for your hits. The opponent always loses; you always survive."""
    rnd = random.Random(seed)
    php, ehp = int(v["player_hp"]), int(v["enemy_hp"])
    pmax, emax = max(1, int(v["player_max"])), max(1, int(v["enemy_max"]))
    speed = float(v.get("speed", 2.4))
    miss = float(v.get("miss_chance", 0.25))
    out = []
    t = 0.8
    p_left, e_left = php, ehp
    xp_total = float(v.get("xp_total", 1_000_000))
    hits = []
    for rnd_i in range(60):
        # you hit
        dmg = 0 if rnd.random() < miss else rnd.randint(1, pmax)
        if rnd_i >= 25:                       # don't let a fight drag on forever
            dmg = max(dmg, e_left)
        dmg = min(dmg, e_left)
        hits.append(("enemy", t, dmg))
        e_left -= dmg
        if e_left <= 0:
            break
        # they hit back, half a beat later (never knocking you out)
        th = t + speed / 2
        dmg = 0 if rnd.random() < miss else rnd.randint(1, emax)
        dmg = max(0, min(dmg, p_left - max(1, php // 10)))
        hits.append(("player", th, dmg))
        p_left -= dmg
        t += speed
    end = hits[-1][1]
    length = end + 2.5
    out.append(("hud", "rs_hpbar", 0.0, length, {"value": float(php), "max_value": float(php), "label": v["player"],
                                                 "x": v.get("px", 0.33), "y": v.get("py", 0.3)}, "player_bar"))
    out.append(("hud", "rs_hpbar", 0.0, end + 1.4, {"value": float(ehp), "max_value": float(ehp), "label": v["enemy"],
                                                    "x": v.get("ex", 0.68), "y": v.get("ey", 0.28)}, "enemy_bar"))
    for who, th, dmg in hits:
        kind = "hit" if dmg else "zero"
        out.append(("hud", "rs_hitsplat", th, 1.2, {"text": str(dmg), "kind": kind,
                                                    "target_bar": "@" + ("enemy_bar" if who == "enemy" else "player_bar"),
                                                    "follow_bar": True, "offset_y": 0.09}, "splat"))
        if who == "enemy":
            out.append(("sound", "hit" if dmg else "whoosh", th, None))
            if dmg and v.get("xp", True):
                out.append(("hud", "rs_xpdrop", th, 2.0, {"amount": float(dmg * 4), "total": xp_total,
                                                          "icon": v.get("icon", "sword")}, "xp"))
                xp_total += dmg * 4
        else:
            out.append(("sound", "damage" if dmg else "whoosh", th, None))
    out.append(("sound", "critical_hit", end + 0.05, None))
    out.append(("hud", "rs_gamemsg", end + 0.8, 4.0,
                {"lines": f"You have defeated [red]{v['enemy']}[black].", "interval": 0.0}, "msg"))
    if v.get("music"):
        out.append(("sound", "music_medieval_battle", 0.0, length))
    stats = {"rounds": sum(1 for h in hits if h[0] == "enemy"), "length": length, "player_left": p_left}
    return out, stats
