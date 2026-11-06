# Сборка PhotonOS (база Debian)

## Требования

- Хост Debian 12+/Ubuntu 22.04+ с правами root (CI подходит идеально).
- Диск: ~6 ГБ на сборку.
- Инструменты: `mmdebstrap`, `squashfs-tools`, `xorriso`, `mtools`,
  `dosfstools`, ключи архива Debian (`debian-archive-keyring`).

```sh
sudo apt install mmdebstrap squashfs-tools xorriso mtools dosfstools \
    debian-archive-keyring
```

## Сборка

```sh
./build/build-iso.sh
# -> dist/PhotonOS-live-amd64-<дата>.iso
```

Пайплайн `build/build-iso.sh`:

1. **mmdebstrap** разворачивает минимальный корень Debian trixie
   (`--variant=apt`) и в хуке `--customize` ставит пакеты из
   `build/packages.list` без рекомендаций, вычищает документацию,
   man-страницы и лишние локали (dpkg path-exclude), включает
   `sddm` и `NetworkManager`, генерирует EFI-загрузчик.
2. **Оверлей** `overlay/` накладывается на корень: конфиги LXQt в стиле
   Deepin (`etc/skel`), композитор picom (`etc/photon/picom.conf`), обои,
   иконки photon, брендинг (`os-release`, `motd`, `issue`).
3. **Plymouth-тема** `branding/plymouth/photon-boot` (фирменная анимация)
   ставится в `/usr/share/plymouth/themes/photon-boot` и подключается как
   `default.plymouth`; командная строка ядра — `quiet splash`.
4. **mksquashfs** пакует корень в `live/filesystem.squashfs` (xz).
5. **xorriso** собирает гибридный ISO: BIOS (isolinux + isohybrid MBR) и
   EFI (grub-mkstandalone, El Torito FAT-образ).

## Переменные

| Переменная | По умолчанию | Что делает |
|---|---|---|
| `SUITE` | `trixie` |Suite Debian |
| `MIRROR` | `https://deb.debian.org/debian` | Зеркало |
| `ARCH` | `amd64` | Архитектура |

## Проверка в QEMU

```sh
qemu-system-x86_64 -m 2G -enable-kvm -cdrom dist/PhotonOS-live-amd64-*.iso
```

Live-пользователь — `user`, пароль — `live` (стандарт Debian live-config).
Загрузка: BIOS (isolinux) и EFI (grub).
