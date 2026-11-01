# Упаковка пакетов и путь к DDE

В официальных репозиториях Void Linux пакетов DDE нет (проверено по пакетному
индексу: `deepin`, `dde-*`, `dtk*` — отсутствуют). Поэтому PhotonOS идёт по
пути независимых дистрибутивов: **собственный репозиторий пакетов** поверх
XBPS. Это стандартный и полностью поддерживаемый xbps сценарий — репозиторий
просто добавляется источником.

## Как устроен пакет в мире XBPS

Пакет — это каталог в `srcpkgs/` с файлом `template` (синтаксис описан в
[Manual.md](https://github.com/void-linux/void-packages/blob/master/Manual.md)):

```sh
# srcpkgs/myapp/template — пример-шаблон, значения заполнить из релиза
pkgname=myapp
version=1.0.0        # брать из релиза проекта
revision=1
build_style=cmake    # или gnu-makefile, meson, qmake...
hostmakedepends="cmake pkg-config"
makedepends="libX11-devel"
short_desc="Короткое описание"
maintainer="mel0k1 <218306052+mel0k1@users.noreply.github.com>"
license="GPL-3.0-or-later"
homepage="https://example.org/myapp"
distfiles="${homepage}/archive/v${version}.tar.gz"
checksum=skip       # sha256 архива, обязателен перед публикацией

do_install() {
    vbin myapp
}
```

## Локальная сборка и репозиторий

```sh
# 1. клонировать void-packages и включить наш каталог пакетов
git clone --depth=1 https://github.com/void-linux/void-packages.git
mkdir void-packages/srcpkgs/photon
cp -r pkg/srcpkgs/* void-packages/srcpkgs/photon/   # (структура — по мере появления пакетов)

# 2. собрать пакет
cd void-packages
./xbps-src binarypkg myapp

# 3. поднять локальный репозиторий
mkdir -p /srv/photon-repo
cp hostdir/binpkgs/*.xbps /srv/photon-repo/
xbps-rindex -a /srv/photon-repo/*.xbps

# 4. подключить репозиторий
echo "repository=/srv/photon-repo" > /etc/xbps.d/photon.conf
ppm sync && ppm install myapp
```

Для сборки ISO наш репозиторий передаётся mklive флагом `-r` (в том числе
`-r file:///srv/photon-repo`) — см. `build/build-iso.sh`.

## План упаковки DDE

Целевой состав для рабочего стола (ориентир — компоненты upstream
[linuxdeepin](https://github.com/linuxdeepin), версии брать из их релизов):

1. **Фундамент DTK**: `dtkcore`, `dtkgui`, `dtkwidget`, `qt5platform-plugins`,
   `qt5integration`, `dde-qt-dbus-factory`.
2. **Оболочка**: `dde-session-shell`, `dde-desktop`, `dde-launcher`,
   `dde-dock`, `dde-polkit-agent`.
3. **Приложения**: `deepin-terminal`, `dde-file-manager`, `deepin-calculator`,
   `deepin-image-viewer`.
4. **Системный слой**: интеграция с `elogind` вместо systemd, `dbus`-сервисы,
   апплет сети на базе NetworkManager.

Практические советы:

- начинать с DTK: всё остальное зависит от него;
- ставить `depends=` честно по `pkg-config`, а не «на глаз»;
- патчить systemd-юниты в runit-сервисы или в XDG-автозапуск;
- каждый пакет обязан собираться `xbps-src` на чистом окружении.

## Статус: фундамент DTK упакован

Первые шесть шаблонов лежат в `pkg/srcpkgs/` — весь фундамент DTK для Qt5
(версии и checksums взяты из реальных релизов upstream, имена зависимостей
сверены с пакетным индексом Void):

| Пакет           | Версия   | Что даёт                                    |
| --------------- | -------- | ------------------------------------------- |
| `gsettings-qt`  | 0.2      | QGSettings — настройки Deepin (нет в Void)  |
| `dtkcommon`     | 6.7.52   | cmake-модули `DtkConfig`, `DtkBuildHelper`  |
| `dtklog`        | 0.0.4    | логгер `DtkLog` (systemd опционален: OFF)   |
| `dtkcore`       | 5.7.30   | ядро DTK (Qt5-линия)                        |
| `dtkgui`        | 5.7.30   | темы/окна DTK                               |
| `dtkwidget`     | 5.7.30   | виджеты DTK                                 |

Порядок сборки: `gsettings-qt` и `dtkcommon` → `dtklog` → `dtkcore` →
`dtkgui` → `dtkwidget`.

```sh
cd void-packages
cp -r /путь/к/PhotonOS/pkg/srcpkgs/* srcpkgs/
for p in gsettings-qt dtkcommon dtklog dtkcore dtkgui dtkwidget; do
    ./xbps-src pkg "$p"
done
```

Существенные решения, принятые при упаковке:

- **Qt5, а не Qt6**: master-ветки `linuxdeepin/dtk*` уже Qt6 (6.7.x), поэтому
  зафиксированы теги **5.7.30** — последняя Qt5-линия DTK.
- **systemd не нужен**: у `dtklog` JournalAppender собирается только при
  `BUILD_WITH_SYSTEMD=ON` — на runit-системе выключаем.
- **Легковесность**: у `dtkgui` FreeImage/libraw опциональны и не включены
  (`DTK_DISABLE_EX_IMAGE_FORMAT`); SVG-рендер — системный librsvg.

Что осталось проверить на живой сборке `xbps-src` (честный список рисков):
наличие приватных заголовков Qt5 в пакете `qt5` Void (нужны `Qt5::CorePrivate`
и т.п.); работа umbrella-конфига `DtkConfig` из `dtkcommon` при
`find_package(Dtk COMPONENTS Gui)`; конфиг-тесты treeland у `dtkgui`
(при проблемах — патч на отключение). После обкатки фундамента —
метапакет `photon-dde` и оболочка: `dde-session-shell`, `dde-desktop`,
`dde-launcher`, `dde-dock`, `dde-polkit-agent`, затем приложения
(`deepin-terminal`, `dde-file-manager`, ...).
