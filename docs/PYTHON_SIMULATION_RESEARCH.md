# Pythonból vezérelhető teljes fheroes2-szimuláció – kutatási jegyzet

Dátum: 2026-10-25. Vizsgált alapcommit: `4ec988682`.

## Cél és a vizsgálat határa

A teljes játék legyen Pythonból indítható, lekérdezhető és vezérelhető, ablak nélküli szimulációval és opcionális rendereléssel. A hatókör része a kalandtérkép, a várak, a hősök, a csaták, a seregek és tárgyak kezelése, a kereskedelem, a varázslás és a közben felmerülő döntések. A Gymnasium/RL egy későbbi adapter ehhez az általános API-hoz.

Ez forráskód-vizsgálat és korábbi internetes kutatás összegzése. Nem készült működő Python-kapcsolat, nem futott headless próba, teljesítménymérés vagy reprodukálhatósági teszt. A „találat” ellenőrzött kódrészletet, a „javaslat” tervezési döntést, a „nyitott” még igazolandó kérdést jelent. A sorhivatkozások a fenti commitra vonatkoznak; a függvénynevek tartósabb keresési pontok.

A munkakönyvtárban már voltak helyi Windows-build módosítások. Ezeket a vizsgálat nem módosítja. Ez a jegyzet az egyetlen új kutatási fájl.

## Fő megállapítások

1. A játéklogika jelentős része már C++ objektumokon elérhető, de nincs egységes külső parancs- és megfigyelési API.
2. A fő játékhurok és sok belső művelet grafikus állapotot, eseménykezelést vagy blokkoló dialógust is használ. Az ablak elrejtése önmagában nem oldja meg a headless működést.
3. A vár- és hősnézet többnyire egy meglévő világobjektum kezelőfelülete. Az adatok lekérése és a műveletek végrehajtása nem igényelhet ablaknyitást az új API-ban.
4. Más természetű helyzet a csata vagy a jutalomválasztás: ezek valódi, akár egymásba ágyazott döntési pontok.
5. Az emberi és AI objektuminterakcióknak külön kódútja is van. Egy külső játékost nem lehet egyszerűen AI-nak jelölni, mert akkor a motor bizonyos döntéseket maga hoz meg.
6. A meglévő automatikus pályateszt jó referencia a teljes játék futtatásához, de nem kész headless backend.
7. A globális világ, beállítások, AI és aktív csata miatt kezdetben egy motorfolyamat / környezet javasolt.
8. A map seed és a csata saját RNG-je jó alap, de nem bizonyítja a teljes játék determinisztikus resetjét.

## 1. Indítás, munkamenet és a fő játékhurok

### Ellenőrzött belépési pontok

| Forrás | Szimbólum / sor | Találat és következmény |
|---|---|---|
| [fheroes2.cpp](../src/fheroes2/game/fheroes2.cpp) | `main`, 56 | Sorban inicializálja a hardware/core/display/data/audio komponenseket, majd palettát, fordítást, eseményeket, animációt és hotkeyeket. Utána a menüs főhurkot indítja. Külön szimulációs indítási út kell. |
| [game_init.cpp](../src/fheroes2/game/game_init.cpp) | `DisplayInitializer`, 70; `DataInitializer`, 146; factoryk, 265–285 | A komponensek már részben külön vannak, de az adatbetöltő is használ képernyőpaletta-visszaállítót, fontellenőrzést és grafikus hibajelzést. Nem bizonyított, hogy a display egyszerűen elhagyható. |
| [core.cpp](../src/engine/core.cpp) | `CoreInitializer`, 172 körül | Alapból Audio és Video alrendszert inicializál. A szimulációs konfigurációnak ezt is szabályoznia kell. |
| [game_mainmenu.cpp](../src/fheroes2/game/game_mainmenu.cpp) | `Game::runMainGameLoop`, 123 | A menü- és fő játékmódokat irányítja. A külső API-nak nem kell a menüt végigjátszania. |
| [game_startgame.cpp](../src/fheroes2/game/game_startgame.cpp) | `Game::StartGame`, 238; `AdventureMap::StartGame`, 732 | A játék indítása az AdventureMap singletonhoz vezet; annak indítása UI-resetet, radarépítést és redraw-t is végez. |
| [game_startgame.cpp](../src/fheroes2/game/game_startgame.cpp) | `AdventureMap::HumanTurn`, 1007 | Grafikus inputhurok, napkezdő üzenetek, automatikus mentés és animációs/eseménykezelési feladatok keverednek. Külső vezérlőnek külön bemeneti ág szükséges. |
| [game_mode.h](../src/fheroes2/game/game_mode.h) | `GameMode` | Főmenü/játékfolyam enum, nem általános „adventure/castle/hero/battle/pending choice” állapotmodell. Nem érdemes közvetlenül publikus Python-állapottípussá tenni. |

