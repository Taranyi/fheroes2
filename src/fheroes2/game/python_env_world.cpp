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

#include <array>
#include <filesystem>
#include <system_error>
#include <utility>

#include "agg.h"
#include "army.h"
#include "army_troop.h"
#include "artifact.h"
#include "castle.h"
#include "color.h"
#include "game.h"
#include "game_io.h"
#include "game_over.h"
#include "heroes.h"
#include "maps_fileinfo.h"
#include "maps_tiles.h"
#include "players.h"
#include "race.h"
#include "resource.h"
#include "save_format_version.h"
#include "serialize.h"
#include "settings.h"
#include "skill.h"
#include "spell.h"
#include "system.h"
#include "world.h"

namespace
{
    using Json = nlohmann::json;

    std::string text( const std::string & value )
    {
        return System::encLocalToUTF8( value );
    }

    const char * colorName( const PlayerColor color )
    {
        switch ( color ) {
        case PlayerColor::BLUE:
            return "blue";
        case PlayerColor::GREEN:
            return "green";
        case PlayerColor::RED:
            return "red";
        case PlayerColor::YELLOW:
            return "yellow";
        case PlayerColor::ORANGE:
            return "orange";
        case PlayerColor::PURPLE:
            return "purple";
        default:
            return "neutral";
        }
    }

    Json position( const int32_t index )
    {
        if ( index < 0 || world.w() == 0 || static_cast<size_t>( index ) >= world.getSize() ) {
            return nullptr;
        }
        return { { "index", index }, { "x", index % world.w() }, { "y", index / world.w() } };
    }

    Json funds( const Funds & value )
    {
        return { { "wood", value.wood },       { "mercury", value.mercury }, { "ore", value.ore },  { "sulfur", value.sulfur },
                 { "crystal", value.crystal }, { "gems", value.gems },       { "gold", value.gold } };
    }

    Json army( const Army & value )
    {
        Json slots = Json::array();
        for ( size_t slot = 0; slot < value.Size(); ++slot ) {
            const Troop * troop = value.GetTroop( slot );
            slots.push_back( troop == nullptr || !troop->isValid() ? Json( nullptr )
                                                                   : Json{ { "slot", slot },
                                                                           { "monster_id", troop->GetMonster().GetID() },
                                                                           { "name", text( troop->GetMonster().GetName() ) },
                                                                           { "count", troop->GetCount() } } );
        }
        return slots;
    }

    Json heroState( const Heroes & hero )
    {
        Json skills = Json::array();
        for ( const auto & skill : hero.GetSecondarySkills().ToVector() ) {
            if ( skill.isValid() ) {
                skills.push_back( { { "id", skill.Skill() }, { "name", text( Skill::Secondary::String( skill.Skill() ) ) }, { "level", skill.Level() } } );
            }
        }
        Json artifacts = Json::array();
        for ( const auto & artifact : hero.GetBagArtifacts() ) {
            artifacts.push_back( artifact.isValid() ? Json{ { "id", artifact.GetID() }, { "name", text( artifact.GetName() ) } } : Json( nullptr ) );
        }
        Json spells = Json::array();
        for ( const auto & spell : hero.getMagicBookSpells() ) {
            spells.push_back( spell.GetID() );
        }

        const Castle * castle = hero.isActive() ? hero.inCastle() : nullptr;
        return { { "id", hero.GetID() },
                 { "name", text( hero.GetName() ) },
                 { "owner", static_cast<int>( hero.GetColor() ) },
                 { "race", hero.GetRace() },
                 { "active", hero.isActive() },
                 { "position", position( hero.GetIndex() ) },
                 { "level", hero.GetLevel() },
                 { "experience", hero.GetExperience() },
                 { "attack", hero.GetAttack() },
                 { "defense", hero.GetDefense() },
                 { "power", hero.GetPower() },
                 { "knowledge", hero.GetKnowledge() },
                 { "spell_points", hero.GetSpellPoints() },
                 { "max_spell_points", hero.GetMaxSpellPoints() },
                 { "move_points", hero.GetMovePoints() },
                 { "army", army( hero.GetArmy() ) },
                 { "secondary_skills", skills },
                 { "artifacts", artifacts },
                 { "spells", spells },
                 { "castle_id", castle == nullptr ? Json( nullptr ) : Json( castle->GetIndex() ) } };
    }

