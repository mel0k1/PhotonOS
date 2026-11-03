#!/bin/sh
# Сборка live-ISO PhotonOS на базе Debian (suite: trixie).
#
# Пайплайн:
#   1. mmdebstrap (mode auto: root на CI, unshare на Void-хосте) — корень;
#      пакеты из build/packages.list идут через --include (apt у mmdebstrap
#      сам делает update из своих же источников — хук host-путей не видит);
#      мусор (доки/man/локали) режется dpkg-паттернами --dpkgopt ДО установки
#   2. customize-хук: пересборка initramfs (после live-boot/plymouth),
#       сервисы, EFI-загрузчик со встроенным конфигом
#   3. брендинг: overlay/ (LXQt-дизайн, обои, иконки photon), plymouth-тема
#      photon-boot (чёрный квадрат с глазами), os-release, motd
#   4. mksquashfs -> live/filesystem.squashfs
#   5. isolinux (BIOS) + bootx64.efi (EFI) -> xorriso -> ISO
#
# Хосту нужны: mmdebstrap, squashfs-tools, xorriso, mtools, dosfstools
# (в CI ставит workflow). Результат: dist/PhotonOS-live-amd64-<дата>.iso
set -eu

ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
SUITE="${SUITE:-trixie}"
MIRROR="${MIRROR:-https://deb.debian.org/debian}"
ARCH="${ARCH:-amd64}"
OUT_DIR="$ROOT/dist"
WORK="$ROOT/build/.work"

log() { printf '\033[36m==> \033[1m%s\033[0m\n' "$1"; }

PKGS=$(grep -vE '^[[:space:]]*(#|$)' "$ROOT/build/packages.list" | paste -sd,)
STAMP=$(date +%Y%m%d)
OUT="$OUT_DIR/PhotonOS-live-$ARCH-$STAMP.iso"

mkdir -p "$OUT_DIR" "$WORK"
ROOTFS="$WORK/rootfs"
ISO="$WORK/iso"
rm -rf "$ROOTFS" "$ISO"
mkdir -p "$ROOTFS" "$ISO"

# ------------------------------------------------------- 1. хук кастомизации
# ВАЖНО: mmdebstrap исполняет customize-хук НА ХОСТЕ (без chroot), передавая
# корень как $1. Весь гостевой код — через `chroot "$1"`.
HOOK="$WORK/photon-hook.sh"
cat > "$HOOK" <<'EOS'
#!/bin/sh
set -eu
chroot "$1" /bin/sh <<'CHROOT'
set -eu
export DEBIAN_FRONTEND=noninteractive

# локали: генерируем en_US + ru_RU сразу в chroot (live-config в boot
# генерировать не успевает — сессия стартует с C-локалью, Qt ругается)
if [ -f /etc/locale.gen ]; then
    sed -i 's/^# *\(ru_RU.UTF-8 UTF-8\)/\1/;s/^# *\(en_US.UTF-8 UTF-8\)/\1/' /etc/locale.gen
    locale-gen
    update-locale LANG=en_US.UTF-8
fi

# initramfs мог собраться до live-boot/plymouth — пересобираем с их хуками
DEBIAN_FRONTEND=noninteractive update-initramfs -u -k all

# сервисы: дисплейный менеджер и сеть
systemctl enable sddm.service NetworkManager.service photon-diag.service 2>/dev/null || true

# EFI-загрузчик со встроенным конфигом и брендированным фоном (bg.png кладёт
# предыдущий хук copy-in). Пишем в /root: mmdebstrap вычищает /tmp чрута.
cat > /tmp/grub-live.cfg <<'GRUB'
set timeout=5
set default=0
loadfont (memdisk)/boot/grub/fonts/unicode.pf2
set gfxmode=1024x768
set gfxpayload=keep
insmod all_video
insmod png
insmod gfxterm
terminal_output gfxterm
background_image (memdisk)/boot/grub/bg.png
menuentry "PhotonOS Live" {
    linux /live/vmlinuz boot=live components quiet splash username=anon console=tty0 console=ttyS0,115200
    initrd /live/initrd
}
menuentry "PhotonOS Live (RAM)" {
    linux /live/vmlinuz boot=live components quiet splash username=anon rd.live.ram console=tty0 console=ttyS0,115200
    initrd /live/initrd
}
GRUB
grub-mkstandalone -O x86_64-efi -o /root/bootx64.efi \
    "boot/grub/grub.cfg=/tmp/grub-live.cfg" \
    "boot/grub/bg.png=/root/bg.png" \
    "boot/grub/fonts/unicode.pf2=/usr/share/grub/unicode.pf2"

