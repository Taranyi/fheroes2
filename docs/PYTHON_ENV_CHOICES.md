# Választások és adventure varázslatok Pythonból

A 9. lépés kezdeti, deklarált profilja: szárazföldi kincsesláda arany/tapasztalat választása,
az abból következő natív szintlépések képességválasztásai, semleges lények ingyenes/fizetős csatlakozása és üldözése,
valamint a dzsinnlámpa és a Wagon Camp toborzási döntései. Az első két varázslat az Identify Hero és a Visions.
A [10. lépés csatái](PYTHON_ENV_BATTLE.md) már ugyanebben a döntési folyamatban vezérelhetők; a többi pályaobjektumot és varázslatot nem állítjuk késznek.

## Futtatás

Az opcionális PC-s build és az eredeti helyi baseline elkészítése után:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File script/windows/python-env-artifact-fixture.ps1
uv run --project python python python/examples/choices.py
```

A natív tesztadat-készítő a korábbi négy mentés mellett hat `choices-*-day1.sav` másolatot ír:
`chest`, `join`, `paid-join`, `pursue`, `recruit`, `spells`. A motor saját objektumelhelyezőjét,
szabályfüggvényeit és mentőjét használja; nincs Python-mentésértelmező vagy éles csalóparancs.
Az eredeti bemenet és felhasználói mentések változatlanok. Ezek helyi, ignorált tesztadatok.

A példa a vár alatti ládát kéri, a tapasztalatot választja, majd minden felkínált szintlépésnél az első képességet.
A végén kiírja a hős szintjét, tapasztalatát, képességeit és az ablak/hang nélküli runtime-adatokat.

## A felfüggesztett döntés szerződése

```python
result = game.move_hero(hero_id, x, y, token=decision["token"])
while result["decision"]["phase"] == "choice":
    decision = result["decision"]
    choice = decision["pending_choice"]
    value = policy(choice)  # A saját Python-agent választ.
    result = game.answer_choice(choice["choice_id"], value, token=decision["token"])