### Napok és játékosok

A `StartGame` kezeli a játékosok sorrendjét, a mentésből folytatást, az új napot, a játék végét és az emberi/AI köröket. A `world.NewDay()` hívás kb. a 792. sorban, a `HumanTurn()` a 882., a `AI::Planner::Get().KingdomTurn()` a 938. sorban található.

A [world.cpp](../src/fheroes2/world/world.cpp) `World::NewDay()` függvénye (425) a nap/hét/hónap előreléptetése után frissíti a királyságokat, várakat, hősöket és eseményeket. Az új API `end_turn` művelete ezért nem lehet egyszerűen `world.NewDay()`: először a következő játékos következik, és meg kell őrizni az eredeti körkezelés sorrendjét.

A [gui/interface_events.cpp](../src/fheroes2/gui/interface_events.cpp) `EventEndTurn()` (244) mozgásra képes hős esetén megerősítő ablakot kér. Az explicit API-parancsnál ez kezelőfelületi megerősítésként kihagyható, a tényleges körváltási szabályok megtartásával.

## 2. Térkép és mentés betöltése, újraindítás

| Forrás | Szimbólum / sor | Találat |
|---|---|---|
| [game_scenarioinfo.cpp](../src/fheroes2/game/game_scenarioinfo.cpp) | pályaindítás, 465–500 körül | A kiválasztott pálya verziójától függően `world.LoadMapMP2(...)` vagy `world.loadResurrectionMap(...)` fut. A környező játékos- és beállítás-előkészítést is reprodukálni kell. |
| [world.h](../src/fheroes2/world/world.h) | `LoadMapMP2`, 211; `Reset`, 528 | Vannak betöltési/reset műveletek; ezek önmagukban nem a teljes munkamenet resetjei. |
| [game_io.cpp](../src/fheroes2/game/game_io.cpp) | `Game::Save`, 116; `Game::Load`, 166 | A mentés World, Settings, GameOver és szükség esetén kampányadatokat tárol. A betöltés hibái/figyelmeztetései UI-ablakokat is nyitnak. |
| [world.cpp](../src/fheroes2/world/world.cpp) | `World::Get`, 277; `Defaults`, 284; `Reset`, 299 | Globális világ és resetelhető adatok. A map seed a világ szerializálásának is része. |
| [game_auto_playtest.cpp](../src/fheroes2/game/game_auto_playtest.cpp) | playthrough hurok, 258–326 körül | Ismételt játékfuttatás, animáció- és hangbeállítások, naplimit, eredmények; hasznos életciklus-referencia. A felületet továbbra is használja. |

Javaslat: elsőre egy ismert mentésből induló, csak olvasó session legyen a belépő. A pályából új játék indítását külön feladatként kezeljük. A resetnek a világon túl az AI cache-eket, játékosállapotokat, aktuális döntést és hivatkozásokat is rendeznie kell.

Nem igazolt, hogy a normál mentés képes egy folyamatban lévő csatát vagy egy függvény belsejében váró választást folytathatóan eltárolni. Ezt az API nem ígérheti automatikusan.

## 3. Kalandtérkép, mozgás és objektuminterakciók

### Újrahasználható részek

