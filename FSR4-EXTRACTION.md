# Extract FSR 4 Lite from your AMD driver / Извлечение FSR 4 Lite

## Easiest: inside Decky FrameGen Hub 0.2.2+

1. Download an official AMD **Windows** graphics driver `.exe` with the Lite model, for example
   [Adrenalin 26.10.1](https://www.amd.com/en/resources/support-articles/release-notes/rn-rad-win-26-10-1.html).
   Save the file; do not run the installer. This package was tested; some older/OEM packages may lack the files.
2. In the plugin, open **FSR 4 libraries → Extract FSR 4 libraries from driver (.exe)** and select the file.
3. Wait for extraction/import, then choose the game → **Upscaler → FSR 4 Lite (INT8)**.

You can instead select **Import libraries from ZIP**.
Both `amdxcffx64.dll` and `amdvkffx64.dll` are required, with matching versions and Lite model markers.
When updating the same way, closed games already using Lite get the new files automatically. Close a running
game and select Lite again to update it. Existing generator and render-quality settings are preserved.

No AMD DLL is shipped in the plugin or the extraction-tool release. Libraries and their generated ZIP remain
on your device in `~/homebrew/data/Decky FrameGen Hub/` (`fsr4-libraries/` and `fsr4-archives/`).
The watermark is off by default; enable it temporarily to confirm `FSR4L-i8` in actual gameplay.

## Standalone script: SteamOS first

Download and extract **FSR4-Extractor.zip** from the plugin release. In SteamOS Desktop Mode, open Konsole
in the extracted `FSR4-Extractor` folder and run (use your actual downloaded filename):

```sh
sh tools/extract-fsr4.sh "$HOME/Downloads/whql-amd-software-adrenalin-edition-26.10.1-win11-c.exe"
```

Or run `sh tools/extract-fsr4.sh` and enter the driver path when asked. Paths with spaces work.
Requires Python 3 (normally available on SteamOS). No pip packages, sudo, Windows or driver installation.
If 7-Zip is absent, the tool downloads official portable 7-Zip 26.06 for Linux x64/ARM64 or macOS, checks its
pinned SHA-256 and runs it from your user cache. Internet is needed for that first download only.
7-Zip source/release: https://www.7-zip.org/download.html and https://github.com/ip7z/7zip/releases/tag/26.06.
To work offline, install 7-Zip beforehand or pass `--sevenzip /path/to/7zz` to the Python script.

The resulting **`AMD-FSR4-Libraries-<DLL-version>.zip`** appears next to the driver. Import that ZIP in the plugin.
It contains just the two DLLs, their SHA-256/version manifest and a short note. Newer compatible driver files
work with the same command. The DLL file version (for example 2.4.0.4370) differs from the model version (4.1.2).

Linux/macOS alternative:

```sh
python3 tools/extract-fsr4.py "/path/to/amd-driver.exe"
```

Windows: install Python 3 and 7-Zip, then drag the driver `.exe` onto `tools\extract-fsr4.cmd`, or run:

```bat
py -3 tools\extract-fsr4.py "C:\Users\YourName\Downloads\amd-driver.exe"
```

Optional output folder: `python3 tools/extract-fsr4.py "/path/to/driver.exe" -o "/path/to/output"`.
Tested end to end on macOS with the downloaded driver, and Linux on the ROG Xbox Ally X.
Windows launcher is provided but has not been tested on Windows.

## Кратко по-русски

Проще всего выбрать скачанный `.exe` драйвера в самом плагине: **FSR 4 libraries → Extract FSR 4 libraries
from driver (.exe)**. Плагин извлечёт и примет библиотеки автоматически. Ручной вариант — импорт ZIP
с двумя DLL. Для новой игры после импорта выберите **FSR 4 Lite (INT8)**.

Отдельно: распакуйте **FSR4-Extractor.zip**, откройте терминал в папке `FSR4-Extractor` и выполните команду выше,
подставив свой путь к драйверу. На выходе рядом с драйвером появится ZIP для импорта в плагин.
Никаких команд с sudo и установки Windows-драйвера не требуется.

При следующем обновлении укажите новый драйвер тем же способом. У запущенных игр файлы не меняются.
Утилита проверяет формат PE, метаданные AMD/FidelityFX, совпадение версий и признаки Lite, но не проверяет
криптографическую подпись издателя. Используйте драйвер из официального источника.
DLL сохраняют условия AMD; инструмент не предоставляет прав на их распространение.
