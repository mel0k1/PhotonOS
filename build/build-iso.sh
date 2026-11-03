#!/bin/sh
# Сборка live-ISO PhotonOS на базе Debian (suite: trixie).
#
# Пайплайн:
#   1. mmdebstrap (mode auto: root на CI, unshare на Void-хосте) — минимальный
#      корень; хук --customize ставит пакеты из build/packages.list (список
#      вшивается в хук: в root-режиме хук идёт ВНУТРИ чрута, host-пути там
#      не видны), вычищает мусор (доки/man/локали), включает сервисы,
#      генерирует EFI-загрузчик
#   2. брендинг: overlay/ (LXQt-дизайн, обои, иконки photon), plymouth-тема
#      photon-boot (чёрный квадрат с глазами), os-release, motd
#   3. mksquashfs -> live/filesystem.squashfs
#   4. isolinux (BIOS) + bootx64.efi (EFI) -> xorriso -> ISO
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

PKGS=$(grep -vE '^[[:space:]]*(#|$)' "$ROOT/build/packages.list" | tr '\n' ' ')
STAMP=$(date +%Y%m%d)
OUT="$OUT_DIR/PhotonOS-live-$ARCH-$STAMP.iso"

mkdir -p "$OUT_DIR" "$WORK"
ROOTFS="$WORK/rootfs"
ISO="$WORK/iso"
rm -rf "$ROOTFS" "$ISO"
mkdir -p "$ROOTFS" "$ISO"

# ------------------------------------------------------- 1. хук кастомизации
# Внимание: heredoc БЕЗ кавычек — $PKGS раскрывается при генерации, потому
# что внутри чрута host-файл packages.txt недоступен.
HOOK="$WORK/photon-hook.sh"
cat > "$HOOK" <<EOS
#!/bin/sh
set -eu
export DEBIAN_FRONTEND=noninteractive
apt-get update

# мусор: документация, man, лишние локали — будущие пакеты тоже без них
printf '%s\n' \
    'path-exclude=/usr/share/doc/*' \
    'path-exclude=/usr/share/man/*' \
    'path-exclude=/usr/share/locale/*' \
    'path-include=/usr/share/locale/ru*' \
    'path-include=/usr/share/locale/en*' \
    > /etc/dpkg/dpkg.cfg.d/01-photon-lean
rm -rf /usr/share/doc/* /usr/share/man/* 2>/dev/null || true

DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    $PKGS

# initramfs мог собраться до live-boot/plymouth — пересобираем с их хуками
DEBIAN_FRONTEND=noninteractive update-initramfs -u -k all

# сервисы: дисплейный менеджер и сеть
systemctl enable sddm.service NetworkManager.service 2>/dev/null || true

# EFI-загрузчик со встроенным конфигом (генерируем внутри корня)
cat > /tmp/grub-live.cfg <<'GRUB'
set timeout=5
set default=0
menuentry "PhotonOS Live" {
    linux /live/vmlinuz boot=live components quiet splash username=anon
    initrd /live/initrd
}
menuentry "PhotonOS Live (RAM)" {
    linux /live/vmlinuz boot=live components quiet splash username=anon rd.live.ram
    initrd /live/initrd
}
GRUB
grub-mkstandalone -O x86_64-efi -o /tmp/bootx64.efi \
    "boot/grub/grub.cfg=/tmp/grub-live.cfg"

apt-get clean
rm -rf /var/lib/apt/lists/* /var/tmp/*
EOS
chmod +x "$HOOK"

log "mmdebstrap: корень Debian $SUITE + пакеты PhotonOS"
mmdebstrap \
    --mode=auto \
    --variant=apt \
    --architectures="$ARCH" \
    --aptopt='Acquire::Retries "3"' \
    --customize="$HOOK" \
    "$SUITE" "$ROOTFS" "$MIRROR"

# EFI-загрузчик лежит в rootfs/tmp — забираем ДО чистки /tmp
log "загрузчики: перенос bootx64.efi"
mkdir -p "$ISO/EFI/boot"
if [ -s "$ROOTFS/tmp/bootx64.efi" ]; then
    cp "$ROOTFS/tmp/bootx64.efi" "$ISO/EFI/boot/bootx64.efi"
else
    echo "ОШИБКА: grub-mkstandalone не создал bootx64.efi" >&2
    exit 1
fi

# ------------------------------------------------- 2. оверлей и брендинг
log "оверлей PhotonOS: LXQt-дизайн, брендинг, plymouth photon-boot"
cp -a "$ROOT/overlay/." "$ROOTFS/"
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
    cat > "$ISO/isolinux/isolinux.cfg" <<'EOF'
default photon
prompt 0
timeout 50

label photon
    kernel /live/vmlinuz
    append initrd=/live/initrd boot=live components quiet splash username=anon
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
