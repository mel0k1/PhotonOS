# Графический установщик PhotonOS

Статус: **M2 готов** — реальный бэкенд (sfdisk → xbps → GRUB → fstab) +
экран прогресса; проверен сухим прогоном (dry-run) и юнит-тестами.
Заменяет `void-installer` в live-сессии: тот работает через `dialog` в
терминале и не умеет branding.

## Почему Python

- **PySide6 уже в репозиториях Void** (`python3-pyside6`) — не тащим
  сторонний стек, а Qt6 и так в ISO ради LXQt;
- бэкенд — «склейка» системных команд (`sfdisk`, `xbps-install`, `grub`):
  Python выигрывает по скорости разработки и читаемости, производительность
  не важна (GUI просто ждёт команды);
- логика без Qt (опрос дисков, план разметки, валидации) покрыта юнит-тестами
  без запуска GUI;
- шаги легко менять/добавлять (окружения, MacShell-ветка);
- если когда-нибудь станет жалко ~40 МБ ОЗУ на рантайм — перенос на C++/Qt
  механический, архитектура та же.

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
   github.com/0-ss/MacShell — с M3 ставится из ISO, см.
   docs/MACSHELL.md), **без окружения** (минимум), XFCE/KDE/GNOME
   («в планах»).
6. **Сводка** — всё выбиранное на одном экране, кнопка «Установить».
7. **Установка** (M2) — 13 шагов бэкенда с живым журналом; пароли в журнал
   не попадают; после ошибки доступен «Назад».
8. **Готово** — «Перезагрузить» в установленную систему.

### Что делает бэкенд (M2)

| Шаг | Содержимое |
| --- | --- |
| Разметка | `sfdisk`: GPT — ESP 512 МиБ (type U), swap 4 ГиБ (опция), корень |
| ФС | `wipefs`, `mkfs.vfat` ESP, `mkswap`+`swapon`, `mkfs.ext4 -L photon` |
| Монтирование | корень в `/target`, ESP в `/target/boot/efi` |
| Пакеты | `xbps-install -r /target`: base + linux-lts + grub-x86_64-efi + NetworkManager + набор окружения (LXQt/без DE) |
| fstab | по `blkid` UUID: `/`, `/boot/efi`, swap, `tmpfs /tmp` |
| chroot | `/proc`, `/dev`, `/sys` — для dracut и grub |
| Настройка | hostname, hosts, локали (ru/en), часовой пояс, `glibc-locales` |
| Пользователи | `useradd -m` (wheel,audio,video,storage,input,cdrom), `chpasswd` (stdin скрыт) |
| Сервисы | dbus, elogind, NetworkManager, chronyd (+sddm для LXQt) в runsvdir/default |
| Брендинг | os-release, /etc/skel-дефолты, /etc/photon — из live-сессии |
| Загрузчик | `grub-install --target=x86_64-efi --bootloader-id=PhotonOS`, `grub-mkconfig` |
| Initramfs | `xbps-reconfigure -fa linux-lts` (dracut) |

### Проверка в QEMU (UEFI)

```sh
# 1) сухой прогон без диска — печать всех команд в журнал
./installer/photon-installer --dev --fake-disks --dry-run

# 2) полная проверка в QEMU: ISO из CI + целевой диск
qemu-img create -f qcow2 target.qcow2 16G
qemu-system-x86_64 -m 4G -bios /usr/share/ovmf/OVMF.fd \
    -drive file=PhotonOS-live-x86_64-YYYYMMDD.iso,media=cdrom \
    -drive file=target.qcow2,if=virtio
# в live-сессии: ./installer/photon-installer (pkexec) → пройти мастер

# 3) юнит-тесты логики без Qt
python3 scripts/installer_tests.py
```

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
- [x] **M2** — бэкенд установки (sfdisk → xbps-install → GRUB → fstab),
      экран прогресса с журналом, dry-run, наборы пакетов по окружениям,
      брендинг и skel-дефолты переносятся в установленную систему.
- **M3** — MacShell-ветка: стек Hyprland шаблонами xbps-src (pkg/srcpkgs),
  сессия «PhotonOS MacShell» в ISO и SDDM, MacShell в skel через штатный
  install.sh, набор пакетов и сервисов в бэкенде, приветствие при первом
  входе — позже (детали: docs/MACSHELL.md).
- **M4** — ручная разметка, обработка ошибок, тесты на пустых дисках.
- **M5** — пакет в репозиторий ISO (`packages.list`), вычистка `void-installer`
  из приветствия live-сессии.

Тестирование: QEMU/UEFI (`qemu-system-x86_64 -bios OVMF.fd -cdrom dist/…iso`),
целевой диск — `qemu-img` 8–16 ГБ; прогон на реальном железе — после M3.
