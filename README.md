<div align="center">

# Photon OS

```text
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@*
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@%
@@*.....@@@@@@@@@@@@@@@@.....%@@%
@@*.....@@@@@@@@@@@@@@@@.....%@@%
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@%
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@%
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@%
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@%
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@%
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@%
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@%
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@%
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@%
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@%
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@%
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@%
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@%
+@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
```

**Лёгкий дистрибутив Linux на базе Void Linux: glibc + runit + XBPS.**

[![CI](https://github.com/mel0k1/PhotonOS/actions/workflows/build.yml/badge.svg)](https://github.com/mel0k1/PhotonOS/actions/workflows/build.yml)
![Base](https://img.shields.io/badge/base-Void%20Linux-green)
![Init](https://img.shields.io/badge/init-runit-orange)
![Libc](https://img.shields.io/badge/libc-glibc-blue)
[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)

</div>

## О проекте

PhotonOS — независимый дистрибутив, собранный на проверенной базе Void Linux и
ориентированный на лёгкость. Ничего лишнего: минимальный базовый набор пакетов,
быстрый init на **runit**, проверенная пакетная система **XBPS** (вариант
**glibc**) и фирменные инструменты поверх неё.

Основные решения:

- **База** — Void Linux, rolling release, репозитории совместимы на 100%.
- **Init** — runit: стартует за секунды, сервисы — три файла в `/etc/sv`.
- **Библиотеки** — glibc: полная совместимость со сторонним и проприетарным софтом.
- **Пакетник** — `ppm` (Photon Package Manager): обёртка над XBPS с человеческим
  интерфейсом, цветным выводом и ASCII-логотипом.
- **Рабочее окружение** — **LXQt** с оформлением в духе **Deepin**: нижняя
  панель-док, светлые темы, композитор picom с тенями и блюром.

## Рабочий стол: LXQt в духе Deepin

v0.1 выходит на **LXQt** из репозиториев Void, оформленном под Deepin:

- нижняя панель-док: иконки без текста, крупные, на всю ширину экрана;
- светлые темы **Arc** (GTK) + **Papirus** (иконки) — плоско, скруглённо,
  близко к фирменному стилю Deepin;
- фирменная тема иконок **photon** (наследует Papirus): Корзина,
  «Недавние документы» и Файловый менеджер — из авторских артов
  (`design/icons-src/`, генератор — `scripts/make_icons.py`);
- обои: 4 авторских изображения (`design/wallpapers-src/` →
  `scripts/make_wallpapers.py` → `/usr/share/backgrounds/photon-*.jpg`) +
  градиент `photon-deepin.png`. По умолчанию — `photon-flow.jpg`;
  смена — без правки файлов: правый клик по рабочему столу →
  «Настройки рабочего стола» (вкладка «Обои») или
  «Настройки внешнего вида» LXQt;
- на рабочем столе — ярлык «Корзина» (`/etc/skel/Desktop/`);
- композитор **picom**: тени, полупрозрачность, фоновое размытие (конфиг —
  `/etc/photon/picom.conf`, автозапуск через XDG autostart);
- дефолты пользователя — `overlay/etc/skel/.config/`: lxqt.conf, panel.conf,
  session.conf, user-dirs.dirs, настройки pcmanfm-qt и GTK.

Честно про DDE: в репозиториях Void его нет, а собственная упаковка (шаблоны
DTK и оболочки в [`pkg/`](pkg/README.md)) отложена — слишком большой объём
работы ради перегонки целого DE. Шаблоны сохранены (готовая база: `pkg/build.sh`
+ `xbps-src`), но ISO собирается на LXQt.

## Состав репозитория

```text
PhotonOS/
├── build/                  # сборка ISO
│   ├── build-iso.sh        # обёртка над void-mklive
│   ├── packages.list       # пакеты live-образа
│   └── services.list       # runit-сервисы образа
├── ppm/
│   └── ppm                 # Photon Package Manager (обёртка над XBPS)
├── fetch/
│   └── photon-fetch        # ASCII-сводка о системе
├── overlay/                # файлы, попадающие в корень ISO
│   ├── etc/motd, etc/issue, etc/photon/picom.conf
│   ├── etc/skel/.config/   # дефолты LXQt в стиле Deepin
│   ├── etc/skel/Desktop/   # ярлык «Корзина» на рабочем столе
│   ├── usr/share/icons/photon/   # фирменная тема иконок (поверх Papirus)
│   ├── usr/share/backgrounds/    # обои photon-*.jpg + photon-deepin.png
│   └── usr/lib/os-release  # брендинг системы
├── design/                 # авторские исходники: иконки и обои
├── logo/photon.txt         # ASCII-логотип
├── docs/                   # PPM.md, BUILDING.md, PACKAGING.md
├── pkg/                    # шаблоны пакетов DDE (на паузе, см. pkg/README.md)
├── scripts/                # утилиты (make_icons.py, make_wallpapers.py, ...)
└── .github/workflows/      # CI: ISO на push, пакеты — вручную
```

## ppm — пакетный менеджер

`ppm` — тонкая обёртка над XBPS: те же скорости, понятные команды, цветной
вывод. Полная справка — [`docs/PPM.md`](docs/PPM.md).

| Команда                 | Что делает                        | Под капотом      |
| ----------------------- | --------------------------------- | ---------------- |
| `ppm sync`              | синхронизировать индексы репо     | `xbps-install -S`  |
| `ppm install firefox`   | установить пакеты                 | `xbps-install -S`  |
| `ppm update`            | обновить систему целиком          | `xbps-install -Su` |
| `ppm remove firefox`    | удалить пакеты с зависимостями    | `xbps-remove -R`   |
| `ppm search слово`      | поиск по репозиториям             | `xbps-query -Rs`   |
| `ppm autoremove`        | удалить пакеты-сироты             | `xbps-remove -O`   |
| `ppm clean`             | очистить кэш пакетов              | `xbps-remove -m`   |
| `ppm list`              | список установленных              | `xbps-query -l`    |

Установка на работающую систему (или на машину с Void):

```sh
sudo install -Dm755 ppm/ppm /usr/bin/ppm
```

## photon-fetch

ASCII-сводка о системе: логотип PhotonOS + ОС, ядро, аптайм, число пакетов,
оболочка, ДЕ, CPU, память. Чистый POSIX sh, без зависимостей — работает даже в
голой консоли.

```sh
./fetch/photon-fetch
```

## Сборка ISO

Нужен хост Void Linux (или контейнер `ghcr.io/void-linux/void-mklive`), ~10 ГБ
диска. Подробности — [`docs/BUILDING.md`](docs/BUILDING.md).

```sh
./build/build-iso.sh          # результат: dist/PhotonOS-live-x86_64-<дата>.iso
```

CI собирает ISO автоматически на каждый push в `main` (вкладка Actions) —
образ доступен артефактом сборки. Установка с образа — стандартный
`void-installer` из live-сессии.

## Дорожная карта

- [x] Каркас репозитория: `ppm`, `photon-fetch`, брендинг
- [x] Сборка ISO через void-mklive + CI на push
- [x] Загрузочная анимация: plymouth-тема `photon-boot` из фирменного ролика
- [x] Рабочий стол: LXQt + оформление в духе Deepin (панель-док, picom, Papirus, Arc, обои)
- [x] Фирменные иконки и обои: тема `photon`, 4 обоев, ярлык «Корзина», смена обоев через настройки
- [x] Заготовка упаковки DDE: шаблоны DTK и оболочки в `pkg/` (на паузе)
- [ ] Графический установщик системы
- [ ] Фирменные приложения PhotonOS (центр управления, приветствие при входе)
- [ ] Публичный репозиторий пакетов (xbps-rindex) — когда появится свой софт

## Благодарности

- [Void Linux](https://voidlinux.org/) — идеальная база и `void-mklive`.
- [Deepin](https://www.deepin.org/) — источник вдохновения для оформления:
  LXQt в PhotonOS настроен под его фирменный стиль.
- Обёртка `ppm` ни на что не претендует: под капотом честный XBPS.

## Лицензия

Проект распространяется по [GPL-3.0](LICENSE).
