# 12. lépés: reset, seed és ismételhető epizódok

Frissítve: 2026-10-31. A normál és mobil játékbuild továbbra sem igényel Pythont.

```python
with HeroesSession("fheroes2.exe", timeout=60) as game:
    episode = game.reset(save="checkpoint.sav", seed=123)
    decision = episode["decision"]
    result = game.end_turn(token=decision["token"])
    episode = game.reset(seed=123)  # ugyanaz a forrás, friss motorfolyamat

    episode = game.reset(map_path="maps/THEOTHER.MP2", seed=123,
                         player_id=1, difficulty=1)
```

Az első `reset` pontosan egy `save` vagy `map_path` forrást kér. A további, forrás nélküli hívás az utolsó sikeres
reset forrását, résztvevőjét és nehézségét használja; a megadott résztvevő/nehézség felülírja az eltárolt beállítást.
Az alacsony szintű `load_save`/`new_game` hívás nem változtatja meg ezt az eltárolt resetkonfigurációt.
A válasz `seed`, `source`, `loaded` és `decision` mezőt tartalmaz. A `decision` már aktív külső várakozás, nem kell ismét `start_session`.
Ez az általános session API; a Gymnasium kétértékű reset-válasza továbbra is a külön wrapper feladata.

## Seed és állapot

- A seed egész szám, `0..2**32-1`; a bool, negatív szám és túlcsordulás hiba. A `0` érvényes seed.
- `seed=None` új, Python `secrets` által készített seedet választ. A tényleges érték a válaszban visszakapott `seed`;
  ezzel az értékkel az epizód megismételhető. Forrás nélküli reset sem használja újra hallgatólagosan az előző seedet.
- Új játék: meglévő standard MP2/MX2/FH2M pályából a natív motor készít új induló állapotot. Ez nem új véletlen pályagenerátor.
  A főszál PCG32 generátora még a résztvevők, a véletlen fajok és a világ inicializálása előtt kapja meg a seedet.
  A kirakós feltárási sorrendje statikus világkonstrukciókor már kisorsolódott, ezért ezt a meglévő `Puzzle` konstruktorral,
  a seed beállítása után újra létrehozzuk minden birodalomnak, a semlegest is beleértve. Ez kizárólag az opcionális adapter útvonala.
- A világ seedjét továbbra is a natív `World::Defaults` sorsolja ki. Nem kell azonosnak lennie a bemeneti seed számszerű értékével.
  A hét, hónap, hősszintlépés és csata saját, ebből származtatott generátorait a közös motor számolja, a meglévő szabályokkal.
- Mentés: a seed a betöltés **után** állítja be a főszál folytatási RNG-jét. A mentésben lévő világseedet, seregeket,
  puzzle-állapotot és más adatokat nem írja át. A teljes betöltött mentéspayload különböző seedeknél is azonos marad.
  A mentés formátuma nem tárolja a főszál teljes PCG-folytatását: ez dokumentált, seedelt folytatás, nem az eredeti UI-játék
  el nem mentett RNG-állapotának visszaállítása. A meglévő, seed nélküli `load_save(path)` viselkedése megmarad.
- Ugyanaz a mentés és eltérő folytatási seed nem feltétlenül ad eltérő csatát: a csataseed a mentett világseedből,
  a helyből és a seregekből származik. A folytatási seed a főgenerátort használó további döntésekre hat.

Az ismételhetőség ugyanarra a motorverzióra/buildre, azonos assetekre, pályára/mentésre, konfigurációra és akciósorra vonatkozik.
Verziók és különböző architektúrák közötti bitazonosságot ez a lépés nem igazol. A session/epizód/döntés azonosítói
kapcsolati metaadatok: új folyamatban szándékosan új sessionazonosító jön létre, ez nem szimulációs eltérés.

## Natív indulás és jelenlegi profil

A `new_game` protokoll pontos paraméterei `path`, `seed`, `player_id`, `difficulty`. A `load_save` opcionális `seed` mezőt kapott.
A `seeded_new_game` és `seeded_save_continuation` capability igaz. Alacsony szinten ezek után külön `start_session` kell;
a Python `reset` ezeket és a folyamatkezelést összefogja.

