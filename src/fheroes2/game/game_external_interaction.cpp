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
                                                              std::function<void( const std::string &, const std::string & )> notify,
                                                              std::function<void( Battle::Arena &, const Battle::Unit &, Battle::Actions & )> battle,
                                                              std::function<void( const Battle::Result &, int32_t )> battleFinished,
                                                              std::function<ControllerType( int )> controller, std::function<bool()> gameOver,
                                                              std::function<std::string( const ExternalTextChoice & )> text,
                                                              std::function<void( const std::string &, int, int )> information )
    : _previous( current )
    , _choose( std::move( choose ) )
    , _notify( std::move( notify ) )
    , _battle( std::move( battle ) )
    , _battleFinished( std::move( battleFinished ) )
    , _controller( std::move( controller ) )
    , _gameOver( std::move( gameOver ) )
    , _text( std::move( text ) )
    , _information( std::move( information ) )
{
    current = this;
}

Game::ScopedExternalInteractions::~ScopedExternalInteractions()
{
    current = _previous;
}

bool Game::ScopedExternalInteractions::hasAssignments()
{
    return current != nullptr && static_cast<bool>( current->_controller );
}
bool Game::ScopedExternalInteractions::isExternal( const int color )
{
    return hasAssignments() && current->_controller( color ) == ControllerType::External;
}
bool Game::ScopedExternalInteractions::isNative( const int color )
{
    return hasAssignments() && current->_controller( color ) == ControllerType::Native;
}
bool Game::ScopedExternalInteractions::hasGameOverController()
{
    return current != nullptr && static_cast<bool>( current->_gameOver );
}
bool Game::ScopedExternalInteractions::gameOver()
{
    return hasGameOverController() && current->_gameOver();
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

bool Game::ScopedExternalInteractions::hasBattleController()
{
    return current != nullptr && static_cast<bool>( current->_battle );
}

void Game::ScopedExternalInteractions::battle( Battle::Arena & arena, const Battle::Unit & unit, Battle::Actions & actions )
{
    if ( !hasBattleController() ) {
        throw System::HeadlessInteractionError( "battle without an external controller" );
    }
    current->_battle( arena, unit, actions );
}

void Game::ScopedExternalInteractions::battleFinished( const Battle::Result & result, const int32_t tile )
{
    if ( current != nullptr && current->_battleFinished ) {
        current->_battleFinished( result, tile );
    }
}

std::string Game::ScopedExternalInteractions::text( const ExternalTextChoice & choice )
{
    if ( current == nullptr || !current->_text )
        throw System::HeadlessInteractionError( "text choice without an external controller" );
    return current->_text( choice );
}

void Game::ScopedExternalInteractions::information( const std::string & kind, const int color, const int detail )
{
    if ( current == nullptr || !current->_information )
        throw System::HeadlessInteractionError( "information view without an external controller" );
    current->_information( kind, color, detail );
}
