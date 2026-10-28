# Külső vezérlő: mentésből induló döntési pont

A 4. lépés első működő vezérlési határa a standard mentés emberi játékosának adventure köre.
A `start_session(player_id)` belép a C++ `Game::StartGame(controller)` útvonalba, amely a döntési callbackben vár.
A parancskiszolgálás a callbackből történik, ugyanazon motorszálon; a C++ hívási verem a várakozás végéig megmarad.
A normál `Game::StartGame()` továbbra is az eredeti ablakos útvonalat használja.

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

- `phase`: jelenleg `adventure`; `controller`: `external`; `waiting`: true.
- `player_id`: az egyetlen emberi játékos színbites azonosítója. Az AI játékos állapota továbbra is lekérhető,
  de AI-vezérlés átvétele ebben a lépésben nincs támogatva.
- `turn_order`: a normál játékkal közös rendezés, emberi játékosok elöl, azon belül növekvő színérték.
- `token`: folyamatonként egyedi `session_id`, betöltésenként növekvő `episode_id`, `state_version`,
  valamint új várakozásonként növekvő `decision_id` és `player_id`.
- `available_actions`: jelenleg kizárólag `session.stop`.
- `notifications`: stabil `decision_required` értesítés. Lekérdezése nem fogyasztja el.
- `pending_choice`: jelenleg null. Valódi ládaválasztás/szintlépés/csata még nem lép be ebbe az útvonalba.

A `step` paraméterei pontosan `action` (szöveg), `token` (objektum), `params` (objektum).
A Python-kliens explicit tokent kér; nem cseréli le automatikusan egy elavult parancs azonosítóját.
Minden ellenőrzés a módosítás előtt fut: `wrong_session`, `stale_decision`, `wrong_player`, `invalid_request`.
Nem támogatott játékmeneti parancs: `unsupported_action`. Ezek a hibák megőrzik a függő döntést és a világot.
Aktív várakozás alatt az újabb `start_session` és a `load_save` hibája `session_active`; előbb a várakozásból kell kilépni.

Az állapotlekérdezés, handshake és képességlista várakozás közben is elérhető. A render és a láthatóságra szűrt
`observe` továbbra sincs implementálva; nem állítjuk róluk, hogy már működnek a várakozás alatt.

## Pontos határ és további bekötés

A callback a mentett emberi kör belépési határán, UI-inicializálás, `ActionBeforeTurn`, napváltás, bevétel és AI-futtatás
előtt áll meg. A nyers mentett `current_player` metaadat; a vezérlendő játékost a normál standard játékkal azonos módon
az egyetlen emberi játékos adja. Ha nincs ilyen aktív játékos, vagy a mentés már lezárt eredményt tartalmaz, `unsupported_state` a válasz.
A vezérlő nem írja át a `CONTROL_HUMAN`/`CONTROL_AI` értékeket, és nem indítja el a teljes `HumanTurn` UI-hurkot.

Ez a kezdeti döntési pont és a közös parancsellenőrzés, nem teljes körszimuláció. A következő szakaszokban az offscreen
megjelenítés, a valódi adventure műveletek és körfolytatás, később a beágyazott döntések használják tovább ezt a határt.
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
