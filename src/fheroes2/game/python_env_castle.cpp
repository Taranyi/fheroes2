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

#include "python_env_castle.h"

#if defined( FHEROES2_ENABLE_PYTHON_ENV )

#include <algorithm>
#include <limits>
#include <vector>

#include "army.h"
#include "army_troop.h"
#include "castle.h"
#include "castle_building_info.h"
#include "heroes.h"
#include "kingdom.h"
#include "maps_fileinfo.h"
#include "monster.h"
#include "payment.h"
#include "python_env_world.h"
#include "resource.h"
#include "settings.h"
#include "system.h"
#include "world.h"

namespace
{
    using Json = nlohmann::json;

    Json funds( const Funds & value )
    {
        return { { "wood", value.wood },       { "mercury", value.mercury }, { "ore", value.ore },  { "sulfur", value.sulfur },
                 { "crystal", value.crystal }, { "gems", value.gems },       { "gold", value.gold } };
    }

    Castle & castleById( const uint32_t id )
    {
        for ( Castle * castle : world.getAllCastles() ) {
            if ( static_cast<uint32_t>( castle->GetIndex() ) == id ) {
                return *castle;
            }
        }
        throw fheroes2::PythonEnvError( "invalid_request", "No castle exists with that castle_id." );
    }

    uint32_t identifier( const Json & params, const char * key )
    {
        if ( !params.contains( key ) || !params[key].is_number_unsigned() || params[key].get<uint64_t>() > std::numeric_limits<uint32_t>::max() ) {
            throw fheroes2::PythonEnvError( "invalid_request", std::string( key ) + " must be an unsigned 32-bit integer." );
        }
        return params[key].get<uint32_t>();
    }

    std::vector<BuildingType> buildingCatalog( const Castle & castle )
    {
        // Reuse the engine's faction/map-version building catalog, excluding the non-purchasable town marker.
        auto buildings = fheroes2::getBuildingDrawingPriorities( castle.GetRace(), Settings::Get().getCurrentMapInfo().version );
        buildings.erase( std::remove( buildings.begin(), buildings.end(), BUILD_TENT ), buildings.end() );
        std::sort( buildings.begin(), buildings.end() );
        return buildings;
    }

    const char * buildingStatus( const BuildingStatus status )
    {
        switch ( status ) {
        case BuildingStatus::ALLOW_BUILD:
            return "allow_build";
        case BuildingStatus::NOT_TODAY:
            return "not_today";
        case BuildingStatus::ALREADY_BUILT:
            return "already_built";
        case BuildingStatus::NEED_CASTLE:
            return "need_castle";
        case BuildingStatus::BUILD_DISABLE:
            return "build_disabled";
        case BuildingStatus::SHIPYARD_NOT_ALLOWED:
            return "shipyard_not_allowed";
        case BuildingStatus::UNKNOWN_UPGRADE:
            return "unknown_upgrade";
        case BuildingStatus::REQUIRES_BUILD:
            return "requires_build";
        case BuildingStatus::LACK_RESOURCES:
            return "lack_resources";
        default:
            return "unknown_condition";
        }
    }

    // Follow RecruitMonster's garrison-first rule. Only fall back to the visiting hero if the garrison cannot join.
    const Army * recruitmentArmy( const Castle & castle, const Monster & monster, const Heroes *& visitor )
    {
        visitor = nullptr;
        if ( castle.GetArmy().CanJoinTroop( monster ) ) {
            return &castle.GetArmy();
        }
        visitor = world.GetHero( castle );
        if ( visitor != nullptr && visitor->GetColor() == castle.GetColor() && visitor->GetArmy().CanJoinTroop( monster ) ) {
            return &visitor->GetArmy();
        }
        visitor = nullptr;
        return nullptr;
    }

    uint32_t capacity( const Army & army, const Monster & monster )
    {
        for ( size_t slot = 0; slot < army.Size(); ++slot ) {
            const Troop * troop = army.GetTroop( slot );
            if ( troop->isValid() && troop->isMonster( monster.GetID() ) ) {
                return std::numeric_limits<uint32_t>::max() - troop->GetCount();
            }
        }
        return std::numeric_limits<uint32_t>::max();
    }

    bool baseDwelling( const uint32_t id )
    {
        return id >= DWELLING_MONSTER1 && id <= DWELLING_MONSTER6 && ( id & ( id - 1 ) ) == 0;
    }

