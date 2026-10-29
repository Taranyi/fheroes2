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

#include "artifact.h"
#include "core.h"
#include "game_io.h"
#include "heroes.h"
#include "python_env_world.h"
#include "spell.h"
#include "world.h"

int main( int argc, char ** argv )
{
    if ( argc != 3 ) {
        std::cerr << "Usage: fheroes2_artifact_fixture BASE_SAVE OUTPUT_DIRECTORY\n";
        return EXIT_FAILURE;
    }
    try {
        const auto input = std::filesystem::absolute( std::filesystem::u8path( argv[1] ) );
        const auto output = std::filesystem::absolute( std::filesystem::u8path( argv[2] ) );
        std::filesystem::create_directories( output );
        for ( const char * name : { "artifacts-day1.sav", "artifacts-full-day1.sav" } ) {
            const auto file = output / name;
            if ( std::filesystem::exists( file ) && std::filesystem::equivalent( input, file ) ) {
                throw std::runtime_error( "The output must not overwrite the input save." );
            }
        }
        const System::ScopedHeadlessMode headless;
        const System::CoreInitializer core( std::set<System::SystemInitializationComponent>{} );
        fheroes2::PythonEnvWorld session( argv[0] );
        session.loadSave( input.u8string() );
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
        std::cout << "Native artifact fixtures saved in " << output.string() << '\n';
        return EXIT_SUCCESS;
    }
    catch ( const std::exception & error ) {
        std::cerr << error.what() << '\n';
        return EXIT_FAILURE;
    }
}
