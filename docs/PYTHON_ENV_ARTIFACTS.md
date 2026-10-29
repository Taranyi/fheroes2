# Tárgyátadás és csere Pythonból

A 8. lépés tárgykezelési része: saját hős tárgyainak belső átrendezése, átadás üres helyre és két tárgy explicit cseréje.
Két hős között a meglévő `hero.meet` találkozás szükséges. Varázskönyvet sem átadni, sem áthelyezni, sem elcserélni nem lehet.
A többi hősművelet (lényfejlesztés, elbocsátás, varázskönyv-vétel) továbbra is hátravan.

## Futtatható példa és natív tesztmentések

A két eredeti referenciamentés saját oldalán nincs mozgatható tárgy. Ezért külön tesztmentések készülnek a
motor saját betöltőjével és `Game::Save` mentőjével, az eredeti The Other Side day-1 mentésből.
Nem készül Python-mentésértelmező, és az éles Python API nem kap tetszőleges tárgyat létrehozó parancsot.

Előfeltétel: bekapcsolt PC-s fejlesztői motor, eredeti játékadatok, a korábbi helyi baseline-mentés. Windows alatt:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File script/windows/python-env-artifact-fixture.ps1
uv run --project python python python/examples/artifacts.py
```

A script explicit, `EXCLUDE_FROM_ALL` natív tesztadat-készítőt fordít; ez nincs benne a normál buildben, nincs telepítve,
és nem része a játéknak vagy az éles parancsprotokollnak. Saját belépési ponttal a meglévő motorforrásokat használja.
Az első fordítása ezért külön munkát igényel. A builder csak bekapcsolt `ENABLE_PYTHON_ENV` mellett létezik.
Más PC-s CMake-buildben a `fheroes2_artifact_fixture` target fordítható, majd `BASE_SAVE OUTPUT_DIRECTORY` argumentummal futtatható;
ennek futását ebben a munkaszakaszban Windowson ellenőriztük.

Az eredmény két helyi, ignorált fájl a `build/python-env-baseline/fixtures` könyvtárban:

- `artifacts-day1.sav`: Roxana és a felkínált Zom teszttárgyakat kap, köztük Távcsövet, kardot, Lightning Bolt-tekercset
  és az Anduran tárgyegyüttes három darabját, két hős között szétosztva.
- `artifacts-full-day1.sav`: Zom mind a 14 tárgyhelye foglalt, az első helyen megmaradó varázskönyvvel.

A script csak ezeket a generált másolatokat írja; az eredeti baseline és a felhasználói mentések változatlanok.
Újrageneráláskor a két tesztmásolat cserélődik. A script külön helyi APPDATA-profilt használ.
A tárgyas integrációs tesztek hiányzó helyi adatoknál jelzett skipet adnak, nem állítanak sikeres pozitív tárgypróbát.

A példa megveszi Zomot, szabályos találkozást indít, átadja a Távcsövet és a tekercset, kardot cserél éremre,
majd átadja a harmadik Anduran-darabot. A motor összeállítja a Battle Garb of Anduran tárgyat.
A példa lezárja a találkozást, és kiírja a tárgyakat, támadóértéket, felderítési távolságot és a tényleges headless runtime-adatokat.

## API és hozzáférés

Egy tárgyhely pontosan `{hero_id, slot}`. A `slot` nulla alapú index `0..13` között; a `get_state` hősönkénti
`artifacts` listájának helyeit jelenti. Üres helyen `null`; érvényes tárgynál `id`, `name`, `spell_id` szerepel.
`spell_id=0` azt jelenti, hogy a tárgy nem ad varázslatot; a tekercs saját varázslata és a varázslatot adó készlet adata megmarad.
A hős `scouting_distance` mezője a natív, aktuális felderítési távolságot adja minden résztvevőnél.

```python
source = {"hero_id": 52, "slot": 3}
target = {"hero_id": 46, "slot": 6}
result = game.transfer_artifact(source, target, token=decision["token"])
decision = result["decision"]
result = game.swap_artifacts({"hero_id": 52, "slot": 2},
                             {"hero_id": 46, "slot": 1}, token=decision["token"])
