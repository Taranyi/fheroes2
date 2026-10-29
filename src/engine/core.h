/***************************************************************************
 *   fheroes2: https://github.com/ihhub/fheroes2                           *
 *   Copyright (C) 2021 - 2026                                             *
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

#include <set>
#include <stdexcept>
#include <string>

#include "component_base.h"

namespace System
{
    enum class SystemInitializationComponent : int
    {
        Audio,
        Video,
        GameController
    };

    class HeadlessInteractionError final : public std::logic_error
    {
    public:
        explicit HeadlessInteractionError( const std::string & operation )
            : std::logic_error( "Interactive operation is unavailable in headless mode: " + operation )
        {}
    };

    // Process-local execution policy. Enter before initializing any presentation component.
    // The engine and its caller use one thread; nested scopes restore the previous policy.
    class ScopedHeadlessMode final
    {
    public:
        ScopedHeadlessMode();
        ~ScopedHeadlessMode();
        ScopedHeadlessMode( const ScopedHeadlessMode & ) = delete;
        ScopedHeadlessMode & operator=( const ScopedHeadlessMode & ) = delete;

    private:
        bool _previous;
    };

    bool isHeadlessMode();
    void requireInteractive( const char * operation );

    class HardwareInitializer final : public ComponentBase
    {
    public:
        HardwareInitializer();
        HardwareInitializer( const HardwareInitializer & ) = delete;
        HardwareInitializer & operator=( const HardwareInitializer & ) = delete;

        ~HardwareInitializer();
    };

    class CoreInitializer final : public ComponentBase
    {
    public:
        explicit CoreInitializer();
        // An empty set leaves SDL and event handling completely uninitialized.
        explicit CoreInitializer( const std::set<SystemInitializationComponent> & components );
        CoreInitializer( const CoreInitializer & ) = delete;
        CoreInitializer & operator=( const CoreInitializer & ) = delete;

        ~CoreInitializer();

    private:
        bool _initialized{ false };
    };

    bool isComponentInitialized( const SystemInitializationComponent component );
}
