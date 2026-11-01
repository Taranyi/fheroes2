# Első adventure RL-kísérlet

Valódi natív kalandtérképen tanítunk MaskablePPO-t. A kísérlet külön Python task;
a C++ játék, a teljes `HeroesEnv`, az alapcsomag függőségei és a mobilprojektek változatlanok.
A kísérlet omniscient: minden oldal állapota lekérdezhető. A tanított stratégiai policy ebből
akciónként 58 számszerű jellemzőt kap, nem a teljes állapot JSON-ját.

## Feladat és vezérlés

[AdventureTask](../python/examples/adventure_task.py) legfeljebb 512 natívan validált stratégiai jelöltet ad:

- Mozgás nyolc sugár mentén, legfeljebb nyolc mezőre: szomszédos célok, interaktív objektumok és sugáronként a legtávolabbi jogszerű cél.
  A teljes útvonalat, mozgáspontköltséget és interakciókat a motor ellenőrzi és hajtja végre.
- Várépítés, maximális toborzás, várból a látogató hősnek maximális összevonható seregátadás.
- Hősbérlés, váranként/naponként egy ajánlatfrissítés, hajóvétel, varázskönyv és a célparaméter nélkül elérhető adventure varázslatok.
- Kör vége, amely a többi oldal eredeti beépített AI-ját is lefuttatja.

Ez szándékosan korlátozott stratégiai **makróprofil**, nem a teljes Gym API minden akciójának másolata.
Nincs itt kereskedés, tetszőleges seregfelosztás, elbocsátás vagy hősök közötti készletoptimalizálás.
Profilkapacitás-túllépés vagy motorhiba kivétel, nem hamis vereség/győzelem.
A helyben változatlan állapotot eredményező mozgás ismétlése a következő állapotváltozásig tiltott.

A csatákat minden policy esetében ugyanaz a determinisztikus szabályvezérlő oldja meg;
a natív választások első felkínált opcióját választjuk, szöveges válasz esetén üres szöveggel.
A hőstalálkozót seregcsere nélkül lezárjuk. Ezek nem most tanított képességek.
A map eredeti emberi/AI szabályprofiljai megmaradnak; a Python vezérli az eredetileg embernek kijelölt oldalt.

A megfigyelés például a gazdaságot, sereget, hősképességeket, várakat, célobjektumot,
látogatottságot, ellenséges/semleges várhoz vezető becsült tereptávolságot és a cél körüli ismeretlen mezők számát tartalmazza.
Az utóbbi a jelenlegi fogállapotból számolt geometriai jellemző, nincs jövőbeli szimuláció vagy tanítói akció.
Hosszabb út során a ténylegesen feltárt terület ennél nagyobb is lehet.
Az alapértelmezett `info['state']` továbbra is teljes, másolt natív világállapot;
a párhuzamos tanítás `rich_info=False` módja ezt nem küldi át minden lépésben a workerből.

## Saját jutalom

`r = 5 * native_result + 0.99 * Phi(next) - Phi(previous) - 0.005 - 0.02 * elapsed_days - 0.02 * stalled_move`

Itt a `native_result` valódi natív győzelemnél +1, vereségnél −1, egyébként 0. A potenciál:

```text
Phi(s) = 5 * explored / map_tiles + 1.5 * castles + 0.15 * heroes
       + 0.25 * ln(1 + army) + 0.15 * ln(1 + mobile)
       + 0.2 * ln(1 + daily_gold_income / 500) + 0.25 * ln(1 + experience / 1000)
```

