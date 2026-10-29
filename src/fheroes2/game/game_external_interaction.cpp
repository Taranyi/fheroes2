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

#include "game_external_interaction.h"

#include <utility>

#include "core.h"

namespace
{
    thread_local Game::ScopedExternalInteractions * current = nullptr;
}

Game::ScopedExternalInteractions::ScopedExternalInteractions( std::function<int64_t( const ExternalChoice & )> choose,
                                                              std::function<void( const std::string &, const std::string & )> notify )
    : _previous( current )
    , _choose( std::move( choose ) )
    , _notify( std::move( notify ) )
{
    current = this;
}

Game::ScopedExternalInteractions::~ScopedExternalInteractions()
{
    current = _previous;
}

int64_t Game::ScopedExternalInteractions::choose( const ExternalChoice & choice )
{
    if ( current == nullptr ) {
        throw System::HeadlessInteractionError( "external choice without a controller" );
    }
    return current->_choose( choice );
}

void Game::ScopedExternalInteractions::notify( const std::string & title, const std::string & message )
{
    if ( current == nullptr ) {
        throw System::HeadlessInteractionError( "external notification without a controller" );
    }
    current->_notify( title, message );
}