    Json castleState( const Castle & castle )
    {
        Json buildings = Json::array();
        // BuildingType is a 32-bit bitset. Export individual bits, not UI-derived affordability checks.
        for ( unsigned int bit = 0; bit < 32; ++bit ) {
            const uint32_t building = uint32_t{ 1 } << bit;
            if ( castle.isBuild( building ) ) {
                buildings.push_back( building );
            }
        }
        Json dwellings = Json::array();
        for ( const uint32_t dwelling : { DWELLING_MONSTER1, DWELLING_MONSTER2, DWELLING_MONSTER3, DWELLING_MONSTER4, DWELLING_MONSTER5, DWELLING_MONSTER6 } ) {
            dwellings.push_back( { { "building_id", dwelling }, { "count", castle.getMonstersInDwelling( dwelling ) } } );
        }
        const Heroes * visitor = world.GetHeroes( castle.GetCenter() );
        return { { "id", castle.GetIndex() },
                 { "name", text( castle.GetName() ) },
                 { "owner", static_cast<int>( castle.GetColor() ) },
                 { "race", castle.GetRace() },
                 { "position", position( castle.GetIndex() ) },
                 { "is_castle", castle.isCastle() },
                 { "buildings", buildings },
                 { "dwellings", dwellings },
                 { "garrison", army( castle.GetArmy() ) },
                 { "visiting_hero_id", visitor == nullptr ? Json( nullptr ) : Json( visitor->GetID() ) } };
    }

    Json objectPart( const Maps::ObjectPart & part )
    {
        return { { "uid", part._uid }, { "layer", part.layerType }, { "icn_type", part.icnType }, { "image", part.icnIndex } };
    }

    std::string hex( const uint8_t * bytes, const size_t size )
    {
        constexpr char digits[] = "0123456789abcdef";
        std::string result( size * 2, '0' );
        for ( size_t i = 0; i < size; ++i ) {
            result[i * 2] = digits[bytes[i] >> 4];
            result[i * 2 + 1] = digits[bytes[i] & 15];
        }
        return result;
    }
}

fheroes2::PythonEnvError::PythonEnvError( std::string errorCode, const std::string & message )
    : std::runtime_error( message )
    , code( std::move( errorCode ) )
{}

fheroes2::PythonEnvWorld::PythonEnvWorld( std::string executablePath )
    : _executablePath( std::move( executablePath ) )
{}

fheroes2::PythonEnvWorld::~PythonEnvWorld() = default;

bool fheroes2::PythonEnvWorld::loaded() const
{
    return _loaded;
}

void fheroes2::PythonEnvWorld::clear()
{
    _loaded = false;
    _warnings.clear();
    world.Reset();
    Settings::Get().GetPlayers().clear();
    GameOver::Result::Get().Reset();
}

nlohmann::json fheroes2::PythonEnvWorld::loadSave( const std::string & utf8Path )
{
    clear();
    ++_stateVersion;
    const std::string path = System::encUTF8ToLocal( utf8Path );
    if ( System::encLocalToUTF8( path ) != utf8Path ) {
        throw PythonEnvError( "invalid_path", "This save path cannot be represented by the engine's filesystem encoding." );
    }
    std::error_code error;
    const auto size = std::filesystem::file_size( std::filesystem::path{ path }, error );
    if ( error || size == 0 || size > 64 * 1024 * 1024 ) {
        throw PythonEnvError( "load_failed", "Expected an accessible, nonempty save file of at most 64 MiB." );
    }

    Settings & settings = Settings::Get();
    settings.SetProgramPath( _executablePath.c_str() );
    settings.SetGameType( Game::TYPE_STANDARD );
    if ( !_resources ) {
        try {
            _resources = std::make_unique<AGG::AGGInitializer>();
        }
        catch ( const std::exception & ) {
            throw PythonEnvError( "assets_unavailable", "Game data could not be opened. Set FHEROES2_DATA to the game data root before starting the session." );
        }
    }

    std::string message;
    Game::LoadOptions options;
    options.showMessages = false;
    options.requireStandardGame = true;
    options.errorMessage = &message;
    options.warnings = &_warnings;
    try {
        if ( Game::Load( path, options ) != GameMode::START_GAME ) {
            clear();
            throw PythonEnvError( "load_failed", message.empty() ? "The engine could not load the save." : text( message ) );
        }
        if ( world.w() <= 0 || world.h() <= 0 || world.getSize() != static_cast<size_t>( world.w() ) * world.h() ) {
            clear();
            throw PythonEnvError( "load_failed", "The save did not contain a valid world." );
        }
        _loaded = true;
    }
    catch ( ... ) {
        clear();
        throw;
    }
    return { { "loaded", true },      { "state_version", _stateVersion }, { "map_name", text( settings.getCurrentMapInfo().name ) }, { "width", world.w() },
             { "height", world.h() }, { "warnings", _warnings } };
}

