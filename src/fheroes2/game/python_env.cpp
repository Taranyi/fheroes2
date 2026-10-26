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

#include "python_env.h"

#if defined( FHEROES2_ENABLE_PYTHON_ENV )

#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <exception>
#include <iostream>
#include <istream>
#include <limits>
#include <ostream>
#include <stdexcept>
#include <string>

#include "../../thirdparty/nlohmann/json.hpp"
#include "python_env_world.h"
#include "version.h"

namespace
{
    using Json = nlohmann::json;

    constexpr uint32_t protocolVersion{ 1 };
    constexpr size_t maxRequestBytes{ 65536 };
    constexpr size_t maxResponseBytes{ 64 * 1024 * 1024 };
    constexpr int maxNestingDepth{ 16 };

    enum class LineStatus
    {
        Ready,
        EndOfInput,
        TooLong,
        Incomplete
    };

    LineStatus readRequest( std::istream & input, std::string & line )
    {
        line.clear();
        bool tooLong = false;
        char character = 0;

        // Drain oversized records without retaining unbounded input in memory.
        while ( input.get( character ) ) {
            if ( character == '\n' ) {
                return tooLong ? LineStatus::TooLong : LineStatus::Ready;
            }
            if ( line.size() < maxRequestBytes ) {
                line.push_back( character );
            }
            else {
                tooLong = true;
            }
        }

        if ( tooLong ) {
            return LineStatus::TooLong;
        }
        return line.empty() ? LineStatus::EndOfInput : LineStatus::Incomplete;
    }

    Json capabilities( const bool loaded )
    {
        return { { "commands", { "hello", "capabilities", "load_save", "get_state", "close" } },
                 { "max_request_bytes", maxRequestBytes },
                 { "max_response_bytes", maxResponseBytes },
                 { "game_initialized", loaded },
                 { "state_queries", true },
                 { "omniscient_state", true },
                 { "player_observations", false },
                 { "simulation", false },
                 { "render", false },
                 { "headless_gameplay", false } };
    }

    bool sendResult( std::ostream & output, const Json & id, const Json & result )
    {
        std::string message = Json( { { "api_version", protocolVersion }, { "id", id }, { "result", result } } ).dump( -1, ' ', false, Json::error_handler_t::replace );
        if ( message.size() >= maxResponseBytes ) {
            message = Json( { { "api_version", protocolVersion },
                              { "id", id },
                              { "error", { { "code", "response_too_large" }, { "message", "State exceeds 64 MiB. Retry without the serialized payload." } } } } )
                          .dump();
        }
        output << message << '\n' << std::flush;
        return output.good();
    }

    bool sendError( std::ostream & output, const Json & id, const char * code, const char * message )
    {
        output << Json( { { "api_version", protocolVersion }, { "id", id }, { "error", { { "code", code }, { "message", message } } } } ).dump() << '\n' << std::flush;
        return output.good();
    }

    class DiagnosticRedirect final
    {
    public:
        DiagnosticRedirect()
            : _previous( std::cout.rdbuf( std::cerr.rdbuf() ) )
        {}
        ~DiagnosticRedirect()
        {
            std::cout.rdbuf( _previous );
        }
        DiagnosticRedirect( const DiagnosticRedirect & ) = delete;
        DiagnosticRedirect & operator=( const DiagnosticRedirect & ) = delete;

    private:
        std::streambuf * _previous;
    };

    Json execute( const std::string & method, const Json & params, fheroes2::PythonEnvWorld & world )
    {
        if ( method == "load_save" ) {
            if ( params.size() != 1 || !params.contains( "path" ) || !params["path"].is_string() || params["path"].get_ref<const std::string &>().empty() ) {
                throw fheroes2::PythonEnvError( "invalid_request", "load_save requires exactly one nonempty path string." );
            }
            const DiagnosticRedirect redirect;
            return world.loadSave( params["path"].get<std::string>() );
        }
        if ( method == "get_state" ) {
            if ( params.size() > 1 || ( !params.empty() && ( !params.contains( "include_serialized" ) || !params["include_serialized"].is_boolean() ) ) ) {
                throw fheroes2::PythonEnvError( "invalid_request", "get_state accepts only an optional boolean include_serialized." );
            }
            const DiagnosticRedirect redirect;
            return world.getState( params.value( "include_serialized", true ) );
        }
        if ( !params.empty() ) {
            throw fheroes2::PythonEnvError( "invalid_request", "This method requires empty params." );
        }
        if ( method == "hello" ) {
            return { { "engine", "fheroes2" }, { "engine_version", ENGINE_VERSION }, { "mode", "bootstrap" }, { "capabilities", capabilities( world.loaded() ) } };
        }
        if ( method == "capabilities" ) {
            return capabilities( world.loaded() );
        }
        if ( method == "close" ) {
            return { { "closed", true } };
        }
        throw fheroes2::PythonEnvError( "unknown_method", "Unknown environment method. Use capabilities to list supported methods." );
    }

