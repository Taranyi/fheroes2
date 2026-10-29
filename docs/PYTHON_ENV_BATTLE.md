# Natív csaták vezérlése Pythonból

A 10. lépés deklarált profilja: kalandtérképről induló semlegeslény- és hős elleni csata,
ellenséges vár megtámadása, valamint a beépített AI köréből induló saját hős/vár védelme.
Ugyanaz az élő C++ `Battle::Arena` fut, mint a normál játékban. Python az egységköröknél választ;
az ellenfél a meglévő beépített harci AI-t használja.

## Futtatható példa

A bekapcsolt PC-s build és az eredeti helyi baseline után:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File script/windows/python-env-artifact-fixture.ps1
uv run --project python python python/examples/battle.py
uv run --project python python python/examples/battle.py --spells
uv run --project python python python/examples/battle.py --save build/python-env-baseline/fixtures/battles-ranged-day1.sav
```

A builder hat új, helyi, ignorált mentést készít: `battles-melee-day1.sav`, `battles-ranged-day1.sav`,
`battles-heroes-day1.sav`, `battles-loss-day1.sav`, `battles-boss-day1.sav`, `battles-siege-day1.sav`.
Az eredeti mentés nem változik. A mentések a motor saját sereg-, objektum- és mentési műveleteivel készülnek;
az éles API nem kap tesztadat-létrehozó vagy közvetlen állapotátíró parancsot.

A példa egy egyszerű Python-policyval lép és támad; a mozgásjelöltek és minden harci hatás a motorból származik.
A melee példában a győztes hős tapasztalatot kap, és a motor saját nekromanciája is módosíthatja a seregét.
A körök/műveletek és a végső eredmény a terminálon láthatók, a motor nem inicializál videót vagy hangot.

## Döntési hurok

```python
result = game.move_hero(hero_id, x, y, token=decision["token"])
while result["decision"]["phase"] in ("battle", "choice"):
    decision = result["decision"]
    if decision["phase"] == "battle":
        battle = decision["battle"]
        action = policy(battle)  # Egy elem a battle["actions"] listából.
        result = game.battle_action(action["action_id"], token=decision["token"])
    else:
        choice = decision["pending_choice"]
        result = game.answer_choice(choice["choice_id"], choice_policy(choice), token=decision["token"])