A sereg itt összesített **darabszám**, nem harcérték: egy sárkány és egy paraszt darabszáma azonos súlyú.
Az `army` a saját hősök és várőrségek együttese, a `mobile` csak a hősöké.
Nincs aranyforgatásért, seregszétvágásért vagy kattintásonként adott növekedési bónusz.
Azonos állapotba visszatérő ciklus diszkontált potenciáljutalma nem pozitív.
A potenciálkülönbség alakja a [Ng–Harada–Russell-féle reward shapinget](https://people.eecs.berkeley.edu/~pabbeel/cs287-fa09/readings/NgHaradaRussell-shaping-ICML1999.pdf) követi;
ez nem ígéret arra, hogy véges tanításból azonnal jó stratégia lesz.

Valódi terminális állapotban `Phi(next)=0`; külső lépés-/naplimitnél megmarad a következő állapot és a bootstrappelhető megfigyelés.
Ez a [Gymnasium termination/truncation szerződését](https://gymnasium.farama.org/v0.27.0/tutorials/handling_time_limits/) követi.
A `sparse` kontroll csak a potenciált hagyja el, a többi jutalom és a feladat azonos.

## Tanítás és elkülönített mérés

[A futtató](../python/examples/adventure_rl.py) CPU-s sb3-contrib MaskablePPO-t használ,
58→32→1 közös jelöltpontozóval, külön átlagolt critic-kel. A kezdeti actor egyenletes eloszlású a jogszerű akciókon.
Négy külön Python-worker és négy saját natív motor gyűjti a lépéseket Windows-kompatibilis `spawn` módban.
Az akciómaszk a worker környezetében van, a [MaskablePPO dokumentált előírásának](https://sb3-contrib.readthedocs.io/en/master/modules/ppo_mask.html) megfelelően.
Adventure resetnél friss motorfolyamat indul; a korábbi battle-only gyors resetet itt nem állítjuk támogatottnak.

A keret futás előtt `plan.json`-ba rögzíti a seedeket és limiteket:

| Rész | Pálya | Seedek | Limit |
|---|---|---|---|
| Tanítás | THEOTHER.MP2 | 0–4095 közül epizódonként | 384 döntés / 64 nap |
| Validáció | THEOTHER.MP2 | 10000–10002 | 128 döntés / 32 nap |
| Elkülönített teszt | THEOTHER.MP2 | 20000–20005 | 128 döntés / 32 nap |
| Új pálya | BROKENA.MP2 | 30000–30001 | 128 döntés / 32 nap |
| Hosszú játék | THEOTHER.MP2 | 40000 | 1536 döntés / 128 nap |

A naplimit az első határátlépő stratégiai döntés után érvényesül.
A validáció és a fő teszt tehát **korai játékszakasz**; külön mérjük a hosszabb natív eredményt.
Sem a lépéslimit, sem a nagyobb feltárt terület nem számít győzelemnek.
A hosszú ellenőrzést a kiválasztott dense modellen, a véletlen és szabályalapú kontrollon futtatjuk.

Két dense tanítási seed (7, 19) és egy azonos kezdősúlyú sparse kontroll (7) kap egyenlő döntéskeretet.
Checkpoint- és modellválasztás csak validációból: győzelmek, kevesebb natív vereség, feltárt mezők, mobil sereg változása;
holtversenyben korábbi checkpoint/seed. A véletlen kontroll a tényleges kezdeti actor eloszlásának felel meg;
a nullázott kezdeti actor greedy változata mindig az első akciót választaná, ezért az nem korrekt véletlen kontroll.
Az egyszerű szabályalapú referencia nem szakértői AI.
A videókészítő `paired-analysis.json` fájlja a hat tesztseed párosított különbségeire rögzített
seedű, 10 000 mintás bootstrap-leírást ad. Ez ezen a kevés seeden belüli bizonytalanságot mutatja;
nem bizonyít általánosítást tetszőleges pályákra, és nem helyettesít több független tanítási seedet.

## Futtatás és helyi videók

Az eredeti játékadatok és a két map helyben szükségesek. A meglévő opcionális `battle-rl` extra az adventure tanításhoz is elegendő:

```powershell
uv run --project python --cache-dir .tools/uv-cache --extra battle-rl --locked python python/examples/adventure_rl.py --output build/python-env-adventure-rl/new-run --steps 8192 --workers 4
uv run --project python --cache-dir .tools/uv-cache --extra battle-rl --with matplotlib python python/examples/adventure_rl_media.py --run build/python-env-adventure-rl/new-run --plot
```

`--pilot` csak validációt nyit meg; a végső tesztesetekhez nem fér hozzá.
Új futáshoz új kimeneti könyvtár kell. A modellek kizárólag saját, ellenőrzött helyi futásból tölthetők vissza.

[A videókészítő](../python/examples/adventure_rl_media.py) a tanítás előtt kijelölt első két tesztseedet játssza újra.
A renderes és eredeti futás minden natív parancsának hash-e, végmetrikái, jutalomrészei és terminális jelzései egyezniük kell.
Ellenőrzi a források, mapok, assetek, motor és modellek SHA256-át, majd a videók képkockaszámát és dekódolhatóságát.
A videó valódi natív döntési pillanatképekből áll: stratégiai döntésenként 0,25 másodperc,
belső csata-/választáslépésenként 1/12 másodperc, köztes játék-animációk nélkül.
A csata képe nem jelenti azt, hogy a stratégiai policy tanulta a csatavezetést.

Minden ZIP, MP4, PNG, HTML és futási JSON az ignorált `build/` fában marad. Ezeket nem commitoljuk és nem töltjük GitHubra.
A források, reprodukálási leírás és tesztek kerülhetnek a saját forkba.

## Eredmények

Helyi futás: `build/python-env-adventure-rl/final/`. Három valódi, egyenként 8192 döntéses tanítás,
összesen 24 576 stratégiai döntés, 63 befejezett tanítóepizód; ebből 21 natív terminális vereség, 0 győzelem.
A többi epizód a külső tanítási limiten ért véget. Mindhárom policy súlyai ténylegesen változtak;
a dense/sparse 7-es seed kezdősúlyai bitpontosan egyeztek. Mindhárom futás négy saját natív motort használt és zárt le 0-s kilépéssel.

A validáció a dense/7 modell 8192-es, a dense/19 és sparse/7 modellek 4096-os checkpointját választotta.
Az összesített dense modellválasztás a 7-es seedre esett. A 19-es seed utolsó checkpointja gyengébb lett a köztesnél;
a több tanítás ebben a kis kísérletben nem adott monoton javulást.

Hat elkülönített THEOTHER tesztseed, legfeljebb 128 döntés / 32 nap:

| Vezérlő | Új mezők átlaga | Mobil sereg változása | Záró nap átlaga | Natív győzelem / vereség / limit |
|---|---:|---:|---:|---|
| Maszkos véletlen | 245,5 | +70,2 | 10,2 | 0 / 0 / 6 |
| Egyszerű szabály | 299,2 | +59,3 | 25,7 | 0 / 1 / 5 |
| Dense/7, kiválasztott | 266,7 | +111,2 | 4,2 | 0 / 0 / 6 |
| Dense/19 | 194,8 | +23,3 | 13,5 | 0 / 2 / 4 |
| Sparse/7 | 191,2 | +57,7 | 6,7 | 0 / 0 / 6 |

**Részleges tanulás, nem nyerő adventure stratégia.** A kiválasztott dense modell a véletlennél átlagosan
8,6%-kal több mezőt és +41 mobil katonát adott, utóbbi mind a hat párosított esetben nagyobb volt.
A felfedezéskülönbség bootstrap 95%-os intervalluma azonban −59,8…+101,5 mező: a véletlenhez képest ez nem stabil bizonyíték.
A mobil darabszámkülönbségé +28,5…+50,2. A sparse/7 kontrollhoz képest a felfedezés átlagos különbsége +75,5 mező,
az intervallum +7,2…+142,7; ezek csak ezen hat seeden belüli leírások, két tanítási seedből nem következik általános RL-siker.

Az akciók is megmutatják a korlátot: a kiválasztott modell hat epizódban 37 hőst bérelt a véletlen 24-ével szemben,
334-szer varázsolt és mindössze 19-szer adott kört, seregátadást egyszer sem választott.
Az első előre kijelölt videós esetben 70 `View Artifacts` és 9 `View Mines` varázslás szerepel;
ennek külön diagnosztikai visszajátszási hash-e is egyezik a tesztével (`behavior-dense_7.json`).
A varázslás nem kap külön pozitív jutalmat, mégis ilyen rossz ismétlési mintát tanult a véges PPO-futás.
A nagyobb mobil létszám jelentős része hősbérlésből jön, nem megtanult seregösszevonásból vagy jobb harcértékből.
A kiválasztott modell tesztjén a bevétel és saját várak száma nem nőtt.
Az epizódok eltérő játéknapig jutnak ugyanannyi döntésből; a rövid teszt nem azonos napig tartó verseny.

A négyworkeres tanítás mért sebessége 43,2 / 54,7 / 44,3 stratégiai döntés/s (dense/7, dense/19, sparse/7),
a modell inicializálásával, friss resetekkel és PPO-frissítésekkel, a validáció idejét külön levonva.
Ez megfigyelt tanítási áteresztés ezen a gépen, nem tiszta natív motorbenchmark vagy battle-only FPS.
Minden checkpoint és idő a futási JSON-okban szerepel.

Ellenőrzés: a 254 helyi tesztből 253 közvetlenül átment; egy meglévő, hardlinket létrehozó assettesztet
a korlátozott Windows-futtatás fájljogosultsága blokkolt, majd normál jogosultságú célzott újrafuttatásban az is sikeres lett.
Az új hét teszt az igazi Gym-szerződést, natív mozgást/felderítést, seregmegmaradást,
jutalominvariánsokat, terminálás/limit különbségét, PPO-frissítést/visszatöltést és MP4-visszajátszást ellenőrzi.
A [platform-CI](https://github.com/Taranyi/fheroes2/actions/runs/41270104420) 7/7 jobja sikeres a `2b84de38a` forráscommiton:
Linux/macOS OFF/ON, macOS bundle, Android négy ABI és iOS-szimulátor.
Ez a meglévő platformok build-/füsttesztje; az adventure PPO tanítását helyben Windows CPU-n mértük.

BROKENA, két új seed, ugyanaz a rövid limit: a kiválasztott modell 1139,0 új mezőt adott a véletlen 746,0 és
a sparse/7 202,5 mezőjével szemben. A mobil seregváltozás +94,5 volt a véletlen +97,0-jához képest,
tehát ez a mutató itt nem javult. A második dense modell csak 176,0 mezőig jutott; mind a tíz epizód limitált, győzelem nélkül.
Ez kevés eset egyetlen új pályán, nem általános pályatámogatás vagy stabil policy-általánosítás bizonyítéka.

A hosszú THEOTHER-próba (seed 40000; max. 1536 döntés / 128 nap) mindhárom vezérlőnél valódi natív vereséggel zárult:

| Vezérlő | Stratégiai döntés | Záró nap | Új mező | Eredmény |
|---|---:|---:|---:|---|
| Véletlen | 486 | 47 | 472 | Natív vereség |
| Egyszerű szabály | 120 | 26 | 492 | Natív vereség |
| Kiválasztott dense/7 | 985 | 64 | 388 | Natív `LOSS_TIME` (2048), nem külső truncation |

A modell a hosszú futáson sem foglalt új várat, a végén a toborzott sereg a várőrségben maradt.
A 64 napig tartó futás önmagában nem jobb stratégia: nem teljesítette a győzelmi célt és a felfedezésben is elmaradt a kontrolloktól.
Ez a kísérlet a teljes natív játékban használható RL-adatgyűjtést, tanítást, kiértékelést és modell-visszajátszást igazolja;
**erős, teljes pályát nyerő adventure agent még nincs**.

Helyi kimenetek:

- `build/python-env-adventure-rl/final/report.json`, `plan.json`: teljes mérés és előre rögzített terv.
- `test-*.json`, `transfer-*.json`, `full-*.json`: minden epizód metrikái, eredménye, parancsszámai és akcióhash-e.
- `dense-7/selected.zip`, `dense-19/selected.zip`, `sparse-7/selected.zip`: visszatölthető, saját tanított modellek.
- `learning.png`, `paired-analysis.json`, `videos/index.html`: görbe, párosított összehasonlítás és helyi videógaléria.
- `videos/media-verification.json`: renderes replay és MP4-ellenőrzés; a videók a tanítás előtt kijelölt két tesztseedből készülnek.
- `build/python-env-adventure-rl/tests-summary.json`, `platform-report.json`: helyi és platformellenőrzés, részletes logokkal.

## Teljes fennmaradó sorrend

5/B. Erősebb adventure policy: fölösleges információs-varázslási ismétlések kezelése a taskban,
   harcérték/gazdaság/seregösszevonás jobb megfigyelése és feladatai, fokozatos várfoglalási tanítás, több pálya és hosszabb tanítás.
   Ez új kísérleti protokollt és új elkülönített tesztseedeket igényel; a mostani teszteredményekre nem hangoljuk utólag a közölt modellt.
6. Kampányátmenetek, átvitt hősök/jutalmak és kampányválasztások.
7. Igény szerint láthatósági korlátozás, több agentes Gym-wrapper és self-play.
8. Platformonkénti telepíthető Python-csomagok, csomagolt motor, automatikus motorkeresés,
   `pip install` és tiszta telepítésből ellenőrzött példák; az eredeti játékadatok külön biztosítandók.

Ezek mellett a jó teljes játékstratégia megtanulása további kísérleti munka: több pálya,
hosszabb tanítás, jobb seregérték-/gazdaságjellemzők és a makróprofil bővítése nem válik automatikusan kész megoldássá ettől az első méréstől.
