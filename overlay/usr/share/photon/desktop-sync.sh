#!/bin/sh
# photon-desktop-sync: live-config создаёт anon не по всем правилам skel —
# ярлыки рабочего стола (Корзина) добираем вручную.
[ -d /etc/skel/Desktop ] || exit 0
mkdir -p "$HOME/Desktop"
cp -n /etc/skel/Desktop/. "$HOME/Desktop/" 2>/dev/null || true
# ярлык должен быть исполняемым, иначе pcmanfm-qt рисует на нём бейдж «!»
# (untrusted launcher, Fm::FileInfo::isTrustable)
for d in "$HOME"/Desktop/*.desktop; do
    [ -f "$d" ] && chmod 755 "$d" 2>/dev/null
done
exit 0
