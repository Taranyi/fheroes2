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

"""Fixed numeric, omniscient observation schema for the Gym v0 profile."""

import numpy as np
from gymnasium import spaces

from .gym_candidates import ACTION_NAMES, BATTLE_KINDS, CHOICE_KINDS, ProfileLimitError

PHASES = ("adventure", "choice", "battle", "terminal")
RESOURCES = ("wood", "mercury", "ore", "sulfur", "crystal", "gems", "gold")
ACTION_FIELDS = ("type", "hero_id", "other_hero_id", "castle_id", "x", "y", "building_id", "dwelling_id", "count",
                 "resource_from", "resource_to", "lots", "spell_id", "choice_id", "value", "action_id", "source_kind",
                 "source_id", "source_slot", "target_kind", "target_id", "target_slot", "battle_kind", "unit_uid",
                 "target_uid", "destination", "target_cell", "attack_direction", "spell_points", "gold")
HERO_FIELDS = ("id", "owner", "active", "race", "level", "experience", "attack", "defense", "power", "knowledge",
               "spell_points", "max_spell_points", "move_points", "scouting_distance", "has_spell_book", "can_dismiss",
               "dismissal_prohibited", "can_buy_spell_book", "castle_id", "is_shipmaster")
UNIT_FIELDS = ("uid", "monster_id", "count", "alive", "army_color", "current_color", "head", "tail", "wide", "flying",
               "hit_points", "shots", "speed", "attack", "defense", "modes")
CHOICE_VALUES = ("gold", "experience", "monster_id", "count", "available", "gold_per_unit", "primary_skill", "first_level", "second_level")


def observation_space(map_size, heroes, castles, units, actions):
    shapes = {"global": (12,), "tiles": (map_size * map_size, 16), "tile_mask": (map_size * map_size,),
              "players": (6, 13), "player_mask": (6,), "heroes": (heroes, len(HERO_FIELDS) + 2), "hero_mask": (heroes,),
              "hero_armies": (heroes, 5, 2), "hero_artifacts": (heroes, 14, 2), "hero_skills": (heroes, 8, 2),
              "hero_spells": (heroes, 128), "castles": (castles, 7), "castle_mask": (castles,),
              "castle_buildings": (castles, 32), "castle_armies": (castles, 5, 2), "castle_dwellings": (castles, 6, 2),
              "battle": (9,), "battle_units": (units, len(UNIT_FIELDS)), "battle_unit_mask": (units,),
              "battle_effects": (units, 32), "battle_board": (99, 3), "battle_commanders": (2, 3),
              "choice": (6,), "choice_values": (len(CHOICE_VALUES),), "choice_value_mask": (len(CHOICE_VALUES),), "actions": (actions, len(ACTION_FIELDS))}
    result = {key: spaces.Box(np.iinfo(np.int64).min, np.iinfo(np.int64).max, shape=shape, dtype=np.int64) for key, shape in shapes.items()}
    result["action_mask"] = spaces.MultiBinary(actions)
    return spaces.Dict(result)


def require(condition, message):
    if not condition:
        raise ProfileLimitError(message)


def fill_army(out, army):
    require(len(army) <= len(out), "Army slot limit exceeded")
    for i, troop in enumerate(army):
        if troop is not None:
            out[i] = (troop["monster_id"], troop["count"])


