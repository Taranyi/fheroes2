# Megvalósítási terv: fheroes2 Python API és headless Gymnasium env

Dátum: 2026-10-25. Állapot: az 1. és 2. lépés elkészült 2026-10-26-án; játékállapot-lekérés és szimuláció még nincs.

2026-10-26-i pontosítás: elsődleges követelmény a meglévő C++ motor kis mértékű, jól elkülönített módosítása és a játék önálló továbbfejleszthetősége.

Platformkövetelmény: a Python-rész opcionális, asztali PC-s fejlesztés. Az Android/iOS és más szokásos játékbuild nem függhet a venv-től vagy Pythontól.
A CMake `ENABLE_PYTHON_ENV` opciója alapból `OFF`; csak a helyi PC-s preset engedélyezi. A későbbi motorintegrációknál is meg kell őrizni ezt a határt.

Előzmény és kódfeltérképezés: [PYTHON_SIMULATION_RESEARCH.md](PYTHON_SIMULATION_RESEARCH.md).

## Végcél és az első kész verzió határa

Pythonból lehessen betölteni/újraindítani és léptetni egy teljes játékmenetet, adatokat lekérni, parancsokat küldeni és kérésre képet kapni. A környezet működjön ablak, hang és animációs várakozások nélkül is. Legyen egy általános Python API és egy erre épülő, ellenőrzött Gymnasium adapter.

A támogatás nem korlátozódik csatára. Az első kész verzió elfogadási pályáján legyen kalandtérképi mozgás, erőforrásfelvétel, körváltás és beépített AI ellenfél, várépítés/toborzás, hős/sereg/tárgy kezelés, valódi választás és kalandtérképről induló, onnan visszatérő csata. A kalandtérkép, vár, hős és csata nézetéről legyen RGB-kép.

Az „alap env” nem egyenlő minden eredeti pálya, kampány és speciális objektum teljes támogatásával. Az első kiadás egy dokumentált standardjáték-profilon és tesztpályán garantálja a működést. A támogatott műveletek és objektumtípusok név szerinti listát kapnak. Nem támogatott helyzetnél egyértelmű hiba és esemény érkezik; sem csendes AI-döntés, sem végtelen UI-várakozás nem elfogadható. Kampányok, pályaszerkesztő, hálózatos játék, teljes speciálisobjektum-lefedettség és optimalizált nagyléptékű RL későbbi bővítés.

Az eredeti játékadatokat kezdetben használjuk. A headless azt jelenti, hogy nincs szükség ablakra, grafikus felhasználói munkamenetre, kézi inputra vagy hangkimenetre; nem ígér SDL nélküli fordítást vagy assetmentes szimulációt.

## Rögzített alapirány

- A játék szabályainak egyetlen megvalósítása a meglévő C++ motor marad. Pythonban nem készül második mozgás-, gazdaság-, csata- vagy AI-logika. Az env ugyanazokat a szabályokat és műveleteket használja, mint az alapjáték.
- Az új session, protokoll, állapotexport és külső vezérlő lehetőleg saját egységekbe kerül. A meglévő kódba kevés, jól megnevezett csatlakozási pontot teszünk: indítás, döntésbekérés, értesítés és megjelenítés. Kerülendő a mindenfelé szétszórt Python/headless feltétel és a teljes motor átszervezése.
- Ha egy szabály jelenleg UI-függvényben él, csak a szükséges műveletet választjuk le közös függvénybe, és azt az eredeti UI is használja. Nem másoljuk át külön env-változatba. A meglevő költségeket, sorrendet, véletlent és mellékhatásokat megőrizzük.
- A szimulációs mód a bemenet, a várakozás és a megjelenítés működését változtatja meg; nem ad eltérő játékszabályokat. Különösen nem hagyunk ki játékmeneti mellékhatást csak azért, mert normálisan rajzolás közelében fut.
- A motor továbbfejlesztésénél a közös szabálymódosítás az envben is érvényesül. Új objektum vagy új döntéstípus igényelhet új adaptert és támogatási tesztet; teljes automatikus kompatibilitást nem ígérünk.

