#!/bin/sh
# pkg/build.sh — подготовка дерева void-packages для сборки пакетов PhotonOS.
#
# Использование: pkg/build.sh <путь-к-void-packages>
#
# Делает две вещи:
#   1. копирует шаблоны из pkg/srcpkgs в <vp>/srcpkgs (симлинки субпакетов
#      сохраняются как симлинки);
#   2. дописывает записи shlibs наших библиотек в <vp>/common/shlibs
#      (идемпотентно, с маркером PhotonOS).
#
# Дальше сборка обычным способом:
#   cd <vp> && ./xbps-src binary-bootstrap && ./xbps-src pkg dtkcore
set -eu

: "${1:?usage: pkg/build.sh <void-packages-dir>}"
VP=$(readlink -f "$1")
SRC=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)

[ -d "$VP/srcpkgs" ] || { echo "void-packages не найден: $VP" >&2; exit 1; }
[ -f "$VP/common/shlibs" ] || { echo "нет $VP/common/shlibs" >&2; exit 1; }

# 1. Шаблоны пакетов.
for d in "$SRC"/srcpkgs/*/; do
    p=$(basename "${d%/}")
    [ -d "${d%/}" ] || continue
    rm -rf "$VP/srcpkgs/$p"
    cp -a "${d%/}" "$VP/srcpkgs/$p"
done
# Симлинки субпакетов (<pkg>-devel и т.п.) — без разыменования.
find "$SRC"/srcpkgs -maxdepth 1 -type l -exec cp -P {} "$VP/srcpkgs/" \;

# 2. Записи shlibs (маркер защищает от повторного добавления).
if ! grep -q 'PhotonOS DDE' "$VP/common/shlibs" 2>/dev/null; then
    printf '\n# PhotonOS DDE\n' >> "$VP/common/shlibs"
    cat "$SRC/shlibs-extra.txt" >> "$VP/common/shlibs"
fi

echo "OK: шаблоны PhotonOS -> $VP/srcpkgs, shlibs дополнены."
