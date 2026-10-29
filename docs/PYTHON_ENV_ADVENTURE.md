# Adventure alapműveletek és natív AI-kör

A 6. lépésben az `adventure_basic` profil működik: saját hős szárazföldi mozgatása, sima erőforráskupac felvétele és
a kör lezárása a beépített AI-játékosokkal. Nem közvetlen koordinátaátírás vagy külön Python-játékszabály hajtja végre.
A csata, választási helyzet és hajózás továbbra is későbbi lépés. A később hozzáadott várépítés és toborzás
külön [várműveleti leírásban](PYTHON_ENV_CASTLE.md) szerepel.

## Használat

```python
with HeroesSession("fheroes2.exe", timeout=60) as game:
    game.load_save("build/python-env-baseline/fixtures/other-side-day1.sav")
    decision = game.start_session(1)
    result = game.move_hero(52, 32, 25, token=decision["token"])
    decision = result["decision"]
    print(result["events"])
    result = game.end_turn(token=decision["token"])
    decision = result["decision"]
```

A két kényelmi hívás ugyanazt a közös `step` dispatchert használja:

- `hero.move`: `params={"hero_id":52,"x":32,"y":25}`.
- `turn.end`: üres `params`.
- A korábbi `session.stop` változatlanul csak a vezérlőről válik le, nem zár le játékoskört.

Az akció válasza `decision`, `events`, `state_version` és `game_result`. Mindig a visszakapott új tokent kell használni.
Az `episode_id` csak mentésbetöltési kísérletenként változik. A `state_version` betöltési kísérletnél és sikeres játékműveletnél
nő, a `decision_id` új várakozásnál és sikeres játékműveletnél. Lekérdezés/render nem lépteti ezeket.
A korábbi tokent újra elküldve `stale_decision` a válasz. A hibás vagy nem támogatott parancs nem fogyasztja el a döntést.

## Mozgás és erőforrás

A hősnek aktívnak és a vezérelt játékos tulajdonában kell lennie. A cél nulla alapú mezőkoordináta.
A motor saját `world.getPath` útkeresője adja az útvonalat és a terep/út/átlós mozgás költségét.
A teljes útvonalnak ki kell férnie a megmaradt mozgáspontból; részleges többnapos útvonal ebben a profilban nincs.
Minden érintett mezőt még a mozgás előtt ellenőrzünk: víz, esemény, harcot/választást igénylő vagy más nem támogatott
akcióobjektum, illetve szörnyvédettség esetén a művelet elutasított. Saját várból ki lehet indulni, a várba belépés még nincs bekötve.

A tényleges lépések `Heroes::Move(true)` hívások. A `Scout`, mozgáspont-levonás, mezőváltás, útvonal-fogyasztás és
`ActionNewPosition` megmarad. A radar/fókusz/hang/frissítő animációk headless ágon kimaradnak.
Az első módosításnál fut a betöltött kör szükséges előkészítése; a `start_session` önmagában továbbra sem változtat világot.

Sima `OBJ_RESOURCE` célmezőn a közös `ActionToPickupResource` adja hozzá a készletet, törli az objektumot és a metaadatát.
Az eltűnésnél ugyanaz az objektumeltávolítás fut, amelyet normálisan az animáció befejezése végez.
Az eredeti szabály szerint a hős a kupac előtt is maradhat; a visszakapott `to` és `target` ezért eltérhet.

Események: `hero_moved` (hős, kiindulás, tényleges cél, kért cél, elköltött mozgáspont),
`resource_collected` (mező és tényleges készletnövekmény).

## Körváltás

A `Game::advanceExternalTurn` a normál játékkal közös játékossorrendben végrehajtja a fennmaradó AI-köröket.
Mindegyikhez az eredeti `ActionNewDayResourceUpdate`, `ActionBeforeTurn` és `AI::Planner::KingdomTurn` tartozik.
Ezután `world.NewDay()` következik, a játék vége ellenőrzésével, majd az emberi kör előkészítése és napi bevétele.
A mentett emberi kör bevételét nem adjuk hozzá még egyszer. A hét/hónap/napi készlet- és hősfrissítések az eredeti motorban maradnak.

Az AI saját szabályai szerint mozog, toboroz, vásárol, épít, és emberi résztvevő nélküli csatát is a meglévő motorra bízhat.
Az emberi játékos nem kap AI-vezérlést és nehézségi AI-bónuszt. A natív szabályokkal már megállapított győzelem/vereség
`phase="terminal"` és numerikus `game_result` formában tér vissza, videó/dialog helyett. Terminális helyzetben csak a lecsatlakozás marad elérhető.

Események: `ai_turn_completed`, `turn_ended`, `new_week`, illetve az ember napi eseményei `daily_event` formában
(cím, szöveg és tényleges készlethatás). A játékosállapotban megjelent a `daily_income` és a `lost_town_days` is.
Az `available_actions` parancsneveket jelez; még nem ad minden paraméterezett célra legalitási maszkot.

## Határ és visszaállítás

Emberi részvételű csata és választási helyzet még nem automatikus döntés. Ha például az AI megtámadja az emberi várat,
`unsupported_interaction` a válasz, és a teljes külső művelet visszaáll. A későbbi csatavezérlő nélkül a kör ezen a ponton nem folytatható.
Más, még leválasztatlan interaktív motorútvonal ugyanezzel a hibakategóriával állhat meg. Ez nem kész, tetszőleges pályát végigjátszó Gym env.

A parancs előtt a motor saját szerializálójával világ/settings/game-result checkpoint készül; emellett megőrizzük a
motor főszálának RNG-állapotát, az objektum-UID számlálót és az adapter döntési állapotát. Kivételnél ezek visszaállnak,
a tranziens AI/útkereső cache-ek érvénytelenednek. A visszaállítás nem fájlmentés, nem írja felül a bemeneti mentést.
Ha maga a visszaállítás hibás, `session_faulted` és új mentésbetöltési igény következik; a hibát nem rejti el vereségként.
A folyamat összeomlását/timeoutját továbbra is a Python-kliens jelzi. Az új seedelt reset a 12. lépés feladata;
külön folyamatok tetszőleges AI-akciósorára még nincs reprodukálhatósági ígéret.

## Ellenőrzés

2026-10-29, Windows, 43 sikeres Python-teszt. Az új nyolc adventure teszt ellenőrzi:
natív útvonal/mozgáspont, egynél több mezős út, egyszeri 7 fa felvétele, elutasítás utáni teljes világ- és tokenegyezés,
mindkét referencia AI-játékosainak tényleges elmozdulása, egyszeri napi bevétel, heti utánpótlás,
lecsatlakozás utáni folytatás és valódi, később elért emberi csatánál a teljes kör visszaállása és azonos hibával újrapróbálhatósága.
A korábbi betöltési, render-, izolációs és kapcsolati tesztek is megmaradtak, érvénytelen SDL-meghajtókkal és külön profillal.

Teljes példa a helyi referencián:

```powershell
uv run --project python python python/examples/adventure.py
uv run --project python python -m unittest discover -s python/tests -v
```

A példa Roxanával lép, lefuttatja az ellenfél körét, majd felvesz 7 fát, és képet ment a `build/python-env-adventure.ppm` fájlba.
A játékműveletekhez az AGG-k mellett a normál játékhoz illő H2D adatcsomag is szükséges; az AI belső harci számításai
is olvashatnak képadatokat. Ez az SDL video/audio inicializálását nem igényli. A Python nélküli Windows-build is sikeres;
más platformok SDK-buildjét helyben nem futtattuk.
