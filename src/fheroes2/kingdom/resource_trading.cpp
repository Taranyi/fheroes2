/***************************************************************************
 *   fheroes2: https://github.com/ihhub/fheroes2                           *
 *   Copyright (C) 2023 - 2026                                             *
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

#include "resource_trading.h"

#include <algorithm>
#include <array>
#include <cassert>
#include <cstddef>
#include <limits>

#include "kingdom.h"
#include "resource.h"

namespace
{
    // Resources for trade are divided into 3 categories:
    // - common such as Ore and Wood
    // - rare such as Mercury, Sulfur, Crystal and Gems
    // - Gold
    //
    // So we could have the following 8 combinations:
    // common --> common
    // common --> rare
    // common --> gold
    // rare   --> common
    // rare   --> rare
    // rare   --> gold
    // gold   --> common
    // gold   --> rare
    //
    // However, common --> common and rare --> rare should have the same conversion ratio as these are within category.
    // So are left with 7 combinations.
    const size_t maxMarketplaces{ 9 };

    const std::array<uint32_t, maxMarketplaces> resourceToResource{ 10, 7, 5, 4, 4, 3, 3, 3, 2 };
    const std::array<uint32_t, maxMarketplaces> commonToRare{ 20, 14, 10, 8, 7, 6, 5, 5, 4 };
    const std::array<uint32_t, maxMarketplaces> rareToCommon{ 5, 4, 3, 2, 2, 2, 2, 2, 1 };
    const std::array<uint32_t, maxMarketplaces> commonToGold{ 25, 37, 50, 62, 74, 87, 100, 112, 124 };
    const std::array<uint32_t, maxMarketplaces> rareToGold{ 50, 74, 100, 124, 149, 175, 200, 224, 249 };
    const std::array<uint32_t, maxMarketplaces> goldToCommon{ 2500, 1667, 1250, 1000, 834, 715, 625, 556, 500 };
    const std::array<uint32_t, maxMarketplaces> goldToRare{ 5000, 3334, 2500, 2000, 1667, 1429, 1250, 1112, 1000 };
}

namespace fheroes2
{
    ResourceTradeQuote getResourceTradeQuote( const Kingdom & kingdom, const int resourceFrom, const int resourceTo, const bool tradingPost )
    {
        const auto validResource = []( const int resource ) {
            return resource == Resource::WOOD || resource == Resource::MERCURY || resource == Resource::ORE || resource == Resource::SULFUR
                   || resource == Resource::CRYSTAL || resource == Resource::GEMS || resource == Resource::GOLD;
        };
        const uint32_t markets = tradingPost ? 3 : kingdom.GetCountMarketplace();
        if ( markets == 0 || !validResource( resourceFrom ) || !validResource( resourceTo ) || resourceFrom == resourceTo ) {
            return {};
        }
        const uint32_t rate = getTradeCost( markets, resourceFrom, resourceTo );
        if ( rate == 0 ) {
            return {};
        }
        ResourceTradeQuote quote;
        quote.sellPerLot = resourceTo == Resource::GOLD ? 1 : rate;
        quote.buyPerLot = resourceTo == Resource::GOLD ? rate : 1;
        const auto source = kingdom.GetFunds().Get( resourceFrom );
        const auto target = kingdom.GetFunds().Get( resourceTo );
        if ( source < 0 || target < 0 ) {
            return quote;
        }
        quote.maxLots
            = std::min( static_cast<uint32_t>( source ) / quote.sellPerLot, static_cast<uint32_t>( std::numeric_limits<int32_t>::max() - target ) / quote.buyPerLot );
        return quote;
    }

    bool tradeResources( Kingdom & kingdom, const int resourceFrom, const int resourceTo, const uint32_t lots, const bool tradingPost )
    {
        const auto quote = getResourceTradeQuote( kingdom, resourceFrom, resourceTo, tradingPost );
        if ( lots == 0 || lots > quote.maxLots ) {
            return false;
        }
        kingdom.OddFundsResource( Funds( resourceFrom, lots * quote.sellPerLot ) );
        kingdom.AddFundsResource( Funds( resourceTo, lots * quote.buyPerLot ) );
        return true;
    }

    uint32_t getTradeCost( uint32_t marketplaceCount, const int resourceFrom, const int resourceTo )
    {
        if ( marketplaceCount == 0 ) {
            assert( 0 );
            return 0;
        }

        if ( resourceFrom == resourceTo || resourceFrom == Resource::UNKNOWN || resourceTo == Resource::UNKNOWN ) {
            // The resource is not selected (Resource::UNKNOWN) or resources are the same.
            // What are we trying to achieve?
            return 0;
        }

        if ( marketplaceCount > 9 ) {
            marketplaceCount = 9;
        }

        --marketplaceCount;

        switch ( resourceFrom ) {
        case Resource::GOLD: {
            switch ( resourceTo ) {
            case Resource::WOOD:
            case Resource::ORE:
                return goldToCommon[marketplaceCount];
            case Resource::MERCURY:
            case Resource::SULFUR:
            case Resource::CRYSTAL:
            case Resource::GEMS:
                return goldToRare[marketplaceCount];
            default:
                assert( 0 );
            }
            return 0;
        }

        case Resource::WOOD:
        case Resource::ORE: {
            switch ( resourceTo ) {
            case Resource::WOOD:
            case Resource::ORE:
                return resourceToResource[marketplaceCount];
            case Resource::GOLD:
                return commonToGold[marketplaceCount];
            case Resource::MERCURY:
            case Resource::SULFUR:
            case Resource::CRYSTAL:
            case Resource::GEMS:
                return commonToRare[marketplaceCount];
            default:
                assert( 0 );
            }
            return 0;
        }

        case Resource::MERCURY:
        case Resource::SULFUR:
        case Resource::CRYSTAL:
        case Resource::GEMS: {
            switch ( resourceTo ) {
            case Resource::WOOD:
            case Resource::ORE:
                return rareToCommon[marketplaceCount];
            case Resource::GOLD:
                return rareToGold[marketplaceCount];
            case Resource::MERCURY:
            case Resource::SULFUR:
            case Resource::CRYSTAL:
            case Resource::GEMS:
                return resourceToResource[marketplaceCount];
            default:
                assert( 0 );
            }
            return 0;
        }

        default:
            assert( 0 );
            return 0;
        }
    }
}
