# Графический установщик PhotonOS

Статус: **Debian-порт (M3) готов** — бэкенд (sfdisk → копия live-системы →
GRUB → fstab) + экран прогресса; мастер на PyQt6; dry-run и юнит-тесты.
Работает из live-сессии, ярлык «Установка PhotonOS» в меню приложений.

## Почему копия live-системы, а не debootstrap/apt

Классический Debian live-installer кладёт на диск то, что уже загружено:
корневой squashfs live-ISO разворачивается в `/target` tar-потоком. Так
установленная PhotonOS получается **1:1 с live-образом** — та же тема
Onyxian-Rounded, те же обои и брендинг, тот же набор пакетов, и всё это
офлайн: ни сети, ни скачивания сотен МБ, ни расхождений версий. Live-специфика
(`live-boot`, `live-config`, `user-setup`) снимается `dpkg --purge` уже в
`/target`, после чего initramfs пересобирается чистым.

Вариант «Без окружения» тоже честный: десктоп-стек (LXQt, SDDM, Xorg)
снимается dpkg-очисткой в `/target` — остаётся консольная база с сетью и
брендингом.

## Почему свой мастер, а не Calamares

- Свой мастер уже написан и оформлен в стиле Deepin Installer — Calamares
  потребовал бы branding-стек и модули заново;
- переиспользует Qt6, который и так есть в ISO ради LXQt (PyQt6 ~15 МБ);
- полный контроль над шагами: копия squashfs + dpkg-чистка — 12 прозрачных
  операций, всё видно в журнале;
- если когда-нибудь понадобится C++/Qt — архитектура переносится механически.

## Технология

| Слой      | Выбор                                                        |
| --------- | ------------------------------------------------------------ |
| GUI       | Python 3 + **PyQt6** (`python3-pyqt6`, trixie; PySide6 в Debian нет) |
| Компоновка| `QStackedWidget` + боковая навигация шагов (как у Deepin Installer) |
| Запуск    | `pkexec /usr/bin/photon-installer` (в live-сессии пароль `live`) |
| Бэкенд    | чистый python: `subprocess` для sfdisk/tar/dpkg/grub, без shell-скриптов |
| Источник  | `/run/live/medium/live/filesystem.squashfs` (loop-mount) → tar → `/target` |

## Экраны (мастер)

1. **Приветствие** — язык (ru/en; смена языка перекрашивает мастер сразу),
   часовой пояс (список `zoneinfo`, зона подхватывается из `/etc/localtime`).
2. **Клавиатура** — раскладка (15 основных), тестовое поле ввода.
3. **Диск** — опрос через `lsblk -Jb`: модель, размер, SSD/HDD/USB, метка
   «есть данные → будет стёрт»; авто-разметка (GPT, ESP 512 МиБ, swap
   по желанию) с живым планом; ручной режим — позже (M4).
4. **Пользователь** — имя, логин (валидация), пароль с показом, hostname.
5. **Окружение** — карточки с бейджами: **LXQt** (фирменный, по умолчанию),
   **без окружения** (консольная база), XFCE/KDE/GNOME («в планах»).
6. **Сводка** — всё выбиранное на одном экране, кнопка «Установить».
7. **Установка** — 12 шагов бэкенда с живым журналом; пароли в журнал
   не попадают; после ошибки доступен «Назад».
8. **Готово** — «Перезагрузить» в установленную систему.

### Что делает бэкенд

| Шаг | Содержимое |
| --- | --- |
| Разметка | `sfdisk`: GPT — ESP 512 МиБ (type U), swap 4 ГиБ (опция), корень |
| ФС | `wipefs`, `mkfs.vfat` ESP, `mkswap`+`swapon`, `mkfs.ext4 -L photon` |
| Монтирование | корень в `/target`, ESP в `/target/boot/efi` |
| Копирование | loop-mount squashfs → tar-поток в `/target` (исключены `/proc`, `/sys`, `/dev`, `/run`, fstab, machine-id и пр.), пересоздание точек монтирования |
| chroot | `/proc`, `/dev`, `/sys` — для dpkg-хуков и grub |
| Очистка | `dpkg --purge live-boot live-config live-tools user-setup xdotool`; `machine-id` опустошается; photon-diag отключается; для «без окружения» — dpkg-снятие десктоп-стека |
| fstab | по `blkid` UUID: `/`, `/boot/efi`, swap, `tmpfs /tmp` |
| Настройка | hostname, hosts, `/etc/locale.gen` + `locale-gen`, `/etc/default/locale`, часовой пояс, `/etc/default/keyboard` |
| Пользователи | `useradd -m -G sudo,audio,video,storage,input,cdrom,netdev`, `chpasswd` (stdin скрыт) |
| Загрузчик | `grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=PhotonOS`, `grub-mkconfig` + fallback-копия `EFI/boot/bootx64.efi` |
| Initramfs | `update-initramfs -u -k all` (после purge live-пакетов — уже без live-хуков) |
| Размонтирование | `swapoff`, `umount -R /target`, отмонтировать squashfs |

Сервисы (sddm, NetworkManager) включены ещё на этапе сборки ISO — копия
squashfs переносит эти симлинки как есть. Установку выполнять только из
**UEFI-сессии**: `grub-install` для x86_64-efi требует живого efivarfs.

## Проверка

```sh
# 1) сухой прогон без диска — печать всех команд в журнал
python3 scripts/installer_tests.py          # юнит-тесты логики без Qt
./installer/photon-installer --dev --fake-disks --dry-run

# 2) полная проверка в QEMU: ISO из CI + целевой диск
qemu-img create -f qcow2 target.qcow2 16G
qemu-system-x86_64 -m 4G -bios OVMF.fd \
    -drive file=PhotonOS-live-amd64-YYYYMMDD.iso,media=cdrom \
    -drive file=target.qcow2,if=virtio
# в live-сессии: pkexec photon-installer → пройти мастер → перезагрузка с диска
```

## Структура

```text
installer/
├── photon-installer          # точка входа: QApplication + MainWindow
├── photon_install/
│   ├── __init__.py
│   ├── wizard.py             # шаги мастера, боковая навигация
│   ├── backend.py            # 12 шагов: sfdisk → tar-копия → dpkg → GRUB
│   ├── disk.py               # lsblk-опрос и план авто-разметки (без Qt)
│   ├── settings.py           # InstallSettings + варианты окружений
│   ├── locale.py             # строки ru/en
│   └── style.py              # палитра и QSS в духе Deepin
└── photon-installer.desktop  # ярлык в live-сессии (pkexec)
```

В ISO ставится `build/build-iso.sh`: модуль в `/usr/lib/photon_install`,
точка входа в `/usr/bin/photon-installer`, ярлык в
`/usr/share/applications/photon-installer.desktop`.

## Вехи

- [x] **M1** — каркас мастера, все шаги, опрос дисков через `lsblk -Jb`,
      выбор окружения, сводка; ru/en с живой сменой языка.
- [x] **M2** — бэкенд (Void: sfdisk → xbps-install → GRUB → fstab), экран
      прогресса с журналом, dry-run. История сохранена в git (до переезда
      на Debian).
- [x] **M3** — Debian-порт: источник — копия live-squashfs (офлайн, система
      = live-ISO 1:1), PyQt6 вместо PySide6, systemd вместо runit,
      `locale-gen` вместо `glibc-locales`, purge live-компонентов,
      честный режим «без окружения».
- **M4** — ручная разметка, обработка ошибок, тесты на пустых дисках.
- **M5** — E2E-прогон установщика в QEMU (UEFI) с загрузкой с установленного
  диска.
