# Várlekérdezés, építés és pontos toborzás

A 7. lépés első része: a meglévő `adventure_basic` profil mellett két új külső művelet,
`castle.build` és `castle.recruit`, valamint egy csak olvasó `get_castle_options` lekérdezés működik.
A várablakot nem kell megnyitni. A szabályok, árak, készlet és seregfeltöltés továbbra is a natív C++ motorban maradnak.

## Futtatható példa

A bekapcsolt PC-s motorral, a repó gyökeréből:

```powershell
uv run --project python python python/examples/castle.py
```

A helyi The Other Side day-1 mentésből kiírja az építési feltételeket, megépíti a Pyramid épületet,
majd három Skeletont toboroz a helyőrségbe. Az eredmény: 1500 + 225 arany és 10 érc levonása;
5775 arany, 10 érc marad, a Skeleton-készlet 8-ról 5-re csökken. A nap nem változik.
Az eredeti mentésfájlt nem írja felül. Más mentés megadható `--save`, másik motor `--executable` útján.
A példa az adott mentésben szabályos építést/toborzást választ, és kiírja, ha nincs ilyen.

```python
with HeroesSession(executable, timeout=60) as game:
    game.load_save(save_path)
    state = game.get_state(include_serialized=False)
    human = next(p for p in state["players"] if p["is_human"])
    castle_id = human["castle_ids"][0]
    decision = game.start_session(human["id"])

    options = game.get_castle_options(castle_id)
    building = next(b for b in options["buildings"] if b["can_build"])
    result = game.build_castle(castle_id, building["building_id"], token=decision["token"])
    decision = result["decision"]

    options = game.get_castle_options(castle_id)
    dwelling = next(d for d in options["dwellings"] if d["max_recruitable"] >= 3)
    result = game.recruit_castle(castle_id, dwelling["dwelling_id"], 3, token=decision["token"])
```

Az utolsó két `next` feltételezi, hogy van megfelelő lehetőség. Az általános példa kezeli az üres listát is.

## Lekérdezés

`get_castle_options(castle_id)` betöltött játékban, vezérlő nélkül is használható. Nem lépteti a világot,
nem készíti elő a kört, nem változtatja a tokent, és nem inicializál videót vagy hangot.
Más játékos és semleges várának adatai is lekérdezhetők, ugyanazzal a mindent látó szemlélettel, mint a teljes állapot.
Ez nem ad jogosultságot a másik játékos várának módosítására.

Válasz: `castle_id`, `owner`, `perspective="omniscient"`, `state_version`, `buildings`, `dwellings`.

- Épület: `building_id`, `name`, `built`, `can_build`, `status`, `cost`, `requires`.
  Az azonosító egyetlen natív `BuildingType` bit; `requires` a natív előfeltétel-bitmaszk.
  A lista a motor meglévő, várfajta- és térképverzió-függő épületkatalógusát használja, növekvő azonosítósorrendben.
  Nem létező faji fejlesztések és a nem megvásárolható `BUILD_TENT` nem szerepelnek benne.
- Építési státusz: `allow_build`, `not_today`, `already_built`, `need_castle`, `build_disabled`,
  `shipyard_not_allowed`, `unknown_upgrade`, `requires_build`, `lack_resources`, `unknown_condition`.
  Ezek a `Castle::CheckBuyBuilding` eredményei, annak eredeti ellenőrzési sorrendjében.
- Lakóhely: `dwelling_id` (hat alaplakóhely egyike), `actual_building_id` (aktuális fejlesztés), `built`,
  `monster_id`, `name`, `available`, `unit_cost`, `max_recruitable`, `status`, `destination`.
  A maximum a meglévő lakóhelyre, készletre, natív fizetőképességre és célbeli sereghelyre vonatkozik.
  A `destination` értéke `null`, vagy `{type:"garrison",hero_id:null}`, vagy `{type:"hero",hero_id:…}`.
  A natív sorrend: először a helyőrség, hely hiányában az ott álló saját hős. A kliens nem választhat célsereget.

