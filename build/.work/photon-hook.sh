#!/bin/sh
set -eu
export DEBIAN_FRONTEND=noninteractive
apt-get update
printf '%s\n' \
    'path-exclude=/usr/share/doc/*' \
    'path-exclude=/usr/share/man/*' \
    'path-exclude=/usr/share/locale/*' \
    'path-include=/usr/share/locale/ru*' \
    'path-include=/usr/share/locale/en*' \
    > /etc/dpkg/dpkg.cfg.d/01-photon-lean
rm -rf /usr/share/doc/* /usr/share/man/* 2>/dev/null || true
xargs -a /tmp/photon-packages.txt apt-get install -y --no-install-recommends
systemctl enable sddm.service NetworkManager.service 2>/dev/null || true
cat > /tmp/grub-live.cfg <<'GRUB'
set timeout=5
set default=0
menuentry "PhotonOS Live" {
    linux /live/vmlinuz boot=live components quiet splash console=ttyS0,115200
    initrd /live/initrd
}
GRUB
if [ -x /usr/bin/grub-mkstandalone ]; then
    grub-mkstandalone -O x86_64-efi -o /tmp/bootx64.efi "boot/grub/grub.cfg=/tmp/grub-live.cfg" || true
fi
apt-get clean
rm -rf /var/lib/apt/lists/* /var/tmp/*
