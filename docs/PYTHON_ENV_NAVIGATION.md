# Hajózás, hajóvásárlás és saját várba belépés

A 7. kiegészítés ugyanazt a natív mozgást és várműveleteket használja, mint a játék.
Nincs külön Python-hajózási szabályrendszer. A támogatás az opcionális desktop env része;
a normál játék továbbra sem függ Pythontól vagy venv-től.

## Futtatható példa

Az eredeti adatokat és a baseline mentést igénylő, külön natív kikötői tesztmentések előkészítése:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File script/windows/python-env-artifact-fixture.ps1
uv run --project python python python/examples/navigation.py
```

A példa hajót vesz, ki- és belép a saját várba, beszáll, másnap hajózik, majd partra száll.
Mindkét oldal Python-vezérelt; a másik oldal csak lezárja a körét, hogy a bemutató ismételhető legyen.
A fixture builder külön mentéseket ír a `build/python-env-baseline/fixtures` alá; az eredeti mentést/pályafájlt nem írja felül.
A példa koordinátái erre a kikötői tesztforgatókönyvre vonatkoznak; az API normál standard pályán is használható.

## Hajóvásárlás

```python
options = game.get_castle_options(castle_id)
boat = options["boat"]
if boat["can_buy"]:
    result = game.buy_boat(castle_id, token=decision["token"])
    decision = result["decision"]
