#!/bin/sh
# photon-diag: срез состояния live-сессии PhotonOS в serial-консоль
# каждые 120 секунд — чтобы поздний наблюдатель на сокете гарантированно
# поймал свежую телеметрию.
while :; do
    {
        echo "===== photon-diag $(date '+%F %T') ====="
        uptime
        echo "--- sddm ---"
        systemctl is-active sddm 2>&1
        pgrep -a sddm | head -3
        echo "--- сессия ---"
        pgrep -a lxqt-session | head -2 || echo "lxqt-session: нет"
        pgrep -a openbox | head -2 || echo "openbox: нет"
        pgrep -a Xorg | head -2 || echo "Xorg: нет"
        echo "--- skel в /home/anon ---"
        ls /home/anon/.config/lxqt/ 2>&1 | head -6
        echo "--- sddm.log tail ---"
        tail -n 25 /var/log/sddm.log 2>&1
        echo "===== end photon-diag ====="
    } > /dev/ttyS0 2>&1
    sleep 120
done