- [heroes.h](../src/fheroes2/heroes/heroes.h): `calculatePath()` (526), `GetPath()`, `Move(bool)` (558), `Action()` (574), `ActionNewPosition()` (575), mozgáspontok, varázslatok és hősazonosító.
- [heroes_move.cpp](../src/fheroes2/heroes/heroes_move.cpp): `_moveStep()` (205 körül) `jumpToNextTile=true` esetén az animációs képkockák helyett logikai mezőlépést végez. A lépés mozgáspontot fogyaszt, felderít, pozíciót vált és objektuminterakciót indíthat.
- [heroes.cpp](../src/fheroes2/heroes/heroes.cpp): `Move2Dest()` (2049) alacsonyabb szintű pozícióváltás. Külső mozgásparancsként önmagában nem elég: nem helyettesíti a teljes mozgási és interakciós útvonalat.

### Összefonódások

A [heroes_action.cpp](../src/fheroes2/heroes/heroes_action.cpp) `Heroes::Action()` (3747) a királyság vezérlése alapján az `AI::HeroesAction()` ágba vagy az emberi objektumkezelésbe lép. Az emberi ág fókuszt, redraw-t, hangot és közvetlen dialógusokat használ.

Az objektumtípus szerinti dispatch többek között lényeket, várakat, hősöket, csónakot, nyersanyagot, kincset, tárgyat, szentélyt, bányát, lakóhelyet, teleportot, eseményt és kiegészítős objektumokat kezel. Ez jó hely az interakciók kategorizálásához, de egyetlen általános „click” helyettesítésével nem válik automatikusan headless-szé.

Az [ai_hero_action.cpp](../src/fheroes2/ai/ai_hero_action.cpp) `AI::HeroesMove()` (2245) is `LocalEvent::HandleEvents()` ciklusban fut. Rejtett AI-mozgásnál `hero.Move(true)` hívást használ, de grafikus/animációs feldolgozás továbbra is előfordul. Az AI-mozgás „elrejtése” nem azonos az eseményhurok nélküli szimulációval.

Javaslat: a parancsok legalább hősazonosítót és célmezőt tartalmazzanak. A parancsellenőrzés ellenőrizze a tulajdonost, aktuális játékost, megközelíthetőséget, mozgáspontot és az aktív döntést. A motor útvonalkezelését kell használni; közvetlen koordinátaátírás kerülendő.

## 4. Várak és gazdaság

| Művelet | Ellenőrzött kód | Használhatóság / további munka |
|---|---|---|
| Építhetőség és építés | [castle.h](../src/fheroes2/castle/castle.h) `CheckBuyBuilding`, `AllowBuyBuilding`; [castle.cpp](../src/fheroes2/castle/castle.cpp) `BuyBuilding`, 1260 | Jó közvetlen művelet. Fizet, módosítja az épületeket és kezeli több kapcsolódó hatásukat. API-s tulajdonos- és körvalidáció ettől még szükséges. |
| Lénytoborzás | `Castle::RecruitMonster`, 1025; `getRecruitLimit`, 1102 körül | Van `showDialog=false`. Készletet, pénzt, seregfeltöltést kezel. A kapott `Troop` mennyiségét a hívónak szigorúan validálnia kell: a helyi `count` korlátozása mellett a fizetés és csatlakoztatás az eredeti `troop` objektumot használja. Tetszőleges Python-bemenetet nem szabad nyersen továbbadni. |
| Hőstoborzás | `Castle::AllowBuyHero`, `RecruitHero`, 1004 | Jó kiindulás; a felkínált hősök, költség, elérhetőség és helyfoglalás ellenőrzését is át kell nézni. |
| Hajóvásárlás | `AllowBuyBoat`, `BuyBoat`, 2142 | Van közvetlen művelet; a hozzáférés és a mellékhatások további ellenőrzést igényelnek. |
| Kereskedelem | [dialog_marketplace.cpp](../src/fheroes2/dialog/dialog_marketplace.cpp) `Dialog::Marketplace`, 344; fizetés/jóváírás, 589–591 | Az emberi tranzakció a dialógusban történik. Kiemelendő egy ellenőrzött műveletbe. |
| Árfolyamok / AI-kereskedelem | [ai_common.cpp](../src/fheroes2/ai/ai_common.cpp) `AI::tradeAtMarketplace`, 368; `getTradeCost` használata | Árfolyamszámítás újrahasználható; az AI „szerezd meg ezt a költséget” stratégiája nem azonos az explicit játékosi csereparanccsal. |

