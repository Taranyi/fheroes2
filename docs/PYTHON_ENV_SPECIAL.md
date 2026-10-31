# Speciális térképi interakciók és információs nézetek

A 9–10. bővítés folytatása. A deklarált profil most **91 térképi objektumtípust, 17 adventure és 48 harci varázslatot** tartalmaz.
Az eredeti C++ játékszabály fut; a Python az ablakos választások helyett kap döntést, illetve adatot és RGB-pillanatképet.
Az opcionális desktop build kapcsolója továbbra is `ENABLE_PYTHON_ENV`; a normál és mobil játékhoz nem kell Python vagy venv.

## Futtatható példa

A már előkészített alapmentésből a következő parancs készíti el a külön tesztmentéseket; az eredeti mentést nem módosítja:

```powershell
powershell -ExecutionPolicy Bypass -File script/windows/python-env-artifact-fixture.ps1 -ExpansionOnly
uv run --project python --cache-dir .tools/uv-cache python python/examples/special.py
```

A [példa](../python/examples/special.py) mind a nyolc speciális objektumot végigjárja, kereskedik,
szöveggel válaszol a Sphinxnek, és mind a hat View World varázslatot használja.
Az Oracle és a térképnézetek valódi képei a `build/python-env-special-views` mappába kerülnek PPM formátumban.
A példa nem igényel Gymet vagy képfeldolgozó csomagot. A mentések és a képek helyi buildtermékek.

## Sphinx: függő szöveges döntés

A kihívás elfogadása után a döntés `pending_choice.kind="sphinx.answer"`, `input_type="text"`.
A `prompt` a rejtvény szövege; a megoldások listája nem kerül ki az API-ba.

```python
choice = decision["pending_choice"]
result = game.answer_text(choice["choice_id"], "my answer", token=decision["token"])
decision = result["decision"]
```

A natív `MapSphinx::isCorrectAnswer` végzi az összevetést, a pályában megadott válaszokkal és csonkolási szabállyal.
Jó válasz esetén a natív jutalom és az egyszeri felhasználás érvényesül; hibás válasznál a hős és serege elpusztul.
A kihívás visszautasítása nem hibás válasz. Az üres szöveg beküldhető: a motor bírálja el.
A bemenet egy sor, legfeljebb 4096 UTF-8 byte, NUL/CR/LF nélkül. Hibás/stale kérés nem fogyasztja el a döntést.
Más művelet a válasz előtt nem léptetheti a világot. `session.stop` az egész kezdeményező lépést visszaállítja.

## Trading Post: helyi kereskedés

A Trading Post meglátogatása megnyit egy hőshöz és helyhez kötött kereskedési kapcsolatot:

```python
options = game.get_trading_post_options(hero_id)
quote = next(q for q in options["trades"]
             if q["resource_from"] == 64 and q["resource_to"] == 1 and q["max_lots"])
result = game.trade_at_post(hero_id, 64, 1, 1, token=decision["token"])
```

Az árak a natív Trading Post rátái, saját várpiac nélkül is. Az erőforrás-ID-k ugyanazok, mint a várpiacnál:
wood=1, mercury=2, ore=4, sulfur=8, crystal=16, gems=32, gold=64.
Minden ajánlat `sell_per_lot`, `buy_per_lot`, `max_lots` adatot ad; a mennyiség pozitív egész lot.
Az elégtelen készlet és a célkészlet túlcsordulása elutasított, részleges csere nincs.
A lekérdezés és további sikeres helyi cserék nyitva tartják a kapcsolatot; más sikeres játékművelet,
körváltás, stop vagy reset lezárja. Elutasított művelet megőrzi. A korábbi `market.trade` továbbra is a várpiac.

## Térképi események, átjárók és felderítés

| Objektum | Viselkedés |
|---|---|
| Map event | Natív színjogosultság és AI-engedély; üzenet, erőforrás, tárgy, tapasztalat és képesség; egyszeri/ismétlődő szabály. A szintlépés döntése felfüggeszthető. |
| Stone Lith | Natív, azonos típusú kijáratválasztás, RNG, mozgás és érkezési felderítés. |
| Whirlpool | Natív hajós átjárás, kijáratválasztás és csapatveszteség. |
| Hut of the Magi | Az Eye of the Magi helyek körüli natív sugarú fogfeltárás; nincs animációs várakozás. |
| Magellan's Maps | Natív megerősítés, ár, látogatási szabály és vízi térképfeltárás. |
| Oracle | Az eredeti Thieves Guild/Oracle statisztikák és natív rajzolás, minden tényleges résztvevővel. |

A Python-vezérlő és a human/AI játékszabályprofil továbbra is külön fogalom.
Egy Python által irányított, natív AI szabályprofilú oldal nem kerülheti meg az esemény computer-player tiltását.
A felsorolt események célmezőként támogatottak; egy útvonal közepén lévő eseményen az adapter nem lép át észrevétlenül.
A teleportalagutak kijáratai és a whirlpool-veszteség a motor RNG-jét használják, seedelt visszajátszással.

## Oracle és View World: adat és render

Oracle-látogatás vagy View World varázslat után:

```python
information = game.get_information_view()
frame = game.render(view=information["kind"], width=640, height=480)
# frame.pixels: RGB bytes; frame.width, frame.height
```

