###########################################################################
#   fheroes2: https://github.com/ihhub/fheroes2                           #
#   Copyright (C) 2026                                                    #
#                                                                         #
#   This program is free software; you can redistribute it and/or modify  #
#   it under the terms of the GNU General Public License as published by  #
#   the Free Software Foundation; either version 2 of the License, or     #
#   (at your option) any later version.                                   #
#                                                                         #
#   This program is distributed in the hope that it will be useful,       #
#   but WITHOUT ANY WARRANTY; without even the implied warranty of        #
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         #
#   GNU General Public License for more details.                          #
#                                                                         #
#   You should have received a copy of the GNU General Public License     #
#   along with this program; if not, write to the                         #
#   Free Software Foundation, Inc.,                                       #
#   59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.             #
###########################################################################

"""Enumerate the discrete Gym command profile; native code validates game rules."""

from itertools import combinations

from .session import EngineError

ACTION_NAMES = ("turn.end", "hero.move", "castle.build", "castle.recruit", "castle.refresh_heroes", "castle.hire",
                "market.trade", "hero.meet", "army.transfer", "army.swap", "artifact.transfer", "artifact.swap",
                "hero.end_meeting", "army.upgrade", "army.dismiss", "hero.dismiss", "hero.buy_spell_book", "hero.cast",
                "choice.answer", "battle.act", "castle.buy_boat")
BATTLE_KINDS = ("skip", "move", "attack", "shoot", "spell", "retreat", "surrender")
CHOICE_KINDS = ("treasure.gold_or_experience", "hero.secondary_skill", "monster.join", "monster.pursue", "confirmation", "army.recruit_count", "hero.primary_skill", "spell.town_portal", "spell.dimension_door")
DIRECTIONS = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))


class ProfileLimitError(EngineError):
    """A state cannot be represented losslessly by the configured fixed Gym profile."""

    def __init__(self, message):
        super().__init__("gym_profile_limit", message)


def command(action, **params):
    return {"action": action, "params": params}


def quantities(limit, capacity):
    if limit > capacity:
        raise ProfileLimitError(f"Quantity range {limit} exceeds action capacity {capacity}; increase max_actions")
    return range(1, limit + 1)


