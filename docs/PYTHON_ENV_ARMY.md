# Seregrendezés és hőstalálkozás Pythonból

A 8. lépés első része: pontos csapatáthelyezés, szétosztás, összevonás és slotcsere, továbbá szabályos átadás
saját hősök, illetve a vár és az ott álló saját hős között. Nincs távoli vagy idegen sereghez hozzáférés.
A [tárgyátadás külön leírásban](PYTHON_ENV_ARTIFACTS.md) már működik; további hősműveletek még hátravannak.

## Futtatható példa

A bekapcsolt PC-s motorral és a helyi referenciamentéssel, a repó gyökeréből:

```powershell
uv run --project python python python/examples/army.py
```

A The Other Side day-1 mentésben Roxana 9 Skeleton és 4 Zombie egységét szétosztja, összevonja és átrendezi.
Négy Zombiet átad a vár helyőrségének, majd visszaadja őket. Roxana kilép a várból, a script megvesz egy felkínált hőst,
natív találkozást hajt végre, és két Skeletont átad neki. A hősvásárlás a 7. lépés meglévő művelete.
Az eredeti mentést nem írja felül. A példa `--executable` és `--save` argumentumot fogad, de a bemutató útvonal ezt a referenciamentést igényli.

```python
source = {"kind": "hero", "id": 52, "slot": 0}
target = {"kind": "hero", "id": 52, "slot": 2}
result = game.transfer_troops(source, target, 4, token=decision["token"])
decision = result["decision"]
result = game.swap_troops(source, {"kind": "hero", "id": 52, "slot": 1}, token=decision["token"])
```

A teljes betöltési és lezárási ciklus a futtatható példában szerepel. Minden sikeres művelet új tokent ad.

## Endpoint és pontos áthelyezés

Az endpoint pontosan `{kind, id, slot}` mezőket tartalmaz. `kind` értéke `hero` vagy `castle`;
`id` a `get_state` hős-/várazonosítója; `slot` nulla alapú hely `0..4` között.
Az állapotban a hős `army`, a vár `garrison` listája ugyanezeket a helyeket adja, üres helyen `null` értékkel.

- `transfer_troops(source, target, count, token=...)` → `army.transfer`, `params={source,target,count}`.
  Pozitív, előjel nélküli 32 bites darabszám. Üres célhelyre áthelyez/szétoszt, azonos lénytípusnál összevon.
  Más lénytípusú célhoz slotcserét kell használni. Nincs automatikus célhelyválasztás vagy részleges teljesítés.
- `swap_troops(source, target, token=...)` → `army.swap`, `params={source,target}`.
  Két különböző slot tartalmát cseréli, akár eltérő lénytípusokkal. Két üres hely cseréjét elutasítjuk.
- Saját seregen belül az egyetlen csapat is áttehető másik üres helyre, mert a sereg összességében nem ürül ki.
  Másik seregbe átadásnál a natív `Army::SaveLastTroop` alapján a hős utolsó kötelező egysége megmarad.
  A kérés elutasított, ha az egész utolsó csapatot elvinné; a kliens kérhet pontosan eggyel kevesebbet.
- A vár helyőrsége teljesen kiüríthető. Két foglalt slot cseréje a hős utolsó csapatával is szabályos,
  ha közben másik csapat kerül a helyére. A cél darabszámának 32 bites túlcsordulását elutasítjuk.

A két slot számlálási művelete a közös `Army::TransferTroops` függvénybe került; ezt a normál seregrendező UI
érintett pontos szétosztási/összevonási ágai is használják. A csere a meglévő `Army::SwapTroops`.
Pythonban nem születik második seregkezelési szabályrendszer.

## Hozzáférés és találkozás

Mindkét endpointnak a várakozó, külső vezérlésű résztvevő tulajdonában kell lennie. A hősnek aktívnak kell lennie.
Egy saját sereg belső rendezése önmagában nem igényel találkozást.

A vár és a hős között csak akkor lehet átadni, ha a hős ténylegesen a vár látogatói helyét foglalja el.
A puszta szomszédság nem elég. Különböző várak között nincs közvetlen átadás.
A jelenlegi mozgási profilban az üres várba visszalépés továbbra sincs bekötve; a mentésben ott álló vagy frissen megvett hős kezelheti a helyőrséget.

