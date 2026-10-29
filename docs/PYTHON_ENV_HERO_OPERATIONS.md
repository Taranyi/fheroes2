# Lényfejlesztés, elbocsátás és varázskönyv Pythonból

A 8. lépés befejező része a deklarált `adventure_basic` profilon. A meglévő sereg- és tárgykezelést
négy művelet egészíti ki: teljes csapat fejlesztése, teljes csapat elbocsátása, hős önkéntes elbocsátása,
valamint varázskönyv vásárlása. A szabályokat továbbra is a natív C++ motor hajtja végre.

## Futtatható példa

Az opcionális PC-s motor fordítása és az eredeti helyi The Other Side day-1 referenciamentés előkészítése után:

```powershell
uv run --project python python python/examples/hero_operations.py
```

A példa lekéri Roxana fejlesztési lehetőségeit, felépíti a fejlesztett temetőt (1000 arany),
négy zombit fejleszt (400 arany), elbocsátja a kilenc csontvázat, és bemutatja az utolsó csapat védelmét.
Roxana kilép a várból, megvesszük Jojosht (2500 arany), veszünk neki könyvet (500 arany), majd elbocsátjuk Roxanát.
A végén az első napon 3100 arany marad; Jojosh könyvvel és a varázstoronyból megtanult varázslatokkal rendelkezik.
Nincs videó-, hang- vagy kézi input-inicializálás. A példa csak a betöltött folyamat világát módosítja, a mentést nem írja felül.

## Lekérdezés és parancsok

```python
options = game.get_army_options("hero", 52)  # Vagy "castle" és a vár azonosítója.
source = {"kind": "hero", "id": 52, "slot": 1}
result = game.upgrade_troop(source, token=decision["token"])
decision = result["decision"]
```

A `get_army_options` pontosan `{kind,id}` paramétereket vár. Nem módosít világot, RNG-t vagy döntési tokent;
aktív AI-hősök és minden vár serege is lekérdezhető, session indítása előtt is.
A válasz: `kind`, `id`, `owner`, `perspective="omniscient"`, `state_version`, `castle_id` és öt `slots` elem.
Slotonként: `occupied`, `count`, `monster_id`, `upgrade_monster_id`, `upgrade_cost`, `can_upgrade`, `can_dismiss`.
A nem fejleszthető/üres csapat ára és célazonosítója `null`; az ár a teljes csapatra vonatkozik.
A `can_upgrade` a helyet, épületet és jelenlegi pénzt is figyelembe veszi. Ezek a natív lehetőségek,
nem jelentenek jogosultságot az AI seregének módosítására.

| Python-hívás | Protokollakció és paraméterek | Szabály |
|---|---|---|
| `upgrade_troop(source, token=...)` | `army.upgrade`, `{source}` | Teljes, érvényes csapat; megfelelő fajú vár, felépített fejlesztett lakhely és teljes ár szükséges. |
| `dismiss_troop(source, token=...)` | `army.dismiss`, `{source}` | Teljes csapat törlése, visszatérítés nélkül. A hős utolsó kötelező csapata megmarad; helyőrség kiüríthető. |
| `dismiss_hero(hero_id, token=...)` | `hero.dismiss`, `{hero_id}` | Saját aktív hős, váron kívül; a pálya `NOTDISMISS` védelme érvényesül. |
| `buy_spell_book(hero_id, token=...)` | `hero.buy_spell_book`, `{hero_id}` | Saját vár tényleges látogatója, legalább első szintű varázstorony, szabad tárgyhely, elegendő pénz és még nincs könyve. |

A sereg-endpoint `{kind:"hero"|"castle",id,slot}`, `slot=0..4`. Módosításkor az aktuális külső résztvevő
saját serege/hőse szükséges. Részleges fejlesztéshez előbb külön slotba kell osztani a kívánt mennyiséget.
A teljes csapat árát ellenőrzött, 64 bites szorzás számítja a natív egységárból; a motor pénzábrázolásán túli összeget elutasítjuk.

