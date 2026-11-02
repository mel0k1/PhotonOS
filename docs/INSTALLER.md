# Графический установщик PhotonOS

Статус: **M1 готов** (каркас мастера, опрос дисков), M2 — бэкенд установки.
Заменяет `void-installer` в live-сессии: тот работает через `dialog` в
терминале и не умеет branding.

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

1. **Приветствие** — язык (ru/en; смена языка перекрашивает мастер сразу),
   часовой пояс (список `zoneinfo`, зона подхватывается из `/etc/localtime`).
2. **Клавиатура** — раскладка (15 основных), тестовое поле ввода.
3. **Диск** — опрос через `lsblk -Jb`: модель, размер, SSD/HDD/USB, метка
   «есть данные → будет стёрт»; авто-разметка (GPT, ESP 512 МиБ, swap
   по желанию) с живым планом; ручной режим — позже (M4).
4. **Пользователь** — имя, логин (валидация), пароль с показом, hostname.
5. **Окружение** — карточки с бейджами: **LXQt** (фирменный, по умолчанию),
   **MacShell** (macOS Tahoe-стиль для Hyprland/Wayland,
   github.com/0-ss/MacShell — экспериментально, интеграция отдельной
   вехой), **без окружения** (минимум), XFCE/KDE/GNOME («в планах»).
6. **Сводка** — всё выбиранное на одном экране, кнопка «Установить».
7. **Прогресс** (M2) — лог по шагам; отмена невозможна после разметки.
8. **Готово** (M2) — «Перезагрузить» / «Продолжить знакомство».

## Каркас уже можно посмотреть

```sh
pip install PySide6                     # или xbps-install python3-pyside6
./installer/photon-installer --dev --fake-disks
```

Тесты без Qt: `python3 scripts/installer_tests.py` (парсер lsblk, план
разметки, валидации). Скриншоты без X: `python3 scripts/installer_shots.py`.

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

## Структура (M1 готова)

```text
installer/
├── photon-installer          # точка входа: QApplication + MainWindow
├── photon_install/
│   ├── __init__.py
│   ├── wizard.py             # шаги мастера, боковая навигация
│   ├── disk.py               # lsblk-опрос и план авто-разметки (без Qt)
│   ├── settings.py           # InstallSettings + варианты окружений
│   ├── locale.py             # строки ru/en
│   └── style.py              # палитра и QSS в духе Deepin
├── photon-installer.desktop  # ярлык в live-сессии (pkexec)
└── README.md
```

Тесты: `scripts/installer_tests.py` — логика дисков/валидаций без Qt;
`scripts/installer_shots.py` — оффскрин-скриншоты шагов.

## Вехи

- [x] **M1** — каркас мастера, все 6 шагов, опрос дисков через `lsblk -Jb`,
      выбор окружения (LXQt/MacShell/без DE/другие), сводка; ru/en с живой
      сменой языка.
- **M2** — авто-разметка и установка базы в QEMU (UEFI), fstab, загрузчик.
- **M3** — локали/пользователи/сервисы, экран прогресса с логом.
- **M4** — ручная разметка, обработка ошибок, тесты на пустых дисках.
- **M5** — пакет в репозиторий ISO (`packages.list`), вычистка `void-installer`
  из приветствия live-сессии.

Тестирование: QEMU/UEFI (`qemu-system-x86_64 -bios OVMF.fd -cdrom dist/…iso`),
целевой диск — `qemu-img` 8–16 ГБ; прогон на реальном железе — после M3.
