#!/bin/sh
# Сборка live-ISO PhotonOS (Debian, suite: trixie):
# mmdebstrap -> customize-хук -> overlay/брендинг -> mksquashfs ->
# isolinux (BIOS) + bootx64.efi (EFI) -> xorriso.
# Хосту: mmdebstrap, squashfs-tools, xorriso, mtools, dosfstools.
# Результат: dist/PhotonOS-live-amd64-<дата>.iso
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

# Возобновляемость: маркер после mmdebstrap - повторный запуск пропускает bootstrap
if [ -f "$ROOTFS/.photon-rootfs-done" ]; then
    log "resume: rootfs уже готов — пропускаю mmdebstrap"
    SKIP_ROOTFS=1
else
    SKIP_ROOTFS=0
    # кэш скачанных deb переживает wipe (докачка после обрыва)
    if [ -d "$ROOTFS/var/cache/apt/archives" ]; then
        rm -rf "$WORK/apt-cache-keep"
        mv "$ROOTFS/var/cache/apt/archives" "$WORK/apt-cache-keep"
    fi
    rm -rf "$ROOTFS" "$ISO"
    mkdir -p "$ROOTFS" "$ISO"
    if [ -d "$WORK/apt-cache-keep" ]; then
        mkdir -p "$ROOTFS/var/cache/apt"
        mv "$WORK/apt-cache-keep" "$ROOTFS/var/cache/apt/archives"
    fi
fi

# ------------------------------------------------------- 1. хук кастомизации
# хук исполняется НА ХОСТЕ (корень = $1), гостевой код - через chroot
HOOK="$WORK/photon-hook.sh"
cat > "$HOOK" <<'EOS'
#!/bin/sh
set -eu
chroot "$1" /bin/sh <<'CHROOT'
set -eu
export DEBIAN_FRONTEND=noninteractive

# локали: генерируем сразу в chroot - live-config в boot не успевает
if [ -f /etc/locale.gen ]; then
    sed -i 's/^# *\(ru_RU.UTF-8 UTF-8\)/\1/;s/^# *\(en_US.UTF-8 UTF-8\)/\1/' /etc/locale.gen
    locale-gen
    update-locale LANG=ru_RU.UTF-8
fi

# initramfs мог собраться до live-boot/plymouth — пересобираем с их хуками
DEBIAN_FRONTEND=noninteractive update-initramfs -u -k all

# сервисы: дисплейный менеджер и сеть; zram/earlyoom - слабые ПК
systemctl enable sddm.service NetworkManager.service photon-diag.service \
    zramswap.service earlyoom.service 2>/dev/null || true

# EFI-загрузчик со встроенным конфигом (bg.png кладёт предыдущий хук);
# пишем в /root - mmdebstrap вычищает /tmp чрута.
cat > /tmp/grub-live.cfg <<'GRUB'
set timeout=5
set default=0
loadfont (memdisk)/boot/grub/fonts/ascii.pf2
set gfxmode=1024x768
set gfxpayload=keep
insmod all_video
insmod png
insmod gfxterm
terminal_output gfxterm
background_image (memdisk)/boot/grub/bg.png
# search обязателен: без него /live/vmlinuz ищется в memdisk ("file not found")
search --no-floppy --set=root --file /live/vmlinuz
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
    "boot/grub/fonts/ascii.pf2=/usr/share/grub/ascii.pf2"

