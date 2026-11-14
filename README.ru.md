# Decky FrameGen Hub — инструкция

Плагин для [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader): генерация кадров в играх под Proton
на Steam Deck, ROG Ally и других Linux-портативках (SteamOS, Bazzite, CachyOS Handheld). Для каждой игры можно выбрать
свой генератор и свой профиль настроек.

| Генератор | Когда выбирать | Что нужно |
|---|---|---|
| **Lossless Scaling (lsfg-vk)** | Максимум FPS и лучший отклик; работает в **любой** игре | Своя купленная Lossless Scaling в Steam, ветка **lsfg-vk** |
| **XeFG** | Самая чистая картинка | Игра на DirectX 12 с DLSS Frame Generation |
| **ANR FG** | Нейросетевой генератор Apex, развивается почти каждый день | Игра с DLSS Frame Generation |

Замер на ROG Xbox Ally X (Radeon 890M), Forza Horizon 6, FSR 4 Balanced, 2X:
**Lossless Scaling ~93 FPS**, XeFG ~73, ANR FG ~71 (FPS на экране).

---

## 1. Установка плагина

1. Скачайте `Decky.FrameGen.Hub.zip` со страницы [Releases](https://github.com/davnozdu/Decky-FrameGen-Hub/releases).
2. Decky → ⚙ Настройки → **Developer** → включите **Developer mode** → **Install Plugin from ZIP** → выберите файл.
   Если вы ставили **Decky ANR**, плагин перенесёт профили игр и предложит удалить старый плагин — согласитесь.

Дальше плагин сам сообщит о новых версиях (свой, ANR FG, lsfg-vk, FSR 4) уведомлением Steam и баннером.

## 2. Lossless Scaling — лучший результат по FPS

**Один раз:**
1. Купите и установите **Lossless Scaling** в Steam (если ещё нет).
2. Steam → Lossless Scaling → ⚙ **Свойства** → **Бета-версии** → выберите **lsfg-vk**. Дождитесь обновления.
   Именно в этой ветке есть `lsfg-vk.dll`; основная ветка не подходит — плагин об этом предупредит.
3. Плагин → раздел **ANR FG** → **Install lsfg-vk (frame generation for any game)**.

**Для игры:**
1. Плагин → **Game** → выберите игру.
   - Если ANR FG в игре **не** установлен: включите **Lossless Scaling frame generation**.
   - Если установлен: **Frame generator → Lossless Scaling (lsfg-vk)**.
2. Настройки: **Lossless multiplier 2X**, **Flow scale 75%** (меньше — быстрее, но мягче движение),
   **Performance mode** — если нужно ещё быстрее.
3. В самой игре **выключите её генерацию кадров** (DLSS FG / FSR FG), иначе будет двойная генерация.
4. Запустите игру. Настройки применяются при запуске игры.

## 3. ANR FG и XeFG

1. Плагин → **Game** → игра → **Install ANR FG**. Плагин сам пропишет параметры запуска
   (`WINEDLLOVERRIDES="dxgi=n,b" %command%`, ваши параметры сохраняются).
2. **Frame generator**: **ANR FG** или **XeFG** (XeFG при первом выборе скачает ~75 МБ, только DirectX 12).
3. В игре: **Настройки графики → NVIDIA DLSS** как апскейлер и **DLSS Frame Generation → вкл.**
   Генерацию делает выбранный генератор, а не NVIDIA.
4. Генерация включается в самой игре (в заезде, на уровне), в меню её может не быть.

## 4. Как выжать максимум

| Настройка в плагине | Рекомендация для портативки |
|---|---|
| **Upscaler** | **FSR 4 (ML)** — чище картинка; **FSR 3.1** — на несколько FPS быстрее |
| **Render quality** | **Balanced** или **Performance** (FSR 4 из низкого разрешения выглядит хорошо) |
| **Benchmark** (для ANR) | Запустите один раз и нажмите **Use … in all games**: на Radeon 890M `portable-linalg` на ~24% быстрее автовыбора |
| **FPS limit** | Ровный темп: ~2× от реальных кадров, шагами по 10 (например 60 при ~30 реальных) |
| **Frame generation multiplier** | 2X; 3X — плавнее, но меньше реальных кадров и хуже отклик |
| **Dynamic MFG** | Экспериментально: в Forza на 890M вызвал сбой GPU. Лучше фиксированный множитель |
| **Sharpening (RCAS)** | 4–5 с FSR 3.1 + Performance, 0–3 с FSR 4 |

**FSR 4** нужен Proton с FSR 4: **proton-cachyos 11** или **GE-Proton 11+**. Если плагин пишет «needs setup»,
нажмите **Get FSR 4 through Proton** — он добавит `PROTON_FFX4_UPGRADE=1`, запустите игру один раз и выберите FSR 4 снова.

Сначала поднимайте **реальные** кадры (Render quality, графика игры), потом добавляйте генерацию: отклик управления
зависит от реальных кадров. Генерация лучше всего работает от ~40 реальных FPS.

## 5. Если что-то не так

| Проблема | Что сделать |
|---|---|
| Lossless не работает | Ветка Lossless Scaling — **lsfg-vk**? Выключена ли генерация кадров в самой игре? |
| Нет DLSS FG в меню игры (ANR/XeFG) | Запустите игру через Steam с параметрами, которые прописал плагин (**Launch options: set**) |
| Рывки | Поднимите реальные FPS, поставьте 2X и FPS limit; выключите Scene cut detection |
| Игра вылетела | Выключите Dynamic MFG; посмотрите **Show generator log** |
| Удалить из игры | **Remove frame generation from this game** — файлы и параметры запуска вернутся как были |

Не используйте в онлайн-играх с античитом.

Лицензии: код плагина — BSD-3-Clause. ANR FG — Apex Compute. XeFG-порт — GPL-3.0 (скачивается с GitHub автора).
lsfg-vk — CC BY-NC-ND 4.0 (скачивается с builds.lsfg-vk.dev). Lossless Scaling — платная программа, плагин её не
копирует и не распространяет.
