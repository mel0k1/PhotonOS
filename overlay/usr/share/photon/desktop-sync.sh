#!/bin/sh
# photon-desktop-sync: Корзину создаёт сам pcmanfm-qt (DesktopShortcuts=Trash);
# старый skel-ярлык ловил бейдж «!» (isTrustable). Чистим остаток.
rm -f "$HOME/Desktop/Корзина.desktop" 2>/dev/null
exit 0
