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

#include "python_env_world.h"

#if defined( FHEROES2_ENABLE_PYTHON_ENV )

#include <algorithm>
#include <string>

#include "ai_planner.h"
#include "game.h"
#include "game_over.h"
#include "kingdom.h"
#include "maps_fileinfo.h"
#include "players.h"
#include "settings.h"
#include "system.h"
#include "world.h"

namespace
{
    using Json = nlohmann::json;
}

bool fheroes2::PythonEnvWorld::externalPlayer( const int color ) const
{
    const auto key = std::to_string( color );
    return _controlled && _controllers.contains( key ) && _controllers[key] == "python";
}

int fheroes2::PythonEnvWorld::gameResult() const
{
    if ( !_controlled )
        return static_cast<int>( GameOver::Result::Get().GetResult() );
    const auto key = std::to_string( _controllerPlayer );
    return _outcomes.contains( key ) ? _outcomes[key].get<int>() : 0;
}

Json fheroes2::PythonEnvWorld::controlState() const
{
    return { { "controllers", _controllers },     { "outcomes", _outcomes },
             { "finished", _simulationFinished }, { "turn_player_id", _turnOrder.empty() ? 0 : _turnOrder.at( _turnIndex ) },
             { "turn_order", _turnOrder },        { "rule_profiles", "native_player_flags" } };
}

void fheroes2::PythonEnvWorld::startControlledSession( const Json & controllers, const std::function<void( const Json & )> & wait )
{
    if ( _waiting )
        throw PythonEnvError( "session_active", "A controller session is already active." );
    if ( !_loaded )
        throw PythonEnvError( "no_game_loaded", "Load a standard map or save before assigning controllers." );
    if ( _controlled )
        throw PythonEnvError( "unsupported_state", "Reset before assigning a new controller configuration." );
    if ( ( Settings::Get().GameType() & ~Game::TYPE_LOADFILE ) != Game::TYPE_STANDARD || GameOver::Result::Get().GetResult() != 0 ) {
        throw PythonEnvError( "unsupported_state", "Expected a live standard game." );
    }
    if ( !controllers.is_object() || controllers.empty() )
        throw PythonEnvError( "invalid_request", "controllers must map every participant ID to python or builtin_ai." );
    std::vector<int> order;
    Json outcomes = Json::object();
    for ( const Player * player : Game::getPlayersInTurnOrder() ) {
        const int color = static_cast<int>( player->GetColor() );
        const auto key = std::to_string( color );
        if ( !controllers.contains( key ) || !controllers[key].is_string() || ( controllers[key] != "python" && controllers[key] != "builtin_ai" ) ) {
            throw PythonEnvError( "invalid_request", "Assign exactly one python or builtin_ai controller to every map participant." );
        }
        order.push_back( color );
        outcomes[key] = world.GetKingdom( player->GetColor() ).isPlay() ? 0U : static_cast<uint32_t>( GameOver::LOSS_ALL );
    }
    if ( order.empty() || controllers.size() != order.size() )
        throw PythonEnvError( "invalid_request", "Unknown controller participant or empty game." );
    const auto current = std::find( order.begin(), order.end(), static_cast<int>( Settings::Get().CurrentColor() ) );
    _turnIndex = current == order.end() ? 0 : static_cast<size_t>( current - order.begin() );
    _turnOrder = std::move( order );
    _controllers = controllers;
    _outcomes = std::move( outcomes );
    _controlled = true;
    _incomePrepared = true; // The saved turn or native new-game first turn already received its daily update.
    _controllerPlayer = externalPlayer( _turnOrder[_turnIndex] ) ? _turnOrder[_turnIndex] : 0;
    ++_decisionId;
    _waiting = true;
    try {
        wait( getDecision() );
    }
    catch ( ... ) {
        _waiting = false;
        _controllerPlayer = 0;
        throw;
    }
    _waiting = false;
    _controllerPlayer = 0;
}

