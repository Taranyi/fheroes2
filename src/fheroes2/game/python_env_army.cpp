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

#include "python_env_army.h"

#if defined( FHEROES2_ENABLE_PYTHON_ENV )

#include <cstdint>
#include <cstdlib>
#include <limits>

#include "army.h"
#include "army_troop.h"
#include "artifact.h"
#include "artifact_info.h"
#include "castle.h"
#include "heroes.h"
#include "kingdom.h"
#include "payment.h"
#include "python_env_world.h"
#include "resource.h"
#include "route.h"
#include "world.h"

namespace
{
    using Json = nlohmann::json;

    uint32_t identifier( const Json & params, const char * key )
    {
        if ( !params.contains( key ) || !params[key].is_number_unsigned() || params[key].get<uint64_t>() > std::numeric_limits<uint32_t>::max() ) {
            throw fheroes2::PythonEnvError( "invalid_request", std::string( key ) + " must be an unsigned 32-bit integer." );
        }
        return params[key].get<uint32_t>();
    }

    Heroes & activeHero( const uint32_t id )
    {
        if ( id > static_cast<uint32_t>( Heroes::DEBUG_HERO ) ) {
            throw fheroes2::PythonEnvError( "invalid_request", "hero_id is outside the native hero catalog." );
        }
        Heroes * hero = world.GetHeroes( static_cast<int>( id ) );
        if ( hero == nullptr || !hero->isActive() ) {
            throw fheroes2::PythonEnvError( "illegal_action", "The hero must be active." );
        }
        return *hero;
    }

    Heroes & ownedHero( const uint32_t id, const int playerId )
    {
        Heroes & hero = activeHero( id );
        if ( static_cast<int>( hero.GetColor() ) != playerId ) {
            throw fheroes2::PythonEnvError( "illegal_action", "The hero must be owned by the waiting player." );
        }
        return hero;
    }

    Json funds( const Funds & value )
    {
        return { { "wood", value.wood },       { "mercury", value.mercury }, { "ore", value.ore },  { "sulfur", value.sulfur },
                 { "crystal", value.crystal }, { "gems", value.gems },       { "gold", value.gold } };
    }

    struct Endpoint
    {
        Army * army;
        Heroes * hero;
        Castle * castle;
        Troop * troop;
    };

    Endpoint resolveEndpoint( const Json & value )
    {
        if ( !value.is_object() || value.size() != 3 || !value.contains( "kind" ) || !value["kind"].is_string() ) {
            throw fheroes2::PythonEnvError( "invalid_request", "An army endpoint requires kind (hero/castle), id and slot." );
        }
        const uint32_t id = identifier( value, "id" );
        const uint32_t slot = identifier( value, "slot" );
        if ( slot >= Army::maximumTroopCount ) {
            throw fheroes2::PythonEnvError( "invalid_request", "Army slots are numbered 0 through 4." );
        }
        if ( value["kind"] == "hero" ) {
            Heroes & hero = activeHero( id );
            return { &hero.GetArmy(), &hero, nullptr, hero.GetArmy().GetTroop( slot ) };
        }
        if ( value["kind"] == "castle" ) {
            for ( Castle * castle : world.getAllCastles() ) {
                if ( static_cast<uint32_t>( castle->GetIndex() ) != id ) {
                    continue;
                }
                return { &castle->GetArmy(), nullptr, castle, castle->GetArmy().GetTroop( slot ) };
            }
            throw fheroes2::PythonEnvError( "invalid_request", "No castle exists with that id." );
        }
        throw fheroes2::PythonEnvError( "invalid_request", "Army endpoint kind must be hero or castle." );
    }

    Endpoint endpoint( const Json & value, const int playerId )
    {
        const auto result = resolveEndpoint( value );
        const auto color = result.hero != nullptr ? result.hero->GetColor() : result.castle->GetColor();
        if ( static_cast<int>( color ) != playerId ) {
            throw fheroes2::PythonEnvError( "illegal_action", "The army must be owned by the waiting player." );
        }
        return result;
    }

    bool inMeeting( const Heroes & a, const Heroes & b, const Json & meeting )
    {
        return !meeting.is_null()
               && ( ( meeting["hero_id"] == a.GetID() && meeting["other_hero_id"] == b.GetID() && meeting["from"] == a.GetIndex() && meeting["to"] == b.GetIndex() )
                    || ( meeting["hero_id"] == b.GetID() && meeting["other_hero_id"] == a.GetID() && meeting["from"] == b.GetIndex() && meeting["to"] == a.GetIndex() ) );
    }