```

Nyers parancs: `castle.buy_boat`, `params={"castle_id":...}`. Egy parancs egy hajót vesz.
A vár az aktuális Python-oldalé kell legyen. A motor `AllowBuyBoat(true)` és `BuyBoat()` függvénye dönt:
hajógyár, megfelelő készlet, alkalmas víz és szabad kikötő szükséges; közeli üres hajó kizárja az új vásárlást.
A natív ár pontosan egyszer levonódik, a motor választja a hajó mezőjét és tulajdonosát.
Esemény: `boat_purchased`, `castle_id`, `player_id`, `tile_index`, `cost`.
Szükség esetén előbb a meglévő `build_castle` hívással építhető hajógyár.

A `get_castle_options` minden oldalra olvasható `boat` blokkja:

| Mező | Jelentés |
|---|---|
| `has_shipyard` | A hajógyár megépült |
| `has_sea_access` | Natív tengeri kijárat |
| `boat_nearby` | Üres hajó van a kikötő közelében |
| `placement_index` | Lehetséges natív lerakási mező, vagy `-1` |
| `can_buy` | Az összes natív vásárlási feltétel teljesül |
| `cost` | Natív erőforrásár |

A lekérdezés és `check_actions` nem vásárol, nem frissít ajánlatot és nem fogyaszt RNG-t.
Hibás paraméter, idegen vár, foglalt kikötő vagy elégtelen készlet változatlan világ mellett elutasított.

## Beszállás, vízi mozgás és partraszállás

Mindháromhoz a meglévő API használható:

```python
result = game.move_hero(hero_id, x, y, token=decision["token"])
decision = result["decision"]
```

- Szárazföldi hős hajómezőre mozgatása beszállás. A hajó objektuma eltűnik, a hős hajózó lesz.
- Hajózó hős vízi célra mozgatása a natív útkeresővel történik, a motor vízi mozgáspontjaival.
- Alkalmas parti szárazföldi cél partraszállást indít; az utolsó vízi mezőn ott marad a hőshöz tartozó üres hajó.
- A beszállás és partraszállás a natív szabály szerint elfogyasztja a maradék mozgást. A folytatáshoz új kör kell.

A teljes kért útvonalnak továbbra is ki kell férnie az aktuális mozgásból.
Egy parancsban a közegváltás csak az út végén lehet: nem szállunk be, majd hajózunk tovább ugyanabban a parancsban.
Az üres vízre nem lehet besétálni, a hajó nem megy át szárazföldi köztes mezőkön.
A motor dönt a járhatóságról, foglalt partról és átlós parti útvonalakról.
Az eddigi objektum-/őrzésellenőrzések megmaradnak; nem támogatott köztes objektumot nem járunk át automatikusan.

Új megfigyelések: `hero["is_shipmaster"]`; üres hajó tulajdonosa a `map.tiles[*].boat_owner` mezőben.
A hajó helyét a mező natív `object_type` értéke jelzi. Beszálláskor az üres hajó tulajdonosa törlődik.
A `hero_moved` mellett `hero_boarded` és `hero_disembarked` esemény érkezik a hős és a tényleges ki-/végpont adataival.
Kép hajózó hősről és a térképről is kérhető, az állapot megváltoztatása nélkül.

Az ellenséges hajón álló hős megtámadása a meglévő élő csatát indítja. A kontrollerek itt is oldalanként működnek;
a túlélő hajózó hőssel térünk vissza a kalandtérképre. Egy ilyen két Python-oldalas csata szerepel az ellenőrzésekben.
Ez nem jelenti az összes hajós objektum, hajótörés, örvény vagy vízi varázslat teljes támogatását.

## Saját vár meglátogatása

A vár bejáratának koordinátájára küldött `move_hero` belépteti a saját hőst, ha a látogatói hely szabad.
A natív `ActionToCastle` és máguscéh-tanítás lefut; headless módban az interaktív várablak kimarad.
A nézet külön `render(view="castle", castle_id=...)` hívással kérhető.

A hős `castle_id` és a vár `visiting_hero_id` mezője frissül; a meglévő látogató/helyőrség műveletek
ezután ténylegesen használhatók. Esemény: `castle_visited`, `hero_id`, `castle_id`.
Foglaltság esetén nem írjuk felül a bent álló hőst. Saját hősök találkozásához továbbra is a `meet_heroes` API tartozik.
A szövetséges, más színű vár látogatásának natív tiltása megmarad.
Ha a hős már a várban van, a célmező ugyanarra mozgatása továbbra is hibás; lekérdezéshez nem kell újra belépni.

## Gym és ellenőrzés

A `Fheroes2-v0` jelöltjei között megjelenik a szabályos `castle.buy_boat`.
A meglévő szomszédos `hero.move` jelöltek a hajóra lépést, vízi lépést, partraszállást és várba belépést is lefedik.
A maszk mindegyiket a natív `check_actions` alapján engedi vagy tiltja.
A hajóvásárlás a korábbi akciókódok megtartásával a kategórialista végére került.
A hős numerikus sora `is_shipmaster` mezővel bővült: a 7. kiegészítés bevezetésekor a `heroes` alakja **128×22** volt.
Azóta a [9–10. bővítés](PYTHON_ENV_EXPANSION.md) max. mozgás/morál/szerencse mezőivel az aktuális alak **128×25**.
A két utolsó oszlop továbbra is x/y. A korábbi 128×21 megfigyelésre épült modell bemenetét ehhez igazítani kell.

A `python/tests/test_navigation.py` ellenőrzi a pontos költséget, kikötőfoglaltságot, hibák atomi elutasítását,
beszállást/vízi lépést/partraszállást/újrabeszállást, körváltást, seedelt visszajátszást,
olvasási/renderelési mellékhatásmentességet, saját várba visszatérést és valódi helyőrség-átadást,
a Gym jelöltjeit/maszkját/megfigyelését, valamint hajó–hajó csatát.
A frissen vett hajó útvonala a parton már várakozó hősnél is azonnal használható, korábbi sikertelen útlekérdezés után is.

2026-10-31, Windows: **165/165** sikeres teljes Python/Gym regressziós futás, majd **9/9** célzott navigációs teszt
(az utólag hozzáadott, azonnali beszállást ellenőrző esettel együtt). Az új esetek Debug buildben,
bekapcsolt C++ ellenőrzésekkel is sikeresek. Az opcionális és a normál `ENABLE_PYTHON_ENV=OFF` build lefordult.
A `navigation.py` teljes példája video/audio inicializálás nélkül lefutott. Más platformok SDK-buildje még nem ellenőrzött.

Hátravan: további objektumok/interakciók/varázslatok (9–10. bővítés), konfigurálható önálló csataindítás
és szélesebb terep-/ostrom-/hajós lefedettség, Linux/macOS/mobil SDK-buildek, nagy léptékű RL-profilozás.
