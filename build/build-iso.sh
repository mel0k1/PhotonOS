#!/bin/sh
# Сборка live-ISO PhotonOS через void-mklive.
#
# Требования: хост Void Linux x86_64 (в CI — контейнер ghcr.io/void-linux/void-mklive),
# git, ~12 ГБ свободного места. Ядро образа: linux-lts. Вариант: glibc.
#
# Переменные окружения:
#   ARCH         архитектура ISO (по умолчанию x86_64)
#   REPO         репозиторий XBPS (по умолчанию https://repo-default.voidlinux.org/current)
#   MKLIVE_DIR   путь к клону void-mklive (по умолчанию ./void-mklive, клонируется сам)
#   VP_DIR       путь к клону void-packages для стека Hyprland
#                (по умолчанию ./build/void-packages, клонируется сам)
#   PHOTON_MACSHELL  0 — не ставить MacShell в skel (по умолчанию 1 — ставить)
#
# Результат: dist/PhotonOS-live-<arch>-<дата>.iso
set -eu

ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
ARCH="${ARCH:-x86_64}"
REPO="${REPO:-https://repo-default.voidlinux.org/current}"
MKLIVE_DIR="${MKLIVE_DIR:-$ROOT/void-mklive}"
VP_DIR="${VP_DIR:-$ROOT/build/void-packages}"
OUT_DIR="$ROOT/dist"
STAGE="$ROOT/build/.stage-overlay"
HOSTREPO="$ROOT/build/hostrepo"
MACSHELL="${PHOTON_MACSHELL:-1}"

# Порядок сборки стека Hyprland (топологический; шаблоны в pkg/srcpkgs).
HYPR_CHAIN="lua5.5 hwdata hyprutils hyprlang glaze hyprland-protocols \
aquamarine hyprcursor hyprgraphics hyprwire hyprland hyprlock hypridle \
xdg-desktop-portal-hyprland"

log() { printf '\033[36m==> \033[1m%s\033[0m\n' "$1"; }

# xbps-src в CI-контейнере работает под root только с этим флагом (см. xbps-src)
export XBPS_ALLOW_CHROOT_BREAKOUT=1

log "PhotonOS ISO | arch=$ARCH | repo=$REPO"

# 1. void-mklive
if [ ! -d "$MKLIVE_DIR/.git" ]; then
    log "клонирую void-mklive"
    git clone --depth=1 https://github.com/void-linux/void-mklive.git "$MKLIVE_DIR"
fi

# 2. сцена оверлея: брендинг + утилиты PhotonOS попадают в корень образа
log "готовлю оверлей"
rm -rf "$STAGE"
mkdir -p "$STAGE/usr/bin" "$STAGE/usr/share/plymouth/themes"
cp -a "$ROOT/overlay/." "$STAGE/"
install -m 0755 "$ROOT/ppm/ppm" "$STAGE/usr/bin/ppm"
install -m 0755 "$ROOT/fetch/photon-fetch" "$STAGE/usr/bin/photon-fetch"
# загрузочная анимация: каноническое место — шаблон пакета photon-boot-splash
cp -a "$ROOT/pkg/srcpkgs/photon-boot-splash/files/photon-boot" \
    "$STAGE/usr/share/plymouth/themes/photon-boot"

# графический установщик (installer/, docs/INSTALLER.md)
install -m 0755 "$ROOT/installer/photon-installer" "$STAGE/usr/bin/photon-installer"
mkdir -p "$STAGE/usr/share/photon-installer" "$STAGE/usr/share/applications"
cp -a "$ROOT/installer/photon_install" "$STAGE/usr/share/photon-installer/"
rm -rf "$STAGE/usr/share/photon-installer/photon_install/__pycache__"
install -m 0644 "$ROOT/installer/photon-installer.desktop" \
    "$STAGE/usr/share/applications/photon-installer.desktop"
chmod +x "$STAGE/usr/share/applications/photon-installer.desktop"