A [castle_dialog.cpp](../src/fheroes2/castle/castle_dialog.cpp) és a vár egyéb dialog fájljai a megjelenítés és input helyei. Az új backend váradat-lekérése/építése nem hívhatja az `OpenDialog()` függvényt. A várkép előállításához viszont a rajzolást ki kell választani az interaktív hurokból.

## 5. Hősök, seregek és tárgyak

- [heroes_dialog.cpp](../src/fheroes2/heroes/heroes_dialog.cpp): `Heroes::OpenDialog()` (75) portrét, képességeket, sereget és tárgyakat rajzol, majd a 435. sor körül saját `HandleEvents()` ciklusba lép. Nem egy egyszerű kép-előállító függvény.
- [heroes_meeting.cpp](../src/fheroes2/heroes/heroes_meeting.cpp): két hős találkozása, sereg- és tárgymozgatás. A `moveArtifacts` (75), `swapArtifacts` (96) helyi segédfüggvények, például a varázskönyv áthelyezésére vonatkozó kivétellel.
- [army.h](../src/fheroes2/army/army.h): létező seregkezelő primitívek, például `SwapTroops`, `JoinTroop`, szétosztás.
- [army_bar.cpp](../src/fheroes2/army/army_bar.cpp): a csapatok szétosztásának, összevonásának és mozgatásának egy része közvetlenül a UI-kezelőben történik, `Dialog::ArmySplitTroop()` hívással és létszámmódosításokkal.

Javasolt parancscsaládok: `army.transfer`, `army.split`, `army.merge`, `army.swap`, `army.dismiss`, `army.upgrade`, `artifact.transfer`, `hero.dismiss`, `hero.buy_spellbook`.

Kötelezően megőrzendő szabályok: saját/engedélyezett cél, tényleges találkozás vagy várbeli hozzáférés, hely- és létszámkorlát, utolsó kötelező hősi csapat, varázskönyv és egyéb tárgykivételek. A primitív setterek létezése nem bizonyítja, hogy ezeket mind ellenőrzik. A felsorolt parancsok tervek, nem létező API-k.

## 6. Varázslás és döntési ablakok

A [heroes_spell.cpp](../src/fheroes2/heroes/heroes_spell.cpp) `Heroes::ActionSpellCast()` (359) adventure varázslatokat dispatch-el. A `Dimension Door` célmezőjét az AdventureMap felülete kéri be (199), a `Town Portal` várát dialógus választja ki (259). A Python API explicit célparamétert vagy külön döntés-választ adhat ezekhez.

A [heroes.cpp](../src/fheroes2/heroes/heroes.cpp) `_levelUpSecondarySkill()` (1862) másodlagos képességeket kínál fel, és emberi vezérlésnél közvetlenül `Dialog::LevelUpSelectSkill()` hívást végez (1891). Ezt adatokkal leírt választássá kell tenni, az eredeti RNG- és képességalkalmazási logika megtartásával.

Ellenőrzött további példák a `heroes_action.cpp` fájlban:

| Döntés | Jelenlegi bekérés |
|---|---|
| Ingyen vagy pénzért csatlakozó semleges lények | `Dialog::ArmyJoinFree`, `ArmyJoinWithCost`, kb. 392/410 |
| Menekülő lények üldözése / igen-nem választások | `showStandardTextMessage(... YES | NO)`, kb. 427 |
| Külső lakóhely toborzási mennyisége | `Dialog::RecruitMonster`, kb. 276 |
| Kincsesláda arany vagy tapasztalat | `Dialog::SelectGoldOrExp`, 1862 |
| Bányák, helyszínek, tárgyak és események | Sok objektumspecifikus kezelő, saját üzenetekkel/döntésekkel |

Az általános szöveges dialógusok globális automatikus „OK/YES” válasza nem megfelelő. El kell választani az értesítést a valódi döntéstől. A választásnak géppel olvasható típust, szereplőt, opciókat, korlátokat és azonosítót kell kapnia. A lokalizált üzenetszöveg csak kiegészítő adat legyen.