- Egy motorfolyamat tartozik egy Python sessionhöz, így a jelenlegi globális állapot izolált.
- A meglévő fheroes2 futtatható állomány kap explicit szimulációs indítási módot; nem kell rögtön újrahasznosítható könyvtárrá szervezni az egész projektet.
- Első kapcsolat: Python által indított gyermekfolyamat, stdin/stdout felett UTF-8 JSON-sorok. A stdout kizárólag protokoll, minden log stderr vagy külön fájl. A Windows standard streamek/SDL indítás viselkedését az első működő próbán igazoljuk; ha nem használhatók megbízhatóan, ugyanazt a protokollt helyi pipe-ra visszük át.
- Nagy RGB-képekhez kezdetben bináris képfájl a session saját ideiglenes könyvtárában és metaadat a protokollban. Python NumPy tömbbé olvassa. Nem adunk pixeleket JSON-számok millióiként. A közvetlen bináris/megosztott memóriás átadás későbbi mért optimalizálás.
- Minden játékállapot-olvasás és -módosítás ugyanazon motorvégrehajtási szálon történik. A döntésre váró parancshurok a beágyazott hívási vermet életben tartja.
- A motor a következő külső döntésig fut. Lekérdezés/render nem lépteti a világot. Az ellenfeleket a session konfigurációja szerint a meglévő AI vezérli.
- Külső vezérlő, játékosi jogosultság és megjelenítési mód külön fogalom. Az AI-nak jelölés nem lehet a külső vezérlés helyettesítője.
- A normál ablakos játék továbbra is működik; a szimulációs eltérések explicit módban lépnek életbe.

## Tervezett API-szerződés

Python session: `HeroesSession(...)`, `reset(...)`, `observe()`, `inspect(...)`, `available_actions()`, `step(action)`, `render(...)`, `close()`.

A reset kezdetben ismert mentést tölt be. A seedelt pályaindítás későbbi lépésben kerül be. A folyamat újraindítása elfogadott első reset-megoldás: ez biztonságosan eldobja a beágyazott csatát/választást és a globális cache-eket. A gyors folyamaton belüli reset nem előfeltétele az alap envnek.

Minden állapotválasz tartalmazza az API-verziót, epizód- és állapotazonosítót, az aktuális játékost, a döntési helyzetet (`adventure`, `battle`, `choice`, `terminal`), a megfigyelést, az előző lépés eseményeit, valamint a függő választás és eredmény adatait. A vár/hős emellett lekérdezhető objektum és választható rendernézet, nem kötelezően egy nyitott ablak állapota.

A parancs típusos és paraméterezett, például `hero.move`, `turn.end`, `castle.build`, `castle.recruit`, `army.transfer`, `artifact.transfer`, `battle.attack`, `choice.answer`. Nem képernyőkoordinátákra kattintunk. További parancsok a lefedettségi táblában kerülnek rögzítésre.

Hibás/idejétmúlt parancs a módosítás előtt elutasítandó. Külön hibakategória: hibás bemenet, tiltott művelet, nem támogatott tartalom, motorhiba és kapcsolati hiba. A motorhibát nem szabad győzelem/vereség vagy szokásos időlimit formájában elrejteni.

## Lépések

### 1. Reprodukálható kiindulás és elfogadási pálya

**Munka:** ellenőrizni a jelenlegi Windows-buildet és a meglévő helyi változtatásokat. Kijelölni egy mentést, majd egy kicsi standard tesztpályát. Összeírni a kezdő hősök/várak/pénz/világnap elvárt adatait és a szükséges grafikus assetek helyét. Rögzíteni az első verzió támogatási profilját.

**Eredmény:** követhető alapállapot, tesztadat-elérési konfiguráció és képességlista. Felhasználói mentést nem írunk felül.

**Kész, ha:** az alapjáték lefordul, a kiválasztott mentés/pálya működik, és a későbbi próbák ugyanebből indíthatók. Nem szükséges érzékeny vagy eredeti játékadatokat a repóba másolni.

### 2. Szimulációs indítás és az első Python-kapcsolat

**Munka:** C++ indítási mód, protokollfejléc, kérésazonosítók, `hello`/`capabilities`/`close`; Pythonból folyamatindítás és válaszolvasás. Elsőre a meglévő grafikus inicializálás átmenetileg megmaradhat. Timeout, hibakimenet és folyamatlezárás már itt kezelendő.

**Fő kód:** `game/fheroes2.cpp`, `game/game_init.cpp`, új session/transport egységek; Python csomagváz. A pontos fájlneveket az implementáció kezdetén rögzítjük.

**Kész, ha:** egy Python-script elindítja a motort, verziót/képességet kér és tisztán leállítja. Nem kell kézzel menüt kezelni. Ez az első tényleges Python-elérés.

### 3. Mentésbetöltés és csak olvasó világ-API

