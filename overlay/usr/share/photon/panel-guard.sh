#!/bin/sh
# photon-panel-guard: lxqt-panel 2.1 изредка стартует окном без геометрии
# (гонка QScreen/XRandR в TCG/q35). Ждём валидный размер окна "LXQt Panel";
# не дождались за 150с - один рестарт панели.

i=0
while [ "$i" -lt 30 ]; do
    sleep 5
    line=$(xwininfo -root -tree 2>/dev/null | grep -i '"lxqt panel"' | head -1)
    if [ -n "$line" ]; then
        w=$(printf '%s' "$line" | sed -n \
            's/^ *0x[0-9a-fA-F]* "[^"]*": *([^)]*) *\([0-9][0-9]*\)x.*/\1/p')
        if [ -n "$w" ] && [ "$w" -ge 200 ] 2>/dev/null; then
            exit 0   # панель отрисовалась штатно — guard не нужен
        fi
    fi
    i=$((i + 1))
done

# панель так и не развернулась: рестарт с конфигом пользователя
pkill lxqt-panel 2>/dev/null
sleep 2
setsid lxqt-panel >/dev/null 2>&1 &
exit 0
