#!/bin/sh
# photon-desktop-sync: live-config создаёт anon не по всем правилам skel —
# ярлыки рабочего стола (Корзина) добираем вручную.
[ -d /etc/skel/Desktop ] || exit 0
mkdir -p "$HOME/Desktop"
cp -n /etc/skel/Desktop/. "$HOME/Desktop/" 2>/dev/null || true
exit 0
