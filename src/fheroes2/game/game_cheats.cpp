#include "game_cheats.h"

#include <SDL2/SDL.h>
#include "logging.h"
#include "settings.h"
#include "world.h"
#include "kingdom.h"
#include "resource.h"
#include "game_interface.h"
#include "castle.h"
#include "heroes.h"
#include "monster.h"
#include "spell.h"
#include "game_over.h"

namespace GameCheats
{
    namespace
    {
        std::string buffer;
        bool enabled = false;

        const size_t MAX_BUFFER = 32;

        const char * const CODE_SHOWMAP = "11111";
        const char * const CODE_RESOURCES = "22222";
        const char * const CODE_BLACKDRAGONS = "32167";
        const char * const CODE_MAXSKILLS = "33333";
        const char * const CODE_INFINITEWALK = "44444";
        const char * const CODE_INSTANTWIN = "55555";
        const char * const CODE_MAXSPELLS = "66666";
        const char * const CODE_BUILDALL = "77777";

        void checkBuffer()
        {
            if ( buffer.find( CODE_SHOWMAP ) != std::string::npos ) {
                DEBUG_LOG( DBG_GAME, DBG_INFO, "Cheat activated: show map" );
                World::Get().ClearFog( Settings::Get().CurrentColor() );
                buffer.clear();
            }
            else if ( buffer.find( CODE_RESOURCES ) != std::string::npos ) {
                DEBUG_LOG( DBG_GAME, DBG_INFO, "Cheat activated: resources" );
                Kingdom & kingdom = World::Get().GetKingdom( Settings::Get().CurrentColor() );
                kingdom.AddFundsResource( Funds( 0, 0, 0, 0, 0, 0, 10000 ) );
                kingdom.AddFundsResource( Funds( Resource::WOOD, 999 ) );
                kingdom.AddFundsResource( Funds( Resource::ORE, 999 ) );
                kingdom.AddFundsResource( Funds( Resource::MERCURY, 999 ) );
                kingdom.AddFundsResource( Funds( Resource::SULFUR, 999 ) );
                kingdom.AddFundsResource( Funds( Resource::CRYSTAL, 999 ) );
                kingdom.AddFundsResource( Funds( Resource::GEMS, 999 ) );
                buffer.clear();
            }
            else if ( buffer.find( CODE_BLACKDRAGONS ) != std::string::npos ) {
                DEBUG_LOG( DBG_GAME, DBG_INFO, "Cheat activated: black dragons" );
                if ( Heroes * hero = Interface::GetFocusHeroes() ) {
                    hero->GetArmy().JoinTroop( Monster::BLACK_DRAGON, 5, true );
                }
                buffer.clear();
            }
            else if ( buffer.find( CODE_MAXSKILLS ) != std::string::npos ) {
                DEBUG_LOG( DBG_GAME, DBG_INFO, "Cheat activated: max skills" );
                if ( Heroes * hero = Interface::GetFocusHeroes() ) {
                    hero->setAttackBaseValue( 12 );
                    hero->setDefenseBaseValue( 12 );
                    hero->setPowerBaseValue( 12 );
                    hero->setKnowledgeBaseValue( 12 );

                    for ( Skill::Secondary & skill : hero->GetSecondarySkills().ToVector() ) {
                        if ( skill.isValid() )
                            skill.SetLevel( Skill::Level::EXPERT );
                    }
                }
                buffer.clear();
            }
            else if ( buffer.find( CODE_INFINITEWALK ) != std::string::npos ) {
                DEBUG_LOG( DBG_GAME, DBG_INFO, "Cheat activated: infinite walk" );
                if ( Heroes * hero = Interface::GetFocusHeroes() ) {
                    hero->SetMovePoints( hero->GetMaxMovePoints() * 10 );
                }
                buffer.clear();
            }
            else if ( buffer.find( CODE_INSTANTWIN ) != std::string::npos ) {
                DEBUG_LOG( DBG_GAME, DBG_INFO, "Cheat activated: instant win" );
                GameOver::Result::Get().SetResult( GameOver::WINS_ALL );
                GameOver::Result::Get().checkGameOver();
                buffer.clear();
            }
            else if ( buffer.find( CODE_MAXSPELLS ) != std::string::npos ) {
                DEBUG_LOG( DBG_GAME, DBG_INFO, "Cheat activated: max spells" );
                if ( Heroes * hero = Interface::GetFocusHeroes() ) {
                    hero->SpellBookActivate();
                    for ( const int spellId : Spell::getAllSpellIdsSuitableForSpellBook() ) {
                        hero->AppendSpellToBook( Spell( spellId ), true );
                    }
                    hero->SetSpellPoints( hero->GetMaxSpellPoints() );
                }
                buffer.clear();
            }
            else if ( buffer.find( CODE_BUILDALL ) != std::string::npos ) {
                DEBUG_LOG( DBG_GAME, DBG_INFO, "Cheat activated: build all" );
                if ( Castle * castle = Interface::GetFocusCastle() ) {
                    for ( uint32_t bit = 1; bit; bit <<= 1 ) {
                        if ( castle->AllowBuyBuilding( bit ) )
                            castle->BuyBuilding( bit );
                    }
                }
                buffer.clear();
            }
        }
    }

    void enableCheats( bool enable )
    {
        enabled = enable;
        if ( !enable )
            buffer.clear();
    }

    bool cheatsEnabled()
    {
        return enabled;
    }

    void reset()
    {
        buffer.clear();
    }

    void onKeyPressed( const fheroes2::Key key, const int32_t modifier )
    {
        if ( !enabled || SDL_IsTextInputActive() )
            return;

        std::string tmp;
        size_t pos = 0;
        pos = fheroes2::InsertKeySym( tmp, pos, key, modifier );
        if ( pos == 0 || tmp.empty() )
            return;

        buffer += tmp;
        if ( buffer.size() > MAX_BUFFER )
            buffer.erase( 0, buffer.size() - MAX_BUFFER );

        checkBuffer();
    }
}

