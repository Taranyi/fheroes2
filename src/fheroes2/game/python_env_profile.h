/***************************************************************************
 *   fheroes2: https://github.com/ihhub/fheroes2                           *
 *   Copyright (C) 2026                                                    *
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 *   This program is distributed in the hope that it will be useful,       *
 *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
 *   GNU General Public License for more details.                          *
 *                                                                         *
 *   You should have received a copy of the GNU General Public License     *
 *   along with this program; if not, write to the                         *
 *   Free Software Foundation, Inc.,                                       *
 *   59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.             *
 ***************************************************************************/

#pragma once

#include <algorithm>
#include <vector>

#include "mp2.h"
#include "spell.h"

namespace fheroes2
{
    // One catalog for validation, capability discovery and the native action entry points.
    inline const std::vector<MP2::MapObjectType> & pythonEnvAdventureObjects()
    {
        static const std::vector<MP2::MapObjectType> objects = {
            MP2::OBJ_RESOURCE,
            MP2::OBJ_TREASURE_CHEST,
            MP2::OBJ_MONSTER,
            MP2::OBJ_GENIE_LAMP,
            MP2::OBJ_WAGON_CAMP,
            MP2::OBJ_WINDMILL,
            MP2::OBJ_WATER_WHEEL,
            MP2::OBJ_MAGIC_GARDEN,
            MP2::OBJ_LEAN_TO,
            MP2::OBJ_WAGON,
            MP2::OBJ_SKELETON,
            MP2::OBJ_BARREL,
            MP2::OBJ_BOTTLE,
            MP2::OBJ_CAMPFIRE,
            MP2::OBJ_SEA_CHEST,
            MP2::OBJ_FLOTSAM,
            MP2::OBJ_SHIPWRECK_SURVIVOR,
            MP2::OBJ_ARTIFACT,
            MP2::OBJ_SHRINE_FIRST_CIRCLE,
            MP2::OBJ_SHRINE_SECOND_CIRCLE,
            MP2::OBJ_SHRINE_THIRD_CIRCLE,
            MP2::OBJ_WITCHS_HUT,
            MP2::OBJ_FOUNTAIN,
            MP2::OBJ_FAERIE_RING,
            MP2::OBJ_IDOL,
            MP2::OBJ_MAGIC_WELL,
            MP2::OBJ_FORT,
            MP2::OBJ_MERCENARY_CAMP,
            MP2::OBJ_WITCH_DOCTORS_HUT,
            MP2::OBJ_STANDING_STONES,
            MP2::OBJ_OASIS,
            MP2::OBJ_TEMPLE,
            MP2::OBJ_WATERING_HOLE,
            MP2::OBJ_BUOY,
            MP2::OBJ_GAZEBO,
            MP2::OBJ_ARTESIAN_SPRING,
            MP2::OBJ_XANADU,
            MP2::OBJ_HILL_FORT,
            MP2::OBJ_FREEMANS_FOUNDRY,
            MP2::OBJ_STABLES,
            MP2::OBJ_TREE_OF_KNOWLEDGE,
            MP2::OBJ_OBSERVATION_TOWER,
            MP2::OBJ_OBELISK,
            MP2::OBJ_ARENA,
            MP2::OBJ_SIRENS,
            MP2::OBJ_MERMAID,
            MP2::OBJ_BLACK_CAT,
            MP2::OBJ_ALCHEMIST_TOWER,
            MP2::OBJ_TRAVELLER_TENT,
            MP2::OBJ_BARRIER,
            MP2::OBJ_ALCHEMIST_LAB,
            MP2::OBJ_MINE,
            MP2::OBJ_SAWMILL,
            MP2::OBJ_LIGHTHOUSE,
            MP2::OBJ_ABANDONED_MINE,
            MP2::OBJ_WATCH_TOWER,
            MP2::OBJ_EXCAVATION,
            MP2::OBJ_CAVE,
            MP2::OBJ_TREE_HOUSE,
            MP2::OBJ_ARCHER_HOUSE,
            MP2::OBJ_GOBLIN_HUT,
            MP2::OBJ_DWARF_COTTAGE,
            MP2::OBJ_HALFLING_HOLE,
            MP2::OBJ_PEASANT_HUT,
            MP2::OBJ_RUINS,
            MP2::OBJ_TREE_CITY,
            MP2::OBJ_DESERT_TENT,
            MP2::OBJ_DRAGON_CITY,
            MP2::OBJ_CITY_OF_DEAD,
            MP2::OBJ_TROLL_BRIDGE,
            MP2::OBJ_WATER_ALTAR,
            MP2::OBJ_AIR_ALTAR,
            MP2::OBJ_FIRE_ALTAR,
            MP2::OBJ_EARTH_ALTAR,
            MP2::OBJ_BARROW_MOUNDS,
            MP2::OBJ_PYRAMID,
            MP2::OBJ_GRAVEYARD,
            MP2::OBJ_SHIPWRECK,
            MP2::OBJ_DERELICT_SHIP,
            MP2::OBJ_DAEMON_CAVE,
            MP2::OBJ_JAIL,
            MP2::OBJ_EYE_OF_MAGI,
            MP2::OBJ_SIGN,
        };
        return objects;
    }

    inline const std::vector<int> & pythonEnvAdventureSpells()
    {
        static const std::vector<int> spells
            = { Spell::IDENTIFYHERO, Spell::VISIONS,      Spell::SUMMONBOAT,   Spell::TOWNGATE,     Spell::TOWNPORTAL,  Spell::DIMENSIONDOOR,
                Spell::HAUNT,        Spell::SETEGUARDIAN, Spell::SETAGUARDIAN, Spell::SETFGUARDIAN, Spell::SETWGUARDIAN };
        return spells;
    }

    inline bool pythonEnvSupportsSpell( const int id )
    {
        const auto & spells = pythonEnvAdventureSpells();
        return std::find( spells.begin(), spells.end(), id ) != spells.end();
    }
}
