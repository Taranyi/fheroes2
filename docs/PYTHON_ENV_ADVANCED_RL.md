# Összetett csata-RL: változatos seregek, varázslás és ostrom

A [battle_advanced.py](../python/examples/battle_advanced.py) a korábbi
[kétcsapatos PPO-példát](PYTHON_ENV_PPO.md) bővíti önálló tanítási kísérlettel.
Valódi natív csatákat használ, az eredeti C++ játékszabályok és a közös `HeroesEnv` módosítása nélkül.
Az opcionális `battle-rl` extra és a korábban ellenőrzött SB3/sb3-contrib MaskablePPO marad a tanítás alapja.
[A könyvtár hivatalos akciómaszk-szerződése](https://sb3-contrib.readthedocs.io/en/master/modules/ppo_mask.html).

## Tényleges Windows-eredmény, 2026-10-31

Két külön, egyenként **8192 döntéses** PPO-tanítás készült, összesen **866 tanítási epizóddal**.
Mindkét seed minden kontextuson tanult, és mind a hét varázslatot kipróbálta.
A tanítások validációval együtt **249,2 és 266,6 másodpercet** igényeltek CPU-n;
a teljes első futás a kontrollokkal, tesztekkel és 16 videóval **687,9 s, azaz 11,5 perc** volt.
A későbbi médiafeldolgozás, OOD-felvételek és regressziós teszt ideje ebben nincs benne.

| Vezérlő | Ismert seregek, új seedek: 36 csata | Új lénytípusok/terep/ostromfaj: 24 csata |
|---|---:|---:|
| Maszkos véletlen, menekülés nélkül | 9 / 36 (**25,0%**) | 4 / 24 (**16,7%**) |
| Egyszerű szabály, varázslat nélkül | 20 / 36 (**55,6%**) | 12 / 24 (**50,0%**) |
| Egyszerű szabály, sebző varázslatokkal | 33 / 36 (**91,7%**) | 21 / 24 (**87,5%**) |
| Kiválasztott PPO, greedy | 34 / 36 (**94,4%**) | 19 / 24 (**79,2%**) |
| Ugyanez a PPO, varázslatok letiltva | 18 / 36 (**50,0%**) | 9 / 24 (**37,5%**) |
| Kiválasztott PPO, mintavételezve | 33 / 36 (**91,7%**) | 19 / 24 (**79,2%**) |

A táblázat a validáció alapján kiválasztott **seed 7 / 8192 döntés** modellje.
A seed 19 modellje is 34/36 tesztet nyert; ott egy vereség és egy körlimit volt, a kiválasztott modellnél két vereség, megszakítás nélkül.
A seed 19 kiadott checkpointja a 4096. döntésnél készült. A végső teszt sem a seed-, sem a checkpointválasztást nem módosította.
A két seed közös teszteseteit nem kezeljük 72 független esetként.

**A varázslás ténylegesen hasznos a megtanult policy-nak:** az azonos 36 esetben +44,4 százalékpont a nyerési különbség
a saját varázslatletiltási ablációjához képest. A 5000 mintás páros bootstrap 95%-os intervalluma +27,8…+61,1 százalékpont.
Az OOD-különbség +41,7 százalékpont, intervalluma +20,8…+62,5 százalékpont.
Ezek a rögzített modell és esetlista összehasonlításai, nem a tanulási seedek bizonytalanságát becslik.
Az abláció nem optimálisan újratanított, varázslat nélküli ellenmodell.

| Környezet | PPO, új seedek | Ugyanaz varázslat nélkül | PPO, OOD |
|---|---:|---:|---:|
| Nyílt terep | 9 / 9 | 7 / 9 | 5 / 6 |
| Hajós csata | 9 / 9 | 6 / 9 | 5 / 6 |
| Támadó ostrom | 7 / 9 | 0 / 9 | 4 / 6 |
| Várvédelem | 9 / 9 | 5 / 9 | 5 / 6 |

**Korlát:** az új seregeken a PPO nem múlta felül a szabályalapú kontrollt (19/24 kontra 21/24).
Az ismert profilos, egy győzelemnyi előnyből sem állítunk általános szakértői fölényt.
Ez működő tanulási és általánosítási kísérlet, nem tetszőleges csatára erős kész AI.

A greedy modell **Lightning Boltra specializálódott**: 136 cast a 36 teszten és 93 cast a 24 OOD-csatában.
Minden tesztcsatában varázsolt. A mintavételezett policy kisebb számban Fireballt, Arrow-t, buffot/debuffot is használ.
Earthquake és a többi támogatott varázslat jelen volt a tanításban és natív regresszióban, de a végső greedy policy
nem választotta őket; **nem állítjuk, hogy megtanulta mind a hét optimális használatát**.
A kiválasztott modell teszt/OOD győzelmei között nem volt ellenfél-menekülés vagy megadás, és nem volt terminális döntetlen.

A teljes wrapper-`step` átlaga a kiválasztott greedy teszten **16,29 ms**, kb. **61,4 lépés/s reset nélkül**;
OOD-n **17,19 ms**, kb. **58,2 lépés/s**. A tanítás validációval és resetekkel együtt 32,9 / 30,7 döntés/s volt.
Az eltérő policy-k eltérő natív akciósort hajtanak végre, ezért ezek nem azonos terhelésű motor/Gym benchmarkok.

A helyi audit igazolta a forrás-/binárisujjlenyomatokat, a tanítási rekordok hashét és seedizolációját,
a warmup utáni, kizárólag validációs modellválasztást és a mentett modell natív visszajátszását.
Az összes renderes teszt/OOD-akciósor és eredmény egyezett a render nélküli kiértékeléssel.
24 nyers videó és 16 összehasonlító MP4 készült, a visszaolvasásuk ellenőrzött; mind helyben marad.
A teljes Python/Gym tesztcsomag **234/234 sikeres** volt (201,0 s), ebből hét új regresszió védi
a natív varázslás/manaköltség/körlimit használatát, a támadó/védő nézőpontot, a hexgeometriát,
a valódi PPO-frissítést és visszatöltést, az új seregek/seedek elkülönítését és a warmup-only modell kiadásának tiltását.
A natív C++-forrás, a futtatható bináris és a csomagfüggőségek változatlanok.

Helyi eredmények:

```text
build/python-env-advanced/final/report.json                 # futások, tesztek, forrás-/adat-/bináris SHA256-ok
build/python-env-advanced/final/verification.json           # seed-, checkpoint-, forrás- és ablációellenőrzés
build/python-env-advanced/final/training-seed-7.json         # tényleges tanítási konfigurációk, seedek, warmup-jelzők
build/python-env-advanced/final/training-seed-19.json
build/python-env-advanced/final/videos/index.html           # ismert profilok összehasonlítása
build/python-env-advanced/final/unseen/videos/index.html    # négy fix OOD-eset összehasonlítása
build/python-env-advanced/final/learning.png                # validáció, teszt, abláció, tényleges spell-választás
```

A futás az `eae4d44be` szülőcommit változatlan natív motorját használta; az új példák/tesztek ekkor még nem voltak commitolva,
pontos SHA256-ukat a jelentés rögzíti. A médiakészítő ezeket is ellenőrzi a feldolgozás előtt.

## Mit tanítunk és mit mérünk?

Négy feladatkörnyezet szerepel ugyanabban a policy-ban:

- `field`: nyílt terepi csata.
- `naval`: a natív vízi csatatér, kalandtérkép nélkül.
- `assault`: Python-támadó ostroma beépített AI-védő ellen.
- `defense`: Python-védő a várban, beépített AI-támadó ellen.

Oldalanként három csapat; három tanítási seregprofil, három létszám-/hőserősség-változattal:

| Profil | Python-sereg, középső változat | AI-sereg, középső változat |
|---|---|---|
| 0 | 10 Ranger, 7 Swordsman, 4 Griffin | 16 Orc Chief, 6 Ogre, 25 Goblin |
| 1 | 10 Grand Elf, 12 Dwarf, 20 Sprite | 18 Centaur, 5 Minotaur, 30 Skeleton |
| 2 | 5 Lich, 40 Skeleton, 10 Zombie | 25 Halfling, 7 Iron Golem, 4 Roc |

A két további változat ±10%-os létszámeltolást használ az oldalak között.
A Python-hős attack/defense értéke 3/3, power 3–5, kezdeti mana 35–49.
Ostromnál az ellenfél hőse is varázsolhat, 14 manával és Lightning Bolt / Slow / Bless könyvvel.
Nyílt és vízi csatában az ellenfél hős nélküli, ezért nem menekülhet.
A Python-oldal menekülése/megadása minden modellnél és kontrollnál letiltott feladatszabály;
a közös env ettől továbbra is támogatja ezeket az akciókat.
A natív ostromtámadó AI menekülése megmarad, és a jelentés külön számolja az ilyen eredményeket.

Tanítási szárazföldi terepek: grass/snow/dirt. Ostromfajok: knight/barbarian/wizard,
változó erődítéssel, oldaltornyokkal és árokkal. A falak, katapult, toronylövések és varázshatások mind natívak.
A horizont 20 natív csatakör vagy 160 Python-döntés; a tanítási wrapper elnyelő feladatvégként kezeli,
a natív megszakítást a kiértékelésben külön megőrzi. A közös Gym truncation-szerződése nem változik.

## Varázslatok, megfigyelés és jutalom

Hét ténylegesen felkínált varázslat: **Fireball, Lightning Bolt, Haste, Slow, Bless, Magic Arrow, Earthquake**.
Ezek használatát a modell választja, a tanítás nem kényszerít ki varázslatot és nem ad külön cast-bónuszt.
A támogatott hét varázslat nem jelenti mind a 48 natív csatavarázslat megtanulását.
Gyógyítás, feltámasztás, idézés és irányításátvétel ebben a curriculumban nem szerepel.

A 97 akciójelölt-jellemző tartalmazza a korábbi 24 mezőt, 48 spell-ID one-hot helyet,
valamint a célpont saját/ellenséges oldalát, HP/létszám/sebesség/lövés/attack/defense adatait,
hatásjelzőinek számát, manát és manaköltséget, körszámot, ostrom-/védőjelzőt, koordinátákat,
a Fireball körüli saját/ellenséges HP-összeget és az ismert saját spell powert.
A hexkoordináták és a területi lefedés a natív sorparitást követik; a széles egységet egyszer számoljuk.
Ez aktuális geometriai foglaltság, nem előre szimulált sebzés vagy jutalomjel.
A bemenet nem kap seedet, jövőbeli eredményt, beégetett jó-akció címkét vagy szabályalapú policy-kimenetet.

A közös jelöltpontozó actor és az átlagolt jelöltekből dolgozó critic továbbra is 32 rejtett egységes.
Az induló actor egyenletes a megengedett natív jelölteken; a padding kizárt.
Kapacitások: 512 akcióhely, 12 csataegység. Érvényes jelölteket nem vágunk le; túlcsordulás explicit hiba.

```text
r = natív végeredmény (+1 / −1 / 0)
    + 0.5 × elvesztett ellenséges HP / kezdeti ellenséges HP
    − 0.5 × elvesztett saját HP / kezdeti saját HP
    − 0.002 / Python-döntés
    − 0.1 × elköltött mana / kezdeti saját mana
```

A HP és mana előző/jelenlegi állapot különbségét használjuk, a terminális pillanatképet is beleértve.
A nézőpont a tényleges Python-oldal: védőként is helyesen számoljuk a saját és ellenséges veszteséget.
Nincs jutalom a puszta varázslásért. Az alakítás a gyorsabb, kevesebb veszteséggel és manapazarlással járó eredményt célozza;
nem állítjuk, hogy változatlanul hagyja az eredeti játék optimális policy-ját.
Az első rövid próbán a modell sok buffot használt rossz csataeredmény mellett. Ezért a végleges tanítás
2048 döntésnyi nyílt/vízi, Lightning Bolt / Magic Arrow bevezetéssel indul, majd új resetektől minden kontextus és hét varázslat elérhető.
A bevezető szakasz checkpointjai diagnosztikai pontok, végső modellként nem választhatók.

## Elkülönített tanítás és kiértékelés

- Két külön tanulási seed: 7 és 19; egyenként 8192 döntés, n_steps=256, batch=64, hat PPO epoch,
  learning rate=0,001, gamma=0,99, entrópia-együttható=0,01; CPU, egy Torch-szál.
- Tanítási natív seedek: 0–4095, a 36 alapkonfiguráció mintavételezett. A bevezetés után mind a négy kontextusnak ténylegesen szerepelnie kell.
- Validáció: 24 külön seedelt csata, 10000-től; csak checkpoint- és tanulásiseed-választásra.
- Teszt: 36 külön seed, 20000-től, az ismert profilok három változatával. Ez elsősorban új RNG-seedeken mér.
- Általánosítás/OOD: 24 csata, 30000-től, a tanításban egyáltalán nem szereplő lénytípusokból álló két új seregprofil,
  desert/swamp/lava terepekkel és sorceress/warlock/necromancer ostromokkal. Vízen a water terep marad.

Az OOD seregek: Mage/Unicorn/Steel Golem kontra Master Swordsman/Gargoyle/Mummy,
illetve Elf/Champion/Power Lich kontra Orc/Ogre Lord/Cavalry; nem pusztán új seedek az eredeti seregekkel.
Több tényező egyszerre változik, ezért egy OOD-kudarcot nem tulajdonítunk automatikusan egyetlen mechanikának.

A teljes modellválasztás megelőzi a végső teszt futtatását. Csak warmup utáni checkpoint választható,
greedy validációs győzelem, majd saját megmaradt HP alapján; egyezésnél a korábbi pont/seed marad.
Minden reset/konfiguráció, a tényleges tanítási varázslatszámok, seedek és fájlujjlenyomatok helyi jelentésbe kerülnek.
Az OOD és a teszt nem módosítja a súlyokat vagy a kiválasztást.

A kiválasztott modell mindkét halmazon hat kontrollmóddal együtt szerepel:
maszkos random; szabály varázslat nélkül; szabály Lightning Bolt/Magic Arrow prioritással;
greedy PPO; **ugyanaz a PPO letiltott varázslatokkal**; mintavételezett PPO.
A varázslatletiltás képesség-abláció, nem újratanított modell. A felkínált jelöltek, a pályák és a sebzések továbbra is natívak.
A szabályalapú kontroll nem tanítóadat és nem szakértői optimum. A két tanulási seed teszteredményét is külön rögzítjük.

## Futtatás és helyi videók

Meglévő opcionális desktop env builddel és játékadatokkal, a repó gyökeréből:

```powershell
uv run --project python --cache-dir .tools/uv-cache --extra battle-rl --locked python python/examples/battle_advanced.py --steps 8192 --seeds 7 19 --output build/python-env-advanced/new-run
# Rövid, csak train/validation próba:
uv run --project python --cache-dir .tools/uv-cache --extra battle-rl --locked python python/examples/battle_advanced.py --pilot --steps 1024 --seeds 7 --output build/python-env-advanced/new-pilot
# Saját, megbízható mentett SB3 ZIP újraértékelése tanítás nélkül:
uv run --project python --cache-dir .tools/uv-cache --extra battle-rl --locked python python/examples/battle_advanced.py --model build/python-env-advanced/final/advanced-seed-7.zip --output build/python-env-advanced/replay
```

Más binárishoz `--executable`, adatkönyvtárhoz `FHEROES2_DATA` használható. A kimeneti mappa legyen friss.
A script csak a repó figyelmen kívül hagyott `build/` fája alatt írhat.
A modellek, videók, képek, mérési JSON-ok és mentések nem kerülnek Gitbe/GitHubra.
A forrás, tesztek és leírás verziózott. A C++ motor és a normál/mobil játék függőségei nem változnak.

A tanítás nem renderel. Utána a tesztlista négy előre kijelölt csatájából készül 16 natív MP4:
négy kontextus × random/szabály/PPO/varázslat nélküli PPO. A felirat a Python-oldal színét, akcióját,
varázslatnevét és az eredményt is mutatja. A terminális csatakép megmarad.
Ezek döntési pillanatképek, állapotonként egy másodperccel; nem a normál játék folyamatos animációi.
A renderes és render nélküli natív akciósor/eredmény egyezését a program ellenőrzi.

A [médiaellenőrző](../python/examples/battle_advanced_media.py) visszaolvassa a videókat, ellenőrzi a forrás-/tervujjlenyomatot,
egymás mellé tett összehasonlításokat és helyi HTML-galériát készít. Opcionálisan további négy, fixen kiválasztott OOD-csatát is rögzít,
ugyanazzal a modellel és varázslatletiltással. Az eseteket nem győzelem alapján válogatjuk.

```powershell
uv run --project python --cache-dir .tools/uv-cache --extra battle-rl --locked --with matplotlib python python/examples/battle_advanced_media.py --run build/python-env-advanced/final --plot --unseen-videos
```

A Matplotlib csak az opcionális ábrához kell, ideiglenes `--with` csomagként.
Helyi galéria: `build/python-env-advanced/final/videos/index.html`; OOD: `final/unseen/videos/index.html`.
Ábra: `final/learning.png`. Összegzés: `final/report.json`; részletes esetek: `test-*.json`, `ood-*.json`.
A ZIP cloudpickle-t tartalmazhat, ezért csak saját/megbízható modell tölthető be.

## Teljes fennmaradó munkasorrend

2. **Kész:** [Gym/reset gyorsítás és párhuzamos tanítás](PYTHON_ENV_PERFORMANCE.md), bemért 1/2/4-env futásokkal.
3. [Linux/macOS és mobil SDK-buildellenőrzés](PYTHON_ENV_PLATFORMS.md) — külön CI-mátrix és eredmények.
4. Kiválasztott normál adventure-pályák végigjátszásának ellenőrzése és az elakadások javítása.
5. Adventure RL: feladathoz illő megfigyelés, jutalom, tanítás, teszt és helyi videók.
6. Kampánykezelés: továbbhaladás, átvitt hősök/jutalmak, kampányválasztások.
7. Igény szerint korlátozott láthatóság, több agentes Gym-wrapper és self-play.
8. Telepíthető platformonkénti Python-csomagok és automatikus motorkeresés (`pip install`).

A jelenlegi csatakísérlet nem teljes varázslat-/hős-/artifact-kombinációs tanítás és nem általános szakértői csata-AI.
