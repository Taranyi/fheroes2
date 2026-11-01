# Teljes adventure-epizódok ellenőrzése

A 4. lépés normál pályák valódi natív játékbefejezését ellenőrzi. Nem kampányteszt és nem adventure RL-tanítás.
Az ellenőrzés két utat jár be: minden oldalt vezérlő beépített AI-szimuláció, illetve aktív Python-policy a teljes `HeroesEnv` felületen.
A pálya- és eredeti mentésadatokat nem módosítja. Az összes jelentés és kép a Git által figyelmen kívül hagyott `build/` fában marad.

## Reprodukálható teljes futás

```powershell
uv run --project python --cache-dir .tools/uv-cache --extra gym --locked python python/examples/adventure_acceptance.py --executable build/windows-local/fheroes2.exe --output build/python-env-adventure/new-run --frames
```

A [futtató](../python/examples/adventure_acceptance.py) friss kimeneti könyvtárat kér.
Ehhez a négy felsorolt eredeti mapfájl és a hozzájuk tartozó játékadatok helyben szükségesek;
a CI külön, SHA256-tal ellenőrzött demóadatokat használ, nem a helyi kereskedelmi adatokat tölti fel.
Minden epizód saját motorfolyamatot és elkülönített ideiglenes profilt használ.
Érvénytelen SDL-videó-/hangdriver mellett fut, a runtime ellenőrzi a video/audio/controller/input/animáció tiltását.
Az eredeti mapfájlok SHA256-a a futás előtt és után egyezik.

A teljes mátrix 15 epizód:

- AI–AI: The Other Side, Broken Alliance és 7 Deserts, két-két seeddel; Dragon Wars egy seeddel.
- The Other Side újrajátszása egyesével léptetett AI-körökkel, a 12 körös kötegekkel kapott teljes végállapottal összehasonlítva.
- Broken Alliance külön, minden oldalon AI szabályprofilú futása: az eredeti hiba regressziója.
- Aktív Gym: The Other Side két seed, 7 Deserts két seed, Broken Alliance egy seed.
- A The Other Side Gym-epizód teljes megismétlése azonos seeddel: minden akció, megfigyeléstömb, jutalom és végállapot hash-e egyezik.

Az alapfutás megőrzi a pálya eredeti emberi/AI **szabályprofiljait**. Ez független a vezérlőtől: az emberi szabályprofilú oldalt is vezérelheti beépített AI.
A 7 Deserts natív időkorlátos vereségi feltétele csak az eredeti emberi szabályprofilra vonatkozik.
Az összes szabályprofil AI-ra cserélése ezt a feltételt megváltoztatná; ilyen konfigurációból nem állítunk elő mesterséges győzelmet vagy vereséget.

## Mit jelent a sikeres epizód?

Csak a motor `terminal` döntése számít. Az AI-szimulációban minden résztvevő natív eredménye ellenőrzött.
A Gym-úton `terminated=True`, `truncated=False`, üres terminális akciómaszk és a natív eredménnyel egyező jutalom szükséges.
Egy natív vereség is teljes epizód; nem nevezzük győzelemnek. A 7 Deserts esetében minden oldal elveszítheti a játékot, például a natív időkorlát miatt.
A futtató saját nap-/lépéskorlátja, motorhiba, nem támogatott interakció vagy Gym-profilhiba **sikertelen ellenőrzés** marad.

A teljes világ továbbra is omniscient, mindegyik oldal hőseivel, seregeivel, váraival és erőforrásaival.
A futtató a mozgások, sereg-/vártulajdon-/épület-/hajóállapot-változások megfigyelt számát rögzíti.
Ezek snapshotok közötti változások, nem a rejtett AI-parancsok kitalált darabszámai.
A natív csaták és AI-körök számát külön a motor eseményeiből veszi.

Az aktív [Python-policy](../python/examples/adventure_policy.py) kizárólag natív módon validált Gym-akciókat választ:
épít, toboroz, várból hősbe adja a sereget, várakat keres, mozog, hőst bérel, választásokra válaszol és csatázik.
Nem írja át a világot, nem csal, és a saját körét nem adja át a beépített AI-nak.
Egyszerű, teljesen informált elfogadási policy, nem tanított vagy szakértői stratégia. A veresége nem motorhiba és nem az RL tanulhatóságának mérése.

A kezdeti, terminális és új döntésfázisú állapotoknál a világ-/döntéslekérdezés és render előtti/utáni állapot/token is egyezik.
Az AI visszajátszási hash csak a protokoll `state_version` kurzorát normalizálja, mivel az eltérő kérésszámot követi; gameplay-adatot nem hagy el.
A `--frames` néhány natív PPM-pillanatképet ír, nem folyamatos animációt vagy válogatott győzelmi videót.

## Javított elakadás

A hosszú Broken Alliance-szimulációban az AI `HeroesCastSummonBoat` függvénye feltétel nélkül lekérte az AdventureMap felületét,
amely a képernyő inicializálásához vezetett. Headless módban ez helyesen `unsupported_interaction: ... display access` hibával megállt.
A hibakereső hívási lánca az AI hajóidézését azonosította; ugyanebbe a hibába a nagy Dragon Wars pálya is belefutott.