**Munka:** a protokollon `load_save` és mindent látó `get_state`. Nap, aktuális játékos, minden játékos (az AI is), pénz, összes hős/vár, pozíciók, seregek, tárgyak és a köd mögötti térkép is. A UI-hibaablakok helyett strukturált betöltési hibák. A kezdeti állapotnál nem indul automatikusan teljes emberi inputhurok vagy extra nap. A játékosi láthatóságra szűrt `observe(player_id)` külön későbbi felület.

**Fő kód:** `game_io.cpp`, `world.*`, `kingdom.*`, `heroes.*`, `castle.*`.

**Kész, ha:** Pythonból ugyanazokat az alapadatokat látjuk, mint a mentésben; ismételt lekérdezés nem módosít világot. A saját játékosi megfigyelés és az explicit debug-állapot külön felület.

### 4. Külső vezérlő és döntési kézfogás

**Munka:** a körkezelésben külső vezérlő bekötése; a motor döntésnél megáll és kiszolgálja a lekérdezéseket. Közös command dispatcher és validálás. Géppel olvasható választási/értesítési szolgáltatás, amelyet az emberi UI és a külső vezérlő eltérően kezelhet. A jelenlegi `CONTROL_*` elágazásokat célzottan auditáljuk.

**Fő kód:** `game_startgame.cpp`, `players.*`, `heroes_action.cpp`; új vezérlő/decision egységek.

**Kész, ha:** az aktuális játékos, az állapot és a várakozás kiszámítható; egy nem megfelelő játékos/elavult állapot parancsa nem fut le. A várakozás alatt az `observe`, `render` és `close` feldolgozható.

### 5. Valódi headless működés

**Munka:** konfigurálható core/display/audio inicializálás, memóriabeli vagy ellenőrzött offscreen render backend; animációs és inputvárakozások leválasztása a session útvonaláról. A működési profilban elért dialógusok már nem nyithatnak ablakot. A nem támogatottak azonosítható hibát adnak.

**Fő kód:** `engine/core.cpp`, `engine/screen.*`, `game_init.cpp`, esemény- és animációkezelés.

**Döntési kapu:** először SDL dummy/software próbával mérjük fel a függőségeket. Ha az nem tud ablak és grafikus munkamenet nélkül pufferbe rajzolni, memóriapufferes backend készül. Az ablak elrejtését nem tekintjük kész headless megoldásnak.

**Kész, ha:** a mentésbetöltés és lekérdezés ablak, kézi input és hang nélkül működik. A később bekötött műveleteknél ugyanezt a feltételt folyamatosan ellenőrizzük.

### 6. Adventure mozgás, felvétel és körváltás

**Munka:** `hero.move`, egyszerű erőforrásfelvétel és `turn.end`. A meglévő útkeresést és logikai mezőlépést használjuk. Megőrizzük a mozgáspontot, ködöt, eseményeket, elvesztett hőst és a játékossorrendet. Az AI-körök is input/animációs várakozás nélkül futnak, majd a motor visszaadja a következő külső döntést.

**Fő kód:** `heroes_move.cpp`, `heroes_action.cpp`, `ai_hero_action.cpp`, `game_startgame.cpp`, `world.cpp`, `interface_events.cpp`.

**Kész, ha:** Python-script szabályosan mozog és felvesz egy erőforrást, lezárja a kört, az ellenfél lép, a nap a megfelelő időben vált. A mozgás nem közvetlen koordinátaátírás.

### 7. Várműveletek és kereskedelem

**Munka:** építhetőség, építés, elérhető lények és pontos mennyiségű toborzás, hősvásárlás, indokolt esetben hajó; közös ellenőrzött piaci csere. Tulajdonos, napi limit, készlet, ár, sereghely és elérhetőség validálása.

**Fő kód:** `castle.cpp`, `castle.h`, `dialog_marketplace.cpp`, közös árfolyamszámítás.

**Kész, ha:** Pythonból várablak nélkül építünk és toborzunk, a készlet/pénz helyes; hibás mennyiség vagy tiltott építés nem módosít adatot. Külön figyelni a kutatási jegyzetben rögzített `RecruitMonster` bemeneti feltételeire.

### 8. Hősök, seregek és tárgyak

**Munka:** csapatcsere, szétosztás, összevonás és átadás, tárgyátadás; a profilhoz szükséges fejlesztés/elbocsátás/varázskönyv-vétel. A UI-ban élő szabálylogika közös műveletekbe kerül. A találkozási és várbeli hozzáférést a backend ellenőrzi.

