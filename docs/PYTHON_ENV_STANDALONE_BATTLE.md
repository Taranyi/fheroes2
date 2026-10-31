# Konfigurálható önálló csataszimulátor

Pythonból most **mentés és kalandtérkép betöltése nélkül** is indítható natív csata.
Ugyanaz a `Battle::Loader`, aréna, AI, sebzés-, varázslat-, ostrom- és eredményszámítás fut, mint a játékban.
Az adapter az eredeti Battle Only mód minimális, belső 2×2-es terepkörnyezetét használja a motor térképi kontextust igénylő részeihez.
Ez nem játszható kalandpálya: nincs mozgási kör, napi bevétel, várépítés vagy kalandjáték-művelet.
Az opcionális desktop CMake kapcsoló továbbra is `ENABLE_PYTHON_ENV`, alapból kikapcsolva; Python/venv nem kell a normál vagy mobil játékhoz.

## Futtatás

Meglévő desktop env build és játékadatok mellett, a repository gyökeréből:

```powershell
uv run --project python --cache-dir .tools/uv-cache python python/examples/standalone_battle.py
uv run --project python --cache-dir .tools/uv-cache python python/examples/standalone_battle.py --scenario siege --output build/battle-siege
uv run --project python --cache-dir .tools/uv-cache python python/examples/standalone_battle.py --scenario naval --attacker builtin_ai --defender builtin_ai --output build/battle-naval
uv run --project python --cache-dir .tools/uv-cache --extra gym python python/examples/standalone_battle.py --gym
```

A [példa](../python/examples/standalone_battle.py) alapból Python–AI csatát játszik.
`--defender python` mindkét oldal döntéseit Pythonba irányítja; két `builtin_ai` emberi döntés nélkül végigjátszik.
`--config sajat.json` saját konfigurációt olvas. `--seed` a kezdőállapotot szabályozza.
Az opcionális `--output` valódi RGB-képeket ír PPM formátumban. A normál session példa külső Python-csomagot nem igényel.
Játékadat továbbra is kell; a példa alapból a repository gyökerét használja, amit a `FHEROES2_DATA` felülírhat.
Nincs referencia-mentés vagy generált kalandtérképes tesztfixture-függőség.

## Python API

```python
from fheroes2_env import HeroesSession

config = {
    "terrain": "grass",
    "max_rounds": 100,
    "attacker": {
        "army": [{"monster_id": 3, "count": 30}],  # Ranger
        "controller": "python",
        "hero": {"id": 1, "attack": 4, "power": 5,
                 "spells": [15, 11], "spell_points": 50},
    },
    "defender": {
        "army": [{"monster_id": 1, "count": 30}],  # Peasant
        "controller": "builtin_ai",
    },
}

with HeroesSession(executable, env=environment) as game:
    episode = game.reset(battle_config=config, seed=123)
    decision = episode["decision"]
    while decision["phase"] == "battle":
        actions = decision["battle"]["actions"]
        action = choose_action(actions, decision["battle"])
        result = game.battle_action(action["action_id"], token=decision["token"])
        decision = result["decision"]
    outcome = game.get_state(include_serialized=False)["standalone_battle"]["result"]
```

Az `action_id` a **jelenlegi döntés** natív listájának indexe; a token és a `player_id` ellenőrzött.
`decision.player_id` jelzi, melyik Python-agent következik. A résztvevő-ID-k rögzítettek: attacker=Blue/1, defender=Green/2.
Beépített AI-köröket a motor automatikusan futtat a következő Python-döntésig vagy a csata végéig.
AI–AI esetben a reset közvetlenül terminális döntést is visszaadhat.

Az alacsonyabb szintű protokoll külön előkészítést is enged:

```python
prepared = game.configure_battle(config, seed=123)
decision = prepared["decision"]              # phase="battle_ready"
result = game.step("battle.start", token=decision["token"])
```

Aktív csata alatt új konfiguráció elutasított. A `reset` új motorfolyamatot indít, így élő csatából, terminális állapotból,
lezárt/crash-elt/timeoutos sessionből is használható. A paraméter nélküli `reset(seed=123)` újrahasználja a korábbi konfiguráció másolatát.
A `save`, `map_path`, `battle_config` egymást kizárják. A csata oldalankénti vezérlése és szabályprofilja a konfigurációban szerepel,
ezért a külön reset-`controllers`/`rule_profiles` paraméterek ezzel a forrással nem használhatók.

## Konfiguráció

Az ismeretlen mezők, hibás típusok, negatív/lebegő mennyiségek, boolként küldött számok, random/editor ID-k és inkompatibilis beállítások hibát adnak.
A konfigurált seregek pontosak: üres helyre nem kerül automatikusan kezdőegység.