# 3. MacShell (macOS Tahoe-стиль поверх Hyprland) -> /etc/skel, чтобы и
# live-сессия, и установленный пользователь получали готовую настройку.
# Ставим штатным install.sh из вендоренной копии (pkg/vendor/MacShell):
# он копирует Quickshell-модули, пишет macshell.lua и хуки в hyprland.lua.
if [ "$MACSHELL" = 1 ]; then
    log "ставлю MacShell в skel (install.sh --local)"
    SKEL="$STAGE/etc/skel"
    # базовый hyprland.lua лежит в overlay/etc/skel — install.sh допишет
    # require("macshell") и Liquid-Glass правила сам
    # install.sh требует bash; git-контекст не нужен (--local)
    ( cd "$ROOT/pkg/vendor/MacShell" && HOME="$SKEL" bash install.sh \
        --local --no-deps --no-services --no-gui --no-start --no-verify \
        --no-auto-update -y ) > /dev/null
    log "MacShell -> $SKEL/.config/quickshell"
fi

# 4. локальный репозиторий со стеком Hyprland (в upstream Void пакетов нет):
# xbps-src собирает цепочку из pkg/srcpkgs, xbps-rindex подписывает и
# отдаёт репозиторий mklive через -r. Отключается: PHOTON_HYPR=0.
LOCAL_REPO_ARGS=""
if [ "${PHOTON_HYPR:-1}" = 1 ]; then
    log "собираю стек Hyprland: $HYPR_CHAIN"
    if [ ! -d "$VP_DIR/.git" ]; then
        git clone --depth=1 https://github.com/void-linux/void-packages.git "$VP_DIR"
    fi
    "$ROOT/pkg/build.sh" "$VP_DIR"
    ( cd "$VP_DIR" && ./xbps-src binary-bootstrap )
    # xbps в контейнере 0.59, свежее дерево требует >= 0.60
    ( cd "$VP_DIR" && ./xbps-src bootstrap-update )
    for p in $HYPR_CHAIN; do
        ( cd "$VP_DIR" && ./xbps-src pkg "$p" )
    done
    mkdir -p "$HOSTREPO"
    cp "$VP_DIR/hostdir/binpkgs/"*.xbps "$HOSTREPO/"
    ( cd "$HOSTREPO" && xbps-rindex -a ./*.xbps )
    # подписываем repodata свежим ключом: xbps-install принимает репозиторий
    # с неизвестным ключом с предупреждением, неподписанный — отклоняет
    PRIVKEY=$(mktemp)
    openssl genrsa -out "$PRIVKEY" 2048 2>/dev/null || true
    ( cd "$HOSTREPO" && xbps-rindex --privkey "$PRIVKEY" -s --signedby "PhotonOS CI" . ) \
        || true
    rm -f "$PRIVKEY"
    LOCAL_REPO_ARGS="-r $HOSTREPO"
    log "локальный репо: $HOSTREPO ($(ls "$HOSTREPO"/*.xbps | wc -l) пакетов)"
fi

# 5. пакеты и сервисы из списков (комментарии и пустые строки игнорируются)
PKGS=$(grep -vE '^[[:space:]]*(#|$)' "$ROOT/build/packages.list" | tr '\n' ' ')
SVC=$(grep -vE '^[[:space:]]*(#|$)' "$ROOT/build/services.list" | tr '\n' ' ')

mkdir -p "$OUT_DIR"
OUT="$OUT_DIR/PhotonOS-live-$ARCH-$(date +%Y%m%d).iso"

# 6. mklive: glibc-архитектура, ядро linux-lts, оверлей, пакеты, сервисы
# -C "quiet splash" — командная строка ядра для plymouth-анимации
cd "$MKLIVE_DIR"
set -- ./mklive.sh \
    -a "$ARCH" \
    $LOCAL_REPO_ARGS \
    -r "$REPO" \
    -v linux-lts \
    -T "PhotonOS Live" \
    -I "$STAGE" \
    -o "$OUT" \
    -p "$PKGS" \
    -C "quiet splash"
if [ -n "$SVC" ]; then
    set -- "$@" -S "$SVC"
fi

log "запускаю: $*"
exec "$@"
