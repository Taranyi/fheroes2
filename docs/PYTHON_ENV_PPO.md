# Stable-Baselines3 csata-RL, saját jutalom és helyi videók

A [battle_ppo.py](../python/examples/battle_ppo.py) a meglévő, változatlan `HeroesEnv` köré épített
opcionális tanítási példa. Stable-Baselines3 + sb3-contrib **MaskablePPO**, PyTorch CPU és natív headless csaták.
A könyvtár [hivatalos maszkos PPO-szerződését](https://sb3-contrib.readthedocs.io/en/master/modules/ppo_mask.html)
használjuk: az env `action_masks()` függvényt ad, és kiértékeléskor is átadjuk a maszkot a `predict` hívásnak.

A C++ játékszabály, a base Python-csomag és az eredeti Gym-jutalom változatlan.
A `battle-rl` extra csak az ezt kifejezetten kérő Python-környezetet bővíti; a normál és mobil játékhoz nem kell.
A korábbi [NumPy-kísérlet](PYTHON_ENV_FIRST_RL.md) külön, egyszerűbb, egycsapatos referencia marad.

Következő, nehezebb kísérlet: [háromcsapatos seregek, hét varázslat, támadó/védő ostrom és új seregeken tesztelés](PYTHON_ENV_ADVANCED_RL.md).

## Tényleges Windows-eredmény, 2026-10-31

Négy futás készült: két seed × két jutalmazás, egyenként 4096 tanítási döntéssel,
összesen **16 384 döntésből**, PyTorch CPU-n. A négy tanítás validációval együtt 195,4 / 220,5 / 221,0 / 225,4 másodpercig tartott.
A teljes első kísérlet tesztekkel és hat videóval **1030,1 s, azaz 17,2 perc** volt.

| Vezérlő | Greedy győzelem / 90 teszt | Mintavételezett győzelem / 90 | Saját HP megmaradt, greedy |
|---|---:|---:|---:|
| Egyenletes random minden legális akción | 58 / 90 (64,4%) | ugyanaz a random kontroll | 64,9% |
| Random menekülés és megadás nélkül | 88 / 90 (97,8%) | ugyanaz a random kontroll | 55,4% |
| Egyszerű shoot/attack/közeledés szabály | 90 / 90 (100%) | determinisztikus szabály | 79,8% |
| Sparse PPO, seed 7 | 90 / 90 (100%) | 87 / 90 (96,7%) | 82,5% |
| Dense PPO, seed 7 | 90 / 90 (100%) | 79 / 90 (87,8%) | 82,5% |
| Sparse PPO, seed 19 | 90 / 90 (100%) | 86 / 90 (95,6%) | 82,0% |
| Dense PPO, seed 19 | 90 / 90 (100%) | 89 / 90 (98,9%) | 82,5% |

**Fontos kontroll:** a videók áttekintésekor kiderült, hogy a teljesen random vezérlő néha elmenekül.
Ezért a már befagyasztott modellek mellé utólag külön random-without-retreat kontrollt is mértünk;
ez sem a súlyokat, sem a checkpointválasztást nem befolyásolta. A végleges futtató ezt a kontrollt is tartalmazza.
A nagy, 64,4 → 100%-os különbség részben a menekülés elkerüléséből származik.
A 97,8 → 100%-os győzelemkülönbségből ilyen kis mintán nem állítunk megbízható taktikai fölényt.

Érdemibb jel itt a veszteség és hatékonyság: a dense seed 7 modell átlagosan **4,59 döntésből** nyert,
a menekülést kizáró randomnak **10,60 döntés** kellett. Saját megmaradt HP-különbségük **+27,1 százalékpont**;
az azonos 90 eseten végzett, 5000 mintás páros bootstrap 95%-os intervalluma **+20,6…+33,8 százalékpont**.
Ez egy rögzített modell ezen teszteseteire vonatkozik, nem a tanulási seedek bizonytalanságát becsli.
A teljes random HP-ja a meneküléssel megőrzött seregek miatt sem közvetlenül veszteséghatékonysági mutató.

A saját jutalom **nem bizonyult általánosan jobbnak**: greedy módban közel azonos lett a két jutalmazás eredménye,
mintavételezve a dense seed 7 gyengébb, a dense seed 19 jobb lett a megfelelő sparse futásnál.
Több seed, nehezebb feladat és külön jutalomsúly-vizsgálat kell, mielőtt ebből erősebb következtetést vonnánk le.
A checkpointok validációs greedy eredmény alapján választottak, nem a mintavételezett teszt alapján.

A validáció szerinti globális választás `sparse-seed-7.zip` volt; a dense modellek közül ugyanazon
validációs szabállyal, egyezésnél az előre rögzített seed-sorrend szerint `dense-seed-7.zip` lett a külön jutalmas demó modellje.
Mindkettő külön folyamatban visszatölthető volt; a dense modell mind a 90 greedy tesztjének natív akciósora és eredménye egyezett.
A renderes demók akciósorai és eredményei is egyeztek a render nélküli tesztekkel; a videókat visszaolvasással ellenőriztük.

Mért teljes wrapper-`step` költség a négy greedy teszten: **14,75–15,23 ms**, nagyjából **66–68 lépés/s reset nélkül**.
A 4096 döntésnyi tanítások validációval és resetekkel együtt **18,2–21,0 döntés/s** sebességet értek el.
Ez nem párhuzamos throughput-mérés, és az eltérő policy-k nem azonos natív akciósort hajtanak végre.
A korábbi [azonos akciósoros Gym/raw összevetés](PYTHON_ENV_FIRST_RL.md) külön benchmark marad.

A teljes Python/Gym csomag **227/227 tesztje sikeres** volt (163,3 s);
a végleges erősebb kontroll bekötése után a négy célzott PPO-teszt is újra sikeres.
C++-forrás vagy natív bináris nem változott. Az extra helyi kontroll-, replay- és médiaellenőrzések ideje nincs benne az 1030,1 s-ban.

Helyi, Gitből kizárt kimenetek:

```text
build/python-env-battle-ppo/final/report.json                 # négy futás, tesztek, időmérések, ujjlenyomatok
build/python-env-battle-ppo/final/additional-baseline.json    # erősebb random kontroll
build/python-env-battle-ppo/final/verification.json           # forrás/bináris/teszt és páros HP-ellenőrzés
build/python-env-battle-ppo/final/learning.png                # ábra
build/python-env-battle-ppo/dense-replay/videos/index.html    # saját jutalmas modell, helyi videógaléria
```

A fő futás pontos forrása helyben `final/executed-battle_ppo.py`. Utána csak a platformfüggő
alapértelmezett binárisnevet javítottuk és az extra random-kontroll kiértékelését adtuk hozzá;
a tanítás, jutalom, curriculum és checkpointválasztás változatlanságát AST-összevetés is ellenőrzi a helyi auditban.

## Jutalom: külön tanítási feladat, natív állapotváltozásból

A jutalmat nem feltétlenül a motor határozza meg. A natív motor állapotot, eseményt és csataeredményt ad;
a tanítási feladat ezekből számolhat saját jutalmat. Lehet csak végeredmény-jutalom vagy sűrűbb visszajelzés.
Más feladathoz — kalandtérkép, várfejlesztés, csata — más függvény indokolt.

Ebben a varázslat nélküli, két-két csapatos feladatban, a Python-oldal nézőpontjából:

```text
r = natív végeredmény
    + 0.5 × (előző ellenséges HP − jelenlegi ellenséges HP) / kezdeti ellenséges HP
    − 0.5 × (előző saját HP − jelenlegi saját HP) / kezdeti saját HP
    − 0.002
```

- Natív eredmény: győzelem +1, vereség −1, döntetlen/limit 0.
- A HP-t a numerikus natív csataállapotból, az eredeti `army_color` alapján összesítjük.
- A kezdeti nevező az első Python-döntés állapota; az addig esetleg megtett AI-akciót nem jutalmazzuk utólag.
- A motor az ellenfél lépéseit is feldolgozza a következő Python-döntésig, így a saját elszenvedett veszteség is számít.
- A terminális csatapillanatkép HP-ját is felhasználjuk, a befejező ütés jutalma nem vész el.
- Előjeles HP-különbséget használunk: egy gyógyítás visszavonná a korábbi sebzésbónuszt.
  Ebben a curriculumban nincs gyógyítás, idézés, feltámasztás vagy irányításátvétel; ilyen feladatokra külön reward-tervezés kell.
- Az `info['reward_parts']` külön megmutatja az egyes tagokat; az `info['native_reward']` megőrzi az eredeti eredményt.

Ez szándékosan módosítja az optimalizált célt: a gyorsabb és kisebb saját veszteségű győzelmet részesíti előnyben.
Nem állítjuk róla, hogy elméletileg változatlanul hagyja az eredeti optimális policy-t.
A siker mércéje továbbra is a külön teszten mért natív győzelem/vereség, megszakítás és megmaradt HP,
nem pusztán a saját alakított jutalom emelkedése.

## Feladat, modell és elkülönített mérés

Három család, grass/snow/water terepen, három létszámváltozattal:

| Család | Saját sereg | Beépített AI serege |
|---|---|---|
| Ranged | 8/10/12 Ranger + 4/5/6 Swordsman | 60/75/90 Peasant + 15/18/21 Goblin |
| Melee | 6/7/8 Swordsman + 20 Peasant | 24/30/36 Goblin + 25 Peasant |
| Flying | 7/8/9 Griffin + 15 Skeleton | 25/30/35 Skeleton + 15/20/25 Goblin |

A támadó Python-oldal alapértékű hőst kap; az ellenfél hős nélküli, ezért nem menekülhet automatikusan.
A limit 15 natív csatakör vagy 80 Python-döntés. Ez a tanítási feladat véges horizontja: a wrapper itt
elnyelő feladatvéget ad a PPO-nak, így az algoritmus nem bootstrapol a horizonton túl.
Az eredeti natív `terminated`/`truncated` adat külön megmarad az `info`-ban és a kiértékelésben.
A közös `HeroesEnv` truncation-szemantikája nem változik.

A 24 megfigyelési jellemző a korábbi példából jön. A hálózat az akciójelölteket közös
24 → 32 `tanh` → 1 pontozóval értékeli. A critic a legális jelöltek maszkolt átlagát használja.
Nincs fix „jó akcióhely”, beégetett shoot/attack prioritás vagy szabályalapú tanítójel a modellben.
Az induló actor pontosan egyenletes a legális jelölteken. A szabályalapú vezérlő csak külön kontrollmérés.
Az SB3 végzi a PPO-adatgyűjtést, GAE-t, clippinget, optimalizálást és checkpoint-mentést.

A teljes kísérlet két tanulási seeden (7, 19), azonos 4096 döntésnyi költségkerettel hasonlítja össze:

1. Az eredeti, ritka végeredmény-jutalmat (`sparse`).
2. A fenti saját jutalmat (`dense`).

Seedpáron belül azonos kezdősúlyok és konfigurációmintavétel; a tanulás következtében az akciósor és az epizódhossz eltérhet.
Tanító csataseedek: 0–4095. Validáció: 27 külön eset 10000-től, végső teszt: 90 külön eset 20000-től.
A checkpointot csak validációs győzelmi arány, majd megmaradt saját HP választja, egyezésnél a korábbi marad.
Minden tanítás és kiválasztás a végső teszt előtt befejeződik, a kiválasztás külön fájlba kerül.
A négy modell greedy és mintavételezett tesztje, a random, a menekülést kizáró random és a szabályalapú referencia is ugyanazt a 90 esetet kapja.
Ez nem új seregtípusokra, ostromra, varázslásra vagy ismeretlen AI-ra végzett általánosítási teszt.

## Futtatás és mentett modell

A repó gyökeréből, opcionális desktop env builddel és játékadatokkal:

```powershell
uv run --project python --cache-dir .tools/uv-cache --extra battle-rl --locked python python/examples/battle_ppo.py --steps 4096 --seeds 7 19 --output build/python-env-battle-ppo/final
# Rövid próba, a végső teszt és videók nélkül:
uv run --project python --cache-dir .tools/uv-cache --extra battle-rl --locked python python/examples/battle_ppo.py --pilot --steps 512 --seeds 7 --output build/python-env-battle-ppo/pilot
# Egy saját, már elkészült modell újraértékelése és videózása tanítás nélkül:
uv run --project python --cache-dir .tools/uv-cache --extra battle-rl --locked python python/examples/battle_ppo.py --model build/python-env-battle-ppo/final/dense-seed-7.zip --output build/python-env-battle-ppo/replay
```

Más futtathatóhoz `--executable`, játékadathoz `FHEROES2_DATA` használható.
Minden új futásnak friss kimeneti könyvtár kell. A script csak a repó figyelmen kívül hagyott `build/` fája alatt írhat kimenetet.
Az SB3 ZIP cloudpickle-adatot tartalmazhat; csak saját/megbízható modell tölthető be.
Az eredmények között `plan.json`, `selection-before-test.json`, `report.json`, esetenkénti teszteredmények,
négy `.zip` modell és `videos/` található. Ezek egyikét sem commitoljuk vagy töltjük fel GitHubra.

A tanítás teljesen render nélkül fut. A kiválasztott modell, a véletlen és a menekülést kizáró véletlen vezérlő ugyanazon három,
előre kijelölt, grass terepű tesztcsatáról kap MP4-et, minden családból a 2. létszámváltozatról.
A felvétel natív RGB döntési pillanatképek sorozata, állapotonként egy másodperc megjelenítéssel;
nem a normál játék folyamatos animációja és nem valós idejű sebességbemutató.
A képaláírás mutatja a vezérlőt, lépésszámot, akciót, összjutalmat és végső eredményt.
A terminális csatakép is szerepel. A videókhoz külön friss csaták futnak, nem a tanítás közben renderelünk.
A végleges script kilenc nyers videót ír futásonként (három család × három vezérlő).
A jelenlegi helyi `dense-replay/videos/index.html` emellett egymás mellé tett összehasonlításokat is mutat;
`comparison-no-retreat-*.mp4` alatt az erősebb random kontroll és a saját jutalmas modell látható.

## Teljes fennmaradó lista

1. Nehezebb és változatosabb többcsapatos feladatok, varázslás/ostrom, új seregkonfigurációkon való általánosítás.
2. A mért Gym-másolási/reset költségek csökkentése, párhuzamos mintavétel és hosszú RL-terhelés.
3. Linux/macOS futásellenőrzés és mobil SDK-buildek.
4. Igény szerint láthatóságra szűrt megfigyelés, több agentes Gym és self-play.