**Fő kód:** `army.*`, `army_bar.cpp`, `heroes_meeting.cpp`, `heroes_dialog.cpp`, tárgykezelés.

**Kész, ha:** egy hős seregét rendezzük, jogosult hősök között átadunk csapatot/tárgyat; az utolsó kötelező csapat és a varázskönyv kivételei megmaradnak. Ez headless módban is működik.

### 9. Választások és adventure varázslatok

**Munka:** legalább kincsesláda arany/tapasztalat, szintlépési képesség, semleges csatlakozás/üldözés, toborzási mennyiség; a profilon szereplő varázslatok célparaméterei. `choice_id` alapján érkező válasz után az eredeti művelet folytatódik. Értesítésből esemény lesz, nem kötelező OK-akció.

**Fő kód:** `heroes_action.cpp`, `heroes.cpp`, `heroes_spell.cpp`, kapcsolódó dialog függvények.

**Kész, ha:** a Python döntés nélkül a motor nem választ helyettünk; a válasz után egyszer alkalmazza a hatást. Több egymást követő vagy egymásba ágyazott választás és reset is kezelhető.

### 10. Csata a teljes játékmenet részeként

**Munka:** külső döntés bekötése az `Arena::UnitTurn` folyamatába. Aktív egység, board, seregek és szabályos lépések exportja. Mozgás, közelharc, lövés, passzolás, majd a profilhoz szükséges varázslás, menekülés és megadás. Belső morál/sorrend/RNG feldolgozás marad a motorban. Eredményablak helyett esemény/eredmény.

**Fő kód:** `battle_main.cpp`, `battle_arena.*`, `battle_command.*`, `battle_action.cpp`.

**Kész, ha:** kalandtérképi támadásból csata indul, Python végigvezérli, a veszteség/jutalom/friss hősállapot alkalmazódik, esetleges szintlépés után visszatérünk a kalandtérképre. Nem csak különálló battle demo működik.

### 11. Kérésre renderelés minden fő nézetről

**Munka:** térkép kamera/nézőpont, vár, hős és aktív csata egyszeri kirajzolása a meglévő rajzolólogikával, interaktív ablakciklus nélkül. Palettaindex -> RGB konverzió, képméret és dtype dokumentálása; Python `uint8[H,W,3]` tömb. Session-ideiglenes képek takarítása lezáráskor.

**Fő kód:** `screen.*`, `interface_gamearea.*`, `castle_dialog.cpp`, `heroes_dialog.cpp`, `battle_interface.*`.

**Kész, ha:** mind a négy nézetről értelmes kép kérhető ablak nélkül; sok lépés render nélkül is működik. Renderelés beiktatásával ugyanaz az akciósor ugyanarra a világ- és RNG-állapotra vezet.

### 12. Reset, seedelt új játék, lezárás és Python csomag

**Munka:** a 2. lépésben kezdett Python kliens kész sessionné bővítése; context manager, beállítások, dokumentált kivételek. Ismert mentéses és seedelt új pályás reset, az összes releváns motor-RNG kezdeti állapotának szabályozása. Az első verzió resetkor újraindíthatja a motorfolyamatot. Kilépés/csatából és választásból reset, timeout és crash kezelése. Csomagolás helyi `pip install -e` használathoz.

**Kész, ha:** ismételt reset különböző helyzetekből megbízható, nincs hátrahagyott motorfolyamat; két session egymástól független. Azonos pálya/konfiguráció/seed/akciósor ugyanazokat a szemantikai állapotokat és eredményeket adja. A seed nem írja felül egy betöltött mentés világadatait; a folytatás RNG-szemantikáját külön dokumentáljuk.

### 13. Gymnasium adapter

**Munka:** `HeroesEnv` a session köré: `reset`, `step`, `render`, `close`, `observation_space`, `action_space`, epizódlimit és egyszerű reward. Az adapter egy külső játékost vezérel, a többit a beépített AI. Minden felmerülő választás/csata ugyanabban az epizódban marad.

Az alap Gym-profil fix felső korlátokat rögzít (térképméret, entitások és választási opciók). A megfigyelés fix alakú, kitöltött `Dict` tömböket, érvényességi maszkokat, döntéstípust és a szabályos akciók leírását tartalmazza. Az első action space `Discrete(K)` lehet a megfigyelésben szereplő akciójelöltekhez: a jelöltleírások és a maszk együtt határozzák meg a slotok aktuális jelentését. A sorrend determinisztikus, az epizódon belüli space nem változik. A korlát feletti pályát/állapotot egyértelműen elutasítjuk, érvényes akciókat nem vágunk le csendben. Az általános Python API továbbra is strukturált parancsokat és gazdag lekérdezést ad.

