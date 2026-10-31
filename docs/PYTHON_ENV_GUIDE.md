# fheroes2 Python és Gym: használati útmutató és ellenőrzött állapot

2026-10-31. Az alap Python API, a strukturált Gym-adapter és a 4/A oldalankénti vezérlés elkészült a dokumentált profilon.
A session több Python-agentet, vegyes és beépített AI–AI játékot is támogat; [vezérlési API és példa](PYTHON_ENV_CONTROLLERS.md).
A Gym-adapter továbbra is egy külső oldalt vezérel. A 14. lépés rögzített mérései az akkori build történeti eredményei.
Ez az útmutató a jelenleg ellenőrzött képességeket írja le, nem minden eredeti pálya/kampány teljes támogatását.

## 1. Fordítás és telepítés

A C++ játékhoz továbbra sem kell Python. A desktop adapter explicit `ENABLE_PYTHON_ENV=ON` opcióval épül;
az alapérték `OFF`. Android/iOS/egyéb nem támogatott célrendszeren az engedélyezést a CMake elutasítja.
A közös játékszabályok a natív motorban maradnak. A venv csak a Python-kliens és az opcionális RL-csomagok környezete.

A már beállított Windows-fejlesztői gépen, a repó gyökeréből:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File script/windows/local.ps1 -Action build
uv sync --project python --extra gym
uv run --project python python python/examples/hello.py
```

Az első helyi Windows-eszköztelepítéshez: [Windows buildútmutató](README_windows_local.md).
Saját desktop CMake-környezetben, a szokásos motorfüggőségek előkészítése után:

```sh
cmake -S . -B build/python-env -DENABLE_PYTHON_ENV=ON
cmake --build build/python-env --parallel
```

A futtatható állomány helyét a saját generátorodhoz kell igazítani: Windows alatt `.exe`, többkonfigurációs buildnél
további konfigurációs almappa is lehet. Az eredeti SDL/runtime könyvtárak továbbra is szükségesek a futtatáshoz.
A mostani futás Windows alatt történt; ez nem Linux/macOS vagy mobil SDK-buildbizonyíték.

`uv` helyett saját Python 3.11+ venv-ben is telepíthető:

```sh
python -m pip install -e ./python
# Csak Gym használatához:
python -m pip install -e "./python[gym]"
```

A base `fheroes2_env` csomagnak nincs külső futásidejű Python-függősége. A Gym-modult külön importáljuk,
így normál sessionhöz nem szükséges NumPy/Gymnasium. A `viewer` extra kizárólag a régebbi vizuális preview külső ablakához kell.

## 2. Játékadatok és induló állapot

Az eredeti AGG játékadatok szükségesek; a játékműveletekhez és renderhez a motorverzióhoz illő
`files/data/resurrection.h2d` is kell. A headless nem jelent SDL- vagy assetmentes motort: ablak, hangkimenet,
kézi input és animációs várakozás nélkül fut.

Ha az executable vagy az assetek más könyvtárban vannak, a motorfolyamat `FHEROES2_DATA` változója mutasson a
játékadatgyökérre. Példa a gyermekfolyamatra korlátozott beállítással:

```python
import os
from fheroes2_env import HeroesSession

environment = dict(os.environ, FHEROES2_DATA="C:/path/to/fheroes2")
with HeroesSession("C:/path/to/build/fheroes2.exe", env=environment, timeout=60) as game:
    episode = game.reset(map_path="C:/path/to/maps/THEOTHER.MP2", seed=123)
    state = game.get_state(include_serialized=False)
    print(state["date"], state["players"])
