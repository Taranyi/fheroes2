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
#include <map>
#include <set>

#include "agg.h"
#include "ai_planner.h"
#include "army.h"
#include "artifact.h"
#include "battle.h"
#include "battle_arena.h"
#include "battle_army.h"
#include "battle_interface.h"
#include "battle_troop.h"
#include "captain.h"
#include "castle.h"
#include "game.h"
#include "game_external_interaction.h"
#include "game_over.h"
#include "ground.h"
#include "heroes.h"
#include "image.h"
#include "kingdom.h"
#include "map_format_info.h"
#include "maps_fileinfo.h"
#include "maps_tiles.h"
#include "monster.h"
#include "mp2.h"
#include "players.h"
#include "puzzle.h"
#include "python_env_battle.h"
#include "race.h"
#include "rand.h"
#include "resource.h"
#include "settings.h"
#include "skill.h"
#include "spell.h"
#include "system.h"
#include "world.h"

namespace
{
    using Json = nlohmann::json;
    struct RoundLimit
    {};
    const std::map<std::string, int> terrains{ { "grass", Maps::Ground::GRASS },         { "snow", Maps::Ground::SNOW },     { "swamp", Maps::Ground::SWAMP },
                                               { "lava", Maps::Ground::LAVA },           { "desert", Maps::Ground::DESERT }, { "dirt", Maps::Ground::DIRT },
                                               { "wasteland", Maps::Ground::WASTELAND }, { "beach", Maps::Ground::BEACH },   { "water", Maps::Ground::WATER } };
    const std::map<std::string, int> races{ { "knight", Race::KNGT },  { "barbarian", Race::BARB }, { "sorceress", Race::SORC },
                                            { "warlock", Race::WRLK }, { "wizard", Race::WZRD },    { "necromancer", Race::NECR } };

