# Python env – 1. lépés: ellenőrzött tesztalap

Ellenőrizve: 2026-10-26. Alapcommit: `4ec988682`. Engine: 1.1.17.

## Elvégzett ellenőrzések

- A teljes helyi buildsegéd sikeresen lefutott `windows-local` / `RelWithDebInfo` módban; a Ninja nem talált újrafordítandó C++ fájlt. A nyelvi fájlok és a futtatási DLL-ek előkészítése is sikerült. Ez a meglévő build inkrementális ellenőrzése, nem tiszta újrafordítás.
- Eszközök: GCC 16.2.0 (MSYS2 Rev6), CMake 4.4.4, Ninja 1.13.2.
- A gyökérben és a buildmappában lévő executable SHA256-a megegyezett: `CAFF16D860EFC3FB796230812A391624EF98286220CE023ED193166FF25231A9`.
- A gyökérből indított játék főmenüje működött, a meglévő standard mentés betöltődött; a kalandtérkép, hős- és várnézet használható volt.
- Külön APPDATA tesztprofillal elindult a The Other Side pálya, majd a kezdőállapot mentése és visszatöltése is sikerült. A tesztpéldány normál kilépés után 0 kóddal zárult.
- A saját eredeti AUTOSAVE fájl SHA256-a a vizsgálat előtt és után megegyezett. Új játékot kizárólag az elkülönített profilban indítottunk.

Játékszabályt, C++ forrást, fordítási beállítást és a meglévő Windows-buildszkripteket ebben a lépésben nem módosítottuk.

## Két rögzített helyi mentés

Az elvárt, képernyőn ellenőrzött adatok és fájlujjlenyomatok: [baseline.expected.json](python_env/baseline.expected.json).

| | Fő tesztalap | Másodlagos betöltési referencia |
|---|---|---|
| Mentés | `build/python-env-baseline/fixtures/other-side-day1.sav` | `build/python-env-baseline/fixtures/forsaken-day2.sav` |
| Pálya | The Other Side / `maps/THEOTHER.MP2` | Forsaken Lands / `maps/FORSAKEN.MP2` |
| Méret | 36×36 | 72×72 |
| Játékos | Kék, Necromancer; zöld Wizard AI ellenfél; Normal | Zöld Knight; meglévő játékállás |
| Idő | 1. hónap, 1. hét, 1. nap | 1. hónap, 1. hét, 2. nap |
| Arany | 7500 | 8060 |
| Hős | Roxana, 1. szint; 9 Skeleton + 4 Zombie | Gwenneth, 1. szint; 42 Peasant |
| Vár | Timberhill; üres helyőrség, vendéghős Roxana | Quick Silver; 12 Peasant + 8 Archer |

Ez a két konkrét mentés a referencia. Friss pályaindításkor más hős vagy véletlen kezdőadat is előfordulhat; az elvárt Roxana/49 XP stb. értékek nem minden új játékra vonatkozó ígéretek.

A hősök számkoordinátáit még nem exportáltuk a futó motorból. A The Other Side eredeti MP2 mezőadataiban a két várbejárat nullától számozva `(3,24)` és `(32,24)`; ezek nem helyettesítik a későbbi save-state/API koordinátaellenőrzést. Roxana a mentésben Timberhill vendéghőse, Gwenneth a másik mentésben a vár melletti lakóhelynél áll. A pontos entitásazonosító, koordináta, mozgáspont, épületlista, varázslatlista és map seed a terv 3. lépésében lesz géppel ellenőrzött referenciaadat.

## Újraellenőrzés és biztonságos indítás

