# Csata-kombinációk és stressztesztek

A [konfigurálható önálló csataszimulátor](PYTHON_ENV_STANDALONE_BATTLE.md) nagyobb ellenőrző készlete.
A tesztek valódi natív csatákat futtatnak, mentés és kalandtérképes fixture nélkül.
Az ellenőrző futtató a [battle_stress.py](../python/examples/battle_stress.py); kizárólag a standard Python-könyvtárat és a session API-t használja.
A rövid regressziós készlet a [test_battle_stress.py](../python/tests/test_battle_stress.py), a normál unittest discover része.

## Reprodukálás

Gyors, helyi ellenőrzés, már lefordított env motorral és játékadatokkal:

```powershell
uv run --project python --cache-dir .tools/uv-cache python python/examples/battle_stress.py --profile quick
```

Teljes Release futás:

```powershell
uv run --project python --cache-dir .tools/uv-cache python python/examples/battle_stress.py --profile full --build-label release --executable build/windows-local/fheroes2.exe --workers 4 --output build/python-env-battle-stress/release.full.json --summary docs/python_env/battle-stress.windows.2026-10-31.release.json
```

Debug futásnál a Debug bináris és a toolchain futtatókörnyezete kell. A helyi Windows toolchainnél:

```powershell
$env:PATH = "$(Join-Path $PWD '.tools/msys64/ucrt64/bin');$env:PATH"
uv run --project python --cache-dir .tools/uv-cache python python/examples/battle_stress.py --profile full --build-label debug --executable build/windows-debug/fheroes2.exe --workers 2 --output build/python-env-battle-stress/debug.full.json --summary docs/python_env/battle-stress.windows.2026-10-31.debug.json
```

Kiválasztható szakasz: `--section matrix|probes|agents|replay|hot|resets|parallel`.
Egyetlen eset például `--profile full --case spell/water/32` vagy `--case siege/swamp/wizard/7/0`.
Az összes esetnek stabil, seedet és konfigurációt azonosító neve van; a jelentés hibánál a teljes konfigurációt is eltárolja.
Nem hagyjuk ki a natív hibákat vagy időtúllépést: a jelentés `passed=false`, a parancs kilépési kódja nem nulla.
A teszt szándékos natív körlimitjét a `result.truncated` külön jelzi.

## Teljes lefedettségi terv

| Szakasz | Futtatott ellenőrzés |
|---|---|
| Terep/sereg | 9 terep × 8 seregprofil × 3 seed = **216 csata** |
| Ostrom | 8 szárazföldi terep × 6 várfaj × 8 oldaltorony/árok kombináció × 2 sereg/védőprofil = **768 csata** |
| Szélső értékek | Szárazföld, ostrom és hajó × 4 létszámpár (1 vagy 100000 lény), 99-es alapképességekkel = **12 csata** |
| Varázslatok | Mind a 48 harci varázslat szárazföldön, ostromban és hajón = **144 próba** |
| Python–AI | Mind a 9 terepen és a 6 várfajnál mindkét Python-oldal, plusz 12 hős nélküli ostrompróba = **42 csata** |
| Visszajátszás | 24 kiválasztott mátrixeset + 6 varázslatos eset, új folyamatban, ugyanabban a folyamatban és rendereléssel = **90 csata** |
| Hosszabb folyamat | **24 bemelegítő + 200 mért csata**, motorfolyamat-csere nélkül |
| Reset/helyreállítás | **100 ciklus**, ciklusonként két indulás, függő/stop/befejezett/bezárt/szándékosan leállított folyamatból |
| Párhuzamosság | Worker-enként 12 csata; azonos seednél azonos eredmény, más session tokenjének elutasítása |

A seregprofilok közelharci, lövész, repülő/széles, élőhalott, elemental, immunitásos,
hősös/hős nélküli és öt sereghelyet használó felállásokat tartalmaznak.
A natív morál/szerencse, másodlagos képességek, tárgyak, vegyes seregek, üres sereghelyek és formációk is szerepelnek.
Az ostromokban van védekező hős, kapitány és parancsnok nélküli helyőrség; a Knight erődítését is variáljuk.
A Python–AI próbák a human/AI szabályprofilt külön változtatják a vezérlőtől.