    void fields( const Json & value, const std::set<std::string> & allowed )
    {
        if ( !value.is_object() )
            throw fheroes2::PythonEnvError( "invalid_request", "Battle configuration entries must be objects." );
        for ( auto it = value.begin(); it != value.end(); ++it )
            if ( !allowed.count( it.key() ) )
                throw fheroes2::PythonEnvError( "invalid_request", "Unknown battle configuration field: " + it.key() );
    }
    int number( const Json & value, const char * key, int fallback, int low, int high )
    {
        if ( !value.contains( key ) )
            return fallback;
        if ( !value[key].is_number_integer() || value[key] < low || value[key] > high )
            throw fheroes2::PythonEnvError( "invalid_request", std::string( "Invalid battle integer: " ) + key );
        return value[key].get<int>();
    }
    bool boolean( const Json & value, const char * key, bool fallback )
    {
        if ( !value.contains( key ) )
            return fallback;
        if ( !value[key].is_boolean() )
            throw fheroes2::PythonEnvError( "invalid_request", std::string( "Expected battle boolean: " ) + key );
        return value[key].get<bool>();
    }
    std::string label( const Json & value, const char * key, const std::string & fallback, const std::set<std::string> & allowed )
    {
        if ( !value.contains( key ) )
            return fallback;
        if ( !value[key].is_string() || !allowed.count( value[key].get<std::string>() ) )
            throw fheroes2::PythonEnvError( "invalid_request", std::string( "Invalid battle option: " ) + key );
        return value[key].get<std::string>();
    }
    Json normalize( const Json & source )
    {
        fields( source, { "terrain", "attacker", "defender", "siege", "max_rounds", "capture_final_frame", "perspective_player_id" } );
        if ( !source.contains( "attacker" ) || !source.contains( "defender" ) )
            throw fheroes2::PythonEnvError( "invalid_request", "Battle requires attacker and defender configurations." );
        std::set<std::string> terrainNames;
        for ( const auto & entry : terrains )
            terrainNames.insert( entry.first );
        Json result = { { "terrain", label( source, "terrain", "grass", terrainNames ) },
                        { "max_rounds", number( source, "max_rounds", 1000, 1, 100000 ) },
                        { "capture_final_frame", boolean( source, "capture_final_frame", false ) } };
        std::set<int> heroIds;
        int firstExternal = 0;
        for ( size_t i = 0; i < 2; ++i ) {
            const char * name = i == 0 ? "attacker" : "defender";
            const auto & side = source[name];
            fields( side, { "army", "hero", "controller", "rule_profile", "gold", "formation" } );
            if ( !side.contains( "army" ) || !side["army"].is_array() || side["army"].empty() || side["army"].size() > 5 )
                throw fheroes2::PythonEnvError( "invalid_request", "Each battle army requires one to five slots." );
            Json army = Json::array();
            bool valid = false;
            for ( const auto & troop : side["army"] ) {
                if ( troop.is_null() ) {
                    army.push_back( nullptr );
                    continue;
                }
                fields( troop, { "monster_id", "count" } );
                const int monster = number( troop, "monster_id", 0, 1, Monster::WATER_ELEMENT );
                const int count = number( troop, "count", 0, 1, 100000 );
                if ( monster == 0 || count == 0 )
                    throw fheroes2::PythonEnvError( "invalid_request", "Army stacks require concrete monster_id and positive count." );
                army.push_back( { { "monster_id", monster }, { "count", count } } );
                valid = true;
            }
            if ( !valid )
                throw fheroes2::PythonEnvError( "invalid_request", "Empty battle armies are not supported." );
            const std::string controller = label( side, "controller", i == 0 ? "python" : "builtin_ai", { "python", "builtin_ai" } );
            if ( controller == "python" && firstExternal == 0 )
                firstExternal = 1 << i;
            Json hero = nullptr;
            if ( side.contains( "hero" ) && !side["hero"].is_null() ) {
                const auto & h = side["hero"];
                fields( h, { "id", "attack", "defense", "power", "knowledge", "spell_points", "spell_book", "spells", "skills", "artifacts" } );
                const int id = number( h, "id", static_cast<int>( i ) + 1, 1, Heroes::DEBUG_HERO - 1 );
                if ( !heroIds.insert( id ).second )
                    throw fheroes2::PythonEnvError( "invalid_request", "Battle heroes must have distinct IDs." );
                hero = { { "id", id },
                         { "attack", number( h, "attack", 1, 0, 99 ) },
                         { "defense", number( h, "defense", 1, 0, 99 ) },
                         { "power", number( h, "power", 1, 1, 99 ) },
                         { "knowledge", number( h, "knowledge", 1, 1, 99 ) },
                         { "spell_points", number( h, "spell_points", 0, 0, 100000 ) },
                         { "spell_book", boolean( h, "spell_book", false ) },
                         { "spells", Json::array() },
                         { "skills", Json::array() },
                         { "artifacts", Json::array() } };
                if ( h.contains( "spells" ) ) {
                    if ( !h["spells"].is_array() || h["spells"].size() > 48 )
                        throw fheroes2::PythonEnvError( "invalid_request", "Battle spells must be an array of combat IDs 1..48." );
                    std::set<int> seen;
                    for ( const auto & value : h["spells"] ) {
                        const int spell = number( Json{ { "id", value } }, "id", 0, 1, 48 );
                        if ( !seen.insert( spell ).second )
                            throw fheroes2::PythonEnvError( "invalid_request", "Duplicate combat spell." );
                        hero["spells"].push_back( spell );
                    }
                    if ( !hero["spells"].empty() )
                        hero["spell_book"] = true;
                }
                if ( h.contains( "skills" ) ) {
                    if ( !h["skills"].is_array() || h["skills"].size() > 8 )
                        throw fheroes2::PythonEnvError( "invalid_request", "At most eight secondary skills may be configured." );
                    std::set<int> seen;
                    for ( const auto & skill : h["skills"] ) {
                        fields( skill, { "id", "level" } );
                        int skillId = number( skill, "id", 0, 1, 14 ), level = number( skill, "level", 0, 1, 3 );
                        if ( !skillId || !level || !seen.insert( skillId ).second )
                            throw fheroes2::PythonEnvError( "invalid_request", "Invalid or duplicate secondary skill." );
                        hero["skills"].push_back( { { "id", skillId }, { "level", level } } );
                    }
                }
                if ( h.contains( "artifacts" ) ) {
                    if ( !h["artifacts"].is_array() || h["artifacts"].size() > 13 )
                        throw fheroes2::PythonEnvError( "invalid_request", "At most thirteen artifacts may be configured." );
                    for ( const auto & entry : h["artifacts"] ) {
                        fields( entry, { "id", "spell_id" } );
                        const int artifactId = number( entry, "id", 0, 1, Artifact::ARTIFACT_COUNT - 1 );
                        if ( !Artifact( artifactId ).isValid() || artifactId == Artifact::MAGIC_BOOK )
                            throw fheroes2::PythonEnvError( "invalid_request", "Use a concrete artifact and the separate spell_book flag." );
                        Json artifact = { { "id", artifactId } };
                        if ( artifactId == Artifact::SPELL_SCROLL ) {
                            const int spell = number( entry, "spell_id", 0, 1, 48 );
                            if ( !spell )
                                throw fheroes2::PythonEnvError( "invalid_request", "A scroll requires a combat spell_id." );
                            artifact["spell_id"] = spell;
                        }
                        else if ( entry.contains( "spell_id" ) )
                            throw fheroes2::PythonEnvError( "invalid_request", "Only spell scrolls accept spell_id." );
                        hero["artifacts"].push_back( artifact );
                    }
                }
            }
            result[name] = { { "army", army },
                             { "hero", hero },
                             { "controller", controller },
                             { "rule_profile", label( side, "rule_profile", controller == "python" ? "human" : "ai", { "human", "ai" } ) },
                             { "gold", number( side, "gold", 0, 0, 1000000000 ) },
                             { "formation", label( side, "formation", "spread", { "spread", "grouped" } ) } };
        }
        result["perspective_player_id"] = number( source, "perspective_player_id", firstExternal ? firstExternal : 1, 1, 2 );
        result["siege"] = nullptr;
        if ( source.contains( "siege" ) && !source["siege"].is_null() ) {
            if ( result["terrain"] == "water" )
                throw fheroes2::PythonEnvError( "invalid_request", "A siege cannot use water terrain." );
            const auto & siege = source["siege"];
            fields( siege, { "race", "fortification", "left_turret", "right_turret", "moat", "captain" } );
            std::set<std::string> names;
            for ( const auto & race : races )
                names.insert( race.first );
            result["siege"] = { { "race", label( siege, "race", "knight", names ) },
                                { "fortification", boolean( siege, "fortification", false ) },
                                { "left_turret", boolean( siege, "left_turret", true ) },
                                { "right_turret", boolean( siege, "right_turret", true ) },
                                { "moat", boolean( siege, "moat", true ) },
                                { "captain", boolean( siege, "captain", false ) } };
            if ( result["siege"]["fortification"] == true && result["siege"]["race"] != "knight" )
                throw fheroes2::PythonEnvError( "invalid_request", "Fortification is the Knight castle's native special building." );
            if ( result["siege"]["captain"] == true && !result["defender"]["hero"].is_null() )
                throw fheroes2::PythonEnvError( "invalid_request", "Choose a defending hero or a castle captain." );
        }
        return result;
    }
}