apt-get clean
rm -rf /var/lib/apt/lists/* /var/tmp/*
CHROOT
EOS
chmod +x "$HOOK"

log "mmdebstrap: корень Debian $SUITE + пакеты PhotonOS"
mmdebstrap \
    --mode=auto \
    --variant=apt \
    --architectures="$ARCH" \
    --aptopt='Acquire::Retries "3"' \
    --aptopt='Apt::Install-Recommends "false"' \
    --dpkgopt='path-exclude=/usr/share/doc/*' \
    --dpkgopt='path-exclude=/usr/share/man/*' \
    --dpkgopt='path-exclude=/usr/share/locale/*' \
    --dpkgopt='path-include=/usr/share/locale/ru*' \
    --dpkgopt='path-include=/usr/share/locale/en*' \
    --include="$PKGS" \
    --customize-hook="copy-in $ROOT/design/boot/bg.png /root" \
    --customize="$HOOK" \
    "$SUITE" "$ROOTFS" "$MIRROR"

# EFI-загрузчик лежит в rootfs/root (tmp mmdebstrap вычищает сам)
log "загрузчики: перенос bootx64.efi"
mkdir -p "$ISO/EFI/boot"
if [ -s "$ROOTFS/root/bootx64.efi" ]; then
    cp "$ROOTFS/root/bootx64.efi" "$ISO/EFI/boot/bootx64.efi"
    rm -f "$ROOTFS/root/bootx64.efi" "$ROOTFS/root/bg.png"
else
    echo "ОШИБКА: grub-mkstandalone не создал bootx64.efi" >&2
    ls -la "$ROOTFS/root/" 2>/dev/null || true
    exit 1
fi

# ------------------------------------------------- 2. оверлей и брендинг
log "оверлей PhotonOS: LXQt-дизайн, брендинг, plymouth photon-boot"
cp -a "$ROOT/overlay/." "$ROOTFS/"
chmod +x "$ROOTFS/usr/share/photon/diag.sh" \
       "$ROOTFS/usr/share/photon/desktop-sync.sh"
# photon-diag: юнит появляется только с оверлеем — включаем симлинком здесь
# (systemctl enable в customize-хуке mmdebstrap отработал РАНЬШЕ оверлея)
mkdir -p "$ROOTFS/etc/systemd/system/multi-user.target.wants"
ln -sf ../photon-diag.service \
    "$ROOTFS/etc/systemd/system/multi-user.target.wants/photon-diag.service"

# PipeWire для всех пользователей: глобальные user-юниты (локальный enable
# юзера live-config не применяет пресеты — иконка звука оставалась красной)
mkdir -p "$ROOTFS/etc/systemd/user/sockets.target.wants" \
         "$ROOTFS/etc/systemd/user/default.target.wants" \
         "$ROOTFS/etc/systemd/user/pipewire.service.wants"
ln -sf /usr/lib/systemd/user/pipewire.socket \
    "$ROOTFS/etc/systemd/user/sockets.target.wants/pipewire.socket"
ln -sf /usr/lib/systemd/user/pipewire-pulse.socket \
    "$ROOTFS/etc/systemd/user/sockets.target.wants/pipewire-pulse.socket"
ln -sf /usr/lib/systemd/user/pipewire.service \
    "$ROOTFS/etc/systemd/user/default.target.wants/pipewire.service"
ln -sf /usr/lib/systemd/user/wireplumber.service \
    "$ROOTFS/etc/systemd/user/pipewire.service.wants/wireplumber.service"

install -Dm0755 "$ROOT/fetch/photon-fetch" "$ROOTFS/usr/bin/photon-fetch"
mkdir -p "$ROOTFS/usr/share/plymouth/themes"
cp -a "$ROOT/branding/plymouth/photon-boot" \
    "$ROOTFS/usr/share/plymouth/themes/photon-boot"

# дефолтная plymouth-тема = photon-boot (альтернатива вручную — live ISO)
ln -sfn /usr/share/plymouth/themes/photon-boot/photon-boot.plymouth \
    "$ROOTFS/usr/share/plymouth/themes/default.plymouth"

# hostname
echo photon > "$ROOTFS/etc/hostname"

# чистка
rm -rf "$ROOTFS/var/lib/apt/lists/"* "$ROOTFS/var/tmp/"* "$ROOTFS/tmp/"* 2>/dev/null || true

# ------------------------------------------------------------- 3. squashfs
log "mksquashfs -> live/filesystem.squashfs"
mkdir -p "$ISO/live"
cp "$ROOTFS"/boot/vmlinuz-* "$ISO/live/vmlinuz"
cp "$ROOTFS"/boot/initrd.img-* "$ISO/live/initrd"
mksquashfs "$ROOTFS" "$ISO/live/filesystem.squashfs" \
    -comp xz -b 1M -noappend -e boot

# --------------------------------------------------------- 4. загрузчики
log "загрузчики: isolinux (BIOS) + bootx64.efi (EFI)"
mkdir -p "$ISO/isolinux"

if [ -f "$ROOTFS/usr/lib/ISOLINUX/isolinux.bin" ]; then
    cp "$ROOTFS/usr/lib/ISOLINUX/isolinux.bin" "$ISO/isolinux/"
    cp "$ROOTFS/usr/lib/syslinux/modules/bios/ldlinux.c32" "$ISO/isolinux/" 2>/dev/null || true
    cp "$ROOTFS/usr/lib/syslinux/modules/bios/vesamenu.c32" "$ISO/isolinux/" 2>/dev/null || true
    cp "$ROOTFS/usr/lib/syslinux/modules/bios/libcom32.c32" "$ISO/isolinux/" 2>/dev/null || true
    cp "$ROOTFS/usr/lib/syslinux/modules/bios/libutil.c32" "$ISO/isolinux/" 2>/dev/null || true
    cp "$ROOT/design/boot/bg.png" "$ISO/bg.png"
    cat > "$ISO/isolinux/isolinux.cfg" <<'EOF'
default vesamenu.c32
prompt 0
timeout 50

MENU RESOLUTION 1024 768
MENU BACKGROUND /bg.png
MENU TITLE Photon OS

label photon
    menu label PhotonOS Live
    kernel /live/vmlinuz
    append initrd=/live/initrd boot=live components quiet splash username=anon console=tty0 console=ttyS0,115200

label ram
    menu label PhotonOS Live (RAM)
    kernel /live/vmlinuz
    append initrd=/live/initrd boot=live components quiet splash username=anon rd.live.ram console=tty0 console=ttyS0,115200
EOF
fi

# EFI El Torito: FAT-образ с bootx64.efi
if [ -s "$ISO/EFI/boot/bootx64.efi" ]; then
    dd if=/dev/zero of="$ISO/efiboot.img" bs=1M count=8 status=none
    mkfs.vfat "$ISO/efiboot.img" >/dev/null
    mmd -i "$ISO/efiboot.img" ::EFI ::EFI/boot
    mcopy -i "$ISO/efiboot.img" "$ISO/EFI/boot/bootx64.efi" ::EFI/boot/
fi

# ------------------------------------------------------------ 5. ISO
log "xorriso -> $OUT"
HYBRID=$(ls "$ROOTFS/usr/lib/ISOLINUX/isohdpfx.bin" 2>/dev/null || true)
set -- xorriso -as mkisofs -r -V "PHOTONOS_LIVE" -J -joliet-long
if [ -n "$HYBRID" ]; then
    set -- "$@" -isohybrid-mbr "$HYBRID" \
        -b isolinux/isolinux.bin -c isolinux/boot.cat \
        -no-emul-boot -boot-load-size 4 -boot-info-table
fi
if [ -f "$ISO/efiboot.img" ]; then
    set -- "$@" -eltorito-alt-boot -e efiboot.img -no-emul-boot \
        -isohybrid-gpt-basdat
fi
set -- "$@" -o "$OUT" "$ISO"
"$@"

log "готово: $OUT ($(du -h "$OUT" | cut -f1))"