```

Alternatíva a `reset(save="...sav", seed=123)`. Mentés esetén a világseed és a mentett világadatok megmaradnak;
a megadott seed a főszál további véletlen döntéseit szabályozza. Új játékban az induló világ is seedelt.
Ez meglévő standard MP2/MX2/FH2M pálya betöltése, nem véletlen pályageneráló API.
Az ismételhetőség azonos motorbuildre, assetekre, konfigurációra és akciósorra vonatkozik.

A session jelenleg egy, a mentésben emberi szabályprofillal rendelkező aktív oldalt vár; annak minden döntését
Python hozhatja, emberi input nélkül. Új pályán `player_id` választhatja a pálya által megengedett ilyen oldalt,
alapértéke kék (`1`); `difficulty=0..4`, alapértéke normal (`1`). A többi oldalt a natív AI vezérli.
Az AI-oldalak adatai ugyanúgy lekérdezhetők, és a 4/A `controllers` konfigurációval Pythonból is vezérelhetők.

A repóban nincs terjesztve eredeti AGG vagy bináris tesztmentés. A helyi referencia mentések előkészítése:
[baseline](PYTHON_ENV_BASELINE.md). Ezt követően a külön teszthelyzetek generálhatók:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File script/windows/python-env-artifact-fixture.ps1
```

Új klónban a hiányzó mentést nem helyettesítjük csendben más kezdőállapottal. Saját map/save megadható az általános API-nak;
a helyi, név szerinti elfogadási példákhoz a dokumentált tesztmentések kellenek.

## 3. Általános Python session

```python
with HeroesSession("fheroes2.exe", timeout=60) as game:
    episode = game.reset(save="checkpoint.sav", seed=123)
    decision = episode["decision"]
    # Az azonosítót saját állapotból válaszd, ne állandó példaszámként kezeld.
    state = game.get_state(include_serialized=False)
    own = next(p for p in state["players"] if p["id"] == decision["player_id"])
    print(own["hero_ids"], own["castle_ids"])
    result = game.end_turn(token=decision["token"])
    decision = result["decision"]
    frame = game.render(view="adventure")
    episode = game.reset(seed=123)  # friss folyamat, ugyanaz a forrás
```

A válasz fázisa adventure/choice/battle/terminal. A session API-ban a parancshoz mindig a legfrissebb tokent kell
visszaadni. Kalandtérképi lépés közben választás vagy csata indulhat: ilyenkor az élő natív művelet vár a Python válaszára,
majd folytatódik. A `get_state` minden résztvevőt exportál, nem láthatóságra szűrt megfigyelés.
A `include_serialized=True` teljes natív mentéspayloadot is visszaad; gyakori tanítási lekérdezéshez ez általában fölösleges.

A képkérés nem lépteti a szimulációt. Hős/vár esetén `hero_id`/`castle_id` kell; AI-entitás is választható.
`view="battle"` csak aktív csatánál működik. A visszaadott `RGBFrame` HWC uint8 pixeleket ad; a három részletes nézet
natív 640×480 képből méreteződik. A `close` idempotens; a context manager használata lezárja a gyermekfolyamatot.

Részletes szerződések: [reset/seed](PYTHON_ENV_RESET.md), [vezérlő](PYTHON_ENV_CONTROLLER.md),
[kalandtérkép](PYTHON_ENV_ADVENTURE.md), [vár/gazdaság](PYTHON_ENV_CASTLE.md), [sereg](PYTHON_ENV_ARMY.md),
[hősműveletek](PYTHON_ENV_HERO_OPERATIONS.md), [tárgyak](PYTHON_ENV_ARTIFACTS.md),
[választások](PYTHON_ENV_CHOICES.md), [csata](PYTHON_ENV_BATTLE.md), [nézetek](PYTHON_ENV_VIEWS.md).

## 4. Gym és RL használat

```python
from fheroes2_env.gym_env import make_env

with make_env(executable="fheroes2.exe", save="checkpoint.sav",
              max_steps=1000, render_mode=None) as env:
    obs, info = env.reset(seed=123)
    for _ in range(10000):
        action = env.action_space.sample(mask=obs["action_mask"])
        obs, reward, terminated, truncated, info = env.step(action)
        if terminated or truncated:
            obs, info = env.reset()
```