Nyitott: teljes, objektumtípusonkénti döntésleltár, beleértve például a szfinx szöveges válaszát, az ásást, a kampányválasztásokat és a speciális kiegészítős eseményeket. A fenti táblázat mintavétel, nem teljes lefedettségi állítás.

## 7. Csata és visszatérés a kalandtérképre

- [battle_main.cpp](../src/fheroes2/battle/battle_main.cpp): `Battle::Loader()` (291) előkészíti a seregeket/hősöket, csatamagot képez, lokális `Arena` objektumot hoz létre (389), és `arena.Turns()` hívásokkal végigfuttatja a csatát. Ezután eredményt és további hatásokat dolgoz fel. Emberi csatánál összefoglaló és újrajátszás-felkínálás is lehet (kb. 410).
- [battle_arena.cpp](../src/fheroes2/battle/battle_arena.cpp): `Arena::UnitTurn()` (460), AI vagy `HumanTurn` döntés (508/513), RNG-stream módosítás (517 körül), majd `ApplyAction()` (522), halottak eltávolítása és sorrendfrissítés. `Turns()` (552) kezeli a magasabb szintű körfolyamatot.
- [battle_command.h](../src/fheroes2/battle/battle_command.h): már léteznek `MOVE`, `ATTACK`, `SPELLCAST`, `RETREAT`, `SURRENDER`, `SKIP` stb. parancsok. Belső/automatikus parancsokat nem szükséges mind publikus akcióvá tenni.
- [battle_arena.h](../src/fheroes2/battle/battle_arena.h): `getAllAvailableMoves()` (192), elérhetőség-, út- és varázslatcél-segédek.
- Az `Arena(..., isShowInterface, ...)` grafikus felület nélkül is létrehozható, de a külső vezérlő ág még hiányzik. Az emberi `HumanTurn` jelenleg felületet követel.

Fontos: az API nem hívhatja egyszerűen az `ApplyAction()` függvényt a körkezelés megkerülésével. A meglévő `UnitTurn` feldolgozási sorrendjét kell megőrizni. Egyetlen publikus lépés nem feltétlenül azonos egy teljes egységkörrel: például a varázslás vagy morál további döntést/műveletet eredményezhet.

A lokális `Arena` és a hívási veremben élő objektuminterakció miatt elsőre előnyös a várakozó külső vezérlő: megtartható a verem és a csata élettartama. Ha minden `step()` visszatéréshez lebontanánk ezt, explicit folytatható állapotgépet kellene írni. A két megoldás eltérő munka; nem kell rögtön teljesen átírni a motort.

## 8. Headless és renderelés

### Ellenőrzött helyzet

- [screen.h](../src/engine/screen.h): a `Display` képpufferhez (`image()`, 248) és render backendhez (`BaseRenderEngine`) kapcsolódik.
- [screen.cpp](../src/engine/screen.cpp): `Display::Display()` (1457) renderert és kurzort készít; `setResolution()` (1474) a renderer erőforrás-allokációját és a kép méretezését együtt végzi. A `Display::resize()` önmagában nem általános offscreen puffer-allokáló API.
- A képpuffer palettaindexeket tárol, nem közvetlenül RGB-t. A publikus képhez palettakonverzió kell; az animált paletta/időzítés kezelését is meg kell határozni.
- [interface_gamearea.h](../src/fheroes2/gui/interface_gamearea.h): `GameArea::Redraw(Image&, ...)` (200) célképre tud rajzolni. Jó kiindulás a térkép renderéhez, de a nézet inicializálási függőségeit ellenőrizni kell.
- A vár- és hősképernyő kezdeti rajzolása interaktív dialog függvények része; a meglévő teljes képernyő headless előállításához külön renderelő belépési pontok szükségesek.

### Javasolt, külön kezelendő képességek

1. **Szimuláció:** nem nyit ablakot, nem vár animációra/inputra, nem játszik hangot, nem rajzol feleslegesen.
2. **Offscreen RGB-render:** kérésre képet készít; ettől még használhatja a grafikai asseteket és a szoftveres rajzolást.
3. **Emberi megjelenítés:** a kapott képet megjelenítő opcionális ablak.

