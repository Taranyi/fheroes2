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

#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>

#include <SDL_video.h>

#include "core.h"
#include "localevent.h"
#include "screen.h"

namespace
{
    void check( const bool condition, const char * message )
    {
        if ( !condition ) {
            throw std::runtime_error( message );
        }
    }

    template <typename Function>
    void mustReject( const Function & operation )
    {
        bool rejected = false;
        try {
            operation();
        }
        catch ( const System::HeadlessInteractionError & ) {
            rejected = true;
        }
        check( rejected, "Interactive operation was not rejected before presentation initialization." );
    }

    void noPresentation()
    {
        for ( const auto component :
              { System::SystemInitializationComponent::Video, System::SystemInitializationComponent::Audio, System::SystemInitializationComponent::GameController } ) {
            check( !System::isComponentInitialized( component ), "A presentation component was initialized." );
        }
    }
}

int main( const int argc, const char * const * argv )
{
    try {
        if ( argc == 2 && ( std::string( argv[1] ) == "--dummy-probe" || std::string( argv[1] ) == "--default-probe" ) ) {
            const bool useDefaults = std::string( argv[1] ) == "--default-probe";
            const auto core
                = useDefaults
                      ? std::make_unique<System::CoreInitializer>()
                      : std::make_unique<System::CoreInitializer>( std::set<System::SystemInitializationComponent>{ System::SystemInitializationComponent::Video } );
            auto & display = fheroes2::Display::instance();
            display.setResolution( { 640, 480 } );
            check( display.width() == 640 && display.height() == 480, "Dummy driver could not allocate the display." );
            check( System::isComponentInitialized( System::SystemInitializationComponent::Audio ) == useDefaults, "Audio initialization options were not preserved." );
            std::cout << "SDL probe: driver=" << SDL_GetCurrentVideoDriver() << ", image=" << display.width() << 'x' << display.height()
                      << ", video_initialized=" << System::isComponentInitialized( System::SystemInitializationComponent::Video )
                      << ", audio_initialized=" << System::isComponentInitialized( System::SystemInitializationComponent::Audio ) << '\n';
            display.release();
            return 0;
        }
        check( !System::isHeadlessMode(), "The normal runtime default changed." );
        System::requireInteractive( "normal policy" );
        {
            const System::ScopedHeadlessMode headless;
            check( System::isHeadlessMode(), "Headless policy was not enabled." );
            {
                const System::ScopedHeadlessMode nested;
                const System::CoreInitializer core( std::set<System::SystemInitializationComponent>{} );
                noPresentation();
            }
            check( System::isHeadlessMode(), "Nested scope failed to restore headless policy." );
            mustReject( []() { const System::CoreInitializer core; } );
            mustReject( []() { (void)fheroes2::Display::instance(); } );
            mustReject( []() { LocalEvent::Get().HandleEvents(); } );
            noPresentation();
        }
        check( !System::isHeadlessMode(), "Headless scope failed to restore normal policy." );
        System::requireInteractive( "normal policy after headless" );
        noPresentation();
        std::cout << "Headless policy checks passed.\n";
        return 0;
    }
    catch ( const std::exception & error ) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
