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
#include <fstream>
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
#include "maps_objects.h"
#include "maps_tiles.h"
#include "maps_tiles_helper.h"
#include "monster.h"
#include "players.h"
#include "python_env_profile.h"
#include "python_env_world.h"
#include "resource.h"
#include "settings.h"
#include "skill.h"
#include "spell.h"
#include "world.h"

int main( int argc, char ** argv )
{
    if ( argc != 3
         && !( argc == 4 && ( std::string( argv[3] ) == "--gym-only" || std::string( argv[3] ) == "--expansion-only" || std::string( argv[3] ) == "--special-only" ) ) ) {
        std::cerr << "Usage: fheroes2_artifact_fixture BASE_SAVE OUTPUT_DIRECTORY [--gym-only|--expansion-only|--special-only]\n";
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
        if ( argc == 4 && ( std::string( argv[3] ) == "--expansion-only" || std::string( argv[3] ) == "--special-only" ) ) {
            if ( input.parent_path() == output && ( input.filename().string().find( "expansion-" ) == 0 || input.filename().string().find( "special-" ) == 0 ) )
                throw std::runtime_error( "Generated outputs must not overwrite the input." );
            const bool special = std::string( argv[3] ) == "--special-only";
            using Json = nlohmann::json;
            Json manifest = Json::array();
            constexpr int target = 18 * 36 + 15;
            const auto prepare = [&]( const bool water ) {
                session.loadSave( input.u8string() );
                if ( world.w() != 36 || world.h() != 36 )
                    throw std::runtime_error( "Expansion fixtures require the recorded 36x36 base map." );
                for ( int y = 10; y <= 21; ++y ) {
                    for ( int x = 10; x <= ( special ? 30 : 21 ); ++x ) {
                        auto & tile = world.getTile( y * 36 + x );
                        if ( tile.getMainObjectType() == MP2::OBJ_HERO || tile.getMainObjectType() == MP2::OBJ_CASTLE )
                            throw std::runtime_error( "Expansion patch must not replace a hero or castle." );
                        if ( tile.getMainObjectType() != MP2::OBJ_NONE )
                            Maps::removeMainObjectFromTile( tile );
                        tile.resetMainObjectPart();
                        tile.getGroundObjectParts().clear();
                        tile.setMainObjectType( MP2::OBJ_NONE );
                        tile.setTerrain( water ? 0 : 30, 0 );
                    }
                }
                Heroes * hero = world.GetHeroes( 52 );
                hero->Move2Dest( 19 * 36 + 15 );
                hero->SetShipMaster( water );
                hero->Scout( hero->GetIndex() );
                hero->GetArmy().Reset();
                hero->GetArmy().JoinTroop( Monster::BONE_DRAGON, 100, false );
                hero->SetSpellPoints( 1000 );
                for ( const int id : fheroes2::pythonEnvAdventureSpells() )
                    hero->AppendSpellToBook( id, true );
                hero->GetKingdom().AddFundsResource( Funds( Resource::GOLD, 20000 ) + Funds( Resource::GEMS, 100 ) );
                world.updatePassabilities();
                return hero;
            };
            const auto save = [&]( const std::string & name ) {
                if ( !Game::Save( ( output / name ).string() ) )
                    throw std::runtime_error( "Could not save an expansion fixture." );
            };
            for ( const auto type : fheroes2::pythonEnvAdventureObjects() ) {
                const bool specialType = type == MP2::OBJ_SPHINX || type == MP2::OBJ_TRADING_POST || type == MP2::OBJ_EVENT || type == MP2::OBJ_STONE_LITHS
                                         || type == MP2::OBJ_WHIRLPOOL || type == MP2::OBJ_HUT_OF_MAGI || type == MP2::OBJ_MAGELLANS_MAPS || type == MP2::OBJ_ORACLE;
                if ( special != specialType )
                    continue;
                if ( type == MP2::OBJ_MONSTER || type == MP2::OBJ_JAIL || type == MP2::OBJ_SIGN || type == MP2::OBJ_BOTTLE )
                    continue; // Existing monster fixtures; jail/sign need authored map data.
                const bool water = type == MP2::OBJ_WHIRLPOOL || type == MP2::OBJ_MAGELLANS_MAPS || type == MP2::OBJ_SEA_CHEST || type == MP2::OBJ_FLOTSAM
                                   || type == MP2::OBJ_SHIPWRECK_SURVIVOR || type == MP2::OBJ_SHIPWRECK || type == MP2::OBJ_DERELICT_SHIP || type == MP2::OBJ_BARREL
                                   || type == MP2::OBJ_BOTTLE || type == MP2::OBJ_BUOY || type == MP2::OBJ_SIRENS || type == MP2::OBJ_MERMAID;
                Heroes * visitor = prepare( water );
                if ( type == MP2::OBJ_WHIRLPOOL )
                    visitor->Move2Dest( 23 * 36 + 15 );
                if ( type == MP2::OBJ_STONE_LITHS || type == MP2::OBJ_WHIRLPOOL ) {
                    for ( int i = 0; i < world.w() * world.h(); ++i ) {
                        if ( world.getTile( i ).getMainObjectType() == type )
                            Maps::removeMainObjectFromTile( world.getTile( i ) );
                    }
                }
                bool placed = false;
                for ( int group = static_cast<int>( Maps::ObjectGroup::ADVENTURE_ARTIFACTS ); group < static_cast<int>( Maps::ObjectGroup::GROUP_COUNT ) && !placed;
                      ++group ) {
                    for ( const auto & info : Maps::getObjectsByGroup( static_cast<Maps::ObjectGroup>( group ) ) ) {
                        if ( info.objectType == type && Maps::setObjectOnTile( world.getTile( target ), info, true ) ) {
                            if ( type == MP2::OBJ_STONE_LITHS || type == MP2::OBJ_WHIRLPOOL ) {
                                if ( !Maps::setObjectOnTile( world.getTile( 18 * 36 + 26 ), info, true ) )
                                    throw std::runtime_error( "Could not place the second native portal." );
                            }
                            placed = true;
                            break;
                        }
                    }
                }
                if ( !placed )
                    throw std::runtime_error( "No native object template for " + std::to_string( type ) );
                auto & tile = world.getTile( target );
                Maps::setInitialObjectInfo( tile );
                if ( type == MP2::OBJ_ARTIFACT )
                    tile.metadata() = { Artifact::TELESCOPE, 0, static_cast<uint32_t>( Maps::ArtifactCaptureCondition::PAY_2000_GOLD ) };
                if ( type == MP2::OBJ_TREE_OF_KNOWLEDGE )
                    tile.metadata() = { Resource::GOLD, 2000, 0 };
                if ( type == MP2::OBJ_SHRINE_FIRST_CIRCLE )
                    Maps::setSpellOnTile( tile, Spell::BLESS );
                if ( type == MP2::OBJ_SHRINE_SECOND_CIRCLE )
                    Maps::setSpellOnTile( tile, Spell::BLIND );
                if ( type == MP2::OBJ_SHRINE_THIRD_CIRCLE )
                    Maps::setSpellOnTile( tile, Spell::FIREBALL );
                if ( type == MP2::OBJ_WITCHS_HUT )
                    tile.metadata()[0] = Skill::Secondary::ARCHERY;
                if ( type == MP2::OBJ_MINE || type == MP2::OBJ_SAWMILL || type == MP2::OBJ_ALCHEMIST_LAB || type == MP2::OBJ_LIGHTHOUSE )
                    world.CaptureObject( target, PlayerColor::NONE );
                int destination = target;
                if ( type == MP2::OBJ_SPHINX ) {
                    auto riddle = std::make_unique<MapSphinx>();
                    riddle->setUIDAndIndex( target );
                    riddle->riddle = "What walks on four legs in the morning, two at noon and three in the evening?";
                    riddle->answers = { "human", "man" };
                    riddle->isTruncatedAnswer = false;
                    riddle->resources = Funds( Resource::GOLD, 1234 );
                    riddle->artifact = Artifact::TELESCOPE;
                    riddle->validate();
                    world.addMapObject( std::move( riddle ) );
                }
                if ( type == MP2::OBJ_EVENT ) {
                    auto event = std::make_unique<MapEvent>();
                    event->setUIDAndIndex( target );
                    event->message = "Native map event: resources, artifact and experience.";
                    event->colors = Color::allPlayerColors();
                    event->isComputerPlayerAllowed = true;
                    event->isSingleTimeEvent = true;
                    event->resources = Funds( Resource::GOLD, 777 );
                    event->artifact = Artifact::TELESCOPE;
                    event->experience = 1500;
                    event->secondarySkill = Skill::Secondary( Skill::Secondary::SCOUTING, Skill::Level::BASIC );
                    world.addMapObject( std::move( event ) );
                }
                if ( type == MP2::OBJ_HUT_OF_MAGI ) {
                    bool eye = false;
                    for ( const auto & info : Maps::getObjectsByGroup( Maps::ObjectGroup::ADVENTURE_MISCELLANEOUS ) ) {
                        if ( info.objectType == MP2::OBJ_EYE_OF_MAGI && Maps::setObjectOnTile( world.getTile( 18 * 36 + 26 ), info, true ) ) {
                            eye = true;
                            break;
                        }
                    }
                    if ( !eye )
                        throw std::runtime_error( "Could not place Eye of Magi." );
                }
                if ( type == MP2::OBJ_WHIRLPOOL ) {
                    for ( int i = 10 * 36 + 10; i < 22 * 36; ++i ) {
                        if ( i % 36 >= 10 && i % 36 <= 20 && world.getTile( i ).getMainObjectType() == type )
                            destination = i;
                    }
                    visitor->Move2Dest( destination + 36 );
                    visitor->Scout( visitor->GetIndex() );
                }
                world.updatePassabilities();
                const auto name = std::string( special ? "special-object-" : "expansion-object-" ) + std::to_string( type ) + ".sav";
                save( name );
                manifest.push_back( { { "object_id", static_cast<int>( type ) },
                                      { "name", MP2::StringObject( type ) },
                                      { "save", name },
                                      { "water", water },
                                      { "target_index", destination } } );
            }
            if ( special ) {
                for ( const auto & record : manifest ) {
                    if ( record["name"] == "Event" ) {
                        const auto original = output / record["save"].get<std::string>();
                        for ( const auto & variant : { std::string( "repeat" ), std::string( "ai-denied" ), std::string( "ai-allowed" ), std::string( "wrong-color" ) } ) {
                            session.loadSave( original.u8string() );
                            auto * event = dynamic_cast<MapEvent *>( world.GetMapObject( target ) );
                            if ( !event )
                                throw std::runtime_error( "Native map event fixture is missing." );
                            event->isSingleTimeEvent = false;
                            event->experience = 0;
                            event->artifact = Artifact::UNKNOWN;
                            event->secondarySkill = {};
                            if ( variant == "ai-denied" || variant == "ai-allowed" ) {
                                event->isComputerPlayerAllowed = variant == "ai-allowed";
                                Players::Get( PlayerColor::BLUE )->SetControl( CONTROL_AI );
                                Settings::Get().GetPlayers().SetStartGame();
                                Settings::Get().SetCurrentColor( PlayerColor::BLUE );
                            }
                            if ( variant == "wrong-color" )
                                event->colors = static_cast<PlayerColorsSet>( PlayerColor::GREEN );
                            save( "special-event-" + variant + ".sav" );
                        }
                    }
                }
                std::ofstream( output / "special-objects.json" ) << manifest.dump( 2 ) << '\n';
                std::cout << "Special native fixtures: " << manifest.size() << " objects.\n";
                return EXIT_SUCCESS;
            }
            Heroes * caster = prepare( false );
            caster->GetArmy().Reset();
            caster->GetArmy().JoinTroop( Monster::ARCHER, 100, false );
            caster->GetArmy().JoinTroop( Monster::SKELETON, 40, false );
            Heroes * opponent = world.GetHeroes( 42 );
            opponent->Move2Dest( target );
            opponent->Scout( target );
            opponent->GetArmy().Reset();
            opponent->GetArmy().JoinTroop( Monster::PEASANT, 1000, false );
            opponent->GetArmy().JoinTroop( Monster::ARCHER, 100, false );
            opponent->SetSpellPoints( 1000 );
            for ( int id = Spell::FIREBALL; id <= Spell::EARTHQUAKE; ++id ) {
                caster->AppendSpellToBook( id, true );
                opponent->AppendSpellToBook( id, true );
            }
            save( "expansion-battle.sav" );
            session.loadSave( ( output / "battles-siege-day1.sav" ).u8string() );
            world.GetHeroes( 52 )->AppendSpellToBook( Spell::EARTHQUAKE, true );
            world.GetHeroes( 52 )->SetSpellPoints( 1000 );
            save( "expansion-siege.sav" );
            session.loadSave( ( output / "navigation-blocked-day1.sav" ).u8string() );
            Heroes * summoner = world.GetHeroes( 52 );
            summoner->Move2Dest( 932 );
            summoner->AppendSpellToBook( Spell::SUMMONBOAT, true );
            summoner->SetSpellPoints( 1000 );
            Maps::removeMainObjectFromTile( world.getTile( 968 ) );
            world.getTile( 34 + 29 * 36 ).setBoat( Direction::RIGHT, PlayerColor::BLUE );
            save( "expansion-summon.sav" );
            std::ofstream( output / "expansion-objects.json" ) << manifest.dump( 2 ) << '\n';
            std::cout << "Expansion fixtures: " << manifest.size() << " objects and native spell battle.\n";
            return EXIT_SUCCESS;
        }
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
        Heroes * navalOpponent = world.GetHeroes( 42 );
        navalOpponent->Move2Dest( 1040 );
        navalOpponent->SetShipMaster( true );
        navalOpponent->GetArmy().Reset();
        navalOpponent->GetArmy().JoinTroop( Monster::PEASANT, 30, false );
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
