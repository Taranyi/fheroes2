# Gym/reset gyorsítás és párhuzamos PPO

A teljes `HeroesEnv` továbbra is ugyanazt a numerikus világmegfigyelést és teljes, módosítható másolatú
`info.state` / `info.actions` adatot adja. A C++ motor és a játékszabályok nem változtak.
Az új `BattleEnv` külön, kifejezetten csatatanításhoz választott kisebb megfigyelési szerződés.
A folyamat újrafelhasználása külön bekapcsolható, alapból továbbra is friss motorfolyamat indul.

## Mi változott?

### Teljes Gym-profil, adatvesztés nélkül

- A jelöltek felsorolása előtti teljes második kódolás helyett olcsó térkép-/entitáskorlát-ellenőrzés fut.
  A végső kódolás minden korábbi séma- és kapacitásellenőrzést megtart.
- A kizárólag natív JSON-ból és saját parancsszótárakból álló `info` fák másolása nem használ általános Python-objektum/memo diszpécsert.
  A dict/list tartalom új tárhelyre kerül, az immutábilis JSON-skalárok megoszthatók. Nem publikus belső állapotot adunk vissza másolat helyett.
- A visszaadott megfigyelést továbbra is külön NumPy-tömbök védik; a kliens módosításai nem változtatják a következő motorállapotot.

### Külön csata-Gym profil

```python
from fheroes2_env.battle_env import BattleEnv

env = BattleEnv(executable=executable, battle_config=config, reuse_process=True)
obs, info = env.reset(seed=123)
action = env.action_space.sample(mask=obs['action_mask'])
obs, reward, terminated, truncated, info = env.step(action)
world = env.world_snapshot()  # teljes natív világ és AI-adatok, olvasó kérésre
env.close()
```

A `BattleEnv` nyolc numerikus mezőt ad: `battle`, `battle_units`, `battle_unit_mask`, `battle_effects`,
`battle_board`, `battle_commanders`, `actions`, `action_mask`. Mindkét sereg és parancsnok adata megmarad.
A mezők alakja/típusa/értéke megegyezik a megfelelő teljes Gym-mezővel; a natív akciók és jutalom is ugyanazok.
A kapacitás fölötti jelölteket nem vágjuk le, explicit profilhiba érkezik.

Élő döntésnél a már visszakapott natív `decision.battle` adatot kódoljuk, nem kérjük le újra az egész világot.
Terminális állapotnál külön natív világkérésből vesszük az eredményt, beleértve a natív körlimit megkülönböztetését.
A kisebb `info` tartalmazza a fázist, résztvevőt, seedet, lépésszámot, elfogadást/elutasítást, eseményeket és `battle_result`-ot.
Nem tartalmaz teljes `state` vagy strukturált `actions` másolatot. Az egész világ továbbra is elérhető `world_snapshot()`-tal,
beleértve az AI és köd mögötti adatokat; a kérés nem lépteti a játékot.
Ez külön adatprofil, nem a teljes világadatok költség nélküli visszaadása.

Az összetett RL-task továbbra is pontosan ugyanazt a **512 × 97** jelöltjellemzőt, akciómaszkot és jutalmat képezi belőle.
A modell bemenetének egyezése külön hash-ellenőrzést kap a benchmarkban.

### Opcionális, azonos folyamatban végzett csata-reset

`HeroesSession.reset(..., reuse_process=True)`, illetve `HeroesEnv(..., reuse_process=True)` / `BattleEnv(...)` használható.
Ez csak önálló `battle_config` epizódokhoz engedélyezett. Kalandtérkép/mentés esetén nem kapcsoljuk be csendben.

Egészséges csatafolyamatban előbb a régi aréna szabályos `session.stop` megszakítása/visszabontása történik,
utána a meglévő natív `configure_battle` újraépíti a kis csatakörnyezetet, törli az AI-világcache-t és újraseedeli az RNG-t.
Az assetek és motorfolyamat megmaradhatnak. Halott/lezárt folyamatnál friss indulás történik.
Hibás konfiguráció vagy protokollhiba nem válik hamis győzelemmé/vereséggé; kivétel marad, a session eltakarítódik.

A PID és a `session_id` újrafelhasználáskor ugyanaz lehet, az epizód-/döntésazonosítók változnak.
Régi token ilyenkor `stale_decision` hibát ad; a hagyományos új folyamat továbbra is `wrong_session` hibát.
A reset összes gameplay-adatát ellenőrizzük; a protokoll állapotverzióját és a függő választás monoton sorszámát
a szemantikai hash normalizálja, a tényleges API-válasz azonban ezeket is megőrzi.

## Párhuzamos tanítás