A `can_build` és `max_recruitable` a vár tulajdonosának natív feltételeit írja le; a külső művelethez
emellett aktív döntés és a vezérelt játékos tulajdonjoga szükséges. Új művelet után friss lekérdezés kell.

## Végrehajtás és védelem

- `castle.build`: `params={castle_id, building_id}`. A várnak sajátnak kell lennie, az épületnek szerepelnie kell
  a vár katalógusában. A `Castle::BuyBuilding` érvényesíti az árat, előfeltételeket, térképi tiltásokat és
  a várankénti napi építési korlátot; létrehozza az új lakóhely kezdeti készletét, kezeli a varázslócéhet,
  kapitányt és a város várrá alakításának natív mellékhatásait is.
- `castle.recruit`: `params={castle_id, dwelling_id, count}`. Pozitív, előjel nélküli 32 bites pontos mennyiség.
  A `dwelling_id` a hat alaplakóhely egyike (`1<<20` … `1<<25`), nem lényazonosító és nem fejlesztésazonosító.
  A motor a lakóhely aktuális fejlesztéséből választja a lényt; épület nélkül vagy hibás mennyiséggel nincs toborzás.
  Nincs automatikus lefelé kerekítés: a teljes mennyiségnek bele kell férnie a készletbe, pénzbe és seregkapacitásba.
  A meglévő csapat darabszámának túlcsordulását is elutasítjuk.

A `RecruitMonster` hívója felelős az eredeti `Troop` mennyiségének ellenőrzéséért. Az adapter ezért csak
előzetesen validált kérést ad át a közös `RecruitMonster(troop, false)` függvénynek; a játék eredeti függvényét nem írja át.
Az alacsonyabb szintű C++ függvény saját hívóit ebben a munkaszakaszban nem változtatjuk.

Mindkét művelet ugyanazt a tokenellenőrzést és világ/RNG checkpointot használja, mint a mozgás és körváltás.
Hibás paraméter: `invalid_request`; tiltott végrehajtás: `illegal_action`; régi token: `stale_decision`.
Elutasításkor a világ, pénz, készlet és döntés változatlan marad, az első módosítás kör-előkészítését is visszaállítva.

Sikeres események: `castle_built` (`castle_id`, `building_id`, `cost`) és `castle_recruited`
(`castle_id`, `dwelling_id`, `monster_id`, `count`, `cost`, `destination`). A válasz új döntést és tokent tartalmaz.

## Határok és platformok

Hősvásárlás, piaci csere és hajóvásárlás a 7. lépés következő része. Seregrendezés és átadás a 8. lépés feladata.
Várba lépő hős mozgási interakciója és a várnézet képkérése sincs még bekötve; a vár távoli kezelése már működik.
A korai Gym-példa kilenc akciója változatlan: ezeket a várműveleteket most a gazdagabb `HeroesSession` API adja.

Az új adapter külön, csak a bekapcsolt PC-s Python-módhoz fordított egységben él. A normál CMake-alapérték továbbra
is `ENABLE_PYTHON_ENV=OFF`; nincs új kötelező Python-csomag vagy platformfüggő kód.
Az eredeti `Castle::BuyBuilding` és `Castle::RecruitMonster` változatlan maradt.

## Ellenőrzés

Hat új integrációs teszt használja a két valódi mentést: mindent látó, változatlan lekérdezések;
építési költség, napi limit és következő nap; pontos toborzás és készletfogyás; faji fejlesztés;
megtelt helyőrség, hősbe továbbítás és helyhiány; hibás azonosító, mennyiség, tulajdonos,
előfeltétel és fizetőképesség; teljes világ és token változatlansága elutasításkor.

2026-10-29, Windows: a teljes, opcionális Gym-teszteket is tartalmazó készlet 57 tesztje sikeres.
A bekapcsolt PC-s fejlesztői build és a külön `ENABLE_PYTHON_ENV=OFF` normál build is sikeresen lefordult.
A normál build ellenőrzése után a helyi Python-bemutatókhoz tartozó fejlesztői futtatható fájl visszakerült a repó gyökerébe.
Más platformok SDK-fordítását és a normál grafikus játék kézi ellenőrzését ebben a munkaszakaszban nem futtattuk.
