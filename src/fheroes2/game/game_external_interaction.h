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

#include <cstdint>
#include <functional>
#include <map>
#include <string>
#include <vector>

namespace Battle
{
    class Arena;
    class Unit;
    class Actions;
    struct Result;
}

namespace Game
{
    // UI-independent description. Options are exact native return values; an empty list describes an integer range.
    struct ExternalChoice
    {
        std::string kind;
        int heroId{ -1 };
        std::vector<int64_t> options;
        std::map<std::string, int64_t> values;
        int64_t minimum{ 0 };
        int64_t maximum{ 0 };
    };

    class ExternalActionCancelled final
    {};

    class ScopedExternalInteractions final
    {
    public:
        ScopedExternalInteractions( std::function<int64_t( const ExternalChoice & )> choose, std::function<void( const std::string &, const std::string & )> notify,
                                    std::function<void( Battle::Arena &, const Battle::Unit &, Battle::Actions & )> battle = {},
                                    std::function<void( const Battle::Result &, int32_t )> battleFinished = {} );
        ~ScopedExternalInteractions();
        ScopedExternalInteractions( const ScopedExternalInteractions & ) = delete;
        ScopedExternalInteractions & operator=( const ScopedExternalInteractions & ) = delete;

        static int64_t choose( const ExternalChoice & choice );
        static void notify( const std::string & title, const std::string & message );
        static bool hasBattleController();
        static void battle( Battle::Arena & arena, const Battle::Unit & unit, Battle::Actions & actions );
        static void battleFinished( const Battle::Result & result, int32_t tile );

    private:
        ScopedExternalInteractions * _previous;
        std::function<int64_t( const ExternalChoice & )> _choose;
        std::function<void( const std::string &, const std::string & )> _notify;
        std::function<void( Battle::Arena &, const Battle::Unit &, Battle::Actions & )> _battle;
        std::function<void( const Battle::Result &, int32_t )> _battleFinished;
    };
}