Army & fheroes2::PythonEnvWorld::standaloneArmy( const size_t side ) const
{
    const auto & config = _standaloneConfig[side == 0 ? "attacker" : "defender"];
    if ( !config["hero"].is_null() )
        return world.GetHeroes( config["hero"]["id"].get<int>() )->GetArmy();
    if ( side == 1 && !_standaloneConfig["siege"].is_null() )
        return world.getCastle( { 1, 0 } )->GetArmy();
    return *_standaloneArmies.at( side );
}

nlohmann::json fheroes2::PythonEnvWorld::configureBattle( const Json & source, const uint32_t seed )
{
    if ( _waiting )
        throw PythonEnvError( "session_active", "Stop or reset before configuring another battle." );
    const Json config = normalize( source ); // Validate every entry before replacing an existing world.
    clear();
    Settings & settings = Settings::Get();
    settings.SetProgramPath( _executablePath.c_str() );
    settings.SetGameType( Game::TYPE_BATTLEONLY );
    settings.SetGameDifficulty( 1 );
    if ( !_resources ) {
        try {
            _resources = std::make_unique<AGG::AGGInitializer>();
        }
        catch ( const std::exception & ) {
            throw PythonEnvError( "assets_unavailable", "Set FHEROES2_DATA to the game data root before configuring a battle." );
        }
    }
    try {
        AI::Planner::Get().resetWorldCaches();
        Rand::CurrentThreadRandomDevice() = Rand::PCG32( seed );
        for ( const int color : { 0, 1, 2, 4, 8, 16, 32 } )
            world.GetKingdom( static_cast<PlayerColor>( color ) ).PuzzleMaps() = Puzzle();
        world.generateBattleOnlyMap( terrains.at( config["terrain"].get<std::string>() ) );
        auto & info = settings.getCurrentMapInfo();
        info.kingdomColors = 3;
        info.colorsAvailableForHumans = 3;
        info.colorsAvailableForComp = 3;
        settings.GetPlayers().Init( 3 );
        for ( size_t i = 0; i < 2; ++i ) {
            const auto color = static_cast<PlayerColor>( 1 << i );
            const auto & side = config[i == 0 ? "attacker" : "defender"];
            Players::SetPlayerControl( color, side["rule_profile"] == "human" ? CONTROL_HUMAN : CONTROL_AI );
            Players::Get( color )->SetFriends( 1 << i );
            Players::SetPlayerInGame( color, true );
        }
        world.InitKingdoms();
        if ( !config["siege"].is_null() ) {
            const auto & siege = config["siege"];
            world.addCastle( 1, races.at( siege["race"].get<std::string>() ), PlayerColor::GREEN );
            world.getTile( 1 ).setMainObjectType( MP2::OBJ_CASTLE );
            Castle * castle = world.getCastle( { 1, 0 } );
            Maps::Map_Format::CastleMetadata metadata;
            metadata.customBuildings = true;
            metadata.customName = "Standalone castle";
            metadata.builtBuildings.push_back( BUILD_CASTLE );
            for ( const auto & pair : std::map<std::string, uint32_t>{ { "left_turret", BUILD_LEFTTURRET },
                                                                       { "right_turret", BUILD_RIGHTTURRET },
                                                                       { "moat", BUILD_MOAT },
                                                                       { "fortification", BUILD_SPEC },
                                                                       { "captain", BUILD_CAPTAIN } } )
                if ( siege[pair.first].get<bool>() )
                    metadata.builtBuildings.push_back( pair.second );
            castle->loadFromResurrectionMap( metadata );
            world.GetKingdom( PlayerColor::GREEN ).AddCastle( castle );
        }
        _standaloneConfig = config;
        _standaloneSeed = seed;
        _captureBattleFrame = config["capture_final_frame"].get<bool>();
        for ( size_t i = 0; i < 2; ++i ) {
            const auto color = static_cast<PlayerColor>( 1 << i );
            const auto & side = config[i == 0 ? "attacker" : "defender"];
            if ( !side["hero"].is_null() ) {
                const auto & h = side["hero"];
                Heroes * hero = world.GetHeroes( h["id"].get<int>() );
                if ( !hero || !hero->Recruit( color, { static_cast<int>( i ), 0 } ) )
                    throw PythonEnvError( "invalid_request", "The configured hero cannot be initialized." );
                hero->GetBagArtifacts().assign( BagArtifacts::maxCapacity, Artifact() );
                hero->SpellBookDeactivate();
                hero->GetSecondarySkills().ToVector().clear();
                hero->setAttackBaseValue( h["attack"] );
                hero->setDefenseBaseValue( h["defense"] );
                hero->setPowerBaseValue( h["power"] );
                hero->setKnowledgeBaseValue( h["knowledge"] );
                for ( const auto & skill : h["skills"] )
                    hero->GetSecondarySkills().AddSkill( { skill["id"], skill["level"] } );
                if ( h["spell_book"].get<bool>() )
                    hero->SpellBookActivate();
                for ( const auto & spell : h["spells"] )
                    hero->AppendSpellToBook( Spell( spell.get<int>() ), true );
                for ( const auto & item : h["artifacts"] ) {
                    Artifact artifact( item["id"].get<int>() );
                    if ( item.contains( "spell_id" ) )
                        artifact.SetSpell( item["spell_id"] );
                    if ( !hero->GetBagArtifacts().PushArtifact( artifact ) )
                        throw PythonEnvError( "invalid_request", "Artifact bag is full." );
                }
                hero->SetSpellPoints( h["spell_points"] );
                hero->SetShipMaster( config["terrain"] == "water" );
            }
            else
                _standaloneArmies[i] = std::make_unique<Army>();
            auto & army = standaloneArmy( i );
            army.Clean();
            army.SetColor( color );
            army.SetSpreadFormation( side["formation"] == "spread" );
            for ( size_t slot = 0; slot < side["army"].size(); ++slot ) {
                const auto & troop = side["army"][slot];
                if ( !troop.is_null() )
                    army.GetTroop( slot )->Set( Monster( troop["monster_id"].get<int>() ), troop["count"] );
            }
            auto & kingdom = world.GetKingdom( color );
            kingdom.OddFundsResource( kingdom.GetFunds() );
            kingdom.AddFundsResource( Funds( Resource::GOLD, side["gold"] ) );
            _controllers[std::to_string( 1 << i )] = side["controller"];
            _outcomes[std::to_string( 1 << i )] = 0;
        }
        _turnOrder = { 1, 2 };
        _turnIndex = 0;
        _controlled = true;
        _turnPrepared = true;
        _controllerPlayer = config["perspective_player_id"];
        settings.SetCurrentColor( static_cast<PlayerColor>( _controllerPlayer ) );
        _loaded = true;
        _waiting = true;
        ++_episodeId;
        ++_stateVersion;
        ++_decisionId;
        return { { "loaded", true }, { "mode", "standalone_battle" }, { "seed", seed }, { "configuration", config }, { "decision", getDecision() } };
    }
    catch ( ... ) {
        clear();
        _waiting = false;
        throw;
    }
}

