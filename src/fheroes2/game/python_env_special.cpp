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
#include <array>
#include <string>

#include "castle.h"
#include "dialog.h"
#include "game.h"
#include "heroes.h"
#include "image.h"
#include "kingdom.h"
#include "maps_tiles.h"
#include "maps_tiles_helper.h"
#include "monster.h"
#include "mp2.h"
#include "players.h"
#include "rand.h"
#include "resource.h"
#include "resource_trading.h"
#include "system.h"
#include "view_world.h"
#include "world.h"

namespace
{
    using Json = nlohmann::json;
    constexpr std::array<int, 7> resources{ Resource::WOOD, Resource::MERCURY, Resource::ORE, Resource::SULFUR, Resource::CRYSTAL, Resource::GEMS, Resource::GOLD };
    uint32_t id( const Json & params, const char * name )
    {
        if ( !params.contains( name ) || !params[name].is_number_unsigned() || params[name].get<uint64_t>() > UINT32_MAX )
            throw fheroes2::PythonEnvError( "invalid_request", std::string( "Expected unsigned " ) + name );
        return params[name].get<uint32_t>();
    }
}

Json fheroes2::PythonEnvWorld::getTradingPostOptions( const uint32_t heroId ) const
{
    if ( !_loaded )
        throw PythonEnvError( "no_game_loaded", "Load a game before querying a Trading Post." );
    if ( heroId > Heroes::DEBUG_HERO )
        throw PythonEnvError( "invalid_request", "Invalid hero ID." );
    const Heroes * hero = world.GetHeroes( heroId );
    const bool active = !_tradingPost.is_null() && _tradingPost["hero_id"] == heroId && hero != nullptr && hero->isActive()
                        && hero->GetIndex() == _tradingPost["hero_index"] && static_cast<int>( hero->GetColor() ) == _controllerPlayer
                        && world.getTile( _tradingPost["tile_index"].get<int>() ).getMainObjectType( false ) == MP2::OBJ_TRADING_POST;
    Json trades = Json::array();
    if ( active ) {
        for ( const int from : resources ) {
            for ( const int to : resources ) {
                if ( from == to )
                    continue;
                const auto quote = getResourceTradeQuote( hero->GetKingdom(), from, to, true );
                trades.push_back( { { "resource_from", from },
                                    { "resource_to", to },
                                    { "sell_per_lot", quote.sellPerLot },
                                    { "buy_per_lot", quote.buyPerLot },
                                    { "max_lots", quote.maxLots } } );
            }
        }
    }
    return { { "hero_id", heroId }, { "active", active }, { "trades", trades }, { "state_version", _stateVersion }, { "visit", _tradingPost } };
}

Json fheroes2::PythonEnvWorld::tradeAtPost( const Json & params, const int player, const bool validateOnly )
{
    if ( params.size() != 4 )
        throw PythonEnvError( "invalid_request", "trading_post.trade requires hero_id, resource_from, resource_to and lots." );
    const auto heroId = id( params, "hero_id" );
    const int from = id( params, "resource_from" );
    const int to = id( params, "resource_to" );
    const auto lots = id( params, "lots" );
    if ( std::find( resources.begin(), resources.end(), from ) == resources.end() || std::find( resources.begin(), resources.end(), to ) == resources.end() || from == to
         || lots == 0 )
        throw PythonEnvError( "invalid_request", "Use two distinct native resource IDs and a positive lot count." );
    if ( !getTradingPostOptions( heroId )["active"].get<bool>() )
        throw PythonEnvError( "illegal_action", "The waiting hero must have an active Trading Post visit." );
    Heroes * hero = world.GetHeroes( heroId );
    if ( static_cast<int>( hero->GetColor() ) != player )
        throw PythonEnvError( "illegal_action", "The Trading Post visitor must belong to the waiting participant." );
    const auto quote = getResourceTradeQuote( hero->GetKingdom(), from, to, true );
    if ( lots > quote.maxLots )
        throw PythonEnvError( "illegal_action", "The exact trade exceeds native funds or destination capacity." );
    if ( !validateOnly && !tradeResources( hero->GetKingdom(), from, to, lots, true ) )
        throw PythonEnvError( "illegal_action", "The native Trading Post exchange failed." );
    return { { "type", "trading_post_trade" },
             { "hero_id", heroId },
             { "player_id", player },
             { "resource_from", from },
             { "resource_to", to },
             { "lots", lots },
             { "sold", lots * quote.sellPerLot },
             { "bought", lots * quote.buyPerLot } };
}

Json fheroes2::PythonEnvWorld::getInformationView() const
{
    if ( _informationView.is_null() )
        throw PythonEnvError( "no_information_view", "Open an Oracle or View World spell first." );
    return _informationView;
}

