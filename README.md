<div align="center">

# PhotonOS

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

**Лёгкий дистрибутив Linux на базе Debian: минимум лишнего, фирменный вид.**

[![CI](https://github.com/mel0k1/PhotonOS/actions/workflows/build.yml/badge.svg)](https://github.com/mel0k1/PhotonOS/actions/workflows/build.yml)
![Base](https://img.shields.io/badge/base-Debian%2013%20trixie-blue)
![Desktop](https://img.shields.io/badge/desktop-LXQt%20%2B%20picom-green)
![Boot](https://img.shields.io/badge/boot-plymouth%20photon--boot-orange)
[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)

</div>

## О проекте

PhotonOS — независимый дистрибутив-/live-образ, собранный на **минимальном
Debian**: только база, наш рабочий стол и наш брендинг — без мусора.

Основные решения:

- **База** — Debian trixie, стабильные пакеты, предсказуемые обновления.
- **Минимум** — LXQt-ядро без метапакетов, без офиса и прочего лишнего;
  документация и man-страницы вырезаны на уровне dpkg.
- **Рабочий стол** — **LXQt в духе Deepin**: нижняя панель-док, тёмные темы
  (Onyxian-Rounded + Kvantum Orchis, иконки Papirus), композитор **picom**
  с тенями и блюром, фирменные обои **photon-ribbon** (лента на графите).
  Русский UI по умолчанию.
- **Загрузка** — фирменная plymouth-тема **photon-boot**: чёрный квадрат
  с двумя белыми глазами собирается из кадра за кадром.
- **Брендинг** — os-release, motd, issue, иконки photon, photon-fetch.

История: раньше проект собирался на базе Void Linux (glibc + runit + XBPS,
шаблоны DDE и Hyprland-стека) — эта линия закрыта, вся обвязка удалена;
в git-истории осталась.

## Скриншоты

Кадры из live-образа (QEMU, Debian trixie, LXQt 2.1 + picom, тема
Onyxian-Rounded + Kvantum Orchis-solidDark):

![Меню загрузчика PhotonOS](docs/screens/grub.png)

![Рабочий стол PhotonOS — Onyxian-Rounded и обои photon-ribbon: плавающая панель-док, куб-меню, часы, трей, корзина](docs/screens/desktop.png)

![Тот же рабочий стол при EFI-загрузке (OVMF)](docs/screens/efi.png)

Загрузка в обоих режимах (BIOS isolinux и EFI OVMF) проверяется
автоматически в CI: smoke-тест грузит ISO в QEMU, снимает скриншоты
через QMP, ждёт телеметрии photon-diag (PID lxqt-session) и проверяет,
что кадры не чёрные.

## Состав репозитория

```text
PhotonOS/
├── build/
│   ├── build-iso.sh        # пайплайн: mmdebstrap -> squashfs -> ISO
│   └── packages.list       # пакеты live-образа (Debian trixie)
├── branding/
│   └── plymouth/photon-boot/  # тема загрузки (кадры анимации)
├── overlay/                # файлы, попадающие в корень образа
│   ├── etc/motd, issue, photon/picom.conf, plymouth/plymouthd.conf
│   ├── etc/skel/           # дефолты LXQt в стиле Deepin + Корзина
│   ├── usr/share/backgrounds/  # фирменные обои
│   ├── usr/share/icons/photon/ # фирменные иконки (24-256)
│   └── usr/lib/os-release  # брендинг системы
├── ppm/ppm                 # Photon Package Manager (обёртка, порт с XBPS)
├── fetch/photon-fetch      # ASCII-сводка о системе
├── logo/photon.txt         # ASCII-логотип
├── scripts/                # генераторы обоев/иконок
└── .github/workflows/      # CI: ISO на push в main
```

## Сборка ISO

Нужен хост Debian/Ubuntu с правами root (CI делает всё сам):

```sh
apt install mmdebstrap squashfs-tools xorriso mtools dosfstools
./build/build-iso.sh          # результат: dist/PhotonOS-live-amd64-<дата>.iso
```

CI собирает ISO на каждый push в `debian`/`main` (плюс катящийся релиз
«iso» — последний образ всегда доступен публично) и сразу прогоняет
smoke-тест: загрузка ISO в QEMU в BIOS и EFI (OVMF) режимах со
скриншотами и serial-диагностикой. Live-сессия: автологин под
пользователем `anon` без пароля.

## Сборка из исходников — планы

- [x] Перевод на базу Debian, минимизация
- [x] Фирменная загрузка photon-boot и логотип
- [x] LXQt + тема Onyxian-Rounded (Kvantum Orchis-solidDark)
- [x] EFI-загрузка (grub-mkstandalone + El Torito, проверена с OVMF в CI)
- [ ] ppm: порт с XBPS на apt
- [ ] Установщик на диск (PyQt6, Debian-порт — отлаживается)
- [ ] Фирменные приложения

## Лицензия

Проект распространяется по [GPL-3.0](LICENSE).