A 144 varázslatpróba **142 pozitív végrehajtás és két negatív Earthquake-próba**:
Earthquake csak ostromban jelenhet meg. Minden más varázslatot tényleges Python-paranccsal választunk ki, nem csak könyvben szerepeltetünk.
Az ellenoldali Python-policy sérülést és buffokat is előállít a gyógyítás/feltámasztás/dispel vizsgálatához.
Az azonos körben visszaadott döntésnél ellenőrizzük a varázslat pontos manaelszámolását.
A beépített AI csatáiban megadott könyvek lefedettségét nem állítjuk be az AI által biztosan végrehajtott varázslatok számának.

## Mit ellenőrzünk?

- Az aréna 11×9 mezős, a UID-k egyediek, az élő csapat feje/farka egyezik a táblával.
- A csapatok létszáma, HP-ja és lövése nem negatív, az élő csapatnak van létszáma és HP-ja.
- A felkínált akció-ID-k folytonosak, támadás és lövés célpontja nem lehet a cselekvő egység saját maga.
- A natív győzelmi flag, a jelentett győztes és a résztvevő jutalomnézőpontja egyezik.
- Körlimitnél nincs hamis győztes; a megfelelő natív körhatáron állunk meg.
- A render nem változtatja meg az állapotot vagy a függő döntést, és a renderes visszajátszás ugyanazt az eredményt adja.
- Visszajátszásnál a teljes szemantikai állapot és Python-döntéssor hash-e is egyezik, nem csupán a győztes.
- A natív human/AI flag nem változik a vezérlő hozzárendelése miatt.
- Nincs video/audio vagy interaktív bemenet, és nem keletkezik váratlan profilfájl.
- A folyamatok rendesen lezárulnak. A szándékos leállításokat külön számoljuk a váratlan összeomlástól.

A szemantikai hash kihagyja a session verziószámlálóját és a végkép megőrzésének konfigurációs flagjét;
ezek a friss és ugyanabban a folyamatban újrakonfigurált futás között szándékosan különbözhetnek.
Nem hagyjuk ki a harci egységeket, seregeket, manát, fogot, pénzt vagy eredményt.

## Erőforrásmérés és korlátok

A hosszabb futás egyetlen natív folyamatot használ, ezért a reset nem fedheti el az aréna és a hozzá kapcsolódó erőforrások növekedését.
A kiválasztott kép-/AI-cache-eket előbb rendereléssel bemelegítjük, majd a mért 200 csata alatt is rendszeresen kérünk képet.
Windows alatt a saját tesztfolyamat privát memóriáját, working setjét és handle-számát olvassuk;
Linuxhoz `/proc`-alapú olvasás van, más rendszernél a hiányzó mérés explicit jelölést kap.

A jelenlegi elfogadási határ **legfeljebb 64 MiB privátmemória-növekedés és +4 handle** a bemelegítés után.
A jelentés a kiinduló/végső értéket és a köztes mintákat is tartalmazza. Ez véges, körülhatárolt növekedésvizsgálat;
nem sanitizer-vizsgálat, és nem állítja, hogy tetszőlegesen hosszú futásban minden lehetséges szivárgás kizárt.
A tesztidők a helyi, párhuzamos ellenőrzés idejét mutatják; nem nagy léptékű RL-throughput mérések.

## Talált és javított regressziók

A kezdeti Debug futásban a `spell/grass/32`, `spell/siege/32` és `spell/water/32` eset a
`battle_troop.cpp` `distance > 0` ellenőrzésén állt meg. A 32-es varázslat a Hypnotize.
A hipnotizált egység irányító színe különbözik az eredeti sereg színétől, ezért a Python-adapter szín szerinti szűrése
önmagát is célpontként adhatta vissza. Release-ben ez nem okozott assertion-leállást, de hibás akciót engedett a listába.

A `python_env_battle.cpp` most azonosság szerint is kizárja a cselekvő egységet a támadási célpontok közül.
A natív sebzés, célpontszabály, Hypnotize hatás és normál játékút változatlan; a módosítás az opcionális env adapterében van.
A három reprodukció a folyamatos regressziós teszt része, és a stresszfuttató minden döntésben tiltja az önmagára célzó támadást.

A `agent/necromancer/1` és `/2` futás egy másik, Release-ben is összeomló helyzetet mutatott:
a hős nélküli ostromló AI-elemzése az `ai_battle.cpp`-ben hőst feltételezett a várfalon át lövés büntetésének becslésénél.
Parancsnok nélkül nincs ilyen tárgy- vagy Archery-bónusz, ezért a becslés most ezt az esetet is kezeli.
A hősös támadó meglévő értékelése megmarad. A hős nélküli felállást nem tiltottuk le;
mind a hat várfajhoz, Python támadóval és Python védővel is hozzáadtuk a regressziós készlethez.