Két hős között előbb `meet_heroes(hero_id, other_hero_id, token=...)` szükséges:

1. `hero.meet`, `params={hero_id,other_hero_id}`. Két különböző, saját, aktív szárazföldi hős kell.
2. A hősöknek közvetlen szomszédoknak kell lenniük; a natív útkeresés egyetlen szabályos lépést kell adjon hozzájuk.
   Így a geometriai közelség önmagában nem enged falon/akadályon keresztüli találkozást.
3. A kezdeményezőnek ki kell fizetnie az út natív mozgáspontköltségét. A meglévő `Heroes::Move(true)` és
   `ActionToHeroes` út fut: a kezdeményező a másik előtt marad, az ára levonódik. A referenciában 100 pont.
4. Headless módban a találkozás seregrendező/tárgykezelő UI-ja nem nyílik meg. Nem történik automatikus sereg- vagy tárgycsere;
   az adott módosítást a külön, validált parancs kéri. A normál mód továbbra is az eredeti találkozási ablakot használja.

A válasz és a `get_state` tartalmazza az `army_meeting` adatot (`hero_id`, `other_hero_id`, `from`, `to`), vagy `null` értéket.
Ez sessionbeli jogosultsági kontextus, nem új, mentésbe írt játékszabály. A tárgyműveleti bővítés az induláskori
felderítési bónuszokat is tárolja benne. A két érintett hős mindkét irányban adhat át csapatokat és tárgyakat.
További seregműveletek nem fizetnek újabb találkozási költséget. Lekérdezés és render nem zárja le a kontextust.
Az `end_meeting` explicit lezárás elvégzi a natív nettó felderítési mellékhatásokat. Más sikeres játékművelet
(mozgás, körváltás, építés, vásárlás, piaci csere) és a `session.stop` ezt automatikusan megteszi;
utóbbi nyitott találkozásnál ezért az állapotverziót is növeli. Új csatlakozás és mentésbetöltés üres kontextusból indul.
Másik hőspárra indított sikeres találkozás lecseréli. Elutasításkor az előző kontextus is megmarad a checkpointból.

Események: `heroes_met` (hősazonosítók, `movement_spent`), `army_transferred` (endpointok, `monster_id`, `count`),
`army_swapped` (endpointok). A rendezés önmagában nem léptet napot, nem fogyaszt pénzt és nem módosít mozgáspontot.
A hadsereg megváltozása a későbbi natív mozgási, morál-, sebesség- és harci számításokra természetesen hat.

## Hibák, határok, ellenőrzés

Hibás mező/típus/hely/darabszám: `invalid_request`; tiltott hozzáférés, távoli átadás, elégtelen mozgás,
inkompatibilis cél vagy utolsó csapat elvesztése: `illegal_action`; hajós találkozás: `unsupported_action`.
Minden művelet a meglévő tokenes döntés- és világ/RNG-checkpointot használja. Elutasításkor világ, döntés és
találkozási kontextus változatlan. Az AI-k teljes állapota továbbra is lekérhető, de külső vezérlésük átvétele még nem támogatott.

Hét új valós motoros teszt ellenőrzi a csapatszámok lénytípusonkénti megmaradását, belső split/merge/cserét,
várbeli átadást és utolsó csapat védelmét mindkét csereirányban, hős–hős találkozást és költségét,
oda-vissza átadást, lejárt kontextust, mozgáspont hiányát, távoli/idegen hozzáférést és hibás bemeneteket.
A futtatható bemutató ablak és hang nélkül sikeres. A normál GUI érintett ágait kézzel és más platformok SDK-fordítását itt nem teszteltük.

A tárgyátadás már elérhető; teljes seregek automatikus szétosztása, fejlesztés/elbocsátás/varázskönyv-vétel és a teljes 8. lépés még hátravan.
A korai Gym-példa kilenc akciója változatlan; az új műveleteket a `HeroesSession` adja.

2026-10-29, Windows: mind a 70 Python-integrációs teszt sikeres, beleértve a Gymnasium ellenőrzőjét és a hét új seregműveleti tesztet.
A bekapcsolt PC-s fejlesztői build és a külön `ENABLE_PYTHON_ENV=OFF` normál Windows-build is sikeresen lefordult.
A normál build után a Python-példákhoz tartozó fejlesztői futtatható fájl került vissza a repó gyökerébe.
