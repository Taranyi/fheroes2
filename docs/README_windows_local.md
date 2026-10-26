# Windows: helyi fordítókörnyezet és VS Code

A fordító, a CMake, a Ninja, a GDB és az SDL2 függőségei a projekt
`.tools/msys64` mappájában vannak. A fordítás nem igényel Visual Studiót,
rendszerszintű PATH-módosítást vagy a `C:/dev/msys64` további használatát.
A `.tools` és a fordítás eredményei nem kerülnek Gitbe.

## VS Code

Nyisd meg a projekt gyökérmappáját. A Microsoft C/C++ bővítmény szükséges
a hibakereséshez és az IntelliSense-hez (ezen a gépen már telepítve van).

- **Ctrl+Shift+B**: fordítás, DLL-ek előkészítése és fordítások generálása.
- **F5**: fordítás, majd indítás GDB hibakeresővel.
- **Ctrl+F5**: fordítás, majd indítás hibakeresés nélkül.
- **Terminal > Run Task > fheroes2: run**: fordítás és indítás terminálból.

Az alapbeállítás optimalizált, hibakeresési információt tartalmazó
`RelWithDebInfo` változat. Ha a változók vizsgálatát az optimalizálás zavarja,
válaszd az **fheroes2 (Debug, no optimization)** indítási beállítást.

## Parancssorból

A projekt gyökerében, PowerShellből:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File script/windows/local.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File script/windows/local.ps1 -Action run
powershell -NoProfile -ExecutionPolicy Bypass -File script/windows/local.ps1 -Preset windows-debug
```

Az alapváltozat itt készül el: `build/windows-local/fheroes2.exe`.
A projekt eredeti CMake-beállítása a gyökérbe is másolja: `fheroes2.exe`.
A segédszkript a szükséges DLL-eket mindkét helyre odateszi.
A fordítás legfeljebb 8 szálat használ; ezt a `-Jobs` kapcsolóval állíthatod.
A magyar nyelvi fájl is elkészül (`files/lang/hu.mo`).

## Az eredeti játék fájljai

A teljes Heroes of Might and Magic II telepítésből másold ide a mappákat:

```text
fheroes2/
  DATA/
    HEROES2.AGG
    HEROES2X.AGG       (ha van Price of Loyalty kiegészítő)
    ...               (a DATA mappa teljes tartalma)
  MAPS/               (az eredeti pályák, a meglévő maps mappába olvad)
  MUSIC/              (ha van; külső zenék)
  ANIM/               (ha van; videók)
  files/              (a projekt saját fájljai, hagyd meg)
  fheroes2.exe
```

A teljes `DATA` és `MAPS` mappát érdemes átmásolni. Windows alatt a
`MAPS` és a már meglévő `maps` ugyanaz a mappa: összemásoláskor a projekt
meglévő `.fh2m` pályáit is tartsd meg. A `DATA` nem azonos a `files/data`
mappával. A játékadat nem szükséges a fordításhoz, csak a játék indításához.

Ha nincs teljes játékod, a projekt saját demóletöltőjét a projekt gyökeréből
futtathatod: `script/demo/download_demo_version.bat`.
Ez internetkapcsolatot igényel; a környezet beállítása nem tölti le automatikusan.

## A környezet újra létrehozása

A jelenlegi mappában a környezet már elő van készítve. Új klón esetén egy
meglévő MSYS2 telepítésből külön helyi másolat készíthető:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File script/windows/setup-local.ps1 -Msys2Source C:/dev/msys64
```

A szkript kizárólag a projektben lévő másolatot frissíti és telepíti bele
a függőségeket. Ehhez internetkapcsolat és néhány GB szabad hely szükséges.
Az elkészült `.tools` mappát a projekt többi részével együtt megőrizheted;
nem kell minden fordításnál letölteni. Ha másik elérési útra költözteted
a projektet, a `build/windows-local` és `build/windows-debug` generált
mappákat töröld, majd fordíts újra (a CMake gyorsítótára abszolút utakat tárol).

A csomagok forrása a hivatalos [MSYS2](https://www.msys2.org/docs/environments/)
UCRT64 környezete; a játékadatok leírása a projekt [README.txt](README.txt)
útmutatóján alapul.
