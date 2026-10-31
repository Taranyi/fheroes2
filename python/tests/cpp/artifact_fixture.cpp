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

// Explicit test-data builder. Never linked into the game or exposed by the production Python protocol.
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <set>

#include <SDL_main.h>

#include "army.h"
#include "artifact.h"
#include "castle.h"
#include "core.h"
#include "direction.h"
#include "game_io.h"
#include "heroes.h"
#include "kingdom.h"
#include "map_object_info.h"
#include "maps_fileinfo.h"
#include "maps_tiles.h"
#include "maps_tiles_helper.h"
#include "monster.h"
#include "players.h"
#include "python_env_world.h"
#include "resource.h"
#include "settings.h"
#include "skill.h"
#include "spell.h"
#include "world.h"

int main( int argc, char ** argv )
{
    if ( argc != 3 && !( argc == 4 && std::string( argv[3] ) == "--gym-only" ) ) {
        std::cerr << "Usage: fheroes2_artifact_fixture BASE_SAVE OUTPUT_DIRECTORY [--gym-only]\n";
        return EXIT_FAILURE;
    }
    try {
        const auto input = std::filesystem::absolute( std::filesystem::u8path( argv[1] ) );
        const auto output = std::filesystem::absolute( std::filesystem::u8path( argv[2] ) );
        std::filesystem::create_directories( output );
        for ( const char * name :
              { "artifacts-day1.sav",           "artifacts-full-day1.sav",     "heroes-full-day1.sav",      "heroes-protected-day1.sav", "choices-chest-day1.sav",
                "choices-join-day1.sav",        "choices-pursue-day1.sav",     "choices-recruit-day1.sav",  "choices-spells-day1.sav",   "choices-paid-join-day1.sav",
                "battles-melee-day1.sav",       "battles-ranged-day1.sav",     "battles-heroes-day1.sav",   "battles-loss-day1.sav",     "battles-boss-day1.sav",
                "controllers-ai-boss-day1.sav", "battles-siege-day1.sav",      "gym-victory-day1.sav",      "navigation-coast-day1.sav", "navigation-shipyard-day1.sav",
                "navigation-poor-day1.sav",     "navigation-blocked-day1.sav", "navigation-battle-day1.sav" } ) {
            const auto file = output / name;
            if ( std::filesystem::exists( file ) && std::filesystem::equivalent( input, file ) ) {
                throw std::runtime_error( "The output must not overwrite the input save." );
            }
        }
        const System::ScopedHeadlessMode headless;
        const System::CoreInitializer core( std::set<System::SystemInitializationComponent>{} );
        fheroes2::PythonEnvWorld session( argv[0] );
        session.loadSave( input.u8string() );
        const auto saveGymVictory = [&]() {
            session.loadSave( input.u8string() );
            auto & info = Settings::Get().getCurrentMapInfo();
            info.victoryConditionType = Maps::FileInfo::VICTORY_COLLECT_ENOUGH_GOLD;
            info.victoryConditionParams = { 10, 0 };
            info.compAlsoWins = false;
            world.GetKingdom( PlayerColor::BLUE ).AddFundsResource( Funds( Resource::GOLD, 2500 ) );
            if ( !Game::Save( ( output / "gym-victory-day1.sav" ).string() ) ) {
                throw std::runtime_error( "Could not save the native Gym victory fixture." );
            }
        };
        if ( argc == 4 ) {
            saveGymVictory();
            return EXIT_SUCCESS;
        }
        Heroes * roxana = world.GetHeroes( 52 );
        Heroes * zom = world.GetHeroes( 46 );
        if ( roxana == nullptr || zom == nullptr || roxana->GetIndex() != 896 || static_cast<int>( roxana->GetColor() ) != 1 ) {
            throw std::runtime_error( "Expected the recorded The Other Side day-1 fixture." );
        }
        auto & a = roxana->GetBagArtifacts();
        auto & b = zom->GetBagArtifacts();
        a.at( 1 ) = Artifact::TELESCOPE;
        a.at( 2 ) = Artifact::DRAGON_SWORD;
        a.at( 3 ) = Artifact::SPELL_SCROLL;
        a.at( 3 ).SetSpell( Spell::LIGHTNINGBOLT );
        a.at( 4 ) = Artifact::BREASTPLATE_ANDURAN;
        b.at( 1 ) = Artifact::MEDAL_COURAGE;
        b.at( 2 ) = Artifact::HELMET_ANDURAN;
        b.at( 3 ) = Artifact::SWORD_ANDURAN;
        if ( !Game::Save( ( output / "artifacts-day1.sav" ).string() ) ) {
            throw std::runtime_error( "Could not save the native artifact fixture." );
        }
        for ( size_t slot = 1; slot < b.size(); ++slot ) {
            b[slot] = Artifact::MEDAL_COURAGE;
        }
        if ( !Game::Save( ( output / "artifacts-full-day1.sav" ).string() ) ) {
            throw std::runtime_error( "Could not save the native full-bag fixture." );
        }
        Heroes * jojosh = world.GetHeroes( 12 );
        if ( jojosh == nullptr || jojosh->HaveSpellBook() ) {
            throw std::runtime_error( "Expected the offered bookless Jojosh." );
        }
        for ( Artifact & artifact : jojosh->GetBagArtifacts() ) {
            artifact = Artifact::MEDAL_COURAGE;
        }
        if ( !Game::Save( ( output / "heroes-full-day1.sav" ).string() ) ) {
            throw std::runtime_error( "Could not save the native bookless full-bag fixture." );
        }
        roxana->SetModes( Heroes::NOTDISMISS );
        if ( !Game::Save( ( output / "heroes-protected-day1.sav" ).string() ) ) {
            throw std::runtime_error( "Could not save the native dismissal-protection fixture." );
        }
        const auto load = [&]() {
            session.loadSave( input.u8string() );
            return world.GetHeroes( 52 );
        };
        const auto save = [&]( const char * name ) {
            if ( !Game::Save( ( output / name ).string() ) ) {
                throw std::runtime_error( "Could not save native choice fixture." );
            }
        };
        const auto place = []( const MP2::MapObjectType type ) -> Maps::Tile & {
            auto & tile = world.getTile( 932 );
            if ( tile.getMainObjectType() != MP2::OBJ_NONE || tile.isWater() ) {
                throw std::runtime_error( "Expected an empty land tile below Timberhill." );
            }
            for ( const Maps::ObjectGroup group : { Maps::ObjectGroup::ADVENTURE_TREASURES, Maps::ObjectGroup::ADVENTURE_DWELLINGS } ) {
                for ( const auto & info : Maps::getObjectsByGroup( group ) ) {
                    if ( info.objectType == type && Maps::setObjectOnTile( tile, info, true ) ) {
                        return tile;
                    }
                }
            }
            throw std::runtime_error( "Could not place native adventure object." );
        };
        // Separate synthetic harbor scenario; no original save or map asset is modified.
        load();
        for ( int y = 26; y <= 29; ++y ) {
            for ( int x = 31; x <= 34; ++x ) {
                auto & tile = world.getTile( y * world.w() + x );
                if ( tile.getMainObjectType() == MP2::OBJ_HERO || tile.getMainObjectType() == MP2::OBJ_CASTLE )
                    throw std::runtime_error( "Navigation fixture must not replace heroes or castles." );
                if ( tile.getMainObjectType() != MP2::OBJ_NONE )
                    Maps::removeMainObjectFromTile( tile );
                tile.resetMainObjectPart();
                tile.setMainObjectType( MP2::OBJ_NONE );
                tile.setTerrain( 0, 0 );
            }
        }
        world.updatePassabilities();
        Castle * harbor = world.getCastleEntrance( { 32, 24 } );
        if ( harbor == nullptr || !harbor->HasSeaAccess() )
            throw std::runtime_error( "Expected a coastal test castle." );
        harbor->GetKingdom().AddFundsResource( Funds( Resource::GOLD, 20000 ) + Funds( Resource::WOOD, 40 ) );
        save( "navigation-coast-day1.sav" );
        harbor->SetModes( Castle::ALLOW_TO_BUILD_TODAY );
        if ( !harbor->BuyBuilding( BUILD_SHIPYARD ) )
            throw std::runtime_error( "Could not prepare the native test shipyard." );
        save( "navigation-shipyard-day1.sav" );
        if ( !harbor->BuyBoat() )
            throw std::runtime_error( "Could not prepare a blocked native harbor." );
        save( "navigation-blocked-day1.sav" );
        Heroes * sailor = world.GetHeroes( 52 );
        sailor->GetArmy().Reset();
        sailor->GetArmy().JoinTroop( Monster::BONE_DRAGON, 100, false );
        sailor->Move2Dest( 968 );
        auto & embarkedTile = world.getTile( 968 );
        embarkedTile.resetMainObjectPart();
        embarkedTile.updateObjectType();
        sailor->setObjectTypeUnderHero( embarkedTile.getMainObjectType( true ) );
        embarkedTile.setMainObjectType( MP2::OBJ_HERO );
        embarkedTile.resetBoatOwnerColor();
        sailor->SetShipMaster( true );
        Heroes * opponent = world.GetHeroes( 42 );
        opponent->Move2Dest( 1040 );
        opponent->SetShipMaster( true );
        opponent->GetArmy().Reset();
        opponent->GetArmy().JoinTroop( Monster::PEASANT, 30, false );
        save( "navigation-battle-day1.sav" );
        session.loadSave( ( output / "navigation-shipyard-day1.sav" ).u8string() );
        world.GetKingdom( PlayerColor::BLUE ).OddFundsResource( world.GetKingdom( PlayerColor::BLUE ).GetFunds() );
        save( "navigation-poor-day1.sav" );
        load();
        auto & chest = place( MP2::OBJ_TREASURE_CHEST );
        chest.metadata() = { Artifact::UNKNOWN, 2500, 0 };
        save( "choices-chest-day1.sav" );

        for ( const bool joins : { true, false } ) {
            Heroes * hero = load();
            hero->GetArmy().Reset();
            hero->GetArmy().JoinTroop( Monster::BLACK_DRAGON, 100, false );
            Maps::Tile & tile = world.getTile( 932 );
            Maps::setMonsterOnTile( tile, Monster::PEASANT, 5 );
            Maps::setMonsterOnTileJoinCondition( tile, joins ? Monster::JOIN_CONDITION_FREE : Monster::JOIN_CONDITION_SKIP );
            save( joins ? "choices-join-day1.sav" : "choices-pursue-day1.sav" );
        }
        load();
        auto & lamp = place( MP2::OBJ_GENIE_LAMP );
        Maps::setMonsterCountOnTile( lamp, 4 );
        save( "choices-recruit-day1.sav" );

        Heroes * diplomat = load();
        diplomat->GetArmy().Reset();
        diplomat->GetArmy().JoinTroop( Monster::BLACK_DRAGON, 100, false );
        diplomat->LearnSkill( Skill::Secondary( Skill::Secondary::DIPLOMACY, Skill::Level::BASIC ) );
        Maps::setMonsterOnTile( world.getTile( 932 ), Monster::PEASANT, 5 );
        Maps::setMonsterOnTileJoinCondition( world.getTile( 932 ), Monster::JOIN_CONDITION_MONEY );
        save( "choices-paid-join-day1.sav" );

        Heroes * hero = load();
        hero->AppendSpellToBook( Spell::IDENTIFYHERO, true );
        hero->AppendSpellToBook( Spell::VISIONS, true );
        Maps::setMonsterOnTile( world.getTile( 968 ), Monster::PEASANT, 5 );
        save( "choices-spells-day1.sav" );
        for ( const int profile : { 0, 1, 2, 3, 4 } ) {
            Heroes * fighter = load();
            fighter->GetArmy().Reset();
            fighter->GetArmy().JoinTroop( profile == 1   ? Monster::ARCHER
                                          : profile == 3 ? Monster::PEASANT
                                          : profile == 4 ? Monster::BONE_DRAGON
                                                         : Monster::SKELETON,
                                          profile == 3   ? 1
                                          : profile == 4 ? 100
                                                         : 40,
                                          false );
            fighter->AppendSpellToBook( Spell::ARROW, true );
            fighter->AppendSpellToBook( Spell::HASTE, true );
            fighter->AppendSpellToBook( Spell::LIGHTNINGBOLT, true );
            fighter->SetSpellPoints( 30 );
            if ( profile == 2 ) {
                Heroes * opponent = world.GetHeroes( 42 );
                opponent->Move2Dest( 932 );
                opponent->GetArmy().Reset();
                opponent->GetArmy().JoinTroop( Monster::PEASANT, 30, false );
                save( "battles-heroes-day1.sav" );
                continue;
            }
            auto & tile = world.getTile( 932 );
            Maps::setMonsterOnTile( tile,
                                    profile == 3   ? Monster::BLACK_DRAGON
                                    : profile == 4 ? Monster::RED_DRAGON
                                                   : Monster::PEASANT,
                                    profile == 3   ? 5
                                    : profile == 4 ? 10
                                                   : 40 );
            Maps::setMonsterOnTileJoinCondition( tile, Monster::JOIN_CONDITION_SKIP );
            save( profile == 0 ? "battles-melee-day1.sav" : profile == 1 ? "battles-ranged-day1.sav" : profile == 3 ? "battles-loss-day1.sav" : "battles-boss-day1.sav" );
            if ( profile == 4 ) {
                // Explicit test scenario: every participant has native AI rules, including the Python-controlled hero.
                for ( Player * player : Settings::Get().GetPlayers() ) {
                    player->SetControl( CONTROL_AI );
                }
                Settings::Get().GetPlayers().SetStartGame();
                Settings::Get().SetCurrentColor( PlayerColor::BLUE );
                save( "controllers-ai-boss-day1.sav" );
            }
        }
        Heroes * attacker = load();
        attacker->Move2Dest( 903 );
        attacker->GetArmy().Reset();
        attacker->GetArmy().JoinTroop( Monster::BONE_DRAGON, 100, false );
        save( "battles-siege-day1.sav" );
        saveGymVictory();
        std::cout << "Native environment fixtures saved in " << output.string() << '\n';
        return EXIT_SUCCESS;
    }
    catch ( const std::exception & error ) {
        std::cerr << error.what() << '\n';
        return EXIT_FAILURE;
    }
}
