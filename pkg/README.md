# Собственный репозиторий пакетов PhotonOS

Здесь будут жить шаблоны пакетов, которых нет в Void Linux, — в первую очередь
**DDE (Deepin Desktop Environment)**.

## Зачем

В официальных репозиториях Void нет DDE, а ставить пакетный менеджер другого
дистрибутива — не наш путь. Стандартный механизм XBPS позволяет подключить
сколь угодно сторонних репозиториев, поэтому PhotonOS будет собирать свои
пакеты через `xbps-src` (формат шаблонов — как в void-packages) и раздавать их
через `xbps-rindex`.

## Текущая структура

```text
pkg/
└── srcpkgs/
    ├── gsettings-qt/          # QGSettings — настройки Deepin (0.2)
    ├── dtkcommon/             # cmake-модули DtkConfig/DtkBuildHelper (6.7.52)
    ├── dtklog/                # логгер DtkLog, systemd OFF (0.0.4)
    ├── dtkcore/               # ядро DTK, Qt5 (5.7.30)
    ├── dtkgui/                # графика DTK, Qt5 (5.7.30)
    ├── dtkwidget/             # виджеты DTK, Qt5 (5.7.30)
    ├── photon-boot-splash/    # загрузочная plymouth-тема PhotonOS
    ├── photon-dde/            # метапакет рабочего стола (план)
    ├── dde-session-shell/     # оболочка DDE (план)
    ├── dde-desktop/
    └── dde-dock/
```

## Статус

- [x] План и формат определены (см. `docs/PACKAGING.md`)
- [x] Шаблоны фундамента DTK: `gsettings-qt`, `dtkcommon`, `dtklog`, `dtkcore`, `dtkgui`, `dtkwidget`
- [x] Шаблон `photon-boot-splash` (кадры анимации + скрипт-тема plymouth)
- [x] Пробная сборка через `xbps-src` на Void-хосте (непривилегированный chroot,
      xbps-static 0.60): собраны DTK-фундамент, QPA/интеграция Qt5 и оболочка —
      `dtkcommon`, `dtklog`, `dtkcore`, `dtkgui`, `dtkwidget`,
      `qt5platform-plugins`, `qt5integration`, `gsettings-qt`, `dwayland`,
      `deepin-wayland-protocols`, `dbusmenu-qt5`, `dde-qt-dbus-factory` 6.0.1,
      `dde-session-shell`, `dde-launcher`, `dde-polkit-agent`, `dde-dock` 6.0.17.
      Патчи: Qt5.15-строгость, cmake-конфиг Void (`polkit-qt5-1`, `PolkitQt5-1`),
      отключение lightdm-greeter и touch-gesture (ISO на SDDM).
- [ ] Рабочий стол: старый `dde-desktop` заморожен upstream (код уехал в
      `dde-shell` 1.x, Qt5-линия deepin 23) — нужен отдельный шаблон+зависимости
      (dde-application-manager и пр.)
- [ ] Метапакет `photon-dde`
- [ ] Сборочный CI для пакетов
- [ ] Публичный репозиторий + подключение в ISO

Версии и checksums всех шаблонов взяты из реальных релизов upstream,
имена зависимостей сверены с пакетным индексом Void. Подробности решений
и честный список рисков — в `docs/PACKAGING.md`.
