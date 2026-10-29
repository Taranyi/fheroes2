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

#include "python_env_views.h"
#if defined( FHEROES2_ENABLE_PYTHON_ENV )

#include "army_bar.h"
#include "artifact.h"
#include "castle.h"
#include "color.h"
#include "game_assets.h"
#include "heroes.h"
#include "heroes_indicator.h"
#include "icn.h"
#include "image.h"
#include "kingdom.h"
#include "race.h"
#include "settings.h"
#include "skill_bar.h"
#include "ui_castle.h"
#include "ui_text.h"
#include "ui_tool.h"
#include "world.h"

namespace
{
    void army( Army & value, fheroes2::Image & output, const int x, const int y )
    {
        ArmyBar bar( &value, false, true );
        bar.setTableSize( { 5, 1 } );
        bar.setRenderingOffset( { x, y } );
        bar.setInBetweenItemsOffset( { 6, 0 } );
        bar.Redraw( output );
    }
}

void fheroes2::renderHeroSnapshot( Heroes & hero, Image & destination )
{
    Image output;
    output._disableTransformLayer();
    output.resize( 640, 480 );
    output.fill( 0 );
    const ScopedDrawingTarget target( output );
    Blit( Assets::getImage( ICN::HEROBKG, 0 ), output, 0, 0 );
    Blit( Assets::getImage( Settings::Get().isEvilInterfaceEnabled() ? ICN::HEROEXTE : ICN::HEROEXTG, 0 ), output, 0, 0 );
    const Text title( hero.GetName() + ", " + Race::String( hero.GetRace() ) + " - " + std::to_string( hero.GetLevel() ), FontType::normalYellow() );
    title.draw( ( 640 - title.width() ) / 2, 6, output );
    hero.PortraitRedraw( 49, 31, PORT_BIG, output );
    const auto & crest = Assets::getImage( ICN::CREST, Color::GetIndex( hero.GetColor() ) );
    Copy( crest, 0, 0, output, 49, 130, crest.width(), crest.height() );
    Blit( Assets::getImage( ICN::HSICONS, 9 ), output, 516, 63 );
    Blit( Assets::getImage( ICN::HSICONS, 10 ), output, 552, 63 );
    Blit( Assets::getImage( ICN::HSICONS, 11 ), output, hero.GetArmy().isSpreadFormation() ? 515 : 551, 62 );
    PrimarySkillsBar primary( &hero, false, false, false );
    primary.setTableSize( { 4, 1 } );
    primary.setInBetweenItemsOffset( { 6, 0 } );
    primary.setRenderingOffset( { 156, 31 } );
    primary.Redraw( output );
    MoraleIndicator morale( &hero );
    morale.SetPos( { 514, 34 } );
    morale.Redraw();
    LuckIndicator luck( &hero );
    luck.SetPos( { 550, 34 } );
    luck.Redraw();
    ExperienceIndicator experience( &hero );
    experience.SetPos( { 512, 86 } );
    experience.Redraw();
    SpellPointsIndicator mana( &hero );
    mana.SetPos( { 550, 88 } );
    mana.Redraw();
    army( hero.GetArmy(), output, 156, 130 );
    SecondarySkillsBar skills( hero, false, false, false );
    skills.setTableSize( { 8, 1 } );
    skills.setInBetweenItemsOffset( { 5, 0 } );
    skills.SetContent( hero.GetSecondarySkills().ToVector() );
    skills.setRenderingOffset( { 3, 233 } );
    skills.Redraw( output );
    ArtifactsBar artifacts( &hero, false, true, false, false, nullptr );
    artifacts.setTableSize( { 7, 2 } );
    artifacts.setInBetweenItemsOffset( { 15, 15 } );
    artifacts.SetContent( hero.GetBagArtifacts() );
    artifacts.setRenderingOffset( { 51, 308 } );
    artifacts.Redraw( output );
    const Text movement( "Movement: " + std::to_string( hero.GetMovePoints() ), FontType::smallWhite() );
    movement.draw( 22, 460, output );
    // Indicators own background restorers; capture before those transient widgets are destroyed.
    Copy( output, destination );
}

void fheroes2::renderCastleSnapshot( Castle & castle, Image & output )
{
    output._disableTransformLayer();
    output.resize( 640, 480 );
    output.fill( 0 );
    const ScopedDrawingTarget target( output );
    Blit( Assets::getImage( ICN::STRIP, 0 ), output, 0, 256 );
    CastleDialog::BuildingsRenderQueue queue( castle, { 0, 0 } );
    CastleDialog::FadeBuilding fade;
    CastleDialog::redrawAllBuildings( output, castle, { 0, 0 }, queue, fade, 0 );
    if ( castle.isBuild( BUILD_CAPTAIN ) ) {
        const auto & portrait = castle.GetCaptain().GetPortrait( PORT_BIG );
        Copy( portrait, 0, 0, output, 5, 262, portrait.width(), portrait.height() );
    }
    else {
        const auto & crest = Assets::getImage( ICN::CREST, Color::GetIndex( castle.GetColor() ) );
        Copy( crest, 0, 0, output, 5, 262, crest.width(), crest.height() );
    }
    army( castle.GetArmy(), output, 112, 262 );
    if ( Heroes * visitor = world.GetHero( castle ) ) {
        visitor->PortraitRedraw( 5, 361, PORT_BIG, output );
        army( visitor->GetArmy(), output, 112, 361 );
    }
    else {
        const auto & emptyPortrait = Assets::getImage( ICN::STRIP, 3 );
        const auto & emptyArmy = Assets::getImage( ICN::STRIP, 11 );
        Copy( emptyPortrait, 0, 0, output, 5, 361, emptyPortrait.width(), emptyPortrait.height() );
        Copy( emptyArmy, 0, 0, output, 112, 361, emptyArmy.width(), emptyArmy.height() );
    }
    drawResourcePanel( castle.GetKingdom().GetFunds(), output, { 0, 0 } );
}
#endif
