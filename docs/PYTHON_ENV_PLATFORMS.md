# Desktop és mobil platformellenőrzés

A Python-bővítés csak desktop Windows/Linux/macOS célra, explicit `ENABLE_PYTHON_ENV=ON`
kapcsolóval épül. Az alapérték továbbra is OFF. A mobilmotor nem igényel Python-, Gym-, NumPy- vagy Torch-telepítést.

## Ellenőrzött buildmátrix

A külön [ellenőrző workflow](../.github/workflows/python-env-platforms.yml) csak olvasási GitHub-jogosultságot kér.
A saját `codex/python-env-bootstrap` ágon releváns kódváltozásra indul, és kézzel is indítható,
ha a workflow az alapértelmezett ágon is szerepel. A meglévő upstream workflow-kat,
mobilprojektet, függőségeket és kiadási folyamatokat nem írja át.

| Platform | Konfiguráció | Ellenőrzés |
|---|---|---|
| Ubuntu 24.04 | Python OFF | Debug, warning-as-error, játék + eszközök, telepítés |
| Ubuntu 24.04 | Python ON | Ugyanez + natív headless policy + Python transport + valódi Gym/reset/RGB |
| macOS 15 | Python OFF | Debug, warning-as-error, játék + eszközök, telepítés |
| macOS 15 | Python ON | Ugyanez + natív headless policy + Python transport + valódi Gym/reset/RGB |
| macOS 15 | Python OFF, app bundle ON | Meglévő `.app` csomag, fordítás és dylibbundler |
| Android | Meglévő Gradle/NDK, Python nélkül | Debug APK + AAB, armeabi-v7a/arm64-v8a/x86/x86_64 |
| iOS | Meglévő Xcode-projekt, Python nélkül | iOS Simulator SDK, aláírás nélküli build |

Az iOS cél általános szimulátor: nem függ a runnerre telepített konkrét iPhone-modell nevétől.
A workflow nem készít release-t, nem használ aláírókulcsot és nem tölti fel a játék eredeti adatait.
Csak fordítási adatbázis, CMake-cache és szöveges/JSON ellenőrzési eredmény lehet CI-artifact.

## Mit védenek a próbák?

A [fordításiprofil-ellenőrző](../script/python/check_build_profile.py) a tényleges CMake
`compile_commands.json` állományban ellenőrzi a kiadott `fheroes2` target minden játékforrását.
OFF esetén egyetlen játékfordítás sem kapja a `FHEROES2_ENABLE_PYTHON_ENV` definíciót.
ON esetén csak a belépési pontból és adapterekből álló tízforrásos kijelölt csoport kaphatja meg;
a külön fixture-target szándékosan eltérő tesztbeállításait nem keverjük a játékéval.

A natív `fheroes2_headless_checks` ellenőrzi a scoped headless állapot visszaállítását,
valamint a videó/input inicializálás tiltását headless módban.
A meglévő `test_transport.py` valódi folyamatokkal teszteli a protokollt és hibaágakat, assetek nélkül.

A [hordozható smoke példa](../python/examples/platform_smoke.py) valódi szárazföldi és hajós csatát indít:
azonos seedű, azonos PID-es resetegyezés, numerikus megfigyelés, RGB-kép,
render előtti/utáni teljes világállapot-egyezés, véges Gym-epizód és szabályos folyamatlezárás.
Nem használ működő SDL videó-/hangdrivert; a runtime mindkettőnél inicializálatlan marad.
A kép memóriában ellenőrzött, nem kerül a repóba vagy CI-artifactba.
A CI az eredeti demoletöltő scriptet és annak rögzített SHA256-ellenőrzését használja;
a helyi próba a meglévő adatokat csak olvassa.

```powershell
uv run --project python --extra gym --locked python python/examples/platform_smoke.py --executable build/windows-local/fheroes2.exe --data . --output build/python-env-platforms/windows-smoke.json
```

Ez build- és célzott runtime-ellenőrzés. Nem állít teljes Linux/macOS adventure-végigjátszást,
mobil eszközös érintőképernyő-/hang-/teljesítménytesztet, iOS fizikai eszközös aláírt terjesztést,
vagy minden történeti OS-/SDK-verzió támogatásának újraminősítését.

## Eredmények

**7/7 sikeres job a végső, teljes CI-futásban**, beleértve az Android és iOS megismételt buildjét is.

Ellenőrzött kódcommit: `62e9657d0c793c48ef45a024c75d495aaf1090ac`.
[Teljes buildmátrix és naplók](https://github.com/Taranyi/fheroes2/actions/runs/41250904849).
A kódcommit után csak dokumentációs változások következnek.

A desktop jobok mind sikeresek: Linux GCC 13.3.0 x86-64 és macOS AppleClang 17 arm64,
Python OFF/ON, továbbá a macOS `.app` csomag. Minden esetben 233 tényleges játékfordítási parancs ellenőrzött:
OFF-nál nulla, ON-nál pontosan tíz kijelölt forrás kap Python-adapter definíciót.
Linuxon és macOS-en külön-külön **14/14 protokollteszt**, natív headless policy és két valódi
Gym-csata/reset/render/lezárás sikeres. A runtime Python 3.12 alatt futott.

Az Android meglévő Gradle 8.13 / NDK 27.0.12077973 buildje elkészítette a debug APK-t és AAB-t,
mind a négy ABI natív fordításával: `armeabi-v7a`, `arm64-v8a`, `x86`, `x86_64`.
Az iOS Xcode 16.4 / build 16F6 alatt sikeres, arm64 és x86_64 szimulátorváltozattal,
aláírás nélkül. Ez a repó meglévő SDK-/minimumverzió-beállításaival végzett ellenőrzés.

A helyi Windows ON/OFF fordításiprofil-ellenőrzés és a két valódi Gym-próba is sikeres.
Az Android/iOS/Emscripten CMake-flageknél a desktop adapter ON beállítása mindhárom esetben
a szándékos, célzott hibaüzenettel elutasított; ez külön konfigurációs gate-próba, nem Emscripten-build.
A helyi Windows executable SHA256-a változatlan:
`b7e7284b9130c538c6c6564139909344741f8d7328b2fab30730fedfd776f58f`.

A natív játékforrásokat, `CMakeLists.txt` fájlokat, Android-/iOS-projektfákat, eredeti
mobil workflow-kat és függőségverziókat ebben a munkaszakaszban nem módosítottuk.
A teljes `android/` és `ios/` projektfa a tárolt upstream referenciához képest is változatlan.
Az első CI-kísérletben a külön demómappából hiányzott a repó saját H2D-erőforrása;
a tesztadat-előkészítés javítása után a desktop runtime-próbák is sikeresek, motorváltoztatás nélkül.

Helyi bizonyítékok: `build/python-env-platforms/windows-smoke.json`, `mobile-gates.json`,
`first-run.json` és `final-report.json`. Ezek figyelmen kívül hagyott mérési kimenetek.

## Teljes fennmaradó sorrend

4. Normál adventure-pályák végigjátszása, elakadások javítása.
5. Adventure RL: megfigyelés, jutalom, tanítás, kiértékelés és helyi videók.
6. Kampányátmenetek, átvitt hősök/jutalmak és kampányválasztások.
7. Igény szerint korlátozott láthatóság, több agentes Gym-wrapper és self-play.
8. Telepíthető platformonkénti Python-csomagok: csomagolt motor, automatikus motorkeresés,
   `pip install` és tiszta környezetből ellenőrzött példák. Az eredeti játékadatok külön biztosítandók.
