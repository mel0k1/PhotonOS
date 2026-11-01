#!/bin/sh
# Сборка live-ISO PhotonOS через void-mklive.
#
# Требования: хост Void Linux x86_64 (или CI-контейнер ghcr.io/void-linux/void-mklive),
# git, ~10 ГБ свободного места. Ядро образа: linux-lts. Вариант: glibc.
#
# Переменные окружения:
#   ARCH        архитектура ISO (по умолчанию x86_64)
#   REPO        репозиторий XBPS (по умолчанию https://repo-default.voidlinux.org/current)
#   MKLIVE_DIR  путь к клону void-mklive (по умолчанию ./void-mklive, клонируется сам)
#
# Результат: dist/PhotonOS-live-<arch>-<дата>.iso
set -eu

ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
ARCH="${ARCH:-x86_64}"
REPO="${REPO:-https://repo-default.voidlinux.org/current}"
MKLIVE_DIR="${MKLIVE_DIR:-$ROOT/void-mklive}"
OUT_DIR="$ROOT/dist"
STAGE="$ROOT/build/.stage-overlay"

log() { printf '\033[36m==> \033[1m%s\033[0m\n' "$1"; }

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

# 3. пакеты и сервисы из списков (комментарии и пустые строки игнорируются)
PKGS=$(grep -vE '^[[:space:]]*(#|$)' "$ROOT/build/packages.list" | tr '\n' ' ')
SVC=$(grep -vE '^[[:space:]]*(#|$)' "$ROOT/build/services.list" | tr '\n' ' ')

mkdir -p "$OUT_DIR"
OUT="$OUT_DIR/PhotonOS-live-$ARCH-$(date +%Y%m%d).iso"

# 4. mklive: glibc-архитектура, ядро linux-lts, оверлей, пакеты, сервисы
# -C "quiet splash" — командная строка ядра для plymouth-анимации
cd "$MKLIVE_DIR"
set -- ./mklive.sh \
    -a "$ARCH" \
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
