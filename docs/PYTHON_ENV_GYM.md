# 13. lépés: strukturált Gymnasium-adapter

Frissítve: 2026-10-31. A `HeroesEnv` és a regisztrált `Fheroes2-v0` a meglévő C++ motor dokumentált
`adventure_basic` profilját vezérli. Az adventure, választás, csata és terminális döntés egyetlen epizód része.
A korábbi `Fheroes2AdventurePreview-v0` kompatibilitási példaként megmarad; az új adapter külön azonosítót kap.

```powershell
uv sync --project python --extra gym
uv run --project python python python/examples/train_loop.py
uv run --project python python python/examples/train_loop.py --battle-demo --max-steps 100
```

```python
from fheroes2_env.gym_env import make_env

with make_env(executable="fheroes2.exe", save="checkpoint.sav", max_steps=1000) as env:
    obs, info = env.reset(seed=123)
    for _ in range(10000):
        action = env.action_space.sample(mask=obs["action_mask"])
        obs, reward, terminated, truncated, info = env.step(action)
        if terminated or truncated:
            obs, info = env.reset()
```

Közvetlenül is példányosítható: `HeroesEnv(...)`. Új pálya: `save` helyett `map_path="maps/THEOTHER.MP2"`.
Az egy külső résztvevő és az omniscient állapot megmarad: az AI-k hősei, várai, erőforrásai és csataegységei is szerepelnek.
A 4/A oldalankénti vezérlés, AI-only és több agent külön feladat; ezt az adapter nem helyettesíti kézi kattintásokkal.

## Akciók és natív maszk

Az akciótér `Discrete(max_actions)`, alapértelmezetten `Discrete(8192)`. A slot az aktuális megfigyelés
`actions[slot]` sorát és az `info["actions"][slot]` strukturált parancsát jelenti. A slotok jelentése döntésenként változhat;
a numerikus jelöltleírás és maszk mindig ugyanahhoz az állapothoz tartozik. Régi állapotból eltett slot nem stabil parancsazonosító.
Az adapter a tokent belül kezeli, nem kéri a tanuló agenttől, és a kapcsolati sessionazonosítót nem teszi a megfigyelésbe.

Az érvényes jelöltek a tömb elején vannak, `action_mask=1`; a többi sor nulla és maszkolt.
`env.unwrapped.action_masks()` külön bool másolatot ad maszkot használó RL-wrapperekhez.
Maszk nélküli `action_space.sample()` is megengedett: a padding slot kiválasztása elutasított próbálkozás,
`info["action_accepted"]=False`, `rejection.code="masked_action"`, nulla jutalom. A motor és a függő döntés változatlan,
de az agent próbálkozása beleszámít az epizódlimitbe. Nem küldünk helyette körvége vagy más játékműveletet.
Érvénytelen típus, bool és a `Discrete` téren kívüli szám `ValueError`, nem számít lépésnek.

A profil parancskategóriái, az `actions[:,0]` 1-alapú kódjának sorrendjében:

1. `turn.end`
2. `hero.move`
3. `castle.build`
4. `castle.recruit`
5. `castle.refresh_heroes`
6. `castle.hire`
7. `market.trade`
8. `hero.meet`
9. `army.transfer`
10. `army.swap`
11. `artifact.transfer`
12. `artifact.swap`
13. `hero.end_meeting`
14. `army.upgrade`
15. `army.dismiss`
16. `hero.dismiss`
17. `hero.buy_spell_book`
18. `hero.cast`
19. `choice.answer`
20. `battle.act`

A hősmozgás az összes saját aktív hős nyolc szomszédos mezőjére ad jelöltet. A hosszabb út ismételt lépésekből
állítható össze; az általános session továbbra is elfogad távolabbi célt. Szimmetrikus sereg-/tárgycserénél csak egy
kanonikus irány szerepel; üres tárgycélra áthelyezés, két foglalt tárgynál csere szerepel. A mennyiségi műveletek
összes engedélyezett egész értéke jelölt: nem csak „egy” és „maximum”. A láda, szintlépés, csatlakozás, megerősítés
és toborzási mennyiség az élő motor opcióit használja. A csatánál minden natív akciójelölt változatlan sorrendben bekerül.
Az első adventure jelölt a kör vége; aztán ID szerint a hősök és várak, stabil slot- és mennyiségi sorrend következik.
A pontos enumerációt a `gym_candidates.py` rögzíti; a séma verziója a környezet `v0` azonosítója.