    void checkAccess( const Endpoint & a, const Endpoint & b, const Json & meeting )
    {
        if ( a.army == b.army ) {
            return;
        }
        if ( a.hero != nullptr && b.hero != nullptr ) {
            if ( inMeeting( *a.hero, *b.hero, meeting ) ) {
                return;
            }
            throw fheroes2::PythonEnvError( "illegal_action", "Use hero.meet before transferring between heroes." );
        }
        const Heroes * hero = a.hero != nullptr ? a.hero : b.hero;
        const Castle * castle = a.castle != nullptr ? a.castle : b.castle;
        if ( hero != nullptr && castle != nullptr && hero->GetIndex() == castle->GetIndex() && world.GetHero( *castle ) == hero ) {
            return;
        }
        throw fheroes2::PythonEnvError( "illegal_action", "A hero must occupy the castle visitor slot; remote castle transfers are forbidden." );
    }

    struct ArtifactEndpoint
    {
        Heroes * hero;
        Artifact * artifact;
    };

    ArtifactEndpoint artifactEndpoint( const Json & value, const int playerId )
    {
        if ( !value.is_object() || value.size() != 2 ) {
            throw fheroes2::PythonEnvError( "invalid_request", "An artifact endpoint requires hero_id and slot." );
        }
        Heroes & hero = ownedHero( identifier( value, "hero_id" ), playerId );
        const uint32_t slot = identifier( value, "slot" );
        if ( slot >= BagArtifacts::maxCapacity || slot >= hero.GetBagArtifacts().size() ) {
            throw fheroes2::PythonEnvError( "invalid_request", "Artifact slots are numbered 0 through 13." );
        }
        return { &hero, &hero.GetBagArtifacts()[slot] };
    }

    Json artifactState( const Artifact & artifact )
    {
        return artifact.isValid() ? Json{ { "id", artifact.GetID() }, { "spell_id", artifact.getSpellId() } } : Json( nullptr );
    }

    Json artifactAction( const std::string & action, const Json & params, const int playerId, const Json & meeting, const bool validateOnly )
    {
        if ( params.size() != 2 || !params.contains( "source" ) || !params.contains( "target" ) ) {
            throw fheroes2::PythonEnvError( "invalid_request", "Artifact operations require source and target endpoints." );
        }
        const auto source = artifactEndpoint( params["source"], playerId );
        const auto target = artifactEndpoint( params["target"], playerId );
        if ( source.hero != target.hero && !inMeeting( *source.hero, *target.hero, meeting ) ) {
            throw fheroes2::PythonEnvError( "illegal_action", "Use hero.meet before exchanging artifacts between heroes." );
        }
        if ( action == "artifact.transfer" && ( !source.artifact->isValid() || target.artifact->isValid() ) ) {
            throw fheroes2::PythonEnvError( "illegal_action",
                                            "Transfer requires a valid source artifact and an empty target slot; use artifact.swap for occupied slots." );
        }
        const Json beforeSource = artifactState( *source.artifact );
        const Json beforeTarget = artifactState( *target.artifact );
        if ( validateOnly ) {
            Artifact a = *source.artifact;
            Artifact b = *target.artifact;
            if ( source.artifact == target.artifact || !BagArtifacts::swapArtifactSlots( a, b ) ) {
                throw fheroes2::PythonEnvError( "illegal_action", "The artifact slots cannot be exchanged." );
            }
            return Json::object();
        }
        if ( !BagArtifacts::swapArtifactSlots( *source.artifact, *target.artifact ) ) {
            throw fheroes2::PythonEnvError( "illegal_action", "Select distinct slots with at least one artifact; Magic Books cannot be moved or traded." );
        }
        Json assembled = Json::array();
        if ( source.hero != target.hero ) {
            // Same set-assembly rule as the normal meeting window, without its notification dialog.
            for ( Heroes * hero : { source.hero, target.hero } ) {
                for ( const auto & set : hero->GetBagArtifacts().assembleArtifactSetIfPossible() ) {
                    assembled.push_back( { { "hero_id", hero->GetID() }, { "artifact_id", set._assembledArtifactID } } );
                }
            }
        }
        world.resetPathfinder();
        return { { "type", action == "artifact.transfer" ? "artifact_transferred" : "artifacts_swapped" },
                 { "source", params["source"] },
                 { "target", params["target"] },
                 { "source_artifact", beforeSource },
                 { "target_artifact", beforeTarget },
                 { "assembled_sets", assembled } };
    }
}