void fheroes2::PythonEnvWorld::showInformation( const std::string & kind, const int color, const int detail, const int destination )
{
    if ( kind == "trading_post" ) {
        Heroes * hero = world.GetHeroes( detail );
        if ( hero == nullptr || destination < 0 || world.getTile( destination ).getMainObjectType( false ) != MP2::OBJ_TRADING_POST )
            throw PythonEnvError( "unsupported_interaction", "Invalid native Trading Post visitor." );
        _tradingPost = { { "hero_id", detail }, { "tile_index", destination }, { "hero_index", hero->GetIndex() } };
        _events.push_back( { { "type", "trading_post_opened" }, { "hero_id", detail }, { "tile_index", destination } } );
        return;
    }
    const auto savedRandom = Rand::CurrentThreadRandomDevice();
    struct RestoreRandom
    {
        Rand::PCG32 state;
        ~RestoreRandom()
        {
            Rand::CurrentThreadRandomDevice() = state;
        }
    } restore{ savedRandom };
    Json data
        = { { "kind", kind }, { "player_id", color }, { "mode", detail }, { "day", world.CountDay() }, { "state_version", _stateVersion + 1 }, { "snapshot", true } };
    auto image = std::make_shared<Image>();
    if ( kind == "world" ) {
        const auto mode = static_cast<ViewWorldMode>( detail );
        if ( detail < 0 || detail > 6 )
            throw PythonEnvError( "invalid_request", "Invalid native View World mode." );
        ViewWorld::renderSnapshot( static_cast<PlayerColor>( color ), mode, *image );
        data["width"] = world.w();
        data["height"] = world.h();
        data["tiles"] = Json::array();
        data["markers"] = Json::array();
        for ( int index = 0; index < world.w() * world.h(); ++index ) {
            const auto & tile = world.getTile( index );
            if ( mode == ViewWorldMode::ViewAll || !tile.isFog( static_cast<PlayerColor>( color ) ) )
                data["tiles"].push_back( { { "index", index }, { "terrain_image", tile.getTerrainImageIndex() }, { "terrain_flags", tile.getTerrainFlags() } } );
            const auto under = tile.getMainObjectType( false );
            const auto main = tile.getMainObjectType( true );
            for ( const auto type : { under, main } ) {
                if ( type != MP2::OBJ_HERO && type != MP2::OBJ_CASTLE && type != MP2::OBJ_MINE && type != MP2::OBJ_ALCHEMIST_LAB && type != MP2::OBJ_SAWMILL
                     && type != MP2::OBJ_RESOURCE && type != MP2::OBJ_ARTIFACT )
                    continue;
                if ( tile.isFog( static_cast<PlayerColor>( color ) ) && !ViewWorld::revealsObject( mode, type ) )
                    continue;
                int owner = static_cast<int>( world.ColorCapturedObject( index ) );
                int resource = 0;
                if ( type == MP2::OBJ_HERO && tile.getHero() != nullptr )
                    owner = static_cast<int>( tile.getHero()->GetColor() );
                if ( type == MP2::OBJ_CASTLE ) {
                    const Castle * castle = world.getCastleEntrance( tile.GetCenter() );
                    if ( castle != nullptr )
                        owner = static_cast<int>( castle->GetColor() );
                }
                if ( type == MP2::OBJ_RESOURCE )
                    resource = Maps::getFundsFromTile( tile ).getFirstValidResource().first;
                if ( type == MP2::OBJ_MINE || type == MP2::OBJ_ALCHEMIST_LAB || type == MP2::OBJ_SAWMILL ) {
                    owner = static_cast<int>( Maps::getColorFromTile( tile ) );
                    resource = Maps::getDailyIncomeObjectResources( tile ).getFirstValidResource().first;
                }
                const char * category
                    = type == MP2::OBJ_HERO
                          ? "hero"
                          : ( type == MP2::OBJ_CASTLE ? "town" : ( type == MP2::OBJ_RESOURCE ? "resource" : ( type == MP2::OBJ_ARTIFACT ? "artifact" : "mine" ) ) );
                data["markers"].push_back(
                    { { "kind", category }, { "index", index }, { "object_type", static_cast<int>( type ) }, { "owner", owner }, { "resource_id", resource } } );
                if ( under == main )
                    break;
            }
        }
    }
    else if ( kind == "oracle" ) {
        Dialog::renderOracleSnapshot( *image );
        data["players"] = Json::array();
        for ( const PlayerColor player : PlayerColorsVector( Game::GetActualKingdomColors() ) ) {
            const auto & kingdom = world.GetKingdom( player );
            const Funds & funds = kingdom.GetFunds();
            const Heroes * best = kingdom.GetBestHero();
            data["players"].push_back(
                { { "player_id", static_cast<int>( player ) },
                  { "towns", kingdom.GetCountTown() },
                  { "castles", kingdom.GetCountCastle() },
                  { "heroes", kingdom.GetHeroes().size() },
                  { "gold", funds.gold },
                  { "wood_ore", static_cast<int64_t>( funds.wood ) + funds.ore },
                  { "rare_resources", static_cast<int64_t>( funds.gems ) + funds.crystal + funds.sulfur + funds.mercury },
                  { "obelisks", kingdom.CountVisitedObjects( MP2::OBJ_OBELISK ) },
                  { "artifacts", kingdom.GetCountArtifacts() },
                  { "army_strength", static_cast<int64_t>( kingdom.GetArmiesStrength() ) },
                  { "income", kingdom.GetIncome().gold },
                  { "best_hero_id", best == nullptr ? -1 : best->GetID() },
                  { "attack", best == nullptr ? 0 : best->GetAttack() },
                  { "defense", best == nullptr ? 0 : best->GetDefense() },
                  { "power", best == nullptr ? 0 : best->GetPower() },
                  { "knowledge", best == nullptr ? 0 : best->GetKnowledge() },
                  { "best_monster_id", kingdom.GetStrongestMonster().GetID() },
                  { "is_human", kingdom.isControlHuman() },
                  { "personality", kingdom.isControlHuman() ? std::string( "Human" ) : System::encLocalToUTF8( Players::Get( player )->GetPersonalityString() ) } } );
        }
    }
    else
        throw PythonEnvError( "unsupported_interaction", "Unknown native information view." );
    _informationView = std::move( data );
    _informationImage = std::move( image );
    _events.push_back( { { "type", "information_view" }, { "kind", kind }, { "player_id", color }, { "mode", detail } } );
}

#endif