A nehézség `0..4` (easy, normal, hard, expert, impossible); új pályán alapértéke `1`. Mentésnél a mentett nehézség az érvényes.
Az új játék ugyanazt a `FileInfo`, résztvevőbeállítást, fajválasztást, natív pályabetöltőt, `NewDay`, fogfelderítést,
`ActionBeforeTurn` és napi erőforrás-/eseményfrissítést használja. Az első külső döntés az első nap előkészítése után érkezik;
az előkészítés nem fut le újra az első akciónál. Az induló események hatásai az állapotban szerepelnek.

Továbbra is egyetlen, emberi szabályprofillal rendelkező külső oldal támogatott. Mentésnél a reset ezt automatikusan
megkeresi, ha nincs `player_id`; új pályán alapértéke kék (`1`). A pályának ezt engednie kell, más kötelező emberi oldal
nem lehet. A többi résztvevő beépített AI; a fajok és szövetségek a pályából származnak.
A 4/A többoldalas vezérlés követelménye megmarad. Egy pálya betölthetősége nem jelent teljes objektum-/varázslat-lefedettséget.
Az önálló battle-only konfigurálás továbbra is külön feladat.

## Folyamatéletciklus és hibák

A reset a korábbi motorfolyamatot leállítja és megvárja, a pipe-okat és a transport szálat lezárja, majd ugyanazzal az
executable/cwd/env/timeout konfigurációval új folyamatot indít. Az éppen futó epizód eldobódik; nem készül automatikus mentés.
Ez adventure, nyitott választás, élő csata és terminális állapot esetén is érvényes. Összeomlás, timeout vagy explicit `close`
után ugyanez az objektum `reset` hívással újraindítható. A régi token az új folyamatban `wrong_session` hibát ad.

A hibás Python-argumentumok ellenőrzése a régi folyamat leállítása előtt történik. Egy valóban megkísérelt, de hibás
betöltés/reset után az új folyamat is lezárul, a session `closed`; az utolsó sikeres resetkonfiguráció megmarad újrapróbáláshoz.
Továbbra is külön kivétel a motor elutasítása (`EngineError`), protokollhiba (`ProtocolError`), folyamatkilépés
(`EngineProcessError`) és időtúllépés (`EngineTimeoutError`). Ezek nem Gym-győzelmek vagy időlimitek.
Két session külön motorban fut, az egyik resetje nem változtatja a másik állapotát vagy tokenjét.

## Futtatható példa és telepítés

```powershell
uv run --project python python python/examples/reset.py
uv run --project python python python/examples/reset.py --map maps/THEOTHER.MP2 --seed 123
```

A példa két friss folyamatban három AI-körön át ugyanazt az akciósort futtatja, és összehasonlítja a teljes állapotokat,
a natív mentéspayloadot is beleértve. Más pályán választás/csata döntésénél megáll; a példa nem választ helyettünk.
Telepítés saját venv-be: `python -m pip install -e ./python`; a base csomag csak a standard könyvtárat használja.
Az opcionális Gym-preview `reset(seed=...)` most már a főgenerátor folytatását is seedeli; az effektív seed `info["seed"]`.
Ez nem bővíti a preview kilenc akcióját vagy jutalmát, a teljes Gym-szerződés továbbra is a 13. lépés.

## Ellenőrzés

A motoros resettesztek teljes mentéspayloadot hasonlítanak: ismételt reset/AI-körök, új pálya azonos/eltérő seedje,
képkéréssel és anélkül egyező átmenetek, MP2/MX2/FH2M indulás, választás/csata/terminális reset,
régi token elutasítása, process crash, timeout, close, hibás betöltés utáni helyreállás és két session függetlensége.
A 2026-10-31-i Windows-ellenőrzésen mind a **131 Python-teszt sikeres**, köztük 12 új resetteszt és a Gymnasium
determináltságot is ellenőrző hivatalos tesztje. Az engedélyezett és az alapértelmezett, Python nélküli Windows-build is
lefordult; a natív headless policy ellenőrzés sikeres. A mentéses és az új pályás példa kétszer három AI-kört futtatott
egyező teljes állapotokkal. Az editable telepítés külön, csak base csomagot tartalmazó venv-ben, offline cache-ből sikeres.
Más platformok SDK-buildjét és a normál ablakos játék kézi végigkattintását ez a lépés nem ellenőrizte.
