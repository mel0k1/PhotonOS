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
- [ ] Пробная сборка всех шаблонов через `xbps-src` на Void-хосте
- [ ] Метапакет `photon-dde` и шаблоны оболочки DDE
- [ ] Сборочный CI для пакетов
- [ ] Публичный репозиторий + подключение в ISO

Версии и checksums всех шаблонов взяты из реальных релизов upstream,
имена зависимостей сверены с пакетным индексом Void. Подробности решений
и честный список рисков — в `docs/PACKAGING.md`.