def encode(space, state, decision, commands, step, max_steps):
    out = {key: np.zeros(value.shape, dtype=value.dtype) for key, value in space.spaces.items()}
    phase = PHASES.index(decision["phase"])
    m, date = state["map"], state["date"]
    out["global"][:] = (phase, decision["player_id"], state["current_player"], m["width"], m["height"], m["seed"],
                          date["total_days"], date["total_weeks"], date["month"], state["game_result"], step, max_steps - step)
    size = int(np.sqrt(len(out["tiles"])))
    require(m["width"] <= size and m["height"] <= size and len(m["tiles"]) <= len(out["tiles"]), "Map dimensions exceed max_map_size")
    for i, tile in enumerate(m["tiles"]):
        require(len(tile["metadata"]) == 3, "Unknown tile metadata schema")
        out["tiles"][i] = tuple(tile[k] for k in ("index", "x", "y", "terrain", "terrain_image", "terrain_flags", "water", "road",
                                                    "object_type", "object_under_hero", "fog_colors", "passability")) + tuple(tile["metadata"]) + (tile["main_part"]["uid"],)
        out["tile_mask"][i] = 1
    require(len(state["players"]) <= 6, "Player count exceeds six")
    for i, p in enumerate(sorted(state["players"], key=lambda p: p["id"])):
        out["players"][i] = (p["id"], p["control"], p["in_play"], p["race"], p["friends"], p["lost_town_days"], *(p["funds"][r] for r in RESOURCES))
        out["player_mask"][i] = 1
    require(len(state["heroes"]) <= len(out["heroes"]), "Hero count exceeds max_heroes")
    for i, h in enumerate(sorted(state["heroes"], key=lambda h: h["id"])):
        out["heroes"][i, :len(HERO_FIELDS)] = [h.get(k) if h.get(k) is not None else -1 for k in HERO_FIELDS]
        out["heroes"][i, -2:] = (-1, -1) if h["position"] is None else (h["position"]["x"], h["position"]["y"])
        out["hero_mask"][i] = 1
        fill_army(out["hero_armies"][i], h["army"])
        require(len(h["artifacts"]) <= 14 and len(h["secondary_skills"]) <= 8, "Hero inventory/skill limit exceeded")
        for j, artifact in enumerate(h["artifacts"]):
            if artifact is not None:
                out["hero_artifacts"][i, j] = (artifact["id"], artifact["spell_id"])
        for j, skill in enumerate(h["secondary_skills"]):
            out["hero_skills"][i, j] = (skill["id"], skill["level"])
        for spell in h["spells"]:
            require(0 <= spell < 128, "Spell ID exceeds observation catalog")
            out["hero_spells"][i, spell] = 1
    require(len(state["castles"]) <= len(out["castles"]), "Castle count exceeds max_castles")
    for i, c in enumerate(sorted(state["castles"], key=lambda c: c["id"])):
        out["castle_mask"][i] = 1
        out["castles"][i] = (c["id"], c["owner"], c["race"], c["is_castle"], c["position"]["x"], c["position"]["y"], c["visiting_hero_id"] if c["visiting_hero_id"] is not None else -1)
        for building in c["buildings"]:
            bit = int(building).bit_length() - 1
            require(0 <= bit < 32 and building == 1 << bit, "Unknown building bit")
            out["castle_buildings"][i, bit] = 1
        fill_army(out["castle_armies"][i], c["garrison"])
        require(len(c["dwellings"]) <= 6, "Dwelling count exceeds six")
        for j, dwelling in enumerate(c["dwellings"]):
            out["castle_dwellings"][i, j] = (dwelling["building_id"], dwelling["count"])
    battle = decision["battle"]
    if battle is not None:
        out["battle"][:] = tuple(battle[k] for k in ("map_index", "width", "height", "round", "current_unit_uid", "current_color", "attacker_color", "defender_color", "siege"))
        require(len(battle["units"]) <= len(out["battle_units"]) and len(battle["board"]) == 99, "Battle unit/board limit exceeded")
        for i, unit in enumerate(battle["units"]):
            out["battle_unit_mask"][i] = 1
            out["battle_units"][i] = tuple(unit[k] for k in UNIT_FIELDS)
            for effect in unit["effects"]:
                bit = int(effect["mode"]).bit_length() - 1
                require(0 <= bit < 32 and effect["mode"] == 1 << bit, "Unknown battle effect")
                out["battle_effects"][i, bit] = effect["rounds"]
        for i, cell in enumerate(battle["board"]):
            out["battle_board"][i] = (cell["index"], cell["object"], cell["unit_uid"] if cell["unit_uid"] is not None else -1)
        for i, key in enumerate(("attacker_commander", "defender_commander")):
            h = battle[key]
            if h is not None:
                out["battle_commanders"][i] = (h["color"], h["spell_points"], h["spell_cast_this_round"])
    choice = decision["pending_choice"]
    if choice is not None and battle is None:
        require(choice["kind"] in CHOICE_KINDS, "Unknown choice kind")
        out["choice"][:] = (CHOICE_KINDS.index(choice["kind"]) + 1, choice["choice_id"], choice["hero_id"], choice.get("minimum", 0), choice.get("maximum", 0), len(commands))
        require(not set(choice["values"]) - set(CHOICE_VALUES), "Unknown choice value field")
        for i, field in enumerate(CHOICE_VALUES):
            if field in choice["values"]:
                out["choice_values"][i] = choice["values"][field]
                out["choice_value_mask"][i] = 1
    require(len(commands) <= len(out["actions"]), "Action count exceeds max_actions")
    for i, cmd in enumerate(commands):
        values = dict(cmd["params"], type=ACTION_NAMES.index(cmd["action"]) + 1)
        if cmd["action"] == "battle.act":
            details = battle["actions"][cmd["params"]["action_id"]]
            require(details["kind"] in BATTLE_KINDS, "Unknown battle command kind")
            values.update(details, battle_kind=BATTLE_KINDS.index(details["kind"]) + 1)
        for side in ("source", "target"):
            endpoint = values.get(side)
            if endpoint is not None:
                values[side + "_kind"] = 1 if endpoint.get("kind", "hero") == "hero" else 2
                values[side + "_id"] = endpoint.get("id", endpoint.get("hero_id"))
                values[side + "_slot"] = endpoint["slot"]
        out["actions"][i] = [values.get(field, 0) for field in ACTION_FIELDS]
        out["action_mask"][i] = 1
    return out
