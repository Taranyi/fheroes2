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

#pragma once

#if defined( FHEROES2_ENABLE_PYTHON_ENV )

#include <cstdint>
#include <functional>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

#include "../../thirdparty/nlohmann/json.hpp"

namespace AGG
{
    class AGGInitializer;
}

namespace fheroes2
{
    class Image;
    namespace h2d
    {
        class H2DInitializer;
    }
    class PythonEnvError final : public std::runtime_error
    {
    public:
        PythonEnvError( std::string code, const std::string & message );
        const std::string code;
    };

    // Adapter over native World/Settings and gameplay calls; game rules stay in the existing engine.
    class PythonEnvWorld final
    {
    public:
        explicit PythonEnvWorld( std::string executablePath );
        ~PythonEnvWorld();
        PythonEnvWorld( const PythonEnvWorld & ) = delete;
        PythonEnvWorld & operator=( const PythonEnvWorld & ) = delete;

        bool loaded() const;
        nlohmann::json loadSave( const std::string & path, std::optional<uint32_t> seed = {} );
        nlohmann::json newGame( const std::string & path, uint32_t seed, int playerId, int difficulty );
        nlohmann::json getState( bool includeSerialized ) const;
        nlohmann::json getCastleOptions( uint32_t castleId ) const;
        nlohmann::json getArmyOptions( const nlohmann::json & params ) const;
        bool waiting() const;
        void startSession( int playerId, const std::function<void( const nlohmann::json & )> & wait );
        nlohmann::json getDecision() const;
        nlohmann::json dispatch( const std::string & action, const nlohmann::json & token, const nlohmann::json & params, const std::function<void()> & choiceWait = {} );
        nlohmann::json actionResult() const;
        nlohmann::json render( const nlohmann::json & params );

    private:
        void clear();
        void ensureGraphicsData();
        const char * decisionPhase() const;

        const std::string _executablePath;
        std::unique_ptr<AGG::AGGInitializer> _resources;
        std::unique_ptr<h2d::H2DInitializer> _renderResources;
        bool _loaded{ false };
        uint64_t _stateVersion{ 0 };
        uint64_t _episodeId{ 0 };
        bool _turnPrepared{ false };
        nlohmann::json _events = nlohmann::json::array();
        nlohmann::json _armyMeeting = nullptr;
        nlohmann::json _pendingChoice = nullptr;
        nlohmann::json _battleState = nullptr;
        std::function<void( Image & )> _battleRender;
        int64_t _choiceAnswer{ 0 };
        uint64_t _nextChoiceId{ 0 };
        const std::string _sessionId;
        uint64_t _decisionId{ 0 };
        int _controllerPlayer{ 0 };
        bool _waiting{ false };
        std::vector<std::string> _warnings;
    };
}

#endif
