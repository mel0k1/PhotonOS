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

## Статус

- `pkg/` — сейчас план и документация, первые шаблоны появятся здесь же
  (см. [pkg/README.md](../pkg/README.md)).
- Цель — `photon-dde` метапакет, который притянет весь рабочий стол, и
  переключение `build/packages.list` на DDE.
