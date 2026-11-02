# Собственный репозиторий пакетов PhotonOS

> Статус: **два трека**. Активный — стек **Hyprland** (сессия MacShell,
> M3): 12 шаблонов `srcpkgs/hypr*` + `hwdata` + `glaze` собираются в ISO
> и в CI (Action **pkg**, цепочка `hyprland`), см. `docs/MACSHELL.md`.
> На паузе — **DDE/DTK** (решение от 2026-11-02): шаблоны ниже сохранены
> как готовая база, сборка — `./xbps-src pkg <имя>` после `pkg/build.sh`.

Здесь живут шаблоны пакетов, которых нет в Void Linux, и вендоренные
исходники (`vendor/`). Формат шаблонов — как в void-packages; раздача
через `xbps-rindex`.

## Текущая структура

```text
pkg/
├── build.sh                 # подготовка void-packages: шаблоны + shlibs
├── shlibs-extra.txt         # SONAME-записи наших библиотек
├── vendor/
│   └── MacShell/            # upstream github.com/0-ss/MacShell (MIT, без .git)
└── srcpkgs/
    ├── hwdata/                      # PCI/USB/PNP-базы (0.412) — для aquamarine
    ├── hyprutils/                   # утилиты Hyprland (0.14.3; в Void 0.11.0)
    ├── hyprlang/                    # парсер конфигов (0.6.8)
    ├── glaze/                       # header-only JSON (7.2.0, пин Hyprland)
    ├── hyprland-protocols/          # Wayland-протоколы (0.8.0)
    ├── aquamarine/                  # бэкенд вывода/ввода (0.16.0)
    ├── hyprcursor/                  # курсоры (0.1.13)
    ├── hyprgraphics/                # изображения (0.6.0)
    ├── hyprland/                    # композитор, Lua-конфиг (0.57.0)
    ├── hyprlock/                    # экран блокировки (0.9.7)
    ├── hypridle/                    # простой (0.1.8)
    ├── xdg-desktop-portal-hyprland/ # порталы (1.5.0)
    ├── photon-boot-splash/  # загрузочная plymouth-тема PhotonOS
    ├── gsettings-qt/ dtkcommon/ dtklog/ dtkcore/ dtkgui/ dtkwidget/
    ├── qt5platform-plugins/ qt5integration/ libqtxdg/ dbusmenu-qt5/
    ├── dde-qt-dbus-factory/ deepin-wayland-protocols/ dwayland/
    └── dde-session-shell/ dde-launcher/ dde-polkit-agent/ dde-dock/
```

## Статус

### Hyprland/MacShell (активно, M3)

- [x] Шаблоны 12 пакетов стека (версии и checksums — из релизов upstream)
- [x] shlibs пяти библиотек (`shlibs-extra.txt`)
- [x] Сборка в ISO: локальный репозиторий + `xbps-rindex` с подписью
- [ ] Прогон цепочки в CI (Action **pkg** → `hyprland`)
- [ ] Живой прогон сессии в QEMU и на железе

### DDE (пауза)

- [x] Шаблоны фундамента DTK: `gsettings-qt`, `dtkcommon`, `dtklog`,
      `dtkcore`, `dtkgui`, `dtkwidget`
- [x] Пробная сборка на Void-хосте: DTK-фундамент, QPA/интеграция Qt5 и
      оболочка (`dde-session-shell`, `dde-launcher`, `dde-polkit-agent`,
      `dde-dock` 6.0.17). Патчи: Qt5.15-строгость, cmake-конфиг Void,
      отключение lightdm-greeter и touch-gesture (ISO на SDDM).
- [ ] Рабочий стол: старый `dde-desktop` заморожен upstream — нужен
      отдельный шаблон + зависимости (dde-application-manager и пр.)
- [ ] Метапакет `photon-dde`

Версии и checksums всех шаблонов взяты из реальных релизов upstream,
имена зависимостей сверены с пакетным индексом Void. Подробности решений
— в `docs/PACKAGING.md` (DDE) и `docs/MACSHELL.md` (Hyprland).
