# Négy headless rendernézet Pythonból

A 11. lépéstől kalandtérkép, aktív csata, aktív hős és vár képe kérhető a natív motorból.
Mindegyik memóriabeli RGB-kép: nincs SDL-ablak, grafikus munkamenet, kézi input, hang vagy animációs várakozás.
A hős- és várnézet a saját és az AI-oldal entitásaira is elérhető, a jelenlegi API mindent látó szemléletével.

## API

```python
adventure = game.render(view="adventure", center=(32, 24))
hero = game.render(view="hero", hero_id=52)
castle = game.render(view="castle", castle_id=896)
battle = game.render(view="battle")  # Függő külső csatadöntésnél.
rgb = battle.to_numpy()              # Opcionális NumPy, uint8[H,W,3].
```

Mindegyik hívás visszatérési értéke a meglévő, változtathatatlan `RGBFrame`:
`width`, `height`, `pixels`, `shape`, `center`, `state_version`; elérhető a `save_ppm()` és az opcionális `to_numpy()` is.
Alapméret 640×480, a kért szélesség/magasság egyenként 32..1024 lehet.

| Nézet | Kiválasztás és tartalom |
|---|---|
| `adventure` | Opcionális `center=(x,y)`, alapból térképközép. Natív terep, objektumok és hősök; a képméret a viewport mérete. |
| `hero` | Kötelező `hero_id`, aktív hős. Natív háttér, portré, címer, elsődleges/másodlagos képességek, morál, szerencse, mana, tapasztalat, alakzat, sereg és tárgyak. |
| `castle` | Kötelező `castle_id` a `get_state` alapján. Natív faji várkép, tényleges épületek, név, kapitány/címer, helyőrség, látogató hős/sereg és erőforrások. |
| `battle` | A jelenleg várakozó csata. Natív terep, akadályok, ostromépítmények/falak, hősök, egységek, létszámok és aktívegység-jelölés. |

A három új nézet natív 640×480 képet rajzol, majd a motor saját nearest-neighbor `Resize` műveletével méretez.
Eltérő oldalaránynál a kép a kért méretre nyúlik; nincs rejtett képkivágás vagy más kamerajelentés.
A `center` visszatérési mező ezeknél az entitás/csata kalandtérképi helye, nem a GUI-n belüli pixelkoordináta.
A `center_x/center_y` csak adventure kérésben, `hero_id` csak hero, `castle_id` csak castle kérésben fogadható el.

A hős/vár adatképek, nem megnyitott interaktív dialógusok. Az eredeti assetek és rajzolókomponensek futnak;
a képről nem indítható kattintás vagy művelet. A csatakép a natív Interface kirajzolási ágát használja, az aréna interaktív UI-jának bekapcsolása nélkül.
Animációt nem léptetünk: várnál rögzített nulladik animációs index, csatánál az egység aktuális natív sprite-állapota és statikus hőskép jelenik meg.

Csata közben a hős/vár képe a tartós kalandtérképi adatokat mutatja. A tényleges harctéri sérülésekhez/létszámokhoz a `battle`
nézet és `battle.units` tartozik; a motor a csata végén szinkronizálja a seregeket a kalandtérképpel.

## Futtatható és látható példa

A bekapcsolt fejlesztői motor és a korábbi natív tesztmentések után:

```powershell
uv run --project python python python/examples/views.py
```

Az eredmény `build/python-env-views/adventure.png`, `hero.png`, `castle.png`, `battle.png`.
A PNG-írás a példa standard Python-könyvtárait használja, nem új kötelező csomagfüggőség.
A script előbb mentésből állapotot kér és kirajzolja a hőst/várat, majd igazi csatát indít és annak képét is menti.
Minden képkérés előtt/után ellenőrzi a világ és a döntés változatlanságát.
Másik kimeneti könyvtár: `--output-dir PATH`. A képek helyi, ignorált eredmények; a játékassetek nem kerülnek a repóba.

## Változatlan szimuláció és biztonságos képkérés

A protokoll ugyanaz a `render` metódus, a fenti kiválasztóparaméterekkel. A `render_views` képességlista
`adventure`, `battle`, `hero`, `castle`. A kliens saját rövid életű könyvtárában kezeli a nyers RGB-fájlt és takarítja azt;
alacsony szinten továbbra is kötelező a `view`, `width`, `height`, `output_path`. Létező kimeneti fájlt nem írunk felül.

Nincs új játéklogika. A várrajzolás ugyanazon épületprioritásokkal és közös, explicit `Image` célú függvényekkel fut,
mint a normál UI. A néhány korábban Display-hez kötött átmeneti segéd (kijelölő sprite, indikátor és képkockakeret)
szűk életű `ScopedDrawingTarget` hatókörben kap memóriaképet. Ezen kívül a normál Display útvonal marad.
A headless `Display::instance()` védőkorlát nem változott és nem kapcsolható ki ettől.

A csata pixelgeometriája az aréna létrehozásakor inicializálódik, képkéréstől függetlenül.
Képkérés nem mozgat egységet, nem vált kört, nem rendez sereget/tárgyat és nem fogyaszt döntési tokent.
A főszál játékmeneti RNG-állapotát a képkérés kivétel esetén is megőrzi; a csata kirajzolása nem futtat harci parancsot.
A csatarender callback csak az élő várakozás alatt létezik; lezárás, megszakítás és betöltés eltávolítja.

Hibák: betöltés nélkül `no_game_loaded`; ismeretlen nézet `unsupported_view`; hibás/hiányzó/oda nem illő ID vagy paraméter
`invalid_request`; függő csata nélkül `no_active_battle`; hiányzó grafikus adat `assets_unavailable`; fájlhiba `render_failed`.
Mindez nem jelent győzelmet/vereséget/időlimitet és nem mozdítja el a függő döntést.
Az eredeti AGG és a hozzá illő H2D grafikus adat továbbra is szükséges.

## Ellenőrzés és platformhatár

Nyolc új valódi motoros teszt: mindkét baseline összes aktív saját/AI-hőse és vára, ismételt és különböző méretű képek,
natív építés/fejlesztés képi változása, mezőcsata és ostrom, élő döntés/mentéspayload változatlansága,
hibakezelés és egy teljes csata azonos végállapota képkérésekkel és azok nélkül.
A példaképeket vizuálisan is ellenőriztük. A natív headless policy teszt továbbra is tiltja a display/input inicializálást.
A Python-rész opcionális PC-s adapter; a közös rajzolósegédek nem függnek Pythontól, NumPytól vagy a venv-től.

A 2026-10-29-i végső Windows-ellenőrzésen mind a 119 Python-teszt sikeres volt, köztük mind a nyolc új nézetteszt.
Az engedélyezett és az alapértelmezett, Python-támogatás nélküli Windows-build is lefordult;
a `fheroes2_headless_checks` natív ellenőrzés és a négy PNG-t készítő példa is sikeres.
Más platformok SDK-buildje és az ablakos játék kézi végigkattintása ebben a lépésben nem történt meg.
