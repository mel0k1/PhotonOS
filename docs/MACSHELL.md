# MacShell: сессия macOS Tahoe-стиля (M3)

Статус: **M3 выполнен** — стек собран шаблонами, ISO несёт сессию
«PhotonOS MacShell», установщик умеет её ставить.

## Что это

[MacShell](https://github.com/0-ss/MacShell) — оболочка в стиле macOS Tahoe
поверх композитора **Hyprland** (Wayland): менюбар, Dock с живыми превью
окон, Spotlight (приложения, буфер обмена, эмодзи), центр управления,
виджеты рабочего стола, экран блокировки **MacLock** (отдельный Quickshell-процесс).
Весь UI — QML, движок — [Quickshell](https://quickshell.org) ≥ 0.3, эффект
«Liquid Glass» — реалтайм-шейдер (`liquidglass.frag` → `qsb`).

Проект вендорен в репозиторий PhotonOS: `pkg/vendor/MacShell` (без `.git`,
обновление — свежий клон + `rsync --delete`).

## Что показал разбор (ноябрь 2026)

**Из репозитория Void** (glibc, x86_64) есть всё главное:

| Пакет | Версия в репо | Роль |
|---|---|---|
| `quickshell` | 0.3.2 | движок оболочки; в бинарнике есть модули Hyprland, UPower, Pipewire, Mpris, Pam, SystemTray, Notifications, SessionLock (проверено по составу .xbps) |
| `awww` | 0.12.1 | обои (рекомендуемый MacShell бэкенд) |
| `kitty`, `cliphist`, `grim`, `slurp`, `wl-clipboard`, `wf-recorder` | — | терминал, буфер, скриншоты, запись |
| `pipewire` + `wireplumber` | 1.6.10 / 0.5.18 | звук и приватность-индикаторы |
| `qt6-*` (6.11.2), `qt6ct`, `font-inter`, `noto-fonts-emoji`, `polkit-gnome` | — | стек Qt и оформление |

**Сам Hyprland в Void не пакуется** — как и его библиотеки (aquamarine,
hyprlang, hyprcursor, hyprgraphics), утилиты (hyprlock, hypridle) и портал.
Из hypr*-стека в Void остались только `hyprpicker`, `hyprutils` (0.11.0 —
старая) и `hyprwayland-scanner`. Поэтому веха M3 с самого начала
предусматривала «шаблоны при необходимости» — необходимость подтвердилась.

## Наши пакеты (pkg/srcpkgs)

12 шаблонов `xbps-src`, собираются цепочкой (порядок — топологический):

| Пакет | Версия | Зачем |
|---|---|---|
| `hwdata` | 0.412 | PCI/USB/PNP-базы; aquamarine читает `pkgdatadir` (в Void пакета нет) |
| `hyprutils` | 0.14.3 | базовая утилитная библиотека (в репо 0.11.0 — мало) |
| `hyprlang` | 0.6.8 | парсер конфигов (Lua-синтаксис Hyprland 0.55+) |
| `glaze` | 7.2.0 | header-only JSON; без него Hyprland тянет FetchContent из сети, что в xbps-src запрещено |
| `hyprland-protocols` | 0.8.0 | Wayland-протоколы экосистемы |
| `aquamarine` | 0.16.0 | бэкенд вывода/ввода (замена wlroots) |
| `hyprcursor` | 0.1.13 | курсоры (xcursor + toml) |
| `hyprgraphics` | 0.6.0 | загрузка изображений |
| `hyprland` | 0.57.0 | композитор; требует aquamarine ≥ 0.15, hyprlang ≥ 0.6.7, hyprutils ≥ 0.14.3, hyprcursor ≥ 0.1.7, hyprgraphics ≥ 0.5.1, udis86, glslang, glaze, sdbus-c++, re2, muparser, lcms2, libcanberra, libei |
| `hyprlock` | 0.9.7 | экран блокировки (PAM `/etc/pam.d/hyprlock` — под ним MacLock) |
| `hypridle` | 0.1.8 | простой (гашение/сон) |
| `xdg-desktop-portal-hyprland` | 1.5.0 | скринкаст/скриншоты через порталы |

Требования MacShell соблюдены: **Hyprland ≥ 0.55 с Lua-конфигом** (0.57 ✓),
**Quickshell ≥ 0.3** (0.3.2 ✓ с нужными модулями), **Qt ≥ 6.5** (6.11.2 ✓).

shlibs-записи пяти библиотек — в `pkg/shlibs-extra.txt` (libhyprutils.so.13,
libhyprlang.so.2, libaquamarine.so.15, libhyprcursor.so.0,
libhyprgraphics.so.5); `pkg/build.sh` дописывает их в `common/shlibs`.

Проверка цепочки в CI: Action **pkg** → Run workflow → `hyprland`
(артефакт `PhotonOS-pkgs-hyprland`).

## Интеграция в ISO

`build/build-iso.sh` делает три новые вещи:

1. **Локальный репозиторий**: клонирует void-packages, копирует шаблоны
   (`pkg/build.sh`), собирает цепочку `xbps-src`, собирает репо
   (`xbps-rindex -a` + подпись свежим ключом) и передаёт mklive первым
   `-r`. XBPS выбирает лучшие версии, так что наш hyprutils 0.14.3
   побеждает репозиториевый 0.11.0. Отключение — `PHOTON_HYPR=0`.
2. **MacShell в `/etc/skel`**: штатный `install.sh` из вендоренной копии
   запускается с `HOME=<stage>/etc/skel` и флагами
   `--local --no-deps --no-services --no-gui --no-start --no-verify
   --no-auto-update -y` (все «нет» — потому что сборочный хост: systemd,
   pacman/apt и живая сессия там не нужны). Он копирует
   `~/.config/quickshell/{MacShell,MacLock}`, хелперы, звуки, лаунчеры,
   пишет `~/.config/hypr/macshell.lua` (автостарт + хоткеи) и дописывает в
   наш `hyprland.lua` блок `require("macshell")` + Liquid-Glass правила
   слоёв. Скрипт проверен в изоляции (Debian, фейковый HOME) — работает
   без диалогов. Отключение — `PHOTON_MACSHELL=0`.
3. **Установщик в образе**: `installer/photon-installer` + модуль
   `photon_install` копируются в `/usr/bin` и `/usr/share/photon-installer`.

Список пакетов (`build/packages.list`) дополнен сессией MacShell:
`hyprland, hyprlock, hypridle, xdg-desktop-portal-hyprland` (наши) +
`quickshell, awww, kitty, cliphist, grim, slurp, wl-clipboard,
wf-recorder, brightnessctl, inotify-tools, pipewire, wireplumber,
playerctl, qt6ct, font-inter, noto-fonts-emoji, polkit-gnome,
xdg-desktop-portal, xdg-desktop-portal-gtk, fastfetch` (репо Void) +
PySide6 для установщика.

## Сессия и дефолты

- `overlay/usr/share/wayland-sessions/photon-macshell.desktop` — пункт
  «PhotonOS MacShell» в SDDM (Exec=Hyprland).
- `overlay/etc/skel/.config/hypr/hyprland.lua` — базовый конфиг-пустышка:
  Hyprland 0.55+ читает `.lua` (а `.conf` игнорирует), а проверенный API
  Lua-конфигов — это вызовы `hl.*`, которые и пишет macshell.lua. Свои
  настройки пользователь дописывает в этот же файл.
- В живой сессии и у установленного пользователя MacShell стартует сам:
  `hl.on("hyprland.start")` → `macshell-start` (ждёт композитор, не плодит
  копий, перезапускает оболочку при падении).
- Выбор окружения в установщике: MacShell — реальный вариант
  (`installer/photon_install/backend.py`: 25 пакетов + `sddm` в сервисы).
  Skel переносится бэкендом в установленную систему как есть.

## Специфика runit и ограничения

- install.sh рассчитан на systemd: сервисы (`--no-services`) и
  автообновление (`--no-auto-update`) отключены. Bluetooth при желании:
  `ln -s /etc/sv/bluetooth /var/service/`.
- «Keep Awake» MacShell использует `systemd-inhibit` — на runit фича
  деградирует тихо; остальное (громкость, яркость, медиа-клавиши) работает
  через `wpctl`/`brightnessctl` из lua-биндов.
- `pipewire`/`wireplumber` стоят в ISO, но пользовательский раннинг аудио
  (dbus-activation) — вопрос M4; в live-сессии при необходимости:
  `pipewire & wireplumber &`.
- `hypridle` установлен, но его конфиг (`hypr-macshell`-скрипты) — после
  первого живого прогона на железе.

## Как попробовать (QEMU)

```sh
qemu-system-x86_64 -m 3G -smp 2 -enable-kvm \
  -bios /usr/share/OVMF/OVMF_CODE.fd \
  -cdrom dist/PhotonOS-live-x86_64-<дата>.iso
```

В SDDM выбрать сеанс **PhotonOS MacShell**, пользователь `anon`
(пароль `voidlinux`). Ждать Liquid Glass: на первом старте `qsb`
компилирует шейдер в `~/.config/macdock/liquidglass.frag.qsb`.

Без KVM (CI-песочница): TCG, `-display none -monitor unix:/tmp/mon,server,nowait`,
скриншоты — `echo screendump /tmp/shot.ppm | socat - UNIX:/tmp/mon`.

## Что дальше (M4+)

- ручная разметка диска и обработка ошибок бэкенда;
- приветствие при первом входе (MacInstaller как основа?);
- вычистка `void-installer` из приветствия live-сессии и пакет установщика
  в `packages.list` (PySide6 уже в образе);
- живой прогон на реальном железе.