```

A `step` a következő külső döntésig fut. Ez lehet újabb `choice`, a befejezett művelet utáni `adventure`,
vagy valódi motoreredménynél `terminal`. Az eredeti C++ hívási verem életben marad; a választás után ugyanaz a natív
művelet folytatódik. Nem játsszuk újra a lépést és nem számolunk második játéklogikát Pythonban.
Több egymást követő választásnál mindig az új válasz döntési tokenjét kell használni.

A függő döntés `available_actions` listája `choice.answer`, `session.stop`. A `get_state` és `get_decision`
ugyanazt a `pending_choice` objektumot adja; `phase="choice"`. Közben a teljes világ, minden AI serege/vára,
képességlista és adventure kép továbbra is lekérhető. A lekérdezés/render nem választ, nem léptet és nem módosít tokent.

`pending_choice` mezői:

- `choice_id`: folyamaton belül növekvő azonosító, visszaállítás után sem használjuk újra.
- `kind`, `hero_id`: a döntés típusa és érintett hőse.
- `options`: az elfogadható egész visszatérési értékek listája.
- `minimum`, `maximum`: üres `options` esetén a választható egész mennyiség zárt tartománya.
- `values`: a motor által felkínált számadatok.

| Típus | Válasz | Adatok |
|---|---|---|
| `treasure.gold_or_experience` | `1` arany, `0` tapasztalat | `gold`, `experience` |
| `hero.secondary_skill` | A felkínált képesség natív azonosítója | Elsődleges képesség és a felkínált képességszintek; az aktuális hősállapot is olvasható. |
| `monster.join` | Az `options` első eleme igen, második nem | `monster_id`, `count`, `gold`; a diplomácia létszáma/ára a natív szabályból jön. |
| `monster.pursue` | Az `options` első eleme üldözés, második elengedés | `monster_id`, `count` |
| `confirmation` | Az `options` első eleme igen, második nem | A kapcsolódó szöveg az ugyanebben a válaszban lévő értesítési eseményben. |
| `army.recruit_count` | `0..maximum`; nulla a vásárlás elutasítása | `monster_id`, `available`, `gold_per_unit`; a maximális mennyiséget minden natív pénzfeltétel korlátozza. |

Protokoll: `step`, `action="choice.answer"`, `params={choice_id,value}`, az aktuális teljes `token` mellett.
Hibás típus/mező: `invalid_request`; idegen vagy régi token: a meglévő tokenhibák; rossz választásazonosító:
`stale_choice`; nem felkínált érték: `illegal_action`; más játékművelet függő döntés közben: `choice_required`.
Ezek nem mozdítják el a várakozó natív műveletet és nem módosítják a világot.

Események: `choice_requested`, `choice_answered`, szöveges `notification`, a végén a szokásos mozgási/műveleti események.
Az eseménylista az egész eredeti művelet eddigi története, nem az utolsó válasz óta keletkezett különbség.
A csak OK-t kérő értesítés eseménnyé válik, nem kérünk hozzá üres agent-akciót.

## Részleges állapot, megszakítás és hibák

A választásnál látható világ az eredeti művelet köztes állapota: a hős már mozoghatott, illetve szintlépésnél az
elsődleges képesség már nőhetett. A hatásokat a motor eredeti sorrendjében alkalmazzuk. A teljes művelet csak a végső
adventure/terminal döntésnél kész. A köztes szerializált payload diagnosztikai pillanatkép; nem tartalmazza az élő C++
hívási vermet, ezért nem önállóan folytatható mentés.

Függő választásnál a `session.stop` megszakítja és a kiindulási checkpointig visszaállítja az egész eredeti műveletet,
az addig megválaszolt szintlépésekkel együtt, majd lecsatlakozik. Új sessionből az eredeti világ folytatható.
A `close`, EOF és a Python-resethez tartozó folyamateldobás is megszakíthatja a várakozást; nem marad UI-inputvárakozás.

A szabályos választás folytatása csatához is vezethet: ilyenkor `phase="battle"`, a [csata saját akcióival](PYTHON_ENV_BATTLE.md).
Egyéb, még nem támogatott interakciónál `unsupported_interaction` érkezhet. Ilyenkor az egész eredeti lépés
világ/settings/RNG/UID/döntési checkpointja áll vissza. A függő döntés megszűnik; új `get_decision()` kell.
A hiba nem vereség és nem időlimit.
Nem támogatott köztes akcióobjektumon/őrzött útvonalon továbbra sem haladunk át.

## Adventure varázslatok

`game.cast_spell(hero_id, spell_id, token=...)` → `hero.cast`, `params={hero_id,spell_id}`.
Jelenleg Identify Hero és Visions; egyik sem igényel képernyős célkijelölést.
Saját, aktív, varázslásra jogosult hős kell könyvvel, elérhető varázslattal, elegendő manával/mozgással és a natív
helyzetfeltételekkel. A `CanCastSpell` ellenőrzést a meglévő `ActionSpellCast` és `SpellCasted` követi, ugyanazzal az árral
és mellékhatással, mint a normál játékban. Az Identify Hero ismétlése aktív hatásnál tiltott; a Visions újra elmondható a natív feltételekkel.

A `get_state` minden hősének `adventure_spell_options` listája tartalmazza a két támogatott varázslat azonosítóját,
nevét, árát (`spell_points`, `move_points`), `can_cast` jelzőjét és `blocked_reason` szövegét.
Ez tisztán olvasó, az AI-hősöket is tartalmazza; módosítási jogosultságot nem ad.
A résztvevők `identify_hero` és `vision_monster_indices` mezői mutatják a natív hatásokat.
Sikeres varázslás: `spell_cast` esemény, tényleges mana- és mozgáspont-levonással.
Más varázslat: `unsupported_action`; hibás azonosító/típus: `invalid_request`; tiltott natív feltétel: `illegal_action`.
A célzott teleportálás, hajóidézés, őrzőlények és a View World varázslatok még nincsenek a támogatott profilon.

## Gym és platformhatár

A korai `Discrete(9)` Gym-példa nem tartalmaz választási akciókat. Ha választást ér el, `unsupported_choice` hibát ad
és resetet kér, nem ad hamis `terminated`/`truncated` eredményt, és nem választ automatikusan.
Az általános Python API már kezeli ezeket; a teljes Gym-kódolás a 13. lépés része.

A közös interakciós szolgáltatás nem függ Pythontól vagy JSON-tól. A normál UI az eredeti ágait használja,
az env-szolgáltatás az explicit headless módban és aktív motoros művelet alatt él.
A mobilos és normál PC-s buildhez továbbra sem szükséges Python vagy venv.

2026-10-29, Windows: mind a 98 integrációs teszt sikeres, a 12 új választási/varázslási teszttel és a Gym választáshatár-tesztjével együtt.
A láda → két szintlépés → adventure példaprogram is sikeresen lefutott (2049 tapasztalat, 3. szint), videó/hang nélkül.
A bekapcsolt PC-s fejlesztői build és a külön `ENABLE_PYTHON_ENV=OFF` normál Windows-build is lefordult.
A bemeneti baseline és felhasználói mentések nem változtak. A többi platform SDK-fordítása és a normál GUI kézi kattintásos próbája itt nem történt meg.