| Felső mező | Jelentés és alapérték |
|---|---|
| `attacker`, `defender` | Kötelező oldalobjektumok |
| `terrain` | `grass` (alap), `snow`, `swamp`, `lava`, `desert`, `dirt`, `wasteland`, `beach`, `water` |
| `siege` | `null` (alap), vagy a lent leírt ostromobjektum |
| `max_rounds` | 1–100000, alapból 1000 teljes natív csatakör; utána megszakítás, győztes nélkül |
| `capture_final_frame` | Alapból false; a befejező aréna képének megőrzése |
| `perspective_player_id` | 1 vagy 2; alapból az első Python-oldal, AI–AI esetben 1; a `game_result` és Gym-jutalom nézőpontja |

| Oldal mezője | Jelentés |
|---|---|
| `army` | Kötelező 1–5 elemű tömb, legalább egy csapattal. Elem: `null` vagy `{"monster_id": N, "count": M}` |
| `hero` | Alapból null: hős nélküli sereg. Objektum esetén a lent leírt hőskonfiguráció |
| `controller` | `python` vagy `builtin_ai`; alapból attacker Python, defender AI |
| `rule_profile` | `human` vagy `ai`; alapból a vezérléshez igazodik, de külön megadható. A vezérlő nem írja felül a natív szabályokat |
| `gold` | 0–1000000000, alapból 0; natív megadáshoz és ellenoldali kifizetéshez is |
| `formation` | `spread` (alap) vagy `grouped`; az üres sereghelyek is megtartják a helyüket |

Konkrét monster ID-k: 1–66, legfeljebb 100000 lény/csapat. A random/editor típusok nem engedélyezettek.
Példák: Peasant=1, Archer=2, Ranger=3, Black Dragon=38, Titan=47, Bone Dragon=57.

| Hős mezője | Jelentés |
|---|---|
| `id` | Natív, nem debug hős-ID, oldalanként különböző. Alapból 1 (Lord Kilburn), illetve 2 (Sir Gallanth) |
| `attack`, `defense` | Alapérték 1, 0–99 tartomány; a natív artifact/képesség-módosítók erre rakódnak |
| `power`, `knowledge` | Alapérték 1, 1–99 tartomány |
| `spell_points` | 0–100000, alapból 0; nincs automatikus manafeltöltés |
| `spell_book` | Alapból false; nem üres `spells` automatikusan aktiválja |
| `spells` | Legfeljebb 48 különböző tanítható harci varázslat-ID, 1–48; a megadott könyv tanulási Wisdom-ellenőrzés nélkül épül fel |
| `skills` | Legfeljebb 8 különböző `{"id": 1..14, "level": 1..3}`; alapból üres, nincs rejtett kezdő képesség |
| `artifacts` | Legfeljebb 13 `{"id": N}`. A Magic Book helyett a `spell_book` mező használandó; a Spell Scrollhoz `spell_id: 1..48` kell |

A hős-ID választja ki a natív hőst, fajt és portrét. A konfigurációban fel nem sorolt képesség, varázslat és tárgy nem öröklődik a normál kezdőhőstől.
A harc közbeni mana, körönkénti varázslási korlát, immunitás, ellenállás, morál, szerencse, visszacsapás és artifact-hatás továbbra is natív.

## Ostrom és hajós csata

```python
config["siege"] = {
    "race": "knight",
    "fortification": True,
    "left_turret": True,
    "right_turret": True,
    "moat": True,
    "captain": False,
}
```

A faj `knight`, `barbarian`, `sorceress`, `warlock`, `wizard` vagy `necromancer`; alapból knight.
A fal, központi torony, híd és támadó hős katapultja natív. A két oldaltorony és az árok alapból bekapcsolt.
A Knight erődítése alapból kikapcsolt; más fajnál nem állítható be.
Védekező hős hiányában `captain=true` a faj natív kapitányát adja, alapértékekkel; hős és kapitány egyszerre nem konfigurálható.
A kapitányos várhoz ez az API nem állít külön máguscéhet vagy tetszőleges kapitánykönyvet.
A védekező hős a várban áll, ezért a natív ostrombeli menekülési korlátozás is érvényesül.

Hajós csatához `terrain="water"` kell; a hősök shipmaster flaget kapnak, a motor vízi harcterét és akadályait használjuk.
Víz és ostrom együtt elutasított. Kalandtérképes hajóvásárlásra vagy beszállásra nincs szükség.

## Állapot, eredmény és render

Az eddigi `get_state`, `get_decision`, `battle_action`, `render(view="battle")` működik.
A `state.standalone_battle` tartalmazza a normalizált `configuration`, az effektív `seed`, a `sides` seregeit/manáját és a `result` mezőt.
Az élő csapatok HP-ja, lövése, buffjai, aktuális pozíciója és a falak állapota a `state.battle` / `decision.battle` mezőben olvasható.
A belső 2×2-es `map` csak natív harctér-környezet, `internal_battle_context=true` jelöléssel. Az általános világállapot hősei itt sem kalandköröket játszanak.

