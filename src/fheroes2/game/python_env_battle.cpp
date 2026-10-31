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

#include "python_env_battle.h"

#if defined( FHEROES2_ENABLE_PYTHON_ENV )

#include <algorithm>
#include <array>
#include <limits>
#include <set>

#include "battle_arena.h"
#include "battle_army.h"
#include "battle_board.h"
#include "battle_cell.h"
#include "battle_troop.h"
#include "heroes.h"
#include "heroes_base.h"
#include "kingdom.h"
#include "resource.h"
#include "spell.h"
#include "system.h"
#include "world.h"

namespace
{
    using Json = nlohmann::json;

    Json commanderState( const HeroBase * hero )
    {
        if ( hero == nullptr ) {
            return nullptr;
        }
        return { { "color", static_cast<int>( hero->GetColor() ) },
                 { "name", System::encLocalToUTF8( hero->GetName() ) },
                 { "spell_points", hero->GetSpellPoints() },
                 { "spell_cast_this_round", hero->Modes( Heroes::SPELLCASTED ) } };
    }

    Json unitState( const Battle::Unit & unit )
    {
        Json effects = Json::array();
        for ( uint32_t flag = 1; flag != 0; flag <<= 1 ) {
            if ( unit.Modes( flag ) ) {
                effects.push_back( { { "mode", flag }, { "rounds", unit.GetAffectedDuration( flag ) } } );
            }
        }
        return { { "uid", unit.GetUID() },
                 { "monster_id", unit.GetID() },
                 { "count", unit.GetCount() },
                 { "alive", unit.isValid() },
                 { "army_color", static_cast<int>( unit.GetArmyColor() ) },
                 { "current_color", static_cast<int>( unit.GetCurrentColor() ) },
                 { "head", unit.GetHeadIndex() },
                 { "tail", unit.GetTailIndex() },
                 { "wide", unit.isWide() },
                 { "flying", unit.isFlying() },
                 { "hit_points", unit.GetHitPoints() },
                 { "shots", unit.GetShots() },
                 { "speed", unit.GetSpeed() },
                 { "attack", unit.GetAttack() },
                 { "defense", unit.GetDefense() },
                 { "modes", unit.getModeMask() },
                 { "effects", effects } };
    }
}