decision = result["decision"]
result = game.end_meeting(token=decision["token"])
```

- `artifact.transfer`, `params={source,target}`: pontosan egy érvényes tárgy egy konkrét üres helyre. Nincs automatikus
  üreshely-keresés, törlés vagy foglalt tárgy felülírása. Megtelt készletnél nincs szabályos átadási cél.
- `artifact.swap`, ugyanezekkel a paraméterekkel: két hely tartalmának cseréje, telt készletek között is.
  Legalább az egyik helyen legyen tárgy; azonos hely önmagával nem cserélhető. Varázskönyv egyik oldalon sem szerepelhet.
- Mindkét hős legyen aktív és a külső vezérlő saját résztvevőjéhez tartozzon. Saját hősön belüli rendezéshez nem kell találkozás.
  Két különböző hős esetén a találkozási kontextus két résztvevője és pozíciója ellenőrzött; nincs távoli vagy idegen tárgyátadás.

A csere a közös `BagArtifacts::swapArtifactSlots` műveletet használja. A normál tárgykezelő UI érintett csereágai
is ezt hívják. A teljes natív `Artifact` objektum cserélődik, a tekercs extra adatával együtt.
Hősök közötti csere után ugyanaz az `assembleArtifactSetIfPossible` fut mindkét készleten, mint a normál találkozási ablakban.
Az összeállítás miatt a végső helyek is változhatnak; a végállapotot új lekérdezésből kell olvasni.
Egy hősön belüli egyszerű rendezés nem indít találkozási készlet-összeállítást, az eredeti hősnézethez hasonlóan.

## Mellékhatások és a találkozás lezárása

A támadás, védelem, varázslat-hozzáférés és más tárgyhatások a motor saját gettereitől és későbbi szabályhívásaitól származnak.
Az átrendezés önmagában nem ad új mozgáspontot és nem fogyaszt további találkozási költséget.

A natív találkozási UI az induláskori felderítési tárgybónuszt a lezáráskori bónusszal hasonlítja össze.
Ezt a session is megőrzi az `army_meeting` kontextus `initial_scout_bonus` / `other_initial_scout_bonus` mezőiben.
A tárgy mozgatása azonnal megváltoztatja az aktuális felderítési távolságot, de a köd tényleges felderítése a találkozás végén történik.
Az ideiglenes átadás és visszaadás ezért nem fed fel több mezőt, mint a normál játék. A már felderített térképet nem ködösítjük vissza.

Az `end_meeting(token=...)` hívás `hero.end_meeting` művelet, üres paraméterekkel. Végrehajtja a nettó nyereségű
hősök natív `Scout` hívását, majd lezárja a kontextust. Nem nyit UI-t és nem fogyaszt további mozgáspontot.
Más sikeres játékművelet vagy új találkozás előtt ez automatikusan megtörténik; hibás műveletnél a lezárás és a felderítés is visszaáll.
A `session.stop` egy nyitott találkozást ugyanezen checkpointolt útvonalon lezár, ezért ilyenkor az állapotverzió is nőhet.
A `close`/reset a motorfolyamat eldobása: megőrizni vagy megvizsgálni kívánt végállapothoz előbb `end_meeting` hívandó.

Események: `artifact_transferred` / `artifacts_swapped` (`source`, `target`, az eredeti `source_artifact` és `target_artifact`,
valamint `assembled_sets`), továbbá `heroes_meeting_ended` a résztvevőkkel és `scouted_heroes` listával.
Az összeállítás értesítése esemény; nincs kötelező OK-dialógus vagy helyettünk hozott döntés.

## Ellenőrzés és határok

Hibás endpoint vagy hely: `invalid_request`; hiányzó tárgy, foglalt cél, varázskönyv, idegen/távoli hős vagy lejárt találkozás:
`illegal_action`; korábbi döntési token: `stale_decision`. Az összes művelet a közös világ/RNG/döntés-checkpointot használja.
Elutasításkor a tárgyak, köd, pénz és találkozási kontextus változatlan. A bemeneti mentések hashét a tárgyas tesztek is ellenőrzik.

Hét új valós motoros teszt ellenőrzi a tekercs varázslatát és a tárgyak megmaradását, natív bónuszok átkerülését,
Anduran-összeállítást, megtelt készletet, varázskönyv-védelmet, belső rendezést, távoli/idegen hozzáférést,
felderítés időzítését, ideiglenes átadás visszavételét és a lezárás visszaállítását hibás kérésnél.
A korai kilencakciós Gym-példa változatlan; az új műveleteket a `HeroesSession` adja. A többoldalas vezérlés továbbra is rögzített, későbbi feladat.

2026-10-29, Windows: mind a 77 Python-integrációs teszt sikeres (a hét tárgyas teszt ténylegesen lefutott, nem skipelt),
a Gymnasium ellenőrzőjével együtt. A bekapcsolt PC-s fejlesztői motor és a külön `ENABLE_PYTHON_ENV=OFF` normál
Windows-build is lefordult. A natív tesztadat-készítő és a tárgyátadási példa sikeresen futott; a builder a bemenettel
azonos kimeneti fájlt külön ellenőrzés alapján elutasítja. Más platformok SDK-fordítása és a normál GUI kézi kattintásos próbája nem történt meg.