nlohmann::json fheroes2::pythonEnvArmyOptions( const nlohmann::json & params )
{
    if ( params.size() != 2 ) {
        throw PythonEnvError( "invalid_request", "get_army_options requires kind and id." );
    }
    Json reference = params;
    reference["slot"] = 0U;
    const auto entity = resolveEndpoint( reference );
    Json slots = Json::array();
    for ( size_t slot = 0; slot < entity.army->Size(); ++slot ) {
        const Troop & troop = *entity.army->GetTroop( slot );
        const bool upgradable = troop.isValid() && troop.isAllowUpgrade();
        Funds cost;
        const bool priced = Army::getTroopUpgradeCost( troop, cost );
        slots.push_back( { { "slot", slot },
                           { "occupied", troop.isValid() },
                           { "count", troop.GetCount() },
                           { "monster_id", troop.isValid() ? Json( troop.GetID() ) : Json( nullptr ) },
                           { "upgrade_monster_id", upgradable ? Json( troop.GetUpgrade().GetID() ) : Json( nullptr ) },
                           { "upgrade_cost", priced ? funds( cost ) : Json( nullptr ) },
                           { "can_upgrade", entity.army->canUpgradeTroop( troop ) },
                           { "can_dismiss", troop.isValid() && !entity.army->SaveLastTroop() } } );
    }
    const Castle * castle = entity.army->inCastle();
    const auto color = entity.hero != nullptr ? entity.hero->GetColor() : entity.castle->GetColor();
    return { { "kind", params["kind"] },
             { "id", params["id"] },
             { "owner", static_cast<int>( color ) },
             { "perspective", "omniscient" },
             { "castle_id", castle != nullptr ? Json( castle->GetIndex() ) : Json( nullptr ) },
             { "slots", slots } };
}

nlohmann::json fheroes2::pythonEnvEndMeeting( nlohmann::json & meeting )
{
    if ( meeting.is_null() ) {
        return nullptr;
    }
    Json scouted = Json::array();
    for ( const bool first : { true, false } ) {
        Heroes * hero = world.GetHeroes( meeting[first ? "hero_id" : "other_hero_id"].get<int>() );
        if ( hero == nullptr || !hero->isActive() || hero->GetIndex() != meeting[first ? "from" : "to"].get<int>() ) {
            throw PythonEnvError( "illegal_action", "The active meeting no longer matches the heroes' positions." );
        }
        const int32_t previousBonus = meeting[first ? "initial_scout_bonus" : "other_initial_scout_bonus"].get<int32_t>();
        if ( hero->GetBagArtifacts().getTotalArtifactEffectValue( ArtifactBonusType::AREA_REVEAL_DISTANCE ) > previousBonus ) {
            hero->Scout( hero->GetIndex() );
            scouted.push_back( hero->GetID() );
        }
    }
    Json result = { { "type", "heroes_meeting_ended" }, { "hero_id", meeting["hero_id"] }, { "other_hero_id", meeting["other_hero_id"] }, { "scouted_heroes", scouted } };
    meeting = nullptr;
    return result;
}