A renderer módját előre konfiguráljuk. A képkérés nem fogyaszthat játék-RNG-t, nem mozgathat hőst, és nem változtathatja meg a szimuláció eredményét. A nézet/kamera változása külön prezentációs állapot.

Nyitott: SDL dummy/software backend elég-e az első offscreen próbához, vagy saját memóriapufferes backend szükséges. Egy elrejtett normál ablak nem bizonyít grafikus munkamenet nélküli működést. Kezdetben az assetek továbbra is szükségesek lehetnek; teljesen assetmentes szimuláció nem igazolt célképesség.

## 9. Megfigyelések, seed, reset és izoláció

### Adatforrások

- [world.h](../src/fheroes2/world/world.h): térkép, mezők, hősök, várak, nap/hét/hónap és királyságok.
- [kingdom.h](../src/fheroes2/kingdom/kingdom.h): `GetFunds()` (135), `GetHeroes()` (178), `GetCastles()` (182).
- [heroes.h](../src/fheroes2/heroes/heroes.h): `GetID()` (330), sereg, mozgáspont, képességek; további adatok a `HeroBase` osztályban.
- [maps_tiles.h](../src/fheroes2/maps/maps_tiles.h): `isFog()` (301/306). A játékosi megfigyelés nem lehet a teljes World ellenőrizetlen másolata.
- Csata: Arena / Force / Unit / Board objektumok, stabil kimeneti pillanatképpé alakítva.

Külön kell specifikálni a **játékosi megfigyelést** és a **teljes debug-állapotot**. Egy felderített térképi mező nem feltétlenül jelenti azt, hogy minden rajta lévő ellenséges adat korlátlanul hozzáférhető. Az API legyen egyértelmű a jogosult nézőpontról. Visszaadott adatok másolatok legyenek, ne reset után érvénytelen C++ pointerek.

### Véletlen és reprodukálhatóság

A [rand.cpp](../src/engine/rand.cpp) `CurrentThreadRandomDevice()` (85) thread-local, `random_device` által inicializált PCG32-t használ. A [world.cpp](../src/fheroes2/world/world.cpp) `Defaults()` (284) `Rand::Get` alapján állítja elő a map seedet. Teleport- és örvénycél kiválasztásánál is van általános `Rand::Get` használat (745/798), és a pályabetöltés is véletlen választásokat végez.

A csatának külön seedelt RNG-je van, a hősi szintlépésnek is vannak származtatott seedjei. Következmény: csak a Gymnasium/Python RNG seedelése, vagy csak a map seed beállítása nem biztosítja a teljes menet reprodukálhatóságát. A seedet a világ előkészítése előtt a szimulációt futtató szál RNG-jéhez is el kell juttatni, majd ellenőrizni az összes releváns kódutat. Az RNG állapotát mentésnél/resetnél külön auditálni kell.

### Izoláció

A globális `world`, `Settings::Get()`, `AdventureMap::Get()`, `AI::Planner::Get()`, `GameOver::Result::Get()` és az aktív Arena pointer miatt több független világ ugyanabban a folyamatban nem igazoltan támogatott. Elsőre egy dedikált motorfolyamat tartozzon egy környezethez. A sessionön belül minden játékállapot-hozzáférés egy motorvégrehajtási szálon történjen.

## 10. Javasolt közös API és végrehajtási modell

Az alábbi nevek tervek, nem meglévő függvények.

```text
Python Session / opcionális Gymnasium adapter
                 |
         verziózott parancskapcsolat
                 |
     motorfolyamat: session + command dispatcher
                 |
       meglévő szabályok és játékobjektumok
                 |
        döntési pont <-> külső vezérlő

     külön: nézet/kamera -> offscreen kép
```

A szimulációs C++ felületet a szállítási protokolltól külön kell tartani. Elsőre kis, strukturált üzenetek elegendők lehetnek; nagyméretű képeknél később bináris átadás vagy megosztott memória jöhet, mért igény alapján. Logok ne keveredjenek a protokoll válaszaival.

### Minimális session műveletek