Győzelem/vereség: `terminated=True`. Külső lépésszámkorlát: `truncated=True`. Nem támogatott állapot/motorhiba: kivétel. Kezdeti reward: győzelem +1, vereség -1, köztes lépés 0; az egyéb pályakimenetek szabályát rögzítjük. A motor eseményei az `info` adatokban elérhetők, későbbi reward wrapperhez.

`render_mode=None`: nincs rajzolás. `render_mode="rgb_array"`: ablak nélkül képkérés a konfigurált nézetről; az általános session API-ban a többi nézet továbbra is kérhető. Az ablakos `human` mód opcionális, nem előfeltétele a kész headless envnek.

**Kész, ha:** a Gymnasium `check_env` sikeres, egy szabályos akciókat mintázó Python-agent több epizódot végigfuttat, reset/terminálás/időlimit helyes. A pontos space-méretek és akciókódolás a 6–10. lépés tényleges adatai alapján rögzítendők a csomag publikus szerződésében.

### 14. Elfogadási futtatás és használati útmutató

**Munka:** egy Python API-példa, egy Gymnasium-példa és egy teljes forgatókönyv futtatása. Dokumentálni: build/telepítés, assetek és pálya megadása, támogatott műveletek, nézetek, ismert korlátok. Mérés: lépések/s, reset-idő, renderidő, több session működése. A mért sebességet közöljük, előzetes teljesítményígéret nélkül.

**Kész, ha:** az alábbi teljes elfogadási lista teljesül, és a normál játék indításának/alapfunkcióinak ellenőrzése sem mutat regressziót. Ez az „alap Python + headless Gym env kész” pont.

## Végső elfogadási lista

- [ ] Pythonból elindítható és lezárható, menükézi kezelés nélkül.
- [ ] Ablak/hang nélkül betölt és léptet; grafikus felhasználói munkamenetre nincs szükség.
- [ ] Játékosi állapot és saját hős/vár/sereg/tárgy adatok lekérdezhetők.
- [ ] Hősmozgás, egyszerű felvétel, körváltás és beépített AI működik.
- [ ] Várépítés, toborzás, hős/sereg/tárgy műveletek működnek a deklarált profilon.
- [ ] A tesztpálya választásai nem nyitnak ablakot, Pythonból megválaszolhatók.
- [ ] Kalandtérkép -> csata -> választás, ha van -> kalandtérkép út működik.
- [ ] Térkép, vár, hős és csata RGB-képe kérhető, a szimuláció módosítása nélkül.
- [ ] Hibás parancs nem okoz részleges tiltott műveletet; nem támogatott helyzet nem fagy le.
- [ ] Ismételt reset, seedelt új játék és több külön session ellenőrizve.
- [ ] Gymnasium space-ek fixek, a jelöltek és akciómaszk következetesek, `check_env` sikeres.
- [ ] Győzelem/vereség és időlimit helyesen különbözik; folyamat-/motorhiba látható.
- [ ] Több epizódos példa, telepítési leírás és támogatási mátrix elkészült.
- [ ] A normál játék és az env közös szabálymegvalósítást használ; nincs párhuzamos Python-/env-játéklogika. A meglévő C++ fájlok változásai célzottak, a szokásos játékút is ellenőrzött.

## Hogyan haladunk ezen végig?

Minden számozott lépés külön végrehajtható munkaszakasz. Kezdetekor átnézzük az előző eredményt és az aktuális repóállapotot. Elvégezzük a módosítást, futtatjuk a hozzá tartozó célzott ellenőrzést, és itt rögzítjük a bizonyítékot/korlátot. A szükséges közös alapok egymás után készülnek; nincs szükség arra, hogy előbb az egész C++ motort átírjuk és csak a végén próbáljuk a Pythont.

Ha egy technikai próba megcáfol egy feltételezést, az érintett megvalósítási részletet és függőséget frissítjük, a végcélt megtartva. Különösen az offscreen backend, a beágyazott döntések és az RNG-reset igényel futtatással igazolt döntést.

