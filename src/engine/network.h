#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace fheroes2
{
namespace network
{
    bool initializeHost( uint16_t port );
    bool initializeGuest( const std::string & address, uint16_t port );
    void shutdown();

    bool sendData( const std::vector<uint8_t> & data );
    bool receiveData( std::vector<uint8_t> & data );
}
}

