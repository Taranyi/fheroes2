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
#include <istream>
#include <limits>
#include <ostream>
#include <stdexcept>
#include <string>

#include "../../thirdparty/nlohmann/json.hpp"
#include "version.h"

namespace
{
    using Json = nlohmann::json;

    constexpr uint32_t protocolVersion{ 1 };
    constexpr size_t maxRequestBytes{ 65536 };
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

    Json capabilities()
    {
        return { { "commands", { "hello", "capabilities", "close" } },
                 { "max_request_bytes", maxRequestBytes },
                 { "game_initialized", false },
                 { "state_queries", false },
                 { "simulation", false },
                 { "render", false },
                 { "headless_gameplay", false } };
    }

    bool sendResult( std::ostream & output, const Json & id, const Json & result )
    {
        output << Json( { { "api_version", protocolVersion }, { "id", id }, { "result", result } } ).dump() << '\n' << std::flush;
        return output.good();
    }

    bool sendError( std::ostream & output, const Json & id, const char * code, const char * message )
    {
        output << Json( { { "api_version", protocolVersion }, { "id", id }, { "error", { { "code", code }, { "message", message } } } } ).dump() << '\n' << std::flush;
        return output.good();
    }

    int serve( std::istream & input, std::ostream & output )
    {
        std::string line;

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
            if ( !request.contains( "method" ) || !request["method"].is_string()
                 || ( request.contains( "params" ) && ( !request["params"].is_object() || !request["params"].empty() ) ) ) {
                if ( !sendError( output, id, "invalid_request", "Expected a method string and optional empty params object." ) ) {
                    return EXIT_FAILURE;
                }
                continue;
            }

            const std::string & method = request["method"].get_ref<const std::string &>();
            if ( method == "hello" ) {
                if ( !sendResult( output, id,
                                  { { "engine", "fheroes2" }, { "engine_version", ENGINE_VERSION }, { "mode", "bootstrap" }, { "capabilities", capabilities() } } ) ) {
                    return EXIT_FAILURE;
                }
            }
            else if ( method == "capabilities" ) {
                if ( !sendResult( output, id, capabilities() ) ) {
                    return EXIT_FAILURE;
                }
            }
            else if ( method == "close" ) {
                return sendResult( output, id, { { "closed", true } } ) ? EXIT_SUCCESS : EXIT_FAILURE;
            }
            else if ( !sendError( output, id, "unknown_method", "This bootstrap supports hello, capabilities and close." ) ) {
                return EXIT_FAILURE;
            }
        }
    }
}

int fheroes2::runPythonEnvBootstrap( std::istream & input, std::ostream & output, std::ostream & diagnostics )
{
    try {
        return serve( input, output );
    }
    catch ( const std::exception & ) {
        // Never route protocol errors through the game's logging/UI initialization.
        diagnostics << "Python environment bootstrap failed.\n";
        return EXIT_FAILURE;
    }
}

#endif
