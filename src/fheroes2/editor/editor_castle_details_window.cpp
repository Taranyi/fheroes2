/***************************************************************************
 *   fheroes2: https://github.com/ihhub/fheroes2                           *
 *   Copyright (C) 2024 - 2025                                             *
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

#include "editor_castle_details_window.h"

#include <algorithm>
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <iterator>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "agg_image.h"
#include "army.h"
#include "army_bar.h"
#include "buildinginfo.h"
#include "castle.h"
#include "castle_building_info.h"
#include "color.h"
#include "cursor.h"
#include "dialog.h"
#include "editor_ui_helper.h"
#include "game_hotkeys.h"
#include "game_language.h"
#include "icn.h"
#include "image.h"
#include "localevent.h"
#include "map_format_helper.h"
#include "map_format_info.h"
#include "math_base.h"
#include "pal.h"
#include "race.h"
#include "screen.h"
#include "settings.h"
#include "statusbar.h"
#include "translations.h"
#include "ui_button.h"
#include "ui_dialog.h"
#include "ui_text.h"
#include "ui_tool.h"
#include "ui_window.h"

namespace
{
    class BuildingData
    {
    public:
        explicit BuildingData( BuildingType buildingType, const int race, const BuildingType builtBuildings, const BuildingType restrictedBuildings )
            : _mainBuildingType( buildingType )
            , _race( race )
        {
            if ( builtBuildings & _mainBuildingType ) {
                _builtId = 0;
            }
            else if ( restrictedBuildings & _mainBuildingType ) {
                _restrictedId = 0;
            }

            for ( BuildingType upgradedBuildingType = fheroes2::getUpgradeForBuilding( _race, _mainBuildingType ); upgradedBuildingType != buildingType;
                  upgradedBuildingType = fheroes2::getUpgradeForBuilding( _race, upgradedBuildingType ) ) {
                if ( builtBuildings & upgradedBuildingType ) {
                    _builtId = _buildingVariants;
                }
                else if ( restrictedBuildings & upgradedBuildingType ) {
                    _restrictedId = _buildingVariants;
                }

                ++_buildingVariants;
                buildingType = upgradedBuildingType;
            }
        }

        void setPosition( const int32_t posX, const int32_t posY )
        {
            _area.x = posX;
            _area.y = posY;
            _buildArea.x = posX;
            _buildArea.y = posY;
            _banArea.x = posX + _buildArea.width;
            _banArea.y = posY;
        }

        void resetBuilding()
        {
            _builtId = -1;
            _restrictedId = -1;
        }

        const fheroes2::Rect & getArea() const
        {
            return _area;
        }

        std::vector<BuildingType> getBuildLevel() const
        {
            if ( _builtId < 0 ) {
                return {};
            }

            const int8_t levelsBuilt = _builtId + 1;
            std::vector<BuildingType> buildings;
            buildings.reserve( levelsBuilt );
            for ( int8_t i = 0; i < levelsBuilt; ++i ) {
                buildings.push_back( _getBuildingType( i ) );
            }
            return buildings;
        }

        BuildingType getRestrictLevel() const
        {
            return _getBuildingType( _restrictedId );
        }

        bool queueEventProcessing( const bool restrictionMode )
        {
            LocalEvent & le = LocalEvent::Get();

            if ( le.MouseClickLeft( _area ) ) {
                if ( restrictionMode ) {
                    if ( _restrictedId <= -1 ) {
                        _restrictedId = _buildingVariants;
                    }

                    --_restrictedId;

                    if ( _builtId != -1 && _builtId >= _restrictedId ) {
                        _builtId = _restrictedId - 1;
                    }
                }
                else {
                    ++_builtId;

                    if ( _builtId >= _buildingVariants ) {
                        _builtId = -1;
                    }
                    else if ( _restrictedId != -1 && _builtId >= _restrictedId ) {
                        _restrictedId = ( _builtId < _buildingVariants - 1 ) ? _builtId + 1 : -1;
                    }
                }

                return true;
            }

            if ( le.isMouseRightButtonPressedInArea( _area ) ) {
                const BuildingType building = _getBuildindTypeForRender();
                std::string description = BuildingInfo::getBuildingDescription( _race, building );
                const std::string requirement = fheroes2::getBuildingRequirementString( _race, building );

                if ( !requirement.empty() ) {
                    description += "\n\n";
                    description += _( "Requires:" );
                    description += "\n";
                    description += requirement;
                }

                fheroes2::showStandardTextMessage( Castle::GetStringBuilding( building, _race ), std::move( description ), Dialog::ZERO );
            }

            return false;
        }

        std::string getSetStatusMessage() const
        {
            return fheroes2::getBuildingName( _race, _getBuildindTypeForRender() );
        }

        void redraw( const bool isNotDefault ) const
        {
            fheroes2::Display & display = fheroes2::Display::instance();
            const int index = fheroes2::getIndexBuildingSprite( _getBuildindTypeForRender() );

            const int buildingIcnId = ICN::getBuildingIcnId( _race );
            const fheroes2::Sprite & buildingImage = ( buildingIcnId == ICN::UNKNOWN )
                                                         ? fheroes2::AGG::GetICN( Settings::Get().isEvilInterfaceEnabled() ? ICN::CASLXTRA_EVIL : ICN::CASLXTRA, 0 )
                                                         : fheroes2::AGG::GetICN( buildingIcnId, index );

            const fheroes2::Rect buildingImageRoi( _area.x + 1, _area.y + 1, 135, 57 );

            if ( isNotDefault ) {
                fheroes2::Copy( buildingImage, 0, 0, display, buildingImageRoi );
            }
            else {
                // Apply the blur effect originally used for the Holy Shout spell.
                fheroes2::Copy( fheroes2::CreateHolyShoutEffect( buildingImage, 1, 0 ), 0, 0, display, buildingImageRoi );
                fheroes2::ApplyPalette( display, buildingImageRoi.x, buildingImageRoi.y, display, buildingImageRoi.x, buildingImageRoi.y, buildingImageRoi.width,
                                        buildingImageRoi.height, PAL::GetPalette( PAL::PaletteType::DARKENING ) );
            }

            // Build and restrict status indicator.
            const int32_t maxUpgrades = static_cast<int32_t>( _buildingVariants );
            for ( int32_t i = 0; i < maxUpgrades; ++i ) {
                if ( _restrictedId != -1 && i >= _restrictedId ) {
                    // Render the restricted sign: gray cross.
                    fheroes2::Sprite denySign( fheroes2::AGG::GetICN( ICN::TOWNWIND, 12 ) );
                    fheroes2::ApplyPalette( denySign, PAL::CombinePalettes( PAL::GetPalette( PAL::PaletteType::GRAY ), PAL::GetPalette( PAL::PaletteType::DARKENING ) ) );

                    fheroes2::Blit( denySign, display, _area.x + _area.width - ( maxUpgrades - i ) * 20 - denySign.width() / 2, _area.y + 48 - denySign.height() / 2 );
                    continue;
                }

                const int icnId = ( i > _builtId ) ? ICN::CELLWIN : ICN::TOWNWIND;
                const uint32_t icnIndex = ( i > _builtId ) ? 5 : 11;
                const fheroes2::Sprite & mark = fheroes2::AGG::GetICN( icnId, icnIndex );
                fheroes2::Blit( mark, display, _area.x + _area.width - ( maxUpgrades - i ) * 20 - mark.width() / 2, _area.y + 48 - mark.height() / 2 );
            }

            if ( _builtId > -1 ) {
                const fheroes2::Sprite & textBackground = fheroes2::AGG::GetICN( ICN::BLDGXTRA, 0 );
                fheroes2::Copy( textBackground, 0, 58, display, _area.x, _area.y + 58, _area.width, textBackground.height() );
            }
            else if ( _restrictedId != 0 ) {
                const fheroes2::Sprite & textBackground = fheroes2::AGG::GetICN( ICN::CASLXTRA, 1 );
                fheroes2::Copy( textBackground, 0, 0, display, _area.x, _area.y + 58, _area.width, textBackground.height() );
            }

            if ( _restrictedId > -1 ) {
                fheroes2::Sprite textBackground( fheroes2::AGG::GetICN( ICN::CASLXTRA, 2 ) );
                fheroes2::ApplyPalette( textBackground, 6, 1, textBackground, 6, 1, 125, 12,
                                        PAL::CombinePalettes( PAL::GetPalette( PAL::PaletteType::GRAY ), PAL::GetPalette( PAL::PaletteType::DARKENING ) ) );

                if ( _restrictedId == 0 ) {
                    fheroes2::Copy( textBackground, 0, 0, display, _area.x, _area.y + 58, _area.width - 5, textBackground.height() );
                }
                else {
                    fheroes2::CreateDitheringTransition( textBackground, _buildArea.width - 5, 0, display, _banArea.x - 5, _area.y + 58, 10, textBackground.height(),
                                                         true, false );
                    fheroes2::Copy( textBackground, _buildArea.width + 5, 0, display, _banArea.x + 5, _area.y + 58, _banArea.width - 5, textBackground.height() );
                }
            }

            if ( !isNotDefault ) {
                // Make the header darker for the default buildings.
                fheroes2::ApplyPalette( display, _area.x + 6, _area.y + 59, display, _area.x + 6, _area.y + 59, 125, 12, PAL::GetPalette( PAL::PaletteType::DARKENING ) );
            }

            const fheroes2::Text buildingName( Castle::GetStringBuilding( _getBuildindTypeForRender(), _race ), fheroes2::FontType::smallWhite() );
            buildingName.draw( _area.x + 68 - buildingName.width() / 2, _area.y + 61, display );
        }

    private:
        BuildingType _getBuildindTypeForRender() const
        {
            if ( _builtId < 1 ) {
                return _mainBuildingType;
            }

            return _getBuildingType( _builtId );
        }

        BuildingType _getBuildingType( const int8_t level ) const
        {
            if ( level < 0 ) {
                return BUILD_NOTHING;
            }

            BuildingType building = _mainBuildingType;
            for ( int8_t i = 0; i < level; ++i ) {
                building = fheroes2::getUpgradeForBuilding( _race, building );
            }

            return building;
        }

        BuildingType _mainBuildingType{ BUILD_NOTHING };
        int _race{ Race::NONE };
        int8_t _builtId{ -1 };
        int8_t _restrictedId{ -1 };
        int8_t _buildingVariants{ 1 };
        fheroes2::Rect _area{ 0, 0, 137, 70 };
        fheroes2::Rect _buildArea{ 0, 0, 69, 70 };
        fheroes2::Rect _banArea{ 0, 0, 68, 70 };
    };

    std::string getCastleName( const std::string & customName, const bool isTown )
    {
        if ( !customName.empty() ) {
            return customName;
        }

        return isTown ? _( "Random Town Name" ) : _( "Random Castle Name" );
    }
}

namespace Editor
{
    bool castleDetailsDialog( Maps::Map_Format::CastleMetadata & castleMetadata, const int race, const PlayerColor color, const fheroes2::SupportedLanguage language )
    {
        const CursorRestorer cursorRestorer( true, Cursor::POINTER );

        fheroes2::Display & display = fheroes2::Display::instance();

        fheroes2::StandardWindow window( fheroes2::Display::DEFAULT_WIDTH, fheroes2::Display::DEFAULT_HEIGHT, false );
        const fheroes2::Rect dialogRoi = window.activeArea();
        const fheroes2::Rect dialogWithShadowRoi = window.totalArea();

        const bool isEvilInterface = Settings::Get().isEvilInterfaceEnabled();

        const fheroes2::Sprite & constructionBackground = fheroes2::AGG::GetICN( isEvilInterface ? ICN::CASLWIND_EVIL : ICN::CASLWIND, 0 );
        const int32_t backgroundHeight = constructionBackground.height();

        // Use the left part of town construction dialog.
        const int32_t rightPartOffsetX = 438;
        const int32_t rightPartWidth = dialogRoi.width - rightPartOffsetX;
        fheroes2::Blit( constructionBackground, 0, 0, display, dialogRoi.x, dialogRoi.y, rightPartOffsetX, backgroundHeight );
        // Use the right part of standard background dialog.
        fheroes2::Copy( fheroes2::AGG::GetICN( isEvilInterface ? ICN::STONEBAK_EVIL : ICN::STONEBAK, 0 ), rightPartOffsetX, 0, display, dialogRoi.x + rightPartOffsetX,
                        dialogRoi.y, rightPartWidth, backgroundHeight );
        // Add horizontal separators.
        fheroes2::Copy( constructionBackground, rightPartOffsetX, 251, display, dialogRoi.x + rightPartOffsetX, dialogRoi.y + 226, rightPartWidth, 4 );
        fheroes2::Copy( constructionBackground, rightPartOffsetX, 251, display, dialogRoi.x + rightPartOffsetX, dialogRoi.y + 306, rightPartWidth, 4 );

        // Castle name background.
        const fheroes2::Sprite & statusBarSprite = fheroes2::AGG::GetICN( ICN::CASLBAR, 0 );
        const int32_t statusBarHeight = statusBarSprite.height();
        const fheroes2::Rect nameArea( dialogRoi.x + rightPartOffsetX, dialogRoi.y + 1, rightPartWidth, statusBarHeight - 2 );
        fheroes2::Copy( statusBarSprite, 17, 0, display, nameArea.x, dialogRoi.y, nameArea.width, statusBarHeight );

        const bool isTown = std::find( castleMetadata.builtBuildings.begin(), castleMetadata.builtBuildings.end(), BUILD_CASTLE ) == castleMetadata.builtBuildings.end();

        // Castle name text.
        auto drawCastleName = [&castleMetadata, &display, &nameArea, isTown]() {
            // TODO: use language for castle name. At the moment it is disabled.
            fheroes2::Text text( getCastleName( castleMetadata.customName, isTown ), fheroes2::FontType::normalWhite() );

            text.fitToOneRow( nameArea.width );
            text.drawInRoi( nameArea.x + ( nameArea.width - text.width() ) / 2, nameArea.y + 2, display, nameArea );
        };
        drawCastleName();

        // Allow castle building checkbox.
        fheroes2::Point dstPt( dialogRoi.x + rightPartOffsetX + 10, dialogRoi.y + 130 );
        fheroes2::MovableSprite allowCastleSign;
        fheroes2::Rect allowCastleArea;
        if ( isTown ) {
            allowCastleArea = drawCheckboxWithText( allowCastleSign, _( "Allow Castle build" ), display, dstPt.x, dstPt.y, isEvilInterface, rightPartWidth - 10 );
            if ( std::find( castleMetadata.bannedBuildings.begin(), castleMetadata.bannedBuildings.end(), BUILD_CASTLE ) == castleMetadata.bannedBuildings.end() ) {
                allowCastleSign.show();
            }
            else {
                allowCastleSign.hide();
            }
        }

        // Default buildings checkbox indicator.
        dstPt.y += 30;
        fheroes2::MovableSprite defaultBuildingsSign;
        const fheroes2::Rect defaultBuildingsArea
            = drawCheckboxWithText( defaultBuildingsSign, _( "Default Buildings" ), display, dstPt.x, dstPt.y, isEvilInterface, rightPartWidth - 10 );
        castleMetadata.customBuildings ? defaultBuildingsSign.hide() : defaultBuildingsSign.show();

        // Build restrict mode button. We use center_center padding to make sure localized variable-width buttons are centered too.
        fheroes2::ButtonSprite buttonRestrictBuilding;

        const char * translatedText = fheroes2::getSupportedText( gettext_noop( "RESTRICT" ), fheroes2::FontType::buttonReleasedWhite() );
        window.renderTextAdaptedButtonSprite( buttonRestrictBuilding, translatedText, { 219, -32 }, fheroes2::StandardWindow::Padding::CENTER_CENTER );

        const bool isNeutral = ( color == PlayerColor::NONE );

        // Castle army.
        dstPt.y = dialogRoi.y + 311;
        fheroes2::MovableSprite defaultArmySign;
        fheroes2::Rect defaultArmyArea;
        if ( isNeutral ) {
            defaultArmyArea = drawCheckboxWithText( defaultArmySign, _( "Default Army" ), display, dstPt.x, dstPt.y, isEvilInterface, rightPartWidth - 10 );

            if ( Maps::isDefaultCastleDefenderArmy( castleMetadata ) ) {
                defaultArmySign.show();
            }
            else {
                defaultArmySign.hide();
            }
        }
        else {
            defaultArmySign.hide();

            const fheroes2::Text armyText( isTown ? _( "Town Army" ) : _( "Castle Army" ), fheroes2::FontType::normalWhite() );
            armyText.drawInRoi( dialogRoi.x + rightPartOffsetX + ( rightPartWidth - armyText.width() ) / 2, dstPt.y + 4, display, dialogRoi );
        }

        Army castleArmy;
        // Load army from metadata.
        Maps::loadCastleArmy( castleArmy, castleMetadata );
        ArmyBar armyBar( &castleArmy, true, false, true, false );
        armyBar.setTableSize( { 3, 2 } );
        armyBar.setCustomItemsCountInRow( { 2, 3 } );
        armyBar.setInBetweenItemsOffset( { 3, 3 } );
        armyBar.setRenderingOffset( { dialogRoi.x + rightPartOffsetX + 33, dialogRoi.y + 332 } );
        armyBar.Redraw( display );

        const BuildingType metadataBuildings = static_cast<BuildingType>( Maps::getBuildingsFromVector( castleMetadata.builtBuildings ) );
        const BuildingType metadataRestrictedBuildings = static_cast<BuildingType>( Maps::getBuildingsFromVector( castleMetadata.bannedBuildings ) );

        assert( ( metadataBuildings & metadataRestrictedBuildings ) == 0 );

        const size_t buildingsSize = 19;
        std::array<BuildingData, buildingsSize> buildings{ BuildingData( DWELLING_MONSTER1, race, metadataBuildings, metadataRestrictedBuildings ),
                                                           BuildingData( DWELLING_MONSTER2, race, metadataBuildings, metadataRestrictedBuildings ),
                                                           BuildingData( DWELLING_MONSTER3, race, metadataBuildings, metadataRestrictedBuildings ),
                                                           BuildingData( DWELLING_MONSTER4, race, metadataBuildings, metadataRestrictedBuildings ),
                                                           BuildingData( DWELLING_MONSTER5, race, metadataBuildings, metadataRestrictedBuildings ),
                                                           BuildingData( DWELLING_MONSTER6, race, metadataBuildings, metadataRestrictedBuildings ),
                                                           BuildingData( BUILD_MAGEGUILD1, race, metadataBuildings, metadataRestrictedBuildings ),
                                                           BuildingData( race == Race::NECR ? BUILD_SHRINE : BUILD_TAVERN, race, metadataBuildings,
                                                                         metadataRestrictedBuildings ),
                                                           BuildingData( BUILD_THIEVESGUILD, race, metadataBuildings, metadataRestrictedBuildings ),
                                                           BuildingData( BUILD_SHIPYARD, race, metadataBuildings, metadataRestrictedBuildings ),
                                                           BuildingData( BUILD_STATUE, race, metadataBuildings, metadataRestrictedBuildings ),
                                                           BuildingData( BUILD_MARKETPLACE, race, metadataBuildings, metadataRestrictedBuildings ),
                                                           BuildingData( BUILD_WELL, race, metadataBuildings, metadataRestrictedBuildings ),
                                                           BuildingData( BUILD_WEL2, race, metadataBuildings, metadataRestrictedBuildings ),
                                                           BuildingData( BUILD_SPEC, race, metadataBuildings, metadataRestrictedBuildings ),
                                                           BuildingData( BUILD_LEFTTURRET, race, metadataBuildings, metadataRestrictedBuildings ),
                                                           BuildingData( BUILD_RIGHTTURRET, race, metadataBuildings, metadataRestrictedBuildings ),
                                                           BuildingData( BUILD_MOAT, race, metadataBuildings, metadataRestrictedBuildings ),
                                                           BuildingData( BUILD_CAPTAIN, race, metadataBuildings, metadataRestrictedBuildings ) };

        dstPt.x = dialogRoi.x + 5;
        dstPt.y = dialogRoi.y + 2;

        for ( size_t i = 0; i < buildingsSize - 1; ++i ) {
            buildings[i].setPosition( dstPt.x + ( static_cast<int32_t>( i ) % 3 ) * 144, dstPt.y );
            buildings[i].redraw( defaultBuildingsSign.isHidden() );
            if ( i % 3 == 2 ) {
                dstPt.y += ( i == 5 || i == 14 ) ? 80 : 75;
            }
        }

        // Captain building.
        dstPt.x = dialogRoi.x + rightPartOffsetX + 33;
        dstPt.y = dialogRoi.y + 232;
        const fheroes2::Sprite & buildingFrame = fheroes2::AGG::GetICN( ICN::BLDGXTRA, 0 );
        fheroes2::Blit( buildingFrame, display, dstPt.x, dstPt.y );
        buildings.back().setPosition( dstPt.x, dstPt.y );
        buildings.back().redraw( defaultBuildingsSign.isHidden() );

        // Reset castle's name button.
        fheroes2::Button buttonResetCastleName;
        window.renderButton( buttonResetCastleName, isEvilInterface ? ICN::BUTTON_RESET_EVIL : ICN::BUTTON_RESET_GOOD, 0, 1, { 56, 24 },
                             fheroes2::StandardWindow::Padding::TOP_RIGHT );

        // Reset army button.
        fheroes2::Button buttonResetArmy;
        window.renderButton( buttonResetArmy, isEvilInterface ? ICN::BUTTON_RESET_EVIL : ICN::BUTTON_RESET_GOOD, 0, 1, { 56, 24 },
                             fheroes2::StandardWindow::Padding::BOTTOM_RIGHT );

        // OKAY button.
        const fheroes2::Point statusBarOffset{ dialogRoi.x, dialogRoi.y + dialogRoi.height - statusBarHeight };

        fheroes2::Button buttonOkay( statusBarOffset.x, statusBarOffset.y, ICN::BUTTON_OKAY_TOWN, 0, 1 );
        buttonOkay.draw();

        // EXIT button.
        const int32_t buttonExitWidth = fheroes2::AGG::GetICN( ICN::BUTTON_GUILDWELL_EXIT, 0 ).width();
        fheroes2::Button buttonExit( statusBarOffset.x + dialogRoi.width - buttonExitWidth, statusBarOffset.y, ICN::BUTTON_GUILDWELL_EXIT, 0, 1 );
        buttonExit.draw();

        // The original status bar image is much longer.
        // Since we are adding 2 buttons on each side we have to copy only left and right parts of the bar.
        const int32_t buttonOkayWidth = fheroes2::AGG::GetICN( ICN::BUTTON_OKAY_TOWN, 0 ).width();
        const int32_t statusBarWidth = dialogRoi.width - buttonExitWidth - buttonOkayWidth;
        fheroes2::Copy( statusBarSprite, 0, 0, display, statusBarOffset.x + buttonOkayWidth, statusBarOffset.y, statusBarWidth / 2, statusBarHeight );
        const int32_t statusBarSecondPart = statusBarWidth - statusBarWidth / 2;
        fheroes2::Copy( statusBarSprite, statusBarSprite.width() - statusBarSecondPart, 0, display, statusBarOffset.x + buttonOkayWidth + statusBarWidth / 2,
                        statusBarOffset.y, statusBarSecondPart, statusBarHeight );

        StatusBar statusBar;
        // The status bar has decorations on both sides.
        // It is important not to render text over them.
        constexpr int32_t decorationsWidth{ 16 };
        statusBar.setRoi( { dialogRoi.x + buttonOkayWidth + decorationsWidth, statusBarOffset.y, statusBarWidth - 2 * decorationsWidth, 0 } );

        display.render( dialogWithShadowRoi );

        LocalEvent & le = LocalEvent::Get();

        std::string message;
        bool buildingRestriction = false;

        while ( le.HandleEvents() ) {
            buttonOkay.drawOnState( le.isMouseLeftButtonPressedAndHeldInArea( buttonOkay.area() ) );
            buttonExit.drawOnState( le.isMouseLeftButtonPressedAndHeldInArea( buttonExit.area() ) );
            buttonResetCastleName.drawOnState( le.isMouseLeftButtonPressedAndHeldInArea( buttonResetCastleName.area() ) );
            buttonResetArmy.drawOnState( le.isMouseLeftButtonPressedAndHeldInArea( buttonResetArmy.area() ) );

            if ( le.MouseClickLeft( buttonOkay.area() ) || Game::HotKeyPressEvent( Game::HotKeyEvent::DEFAULT_OKAY ) ) {
                break;
            }

            if ( le.MouseClickLeft( buttonExit.area() ) || Game::HotKeyPressEvent( Game::HotKeyEvent::DEFAULT_CANCEL ) ) {
                return false;
            }

            if ( le.MouseClickLeft( buttonRestrictBuilding.area() ) ) {
                buildingRestriction = !buildingRestriction;
            }

            buttonRestrictBuilding.drawOnState( buildingRestriction || le.isMouseLeftButtonPressedAndHeldInArea( buttonRestrictBuilding.area() ) );

            if ( le.isMouseCursorPosInArea( nameArea ) ) {
                message = _( "Click to change the Castle name." );

                bool redrawName = false;
                if ( le.MouseClickLeft( nameArea ) ) {
                    std::string res = castleMetadata.customName;

                    // TODO: use the provided language to set the castle's name.
                    (void)language;

                    const fheroes2::Text body{ _( "Enter Castle name" ), fheroes2::FontType::normalWhite() };
                    if ( Dialog::inputString( fheroes2::Text{}, body, res, 30, false, fheroes2::SupportedLanguage::English ) && !res.empty() ) {
                        castleMetadata.customName = std::move( res );
                        redrawName = true;
                    }
                }
                else if ( le.isMouseRightButtonPressedInArea( nameArea ) ) {
                    fheroes2::showStandardTextMessage( getCastleName( castleMetadata.customName, isTown ), {}, Dialog::ZERO );
                }

                if ( redrawName ) {
                    // Restore name background
                    fheroes2::Copy( statusBarSprite, 17, 1, display, nameArea );
                    drawCastleName();
                    display.render( nameArea );
                }
            }
            else if ( le.isMouseCursorPosInArea( buttonResetCastleName.area() ) ) {
                message = _( "Reset the Castle name." );

                if ( le.MouseClickLeft( buttonResetCastleName.area() ) ) {
                    castleMetadata.customName.clear();

                    fheroes2::Copy( statusBarSprite, 17, 1, display, nameArea );
                    drawCastleName();
                    display.render( nameArea );
                }
                else if ( le.isMouseRightButtonPressedInArea( buttonResetCastleName.area() ) ) {
                    fheroes2::showStandardTextMessage( _( "Reset" ), message, Dialog::ZERO );
                }
            }
            else if ( isTown && le.isMouseCursorPosInArea( allowCastleArea ) ) {
                message = _( "Allow to build a castle in this town." );

                if ( le.MouseClickLeft( allowCastleArea ) ) {
                    allowCastleSign.isHidden() ? allowCastleSign.show() : allowCastleSign.hide();
                    display.render( allowCastleSign.getArea() );
                }
                else if ( le.isMouseRightButtonPressedInArea( allowCastleArea ) ) {
                    fheroes2::showStandardTextMessage( _( "Allow Castle build" ), message, Dialog::ZERO );
                }
            }
            else if ( le.isMouseCursorPosInArea( defaultBuildingsArea ) ) {
                message = _( "Toggle the use of default buildings. Custom buildings will be reset!" );

                if ( le.MouseClickLeft( defaultBuildingsArea ) ) {
                    if ( defaultBuildingsSign.isHidden() ) {
                        // Reset all buildings to their build and restrict default states.
                        for ( BuildingData & building : buildings ) {
                            building.resetBuilding();
                            building.redraw( false );
                        }

                        defaultBuildingsSign.show();
                        display.render( dialogRoi );
                    }
                    else {
                        defaultBuildingsSign.hide();

                        for ( const BuildingData & building : buildings ) {
                            building.redraw( true );
                        }

                        display.render( dialogRoi );
                    }
                }
                else if ( le.isMouseRightButtonPressedInArea( defaultBuildingsArea ) ) {
                    fheroes2::showStandardTextMessage( _( "Default Buildings" ), message, Dialog::ZERO );
                }
            }
            else if ( le.isMouseCursorPosInArea( buttonRestrictBuilding.area() ) ) {
                message = _( "Toggle building construction restriction mode." );

                if ( le.isMouseRightButtonPressedInArea( buttonRestrictBuilding.area() ) ) {
                    fheroes2::showStandardTextMessage( _( "Restrict Building Construction" ), message, Dialog::ZERO );
                }
            }
            else if ( isNeutral && le.isMouseCursorPosInArea( defaultArmyArea ) ) {
                message = _( "Use default defenders army." );

                if ( le.MouseClickLeft( defaultArmyArea ) ) {
                    if ( defaultArmySign.isHidden() ) {
                        defaultArmySign.show();
                        castleArmy.Reset( false );
                        armyBar.Redraw( display );
                        display.render( dialogRoi );
                    }
                    else {
                        defaultArmySign.hide();
                        display.render( defaultArmySign.getArea() );
                    }
                }
                else if ( le.isMouseRightButtonPressedInArea( defaultArmyArea ) ) {
                    fheroes2::showStandardTextMessage( _( "Default Army" ), message, Dialog::ZERO );
                }
            }
            else if ( le.isMouseCursorPosInArea( buttonResetArmy.area() ) ) {
                message = _( "Reset the army." );
                if ( le.MouseClickLeft( buttonResetArmy.area() ) ) {
                    castleArmy.Reset( false );
                    armyBar.Redraw( display );
                    display.render( armyBar.GetArea() );
                }
                else if ( le.isMouseRightButtonPressedInArea( buttonResetArmy.area() ) ) {
                    fheroes2::showStandardTextMessage( _( "Reset" ), message, Dialog::ZERO );
                }
            }
            else if ( le.isMouseCursorPosInArea( armyBar.GetArea() ) ) {
                if ( armyBar.QueueEventProcessing( &message ) ) {
                    armyBar.Redraw( display );

                    defaultArmySign.hide();
                    display.render( dialogRoi );
                }

                if ( message.empty() ) {
                    message = _( "Set custom Castle Army." );
                }
            }
            else if ( le.isMouseCursorPosInArea( buttonOkay.area() ) ) {
                message = _( "Click to accept the changes made." );

                if ( le.isMouseRightButtonPressedInArea( buttonOkay.area() ) ) {
                    fheroes2::showStandardTextMessage( _( "Okay" ), message, Dialog::ZERO );
                }
            }
            else if ( le.isMouseCursorPosInArea( buttonExit.area() ) ) {
                message = _( "Exit this dialog, discarding the changes made." );

                if ( le.isMouseRightButtonPressedInArea( buttonExit.area() ) ) {
                    fheroes2::showStandardTextMessage( _( "Exit" ), message, Dialog::ZERO );
                }
            }
            else {
                for ( size_t i = 0; i < buildingsSize; ++i ) {
                    if ( le.isMouseCursorPosInArea( buildings[i].getArea() ) ) {
                        message = buildings[i].getSetStatusMessage();

                        if ( buildings[i].queueEventProcessing( buildingRestriction ) ) {
                            if ( defaultBuildingsSign.isHidden() ) {
                                buildings[i].redraw( true );
                                display.render( buildings[i].getArea() );
                            }
                            else {
                                // The building properties have been changed. Uncheck the default buildings checkbox.
                                defaultBuildingsSign.hide();

                                for ( const BuildingData & building : buildings ) {
                                    building.redraw( true );
                                }

                                display.render( dialogRoi );
                            }
                        }

                        break;
                    }
                }
            }

            if ( message.empty() ) {
                statusBar.ShowMessage( _( "Castle Settings" ) );
            }
            else {
                statusBar.ShowMessage( std::move( message ) );
                message.clear();
            }
        }

        // Update army in metadata.
        if ( isNeutral && !defaultArmySign.isHidden() ) {
            Maps::setDefaultCastleDefenderArmy( castleMetadata );
        }
        else {
            Maps::saveCastleArmy( castleArmy, castleMetadata );
        }

        // Update buildings data.
        castleMetadata.builtBuildings.clear();
        castleMetadata.bannedBuildings.clear();

        // Build main buildings for town or castle.
        castleMetadata.builtBuildings.push_back( isTown ? BUILD_TENT : BUILD_CASTLE );

        if ( isTown && allowCastleSign.isHidden() ) {
            castleMetadata.bannedBuildings.push_back( BUILD_CASTLE );
        }

        castleMetadata.customBuildings = defaultBuildingsSign.isHidden();

        if ( castleMetadata.customBuildings ) {
            for ( const BuildingData & building : buildings ) {
                std::vector<BuildingType> buildingLevels = building.getBuildLevel();
                std::move( buildingLevels.begin(), buildingLevels.end(), std::back_inserter( castleMetadata.builtBuildings ) );

                if ( const BuildingType buildId = building.getRestrictLevel(); buildId != BUILD_NOTHING ) {
                    castleMetadata.bannedBuildings.push_back( buildId );
                }
            }
        }

        return true;
    }
}
