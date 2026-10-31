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

#include <string>

#include "../../thirdparty/nlohmann/json.hpp"

namespace fheroes2
{
    nlohmann::json pythonEnvArmyAction( const std::string & action, const nlohmann::json & params, int playerId, nlohmann::json & meeting, bool validateOnly = false );
    nlohmann::json pythonEnvEndMeeting( nlohmann::json & meeting );
    nlohmann::json pythonEnvArmyOptions( const nlohmann::json & params );
}

#endif