Az új környezet `Fheroes2-v0`; a régi `Fheroes2AdventurePreview-v0` továbbra is csak kilenc akciós vizuális bemutató.
A tanításhoz az új, fix numerikus Dict megfigyelést és maszkolt Discrete jelölteket használd.
A slot jelentése az aktuális `obs["actions"]` sorában van, döntésenként változhat; nem stabil, örök parancsazonosító.
`info["actions"]` ugyanezt olvasható parancsobjektumként adja, `info["state"]` az összes oldal teljes strukturált állapotát,
`info["events"]` a natív eseményeket tartalmazza. Ezek Python-másolatok, nem a motor belső memóriájának írható nézetei.

A maszkot használó algoritmus/wrapper előnyös. `env.unwrapped.action_masks()` bool maszkot is ad.
A padding slot nem küld motorparancsot: nulla jutalmú elutasított próbálkozás, amely beleszámít a lépésszámkorlátba.
A véletlen mintázás működési próba, nem tanított agent és nem bizonyítja, hogy értelmes stratégiát tanultunk.
Az `int64` feature-ök skálázását/normalizálását és a numerikus jelöltleírások feldolgozását az RL-modellhez kell kialakítani.

Jutalom: köztes `0`, natív győzelem `+1`, natív vereség `-1`; eseményekből külön reward wrapper építhető.
`terminated` csak valódi motoreredmény, `truncated` az agent-próbálkozások limitje. A motorhiba, timeout, nem támogatott
helyzet és profilkorlát kivétel, utána reset kell; nem tévesztjük össze játék végi eredménnyel.

`render_mode=None` egyáltalán nem rajzol. `render_mode="rgb_array"` esetén az explicit `env.render()` kér képet;
`render_view="auto"` csatában csataképet, egyébként térképet ad. Hős/vár és explicit battle nézet is megadható.
Alapkorlátok: 144×144 térkép, 128 hős, 128 vár, 32 csataegység, 8192 akciójelölt. Túllépés explicit hiba, nem csendes levágás.
Az összes egész toborzási/átadási/kereskedelmi mennyiség enumerálása nagy seregeknél sok jelöltet eredményezhet.
Teljes séma és konfigurációs maximumok: [Gym-szerződés](PYTHON_ENV_GYM.md).

## 5. Támogatási mátrix

| Terület | Ellenőrzött jelenlegi képesség | Megmaradó határ |
|---|---|---|
| Betöltés/reset | Standard mentés, seedelt MP2/MX2/FH2M új játék; csatából/választásból reset | Kampányok, szerkesztő és hálózati játék nem célprofil |
| Állapot | Minden oldal, AI-hősök/várak/seregek/tárgyak és teljes térkép | Láthatóságra szűrt `observe` nincs |
| Vezérlés | Oldalanként Python/beépített AI, több Python-agent, AI-only, csata/választás útválasztás | Hozzárendelés resetkor; Gym egy külső oldalas; külön multi-agent wrapper nincs |
| Adventure | Szárazföldi/vízi mozgás, beszállás/partraszállás, saját várba belépés, 83 deklarált objektumtípus, AI-körök | További objektumok és speciális tengeri interakciók |
| Gazdaság | Natív építés, toborzás, hős- és hajóvásárlás, ajánlatfrissítés, piaci csere | További speciális gazdasági műveletek |
| Sereg/hős/tárgy | Natív találkozás, seregátadás/csere, upgrade/dismiss, könyvvásárlás, tárgy/tekercs/set | Jogosultság és találkozási távolság a natív szabályok szerint |
| Választás | Láda, szintlépés, semleges csatlakozás/üldözés, megerősítés és toborzási darabszám | Arena elsődleges képesség és térképi teleportcél is; szöveges Sphinx még nincs |
| Adventure varázslat | 11 varázslat: Identify/Visions, hajóidézés, Dimension Door, Town Gate/Portal, őrzőlények | Hat View World információs nézet |
| Csata | Térképi támadás/védekezés, egységkörök, mozgás, támadás, lövés, menekülés, megadás, natív eredmény | 48 tanítható harci varázslat, natív célzással; konfigurálható battle-only reset külön feladat |
| Render | Adventure, aktív csata, saját/AI-hős és vár, RGB; UI nélkül | Statikus képkérés, nem animációs/videóstream |
| Gym | Több hős, választás/csata ugyanabban az epizódban, maszk, fix terek, terminális reward | Bounded profil, numerikus feature-ök; nem optimalizált tömeges RL backend |
| Önálló csata | A vezérlő és render alapjai adottak | Konfigurálható battle-only reset nincs; terep/ostrom/hajós kombinációk külön bővítés |
| Platform | Opcionális desktop CMake-út; Windows futás és normál Windows UI ellenőrizve | Linux/macOS és mobil SDK-build most nem futott |