Az új natív `check_actions` lekérés legfeljebb 128 `{action,params}` parancsot és egy aktuális `token` objektumot fogad,
és ugyanennyi booleant ad a `valid` mezőben. Csak adventure várakozásnál használható; választás/csata eleve kész
opciókat ad. A Python jelölteket állít össze, a végső érvényességről a C++ adapter és a közös natív ellenőrzések döntenek.
A mozgás ellenőrzése és végrehajtása ugyanazt az útvonalvalidálást használja. A sereg-/tárgyműveletek ellenőrzése
lokális másolatokon használja a natív csere/átadás függvényeket; a világ nem kerül próbaképpen végrehajtásra és visszatöltésre.
Nincs vásárlás, RNG-fogyasztás, ajánlatfrissítés, felderítés vagy új döntés a maszk lekérdezése közben.

A maszk a parancs jelenlegi natív előfeltételeit ellenőrzi. Egy későbbi AI-kör vagy interakció elérhet a még nem támogatott
motorprofilhoz: ekkor továbbra is kivétel jön, nem automatikus válasz vagy hamis epizódvége.

## Fix megfigyelés

`observation_space` egy `Dict`. A numerikus adatok `int64`, a `action_mask` `int8`.
Nincs string, változó méretű tömb vagy kép az RL-megfigyelésben. A hiányzó sorok nulla kitöltést kapnak;
a sorok érvényességét külön maszk jelzi. Null entitásazonosító/hely egy létező soron belül általában `-1`.
A natív ID-kat megtartjuk; a hős/vár sorindex nem ugyanaz, mint a hős/vár ID.

| Mező | Alapméret | Tartalom |
|---|---|---|
| `global` | 12 | Fázis, külső résztvevő, aktuális szín, térképméret/seed, dátum, eredmény, agent lépésszám és hátralévő limit |
| `tiles`, `tile_mask` | 20736×16, 20736 | Terep, objektum, köd, járhatóság, metadata, fő objektum UID; natív tile-index sorrend |
| `players`, `player_mask` | 6×13, 6 | ID, control, in_play, faj, szövetség, vár nélküli napok, hét erőforrás; minden oldal |
| `heroes`, `hero_mask` | 128×22, 128 | Katalógus-ID szerint, az inaktív hősökkel együtt; képességek, mana, mozgás, státusz, vár és koordináta |
| `hero_armies` | 128×5×2 | Lényazonosító, darabszám |
| `hero_artifacts` | 128×14×2 | Tárgyazonosító, tekercsvarázslat |
| `hero_skills`, `hero_spells` | 128×8×2, 128×128 | Másodlagos képesség/szint, varázslat-ID maszk |
| `castles`, `castle_mask` | 128×7, 128 | ID szerint: ID, tulajdonos, faj, vár-e, x/y, látogató hős |
| `castle_buildings` | 128×32 | Natív épületbitek |
| `castle_armies`, `castle_dwellings` | 128×5×2, 128×6×2 | Helyőrség; alaplakóhely-ID és készlet |
| `battle` | 9 | Térképi hely, 11×9 méret, kör, aktuális UID/szín, támadó/védő szín, ostrom-e |
| `battle_units`, `battle_unit_mask` | 32×16, 32 | Mindkét sereg élő harci egységei, HP, lövés, hely, módok; a natív listában a halott egységek is szerepelhetnek |
| `battle_effects`, `battle_board` | 32×32, 99×3 | Egység módonként hátralévő kör; mezőindex, objektum és egység-UID |
| `battle_commanders` | 2×3 | Szín, mana, varázsolt-e ebben a körben; támadó, majd védő |
| `choice`, `choice_values`, `choice_value_mask` | 6, 9, 9 | Választástípus, ID, hős-ID, minimum/maximum, jelöltszám; jutalom/költség/képességadatok |
| `actions`, `action_mask` | 8192×30, 8192 | Numerikus akcióleírások és aktuális érvényességük |

