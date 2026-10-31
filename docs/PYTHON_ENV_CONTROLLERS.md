# Oldalankénti Python-/AI-vezérlés — 4/A

A `HeroesSession` minden standard pályabeli résztvevőjéhez külön `python` vagy `builtin_ai` vezérlő rendelhető.
Ez érvényes a kalandtérképre, a csatában sorra kerülő oldalra és a hőshöz tartozó választásokra is.
Az állapot továbbra is minden résztvevő adatait tartalmazza; nincs kötelező kézi játékos.

## Futtatható bemutató

Az eredeti játékadatokkal, opcionális Python-builddel és a `THEOTHER.MP2` pályával:

```powershell
uv run --project python python python/examples/controllers.py
uv run --project python python python/examples/controllers.py --mode mixed --steps 30
uv run --project python python python/examples/controllers.py --mode python --steps 10
```

Az alap mód beépített AI–AI játékot futtat, egy résztvevő köre után állapotot kér és kiírja mindkét oldal
aranyát/hősszámát. A `mixed` mód a zöld oldalt, a `python` mód mindkettőt Pythonból vezérli.
A példában a Python kalandtérképi policy csak befejezi a körét; a csatában egyszerű harci policy válaszol.
Ez vezérlési példa, nem tanított vagy teljes stratégiai agent. Más pályán az összes tényleges résztvevőt konfigurálni kell.

## Minimális AI–AI ciklus

```python
from fheroes2_env import HeroesSession

with HeroesSession("./fheroes2.exe", timeout=120) as game:
    decision = game.reset(
        map_path="maps/THEOTHER.MP2",
        seed=123,
        controllers={1: "builtin_ai", 2: "builtin_ai"},
        rule_profiles={1: "ai", 2: "ai"},
    )["decision"]
    while decision["phase"] != "terminal":
        result = game.advance_simulation(max_turns=1, token=decision["token"])
        state = game.get_state(include_serialized=False)
        decision = result["decision"]
    print(decision["simulation"]["outcomes"])
```

Linux/macOS alatt a megfelelő `fheroes2` executable útvonalát add meg.
`max_turns=1..64` résztvevői kört jelent, nem napot vagy csataegység-lépést.
Az előreléptetés legkésőbb a kért körök után megáll; Python-döntésnél korábban is visszatér.
Egy natív AI-kör maga teljes, szinkron motorművelet; közben csak külső csata/választás szakítja meg.
A kliens timeoutja továbbra is érvényes. A köztes lekérdezéshez az egykörös léptetés ajánlott.

## Vezérlő és natív szabályprofil

Külön fogalom a résztvevő színe, szabályprofilja és döntéshozója:

| Beállítás | Jelentés |
|---|---|
| `controllers={1: "python", 2: "builtin_ai"}` | Ki hozza az oldal döntéseit |
| `rule_profiles={1: "ai", 2: "ai"}` | Új pálya natív human/AI beállítása, még a világ inicializálása előtt |
| `player["control"]`, `is_human`, `is_ai` | Tényleges natív szabályprofil az exportált állapotban |
| `player["controller"]` | Az aktuális sessionben hozzárendelt döntéshozó |

A vezérlő megadása nem írja át a mentés `CONTROL_HUMAN`/`CONTROL_AI` jelöléseit, pénzét vagy világát.
Ez megőrzi a natív nehézségi induló erőforrásokat, napi bónuszokat, eseményjogosultságokat és körsorrendet.
Új pályán az explicit `rule_profiles` az összes pályabeli résztvevőt lefedi; mentésnél nem használható.
Elhagyásakor az eddigi új játék alapbeállítás marad: a kijelölt `player_id` emberi szabályú, a többiek AI-szabályúak.
AI-szabályú oldal is lehet teljesen Python-vezérelt, emberi szabályú oldal pedig beépített AI-vezérelt.
A `controllers` elhagyásával a korábbi egykülsőoldalas API és Gym-adapter működése megmarad.

Résztvevőazonosítók: kék `1`, zöld `2`, piros `4`, sárga `8`, narancs `16`, lila `32`.
A Python API elfogadja az angol színneveket és numerikus stringeket is. Mindegyik pályabeli oldalhoz
pontos hozzárendelés kell, további/hiányzó oldal hiba. Megszűnt oldal eredménye megmarad, körét az ütemező kihagyja.
A vezérlők sessionen belüli átadása nincs: más konfigurációhoz `reset` szükséges.
Forrás nélküli `reset(seed=...)` megőrzi az előző pályát, vezérlőket és új pályás szabályprofilokat.

## Több Python-agent döntési ciklusa

`decision["player_id"]` az éppen döntő résztvevő, nem feltétlenül a kalandtérképi támadó.
Egy program például `agents[player_id]` szerint küldheti a megfigyelést külön policyknak.
Egy sessionhez egy soros klienskapcsolat tartozik; több motorfolyamat továbbra is indítható egymástól függetlenül.