bool fheroes2::PythonEnvWorld::evaluateSimulation()
{
    if ( _simulationFinished )
        return true;
    const auto & map = Settings::Get().getCurrentMapInfo();
    std::vector<int> winners;
    std::vector<int> eliminated;
    // Native predicates retain map victory eligibility, alliances and special human-rule loss conditions.
    for ( const int color : _turnOrder ) {
        const auto key = std::to_string( color );
        if ( _outcomes[key].get<uint32_t>() != 0 )
            continue;
        Kingdom & kingdom = world.GetKingdom( static_cast<PlayerColor>( color ) );
        uint32_t loss = !kingdom.isPlay() ? GameOver::LOSS_ALL : ( kingdom.isControlHuman() ? world.CheckKingdomLoss( kingdom ) : 0 );
        if ( loss != 0 ) {
            _outcomes[key] = loss;
            eliminated.push_back( color );
            continue;
        }
        uint32_t win = 0;
        if ( kingdom.isControlHuman() )
            win = world.CheckKingdomWins( kingdom );
        else {
            for ( const uint32_t condition : { GameOver::WINS_ALL, GameOver::WINS_TOWN, GameOver::WINS_ARTIFACT, GameOver::WINS_SIDE, GameOver::WINS_GOLD } ) {
                if ( ( map.ConditionWins() & condition ) && world.KingdomIsWins( kingdom, condition ) ) {
                    win = condition;
                    break;
                }
            }
        }
        if ( win != 0 ) {
            _outcomes[key] = win;
            winners.push_back( color );
        }
    }
    for ( const int color : eliminated ) {
        world.GetKingdom( static_cast<PlayerColor>( color ) ).LossPostActions();
        _events.push_back( { { "type", "participant_eliminated" }, { "player_id", color }, { "result", _outcomes[std::to_string( color )] } } );
    }
    if ( !winners.empty() ) {
        _simulationFinished = true;
        for ( const int color : _turnOrder ) {
            auto & outcome = _outcomes[std::to_string( color )];
            if ( outcome.get<uint32_t>() == 0 )
                outcome = GameOver::LOSS_ALL;
        }
    }
    else if ( std::all_of( _outcomes.begin(), _outcomes.end(), []( const Json & outcome ) { return outcome.get<uint32_t>() != 0; } ) ) {
        _simulationFinished = true;
    }
    if ( _simulationFinished )
        _events.push_back( { { "type", "simulation_finished" }, { "outcomes", _outcomes } } );
    return _simulationFinished;
}

void fheroes2::PythonEnvWorld::prepareScheduledTurn()
{
    const auto color = static_cast<PlayerColor>( _turnOrder.at( _turnIndex ) );
    Settings::Get().SetCurrentColor( color );
    const auto income = [&]() {
        world.GetKingdom( color ).ActionNewDayResourceUpdate( [&]( const EventDate & event, const Funds & funds ) {
            _events.push_back( { { "type", "daily_event" },
                                 { "player_id", static_cast<int>( color ) },
                                 { "day", world.CountDay() },
                                 { "title", System::encLocalToUTF8( event.title ) },
                                 { "message", System::encLocalToUTF8( event.message ) },
                                 { "funds",
                                   { { "wood", funds.wood },
                                     { "mercury", funds.mercury },
                                     { "ore", funds.ore },
                                     { "sulfur", funds.sulfur },
                                     { "crystal", funds.crystal },
                                     { "gems", funds.gems },
                                     { "gold", funds.gold } } } } );
        } );
        _incomePrepared = true;
    };
    // Retain the native rule-profile ordering: AI income precedes ActionBeforeTurn;
    // the human turn receives its income after ActionBeforeTurn.
    if ( !_incomePrepared && world.GetKingdom( color ).isControlAI() )
        income();
    if ( !_turnPrepared ) {
        world.resetPathfinder();
        world.GetKingdom( color ).ActionBeforeTurn();
        _turnPrepared = true;
    }
    if ( !_incomePrepared ) {
        income();
    }
}

void fheroes2::PythonEnvWorld::completeScheduledTurn()
{
    if ( evaluateSimulation() )
        return;
    for ( size_t skipped = 0; skipped <= _turnOrder.size(); ++skipped ) {
        _turnIndex = ( _turnIndex + 1 ) % _turnOrder.size();
        if ( _turnIndex == 0 ) {
            Settings::Get().SetCurrentColor( PlayerColor::NONE );
            world.NewDay();
            if ( evaluateSimulation() )
                return;
        }
        _turnPrepared = false;
        _incomePrepared = false;
        const int color = _turnOrder[_turnIndex];
        if ( _outcomes[std::to_string( color )].get<uint32_t>() != 0 )
            continue;
        Settings::Get().SetCurrentColor( static_cast<PlayerColor>( color ) );
        _controllerPlayer = externalPlayer( color ) ? color : 0;
        if ( _controllerPlayer != 0 )
            prepareScheduledTurn();
        return;
    }
    throw PythonEnvError( "engine_error", "No active scheduled participant found." );
}

void fheroes2::PythonEnvWorld::advanceSimulation( const uint32_t maxTurns )
{
    for ( uint32_t count = 0; count < maxTurns && !_simulationFinished && _controllerPlayer == 0; ++count ) {
        if ( evaluateSimulation() )
            break;
        prepareScheduledTurn();
        const int color = _turnOrder.at( _turnIndex );
        const uint32_t day = world.CountDay();
        const auto result = AI::Planner::Get().KingdomTurn( world.GetKingdom( static_cast<PlayerColor>( color ) ) );
        if ( result != GameMode::END_TURN && !_simulationFinished )
            throw PythonEnvError( "unsupported_state", "Native AI did not complete its scheduled turn." );
        _events.push_back( { { "type", "ai_turn_completed" }, { "player_id", color }, { "day", day } } );
        completeScheduledTurn();
    }
}

#endif