    Json dwellingOptions( const Castle & castle, const uint32_t dwelling )
    {
        const uint32_t actual = castle.GetActualDwelling( dwelling );
        const Monster monster( castle.GetRace(), actual );
        const Heroes * visitor = nullptr;
        const Army * target = recruitmentArmy( castle, monster, visitor );
        const uint32_t stock = castle.getMonstersInDwelling( dwelling );
        const bool built = castle.isBuild( dwelling );
        uint32_t limit = built ? castle.getRecruitLimit( monster, castle.GetKingdom().GetFunds() ) : 0;
        limit = target == nullptr ? 0 : std::min( limit, capacity( *target, monster ) );
        const char * status = !built              ? "dwelling_not_built"
                              : stock == 0        ? "out_of_stock"
                              : target == nullptr ? "no_army_room"
                              : limit == 0        ? "lack_resources_or_capacity"
                                                  : "allow_recruit";
        return { { "dwelling_id", dwelling },
                 { "actual_building_id", actual },
                 { "built", built },
                 { "monster_id", monster.GetID() },
                 { "name", System::encLocalToUTF8( monster.GetName() ) },
                 { "available", stock },
                 { "unit_cost", funds( monster.GetCost() ) },
                 { "max_recruitable", limit },
                 { "status", status },
                 { "destination", target == nullptr ? Json( nullptr )
                                                    : Json{ { "type", visitor == nullptr ? "garrison" : "hero" },
                                                            { "hero_id", visitor == nullptr ? Json( nullptr ) : Json( visitor->GetID() ) } } } };
    }
}

nlohmann::json fheroes2::pythonEnvCastleOptions( const uint32_t castleId )
{
    const Castle & castle = castleById( castleId );
    Json buildings = Json::array();
    for ( const auto id : buildingCatalog( castle ) ) {
        const BuildingStatus status = castle.CheckBuyBuilding( id );
        buildings.push_back( { { "building_id", id },
                               { "name", System::encLocalToUTF8( castle.GetStringBuilding( id ) ) },
                               { "built", castle.isBuild( id ) },
                               { "can_build", status == BuildingStatus::ALLOW_BUILD },
                               { "status", buildingStatus( status ) },
                               { "cost", funds( PaymentConditions::BuyBuilding( castle.GetRace(), id ) ) },
                               { "requires", static_cast<uint32_t>( getBuildingRequirement( castle.GetRace(), static_cast<BuildingType>( id ) ) ) } } );
    }
    Json dwellings = Json::array();
    for ( uint32_t id = DWELLING_MONSTER1; id <= DWELLING_MONSTER6; id <<= 1 ) {
        dwellings.push_back( dwellingOptions( castle, id ) );
    }
    return { { "castle_id", castleId },
             { "owner", static_cast<int>( castle.GetColor() ) },
             { "perspective", "omniscient" },
             { "buildings", buildings },
             { "dwellings", dwellings } };
}

nlohmann::json fheroes2::pythonEnvCastleAction( const std::string & action, const nlohmann::json & params, const int playerId )
{
    Castle & castle = castleById( identifier( params, "castle_id" ) );
    if ( static_cast<int>( castle.GetColor() ) != playerId ) {
        throw PythonEnvError( "illegal_action", "The castle must be owned by the waiting player." );
    }
    if ( action == "castle.build" ) {
        if ( params.size() != 2 ) {
            throw PythonEnvError( "invalid_request", "castle.build requires castle_id and building_id." );
        }
        const uint32_t building = identifier( params, "building_id" );
        const auto catalog = buildingCatalog( castle );
        if ( std::find( catalog.begin(), catalog.end(), building ) == catalog.end() ) {
            throw PythonEnvError( "invalid_request", "building_id must identify one purchasable building." );
        }
        const auto status = castle.CheckBuyBuilding( building );
        if ( status != BuildingStatus::ALLOW_BUILD ) {
            throw PythonEnvError( "illegal_action", std::string( "Cannot build: " ) + buildingStatus( status ) );
        }
        const Funds cost = PaymentConditions::BuyBuilding( castle.GetRace(), building );
        if ( !castle.BuyBuilding( building ) ) {
            throw PythonEnvError( "engine_error", "The validated building purchase failed." );
        }
        return { { "type", "castle_built" }, { "castle_id", castle.GetIndex() }, { "building_id", building }, { "cost", funds( cost ) } };
    }
    if ( params.size() != 3 ) {
        throw PythonEnvError( "invalid_request", "castle.recruit requires castle_id, dwelling_id and count." );
    }
    const uint32_t dwelling = identifier( params, "dwelling_id" );
    const uint32_t count = identifier( params, "count" );
    if ( !baseDwelling( dwelling ) || count == 0 ) {
        throw PythonEnvError( "invalid_request", "Use a base dwelling_id and a positive count." );
    }
    const Json options = dwellingOptions( castle, dwelling );
    if ( count > options["max_recruitable"].get<uint32_t>() ) {
        throw PythonEnvError( "illegal_action", "The exact count exceeds the built dwelling's stock, funds or army capacity." );
    }
    const Troop troop( Monster( castle.GetRace(), castle.GetActualDwelling( dwelling ) ), count );
    const Funds cost = troop.GetTotalCost();
    // RecruitMonster assumes the original troop count is in stock; never forward an unchecked request.
    if ( !castle.RecruitMonster( troop, false ) ) {
        throw PythonEnvError( "engine_error", "The validated recruitment failed." );
    }
    return { { "type", "castle_recruited" }, { "castle_id", castle.GetIndex() },       { "dwelling_id", dwelling }, { "monster_id", troop.GetID() }, { "count", count },
             { "cost", funds( cost ) },      { "destination", options["destination"] } };
}

#endif