| `phase` | Következő művelet |
|---|---|
| `adventure` | Az aktuális Python-oldal engedélyezett hős-/várművelete vagy `end_turn` |
| `battle` | Az aktuális egység oldalának Python-agentje választ a natív `battle.actions` listából |
| `choice` | A hős tulajdonosának agentje válaszol a `pending_choice` alapján |
| `simulation` | `advance_simulation`; itt `player_id=0`, az ütemezett oldal `simulation.turn_player_id` |
| `terminal` | Eredmények lekérése, majd reset vagy lezárás |

A Python-oldal `end_turn` parancsa a következő résztvevőhöz lép. Ha az beépített AI,
először `simulation` határ érkezik, és külön előreléptetés szükséges. Az AI-kör eseménye
`ai_turn_completed`, `player_id` és `day` mezőkkel; a napi pályaesemény szintén azonosítja az oldalt.
A következő Python-oldal előkészített körét az ütemező egyszer adja át, napi bevétel duplázása nélkül.
A mentés aktuális köre már előkészített checkpoint, ezért első hozzárendeléskor nem jár új bevétel.

A beépített AI támadása közben egy Python-védő csatájánál az előreléptetés visszatér a védő tokenjével.
A válasz után ugyanaz a natív AI-hívás folytatódik. Ha a kezdeményező külső oldal veszít,
a másik aktív résztvevő kapja a következő döntést, nem maradunk egy kiesett oldalnál.
Minden akcióhoz az aktuális friss token kell; rossz oldal, idegen entitás vagy elavult döntés nem módosítja a világot.
Folyamatban lévő csatánál/választásnál a `session.stop` az egész kezdeményező műveletet — akár AI-kört — visszagörgeti.

## Eredmények és határok

`decision["simulation"]` és `state["simulation"]` tartalmazza a vezérlőket, natív körsorrendet,
következő oldalt, `finished` jelzést és az `outcomes` résztvevőnkénti natív GameOver bitértékeit.
`0` folyamatban; a natív nyerési/vesztési bitek értelmezése a `game_over.h` szerinti.
AI-only futásnál a régi, egy külső oldalhoz kötött `game_result` lehet `0` terminális állapotban is;
az összes eredményt az `outcomes` alapján értelmezd.

A lezárás a natív győzelmi/vereségi predikátumokat használja. A kizárólag emberi szabályprofilokra vonatkozó
speciális célhős-/vereségfeltételek nem válnak automatikusan AI-jogosultságúvá; a pálya natív AI-győzelmi
engedélyei megmaradnak. Ezért a speciális célú térképek mindegyike külön ellenőrzést igényel.
A szokásos összes ellenfél legyőzése AI-only módban is natív győzelemhez vezet.

A konfigurált session nem bővíti automatikusan a külső akcióprofil objektum- és varázslatlistáját.
A beépített AI továbbra is a saját teljes natív stratégiáját használja: mozog, gyűjt, épít, vásárol és harcol.
A külső profilban nem támogatott művelet hiba és visszaállítás; nincs helyette hallgatólagos AI-döntés.
A Gym `Fheroes2-v0` továbbra is egy külső oldal tanítási adaptere. Több agent már az alap sessionnel vezérelhető;
PettingZoo/RLlib multi-agent wrapper külön, nem ennek a lépésnek a része.

## Ellenőrzés

2026-10-31, Windows: a teljes Python/Gym regressziós készlet **157/157** sikeres;
a **11/11** új vezérlési teszt Debug buildben, bekapcsolt C++ assert ellenőrzésekkel is sikeres.
Az opcionális Release/Debug és a normál `ENABLE_PYTHON_ENV=OFF` build lefordult.
Mindhárom `controllers.py` példa lefutott; a seed=123 AI–AI játék 77 résztvevői kör után,
a 39. napon natív kék győzelemmel zárult (`outcomes={"1":1,"2":256}`), video/audio inicializálás nélkül.
A korábbi 14. lépés teljesítményméréseit ez nem helyettesíti új benchmarkkal.

A `python/tests/test_controllers.py` valódi motortesztjei: két Python-oldal körsorrendje/bevétele,
változatlan natív mentésflag-ek, AI-only futás emberi szabályprofil nélkül natív eredményig,
seedelt ismétlés és tömbösített/egykörös léptetés egyezése, kétoldalas csata, vegyes támadó/védő,
AI-szabályú Python-hős szintlépése, rossz token és hibás parancs atomi elutasítása.
A külön `controllers-ai-boss-day1.sav` tesztmentést a meglévő natív fixture builder készíti;
ez a teszt előkészítésének explicit szabályprofil-választása, nem a futó session átjelölése.

A normál játékban nincsenek vezérlő-hozzárendelések: a célzott közös motorhookok ilyenkor az eredeti
natív ágra esnek vissza. A Python-rész továbbra is opcionális desktop build; nincs új Python- vagy venv-függőség
a hagyományos játékhoz vagy mobilbuildhez. Linux/macOS/mobil SDK-ellenőrzés továbbra is hátralévő munka.
