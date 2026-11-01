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

A végleges, elkülönített futás mért eredményeit a befejezés után rögzítjük itt.

## Teljes fennmaradó sorrend

6. Kampányátmenetek, átvitt hősök/jutalmak és kampányválasztások.
7. Igény szerint láthatósági korlátozás, több agentes Gym-wrapper és self-play.
8. Platformonkénti telepíthető Python-csomagok, csomagolt motor, automatikus motorkeresés,
   `pip install` és tiszta telepítésből ellenőrzött példák; az eredeti játékadatok külön biztosítandók.

Ezek mellett a jó teljes játékstratégia megtanulása további kísérleti munka: több pálya,
hosszabb tanítás, jobb seregérték-/gazdaságjellemzők és a makróprofil bővítése nem válik automatikusan kész megoldássá ettől az első méréstől.
