# Külső vezérlő: mentésből induló döntési pont

A 4. lépés első működő vezérlési határa a standard mentés emberi játékosának adventure köre.
A `start_session(player_id)` belép a C++ `Game::StartGame(controller)` útvonalba, amely a döntési callbackben vár.
A parancskiszolgálás a callbackből történik, ugyanazon motorszálon; a C++ hívási verem a várakozás végéig megmarad.
A normál `Game::StartGame()` továbbra is az eredeti ablakos útvonalat használja.

2026-10-29-i követelmény: ez az egyetlen emberinek jelölt résztvevőre szűkített megoldás átmeneti.
A végcél résztvevőnként választható beépített AI vagy Python-vezérlő, több külső oldal és teljesen AI-s futás,
kézi játékos nélkül. A mindent látó állapotlekérés már minden oldalra működik; a több résztvevős vezérlés még nem.
A megvalósítás előtt követendő pontosítás és elfogadási esetek a [terv résztvevői követelményeinél](PYTHON_ENV_IMPLEMENTATION_PLAN.md) szerepelnek (4/A feladat).

## Használat

```python
with HeroesSession("fheroes2.exe") as game:
    game.load_save("mentes.sav")
    state = game.get_state(include_serialized=False)
    human = next(player for player in state["players"] if player["is_human"])
    decision = game.start_session(human["id"])
    assert game.get_decision() == decision
    state_while_waiting = game.get_state()
    game.step("session.stop", token=decision["token"])
```

Futtatható példa: `python/examples/decision.py`. A `session.stop` csak a külső vezérlési várakozásból lép ki;
nem zár le játékoskört, nem futtat AI-t és nem változtatja a betöltött világot. Utána ugyanaz a mentett állapot
új döntési azonosítóval ismét vezérelhető, vagy másik mentés tölthető be. A `close` és az EOF a teljes folyamatot lezárja.

## A döntés szerződése

- `phase`: `adventure` vagy a motor által megállapított eredménynél `terminal`; `controller`: `external`; `waiting`: true.
- `player_id`: az egyetlen emberi játékos színbites azonosítója. Az AI játékos állapota továbbra is lekérhető,
  de AI-vezérlés átvétele ebben a lépésben nincs támogatva.
- `turn_order`: a normál játékkal közös rendezés, emberi játékosok elöl, azon belül növekvő színérték.
- `token`: folyamatonként egyedi `session_id`, betöltési kísérletenként növekvő `episode_id`, betöltési kísérletnél és
  sikeres játékműveletnél növekvő `state_version`, új várakozásnál és sikeres játékműveletnél növekvő `decision_id`, valamint `player_id`.
- `available_actions`: `session.stop`, `hero.move`, `turn.end`, `castle.build`, `castle.recruit`; terminális helyzetben csak `session.stop`.
- `events`: a legutóbbi sikeres művelet eseményei; lekérdezése nem fogyasztja el.
- `notifications`: stabil `decision_required` értesítés. Lekérdezése nem fogyasztja el.
- `pending_choice`: jelenleg null. Valódi ládaválasztás/szintlépés/csata még nem lép be ebbe az útvonalba.

A `step` paraméterei pontosan `action` (szöveg), `token` (objektum), `params` (objektum).
A Python-kliens explicit tokent kér; nem cseréli le automatikusan egy elavult parancs azonosítóját.
Minden ellenőrzés a módosítás előtt fut: `wrong_session`, `stale_decision`, `wrong_player`, `invalid_request`.
Nem támogatott játékmeneti parancs: `unsupported_action`. Ezek a hibák megőrzik a függő döntést és a világot.
Aktív várakozás alatt az újabb `start_session` és a `load_save` hibája `session_active`; előbb a várakozásból kell kilépni.

Az állapotlekérdezés, handshake és képességlista várakozás közben is elérhető. Az 5. lépéstől az adventure
[képkérés](PYTHON_ENV_HEADLESS.md) is működik itt. A láthatóságra szűrt `observe` továbbra sincs implementálva.

## Pontos határ és további bekötés

A callback a mentett emberi kör belépési határán, UI-inicializálás, `ActionBeforeTurn`, napváltás, bevétel és AI-futtatás
előtt áll meg. A nyers mentett `current_player` metaadat; a vezérlendő játékost a normál standard játékkal azonos módon
az egyetlen emberi játékos adja. Ha nincs ilyen aktív játékos, vagy a mentés már lezárt eredményt tartalmaz, `unsupported_state` a válasz.
A vezérlő nem írja át a `CONTROL_HUMAN`/`CONTROL_AI` értékeket, és nem indítja el a teljes `HumanTurn` UI-hurkot.

Ezt a közös döntési pontot az 5. lépéstől az offscreen megjelenítés, a 6. lépéstől a
[korlátozott adventure műveletek és natív AI-körfolytatás](PYTHON_ENV_ADVENTURE.md) is használják.
A konkrét választási dialógusok átalakítása a terv 9. lépésének része; helyettük itt nem választ automatikusan a motor.

## CONTROL-elágazások auditja

| Hely | Jelentőség a további munkához |
|---|---|
| `game_startgame.cpp`, `AdventureMap::StartGame` | Emberi játékosok elöl; standard mentés az egyetlen embernél folytatódik. A UI, fog-frissítés és `ActionBeforeTurn` a normál útvonalon marad. |
| `game_startgame.cpp`, `HumanTurn` | Betöltésnél eltérő napi előkészítés; a bevétel és mentés nem futhat le még egyszer. |
| `kingdom.cpp`, `ActionBeforeTurn` | Embernél útvonal-újraszámítás, AI-nál útvonaltörlés. Nem pusztán megjelenítés. |
| `kingdom.cpp`, `ActionNewDayResourceUpdate` és `GetIncome` | Események AI-jogosultsága, nehézségi bevételbónusz; az AI-nak átjelölés megváltoztatná a szabályokat. |
| `heroes_action.cpp`, `Heroes::Action` | AI esetén másik akcióútvonalra vált; emberi ágon fókusz, zene és dialógusok is vannak. A grafikus részt külön kell leválasztani. |
| `heroes_move.cpp` | Az animációsebesség, útvonal-frissítés és kirajzolás függ a vezérléstől; az AI-jelölés nem headless megoldás. |
| `ai_hero_action.cpp` | A védő emberi típusa csatánál is számít. Az ellenfelek típusa változatlan marad. |

A két saját referencia mentésen a 28 Python teszt ellenőrzi a változatlan teljes mentéspayloadot, a két folyamat tokenjeinek
elkülönülését, az elavult döntéseket, az elutasított műveleteket, a lezárást és a hibás bemenet utáni folytatást.
Az üres tesztprofil és az érvénytelen SDL-meghajtók igazolják, hogy ez a kezdeti várakozás nem igényel ablakot vagy hangot.
Ez Windows-futtatás; a többi platform SDK-buildjét nem helyettesíti.

A Python nélküli Windows-build is sikeres. Az ablakos regressziós próba során az indítás a bevezető videóig jutott;
a Computer Use vezérlést a felhasználó fizikai Escape billentyűje megszakította. A főmenü és a mentés grafikus
betöltésének ellenőrzése ebben a lépésben ezért nem befejezett.