fheroes2::PythonEnvBattleDecision fheroes2::pythonEnvBattleDecision( Battle::Arena & arena, const Battle::Unit & unit )
{
    using namespace Battle;
    PythonEnvBattleDecision result;
    Json choices = Json::array();
    const auto add = [&]( Command command, Json description ) {
        description["action_id"] = result.commands.size();
        choices.push_back( std::move( description ) );
        result.commands.push_back( std::move( command ) );
    };
    add( Command( Command::SKIP, unit.GetUID() ), { { "kind", "skip" }, { "unit_uid", unit.GetUID() } } );

    std::set<int32_t> positions{ unit.GetHeadIndex() };
    for ( const int32_t cell : arena.getAllAvailableMoves( unit ) ) {
        const Position pos = Position::GetReachable( unit, cell );
        if ( pos.GetHead() != nullptr && arena.isPositionReachable( unit, pos, true ) ) {
            positions.insert( pos.GetHead()->GetIndex() );
        }
    }
    for ( const int32_t cell : positions ) {
        if ( cell != unit.GetHeadIndex() ) {
            add( Command( Command::MOVE, unit.GetUID(), cell ), { { "kind", "move" }, { "unit_uid", unit.GetUID() }, { "destination", cell } } );
        }
    }
    Json units = Json::array();
    for ( const Force * force : { &arena.getAttackingForce(), &arena.getDefendingForce() } ) {
        for ( const Unit * target : force->getUnits() ) {
            units.push_back( unitState( *target ) );
            if ( !target->isValid() || target->GetColor() == unit.GetCurrentColor() ) {
                continue;
            }
            if ( unit.isArchers() && !unit.isHandFighting() ) {
                if ( unit.GetShots() > 0 ) {
                    for ( const int32_t targetCell : { target->GetHeadIndex(), target->GetTailIndex() } ) {
                        if ( Board::isValidIndex( targetCell ) ) {
                            add( Command( Command::ATTACK, unit.GetUID(), target->GetUID(), -1, targetCell, 0 ),
                                 { { "kind", "shoot" }, { "unit_uid", unit.GetUID() }, { "target_uid", target->GetUID() }, { "target_cell", targetCell } } );
                        }
                    }
                }
                continue;
            }
            for ( const int32_t cell : positions ) {
                if ( Board::CanAttackTargetFromPosition( unit, *target, cell ) ) {
                    const Position pos = Position::GetReachable( unit, cell );
                    for ( const Cell * source : std::array<const Cell *, 2>{ pos.GetHead(), pos.GetTail() } ) {
                        if ( source == nullptr || !Board::CanAttackFromCell( unit, source->GetIndex() ) ) {
                            continue;
                        }
                        for ( const int32_t targetCell : { target->GetHeadIndex(), target->GetTailIndex() } ) {
                            if ( !Board::isValidIndex( targetCell ) || !Board::isNearIndexes( source->GetIndex(), targetCell ) ) {
                                continue;
                            }
                            const int direction = static_cast<int>( Board::GetDirection( source->GetIndex(), targetCell ) );
                            add( Command( Command::ATTACK, unit.GetUID(), target->GetUID(), cell == unit.GetHeadIndex() ? -1 : cell, targetCell, direction ),
                                 { { "kind", "attack" },
                                   { "unit_uid", unit.GetUID() },
                                   { "target_uid", target->GetUID() },
                                   { "destination", cell },
                                   { "target_cell", targetCell },
                                   { "attack_direction", direction } } );
                        }
                    }
                }
            }
        }
    }

    const HeroBase * hero = arena.GetCurrentCommander();
    if ( hero != nullptr && hero->HaveSpellBook() ) {
        for ( int id = Spell::FIREBALL; id <= Spell::EARTHQUAKE; ++id ) {
            const Spell spell( id );
            if ( !hero->HaveSpell( spell ) || !hero->CanCastSpell( spell ) || arena.isDisableCastSpell( spell ) ) {
                continue;
            }
            if ( spell == Spell::TELEPORT ) {
                for ( const Force * force : { &arena.getAttackingForce(), &arena.getDefendingForce() } ) {
                    for ( const Unit * target : force->getUnits() ) {
                        if ( !target->isValid() || !target->AllowApplySpell( spell, hero ) )
                            continue;
                        for ( const Cell & cell : *Arena::GetBoard() ) {
                            if ( cell.GetIndex() != target->GetHeadIndex() && cell.GetIndex() != target->GetTailIndex() && cell.isPassableForUnit( *target ) ) {
                                add( Command( Command::SPELLCAST, id, target->GetHeadIndex(), cell.GetIndex() ), { { "kind", "spell" },
                                                                                                                   { "spell_id", id },
                                                                                                                   { "target_uid", target->GetUID() },
                                                                                                                   { "target_cell", cell.GetIndex() },
                                                                                                                   { "spell_points", spell.spellPoints( hero ) } } );
                            }
                        }
                    }
                }
                continue;
            }
            if ( spell.isApplyWithoutFocusObject() ) {
                add( Command( Command::SPELLCAST, id, -1 ),
                     { { "kind", "spell" }, { "spell_id", id }, { "target_cell", -1 }, { "spell_points", spell.spellPoints( hero ) } } );
                continue;
            }
            for ( int32_t cell = 0; cell < Board::sizeInCells; ++cell ) {
                if ( spell == Spell::CHAINLIGHTNING ) {
                    const Unit * first = arena.GetTroopBoard( cell );
                    if ( first == nullptr || !first->AllowApplySpell( spell, hero ) )
                        continue;
                }
                if ( !arena.GetTargetsForSpell( hero, spell, cell ).empty() ) {
                    add( Command( Command::SPELLCAST, id, cell ),
                         { { "kind", "spell" }, { "spell_id", id }, { "target_cell", cell }, { "spell_points", spell.spellPoints( hero ) } } );
                }
            }
        }
    }
    const PlayerColor color = arena.GetCurrentColor();
    if ( arena.CanRetreatOpponent( color ) ) {
        add( Command( Command::RETREAT ), { { "kind", "retreat" } } );
    }
    const uint32_t surrenderCost = arena.GetCurrentForce().GetSurrenderCost();
    if ( arena.CanSurrenderOpponent( color ) && surrenderCost <= static_cast<uint32_t>( std::numeric_limits<int32_t>::max() )
         && world.GetKingdom( color ).AllowPayment( Funds( Resource::GOLD, surrenderCost ) ) ) {
        add( Command( Command::SURRENDER ), { { "kind", "surrender" }, { "gold", surrenderCost } } );
    }
    Json board = Json::array();
    for ( const Cell & cell : *Arena::GetBoard() ) {
        board.push_back( { { "index", cell.GetIndex() },
                           { "object", cell.GetObject() },
                           { "unit_uid", cell.GetUnit() != nullptr ? Json( cell.GetUnit()->GetUID() ) : Json( nullptr ) } } );
    }
    result.state = { { "map_index", arena.getMapIndex() },
                     { "width", Board::widthInCells },
                     { "height", Board::heightInCells },
                     { "round", arena.GetTurnNumber() },
                     { "current_unit_uid", unit.GetUID() },
                     { "current_color", static_cast<int>( color ) },
                     { "attacker_color", static_cast<int>( arena.getAttackingArmyColor() ) },
                     { "defender_color", static_cast<int>( arena.getDefendingForce().GetColor() ) },
                     { "attacker_commander", commanderState( arena.getAttackingArmyCommander() ) },
                     { "defender_commander", commanderState( arena.getDefendingArmyCommander() ) },
                     { "siege", Arena::GetCastle() != nullptr },
                     { "units", units },
                     { "board", board },
                     { "actions", choices } };
    return result;
}
#endif