A projekt gyökeréből:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File script/windows/python-env-baseline.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File script/windows/python-env-baseline.ps1 -Action run
```

Az első parancs a mentések, pályák és AGG fájlok ujjlenyomatát, valamint a két executable azonosságát ellenőrzi. A helyi ellenőrzési eredményt a `build/python-env-baseline/verified-inputs.json` fájlba írja. Nem helyettesíti a játékon belüli állapotellenőrzést.

A `run` az eredeti mentésekből munkamásolatot készít az elkülönített profilba, beállítja a csak a gyermekfolyamatra érvényes adatútvonalakat, és ablakos játékot indít. Betöltés: **Load Game → Standard Game → other-side-day1**. A másik referencia neve `forsaken-day2`.

A folyamat végéig a parancs futva marad; a játék normál kilépése után visszaállítja a hívó környezetet. A runner az esetleges `HOME` környezeti változó jelenlétét külön jelzi, mert a motor Windows alatt is azt részesíti előnyben az APPDATA-val szemben.

Az izolált profil: `build/python-env-baseline/appdata/fheroes2`. Az itteni gyors/automatikus mentések nem az eredeti felhasználói profilba kerülnek. A fixtures mappát nem írja a játék; a runner onnan csak másol. A felhasználói profil beállításait a runner nem másolja vagy módosítja.

## Helyi fájlok és Git

A `build/` már figyelmen kívül hagyott könyvtár, a `.sav`, az AGG és az eredeti pályafájlok nem kerülnek a változtatáscsomagba. Az eredeti játékadatokat nem terjesztjük a forráskóddal.

A mentéspéldányok csak ezen a gépen vannak. Ha a buildkönyvtár törlődik, a két mentést külön megőrzött példányból kell visszaállítani a dokumentált ujjlenyomattal. Új klónban hiányukat a segéd egyértelműen jelzi; nem generál csendben más tartalmú referenciát. Teljesen generálható/terjeszthető saját elfogadási pálya későbbi bővítés lehet.

## Az első verzió támogatási profilja

Ez a célprofil, nem már működő API-képességlista:

- Standard egyjátékos session, egy külső játékos és beépített AI ellenfél.
- Mentés betöltése/reset, később seedelt pályaindítás.
- Saját hős/vár/sereg/tárgy és játékosnak látható térkép lekérése.
- Térképi mozgás, alap erőforrásfelvétel, körváltás.
- Építés, toborzás, sereg/tárgy kezelés.
- Kincsesláda és szintlépés típusos választásai, térképből induló csata és visszatérés.
- Kalandtérkép, vár, hős és aktív csata RGB-render.
- Később Gymnasium adapter ugyanazon motor fölött.

A The Other Side jó kis pálya indításhoz, lekérdezéshez, mozgáshoz, várhoz és ládákhoz. A pálya nem bizonyít minden speciális objektumot vagy varázslatot, és önmagában nem garantál gyors hozzáférést minden későbbi elfogadási helyzethez. A csata/szintlépés/tárgycsere szakaszánál célzott további mentés szükség szerint készül. Nem támogatott interakciót az envnek azonosíthatóan kell jeleznie.

## Fontos indítási tapasztalatok

1. A buildmappából közvetlenül indított exe környezeti adatútvonal nélkül „Data files not found” képernyőt adott. A gyökérben lévő exe működött. A Python-indító ezért explicit `FHEROES2_DATA` útvonalat és munkakönyvtárat fog használni; az exe helyére nem hagyatkozhatunk.
2. A buildszkript MSYS2 nyelvigenerálása a korlátozott futtatási környezetben `NtCreateDirectoryObject ... 0xC0000022` hibát adott. A szükséges jogosultsággal az eredeti szkript változtatás nélkül sikeresen lefutott. Ez nem C++ fordítási hiba.
3. A tesztprofilban a valódi grafikus indítást a folyamat végéig élő PowerShell-futtatással igazoltuk. A korábbi rövid háttérindítási próbákat nem tekintjük sikeres indításnak.
4. Headless, Python-protokoll, seedelt determinisztikusság és steps/s ebben a lépésben még nem lett megvalósítva vagy igazolva.

## Következő lépés

A 2. lépés azóta elkészült: [Python-kapcsolat](../python/README.md). Következik a **3. lépés**, a mentésbetöltés és a csak olvasó játékállapot-API.
Az itt rögzített executable-ujjlenyomat az 1. lépés eredeti buildjének történeti adata; a segéd mindig az aktuális gyökérbeli és buildbeli exe egyezését ellenőrzi.