## 6. Elfogadási eredmény és mért sebesség

A géppel olvasható, rögzített eredmény: [Windows elfogadási jelentés](python_env/acceptance.windows.2026-10-31.json).
A mért natív build alapcommitja `3d53ee697404db3c330f95a5bb9706e56702e5d8`; a 14. lépés nem változtatott a motoron.
Windows 11, 16 logikai CPU, Intel64 Family 6 Model 186, Python 3.14.7, GCC 16.2 / RelWithDebInfo.
Az eredmények ennek a gépnek és a 36×36 The Other Side referenciaállapotnak a mérései.

| Művelet | Medián | Minták |
|---|---:|---:|
| Session reset mentésből, friss folyamattal | 65,5 ms | 10 |
| Session reset új pályából | 49,8 ms | 10 |
| Teljes strukturált állapot, mentéspayload nélkül | 19,5 ms | 30 |
| Natív körvége AI-val, csak parancs/válasz | 1,71 ms | 10 |
| Teljes Gym reset, állapottal és maszkkal | 109,4 ms | 10 |
| Teljes Gym körvége AI-val, megfigyeléssel/maszkkal/info-val | 42,9 ms | 10 |
| Adventure render, 640×480, bemelegített | 2,51 ms | 10 |
| Hősrender, 640×480, bemelegített | 2,64 ms | 10 |
| Várrender, 640×480, bemelegített | 2,55 ms | 10 |
| Csatarender, 640×480, bemelegített | 2,90 ms | 10 |

Az átlagos teljes Gym-lépés alapján **23,4 lépés/s** ezen az állapoton, render nélkül.
Ez nem általános játékmeneti vagy RL-tanítási sebesség: a különböző csaták, térképméretek, jelöltszámok és modellek eltérően terhelnek.
A natív 1,71 ms és a teljes Gym 42,9 ms közötti különbség az állapotexportot, JSON/Python feldolgozást,
jelöltellenőrzést, numerikus kódolást és másolatokat is tartalmazza. Ezek arányát ez a mérés nem profilozta külön.
Gyorsítás előtt ezeket érdemes részletesen profilozni; a motor játékszabályainak átírása ebből nem következik.

A mérés `perf_counter` faliórát használ a teljes Python-hívás körül; az első, bemelegítő hívás nem része a mediánnak.
Az első renderkérések külön rögzítve szerepelnek a JSON-ban (4,1–10,1 ms); a csatakép előtt a támadás már inicializált grafikus adatokat.
Két párhuzamos, független motorfolyamat összesen 20 reset+AI-kör+teljes állapotlekérést végzett 1,06 másodperc alatt;
mindkét seed ismételhető állapotokat adott. Ez működési mérés, nem általános párhuzamos skálázódási ígéret.

Elvégzett ellenőrzések:

- **146 sikeres teszt**, nulla skip vagy hiba, 78,7 másodperc alatt; hivatalos Gymnasium checkerrel.
- Összefüggő API-forgatókönyv: építés → toborzás → sereg osztása/egyesítése → csata → szintlépési válasz → adventure → AI-kör.
  A hős 3. szintre jutott; mind a négy nézet állapotot és döntést megőrző képkérése is ellenőrzött.