| Lépés | Állapot | Bizonyíték / következő teendő |
|---|---|---|
| 1 | Kész | Inkrementális build és ablakos indítás ellenőrizve; két helyi referenciamentés, 36×36-os kis pálya indítása/mentése/visszatöltése, elvárt UI-adatok és fájlujjlenyomatok rögzítve. Részletek: [PYTHON_ENV_BASELINE.md](PYTHON_ENV_BASELINE.md). A numerikus motorállapot exportja a 3. lépés feladata. |
| 2 | Kész | Opcionális `--python-env` bootstrap, JSON-soros `hello`/`capabilities`/`close`, külön uv-csomag és 14 integrációs/folyamathiba-teszt. Leírás: [Python-kapcsolat](../python/README.md). A bootstrap nem tölt játékot és nem jelenti a teljes headless szimuláció elkészültét. |
| 3 | Kész | Valódi C++ mentésbetöltő, ablak/hang nélküli `load_save` és mindent látó `get_state`, AI-val és teljes térképpel. A JSON-projekció mellett a teljes tartós motorállapot saját szerializált payloadja is kérhető. Két referencia, változatlan ismételt lekérdezés, hibából helyreállás és folyamatizoláció: összesen 21 sikeres teszt. Részletek: [Python API](../python/README.md). Műveletek és láthatóságra szűrt megfigyelés még nincsenek. |
| 4 | Kész: kezdeti adventure döntési pont | `start_session`/`get_decision`, C++ mentettkör-callbackben élő parancsvárakozás, közös tokenes `step` ellenőrzés, `session.stop`, `close`/EOF kilépés. A játékos vezérléstípusa nem változik, a világ nem lép. 28 sikeres teszt. [Szerződés és CONTROL-audit](PYTHON_ENV_CONTROLLER.md). Valódi játékmeneti művelet, render és konkrét választási dialógus még nincs; ezeket az 5–10. lépés köti be. |
| 5 | Kész: jelenlegi betöltés/döntés/render profil | Explicit headless policy; választható core-komponensek a régi alapértékekkel; önálló adventure viewport, RGB képkérés és tényleges runtime-adatok. 35 sikeres Python-teszt, C++ policy-ellenőrzés és SDL dummy/software próbák. [Leírás és korlátok](PYTHON_ENV_HEADLESS.md). A még nem bekötött játékműveleteknél ezt továbbra is ellenőrizni kell. |
| 6 | Kész: adventure_basic profil | Natív útkeresés/mezőlépés, saját szárazföldi hős és sima erőforráskupac; `turn.end` valódi AI-körökkel, bevétellel és hétváltással. Tokenverziózás, események és teljes műveleti checkpoint/visszaállítás a nem támogatott interakcióknál. 43 sikeres Python-teszt. [Szerződés, példa és korlátok](PYTHON_ENV_ADVENTURE.md). Emberi csata, választás és hajózás még nincs bekötve. |
| 7 | Első rész kész: várlekérdezés, építés, pontos toborzás | A natív feltételek, költségek, napi limit, faji fejlesztések, készlet és garrison/hős cél ellenőrzésével; az eredeti játékszabály-függvények változatlanok. [Szerződés és futtatható példa](PYTHON_ENV_CASTLE.md). Hősvásárlás, piaci csere és hajó még hátravan. |
| 8–14 | Tervezett | A fenti lépések szerint. |

### Korai, futtatható Gym-példa a 6. lépés után

A felhasználó kérésére már most készült egy opcionális `AdventurePreviewEnv` és
[futtatható bemutató](../python/examples/gym_loop.py), [használati leírással](../python/README.md#runnable-gymnasium-preview).
A meglévő C++ motor köré kerül: egy saját hős nyolc iránya és kör vége, valódi RGB-kép, teljes világállapot az `info` mezőben,
friss folyamatból történő reset, ötértékű `step`, külön Python-megjelenítő vagy teljesen ablak nélküli futás.
A jutalom egyelőre mindig nulla, nincs akciómaszk, a seed nem vezérli a motor véletlenét; a nem támogatott csata/választás
továbbra is kivétel. A 12 próbálkozásos bemutató-időlimit `truncated`, a valódi motorbeli végállapot `terminated`.
A Gymnasium saját ellenőrzőjének sikeres futása ezt a szűk profilt igazolja; a 13. lépés teljes szerződése továbbra is tervezett.
Ez a kiegészítés csak Python-kódot és opcionális Python-függőségeket ad, új C++-módosítás nélkül.
Windows alatt mind az 51 Python-teszt sikeres (ebből 8 az opcionális Gym-példát ellenőrzi); a látható bemutató
két epizódon át lefutott. A base Python-csomag külső függőség nélkül is importálható maradt.