nlohmann::json fheroes2::PythonEnvWorld::getState( const bool includeSerialized ) const
{
    if ( !_loaded ) {
        throw PythonEnvError( "no_game_loaded", "Call load_save before requesting game state." );
    }
    const Settings & settings = Settings::Get();
    Json players = Json::array();
    for ( const Player * player : settings.GetPlayers().getVector() ) {
        const Kingdom & kingdom = world.GetKingdom( player->GetColor() );
        Json heroIds = Json::array();
        for ( const Heroes * hero : kingdom.GetHeroes() ) {
            heroIds.push_back( hero->GetID() );
        }
        Json castleIds = Json::array();
        for ( const Castle * castle : kingdom.GetCastles() ) {
            castleIds.push_back( castle->GetIndex() );
        }
        players.push_back( { { "id", static_cast<int>( player->GetColor() ) },
                             { "color", colorName( player->GetColor() ) },
                             { "name", text( player->GetName() ) },
                             { "control", player->GetControl() },
                             { "is_ai", player->isControlAI() },
                             { "is_human", player->isControlHuman() },
                             { "in_play", player->isPlay() },
                             { "race", player->GetRace() },
                             { "friends", player->GetFriends() },
                             { "funds", funds( kingdom.GetFunds() ) },
                             { "hero_ids", heroIds },
                             { "castle_ids", castleIds } } );
    }
    Json heroes = Json::array();
    for ( const Heroes * hero : world.getAllHeroes() ) {
        if ( Heroes::isValidId( hero->GetID() ) ) {
            heroes.push_back( heroState( *hero ) );
        }
    }
    Json castles = Json::array();
    for ( const Castle * castle : world.getAllCastles() ) {
        castles.push_back( castleState( *castle ) );
    }
    Json tiles = Json::array();
    for ( int32_t index = 0; static_cast<size_t>( index ) < world.getSize(); ++index ) {
        const Maps::Tile & tile = world.getTile( index );
        PlayerColorsSet fog = 0;
        for ( const PlayerColor color : PlayerColorsVector( Color::allPlayerColors() ) ) {
            if ( tile.isFog( color ) ) {
                fog |= color;
            }
        }
        Json ground = Json::array();
        for ( const auto & part : tile.getGroundObjectParts() ) {
            ground.push_back( objectPart( part ) );
        }
        Json top = Json::array();
        for ( const auto & part : tile.getTopObjectParts() ) {
            top.push_back( objectPart( part ) );
        }
        tiles.push_back( { { "index", index },
                           { "x", index % world.w() },
                           { "y", index / world.w() },
                           { "terrain", tile.GetGround() },
                           { "terrain_image", tile.getTerrainImageIndex() },
                           { "terrain_flags", tile.getTerrainFlags() },
                           { "water", tile.isWater() },
                           { "road", tile.isRoad() },
                           { "object_type", tile.getMainObjectType() },
                           { "object_under_hero", tile.getMainObjectType( false ) },
                           { "metadata", tile.metadata() },
                           { "fog_colors", fog },
                           { "passability", tile.GetPassable() },
                           { "main_part", objectPart( tile.getMainObjectPart() ) },
                           { "ground_parts", ground },
                           { "top_parts", top } } );
    }

    const auto & map = settings.getCurrentMapInfo();
    Json result{ { "schema_version", 1 },
                 { "state_version", _stateVersion },
                 { "perspective", "omniscient" },
                 { "phase", "adventure" },
                 { "current_player", static_cast<int>( settings.GetPlayers().getCurrentColor() ) },
                 { "date",
                   { { "day", world.GetDay() },
                     { "week", world.GetWeek() },
                     { "month", world.GetMonth() },
                     { "total_days", world.CountDay() },
                     { "total_weeks", world.CountWeek() } } },
                 { "map",
                   { { "name", text( map.name ) },
                     { "width", world.w() },
                     { "height", world.h() },
                     { "seed", world.GetMapSeed() },
                     { "victory_condition", map.victoryConditionType },
                     { "loss_condition", map.lossConditionType },
                     { "tiles", tiles } } },
                 { "players", players },
                 { "heroes", heroes },
                 { "castles", castles },
                 { "game_result", GameOver::Result::Get().GetResult() } };
    if ( includeSerialized ) {
        RWStreamBuf stream;
        stream.setBigendian( true );
        stream << world << settings << GameOver::Result::Get();
        if ( stream.fail() ) {
            throw PythonEnvError( "state_export_failed", "The engine could not serialize the complete save payload." );
        }
        result["serialized_state"] = { { "encoding", "hex" },
                                       { "format", "fheroes2_save_payload" },
                                       { "save_format_version", CURRENT_FORMAT_VERSION },
                                       { "data", hex( stream.data(), stream.size() ) } };
    }
    return result;
}

#endif
