#include "network.h"
#include "logging.h"

#if defined( _WIN32 )
#include <winsock2.h>
#include <ws2tcpip.h>
#pragma comment( lib, "Ws2_32.lib" )
#else
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

namespace fheroes2
{
namespace network
{
    namespace
    {
#if defined( _WIN32 )
        using socket_t = SOCKET;
        constexpr socket_t invalid_socket = INVALID_SOCKET;
#else
        using socket_t = int;
        constexpr socket_t invalid_socket = -1;
#endif
        socket_t g_socket = invalid_socket;
    }

    bool initializeHost( uint16_t port )
    {
#if defined( _WIN32 )
        WSADATA wsaData;
        if ( WSAStartup( MAKEWORD( 2, 2 ), &wsaData ) != 0 ) {
            ERROR_LOG( "Failed to initialize WinSock" );
            return false;
        }
#endif
        g_socket = ::socket( AF_INET, SOCK_STREAM, 0 );
        if ( g_socket == invalid_socket ) {
            ERROR_LOG( "Unable to create socket" );
            return false;
        }
        sockaddr_in addr{};
        addr.sin_family = AF_INET;
        addr.sin_addr.s_addr = htonl( INADDR_ANY );
        addr.sin_port = htons( port );
        if ( ::bind( g_socket, reinterpret_cast<sockaddr *>( &addr ), sizeof( addr ) ) < 0 ) {
            ERROR_LOG( "Bind failed" );
            shutdown();
            return false;
        }
        if ( ::listen( g_socket, 1 ) < 0 ) {
            ERROR_LOG( "Listen failed" );
            shutdown();
            return false;
        }
        DEBUG_LOG( DBG_NETWORK, DBG_INFO, "Listening on port " << port );
        return true;
    }

    bool initializeGuest( const std::string & address, uint16_t port )
    {
#if defined( _WIN32 )
        WSADATA wsaData;
        if ( WSAStartup( MAKEWORD( 2, 2 ), &wsaData ) != 0 ) {
            ERROR_LOG( "Failed to initialize WinSock" );
            return false;
        }
#endif
        g_socket = ::socket( AF_INET, SOCK_STREAM, 0 );
        if ( g_socket == invalid_socket ) {
            ERROR_LOG( "Unable to create socket" );
            return false;
        }
        sockaddr_in addr{};
        addr.sin_family = AF_INET;
        addr.sin_port = htons( port );
        inet_pton( AF_INET, address.c_str(), &addr.sin_addr );
        if ( ::connect( g_socket, reinterpret_cast<sockaddr *>( &addr ), sizeof( addr ) ) < 0 ) {
            ERROR_LOG( "Connect failed" );
            shutdown();
            return false;
        }
        DEBUG_LOG( DBG_NETWORK, DBG_INFO, "Connected to " << address << ":" << port );
        return true;
    }

    void shutdown()
    {
        if ( g_socket != invalid_socket ) {
#if defined( _WIN32 )
            ::closesocket( g_socket );
            WSACleanup();
#else
            ::close( g_socket );
#endif
            g_socket = invalid_socket;
        }
    }

    bool sendData( const std::vector<uint8_t> & data )
    {
        if ( g_socket == invalid_socket )
            return false;
        const ssize_t sent = ::send( g_socket, reinterpret_cast<const char *>( data.data() ), data.size(), 0 );
        return sent == static_cast<ssize_t>( data.size() );
    }

    bool receiveData( std::vector<uint8_t> & data )
    {
        if ( g_socket == invalid_socket )
            return false;
        uint8_t buffer[1024];
        const ssize_t r = ::recv( g_socket, reinterpret_cast<char *>( buffer ), sizeof( buffer ), 0 );
        if ( r <= 0 )
            return false;
        data.assign( buffer, buffer + r );
        return true;
    }
}
}

