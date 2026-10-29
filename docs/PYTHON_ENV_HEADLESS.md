# Headless alap és adventure képkérés

Az 5. lépésben a jelenleg támogatott mentésbetöltés, állapotlekérdezés, döntésre várakozás és adventure képkérés
ablak, kézi input és hang nélkül működik. A világot a játék saját C++ kódja tölti be, a képet a saját rajzolója készíti.
A 6. lépéstől a [korlátozott adventure profil](PYTHON_ENV_ADVENTURE.md) mozgást és AI-val együtt körváltást is támogat;
a `headless_gameplay` erre a profilra true. Külső csatavezérlés még nincs.

## Megvalósítás

- `System::ScopedHeadlessMode`: a Python bootstrap indításkor explicit headless futtatási profilt választ.
  Alapértelmezésben a normál interaktív profil érvényes. A policy a fő motorszálhoz tartozik, nem párhuzamos
  világok szálankénti kapcsolója; minden Python-session továbbra is külön folyamatot kap.
- `CoreInitializer(components)`: a videó, hang és kontroller komponensei kiválaszthatók. Üres halmaznál SDL/event
  inicializálás sem történik. A paraméter nélküli konstruktor az eredeti Audio+Video alapértéket használja;
  a meglévő Vita/Switch kontrollerkiegészítés megmaradt.
- A Display elérése/allokálása, a LocalEvent interaktív hurka, a térképi input és a közös szöveges dialógus belépése
  headless módban azonosítható `unsupported_interaction` hibát ad. Nem nyit rejtett ablakot és nem választ a játékos helyett.
- Az animációs késleltetés-ellenőrzések a headless ágon nem várnak. Az inputot használó régi animációs hurkokat ez
  önmagában nem teszi támogatott játékműveletté: a további lépésekben a logikai műveletet a megfelelő határon kell bekötni.
  A védőkorlát nem állapot-visszagörgetés, ezért egy későbbi művelet támogatását a módosítás előtt kell ellenőrizni.
- `GameArea` önálló, interaktív interfész nélküli viewportként is létrehozható. A normál konstruktor ugyanazt az interfészt
  kapja, mint korábban. A standalone változat nem hoz létre radart, dialóguskeretet vagy Display-t.
- Az adapter a viewportot egy külön `Image` pufferre rajzolja, majd az eredeti játékszínpalettával RGB bájtokra alakítja.
  Nem indítja el az interaktív singleton resetjét, nem frissít ködöt, útvonalat vagy játékanimációs számlálót.

## Python-felület

```python
frame = game.render(view="adventure", width=640, height=480, center=(32, 24))
assert frame.shape == (480, 640, 3)
pixels = frame.pixels          # RGB uint8 bytes, HWC, soronkénti padding nélkül
frame.save_ppm("build/frame.ppm")
# Ha a hívó telepített NumPy-t: array = frame.to_numpy()
print(game.runtime_info())
```

A szélesség és magasság 32–1024 pixel. A középpont nulla alapú térképmező; alapértelmezésben a pálya közepe.
A nézet mindent lát: terep, objektumok és hősök, köd/láthatósági szűrés és emberi UI-panelek nélkül. Ez nem fair játékosi
megfigyelés. A 11. lépéstől a [vár-, hős- és csatanézet is elérhető](PYTHON_ENV_VIEWS.md), memóriaképként, döntés- és világváltozás nélkül.

A szükséges grafikus adatok: az eredeti AGG-k és a megfelelő `files/data/resurrection.h2d`.
Az állapot betöltése nem kéri a H2D-t; az első render igen. A hiányzó csomag `assets_unavailable` hibát ad a rajzolás előtt.
Pythonban nincs mentésparser vagy második játékszabály-implementáció, és nincs kötelező NumPy/Pillow-függőség.

Az RGB a kliens saját ideiglenes könyvtárába kerül bináris fájlként. A kliens ellenőrzi a metaadatokat/méretet,
legfeljebb a várt képméretnyi adatot olvas, majd takarít sikeres és hibás kérés után is. A fájl a visszaadott képtől függetlenül
törölhető: az `RGBFrame` saját immutable bytes tartalmat tárol. A motor meglévő fájlt nem ír felül.

## Méréssel ellenőrzött backendválasztás

2026-10-29, helyi Windows-build:

| Próba | Eredmény |
|---|---|
| SDL dummy + software, explicit Video-only core | 640×480 képallokáció, Video=1, Audio=0 |
| SDL dummy + software, normál default core | 640×480 képallokáció, Video=1, Audio=1 |
| Env memória-viewport, érvénytelen video/audio driverekkel | Betöltés, döntésvárakozás és RGB-kérés sikeres; Video=Audio=Controller=0 |
| C++ headless policy | Normál alapmód és scope-visszaállítás helyes; a tiltott Display/core/input belépés SDL-indítás előtt hibát ad |
| Python tesztcsomag | 35 sikeres teszt, két rögzített mentéssel |

A dummy út használható, de a már meglévő memóriarajzolóhoz nincs szükség a videó inicializálására. Ezért az env jelenleg
a `memory_image` utat használja. A normál játék megtartja a meglévő SDL render backendjét.

A render tesztjei ismételt képeknél bájtra azonos eredményt, változatlan teljes mentéspayloadot/döntési tokent,
üres profilt, két izolált folyamatot, kamerahatárokat, ideiglenes fájlok takarítását, írási hibából helyreállást és hiányzó H2D
esetén a motor életben maradását ellenőrzik. Ez nem helyettesíti a későbbi akciósorok RNG-egyezőségének vizsgálatát.

## Futtatás

```powershell
uv run --project python python python/examples/render.py build/python-env-baseline/fixtures/other-side-day1.sav
uv run --project python python -m unittest discover -s python/tests -v
.tools/msys64/ucrt64/bin/cmake.exe --build --preset windows-local --target fheroes2_headless_checks
build/windows-local/fheroes2_headless_checks.exe
$env:SDL_VIDEODRIVER = "dummy"
$env:SDL_AUDIODRIVER = "dummy"
$env:SDL_RENDER_DRIVER = "software"
build/windows-local/fheroes2_headless_checks.exe --dummy-probe
build/windows-local/fheroes2_headless_checks.exe --default-probe
```

A teszttarget külön kérhető, nem része a szokásos játékbuildnek, és kikapcsolt `ENABLE_PYTHON_ENV` mellett nem létezik.
A Python nélküli Windows-build is sikeresen lefordult. Az Android/iOS/Linux/macOS és konzolos SDK-buildet
helyben nem futtattuk; a közös C++ csatlakozási pontok nem kérnek Python-, JSON- vagy venv-függőséget.