void fheroes2::PythonEnvWorld::battleDecision( Battle::Arena & arena, const Battle::Unit & unit, Battle::Actions & actions, const std::function<void()> & wait )
{
    if ( !wait || ( _controlled ? !externalPlayer( static_cast<int>( arena.GetCurrentColor() ) ) : static_cast<int>( arena.GetCurrentColor() ) != _controllerPlayer ) )
        throw PythonEnvError( "unsupported_interaction", "This battle side has no matching external controller." );
    const int previous = _controllerPlayer;
    if ( _controlled )
        _controllerPlayer = static_cast<int>( arena.GetCurrentColor() );
    auto decision = pythonEnvBattleDecision( arena, unit );
    _battleState = std::move( decision.state );
    _battleRender = [&]( Image & output ) { Battle::Interface::renderSnapshot( arena, unit, output ); };
    _pendingChoice = { { "choice_id", ++_nextChoiceId }, { "kind", "battle.unit" }, { "unit_uid", unit.GetUID() } };
    ++_stateVersion;
    ++_decisionId;
    _events.push_back( { { "type", "battle_decision" }, { "round", arena.GetTurnNumber() }, { "unit_uid", unit.GetUID() }, { "player_id", _controllerPlayer } } );
    wait();
    const auto selected = static_cast<size_t>( _choiceAnswer );
    _events.push_back( { { "type", "battle_action" }, { "action", _battleState["actions"][selected] }, { "round", arena.GetTurnNumber() } } );
    actions.push_back( decision.commands.at( selected ) );
    _pendingChoice = nullptr;
    _battleState = nullptr;
    _battleRender = {};
    _controllerPlayer = previous;
}