- `load_save(path)`, később `new_game(map, players, seed)`.
- `observe(player_id)`, `inspect(entity_id)` a megengedett nézőponttal.
- `available_actions()` vagy akciótípusonkénti lekérdezések; nagy kalandtérképen nem feltétlenül jó minden lehetséges paraméterkombinációt kilistázni.
- `step(command)` végrehajt egy külső döntést és visszaadja a következő külső döntési pontot vagy a terminális eredményt.
- `answer_choice(choice_id, option)` a függőben lévő választáshoz.
- `render(view, entity_id, camera)`, `save(path)` csak támogatott biztonságos pontokon, `close()`.

### Válasz/pillanatkép

```text
session_id, episode_id, state_version
phase: adventure | battle | choice | terminal
current_player
observation
pending_choice: { id, kind, actor, options, constraints } | null
events: [ ... ]
result / error
```

A `castle` és `hero` elsődlegesen lekérdezhető/rajzolható nézetek. Ha például egy találkozás közben csak két hős közti cserék engedélyezettek, azt a döntési kontextus külön leírja. A phase nem a jelenlegi ablak nevét tükrözi.

### Végrehajtási szabályok

- A motor a külső döntési pontnál vár; a lekérdezések és képkérések nem folytatják a játékot.
- Beágyazott csata vagy választás esetén ugyanaz a session marad, a következő döntési pont megváltozik.
- A várakozás idején a hívási verem első változatban megmaradhat. A protokoll kiszolgálásának a várakozó állapotban is működnie kell.
- A `step()` alapból a következő **bármely külső vezérlőhöz tartozó** döntésig halad. Az „ellenfél automatikusan lépjen a következő saját körömig” viselkedést egy adapter adhatja.
- A belső események (sebzés, jutalom, halál, napváltás) naplózódnak. Az értesítések nem válnak felesleges OK-akciókká.
- Hibás vagy elavult parancs strukturált hibát ad, és lehetőség szerint nem módosít állapotot; validálás a mutáció előtt. A command/state/choice azonosítók megakadályozzák az előző resetből maradt válaszok alkalmazását.
- Külső vezérlés külön fogalom legyen az emberi/AI szabályoktól és a grafika engedélyezésétől. A pontos integrációhoz a `CONTROL_*` ellenőrzések auditja szükséges; nem elegendő egy új enumérték felvétele.
- Gymnasium reward/observation encoding a Python adapter felelőssége lehet; az alap API adjon használható eseményeket és nyers adatokat.

## 11. Megvalósítási sorrend és igazolási pontok

| Szakasz | Konkrét eredmény | Ellenőrzés |
|---|---|---|
| A. Session és csak olvasó hozzáférés | Ismert mentés betöltése menü nélkül; nap, játékos, hősök, várak és erőforrások lekérése | Összevetés a normál játékban látható adatokkal; hiba esetén nincs blokkoló ablak |
| B. Headless alap és közös vezérlő | Ablak/hang nélküli indulás, külső döntés-várakozás, leállítás és ismételt reset | Több egymást követő betöltés; nincs felugró ablak, végtelen inputvárás vagy állapotmaradvány |
| C. Adventure végigmenő próba | Hős szabályos mozgatása, egyszerű nyersanyagfelvétel, kör vége és AI-kör | Mozgáspont, készlet, új nap és ellenfél válaszának helyessége; nem puszta koordinátaátírás |
| D. Vár- és hősműveletek | Építés, toborzás, sereg/tárgy kezelés; piaci csere kiemelése | Költség, készlet, napi korlát, hozzáférés; hibás mennyiségek/utolsó csapat kezelése |
| E. Választások és csata | Láda/szintlépés/semleges csatlakozás; kalandtérképből indult csata és visszatérés | Minden döntés Pythonból jön; jutalom, veszteség, hősállapot és következő döntés helyes |
| F. Render | Térkép, vár, hős, csata RGB-képe | Ablak nélkül előáll; `render()` előtt/után ugyanaz a játékállapot és RNG-állapot |
| G. Reprodukálhatóság, lefedettség és Gymnasium | Seedelt új játék, akciómaszk/encoding, terminálás/időlimit, több motorfolyamat | Azonos seed+akciósor azonos kimenet; eltérő példányok izoláltak; Gymnasium env checker; sebességmérés |