A [battle_vector.py](../python/examples/battle_vector.py) ugyanazt az összetett csatafeladatot és 32 rejtett egységes PPO-hálózatot használja.
Egy résztvevőnél `DummyVecEnv`, többnél **`SubprocVecEnv(start_method='spawn')`** működik.
Minden worker saját Python-folyamatot, saját natív motorfolyamatot és saját APPDATA/XDG tesztprofilt kap.
A [MaskablePPO követelménye](https://sb3-contrib.readthedocs.io/en/master/modules/ppo_mask.html) szerint
az `action_masks()` maga a worker env metódusa, nem a szülőfolyamatban működő maszkoló.
A [Windows/macOS-safe spawn belépési pontot](https://stable-baselines3.readthedocs.io/en/master/guide/vec_envs.html) a példák külön `__main__` ágban indítják.

Ez egy közös policy párhuzamos adatgyűjtése és tanítása, nem több egymástól független agent önálló tanulása.
A CPU Torch-szálszám 1; a worker diagnosztika számlálókat és növekményes konfigurációhash-t tart meg, nem végtelen epizódlistát.
Lezáráskor a natív folyamatok visszatérési kódját is visszakérjük, majd a workerfolyamatokat csatlakoztatjuk.

```powershell
uv run --project python --cache-dir .tools/uv-cache --extra battle-rl --locked python python/examples/battle_vector.py --workers 4 --steps 8192 --output build/python-env-performance/new-training
# Egy környezet / régi teljes adatprofil / friss folyamat minden resetnél:
uv run --project python --cache-dir .tools/uv-cache --extra battle-rl --locked python python/examples/battle_vector.py --workers 1 --profile full --fresh --steps 8192 --output build/python-env-performance/new-full-training
```

Minden konfiguráció összesen ugyanannyi natív Python-döntést kap.
Az összesített PPO rollout-batch **256**: egy envnél 256, kettőnél 128, négynél 64 döntés/workerenként.
A minibatch 64, az epoch 6, a learning rate 0,001, gamma 0,99, entrópia 0,01; azonos számú hálózatfrissítés történik.
A bevezető tanítás névleges globális 2048-as keretét is elosztjuk a workerek között.
Több worker eltérő seedfolyamot és eltérő GAE-időablakot jelent: a párhuzamos súlyok nem szükségszerűen egyeznek az egyenv-súlyokkal.
Az egyenvs régi és gyors út azonos seednél viszont bitpontos policy- és resetfolyam-egyezést ellenőriz.

### Opcionális számítás a kitöltő jelöltek nélkül

Az első tanításmérésben a párhuzamosítás kisebb javulást adott, mint a külön Gym-benchmark.
Ezért külön kipróbáltuk az actor kitöltő sorainak kihagyását: eredetileg minden batchben mind az 512 jelöltet feldolgozta.
A külön `--packed` kapcsoló a változatlan közös Linear/Tanh actorban csak a valódi, bias=1 sorokat számolja ki,
majd az eredeti indexekre helyezi vissza a logitokat. A critic, paraméterszám, maszkos eloszlás, PPO-jutalom és frissítésszám változatlan.
Ez az adott, soronként független jelöltpontozó optimalizálása; nem általános BatchNorm/attention-hálózat átalakítása.

A teszt változó maszkokkal ellenőrzi a valószínűség-, érték- és paramétergradiens-egyezést (float32 toleranciával).
A különböző mátrixméret miatt lebegőpontos kerekítési különbség lehet, így a packed tanításra nem állítunk bitpontos súlyazonosságot.
A kapcsoló nélküli út megőrzi az ilyen kontrollmérés lehetőségét.

```powershell
uv run --project python --cache-dir .tools/uv-cache --extra battle-rl --locked python python/examples/battle_vector.py --packed --workers 4 --steps 8192 --output build/python-env-performance/new-packed-training
```

## Mérés, egyezés és reprodukálás

A [run_performance.py](../python/examples/run_performance.py) a gyorsítás előtti **`f3d8a3405`** commit Python-csomagját
egy figyelmen kívül hagyott helyi könyvtárba másolja `git show`-val. Nem váltja át és nem írja felül a munkafát.
Ugyanazt a natív binárist és ugyanazokat a mai feladat-/modellfüggvényeket használja minden backenddel.
Az eredmények tartalmazzák a ténylegesen importált csomag elérési útját és fájlujjlenyomatait.

```powershell
uv run --project python --cache-dir .tools/uv-cache --extra battle-rl --locked python python/examples/run_performance.py --output build/python-env-performance/new-run --repeats 5 --train-steps 8192
# Packed actor külön 1/2/4-worker összevetésével is:
uv run --project python --cache-dir .tools/uv-cache --extra battle-rl --locked python python/examples/run_performance.py --output build/python-env-performance/new-complete-run --repeats 5 --train-steps 8192 --packed-comparison
```

Öt változat: régi teljes csomag; gyorsított teljes/friss; gyorsított teljes/újrafelhasznált;
kis csata/friss; kis csata/újrafelhasznált. Mindegyik ugyanazt a nyolc csatát hajtja végre öt mért ismétlésben.
A filesystem-/allokátor-warmup és a részletes megfigyeléshash-ellenőrzés a mért körök előtt fut.
Minden mért ismétlésben egyeznie kell a natív akciósornak, jutalomsornak és eredménynek.
A külön egyezési kör ellenőrzi a csataösszesítőket, a policy bemenetét, teljes profilnál az összes numerikus mezőt és a teljes szemantikai világállapotot is.

A `step` és `reset` saját ideje külön szerepel. Az ismétlés teljes falaideje tartalmazza a resetet, a vezérlő választását és a lépéseket is;
az ezen alapuló lépés/s az öt ismétlés mediánja. Nem renderelünk.

Utána négy 8192-döntéses tanítás fut: régi egyenv, gyors egyenv, gyors két- és négyenv.
Külön szerepel az env/modell indulásának, `learn()`-nek és lezárásnak az ideje.
Az indulási mérés a szülő Python-importok után kezdődik, a spawnolt workerek indulását viszont tartalmazza.
Az értékelés és ZIP-mentés nincs a tanítási időbe számolva. A kiértékelés a korábbi, teljes Gym-adapteren futó 24 validációs eset;
a végső teszt/OOD-készletet ehhez a teljesítményhangoláshoz nem használjuk.
A tanítási sebesség itt az egész PPO-adatgyűjtés és hálózatfrissítés költsége, nem a tiszta motor lépés/s értéke.

Önálló benchmarkok: [benchmark_gym.py](../python/examples/benchmark_gym.py),
illetve [benchmark_adventure.py](../python/examples/benchmark_adventure.py) egy meglévő, olvasásra használt adventure-mentésen.
Az adventure-mérés a teljes, alapkapacitású világmegfigyelést és három maszkolt első akciót ellenőriz resetenként;
a bemeneti mentés SHA256-a futás előtt/után egyezik.

Minden modell, mérés, ábra és esetleges média a `build/` fában marad, GitHubra nem kerül.
Nincs új függőség, C++-módosítás vagy mobil build-opció.

## Tényleges eredmények

Windows 11, 16 logikai CPU, CPU Torch, egy Torch-szál; Python 3.14.7, Gymnasium 1.4.0,
Torch 2.15.0, SB3/sb3-contrib 2.9.2. Az összevetések egymás után futottak, tesztcsomag nélkül.
Ezek ezen a gépen mért értékek, nem általános platformgaranciák. A nyolc rögzített csata ismétlésenként 113 döntés.

| Adatprofil / reset | Step (ms) | Reset (ms) | Lépés/s, resetekkel és vezérlővel |
|---|---:|---:|---:|
| Régi teljes / friss folyamat | 34,25 | 91,01 | 24,35 |
| Gyorsított teljes / friss folyamat | 22,09 | 72,51 | 36,33 |
| Gyorsított teljes / újrafelhasznált | 34,71 | 37,14 | 26,61 |
| Kis csata / friss folyamat | 3,23 | 50,48 | 143,45 |
| Kis csata / újrafelhasznált | 2,74 | 4,00 | 321,79 |

Az értékek az öt ismétlés körönkénti átlagának mediánjai; a throughput az öt teljes kör sebességének mediánja.
A teljes API adatvesztés nélküli gyorsulása **1,49×**. A külön csataprofil újrafelhasznált folyamattal
**13,22×** teljes feladatsebességet, **22,77×** resetgyorsulást adott a régi teljes profilhoz képest.
Utóbbihoz kisebb API-válasz tartozik, miközben a tanítást vezérlő összes jellemző megmarad.
A teljes profilban a folyamat újrafelhasználása önmagában nem adott jobb összteljesítményt a gyorsított friss indulásnál;
nem kapcsoljuk be alapértelmezésként.

| PPO-konfiguráció | `learn()` (s) | Indulás + tanítás + lezárás (s) | Validációs győzelem |
|---|---:|---:|---:|
| Régi teljes, 1 env | 440,53 | 442,37 | 22/24 |
| Kis csata + reuse, 1 env | 101,66 | 103,98 | 22/24 |
| Kis csata + reuse, 2 env | 103,74 | 109,76 | 23/24 |
| Kis csata + reuse, 4 env | 82,27 | 88,40 | 22/24 |
| Ugyanez packed actorral, 1 env | 106,43 | 108,09 | 22/24 |
| Ugyanez packed actorral, 2 env | 73,45 | 79,21 | 23/24 |
| Ugyanez packed actorral, 4 env | **53,83** | **59,70** | 22/24 |

Minden sor 8192 döntés és azonos méretű hálózat: 32 rollout × 6 epoch = 192 PPO-epoch,
768 minibatch-optimalizálás. A JSON `ppo_updates` mezője az SB3 `_n_updates` epoch-számlálója.
Egy seed futott konfigurációnként:
ez sebességmérés és minőségi ellenőrzés, nem statisztikai bizonyíték jobb stratégiára.
A korábbi és a gyorsított, nem packed **egyenv-tanítás végső súlyhash-e és teljes resetfolyam-hash-e bitpontosan egyezik**.
A packed négyenv-változat **8,18×** gyorsabb tanítási időben a réginél, indulással/lezárással együtt **7,41×**.
A párhuzamosítás saját nyeresége packed 1→4 env esetén **1,98×**; az egyszálas packed itt kissé lassabb,
a nem packed kétworker-változat pedig nem gyorsabb az egyworkeresnél. Nyolc worker nincs teljes futással bemérve.
Az eltérő worker-számok nem bitazonos tanítások: azonos költségkeretű, eltérő adatfolyamú PPO-futások.

Kiegészítő adventure-kontroll: ugyanaz a mentés, három reset × három döntés, alapméretű teljes Gym-profil.
Az összes numerikus mező és szemantikai világállapot egyezik; a bemeneti mentés változatlan.
Step **57,51→45,29 ms** (1,27×), reset **130,68→118,98 ms** (1,10×).
Ez egy rövid mentéses kontroll, nem teljes adventure-végigjátszás.

Helyi eredmények a `build/python-env-performance/final/` alatt:

- `report.json`: az öt Gym-változat és négy eredeti tanítás teljes, sikeres futtatójelentése.
- `train_packed_1/2/4/report.json`: a három későbbi packed tanítás; `supplemental-report.json`: ellenőrzött összevonás,
  adventure-egyezés, csomag-/futtatóhash-ek és sikeres folyamatlezárások.
- `executed-battle_vector.py`: az első négy tanításkor ténylegesen használt futtató másolata;
  a packed kapcsoló ezután került hozzá, az alapértelmezett algoritmus változtatása nélkül.
- `performance.png`: a [performance_plot.py](../python/examples/performance_plot.py) által rajzolt összehasonlítás;
  az API-ábrán a hibasáv az öt kör minimuma–maximuma, nem konfidenciaintervallum.
- A tanítási mappákban a helyi modellek és az eredeti teljes adapteren készült validációs részletek.

```powershell
uv run --project python --cache-dir .tools/uv-cache --extra battle-rl --locked --with matplotlib python python/examples/performance_plot.py build/python-env-performance/final
```

### Regressziós ellenőrzés

A teljes csomag **243/243 sikeres tesztet** adott 214,3 másodperc alatt, kihagyás nélkül.
A helyi napló `build/python-env-performance-full-tests-unrestricted.log`.
Az első, megszakított futásnál a korlátozott tesztfolyamat ideiglenes mappájába nem tudott képet írni a natív motor;
a teljes újrafuttatás megfelelő hozzáféréssel sikeres volt, kódváltoztatás nélkül.

Az új ellenőrzések valódi motorfolyamatokkal futnak: négy csatakörnyezet teljes/kis profiljának jellemző-,
jutalom- és eredményegyezése; teljes világmásolat izolációja; élő csata megszakítása/resetje;
régi token elutasítása; megölt folyamat helyreállítása; maszkolt padding és kapacitáshiba;
teljes világ read-only lekérése; hivatalos Gymnasium checker; tényleges kétworker-PPO és folyamatlezárás.
A packed policy külön tesztje a maszkolt valószínűségeket, criticértékeket és paramétergradienseket hasonlítja össze.

## Teljes fennmaradó sorrend

3. [Linux/macOS és mobil SDK-buildellenőrzés](PYTHON_ENV_PLATFORMS.md) — a következő munkaszakasz eredményei külön dokumentumban.
4. Kiválasztott normál adventure-pályák végigjátszásának ellenőrzése és az elakadások javítása.
5. Adventure RL: megfigyelés, jutalom, tanítás, kiértékelés és helyi videók.
6. Kampánykezelés: továbbhaladás, átvitt hősök/jutalmak, kampányválasztások.
7. Igény szerint korlátozott láthatóság, több agentes Gym-wrapper és self-play.
8. Platformonkénti telepíthető Python-csomagok és automatikus motorkeresés (`pip install`).
