# Графический установщик PhotonOS

Статус: **в работе** (этап 1 — архитектура). Заменяет `void-installer` в
live-сессии: тот работает через `dialog` в терминале и не умеет branding.

## Почему свой, а не Calamares

- Calamares не знает **runit**: его модули под systemd (timedatectl,
  systemctl enable …), пришлось бы переписывать всё равно.
- Тянет тяжёлый стек и собственную тему; свой установщик переиспользует
  уже присутствующий в ISO Qt6 (LXQt) и наш стиль (Arc/photon, скругления,
  синие акценты — как у Deepin Installer).
- Полный контроль над шагами xbps/runit = меньше «магии» и лог проще.

## Технология

| Слой      | Выбор                                                        |
| --------- | ------------------------------------------------------------ |
| GUI       | Python 3 + **PySide6** (`python3-pyside6`, `-gui`, `-widgets` в репо Void, Qt6) |
| Компоновка| `QStackedWidget` + боковая навигация шагов (как у Deepin Installer) |
| Запуск    | `pkexec /usr/bin/photon-installer` (политика polkit — из коробки LXQt) |
| Бэкенд    | чистый python: `subprocess` для xbps/sfdisk/grub, без shell-скриптов |

## Экраны (мастер)

1. **Приветствие** — язык (ru/en), часовой пояс (список `zoneinfo`).
2. **Клавиатура** — раскладка/вариант, тестовое поле ввода.
3. **Диск** — авто-разметка («Стереть диск»: GPT, ESP 512 MiB + корень,
   swap по желанию) или ручной режим (v1: только просмотр + выбор
   раздела под корень/ESP).
4. **Пользователь** — имя, логин, пароль, hostname.
5. **Сводка** — всё выбиранное на одном экране, кнопка «Установить».
6. **Прогресс** — лог по шагам, проценты; отмена невозможна после
   разметки (предупреждение на сводке).
7. **Готово** — «Перезагрузить» / «Продолжить знакомство».

## Бэкенд: шаги и команды

| Шаг                | Команды (цель — `/target`)                                        |
| ------------------ | ----------------------------------------------------------------- |
| Разметка           | `sfdisk <диск>` (GPT: ESP type=uefi, root type=linux)             |
| Файловые системы   | `mkfs.vfat -F32 ESP`, `mkfs.ext4 -F корень` (btrfs/xfs — позже)   |
| Монтирование       | `mount`, `mkdir -p /target/boot/efi`                              |
| Установка базы     | `xbps-install -Sy -R $REPO -r /target base-system linux-lts grub …` |
| fstab              | по `blkid -o export` (UUID), `noatime`                            |
| chroot-фаза        | `grub-install --target=x86_64-efi --efi-directory=/boot/efi`, `grub-mkconfig -o /boot/grub/grub.cfg`, `xbps-reconfigure -fa linux-lts` |
| Локаль/время       | `/etc/default/libc-locales`, `ln -sf zoneinfo … /etc/localtime`, `/etc/rc.conf` |
| Пользователь       | `useradd -m -G wheel,audio,video,storage`, `chpasswd`             |
| Сервисы runit      | `ln -s /etc/sv/<svc> /target/etc/runit/runsvdir/default/` (из `build/services.list`) |
| Брендинг           | копия `os-release`, motd, `/etc/skel`-настройки уже в пакетах     |

Каждый шаг пишет в журнал `/tmp/photon-installer.log`; failure любого
шаблона шага — красный экран с логом и подсказкой.

## Структура (этап 2)

```text
installer/
├── photon-installer          # точка входа: мастер (QWizard-подобный, свой стиль)
├── photon_install/
│   ├── __init__.py
│   ├── locale.py             # словари ru/en
│   ├── disk.py               # lsblk/sfdisk: опрос и разметка
│   ├── backend.py            # установка: команды шагов, журнал
│   └── settings.py           # выбранная конфигурация (dataclass)
├── photon-installer.desktop  # ярлык в live-сессии (pkexec)
└── README.md
```

## Вехи

- **M1** — каркас мастера + экраны приветствия/пользователя, опрос дисков (read-only).
- **M2** — авто-разметка и установка базы в QEMU (UEFI), fstab, загрузчик.
- **M3** — локали/пользователи/сервисы, экран прогресса с логом.
- **M4** — ручная разметка, обработка ошибок, тесты на пустых дисках.
- **M5** — пакет в репозиторий ISO (`packages.list`), вычистка `void-installer`
  из приветствия live-сессии.

Тестирование: QEMU/UEFI (`qemu-system-x86_64 -bios OVMF.fd -cdrom dist/…iso`),
целевой диск — `qemu-img` 8–16 ГБ; прогон на реальном железе — после M3.
