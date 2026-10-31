# 9–10. bővítés: objektumok, interakciók és varázslatok

A bővítés a meglévő `hero.move`, `hero.cast`, `choice.answer` és `battle.act` parancsokat használja.
A pénzlevonás, egyszeri/heti látogatás, képességnövelés, csata, idézés és feltámasztás a natív C++ motorban történik.
Pythonban nem készült második játékszabály-rendszer. A vezérlés továbbra is oldalanként konfigurálható.

## Futtatható bemutató

Az eredeti assetekkel és az előkészített baseline mentéssel:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File script/windows/python-env-artifact-fixture.ps1
uv run --project python python python/examples/expansion.py
```

Választható rész: `--scenario objects`, `--scenario travel`, `--scenario battle`.
A példa a külön tesztmentéseken szélmalmot, arénát, tudásfát, tárgyvásárlást és bányavédelmet használ;
Dimension Door/Town Portal célpontot választ, majd tömegvarázslatot, idézést és harci teleportot mutat be.
A koordináták és bemeneti mentések erre a bemutatóra vonatkoznak. Az API standard játékban is használható.

A builder külön `expansion-*.sav` fájlokat és `expansion-objects.json` jegyzéket ír a build mappába.
Nem módosítja az eredeti pálya- vagy baseline mentésfájlokat, és nincs benne a normál játékbuildben.
Már előkészített régebbi fixture-ek mellett `-ExpansionOnly` is használható.

## Támogatott térképi objektumok

A teljes név szerinti forráslista: `src/fheroes2/game/python_env_profile.h`.
A `game.capabilities()["adventure_object_ids"]` ugyanazt a **83 natív objektumtípusból** álló listát adja vissza.
A hősök, várak és hajók korábbi, külön ellenőrzött mozgási céljai ezen felül működnek.

| Csoport | Támogatás |
|---|---|
| Erőforrás és kincs | Erőforráskupac, tábortűz, hordó, flotsam, szárazföldi/tengeri láda; szélmalom, vízikerék, varázskert, lean-to, szekér, csontváz |
| Tárgy | Artifact és Shipwreck Survivor; natív feltételek, fizetés, képességkövetelmény vagy őrzőcsata; könyv-/táskaellenőrzés |
| Tanulás | Három shrine-kör, Witch's Hut, Fort, Mercenary Camp, Witch Doctor's Hut, Standing Stones, Gazebo, Tree of Knowledge, Arena, Xanadu |
| Átmeneti hatás | Fountain, Faerie Ring, Idol, Oasis, Temple, Watering Hole, Buoy, Mermaid, Black Cat, Sirens |
| Mana és sereg | Magic Well, Artesian Spring, Stables, Hill Fort, Freeman's Foundry, Alchemist Tower |
| Foglalás | Mine, Sawmill, Alchemist Lab, Lighthouse; belső őrség esetén natív csata; Abandoned Mine visszafoglalása |
| Lakóhely | Ingyenes, fizetett és csatával felszabadítható lakóhelyek: Watch Tower, Excavation, Cave, Tree House, Archer House, Goblin Hut, Dwarf Cottage, Halfling Hole, Peasant Hut, Ruins, Tree City, Wagon Camp, Desert Tent, Dragon City, City of Dead, Troll Bridge, négy elemental altar és Barrow Mounds |
| Veszélyes hely | Pyramid, Graveyard, Shipwreck, Derelict Ship, Daemon Cave; döntés → csata → jutalom/toborzás folytatás |
| Egyéb | Observation Tower, Obelisk, Traveller Tent, Barrier, Sign, Bottle, Jail, Eye of Magi |

`move_hero(hero_id, x, y, token=...)` ugyanazt az eredeti `Heroes::Action` folyamatot hívja.
Egy művelet több választást és csatát is visszaadhat; a visszakapott `phase` és friss token alapján kell folytatni.
Az elutasítás, fizetés, készletcsökkenés, látogatási jelölés és esetleges hősvesztés az eredeti szabály szerint történik.
Az OK-értesítések szöveges `notification` eseményekké válnak; az igen/nem és mennyiségi döntést az agent hozza.

Az aréna új választása `hero.primary_skill`, a natív attack/defense/power opcióazonosítókkal.
Tárgyvásárlás és tudásfa megerősítése `confirmation`; a `values` a natív árakat/jutalmat is tartalmazza:
`gold`, szükség szerint a többi erőforrás, `artifact_id`, illetve `experience`.
A fizetett toborzás továbbra is `army.recruit_count`, pontos mennyiséggel és natív megfizethetőségi határral.

A teljes útvonal továbbra is az aktuális mozgásból fizetendő. Csak a cél lehet interakció;
nem támogatott köztes objektumon vagy külön térképi szörny által őrzött útvonalon nem megyünk át automatikusan.
Az ilyen őrséget előbb külön megtámadhatja a Python-agent. A foglalható objektum saját belső őrsége támogatott.

## Adventure varázslatok

```python
options = hero["adventure_spell_options"]
result = game.cast_spell(hero_id, spell_id, token=decision["token"])
decision = result["decision"]
```

| ID | Varázslat | Folytatás |
|---|---|---|
| 55 | Identify Hero | Natív felismerési hatás |
| 60 | Visions | Natív szörnyinformációs hatás |
| 56 | Summon Boat | A natív kiválasztott hajó áthelyezése; az eredeti hajó eltűnik |
| 57 | Dimension Door | `spell.dimension_door` célválasztás |
| 58 | Town Gate | Natív legközelebbi, alkalmas saját vár |
| 59 | Town Portal | `spell.town_portal` választás a szabad saját várakból |
| 61 | Haunt | Natív szellemek és tulajdonosi szabály |
| 62–65 | Set Earth/Air/Fire/Water Guardian | Natív őrség a bánya bejáratánál |

A **11 támogatott varázslat** aktuális listája az `adventure_spell_ids` capability-ben és minden hős
`adventure_spell_options` mezőjében olvasható. A könyv, ismert varázslat, mana, mozgás és helyzetfeltétel natív ellenőrzésből jön.
Nem elég a listában szerepelni: `can_cast` és `blocked_reason` jelzi az aktuális használhatóságot.

A célválasztás `pending_choice.options` mezője natív tile-indexeket ad.
Koordináta: `x = index % map_width`, `y = index // map_width`.
A Town Portal kizárólag szabad saját várakat kínál. A Dimension Door a natív spell-távolság és
`Maps::isValidForDimensionDoor` feltételei szerint kínál célt: közeg, járhatóság, foglalt mező és akcióobjektum ellenőrzéssel.
A választás nem függ a headless ablak/kamera méretétől; a natív 14 mezős átmérőből számolt legfeljebb 7 mezős féloldali tartományt használja.
A válaszra várás alatt más játékművelet nem módosíthatja a világot.