A `kind` értéke `oracle` vagy `world`. A nézet **rögzített pillanatkép**, nem távoli, folyamatosan frissülő felderítés:
`player_id`, `mode`, `day`, `state_version`, `snapshot=true` jelzi eredetét. Új információs nézet felülírja, reset törli.
A lekérdezés/render nem kerül újabb manába, nem léptet és nem módosít fogot vagy RNG-t.
Megfelelő megnyitott nézet nélkül `no_information_view` a válasz. A render `perspective="native_information"`.
Az általános `get_state` továbbra is minden oldal teljes állapota; a nézet adatai a natív információs szabályokat követik.

| Varázslat-ID | Natív mód | Feltárt kategória |
|---|---|---|
| 49 | 2 | Mines |
| 50 | 3 | Resources |
| 51 | 1 | Artifacts |
| 52 | 5 | Towns |
| 53 | 4 | Heroes |
| 54 | 6 | All |

A `world` adataiban `width`, `height`, `tiles` és `markers` található.
A `tiles` csak ismert terepet tartalmaz, kivéve a View All teljes térképét.
A `markers` a már látható, illetve az adott varázslat által feltárt kategóriákat mutatja:
`kind`, `index`, `object_type`, `owner`, `resource_id`. A View Artifacts nem árulja el az artifact pontos típusát.
A natív térképkép ugyanazt a gyorsítótárat és ikonrajzolást használja, mint az ablakos View World, eredetileg 4 pixel/mező felbontással.

Az `oracle.players` résztvevőnként tartalmazza a város/vár/hős számot, aranyat, fa+ércet, ritka erőforrásösszeget,
obeliszket, tárgyszámot, seregerőt, aranybevételt, legjobb hőst és képességeit, legerősebb szörnyet, human flaget és személyiséget.
A seregerő egészre alakított natív érték. A natív kép az eredeti rangsort és statisztikaképernyőt rajzolja.

## Gym

A `Discrete` akciótérbe a korábbi kategóriák után került a `choice.answer_text` és `trading_post.trade`.
A Sphinx szabad szövege véges Gym-választékkal használható:

```python
env = HeroesEnv(executable=exe, save=save, sphinx_answers=("human", "other guess"))
obs, info = env.reset(seed=123)
for _ in range(10000):
    action = env.action_space.sample(mask=obs["action_mask"])
    obs, reward, terminated, truncated, info = env.step(action)
    if terminated or truncated:
        obs, info = env.reset()
```

A helyes válasz nincs automatikusan kikeresve. A konfigurált szólista mellett mindig szerepel az üres válasz;
alapból csak ez van, ami tipikusan a rejtvény elvesztését jelenti. Generált szöveghez a `HeroesSession.answer_text` használható.
Az egyszerű Gym-sampling használja a maszkot. Az új mezők miatt a korábbi modell bemenetét frissíteni kell.

| Megfigyelés | Méret/alapérték |
|---|---|
| `actions` | 8192×31; új utolsó oszlop `text_id` |
| `text`, `text_mask` | 4096 byte; a függő rejtvény UTF-8 promptja és hossza maszkkal |
| `action_text` | 8192×256 uint8; konfigurált válasz UTF-8 byte-jai, nullával kitöltve |
| `view` | 4 int: kind (0/1/2), player_id, mode, day |
| `view_tiles` | 20736×3: terrain_image, terrain_flags, ismert bit |
| `view_markers` | 20736×3: kategória-bitmaszk (hero/town/mine/resource/artifact), owner, resource_id |
| `oracle`, `oracle_mask` | 6×18, illetve 6; player_id, towns, castles, heroes, gold, wood_ore, rare_resources, obelisks, artifacts, army_strength, income, best_hero_id, attack, defense, power, knowledge, best_monster_id, is_human |

Azonos mezőn több marker esetén a kategória-bitmaszk egyesül, a tulajdonos/erőforrás a legutóbbi marker értéke;
a teljes, veszteségmentes lista a session adatában érhető el.
A `max_text_bytes`/`max_answer_bytes` konstruktorparaméter rögzített kapacitást ad; az összes válaszbuffer legfeljebb 16 MiB.
A space epizódon belül nem változik, túlcsorduláskor explicit profilhiba érkezik.

## Ellenőrzés és fennmaradó munka

A `python/tests/test_special.py` a valódi mentéseket és motort használja: helyes/hibás/elhárított Sphinx,
stale és hibás bemenet, stop-visszaállítás, natív kereskedelmi árak, események jogosultsága és ismétlése,
seedelt átjárás és veszteség, fogfeltárás, mind a hat információs varázslat, Oracle mindkét oldala és a Gym új mezői.

2026-10-31, Windows: **193/193 teljes Python/Gym teszt sikeres**; a **13/13 speciális teszt Debug buildben is sikeres**,
bekapcsolt C++ belső ellenőrzésekkel. Az opcionális desktop és a normál `ENABLE_PYTHON_ENV=OFF` build is lefordult.
A teljes bemutató ablak és hang nélkül lefutott, az Oracle és View World képei vizuálisan is ellenőrizve.
A gyökérben az opcionális Release futtatható maradt. Más platform SDK-buildje ebben a munkaszakaszban nem futott.

A felsorolt speciális esetek elkészültek. A további feladatok:

1. Konfigurálható önálló battle-only indítás/reset, kalandtérképes előzmény nélkül.
2. Szélesebb pálya-, terep-, ostrom- és hajós kombinációs ellenőrzések.
3. Linux/macOS és mobil SDK-buildek ellenőrzése.
4. Nagyobb léptékű RL-profilozás és teljesítményjavítás; külön bővítés a láthatóságra szűrt observation és a több agentes Gym-wrapper.