apt-get clean
rm -rf /var/lib/apt/lists/* /var/tmp/*
CHROOT
EOS
chmod +x "$HOOK"

log "mmdebstrap: корень Debian $SUITE + пакеты PhotonOS"
if [ "$SKIP_ROOTFS" = "1" ]; then
    log "resume: фаза mmdebstrap пропущена"
else
# MMDEBSTRAP_MODE/EXTRA_ARGS - флаги mmdebstrap (на CI с урезанным seccomp
# помогает fakechroot); PHOTON_CHROOT_SHIM - шим chroot, инжектится extract-хуком.
set --
if [ -n "${PHOTON_CHROOT_SHIM:-}" ] && [ "$MMDEBSTRAP_MODE" = "fakechroot" ]; then
    set -- "$@" --extract-hook \
        "cp $PHOTON_CHROOT_SHIM \$1/usr/sbin/chroot"
    if [ -n "${PHOTON_PRESEED:-}" ]; then
        set -- "$@" --extract-hook "$PHOTON_PRESEED \$1"
    fi
fi
for a in ${MMDEBSTRAP_EXTRA_ARGS:-}; do
    set -- "$@" "$a"
done
mmdebstrap \
    --mode="${MMDEBSTRAP_MODE:-auto}" \
    "$@" \
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
touch "$ROOTFS/.photon-rootfs-done"
fi

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
       "$ROOTFS/usr/share/photon/desktop-sync.sh" \
       "$ROOTFS/usr/share/photon/panel-guard.sh"
# photon-diag включаем после оверлея: в customize-хуке юнита ещё нет
mkdir -p "$ROOTFS/etc/systemd/system/multi-user.target.wants"
ln -sf ../photon-diag.service \
    "$ROOTFS/etc/systemd/system/multi-user.target.wants/photon-diag.service"

# декорации openbox в тон темы (fallback, пока у юзера нет своего rc.xml)
if [ -f "$ROOTFS/etc/xdg/openbox/rc.xml" ]; then
    sed -i '/<theme>/,/<\/theme>/ s|<name>[^<]*</name>|<name>Arc-Dark</name>|' \
        "$ROOTFS/etc/xdg/openbox/rc.xml"
fi

# PipeWire глобальными user-юнитами: локальный enable live-юзера пресеты не применяет
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

# photon-backup: ежедневный таймер пользователя
mkdir -p "$ROOTFS/etc/systemd/user/timers.target.wants"
ln -sf ../photon-backup.timer \
    "$ROOTFS/etc/systemd/user/timers.target.wants/photon-backup.timer"

install -Dm0755 "$ROOT/fetch/photon-fetch" "$ROOTFS/usr/bin/photon-fetch"

# ppm - обёртка над apt: единый вход для установки/обновления
install -m0755 "$ROOT/ppm/ppm" "$ROOTFS/usr/bin/ppm"

# установщик: мастер (PyQt6) + бэкенд — доступны из live-сессии
log "установщик PhotonOS: мастер и бэкенд"
mkdir -p "$ROOTFS/usr/lib/photon_install"
cp -a "$ROOT/installer/photon_install/." "$ROOTFS/usr/lib/photon_install/"
install -m0755 "$ROOT/installer/photon-installer" "$ROOTFS/usr/bin/photon-installer"
install -m0644 "$ROOT/installer/photon-installer.desktop" \
    "$ROOTFS/usr/share/applications/photon-installer.desktop"
find "$ROOTFS/usr/lib/photon_install" -type d -name '__pycache__' \
    -prune -exec rm -rf {} + 2>/dev/null || true

# welcome-окно первого входа: обновления, принтеры, копия, почта
log "photon-welcome: окно первого входа"
mkdir -p "$ROOTFS/usr/lib/photon_welcome"
cp -a "$ROOT/welcome/photon_welcome/." "$ROOTFS/usr/lib/photon_welcome/"
install -m0755 "$ROOT/welcome/photon-welcome" "$ROOTFS/usr/bin/photon-welcome"
install -m0644 "$ROOT/welcome/photon-welcome.desktop" \
    "$ROOTFS/usr/share/applications/photon-welcome.desktop"
install -m0644 "$ROOT/welcome/photon-welcome-autostart.desktop" \
    "$ROOTFS/etc/xdg/autostart/photon-welcome-autostart.desktop"
find "$ROOTFS/usr/lib/photon_welcome" -type d -name '__pycache__' \
    -prune -exec rm -rf {} + 2>/dev/null || true

# photon-backup: rsync-копия домашнего каталога
install -m0755 "$ROOT/backup/photon-backup" "$ROOTFS/usr/bin/photon-backup"
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
    -comp xz -b 1M -noappend -e boot -e .photon-rootfs-done

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