```

A csata az eredeti mozgás vagy `turn.end` végrehajtásán belül marad. Egy válasz után a motor feldolgozza
a belső morált, visszatámadást, sebzést, hatásokat és AI-lépéseket, majd a következő külső egységkörnél megáll.
A varázslás nem feltétlenül zárja le az aktív egység körét. A csata végén következhet képességválasztás,
majd adventure vagy tényleges motoreredménynél terminal döntés. Nem kell külön battle-demót indítani.

AI-támadáskor ugyanez a döntés jön vissza a `turn.end` hívásból. A token `player_id` mezője a vezérelt oldal,
miközben a világbeli `current_player` még a támadó AI körét jelölheti. A motor meglévő szerep-/nehézségi szabályait nem írjuk át.
A résztvevőnkénti több külső vezérlő továbbra is a 4/A feladata.

## Csataállapot és szabályos akciójelöltek

A `get_state` és `get_decision` `phase="battle"`, `battle={...}` adatot ad. A csata vége után `battle=null`.
Az aktuális csataobjektum tartalmazza:

- `map_index` a kalandtérképi hely azonosítója; `width=11`, `height=9`, `round`, `current_unit_uid`, `current_color`.
- `attacker_color`, `defender_color`, mindkét parancsnok neve/színe/manája és az adott körben elmondott varázslat jelzője.
- `siege`: erődített vár ostroma; a falak/kapu állapota a board objektumértékeiben is megjelenik.
- `board`: 99 mező, index, natív akadály-/falobjektum-érték és foglaló egység UID-je.
- `units`: mindkét oldal, halott egységekkel együtt; UID, lénytípus, létszám, életben van-e, eredeti és aktuális szín,
  fej/farok mező, kétmezős/repülő tulajdonság, megmaradt teljes HP, lövések, sebesség, támadás, védelem,
  natív `modes` bitmaszk és a beállított hatásokhoz tartozó `effects` időtartamok.
- `actions`: az aktuális egység és a támogatott profil szabályos, paraméterezett akciójelöltjei.

A világ `heroes[*].army` adata a tartós kalandtérképi sereg. A harctéri sereg külön natív példány;
csata közben a `battle.units` a tényleges harctéri állapot, a végén a motor szinkronizálja vissza a tartós sereget.
Az AI-k pozíciói, létszámai, sérülései és manája is szerepelnek a csataállapotban.

| `kind` | Jelentés és mezők |
|---|---|
| `skip` | Natív passzolás/védekezés, `unit_uid`. |
| `move` | Mozgás a `destination` mezőre, `unit_uid`. |
| `attack` | Mozgással vagy helyből közelharc: `unit_uid`, `target_uid`, `destination`, `target_cell`, `attack_direction`. |
| `shoot` | Lövés: `unit_uid`, `target_uid`, `target_cell`. |
| `spell` | `spell_id`, `target_cell`, `spell_points`; natív célpont- és körönkénti varázslási ellenőrzés. |
| `retreat` | Natív menekülés, ha az adott hősnek/helyzetben szabad. |
| `surrender` | Natív megadás, ha az ellenfél elfogadhatja és megfizethető; `gold` a teljes ár. |

Minden elemhez `action_id` tartozik. Csak az aktuális döntés listájában érvényes; új döntésnél újra kell olvasni.
Protokoll: `step`, `action="battle.act"`, `params={action_id}`, a teljes aktuális tokennel.
Nem küldünk ellenőrizetlen natív parancsparamétereket a harci végrehajtónak.
A lépésjelöltek a motor útkeresőjéből, a támadások a `Position`/`Board` natív elérhetőségi és irányellenőrzéseiből származnak.
A kétmezős egység célzott testrésze és a támadási irány is megmarad.
A varázslatjelöltek `GetTargetsForSpell` hívása nem dob ellenállásra és nem fogyaszt RNG-t.

A kezdeti `basic_targeted` varázslatprofil: Magic Arrow, Lightning Bolt, Bless, Curse, Haste, Slow, Shield,
Stone Skin, Steel Skin, Cure, Dispel, Cold Ray, Fireball. A hősnek ténylegesen ismernie/elérnie kell a varázslatot,
rendelkeznie kell könyvvel/manával, és a natív csataszabályoknak is engedniük kell azt.
Más harci varázslatok, teleport, tükörkép, feltámasztás, tömegvarázslatok és idézés nem kapnak külső jelöltet ebben a profilban.
A natív AI továbbra is a saját meglévő teljes harci tervezőjét használja.

## Eredmény, lekérdezés és megszakítás

Események: `battle_decision`, a választott paramétereket hordozó `battle_action`, végül `battle_completed`:
mezőindex, támadó/védő eredmény, tapasztalati értékek és a nekromanciához számított halottak.
Natív eredménybitek: vereség `1`, menekülés `2`, megadás `4`, győzelem `128`.
Az alkalmazott eredmény a világban is látható: veszteség, hős eltávolítása, foglalás, pénzátadás, tapasztalat,
tárgykezelés és nekromancia a meglévő natív folytatásból származik. Az eredményablak nem nyílik meg.
A szöveges nekromanciaértesítés esemény, kötelező OK-akció nélkül.

A várakozás alatt az állapot, AI-adatok és adventure kép ismételten lekérhetők, token- és világváltozás nélkül.
A 11. lépéstől a [natív csatakép is kérhető](PYTHON_ENV_VIEWS.md): `game.render(view="battle")`, kizárólag az élő külső csatadöntés alatt.
Hibás típus/mező: `invalid_request`; nem felkínált jelölt: `illegal_action`; más gameplay akció csata közben:
`battle_action_required`; elavult/idegen token: a meglévő tokenhibák. Ezek változatlanul hagyják az élő csatát.

A `session.stop` a csatát és a teljes eredeti kalandtérképi műveletet visszaállítja a kezdő checkpointig,
a már végrehajtott harci lépésekkel és AI-körrészlettel együtt, majd lecsatlakozik.
A close/EOF/reset szintén megszakíthatja a várakozást. A natív Arena előbb lebomlik, csak utána áll vissza a világ;
nem marad hivatkozás egy eldobott harctérre. A köztes szerializált világ nem tartalmazza a C++ vermet/harcteret,
ezért diagnosztikai pillanatkép, nem önállóan folytatható harci mentés.

## Határok

A csata az általános `HeroesSession` része. A korai kilencakciós Gym-példa csatánál `unsupported_battle` hibát és resetigényt ad;
nem választ automatikusan, nem jelenti vereségnek vagy időlimitnek. A teljes Gym-kódolás továbbra is a 13. lépés feladata.
Ha a motor külső egységdöntés előtt tényleges vereséget állapít meg, az természetesen valódi terminal/terminated eredmény.
A támogatott mozgási célok ellenséges hőssel/várral bővültek; a saját várba belépés és más, még nem bekötött kalandtérképi objektumok külön feladatok.
A headless ágak az inputot és megjelenítést cserélik; a normál UI megmarad. Python/JSON csak az opcionális PC-s adapterhez kell.

2026-10-29, Windows: mind a 111 Python-integrációs teszt sikeres, a 12 új csatateszttel, a Gym csatahatárával és az AI-körből
induló várvédelem/rollback próbájával együtt. Támadó ostromban a vár ténylegesen a saját oldalhoz került.
A Python-bemutató varázslással is végigfutott videó/hang nélkül. A bekapcsolt fejlesztői build és a külön
`ENABLE_PYTHON_ENV=OFF` normál Windows-build is sikeres. A gyökérben a példákhoz használható bekapcsolt program maradt.
Más platformok SDK-fordítása és a normál GUI kézi kattintásos ellenőrzése ebben a munkaszakaszban nem történt meg.