A szakaszok a teljes játék architektúráját építik. Az első adventure próba szándékosan korlátozott tartalmú, nem jelenti azt, hogy a még át nem vezetett objektuminterakciók már támogatottak. Az API jelölje a képességeket és adjon egyértelmű hibát a nem támogatott helyzetekre; ne döntsön helyettünk csendben.

Első technikai kísérlet: **a meglévő mentésbetöltő és World-adatok menü nélküli használata, minimális inicializálással**. Ez gyorsan megmutatja a tényleges display/asset függőségeket. Utána a mozgási út és az első választás kezelése a következő kockázatcsökkentő próba.

## 12. Még elvégzendő célzott vizsgálatok

- Minden emberi és AI objektuminterakció eltéréseinek listája; a megosztható szabálylogika kijelölése.
- Az összes döntést kérő hely kategorizálása, nemcsak `Dialog::` névkereséssel.
- AI-körök és pathfinder/cache resetje, győzelem/vereség és kampányfolytatás UI-függései.
- Tulajdonos-, láthatóság-, távolság-, költség- és mennyiségvalidáció parancscsaládonként.
- Betöltési/mentési hibaútvonalak, valamint félbeszakítás folyamatban lévő nested döntésnél.
- SDL/renderer nélküli vagy offscreen inicializálás tényleges futtatási próbája; grafikus assetek minimális készlete.
- A vár/hős/csata nézet egyszeri statikus kirajzolásának leválasztási pontjai.
- RNG-hívások teljes auditja, renderelés és szimuláció RNG-függetlensége, mentés folytathatósága.
- Windows többfolyamatos indítás, protokoll-életciklus, process crash és elveszett kapcsolat kezelése.
- Steps/s, reset-idő, memória és renderköltség mérése. Jelenleg nincs megalapozott sebességígéret.

## 13. Külső referenciák

Ezek az előző beszélgetési körben megnyitott elsődleges projektforrások. Nem kész fheroes2-integrációk.

- [ViZDoom fejlesztői útmutató](https://vizdoom.farama.org/main/dev/dev_guide/): C++ mag, Python bindingok, külön Gymnasium wrapper. A motorvezérlő API és az RL-adapter rétegzéséhez referencia.
- [ViZDoom DoomGame API](https://vizdoom.farama.org/main/api/python/doom_game/): epizódindítás, `get_state`, `set_action`, `advance_action`, `make_action`. Itt időlépések vannak; a Heroes API döntési pontokra épülhet.
- [OpenSpiel API](https://github.com/google-deepmind/open_spiel/blob/master/docs/api_reference.md): `current_player`, `legal_actions`, `apply_action`, játékosi megfigyelés és terminális állapot. A körökre osztott szemantikához referencia.
- [VCMI Gym](https://github.com/smanolloff/vcmi-gym): közeli Heroes III csata/RL projekt. A README a dokumentáció elavultságát külön jelzi.
- [VCMI connector dokumentáció](https://github.com/smanolloff/vcmi-gym/blob/main/doc/connector.md): a motor állapotot ad és akciót vár, a Python akciót ad és állapotot vár; a dokumentált megoldás szálakat és szinkronizációt használ. Ebből a kézfogási elv alkalmazható, a konkrét technológia külön döntés.
- [VCMI környezet dokumentáció](https://github.com/smanolloff/vcmi-gym/blob/main/doc/env_info.md): strukturált csataadatok, akciók és maszkok. Ez a leírás régebbi környezetverzióra vonatkozik.
- [Gymnasium Env API](https://gymnasium.farama.org/api/env/): `reset`, `step`, `terminated`, `truncated`, render módok.

## Következő munkamenethez

Először ezt a fájlt és az aktuális változásokat ellenőrizni; a jegyzet kutatási állapot, nem implementáció. Megvalósításkor az A–C szakaszra fókuszálni, a teljes játék közös session- és döntési modelljével. A csata önálló demo lehet később, de nem helyettesíti az adventure/vár/hős lefedettségét. Új ellenőrzött találatot és tényleges futtatási eredményt ebbe a jegyzetbe visszavezetni.
