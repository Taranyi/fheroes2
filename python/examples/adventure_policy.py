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

"""Deterministic omniscient expedition policy for API acceptance, not a trained agent."""

from collections import Counter, deque
import math


def battle_action(battle):
    actions = battle['actions']
    for spell in (3, 26):
        options = [a for a in actions if a['kind'] == 'spell' and a.get('spell_id') == spell]
        if options:
            return options[0]['action_id']
    for kind in ('shoot', 'attack'):
        options = [a for a in actions if a['kind'] == kind]
        if options:
            return options[0]['action_id']
    enemies = [u for u in battle['units'] if u['alive'] and u['current_color'] != battle['current_color']]
    moves = [a for a in actions if a['kind'] == 'move']
    def xy(cell):
        row, col = divmod(cell, battle['width'])
        return col - .5 * (row % 2), row * math.sqrt(3) / 2
    def distance(action):
        x, y = xy(action['destination'])
        return min((x - xy(u['head'])[0]) ** 2 + (y - xy(u['head'])[1]) ** 2 for u in enemies)
    if moves and enemies:
        return min(moves, key=distance)['action_id']
    return next(a['action_id'] for a in actions if a['kind'] == 'skip')


class ExpeditionPolicy:
    """Build/recruit, transfer a castle garrison, then seek hostile/neutral castles.

    Approximate terrain routing only chooses among native-validated Gym actions.
    It neither edits the world nor delegates Python turns to native AI. Losing is
    a valid acceptance outcome; this is deliberately not an expert strategy.
    """
    def __init__(self):
        self.visits = Counter()
        self.refreshed = set()

    @staticmethod
    def distances(state, targets, water):
        width, height = state['map']['width'], state['map']['height']
        tiles = state['map']['tiles']
        distance = {i: 0 for i in targets}
        queue = deque(targets)
        directions = ((-1, -1, 1, 16), (0, -1, 2, 32), (1, -1, 4, 64), (1, 0, 8, 128),
                      (1, 1, 16, 1), (0, 1, 32, 2), (-1, 1, 64, 4), (-1, 0, 128, 8))
        while queue:
            index = queue.popleft()
            tile = tiles[index]
            x, y = index % width, index // width
            for dx, dy, outward, inward in directions:
                nx, ny = x + dx, y + dy
                neighbor = ny * width + nx
                if not (0 <= nx < width and 0 <= ny < height) or neighbor in distance:
                    continue
                other = tiles[neighbor]
                if other['water'] != water or not other['passability']:
                    continue
                if not (tile['passability'] & outward and other['passability'] & inward):
                    continue
                distance[neighbor] = distance[index] + 1
                queue.append(neighbor)
        return distance

    def choose(self, obs, info):
        commands, state, player = info['actions'], info['state'], info['player_id']
        if info['phase'] == 'battle':
            aid = battle_action(state['battle'])
            return next(i for i, c in enumerate(commands) if c['params']['action_id'] == aid)
        if info['phase'] == 'choice':
            return 0  # exact first offered native answer, including bounded text vocabulary
        assert info['phase'] == 'adventure'
        if state['army_meeting'] is not None:
            return next(i for i, c in enumerate(commands) if c['action'] == 'hero.end_meeting')
        day = state['date']['total_days']
        heroes = {h['id']: h for h in state['heroes'] if h['active'] and h['owner'] == player}
        own = [c for c in state['castles'] if c['owner'] == player]
        friends = next(p['friends'] for p in state['players'] if p['id'] == player)
        targets = [c['id'] for c in state['castles'] if c['owner'] == 0 or not (c['owner'] & friends)]
        transfers = [(i, c['params']['count']) for i, c in enumerate(commands) if c['action'] == 'army.transfer'
                     and c['params']['source']['kind'] == 'castle' and c['params']['target']['kind'] == 'hero']
        if transfers:
            return max(transfers, key=lambda pair: pair[1])[0]
        recruits = [(i, c['params']['count']) for i, c in enumerate(commands) if c['action'] == 'castle.recruit']
        if recruits:
            return max(recruits, key=lambda pair: pair[1])[0]
        # One native construction per castle/day; prioritize productive dwellings.
        buildings = [(i, c['params']['building_id']) for i, c in enumerate(commands) if c['action'] == 'castle.build'
                     and c['params']['building_id'] >= 1 << 20]
        if buildings:
            return min(buildings, key=lambda pair: pair[1])[0]
        if not heroes:
            hires = [i for i, c in enumerate(commands) if c['action'] == 'castle.hire']
            if hires:
                return hires[0]
            refreshes = [(i, c['params']['castle_id']) for i, c in enumerate(commands) if c['action'] == 'castle.refresh_heroes'
                         and (day, c['params']['castle_id']) not in self.refreshed]
            if refreshes:
                i, cid = refreshes[0]
                self.refreshed.add((day, cid))
                return i
        moves = [(i, c) for i, c in enumerate(commands) if c['action'] == 'hero.move']
        # Rest/recruit for the first week; then actively explore and attack.
        if (day >= 6 or not own) and moves:
            fields = {water: self.distances(state, targets, water) for water in {h['is_shipmaster'] for h in heroes.values()}}
            def score(item):
                _, c = item
                params = c['params']
                h = heroes[params['hero_id']]
                index = params['y'] * state['map']['width'] + params['x']
                distance = fields[h['is_shipmaster']].get(index)
                if distance is None:
                    distance = min((max(abs(params['x'] - t % state['map']['width']),
                                        abs(params['y'] - t // state['map']['width'])) for t in targets), default=0) + 1000
                return distance + self.visits[(h['id'], index)] * 2, -h['move_points'], h['id'], index
            i, c = min(moves, key=score)
            p = c['params']
            self.visits[(p['hero_id'], p['y'] * state['map']['width'] + p['x'])] += 1
            return i
        return next(i for i, c in enumerate(commands) if c['action'] == 'turn.end')