def adventure_proposals(game, state, decision, capacity):
    player = decision["player_id"]
    heroes = sorted((h for h in state["heroes"] if h["active"] and h["owner"] == player), key=lambda h: h["id"])
    castles = sorted((c for c in state["castles"] if c["owner"] == player), key=lambda c: c["id"])
    meeting = decision["army_meeting"]
    meeting_ids = set() if meeting is None else {meeting["hero_id"], meeting["other_hero_id"]}
    yield command("turn.end")
    if meeting is not None:
        yield command("hero.end_meeting")
    for hero in heroes:
        for dx, dy in DIRECTIONS:
            x, y = hero["position"]["x"] + dx, hero["position"]["y"] + dy
            if 0 <= x < state["map"]["width"] and 0 <= y < state["map"]["height"]:
                yield command("hero.move", hero_id=hero["id"], x=x, y=y)
        yield command("hero.dismiss", hero_id=hero["id"])
        yield command("hero.buy_spell_book", hero_id=hero["id"])
        for spell in hero["adventure_spell_options"]:
            yield command("hero.cast", hero_id=hero["id"], spell_id=spell["spell_id"])
        for other in heroes:
            if hero["id"] != other["id"] and max(abs(hero["position"][k] - other["position"][k]) for k in ("x", "y")) <= 1:
                yield command("hero.meet", hero_id=hero["id"], other_hero_id=other["id"])
    for castle in castles:
        cid = castle["id"]
        options = game.get_castle_options(cid)
        if options["boat"]["can_buy"]:
            yield command("castle.buy_boat", castle_id=cid)
        for building in options["buildings"]:
            if building["can_build"]:
                yield command("castle.build", castle_id=cid, building_id=building["building_id"])
        for dwelling in options["dwellings"]:
            for count in quantities(dwelling["max_recruitable"], capacity):
                yield command("castle.recruit", castle_id=cid, dwelling_id=dwelling["dwelling_id"], count=count)
        yield command("castle.refresh_heroes", castle_id=cid)
        if options["hero_hiring"]["can_hire"]:
            for offer in options["hero_hiring"]["offers"]:
                if offer["available"]:
                    yield command("castle.hire", castle_id=cid, hero_id=offer["hero_id"])
        for trade in options["market"]["trades"]:
            for lots in quantities(trade["max_lots"], capacity):
                yield command("market.trade", castle_id=cid, resource_from=trade["resource_from"], resource_to=trade["resource_to"], lots=lots)
    entities = [("hero", h["id"], h["army"], h["castle_id"]) for h in heroes]
    entities += [("castle", c["id"], c["garrison"], None) for c in castles]
    endpoints = []
    for kind, eid, army, castle_id in entities:
        options = game.get_army_options(kind, eid)
        for slot, troop in enumerate(army):
            endpoint = {"kind": kind, "id": eid, "slot": slot}
            endpoints.append((endpoint, troop, castle_id))
            if options["slots"][slot]["can_upgrade"]:
                yield command("army.upgrade", source=endpoint)
            if options["slots"][slot]["can_dismiss"]:
                yield command("army.dismiss", source=endpoint)
    def accessible(a, b):
        ea, _, ca = a
        eb, _, cb = b
        if (ea["kind"], ea["id"]) == (eb["kind"], eb["id"]):
            return True
        if ea["kind"] == eb["kind"] == "hero":
            return {ea["id"], eb["id"]} == meeting_ids
        return (ea["kind"] == "hero" and ca == eb["id"]) or (eb["kind"] == "hero" and cb == ea["id"])
    for a, b in combinations(endpoints, 2):
        if not accessible(a, b):
            continue
        if a[1] is not None or b[1] is not None:
            yield command("army.swap", source=a[0], target=b[0])
        for source, target in ((a, b), (b, a)):
            troop, other = source[1], target[1]
            if troop is None or (other is not None and other["monster_id"] != troop["monster_id"]):
                continue
            limit = min(troop["count"], 0xFFFFFFFF - (0 if other is None else other["count"]))
            for count in quantities(limit, capacity):
                yield command("army.transfer", source=source[0], target=target[0], count=count)
    artifacts = [({"hero_id": h["id"], "slot": slot}, artifact) for h in heroes for slot, artifact in enumerate(h["artifacts"])]
    for (a, va), (b, vb) in combinations(artifacts, 2):
        if a["hero_id"] != b["hero_id"] and {a["hero_id"], b["hero_id"]} != meeting_ids:
            continue
        if va is not None and vb is not None:
            yield command("artifact.swap", source=a, target=b)
        elif va is not None:
            yield command("artifact.transfer", source=a, target=b)
        elif vb is not None:
            yield command("artifact.transfer", source=b, target=a)


def candidates(game, state, decision, capacity):
    phase = decision["phase"]
    if phase == "terminal":
        return []
    if phase == "battle":
        actions = decision["battle"]["actions"]
        if len(actions) > capacity:
            raise ProfileLimitError("Battle action count exceeds max_actions")
        return [command("battle.act", action_id=a["action_id"]) for a in actions]
    if phase == "choice":
        choice = decision["pending_choice"]
        if choice["kind"] not in CHOICE_KINDS:
            raise ProfileLimitError("Unknown native choice kind")
        values = choice["options"]
        if not values:
            if choice["maximum"] - choice["minimum"] + 1 > capacity:
                raise ProfileLimitError("Choice range exceeds max_actions")
            values = range(choice["minimum"], choice["maximum"] + 1)
        if len(values) > capacity:
            raise ProfileLimitError("Choice count exceeds max_actions")
        return [command("choice.answer", choice_id=choice["choice_id"], value=value) for value in values]
    if phase != "adventure":
        raise ProfileLimitError(f"Unsupported decision phase: {phase}")
    result, batch, checked = [], [], 0
    def flush():
        nonlocal checked
        checked += len(batch)
        if checked > 262144:
            raise ProfileLimitError("More than 262144 candidate checks in one decision")
        valid = game.check_actions(batch, token=decision["token"])
        result.extend(action for action, accepted in zip(batch, valid) if accepted)
        batch.clear()
        if len(result) > capacity:
            raise ProfileLimitError("Legal command count exceeds max_actions; no actions were dropped")
    for proposal in adventure_proposals(game, state, decision, capacity):
        batch.append(proposal)
        if len(batch) == 128:
            flush()
    if batch:
        flush()
    return result
