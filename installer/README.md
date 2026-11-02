# photon-installer — графический установщик PhotonOS

Каркас мастера (веха **M1**, см. [docs/INSTALLER.md](../docs/INSTALLER.md)):
шаги приветствия/клавиатуры/диска/пользователя/окружения/сводки + опрос
дисков через `lsblk`. Реальная установка — M2.

## Запуск (разработка)

```sh
pip install PySide6                 # или из репо Void: xbps-install python3-pyside6
./installer/photon-installer --dev --fake-disks
```

Флаги: `--lang ru|en`, `--fake-disks` (встроенный пример дисков), `--dev`
(без предупреждения о root). Без `--fake-disks` шаг «Диск» опрашивает
реальную систему через `lsblk -Jb`.

## Состав

| Файл                        | Назначение                                   |
| --------------------------- | -------------------------------------------- |
| `photon-installer`          | точка входа (QApplication + MainWindow)      |
| `photon_install/wizard.py`  | шаги мастера, боковая навигация, стиль-обвязка |
| `photon_install/disk.py`    | `lsblk`-опрос, план авто-разметки (чистый python, без Qt) |
| `photon_install/settings.py`| `InstallSettings` + варианты окружений       |
| `photon_install/locale.py`  | строки ru/en                                 |
| `photon_install/style.py`   | палитра и QSS в духе Deepin                  |
| `photon-installer.desktop`  | ярлык в live-сессии (`pkexec`)               |

## Окружения (шаг «Окружение»)

- **LXQt** — фирменный вариант PhotonOS (по умолчанию);
- **MacShell** — macOS Tahoe-стиль для Hyprland (Wayland, Quickshell,
  github.com/0-ss/MacShell) — экспериментальный вариант, интеграция
  отдельной вехой;
- **Без окружения** — базовая система;
- XFCE / KDE Plasma / GNOME — помечены «в планах».