Sikeres használatkor a mana/mozgás pontosan egyszer fogy. A Dimension Door eredeti rutinja maga vonja le a költséget;
az adapter ezt nem ismétli meg. A várba utazás az eredeti máguscéh-tanítást is alkalmazza.
A Summon Boat ténylegesen mozgat egy hajót, nem hoz létre plusz példányt vagy ingyenes vásárlást.
Az őrzővarázslat előfeltétele és létszáma a natív bányaszabályból származik.
A human/AI szabályprofil a Haunt tulajdonosi viselkedésénél is megmarad; a Python-vezérlő nem írja át ezeket a flag-eket.

## Harci varázslatok

A `native_combat` profil a játékosnak tanítható **mind a 48 harci varázslatot** kezeli (jelenlegi natív ID-k: 1–48).
Az automatikus, kizárólag lényekhez tartozó Petrify nem játékosvarázslat; a motor maga használja.
A hős könyve, tudása, mana, körönkénti varázslás, célpontimmunitás, ellenállás és arénabeli tiltások továbbra is számítanak.

- Célzott/területi varázslat: natív `GetTargetsForSpell` alapján érvényes `target_cell`.
- Láncvillám: érvényes első lény, natív célpontellenőrzéssel; a további ugrásokat a motor végzi.
- Teleport: natív érvényes lény/mező párok; `target_uid` a mozgatott saját egység, `target_cell` a cél.
- Tömeg-/globális varázslat és elemental idézés: egyetlen jelölt, `target_cell=-1`, nincs 99 egyenértékű másolat.
- Feltámasztás/Animate Dead: natív sérült csapat- és temetőellenőrzés, az eredeti ideiglenes/tartós szabályokkal.
- Mirror Image és idézés: valódi új csataegység, natív tulajdonossal és képességekkel.
- Earthquake: csak ostromban jelenik meg.

```python
action = next(a for a in decision["battle"]["actions"]
              if a["kind"] == "spell" and a["spell_id"] == wanted_spell_id)
result = game.battle_action(action["action_id"], token=decision["token"])
```