A `global` pontos sorrendje: phase, player_id, current_player, width, height, map_seed, total_days, total_weeks, month,
game_result, episode_step, remaining_steps. Fáziskód: adventure=0, choice=1, battle=2, terminal=3.
A `tiles` sorrendje: index, x, y, terrain, terrain_image, terrain_flags, water, road, object_type, object_under_hero,
fog_colors, passability, a három metadata és main_part.uid.
A hős- és egységoszlopokat a `gym_observation.HERO_FIELDS`, `UNIT_FIELDS` publikus konstansok adják;
a hős sor végén még x/y szerepel. A `CHOICE_VALUES` sorrend: gold, experience, monster_id, count, available,
gold_per_unit, primary_skill, first_level, second_level. Ismeretlen választási értékmezőt explicit elutasítunk.

Az `ACTION_FIELDS` oszlopai:

```text
type, hero_id, other_hero_id, castle_id, x, y, building_id, dwelling_id,
count, resource_from, resource_to, lots, spell_id, choice_id, value, action_id,
source_kind, source_id, source_slot, target_kind, target_id, target_slot,
battle_kind, unit_uid, target_uid, destination, target_cell, attack_direction,
spell_points, gold
```

Endpointfajta: 0=nincs, 1=hős, 2=vár. A csatatípus 1-alapú sorrendje skip, move, attack, shoot, spell, retreat, surrender.
A választástípus 1-alapú sorrendje treasure.gold_or_experience, hero.secondary_skill, monster.join, monster.pursue,
confirmation, army.recruit_count. Más mezőkben a natív motorazonosítók szerepelnek.
Minden visszaadott tömb és `info` független másolat; az agent általi módosítás nem változtatja az adapter parancsait.
Az `info["state"]` a teljes strukturált, minden oldali állapot, mentéspayload nélkül; az `info["events"]` a natív események,
az `info["actions"]` a numerikus sorokhoz tartozó parancsobjektumok. Nem kell szöveges parancsot visszaküldeni.

## Korlátok és lezárás

Az alap felső korlátok: térképméret 144×144, 128 hős, 128 vár, 32 csataegység, 8192 akciójelölt.
Konstruktorparaméterek: `max_map_size`, `max_heroes`, `max_castles`, `max_battle_units`, `max_actions`.
Megengedett konfigurációs maximumok: 144, 256, 512, 256, 65536. Egy döntésben legfeljebb 262144 adventure jelöltet vizsgálunk.
A tér és a tömbméret az epizódok között sem változik. Korláttúllépéskor `ProfileLimitError` (`gym_profile_limit`) jön;
nem dobunk el egységet, opciót vagy érvényes jelöltet csendben. A teljes mennyiségi enumeráció miatt nagyon nagy
seregek vagy készletek nagyobb `max_actions` értéket igényelhetnek. Ez a kezdő profil még nincs nagyléptékű RL-re optimalizálva.

Köztes jutalom `0.0`, natív győzelem `+1.0`, natív vereség `-1.0`. Az eredmény a motor `GameOver` bitjeiből jön;
ismeretlen vagy egyszerre győzelem/vereség eredmény kivétel. Döntetlenre most nincs külön támogatott natív eredmény.
A jutalom nincs összekötve a toborzás, aranyfelvétel vagy ellenséges veszteség mennyiségével; ezekhez külön reward wrapper írható.
Natív végállapot: `terminated=True`. `max_steps` agent próbálkozás után: `truncated=True`, amennyiben nem lett valódi végállapot.
Ha ugyanazon lépésben mindkettő esedékes, a natív végállapot elsőbbséget élvez. Choice/battle válasz is egy agent lépés.
A számláló nem motorbeli napokat vagy csataköröket jelent.