- **13 hosszabb Gym-epizód, 2707 lépés, nulla motorhiba**: tíz maszkoltan véletlen epizód 250 lépés után truncation;
  három csatával kezdő, majd köröket záró policy 69 lépés és 64 játéknap után valódi vereség, `-1` jutalom.
  A véletlen epizódok csak a 3–8. napig jutottak: a sok inventory/gazdasági akció nem jelent ugyanennyi napot vagy stratégiai előrehaladást.
- A normál, Python nélküli Windows-buildben: főmenü, standard mentésbetöltés, adventure/hős/vár/építési felület,
  interaktív csata, egységmozgatás, AI-harci folytatás, csataeredmény/nekromancia, visszatérés és napváltás; végül normál kilépés 0 kóddal.
- Mindkét Windows-build inkrementális ellenőrzése sikeres; a headless policy teszt változatlanul tiltja a display/input használatát.
- Két eredeti mentés, két térkép és két AGG ujjlenyomata változatlan. Az ablakos próba kizárólag külön tesztprofilban futott.
- A base csomag szerkeszthető telepítése külön venv-ben sikeres.

Nem történt teljes kampánybejárás, minden billentyűparancs vagy más platform SDK-jának ellenőrzése.
A 14. lépés jelentése az akkori egykülsőoldalas profilt rögzíti; az ezt követő 4/A megvalósítás teljesíti a két vezérlési feltételt.

## 7. Újrafuttatás és hibakeresés

Az alábbi script helyi profilokat és JSON-jelentést ír a figyelmen kívül hagyott `build/python-env-acceptance` mappába:

```powershell
uv run --project python --extra gym python python/examples/acceptance.py
# Egyes részek külön:
uv run --project python --extra gym python python/examples/acceptance.py --section scenario
uv run --project python --extra gym python python/examples/acceptance.py --section stress --episodes 10 --max-steps 250
uv run --project python --extra gym python python/examples/acceptance.py --section benchmark --samples 10
```

Más buildhez, forráscommithoz vagy bemeneti ujjlenyomathoz új `--output` fájlt kell választani; a script nem keveri össze eltérő futási alapok méréseit.
Sikertelen szakasznál a jelentés explicit hibát tárol és a program hibakóddal lép ki, nem marad helyette korábbi sikerjelzés.
A benchmark alatt ne fusson a stresszteszt vagy más nagy terhelés. A grafikus smoke próba külön, a normál UI-ban történik,
nem a benchmark script végzi. Helyi API/Gym-bemutatók: `battle.py`, `views.py`, `reset.py`, `train_loop.py`.

Tipikus hibák:

- `unknown_method` / hiányzó Gym capability: ellenőrizd, hogy valóban az új, Python-támogatású executable-t adtad-e meg.
- `assets_unavailable`: eredeti AGG, illeszkedő H2D, `FHEROES2_DATA` és a runtime könyvtárak ellenőrzése.
- `wrong_player` / `unsupported_state`: az aktuális token, a vezérlő-hozzárendelés és a művelet tulajdonosa egyezzen.
- `gym_profile_limit`: emeld a megfelelő fix korlátot, vagy válassz a profilba férő állapotot; az adapter nem vág le opciókat.
- `unsupported_action` / `unsupported_interaction`: a motorprofil még nem kezeli az adott helyzetet. Ne alakítsd jutalommá vagy vereséggé.
- `stale_decision` / `wrong_session`: session API-ban friss tokent használj, reset után a régi token érvénytelen.
- Timeout/crash: kivétel után reset; a motorfolyamat kilépése nem játékmeneti eredmény.

A 7. kiegészítés hajózása/hajóvásárlása/saját várba belépése elkészült: [navigációs példa és API](PYTHON_ENV_NAVIGATION.md).
A [9–10. bővítés](PYTHON_ENV_EXPANSION.md) 83 objektumot, 11 adventure és 48 harci varázslatot kezel.
További munka: a dokumentált speciális objektumok és View World nézetek; konfigurálható battle-only indítás. Nagy léptékű RL-optimalizálás és láthatóságra szűrt observation ezek mellett külön bővítés.