A hős elbocsátása a meglévő `Heroes::Dismiss(0)` műveletet hívja: eltűnik a térképről és a birodalom hőslistájáról,
szabad hőssé válik, serege a natív alapállapotra áll vissza. A motor megtartja tárgyait és varázslatait;
nem adjuk át ezeket egy másik hősnek és nem jár pénzvisszatérítés. A játékvég feltételeit utána a motor ellenőrzi.
A harci menekülés/megadás ettől külön, még nem támogatott művelet.

A könyv ára a `PaymentConditions::BuySpellBook` függvényből származik (jelenleg 500 arany).
A natív `SpellBookActivate` rendezi el a tárgyhelyeket, majd a vár saját tanítófüggvénye adja a megtanulható varázslatokat.
A `get_state` minden hősénél szerepel `has_spell_book`, `can_buy_spell_book`, `spell_book_cost`,
`can_dismiss`, `dismissal_prohibited`; a lehetőségek nem módosítási jogosultságok.

## Közös szabályok és visszaállítás

A normál seregkezelő UI és az adapter ugyanazokat az új `Army` fejlesztési/elbocsátási műveleteket használja.
A normál könyvvásárlási dialógus megtartja kérdését, a közös végrehajtás külön `purchaseSpellBook` függvény.
A hősnézet önkéntes elbocsátási feltétele szintén közös; a harci kényszerű eltávolítást nem korlátozzuk vele.

Mindegyik parancs tokenes és világ/RNG-checkpointolt. Hibás típus/endpoint: `invalid_request`;
tiltott tulajdon, hely, üres slot, pénzhiány vagy más natív feltétel: `illegal_action`.
Elutasításkor világ, pénz, fog, döntés és találkozás is változatlan.
Az `army.upgrade` és `army.dismiss` megtartja az aktuális találkozást;
a két sikeres hősművelet előtte lezárja azt a meglévő natív felderítési szabállyal.
Sikeres események: `army_upgraded`, `army_dismissed`, `hero_dismissed`, `spell_book_bought`.

## Ellenőrzés és határok

Nyolc új valódi motoros teszt ellenőrzi az AI-kra is tisztán olvasó lekérdezést, hős/helyőrség fejlesztését,
pontos árat és létszámot, hely- és pénzhiányt, elbocsátási védelmeket, könyvvételt/tanulást, megtelt tárgykészletet,
pályavédett hőst és a hibák utáni változatlan világot.
A telt könyv nélküli hős és a `NOTDISMISS` eset a korábbi natív fixture builder két új mentésével készül:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File script/windows/python-env-artifact-fixture.ps1
```

A helyi, ignorált `heroes-full-day1.sav` és `heroes-protected-day1.sav` a két korábbi tárgyas mentés mellett készül.
Az eredeti mentést a builder nem módosítja; az éles API nem kap tesztadat-létrehozó parancsot.
Hiányzó tesztmentésnél az érintett teszt jelzett skipet ad.

A kilencakciós Gym-példa továbbra is a korábbi szűk mozgás/körváltás profilt adja; ezek a bővítések a `HeroesSession` API-ban érhetők el.
Valódi választások, adventure varázslás, csata, többoldalas vezérlés és a teljes Gym adapter továbbra is hátralévő munka.

2026-10-29, Windows: mind a 85 Python-integrációs teszt sikeres, a nyolc új teszttel, ténylegesen betöltött natív
tesztmentésekkel és a Gymnasium ellenőrzőjével együtt. A futtatható példa is sikeres, 3100 arannyal és video/audio nélkül.
A bekapcsolt PC-s és a külön `ENABLE_PYTHON_ENV=OFF` normál Windows-build is sikeresen lefordult.
A normál GUI kattintásos próbája és más platformok SDK-fordítása ebben a munkaszakaszban nem történt meg.
