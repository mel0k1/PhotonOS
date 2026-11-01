# Сборка ISO PhotonOS

ISO собирается через [void-mklive](https://github.com/void-linux/void-mklive) —
тот же инструмент, которым Void собирает свои официальные образы. PhotonOS
добавляет поверх него: свой пакетный список, runit-сервисы, оверлей брендинга
(`os-release`, `motd`, `issue`) и утилиты `ppm` / `photon-fetch`.

## Требования

- Хост **Void Linux x86_64** (mklive официально не гарантирует работу на других
  дистрибутивах; на CI используется Void-контейнер — см. ниже).
- `git` (остальное — xbps — уже есть на Void).
- ~10 ГБ свободного места (кэш пакетов + корневая ФС + ISO).

## Быстрый старт

```sh
./build/build-iso.sh
```

Скрипт сам клонирует `void-mklive` в `./void-mklive` (если его нет), соберёт
овлей, скачает пакеты и выдаст:

```text
dist/PhotonOS-live-x86_64-ГГГГММДД.iso
```

Параметры образа задаются двумя списками:

- `build/packages.list` — пакеты live-образа (по одному на строку, `#` —
  комментарии). Ядро — `linux-lts`, задаётся флагом `-v` в `build-iso.sh`.
- `build/services.list` — runit-сервисы, включаемые в образе
  (`/etc/sv/<имя>`).

Утилиты и брендинг попадают в образ из каталогов `ppm/`, `fetch/`, `overlay/`
(механизм: mklive `-I` — включение каталога в корень образа).

## Переменные окружения

| Переменная   | По умолчанию                                    | Назначение            |
| ------------ | ------------------------------------------------ | --------------------- |
| `ARCH`       | `x86_64`                                          | архитектура ISO (glibc) |
| `REPO`       | `https://repo-default.voidlinux.org/current`      | репозиторий XBPS      |
| `MKLIVE_DIR` | `./void-mklive`                                   | путь к клону mklive   |

Пример: собрать с зеркалом CI и другим каталогом mklive:

```sh
REPO=https://repo-ci.voidlinux.org/current MKLIVE_DIR=/tmp/mklive ./build/build-iso.sh
```

## Локаль и раскладка в образе

`build-iso.sh` оставляет дефолты mklive (`en_US.UTF-8`, `us`). Чтобы baked-in
сразу были русские локаль и раскладка, добавьте в конец команды в скрипте:

```sh
-l ru_RU.UTF-8 -k ru
```

## Сборка в контейнере (хост не-Void)

Void публикует готовый образ сборщика. На любом Linux-хосте с Docker:

```sh
docker run --rm --privileged -v /dev:/dev -v "$PWD":/work -w /work \
  ghcr.io/void-linux/void-mklive:20250116R1 \
  ./build/build-iso.sh
```

Ровно этот рецепт использует наш CI (`.github/workflows/build.yml`): сборка
запускается на каждый push в `main` и на ручной запуск (workflow_dispatch),
готовый ISO публикуется артефактом. Тег образа закреплён — при обновлении
mklive поднимите его вручную.

## Установка на диск

Установка с образа — штатный `void-installer` из live-сессии (инструмент
Void, включён в базу). После установки `ppm` и `photon-fetch` в системе уже
есть, `sddm` стартует графическую сессию автоматически.