nlohmann::json fheroes2::PythonEnvWorld::standaloneState() const
{
    if ( _standaloneConfig.is_null() )
        return nullptr;
    Json sides = Json::array();
    for ( size_t i = 0; i < 2; ++i ) {
        const auto & army = standaloneArmy( i );
        Json troops = Json::array();
        for ( size_t slot = 0; slot < army.Size(); ++slot ) {
            const auto * troop = army.GetTroop( slot );
            troops.push_back( troop->isValid() ? Json{ { "monster_id", troop->GetID() }, { "count", troop->GetCount() } } : Json( nullptr ) );
        }
        const auto * commander = army.GetCommander();
        sides.push_back( { { "player_id", 1 << i }, { "army", troops }, { "spell_points", commander ? Json( commander->GetSpellPoints() ) : Json( nullptr ) } } );
    }
    return { { "configuration", _standaloneConfig },
             { "seed", _standaloneSeed },
             { "result", _standaloneResult },
             { "sides", sides },
             { "internal_battle_context", true } };
}

nlohmann::json fheroes2::PythonEnvWorld::runStandaloneBattle( const std::function<void()> & wait )
{
    const auto config = _standaloneConfig;
    const auto seed = _standaloneSeed;
    const auto version = _stateVersion, episode = _episodeId, decisionId = _decisionId, choiceId = _nextChoiceId;
    const auto capture = [&]( Battle::Arena & arena ) {
        _battleState = pythonEnvBattleSnapshot( arena );
        _battleRender = {};
        if ( _captureBattleFrame ) {
            struct RestoreRandom
            {
                Rand::PCG32 state = Rand::CurrentThreadRandomDevice();
                ~RestoreRandom()
                {
                    Rand::CurrentThreadRandomDevice() = state;
                }
            } restoreRandom;
            ensureGraphicsData();
            auto image = std::make_shared<Image>();
            Battle::Interface::renderSnapshot( arena, *image );
            _battleRender = [image]( Image & output ) { output = *image; };
        }
    };
    try {
        _events = Json::array();
        Game::ScopedExternalInteractions
            interactions( []( const Game::ExternalChoice & )
                              -> int64_t { throw PythonEnvError( "unsupported_interaction", "Unexpected adventure choice in standalone battle." ); },
                          [&]( const std::string & title, const std::string & message ) {
                              _events.push_back(
                                  { { "type", "notification" }, { "title", System::encLocalToUTF8( title ) }, { "message", System::encLocalToUTF8( message ) } } );
                          },
                          [&]( Battle::Arena & arena, const Battle::Unit & unit, Battle::Actions & actions ) { battleDecision( arena, unit, actions, wait ); }, {},
                          [&]( int color ) { return externalPlayer( color ) ? Game::ControllerType::External : Game::ControllerType::Native; }, {}, {}, {}, capture,
                          [&]( Battle::Arena & arena ) {
                              if ( arena.GetTurnNumber() >= config["max_rounds"].get<uint32_t>() ) {
                                  arena.getAttackingForce().syncOriginalArmy();
                                  arena.getDefendingForce().syncOriginalArmy();
                                  capture( arena );
                                  throw RoundLimit{};
                              }
                          } );
        Battle::Result result;
        try {
            result = Battle::Loader( standaloneArmy( 0 ), standaloneArmy( 1 ), 1 );
            const int winner = result.isAttackerWin() ? 1 : ( result.isDefenderWin() ? 2 : 0 );
            _standaloneResult = { { "attacker_result", result.attacker },
                                  { "defender_result", result.defender },
                                  { "attacker_experience", result.attackerExperience },
                                  { "defender_experience", result.defenderExperience },
                                  { "dead_units_for_necromancy", result.numOfDeadUnitsForNecromancy },
                                  { "winner_player_id", winner },
                                  { "truncated", false },
                                  { "rounds", _battleState["round"] } };
            for ( int color : { 1, 2 } )
                _outcomes[std::to_string( color )] = winner == 0 ? 0U : static_cast<uint32_t>( color == winner ? GameOver::WINS_ALL : GameOver::LOSS_ALL );
        }
        catch ( const RoundLimit & ) {
            for ( size_t i = 0; i < 2; ++i ) {
                standaloneArmy( i ).resetInvalidMonsters();
                if ( auto * h = standaloneArmy( i ).GetCommander() )
                    h->ActionAfterBattle();
            }
            _standaloneResult = { { "winner_player_id", 0 }, { "truncated", true }, { "reason", "round_limit" }, { "rounds", _battleState["round"] } };
        }
        _simulationFinished = true;
        _pendingChoice = nullptr;
        _controllerPlayer = config["perspective_player_id"];
        ++_stateVersion;
        ++_decisionId;
        _events.push_back( { { "type", "battle_completed" }, { "result", _standaloneResult } } );
        return actionResult();
    }
    catch ( ... ) {
        // Native Arena has unwound. Rebuild only the tiny battle context, never load a map/save.
        _waiting = false;
        configureBattle( config, seed );
        _stateVersion = version;
        _episodeId = episode;
        _decisionId = decisionId;
        _nextChoiceId = choiceId;
        throw;
    }
}

#endif
