#!/bin/sh
# photon-desktop-sync: смена механизма ярлыка Корзины. Раньше ярлык
# Корзина.desktop приходил из /etc/skel, но pcmanfm-qt вешает на
# недоверенные .desktop бейдж «!» (Fm::FileInfo::isTrustable). Теперь
# корзину создаёт сам pcmanfm-qt: DesktopShortcuts=Trash в settings.conf —
# он генерирует доверенный trash-can.desktop (без бейджа), подпись
# «Корзина (пусто)» из pcmanfm-qt-l10n. Здесь только чистим старый ярлык.
rm -f "$HOME/Desktop/Корзина.desktop" 2>/dev/null
exit 0