A [célzott javítás](../src/fheroes2/ai/ai_hero_action.cpp) a `GameArea` lekérését a két tényleges animációs ágba helyezi.
A mana-/mozgásköltség, hajóeltávolítás, célmező, tulajdonos és varázslási logika nem változik.
Headless módban az animációs feltétel eleve hamis. A normál ablakos/mobil játék ugyanazokat az animációkat futtatja.
Nincs új buildkapcsoló, Python-függőség vagy mobilprojekt-módosítás.

A [regressziós tesztek](../python/tests/test_adventure_complete.py) valódi teljes pályával védik a hajóidézést,
a natív FH2M időlimites vereséget, az aktív Gym-epizód determinisztikus visszajátszását és a saját tesztkeret kifutásának hibáját.
A platform-CI Linux/macOS Python ON jobjai a demoletöltés után a teljes Broken Alliance AI-regressziót is futtatják,
kép-/modellfeltöltés nélkül.

## Eredmények és korlátok

**15/15 teljes natív epizód sikeres**, saját tesztkeret miatti truncation és motorhiba nélkül.
Kilenc AI–AI futás összesen **2607 natív oldalkört**, hat aktív Gym-futás **1499 elfogadott akciót** végzett;
a számok a külön visszajátszási kontrollokat is tartalmazzák.

| Pálya | Méret | AI–AI befejezési nap | Aktív Gym befejezési nap |
|---|---|---|---|
| The Other Side | 36×36 | 56, 39; ismétlés: 56 | 42, 28; ismétlés: 42 |
| Broken Alliance | 72×72 | 149, 190; külön minden-AI szabályprofil: 98 | 63 |
| 7 Deserts | 72×72, FH2M | 9, 9 | 8, 8 |
| Dragon Wars | 144×144 | 235 | Nem része a Gym-mátrixnak |

A The Other Side, Broken Alliance és Dragon Wars AI–AI futásai natív győztest adtak.
A 7 Deserts futásai natív vereséggel zárultak; az eredeti emberi szabályprofilú oldal eredménye `LOSS_TIME`.
Az egyszerű aktív Python-policy mind a hat Gym-epizódot vereséggel fejezte be (`reward=-1`).
Ez az API végigfuttathatóságának ellenőrzése, nem sikeres adventure RL-tanítás vagy erős Python-stratégia bizonyítéka.

Az egyesével/kötegelve léptetett AI-futás teljes végállapota, valamint a megismételt Gym-futás
összes megfigyelés-/akció-/jutalomhash-e egyezik. A futások után minden motorfolyamat 0 kóddal lezárult.
A forrás-, natív executable- és bemeneti mapujjlenyomatok külön ellenőrzöttek.
Az időadatok funkcionális tesztfutásokból származnak, részben a regressziós csomaggal párhuzamosan; nem külön sebességbenchmarkok.

**247/247 sikeres regressziós teszt**, kihagyás és hiba nélkül, 289,6 másodperc alatt.
A normál Windows-build Python OFF állapotban is sikeresen újrafordult; a kiadott játék 233 fordítási parancsából egyik sem kap Python-adapter definíciót.
A javítás [platform-CI-futásában](https://github.com/Taranyi/fheroes2/actions/runs/41265920968) **7/7 build sikeres**,
beleértve az Android négy ABI-ját, az iOS-szimulátort, a normál desktop buildeket és a macOS alkalmazáscsomagot.
Linuxon és macOS-en a teljes demópályás hajóidézés-regresszió is sikeres.

A végső helyi jelentés: `build/python-env-adventure/completed/report.json`.
A képek és részletes akciósorok az epizódok almappáiban vannak; a teljes regresszió naplója `build/python-env-adventure/full-tests.log`.
A forrás-/motor-/bemeneti ujjlenyomatok a jelentésben szerepelnek.
A platform-CI helyi összesítője: `build/python-env-adventure/platform-report.json`.

Ez négy konkrét normál pálya, 36×36/72×72/144×144 mérettel és MP2/FH2M formátummal.
Nem minden létező pálya, objektumkombináció, Sphinx-válasz, csapatfelállás vagy kampány teljes bejárása.
A Gym továbbra is fix kapacitású, és a profilba nem férő állapotnál explicit hibát ad; nem dob el csendben akciókat vagy adatokat.

## Teljes fennmaradó sorrend

5. Az első adventure RL-kísérlet azóta elkészült: [jutalom, tanítás, mérés és helyi videók](PYTHON_ENV_ADVENTURE_RL.md).
   A folytatás erősebb, teljes pályát nyerő stratégia, az információs-varázslási ismétlések kezelése és több feladatos tanítás.
6. Kampányátmenetek, átvitt hősök/jutalmak és kampányválasztások.
7. Igény szerint korlátozott láthatóság, több agentes Gym-wrapper és self-play.
8. Platformonkénti Python-csomagok, csomagolt motor, automatikus motorkeresés,
   `pip install` és tiszta telepítésből ellenőrzött példák; az eredeti játékadatok külön biztosítandók.