Normál eredmény: attacker/defender natív result flag, kapott tapasztalat, necromancy-halottak száma,
`winner_player_id` (1/2, döntetlennél 0), `rounds`, `truncated=false`.
A motor szinkronizálja a veszteségeket, manát, megadás aranyát, artifact-átszállást és a natív harc utáni képességeket.
A jelentett tapasztalatot nem írjuk hozzá kalandtérképes hősfejlődéshez, és nincs újabb szintlépés-kör.
Körlimitnél `truncated=true`, `reason="round_limit"`, nincs győztes és nincs kiosztott győzelmi jutalom;
a részleges csapatveszteség és mana megmarad. `phase="terminal"` mindkét lezárási módnál, a result megkülönbözteti őket.

A befejező aréna megfigyelése a csata után is olvasható, üres akciólistával.
A befejező kép a `capture_final_frame=true` beállítással őrizhető meg; egy sikeres élő `render` szintén bekapcsolja.
Ha egyik sem történt, a csata után `render` képhibát ad, nem készít hamis végállapotot.
Képkérés nélkül a futás nem inicializál videót, hangot vagy ablakot, és nem renderel rejtetten minden kört.
A képkérés és a grafikai adatok késleltetett betöltése nem fogyasztja a játékmenet RNG-jét.

Hibás/stale akció nem módosítja a csatát. `session.stop` az egész önálló csatát visszaállítja az előkészített felállásra, majd leválaszt.
Új indításhoz reset vagy új konfiguráció kell. Azonos konfiguráció/seed/akciósor azonos szemantikai eredményt ad.

## Gym

A meglévő `Fheroes2-v0` / `HeroesEnv` fogadja a `battle_config` forrást is, az eddigi fix megfigyelési és akcióterekkel:

```python
from fheroes2_env.gym_env import HeroesEnv

with HeroesEnv(executable=executable, battle_config=config) as env:
    obs, info = env.reset(seed=123)
    for _ in range(10000):
        action = env.action_space.sample(mask=obs["action_mask"])
        obs, reward, terminated, truncated, info = env.step(action)
        if terminated or truncated:
            obs, info = env.reset()
```

Gymben pontosan egy Python-oldal kell; a másik natív AI. A Python-oldal lehet támadó vagy védő,
a jutalom nézőpontja ehhez igazodik: +1 győzelem, -1 vereség, 0 döntetlen vagy megszakítás.
Native körlimit és a külön Gym-lépéslimit `truncated`; valódi harci eredmény `terminated`.
A `render_mode="rgb_array"` a befejező képet is megőrzi, az `auto` render ebben a módban mindig a csatát adja.
`reset(options={"battle_config": uj_config})` új felállást adhat ugyanazzal a fix space-szel.
Több Python-agenthez vagy AI–AI futáshoz a session API használható; külön több agentes Gym-wrapper még nincs.
Ha a motor a Python első döntése előtt befejezi a csatát, már a reset eredménye is terminális lehet (`info.phase`).

## Ellenőrzés és hátralévő munka

A `python/tests/test_standalone.py` önálló csatakonfigurációkat használ referencia-mentés helyett:
kilenc terep, hat várfaj ostroma, kapitány és hős nélküli seregek, két Python-oldal, AI–AI,
natív falak/varázslatok, menekülés/megadás/arany, pontos sereghelyek és képességek,
seedelt replay, stop-visszaállítás, hibás konfiguráció és akció, körlimit, natív RGB és a hivatalos Gym-ellenőrző.

2026-10-31, Windows: **208/208 teljes Python/Gym teszt sikeres**. Az önálló csata **15/15 célzott tesztje Debug buildben is sikeres**,
bekapcsolt C++ belső ellenőrzésekkel. Mind a hat várfajnál tényleges Earthquake falrombolás és manaelszámolás is ellenőrzött.
Az opcionális és a normál `ENABLE_PYTHON_ENV=OFF` build lefordult; a gyökérben az opcionális Release futtatható maradt.
A szárazföldi, ostromos, AI–AI hajós és Gym-példa lefutott; az ostrom és a hajós végkép vizuálisan is ellenőrizve.
A végkép a natív halálképkockát használja az elesett egységeknél, a csapat animációs állapotának módosítása nélkül.
Más platform SDK-buildje és nagy léptékű RL-benchmark ebben a munkaszakaszban nem futott.

Az önálló csataindítás elkészült. Fennmaradó feladatok:

A [nagyobb kombinációs és stresszteszt-készlet](PYTHON_ENV_BATTLE_STRESS.md) is elkészült, reprodukálható futtatóval és Windows jelentésekkel.

1. Linux/macOS és mobil SDK-build ellenőrzése.
2. Nagyobb léptékű RL-profilozás és teljesítményjavítás.
3. Igény szerint láthatóságra szűrt observation és több agentes Gym-wrapper.