nlohmann::json fheroes2::pythonEnvArmyAction( const std::string & action, const nlohmann::json & params, const int playerId, nlohmann::json & meeting,
                                              const bool validateOnly )
{
    if ( action == "hero.dismiss" || action == "hero.buy_spell_book" ) {
        if ( params.size() != 1 ) {
            throw PythonEnvError( "invalid_request", "This hero operation requires only hero_id." );
        }
        Heroes & hero = ownedHero( identifier( params, "hero_id" ), playerId );
        if ( action == "hero.dismiss" ) {
            if ( !hero.canDismissVoluntarily() ) {
                throw PythonEnvError( "illegal_action", "This hero cannot be dismissed: leave the castle and respect scenario restrictions." );
            }
            const int index = hero.GetIndex();
            if ( validateOnly )
                return Json::object();
            hero.Dismiss( 0 );
            world.resetPathfinder();
            return { { "type", "hero_dismissed" }, { "hero_id", hero.GetID() }, { "from", index } };
        }
        const Castle * castle = hero.inCastle();
        if ( castle == nullptr || static_cast<int>( castle->GetColor() ) != playerId || world.GetHero( *castle ) != &hero ) {
            throw PythonEnvError( "illegal_action", "The hero must occupy an owned castle's visitor slot to buy a spell book." );
        }
        if ( validateOnly ) {
            if ( !hero.canPurchaseSpellBook( *castle ) )
                throw PythonEnvError( "illegal_action", "The hero cannot purchase a spell book." );
            return Json::object();
        }
        if ( !hero.purchaseSpellBook( *castle ) ) {
            throw PythonEnvError( "illegal_action", "Buying a spell book requires a mage guild, enough funds, a free artifact slot and no existing spell book." );
        }
        return { { "type", "spell_book_bought" },
                 { "hero_id", hero.GetID() },
                 { "castle_id", castle->GetIndex() },
                 { "cost", funds( PaymentConditions::BuySpellBook() ) } };
    }
    if ( action == "army.upgrade" || action == "army.dismiss" ) {
        if ( params.size() != 1 || !params.contains( "source" ) ) {
            throw PythonEnvError( "invalid_request", "This army operation requires only a source endpoint." );
        }
        const auto source = endpoint( params["source"], playerId );
        const int monster = source.troop->GetID();
        const uint32_t count = source.troop->GetCount();
        if ( action == "army.dismiss" ) {
            if ( validateOnly ) {
                if ( !source.troop->isValid() || source.army->SaveLastTroop() )
                    throw PythonEnvError( "illegal_action", "The stack cannot be dismissed." );
                return Json::object();
            }
            if ( !source.army->dismissTroop( *source.troop ) ) {
                throw PythonEnvError( "illegal_action", "Dismissal requires a nonempty slot and cannot remove the hero's last stack." );
            }
            world.resetPathfinder();
            return { { "type", "army_dismissed" }, { "source", params["source"] }, { "monster_id", monster }, { "count", count } };
        }
        Funds cost;
        if ( validateOnly ) {
            if ( !source.army->canUpgradeTroop( *source.troop ) )
                throw PythonEnvError( "illegal_action", "The stack cannot be upgraded." );
            return Json::object();
        }
        if ( !Army::getTroopUpgradeCost( *source.troop, cost ) || !source.army->upgradeTroop( *source.troop ) ) {
            throw PythonEnvError( "illegal_action", "Upgrade requires an upgradable stack, the matching upgraded castle dwelling and enough funds for the whole stack." );
        }
        world.resetPathfinder();
        return { { "type", "army_upgraded" }, { "source", params["source"] }, { "from_monster_id", monster }, { "monster_id", source.troop->GetID() },
                 { "count", count },          { "cost", funds( cost ) } };
    }
    if ( action == "hero.end_meeting" ) {
        if ( !params.empty() ) {
            throw PythonEnvError( "invalid_request", "hero.end_meeting requires empty params." );
        }
        if ( meeting.is_null() ) {
            throw PythonEnvError( "illegal_action", "There is no active meeting to end." );
        }
        if ( validateOnly )
            return Json::object();
        return pythonEnvEndMeeting( meeting );
    }
    if ( action == "artifact.transfer" || action == "artifact.swap" ) {
        return artifactAction( action, params, playerId, meeting, validateOnly );
    }
    if ( action == "hero.meet" ) {
        if ( params.size() != 2 ) {
            throw PythonEnvError( "invalid_request", "hero.meet requires hero_id and other_hero_id." );
        }
        Heroes & hero = ownedHero( identifier( params, "hero_id" ), playerId );
        Heroes & other = ownedHero( identifier( params, "other_hero_id" ), playerId );
        if ( &hero == &other || inMeeting( hero, other, meeting ) ) {
            throw PythonEnvError( "illegal_action", "Select two different heroes that are not already in this meeting." );
        }
        if ( hero.isShipMaster() || other.isShipMaster() ) {
            throw PythonEnvError( "unsupported_action", "External meetings currently support land heroes only." );
        }
        if ( std::abs( hero.GetCenter().x - other.GetCenter().x ) > 1 || std::abs( hero.GetCenter().y - other.GetCenter().y ) > 1 ) {
            throw PythonEnvError( "illegal_action", "The heroes must occupy adjacent tiles." );
        }
        const auto path = world.getPath( hero, other.GetIndex() );
        if ( path.size() != 1 || path.back().GetIndex() != other.GetIndex() || path.front().GetPenalty() > hero.GetMovePoints() ) {
            throw PythonEnvError( "illegal_action", "The heroes must be adjacent through a native passable route and the initiating hero must afford the meeting." );
        }
        const int from = hero.GetIndex();
        if ( validateOnly )
            return Json::object();
        const uint32_t movement = hero.GetMovePoints();
        pythonEnvEndMeeting( meeting );
        hero.GetPath().setPath( path );
        hero.SetMove( true );
        size_t remaining = path.size() + 1;
        while ( hero.isActive() && hero.isMoveEnabled() ) {
            if ( remaining-- == 0 ) {
                throw PythonEnvError( "engine_error", "The native meeting movement did not complete." );
            }
            hero.Move( true );
        }
        hero.SetMove( false );
        hero.ResetAction();
        if ( hero.GetIndex() != from || world.GetHeroes( other.GetCenter() ) != &other ) {
            throw PythonEnvError( "engine_error", "The native meeting changed an unexpected hero position." );
        }
        meeting = { { "hero_id", hero.GetID() },
                    { "other_hero_id", other.GetID() },
                    { "from", from },
                    { "to", other.GetIndex() },
                    { "initial_scout_bonus", hero.GetBagArtifacts().getTotalArtifactEffectValue( ArtifactBonusType::AREA_REVEAL_DISTANCE ) },
                    { "other_initial_scout_bonus", other.GetBagArtifacts().getTotalArtifactEffectValue( ArtifactBonusType::AREA_REVEAL_DISTANCE ) } };
        return { { "type", "heroes_met" }, { "hero_id", hero.GetID() }, { "other_hero_id", other.GetID() }, { "movement_spent", movement - hero.GetMovePoints() } };
    }
    if ( params.size() != ( action == "army.transfer" ? 3u : 2u ) || !params.contains( "source" ) || !params.contains( "target" ) ) {
        throw PythonEnvError( "invalid_request", "Use source and target army endpoints; army.transfer also requires count." );
    }
    const auto source = endpoint( params["source"], playerId );
    const auto target = endpoint( params["target"], playerId );
    checkAccess( source, target, meeting );
    if ( source.troop == target.troop ) {
        throw PythonEnvError( "illegal_action", "Source and target must be different army slots." );
    }
    if ( action == "army.transfer" ) {
        const uint32_t count = identifier( params, "count" );
        if ( count == 0 ) {
            throw PythonEnvError( "invalid_request", "count must be positive." );
        }
        const int monster = source.troop->GetID();
        if ( validateOnly ) {
            Troop a = *source.troop;
            Troop b = *target.troop;
            if ( !Army::TransferTroops( a, b, count, source.army != target.army && source.army->SaveLastTroop() ) ) {
                throw PythonEnvError( "illegal_action", "The exact transfer is not allowed." );
            }
            return Json::object();
        }
        if ( !Army::TransferTroops( *source.troop, *target.troop, count, source.army != target.army && source.army->SaveLastTroop() ) ) {
            throw PythonEnvError( "illegal_action",
                                  "The exact transfer requires enough source units, a compatible target, no count overflow and preservation of the hero's last unit." );
        }
        world.resetPathfinder();
        return { { "type", "army_transferred" }, { "source", params["source"] }, { "target", params["target"] }, { "monster_id", monster }, { "count", count } };
    }
    if ( ( !source.troop->isValid() && !target.troop->isValid() )
         || ( source.army != target.army
              && ( ( source.army->SaveLastTroop() && !target.troop->isValid() ) || ( target.army->SaveLastTroop() && !source.troop->isValid() ) ) ) ) {
        throw PythonEnvError( "illegal_action", "A swap must change a stack and cannot empty a hero's army." );
    }
    if ( validateOnly )
        return Json::object();
    Army::SwapTroops( *source.troop, *target.troop );
    world.resetPathfinder();
    return { { "type", "army_swapped" }, { "source", params["source"] }, { "target", params["target"] } };
}

#endif