    int serve( std::istream & input, std::ostream & output, const char * executablePath )
    {
        std::string line;
        fheroes2::PythonEnvWorld world( executablePath );

        while ( true ) {
            const LineStatus status = readRequest( input, line );
            if ( status == LineStatus::EndOfInput ) {
                return input.bad() ? EXIT_FAILURE : EXIT_SUCCESS;
            }
            if ( status != LineStatus::Ready ) {
                const bool tooLong = status == LineStatus::TooLong;
                if ( !sendError( output, nullptr, tooLong ? "request_too_large" : "invalid_request",
                                 tooLong ? "Request exceeds 65536 bytes." : "Requests must end with a newline." ) ) {
                    return EXIT_FAILURE;
                }
                continue;
            }

            Json request;
            try {
                request = Json::parse( line, []( const int depth, const Json::parse_event_t, Json & ) {
                    if ( depth > maxNestingDepth ) {
                        throw std::invalid_argument( "Request nesting exceeds the protocol limit." );
                    }
                    return true;
                } );
            }
            catch ( const std::exception & ) {
                if ( !sendError( output, nullptr, "invalid_request", "Expected a valid JSON request object with shallow nesting." ) ) {
                    return EXIT_FAILURE;
                }
                continue;
            }

            if ( !request.is_object() || !request.contains( "id" ) || !request["id"].is_number_unsigned()
                 || request["id"].get<uint64_t>() > std::numeric_limits<uint32_t>::max() ) {
                if ( !sendError( output, nullptr, "invalid_request", "Request id must be an unsigned 32-bit integer." ) ) {
                    return EXIT_FAILURE;
                }
                continue;
            }

            const Json & id = request["id"];
            if ( !request.contains( "api_version" ) || !request["api_version"].is_number_unsigned() || request["api_version"] != protocolVersion ) {
                if ( !sendError( output, id, "unsupported_version", "Expected api_version 1." ) ) {
                    return EXIT_FAILURE;
                }
                continue;
            }
            if ( !request.contains( "method" ) || !request["method"].is_string() || ( request.contains( "params" ) && !request["params"].is_object() ) ) {
                if ( !sendError( output, id, "invalid_request", "Expected a method string and optional params object." ) ) {
                    return EXIT_FAILURE;
                }
                continue;
            }

            const std::string & method = request["method"].get_ref<const std::string &>();
            try {
                if ( !sendResult( output, id, execute( method, request.value( "params", Json::object() ), world ) ) ) {
                    return EXIT_FAILURE;
                }
                if ( method == "close" ) {
                    return EXIT_SUCCESS;
                }
            }
            catch ( const fheroes2::PythonEnvError & error ) {
                if ( !sendError( output, id, error.code.c_str(), error.what() ) ) {
                    return EXIT_FAILURE;
                }
            }
            catch ( const std::exception & ) {
                if ( !sendError( output, id, "engine_error", "The engine could not complete the read-only request." ) ) {
                    return EXIT_FAILURE;
                }
            }
        }
    }
}

int fheroes2::runPythonEnvBootstrap( std::istream & input, std::ostream & output, std::ostream & diagnostics, const char * executablePath )
{
    try {
        return serve( input, output, executablePath );
    }
    catch ( const std::exception & ) {
        // Never route protocol errors through the game's logging/UI initialization.
        diagnostics << "Python environment bootstrap failed.\n";
        return EXIT_FAILURE;
    }
}

#endif