## Jelentések

A verziózott, tömör összegzések a `docs/python_env` könyvtárban vannak.
A részletes helyi JSON minden esetről külön nyugtát tartalmaz, alapból a figyelmen kívül hagyott `build/python-env-battle-stress` mappában.
A tömör jelentés megőrzi a teljes jelentés és az esetnyugták kanonikus SHA-256 hash-ét.
Rögzítjük a natív források, a futtatható, a Python-futtató és a játékadatok hash-ét is.
A Git-commit a mérés kezdeti állapotát jelöli; a `worktree_dirty` és a fájlhash-ek jelzik a még nem commitolt javítást/futtatót.

Release és Debug szemantikai összehasonlítása, új csatafuttatás nélkül:

```powershell
uv run --project python --cache-dir .tools/uv-cache python python/examples/battle_stress.py --compare-reports build/python-env-battle-stress/release.full.json build/python-env-battle-stress/debug.full.json --output docs/python_env/battle-stress.windows.2026-10-31.comparison.json
```

Az összehasonlítás csak két sikeres, azonos natív forrást és játékadatot használó jelentést fogad el.
Mátrix, varázslat, Python–AI és replay esetenként hasonlítjuk az állapotot, a döntéssort és az eredményt.
A `matrix_manifest_coverage` a generált mátrix tervét mutatja; a ténylegesen lefutott szakaszokat és darabszámokat a `sections` adja.
Egyetlen kiválasztott esetnél külön `selected_case_coverage` szerepel.

## Rögzített Windows-eredmény, 2026-10-31

| Ellenőrzés | Release | Debug |
|---|---:|---:|
| Mátrix / varázslat / Python–AI | 996 / 144 / 42, mind sikeres | 996 / 144 / 42, mind sikeres |
| Replay | 30 összehasonlítás, 90 csata | 30 összehasonlítás, 90 csata |
| Ugyanabban a folyamatban | 24 bemelegítő + 200 mért csata | 24 bemelegítő + 200 mért csata |
| Reset/helyreállítás | 100 ciklus, 200 indulás | 100 ciklus, 200 indulás |
| Párhuzamos csaták | 4×12 = 48 | 2×12 = 24 |
| Csataindítás összesen | **1744** | **1720** |
| Privátmemória-változás a mért folyamat végén | −1,23 MiB | +2,44 MiB |
| Legnagyobb mintázott privátmemória-többlet | +2,08 MiB | +2,73 MiB |
| Végső handle-változás | **0** | **0** |

A 3464 indulás között a resetpróbák szándékosan megszakított csatái is szerepelnek; nem mind teljesen végigjátszott csata.
A resetpróbák buildenként 20 saját natív folyamatot szándékosan leállítanak, és ellenőrzik a helyreállítást.
A végső mátrix/varázslat/agent futásokban nem volt váratlan natív hiba vagy kihagyott eset.

A külön Release–Debug összehasonlítás **1212 esetben nulla eltérést** talált a szemantikai állapotban,
Python-döntéssorban és a jelentett eredményben. A natív Debug ellenőrzések bekapcsolva maradtak.
A normál **218/218 Python/Gym teszt** sikeres; az új, csoportosított **10/10 regressziós teszt Debug módban is sikeres**.
A normál `ENABLE_PYTHON_ENV=OFF` Windows build lefordult, a gyökérben az opcionális Release futtatható maradt.

- [Release összegzés](python_env/battle-stress.windows.2026-10-31.release.json)
- [Debug összegzés](python_env/battle-stress.windows.2026-10-31.debug.json)
- [Buildenkénti szemantikai összehasonlítás](python_env/battle-stress.windows.2026-10-31.comparison.json)

## Ami továbbra is hátravan

1. Linux/macOS és mobil SDK-buildek, illetve ottani tényleges futásellenőrzés.
2. Nagyobb léptékű RL-profilozás és az eredmény alapján teljesítményjavítás.
3. Igény szerint láthatóságra szűrt observation és több agentes Gym-wrapper.

A kombinációs/stressztesztelés reprodukálható kerete és a fenti Windows mátrix elkészült.
További speciális kombinációkat új regresszió vagy új motorfunkció indokolhat; a tesztek nem jelentenek minden lehetséges sereg/seed kimerítő bejárását.
