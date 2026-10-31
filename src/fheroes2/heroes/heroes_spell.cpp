/***************************************************************************
 *   fheroes2: https://github.com/ihhub/fheroes2                           *
 *   Copyright (C) 2019 - 2026                                             *
 *                                                                         *
 *   Free Heroes2 Engine: http://sourceforge.net/projects/fheroes2         *
 *   Copyright (C) 2010 by Andrey Afletdinov <fheroes2@gmail.com>          *
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

#include <algorithm>
#include <cassert>
#include <cstdint>
#include <memory>
#include <ostream>
#include <string>
#include <vector>

#include "army.h"
#include "army_troop.h"
#include "audio_manager.h"
#include "castle.h"
#include "color.h"
#include "core.h"
#include "dialog.h"
#include "dialog_selectitems.h"
#include "direction.h"
#include "game_external_interaction.h"
#include "game_interface.h"
#include "heroes.h" // IWYU pragma: associated
#include "interface_base.h"
#include "interface_gamearea.h"
#include "interface_radar.h"
#include "kingdom.h"
#include "logging.h"
#include "m82.h"
#include "maps.h"
#include "maps_tiles.h"
#include "maps_tiles_helper.h"
#include "math_base.h"
#include "monster.h"
#include "mp2.h"
#include "resource.h"
#include "route.h"
#include "settings.h"
#include "spell.h"
#include "spell_info.h"
#include "tools.h"
#include "translations.h"
#include "ui_dialog.h"
#include "view_world.h"
#include "world.h"

namespace
{
    void HeroesTownGate( Heroes & hero, const Castle * castle )
    {
        assert( castle && castle->GetHero() == nullptr );
        const fheroes2::Point fromPosition = hero.GetCenter();
        if ( !System::isHeadlessMode() ) {
            Interface::AdventureMap & I = Interface::AdventureMap::Get();
            I.getGameArea().SetCenter( fromPosition );
            I.redraw( Interface::REDRAW_GAMEAREA | Interface::REDRAW_RADAR_CURSOR );
            AudioManager::PlaySound( M82::KILLFADE );
        }
        const int32_t dst = castle->GetIndex();
        assert( Maps::isValidAbsIndex( dst ) );
        hero.ShowPath( false );
        if ( !System::isHeadlessMode() )
            hero.FadeOut();
        hero.Scout( dst );
        hero.Move2Dest( dst );
        hero.GetPath().Reset();
        if ( !System::isHeadlessMode() ) {
            Interface::AdventureMap & I = Interface::AdventureMap::Get();
            I.getRadar().SetRenderArea( { fromPosition.x, fromPosition.y, 1, 1 } );
            I.redraw( Interface::REDRAW_RADAR );
            I.getGameArea().SetCenter( hero.GetCenter() );
            I.getRadar().SetRenderArea( hero.GetScoutRoi() );
            I.setRedraw( Interface::REDRAW_GAMEAREA | Interface::REDRAW_RADAR );
            AudioManager::PlaySound( M82::KILLFADE );
            hero.FadeIn();
        }
        hero.ShowPath( true );
        castle->trainHeroInMageGuild( hero );
    }

    bool ActionSpellViewMines()
    {
        if ( System::isHeadlessMode() )
            Game::ScopedExternalInteractions::information( "world", static_cast<int>( Settings::Get().CurrentColor() ), static_cast<int>( ViewWorldMode::ViewMines ) );
        else
            ViewWorld::ViewWorldWindow( Settings::Get().CurrentColor(), ViewWorldMode::ViewMines, Interface::AdventureMap::Get() );
        return true;
    }

    bool ActionSpellViewResources()
    {
        if ( System::isHeadlessMode() )
            Game::ScopedExternalInteractions::information( "world", static_cast<int>( Settings::Get().CurrentColor() ),
                                                           static_cast<int>( ViewWorldMode::ViewResources ) );
        else
            ViewWorld::ViewWorldWindow( Settings::Get().CurrentColor(), ViewWorldMode::ViewResources, Interface::AdventureMap::Get() );
        return true;
    }

    bool ActionSpellViewArtifacts()
    {
        if ( System::isHeadlessMode() )
            Game::ScopedExternalInteractions::information( "world", static_cast<int>( Settings::Get().CurrentColor() ),
                                                           static_cast<int>( ViewWorldMode::ViewArtifacts ) );
        else
            ViewWorld::ViewWorldWindow( Settings::Get().CurrentColor(), ViewWorldMode::ViewArtifacts, Interface::AdventureMap::Get() );
        return true;
    }

    bool ActionSpellViewTowns()
    {
        if ( System::isHeadlessMode() )
            Game::ScopedExternalInteractions::information( "world", static_cast<int>( Settings::Get().CurrentColor() ), static_cast<int>( ViewWorldMode::ViewTowns ) );
        else
            ViewWorld::ViewWorldWindow( Settings::Get().CurrentColor(), ViewWorldMode::ViewTowns, Interface::AdventureMap::Get() );
        return true;
    }

    bool ActionSpellViewHeroes()
    {
        if ( System::isHeadlessMode() )
            Game::ScopedExternalInteractions::information( "world", static_cast<int>( Settings::Get().CurrentColor() ), static_cast<int>( ViewWorldMode::ViewHeroes ) );
        else
            ViewWorld::ViewWorldWindow( Settings::Get().CurrentColor(), ViewWorldMode::ViewHeroes, Interface::AdventureMap::Get() );
        return true;
    }

    bool ActionSpellViewAll()
    {
        if ( System::isHeadlessMode() )
            Game::ScopedExternalInteractions::information( "world", static_cast<int>( Settings::Get().CurrentColor() ), static_cast<int>( ViewWorldMode::ViewAll ) );
        else
            ViewWorld::ViewWorldWindow( Settings::Get().CurrentColor(), ViewWorldMode::ViewAll, Interface::AdventureMap::Get() );
        return true;
    }

    bool ActionSpellIdentifyHero( const Heroes & hero )
    {
        assert( !hero.GetKingdom().Modes( Kingdom::IDENTIFYHERO ) );

        hero.GetKingdom().SetModes( Kingdom::IDENTIFYHERO );
        fheroes2::showStandardTextMessage( _( "Identify Hero" ), _( "Enemy heroes are now fully identifiable." ), Dialog::OK );

        return true;
    }

    bool ActionSpellSummonBoat( const Heroes & hero )
    {
        assert( !hero.isShipMaster() );

        const int32_t boatDestination = fheroes2::getPossibleBoatPosition( hero );
        assert( Maps::isValidAbsIndex( boatDestination ) );

        const int32_t boatSource = fheroes2::getSummonableBoat( hero );

        // Player should have a summonable boat before calling this function.
        assert( Maps::isValidAbsIndex( boatSource ) );

        const PlayerColor heroColor = hero.GetColor();

        Maps::Tile & tileSource = world.getTile( boatSource );

        if ( System::isHeadlessMode() )
            Maps::removeMainObjectFromTile( tileSource );
        else
            Interface::AdventureMap::Get().getGameArea().runSingleObjectAnimation(
                std::make_shared<Interface::ObjectFadingOutInfo>( tileSource.getMainObjectPart()._uid, boatSource, MP2::OBJ_BOAT ) );

        Maps::Tile & tileDest = world.getTile( boatDestination );

        tileDest.setBoat( Direction::RIGHT, heroColor );
        tileSource.resetBoatOwnerColor();

        if ( !System::isHeadlessMode() )
            Interface::AdventureMap::Get().getGameArea().runSingleObjectAnimation(
                std::make_shared<Interface::ObjectFadingInInfo>( tileDest.getMainObjectPart()._uid, boatDestination, MP2::OBJ_BOAT ) );

        return true;
    }

    bool ActionSpellDimensionDoor( Heroes & hero )
    {
        const fheroes2::Point fromPosition = hero.GetCenter();
        const int32_t src = hero.GetIndex();
        assert( Maps::isValidAbsIndex( src ) );
        int32_t dst = -1;
        if ( System::isHeadlessMode() ) {
            std::vector<int64_t> options;
            const int radius = Spell::CalculateDimensionDoorDistance() / 2;
            for ( int y = std::max( 0, fromPosition.y - radius ); y <= std::min( world.h() - 1, fromPosition.y + radius ); ++y ) {
                for ( int x = std::max( 0, fromPosition.x - radius ); x <= std::min( world.w() - 1, fromPosition.x + radius ); ++x ) {
                    const int index = y * world.w() + x;
                    if ( Maps::isValidForDimensionDoor( index, hero.isShipMaster() ) )
                        options.push_back( index );
                }
            }
            if ( options.empty() )
                return false;
            dst = static_cast<int32_t>( Game::ScopedExternalInteractions::choose( { "spell.dimension_door", hero.GetID(), options, {} } ) );
        }
        else {
            Interface::AdventureMap & I = Interface::AdventureMap::Get();
            I.getGameArea().SetCenter( hero.GetCenter() );
            I.redraw( Interface::REDRAW_GAMEAREA | Interface::REDRAW_RADAR_CURSOR );
            dst = I.GetDimensionDoorDestination( src, Spell::CalculateDimensionDoorDistance(), hero.isShipMaster() );
        }
        if ( !Maps::isValidAbsIndex( dst ) )
            return false;
        hero.ShowPath( false );
        if ( !System::isHeadlessMode() ) {
            AudioManager::PlaySound( M82::KILLFADE );
            hero.FadeOut();
        }
        hero.Scout( dst );
        hero.Move2Dest( dst );
        hero.SpellCasted( Spell::DIMENSIONDOOR );
        hero.calculatePath( -1 );
        if ( !System::isHeadlessMode() ) {
            Interface::AdventureMap & I = Interface::AdventureMap::Get();
            I.getRadar().SetRenderArea( { fromPosition.x, fromPosition.y, 1, 1 } );
            I.redraw( Interface::REDRAW_RADAR );
            I.getGameArea().SetCenter( hero.GetCenter() );
            I.getRadar().SetRenderArea( hero.GetScoutRoi() );
            I.setRedraw( Interface::REDRAW_GAMEAREA | Interface::REDRAW_RADAR );
            AudioManager::PlaySound( M82::KILLFADE );
            hero.FadeIn();
        }
        hero.ShowPath( true );
        hero.ActionNewPosition( false );
        // Already charged above. Preserve the UI routine's legacy apply=false convention.
        return System::isHeadlessMode();
    }

    bool ActionSpellTownGate( Heroes & hero )
    {
        assert( !hero.isShipMaster() );

        const Castle * castle = fheroes2::getNearestCastleTownGate( hero );
        if ( !castle ) {
            // A hero must be able to have a destination castle. Something is wrong with the logic!
            assert( 0 );
            return false;
        }

        if ( castle->GetHero() ) {
            // The nearest town occupation must be checked before casting this spell. Something is wrong with the logic!
            assert( 0 );
            return false;
        }

        HeroesTownGate( hero, castle );

        return true;
    }

    bool ActionSpellTownPortal( Heroes & hero )
    {
        assert( !hero.isShipMaster() );

        int32_t townPositionIndex = -1;
        if ( System::isHeadlessMode() ) {
            std::vector<int64_t> options;
            for ( const Castle * castle : hero.GetKingdom().GetCastles() ) {
                if ( castle->GetHero() == nullptr )
                    options.push_back( castle->GetIndex() );
            }
            townPositionIndex = static_cast<int32_t>( Game::ScopedExternalInteractions::choose( { "spell.town_portal", hero.GetID(), options, {} } ) );
        }
        else
            townPositionIndex = Dialog::selectKingdomCastle( hero.GetKingdom(), true, _( "Town Portal" ), _( "Select town to port to." ) );

        if ( townPositionIndex == -1 ) {
            return false;
        }

        HeroesTownGate( hero, world.getCastleEntrance( Maps::GetPoint( townPositionIndex ) ) );

        return true;
    }

    bool ActionSpellVisions( Heroes & hero )
    {
        const MapsIndexes monsters = Maps::getVisibleMonstersAroundHero( hero );

        assert( !monsters.empty() );

        hero.GetKingdom().addMonstersUnderVisionSpell( monsters );

        for ( const int32_t monsterIndex : monsters ) {
            const Maps::Tile & tile = world.getTile( monsterIndex );

            const Troop troop = getTroopFromTile( tile );
            const NeutralMonsterJoiningCondition join = Army::GetJoinSolution( hero, tile, troop );

            std::string hdr;
            std::string msg;

            hdr = std::string( "%{count} " ) + troop.GetPluralName( join.monsterCount );
            StringReplace( hdr, "%{count}", troop.GetCount() );

            switch ( join.reason ) {
            case NeutralMonsterJoiningCondition::Reason::Free:
            case NeutralMonsterJoiningCondition::Reason::Alliance:
                msg = _( "The creatures are willing to join us!" );
                break;

            case NeutralMonsterJoiningCondition::Reason::ForMoney:
                if ( join.monsterCount == troop.GetCount() )
                    msg = _( "All the creatures will join us..." );
                else {
                    msg = _n( "The creature will join us...", "%{count} of the creatures will join us...", join.monsterCount );
                    StringReplace( msg, "%{count}", join.monsterCount );
                }

                msg += '\n';
                msg.append( _( "\n for a fee of %{gold} gold." ) );
                StringReplace( msg, "%{gold}", troop.GetTotalCost().gold );
                break;

            case NeutralMonsterJoiningCondition::Reason::RunAway:
            case NeutralMonsterJoiningCondition::Reason::Bane:
                msg = _( "These weak creatures will surely flee before us." );
                break;
            default:
                msg = _( "I fear these creatures are in the mood for a fight." );
                break;
            }

            fheroes2::MonsterDialogElement monsterUI( troop );
            const std::vector<const fheroes2::DialogElement *> uiElements{ &monsterUI };

            fheroes2::showStandardTextMessage( hdr, msg, Dialog::OK, uiElements );
        }

        hero.SetModes( Heroes::VISIONS );

        return true;
    }

    bool ActionSpellSetGuardian( const Heroes & hero, const Spell & spell )
    {
        Maps::Tile & tile = world.getTile( hero.GetIndex() );
        assert( MP2::OBJ_MINE == tile.getMainObjectType( false ) );

        const uint32_t count = fheroes2::getGuardianMonsterCount( spell, hero.GetPower() );

        if ( count == 0 ) {
            return false;
        }

        Maps::setMineSpellOnTile( tile, spell.GetID() );

        if ( spell == Spell::HAUNT && hero.isControlHuman() ) {
            world.CaptureObject( tile.GetIndex(), PlayerColor::NONE );

            if ( !System::isHeadlessMode() ) {
                // Update the color of haunted mine on radar.
                Interface::AdventureMap & I = Interface::AdventureMap::Get();
                const fheroes2::Point heroPosition = hero.GetCenter();
                I.getRadar().SetRenderArea( { heroPosition.x - 1, heroPosition.y - 1, 3, 2 } );

                I.setRedraw( Interface::REDRAW_RADAR );
            }
        }

        world.GetCapturedObject( tile.GetIndex() ).GetTroop().Set( Monster( spell ), count );

        return true;
    }
}

bool Heroes::ActionSpellCast( const Spell & spell )
{
    assert( spell.isValid() && !spell.isCombat() && CanCastSpell( spell ) );

    bool apply = false;

    switch ( spell.GetID() ) {
    case Spell::VIEWMINES:
        apply = ActionSpellViewMines();
        break;
    case Spell::VIEWRESOURCES:
        apply = ActionSpellViewResources();
        break;
    case Spell::VIEWARTIFACTS:
        apply = ActionSpellViewArtifacts();
        break;
    case Spell::VIEWTOWNS:
        apply = ActionSpellViewTowns();
        break;
    case Spell::VIEWHEROES:
        apply = ActionSpellViewHeroes();
        break;
    case Spell::VIEWALL:
        apply = ActionSpellViewAll();
        break;
    case Spell::IDENTIFYHERO:
        apply = ActionSpellIdentifyHero( *this );
        break;
    case Spell::SUMMONBOAT:
        apply = ActionSpellSummonBoat( *this );
        break;
    case Spell::DIMENSIONDOOR:
        if ( System::isHeadlessMode() )
            return ActionSpellDimensionDoor( *this );
        apply = ActionSpellDimensionDoor( *this );
        break;
    case Spell::TOWNGATE:
        apply = ActionSpellTownGate( *this );
        break;
    case Spell::TOWNPORTAL:
        apply = ActionSpellTownPortal( *this );
        break;
    case Spell::VISIONS:
        apply = ActionSpellVisions( *this );
        break;
    case Spell::HAUNT:
    case Spell::SETEGUARDIAN:
    case Spell::SETAGUARDIAN:
    case Spell::SETFGUARDIAN:
    case Spell::SETWGUARDIAN:
        apply = ActionSpellSetGuardian( *this, spell );
        break;
    default:
        break;
    }

    if ( !apply ) {
        return false;
    }

    DEBUG_LOG( DBG_GAME, DBG_INFO, GetName() << " cast spell: " << spell.GetName() )

    SpellCasted( spell );
    return true;
}
