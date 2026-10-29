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

#if defined( FHEROES2_ENABLE_PYTHON_ENV )
#include <vector>

#include "../../thirdparty/nlohmann/json.hpp"
#include "battle_command.h"

namespace Battle
{
    class Arena;
    class Unit;
}

namespace fheroes2
{
    struct PythonEnvBattleDecision
    {
        nlohmann::json state;
        std::vector<Battle::Command> commands;
    };

    PythonEnvBattleDecision pythonEnvBattleDecision( Battle::Arena & arena, const Battle::Unit & unit );
}
#endif