Nem támogatott motorhelyzet, hibás protokoll, timeout, crash vagy profilkorlát kivétel, utána reset szükséges.
Nem jelöljük győzelemnek/vereségnek/időlimitnek. A reset hibánál lezárja az új folyamatot; a `close` idempotens.
A reset a 12. lépés seedelt, friss folyamatú API-ját használja. `options` megengedett kulcsai `save`, `map_path`,
`player_id`, `difficulty`; a sikeres új konfiguráció megmarad a későbbi resetekre. Az effektív seed `info["seed"]`.

## Renderelés és opcionális függőségek

`render_mode=None`: a reset, léptetés és render egyáltalán nem kér képet a motortól. A numerikus megfigyelés ettől független.
`render_mode="rgb_array"`: csak az explicit `env.render()` kér RGB uint8 HWC képet.
`render_view="auto"` csatánál a csatát, egyébként a kalandtérképet rajzolja. Megadható adventure/battle/hero/castle is;
hős/vár esetén `hero_id`/`castle_id`, vagy az első aktív saját entitás. A battle nézet aktív csatát követel.
Az általános session API minden további renderparamétere külön is elérhető.
Az új adapter ablakos `human` módot nem tartalmaz; a meglévő preview külső megjelenítője megmarad.

A base Python-csomag továbbra is külső függőség nélkül importálható; a Gym-modult külön kell importálni.
A C++ ellenőrzési bővítés csak az opcionális adapterben fordul. Nincs új Python- vagy venv-követelmény a normál,
Android vagy iOS build számára. A további varázslatok és objektumok
ugyanazok a nyitott feladatok, mint az általános sessionnél; a „teljes Gym-adapter” e dokumentált profil teljes Gym-életciklusát jelenti.

## Ellenőrzés

`test_gym_env.py`: hivatalos Gymnasium checker, determinisztikus visszajátszás, minden kezdeti maszkolt natív parancs
külön friss állapotból történő végrehajtása, AI-adatok és fix terek, választás/szintlépés/csata egy epizódban,
pozitív/negatív terminális jutalom, időlimit, profilkorlát, két maszkoltan mintázott epizód, reset, render nélküli futás,
nézetek és a natív maszk lekérdezésének teljes payload-/döntés-/RNG-változatlansága.
A győzelmi tesztmentést a meglévő natív fixture builder alapfutása, vagy külön a `--gym-only` kapcsoló készíti: 10000 arany és ennyit
követelő szabványos győzelmi feltétel, amelyet a natív motor az első körlezárásnál értékel. Nem állítunk közvetlenül eredménybitet.
A bináris tesztmentések és az eredeti assetek nem kerülnek a repóba.

A baseline elkészítése után a további mentések Windows alatt reprodukálhatók:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File script/windows/python-env-artifact-fixture.ps1
uv run --project python --extra gym python -m unittest discover -s python/tests -v
```

2026-10-31-i végső ellenőrzés: **146 sikeres Python-teszt**, ebből 15 új Gym-teszt, köztük a hivatalos
Gymnasium checker. A maszkoltan mintázó példa két 50 lépéses epizódja időlimittel ért véget; a csatás példa
két epizódja valódi motorbeli vereséggel és `-1` jutalommal zárult, 27 és 22 lépés után.
A headless policy ellenőrzés, az engedélyezett és Python nélküli Windows-build is sikeres.
A base csomag NumPy/Gym importálása nélkül is működik. Más platformok SDK-buildjét és a normál ablakos
játék kézi végigkattintását ebben a lépésben nem ellenőriztük. A teljesítménymérés és a végső elfogadási futás a 14. lépés.

## 7. kiegészítés: navigáció

A `castle.buy_boat` új kategória a korábbiak után (21.), a natív maszk alapján. A `hero.move` hajózást és saját várba belépést is kezel.
A hős numerikus sora `is_shipmaster` mezővel bővült (az x/y előtt), így a `heroes` alap alakja 128×22.
A korábbi 128×21 bemenetet használó modelleket módosítani kell; az epizódon belüli alak továbbra is fix.
[Natív szabályok, API, futtatható példa és ellenőrzések](PYTHON_ENV_NAVIGATION.md).