A varázslat után ugyanabban a natív csatában folytatjuk. Egy csatafordulóban nem adunk második varázslatot,
ha a motor szerint a hős már varázsolt. A célpontlista építése nem alkalmaz véletlen ellenállást vagy találati hatást.
A natív harci hatás és RNG kizárólag a kiválasztott parancs végrehajtásakor fut.

## Állapot, Gym és megszakítás

Új olvasható mezők minden oldalra:

- Hős: `max_move_points`, `morale`, `luck`.
- Térképmező: `owner`, `guardian_monster_id`, `guardian_count`.
- A korábbi készlet-, sereg-, tárgy-, képesség-, fog- és manaadatok az új interakciók eredményét is mutatják.

A foglalási rekordokat tisztán olvasó lookup adja: a lekérdezés nem hoz létre üres őrségi rekordot.
Állapot, döntés és render ismételt lekérése nem lépteti a játékot.
`session.stop` függő választás/csata közben az egész kezdeményező műveletet visszaállítja, az előző választásokkal együtt.
A lecsatlakozás utáni fázisjelzés javítva: külső oldal visszaállított kalandköre nem válik tévesen AI-szimulációvá.

A strukturált Gym ugyanazokat a natív parancsokat/maszkokat és új választási típusokat használja.
Az akciótér továbbra is `Discrete(8192)` alapból; az eddigi kategóriakódok megmaradtak.
Az epizódon belüli space fix, de a megfigyelés a korábbi verzióhoz képest bővült:

| Adat | Új alapméret |
|---|---|
| `heroes` | 128×25: új max. mozgás/morál/szerencse, az x/y előtt |
| `tiles` | 20736×19: az eddigi 16 oszlop után tulajdonos és őrség |
| `choice_values`, `choice_value_mask` | 16: erőforrásárak és artifact ID is szerepelnek |

Régebbi megfigyelésméretre épített modell bemenetét módosítani kell.
Sok varázslat/idézett egység esetén a meglévő profilkorlátok továbbra is érvényesek;
túllépéskor explicit `gym_profile_limit` érkezik, nem vágjuk le csendben a jelölteket vagy csapatokat.

## Ellenőrzött és még hiányzó részek

`python/tests/test_expansion.py`: 79 külön natív objektumfixture végigjátszása; valós ár/toborzás/képesség/bevétel;
visszautasítás és rollback; összes kezdetben szabályos harci varázslat végrehajtása;
feltámasztás/Animate Dead sérült célon, teleport, Mirror Image, négy idézés, ostromvarázslat;
Town Gate/Portal/Dimension Door/Summon Boat és bányavédelmi varázslatok; Gym célválasztások és új megfigyelések.
A Monster korábbi csatatesztekkel is ellenőrzött; Sign/Bottle/Jail érvényes, szerkesztett pályaadatot igényel,
ezekhez ez a generátor nem gyárt mesterséges szöveget vagy rabot.

2026-10-31, Windows: **180/180** teljes Python/Gym teszt sikeres. A **14/14** új bővítési teszt
Debug buildben, bekapcsolt C++ ellenőrzésekkel is sikeres, benne a 79 objektumfixture-rel.
Az opcionális és a normál `ENABLE_PYTHON_ENV=OFF` build lefordult; az `expansion.py` teljes példája
video/audio inicializálás nélkül lefutott. A korábbi 14. lépés teljesítménymérései történeti eredmények,
ez a munkaszakasz nem helyettesíti azokat új RL-benchmarkkal vagy más platform SDK-buildjével.

A támogatási lista továbbra is explicit. Még hiányzik többek között a szöveges Sphinx-válasz,
a helyi Trading Post külön kereskedelmi felülete, a scripted map eventek, Stone Lith/Whirlpool,
Hut of Magi, Magellan's Maps és Oracle speciális nézete, valamint a hat View World varázslat külön információs nézete.
Ezekre nem adunk hamis sikeres vagy automatikus AI-műveletet; a profilon kívüli művelet elutasított és visszaállított.
A beépített AI teljes natív stratégiai útja továbbra is megmarad.

Külön hátravan a konfigurálható önálló csataindítás, a szélesebb pálya-/terep-/ostrom-/hajós kombinációs lefedettség,
a Linux/macOS/mobil SDK-ellenőrzés és a nagy léptékű RL-profilozás. A Python/venv továbbra is csak opcionális desktop függőség.
