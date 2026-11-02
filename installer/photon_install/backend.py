"""Бэкенд установки PhotonOS (M2): разметка -> xbps -> GRUB -> fstab.

Чистый python, без Qt: мастер вызывает Installer из рабочего потока,
прогресс приходит через колбэки. Каждый шаг = список «операций»:

    ("cmd",  argv, stdin_or_None)   — внешняя команда
    ("file", path, content, mode)   — запись файла в /target
    ("call", callable)              — python-действие (копирование файлов)

В dry-run операции только логируются — так бэкенд тестируется без диска.

Пароли никогда не попадают в журнал: stdin команд с паролями маскируется.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field

from . import disk as _disk
from .settings import InstallSettings

TARGET = "/target"
LOG_PATH = "/tmp/photon-installer.log"

REPO = "https://repo-default.voidlinux.org/current"

# База любой установки (UEFI).
BASE_PKGS = [
    "base-system", "linux-lts", "linux-firmware-network",
    "grub-x86_64-efi", "chrony", "nano", "sudo", "NetworkManager",
]

# Наборы по окружению (шаг «Окружение»).
DE_PKGS = {
    "lxqt": [
        "xorg", "sddm", "lxqt", "pcmanfm-qt", "qterminal", "lximage-qt",
        "lxqt-archiver", "obconf-qt", "lxqt-powermanagement",
        "xdg-desktop-portal-lxqt", "openbox", "picom", "papirus-icon-theme",
        "arc-theme", "noto-fonts-ttf", "xdg-user-dirs",
        "network-manager-applet",
    ],
    "none": [],
    # MacShell (M3, docs/MACSHELL.md): Hyprland + Quickshell.
    # hyprland/hyprlock/hypridle/xdg-desktop-portal-hyprland — наши пакеты
    # (pkg/srcpkgs, попадают в ISO через локальный репозиторий);
    # quickshell/awww/kitty/... — из репозитория Void.
    "macshell": [
        "hyprland", "hyprlock", "hypridle", "xdg-desktop-portal-hyprland",
        "quickshell", "awww", "kitty", "cliphist", "grim", "slurp",
        "wl-clipboard", "wf-recorder", "brightnessctl", "inotify-tools",
        "pipewire", "wireplumber", "playerctl", "qt6ct", "font-inter",
        "noto-fonts-emoji", "polkit-gnome", "xdg-desktop-portal",
        "xdg-desktop-portal-gtk", "fastfetch", "noto-fonts-ttf",
        "xdg-user-dirs",
    ],
}

# runit-сервисы в runsvdir/default (сами директории /etc/sv приходят пакетами)
SERVICES_BASE = ["dbus", "elogind", "NetworkManager", "chronyd"]
SERVICES_DE = {"lxqt": ["sddm"], "none": [], "macshell": ["sddm"]}

USER_GROUPS = "wheel,audio,video,storage,input,cdrom"

LOCALES = ["en_US.UTF-8 UTF-8", "ru_RU.UTF-8 UTF-8"]


class BackendError(RuntimeError):
    pass


def part_path(disk_name: str, index: int) -> str:
    """sda -> sda3; nvme0n1 -> nvme0n1p3; mmcblk0 -> mmcblk0p3."""
    sep = "p" if disk_name[-1].isdigit() else ""
    return f"/dev/{disk_name}{sep}{index}"


@dataclass
class Installer:
    settings: InstallSettings
    dry_run: bool = False
    repo: str = REPO
    log_path: str = LOG_PATH

    # колбэки: on_step(key, i, total), on_log(text), on_done()
    on_step: object = None
    on_log: object = None
    on_done: object = None

    steps: list = field(default_factory=list, init=False)
    _log_fh: object = None

    # ── журнал ──────────────────────────────────────────────────────────
    def log(self, text: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {text}"
        if self.on_log:
            self.on_log(line)
        if self._log_fh is None and not self.dry_run:
            self._log_fh = open(self.log_path, "a", encoding="utf-8")
        if self._log_fh:
            self._log_fh.write(line + "\n")
            self._log_fh.flush()

    def close(self) -> None:
        if self._log_fh:
            self._log_fh.close()
            self._log_fh = None

    # ── план шагов ──────────────────────────────────────────────────────
    def run(self) -> None:
        s = self.settings
        try:
            self.steps = self.build_steps()
            total = len(self.steps)
            for i, (key, title, _ops) in enumerate(self.steps):
                if self.on_step:
                    self.on_step(key, i, total)
                self.log(f"── {title}")
                for op in _ops:
                    self._do(op)
            if self.on_step:
                self.on_step("done", total, total)
            self.log("Установка завершена успешно.")
            if self.on_done:
                self.on_done()
        except BackendError as e:
            self.log(f"ОШИБКА: {e}")
            raise
        finally:
            self.close()

    # ── сборка шагов ────────────────────────────────────────────────────
    def build_steps(self) -> list:
        s = self.settings
        d = next((x for x in s.disks if x.path == s.disk), None)
        if d is None:
            raise BackendError(f"диск {s.disk} не найден в опросе — обновите список")

        pkgs = BASE_PKGS + DE_PKGS.get(s.de, [])
        services = SERVICES_BASE + SERVICES_DE.get(s.de, [])
        steps = [
            ("part", "Разметка диска (sfdisk)", self._ops_partition(d)),
            ("mkfs", "Файловые системы", self._ops_mkfs(d)),
            ("mount", "Монтирование /target", self._ops_mount(d)),
            ("pkgs", "Установка базовой системы (xbps)",
             self._ops_packages(pkgs)),
            ("fstab", "fstab и точки монтирования", self._ops_fstab(d)),
            ("chroot", "Подготовка chroot (/proc, /dev, /sys)", self._ops_bind()),
            ("config", "Настройка системы", self._ops_config()),
            ("users", "Пользователи и пароли", self._ops_users()),
            ("svc", "Сервисы runit", self._ops_services(services)),
            ("brand", "Брендинг PhotonOS", self._ops_branding()),
            ("boot", "Загрузчик GRUB (UEFI)", self._ops_bootloader()),
            ("kernel", "Initramfs (xbps-reconfigure linux-lts)",
             self._ops_initramfs()),
            ("umount", "Размонтирование", self._ops_umount(d)),
        ]
        return steps

    def step_title(self, steps: list, key: str) -> str:
        for k, t, _ in steps:
            if k == key:
                return t
        return key

    # ── операции по шагам ───────────────────────────────────────────────
    def _ops_partition(self, d) -> list:
        s = self.settings
        lines = ["label: gpt",
                 "size=512MiB, type=U, bootable"]
        if s.swap:
            lines.append("size=4GiB, type=S")
        lines.append("type=L")
        script = "\n".join(lines) + "\n"
        return [("cmd", ["sfdisk", "-f", d.path], script)]

    def _ops_mkfs(self, d) -> list:
        s = self.settings
        ops = [("cmd", ["wipefs", "-a", "-f", d.path], None),
               ("cmd", ["mkfs.vfat", "-F32", "-n", "ESP",
                        part_path(d.name, 1)], None)]
        idx = 2
        if s.swap:
            ops.append(("cmd", ["mkswap", "-L", "swap",
                                part_path(d.name, idx)], None))
            ops.append(("cmd", ["swapon", part_path(d.name, idx)], None))
            idx += 1
        ops.append(("cmd", ["mkfs.ext4", "-F", "-L", "photon",
                            part_path(d.name, idx)], None))
        return ops

    def _root_part(self, d) -> str:
        # ESP=1, swap=2 (если есть) → корень последний
        return part_path(d.name, 3 if self.settings.swap else 2)

    def _esp_part(self, d) -> str:
        return part_path(d.name, 1)

    def _swap_part(self, d):
        return part_path(d.name, 2) if self.settings.swap else None

    def _ops_mount(self, d) -> list:
        return [
            ("cmd", ["mkdir", "-p", TARGET], None),
            ("cmd", ["mount", "-o", "defaults,noatime",
                     self._root_part(d), TARGET], None),
            ("cmd", ["mkdir", "-p", f"{TARGET}/boot/efi"], None),
            ("cmd", ["mount", self._esp_part(d), f"{TARGET}/boot/efi"], None),
        ]

    def _ops_packages(self, pkgs: list) -> list:
        return [
            ("cmd", ["mkdir", "-p", f"{TARGET}/etc/xbps.d"], None),
            ("call", self._copy_xbps_conf),
            ("cmd", ["xbps-install", "-r", TARGET, "-Sy", "-R", self.repo,
                     *pkgs], None),
        ]

    def _copy_xbps_conf(self) -> None:
        """Репозитории live-сессии -> /target, чтобы xbps-install -r видел их."""
        os.makedirs(f"{TARGET}/etc/xbps.d", exist_ok=True)
        for src_dir in ("/usr/share/xbps.d", "/etc/xbps.d"):
            if not os.path.isdir(src_dir):
                continue
            for f in os.listdir(src_dir):
                if f.endswith(".conf") and "*-repository" in f:
                    shutil.copy2(os.path.join(src_dir, f),
                                 f"{TARGET}/etc/xbps.d/{f}")

    def _ops_fstab(self, d) -> list:
        def gen() -> None:
            uuids = {}
            for p in (self._esp_part(d), self._root_part(d),
                      self._swap_part(d)):
                if not p:
                    continue
                out = subprocess.run(["blkid", "-o", "export", p],
                                     capture_output=True, text=True,
                                     check=True).stdout
                for line in out.splitlines():
                    if line.startswith("UUID="):
                        uuids[p] = line.split("=", 1)[1].strip()
            fstab = ["# PhotonOS: /etc/fstab (сгенерирован установщиком)",
                     "tmpfs /tmp tmpfs defaults,nosuid 0 0", ""]
            fstab.append(
                f"UUID={uuids[self._root_part(d)]} / ext4 "
                "defaults,noatime 0 1")
            fstab.append(
                f"UUID={uuids[self._esp_part(d)]} /boot/efi vfat "
                "defaults,noatime 0 2")
            if self.settings.swap and self._swap_part(d) in uuids:
                fstab.append(
                    f"UUID={uuids[self._swap_part(d)]} none swap sw 0 0")
            content = "\n".join(fstab) + "\n"
            with open(f"{TARGET}/etc/fstab", "w", encoding="utf-8") as f:
                f.write(content)
            self.log("записан /etc/fstab:\n" + content)
        return [("call", gen)]

    def _ops_bind(self) -> list:
        return [
            ("cmd", ["mount", "-t", "proc", "proc", f"{TARGET}/proc"], None),
            ("cmd", ["mount", "--rbind", "/dev", f"{TARGET}/dev"], None),
            ("cmd", ["mount", "--make-rslave", f"{TARGET}/dev"], None),
            ("cmd", ["mount", "--rbind", "/sys", f"{TARGET}/sys"], None),
            ("cmd", ["mount", "--make-rslave", f"{TARGET}/sys"], None),
        ]

    def _ops_config(self) -> list:
        s = self.settings
        ops = []

        def hostname() -> None:
            with open(f"{TARGET}/etc/hostname", "w") as f:
                f.write(s.hostname + "\n")
            with open(f"{TARGET}/etc/hosts", "a") as f:
                f.write(f"127.0.1.1  {s.hostname}  {s.hostname}.localdomain\n")
        ops.append(("call", hostname))

        def locales() -> None:
            path = f"{TARGET}/etc/default/libc-locales"
            lines = []
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    lines = f.readlines()
            have = set()
            out = []
            for loc in LOCALES:
                have.add(loc.split()[0])
            for line in lines:
                name = line.split()[0] if line.split() else ""
                if line.startswith("#") and name in have:
                    out.append(line.lstrip("#"))
                else:
                    out.append(line)
            for loc in LOCALES:
                if not any(l.startswith(loc.split()[0]) for l in out if not l.startswith("#")):
                    out.append(loc + "\n")
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(out)
        ops.append(("call", locales))

        ops.append(("cmd", ["chroot", TARGET, "ln", "-sf",
                            f"/usr/share/zoneinfo/{s.tz}",
                            "/etc/localtime"], None))
        ops.append(("cmd", ["chroot", TARGET, "xbps-reconfigure", "-f",
                            "glibc-locales"], None))
        return ops

    def _ops_users(self) -> list:
        s = self.settings
        ops = [("cmd", ["chroot", TARGET, "useradd", "-m", "-s", "/bin/bash",
                        "-G", USER_GROUPS, s.username], None),
               ("cmd", ["chroot", TARGET, "chpasswd"],
                f"root:{s.password}\n{s.username}:{s.password}\n")]
        return ops

    def _ops_services(self, services: list) -> list:
        ops = []
        for svc in services:
            ops.append(("cmd", ["ln", "-sf", f"/etc/sv/{svc}",
                                f"{TARGET}/etc/runit/runsvdir/default/{svc}"],
                        None))
        return ops

    def _ops_branding(self) -> list:
        ops = [("call", self._copy_brand)]
        return ops

    def _copy_brand(self) -> None:
        # os-release, skel-дефолты и /etc/photon — с live-сессии в /target
        for src, dst in (("/usr/lib/os-release", f"{TARGET}/usr/lib/os-release"),):
            if os.path.exists(src):
                shutil.copy2(src, dst)
        if os.path.isdir("/etc/skel"):
            shutil.copytree("/etc/skel", f"{TARGET}/etc/skel",
                            dirs_exist_ok=True)
        if os.path.isdir("/etc/photon"):
            shutil.copytree("/etc/photon", f"{TARGET}/etc/photon",
                            dirs_exist_ok=True)

    def _ops_bootloader(self) -> list:
        return [
            ("cmd", ["chroot", TARGET, "grub-install", "--target=x86_64-efi",
                     "--efi-directory=/boot/efi", "--bootloader-id=PhotonOS",
                     "--recheck"], None),
            ("cmd", ["chroot", TARGET, "grub-mkconfig", "-o",
                     "/boot/grub/grub.cfg"], None),
        ]

    def _ops_initramfs(self) -> list:
        return [("cmd", ["chroot", TARGET, "xbps-reconfigure", "-fa",
                         "linux-lts"], None)]

    def _ops_umount(self, d) -> list:
        ops = [("cmd", ["swapoff", "-a"], None),
               ("cmd", ["umount", "-R", TARGET], None)]
        return ops

    # ── исполнение ──────────────────────────────────────────────────────
    def _do(self, op: tuple) -> None:
        kind = op[0]
        if kind == "cmd":
            _, argv, stdin = op
            shown = " ".join(argv)
            if stdin and ":" in stdin and "chpasswd" in shown:
                shown += "  <<< stdin (пароли скрыты)"
            self.log(f"$ {shown}")
            if stdin and not ("chpasswd" in shown):
                # скрипты вроде sfdisk важны для разбора ошибок; пароли — никогда
                self.log("   stdin: " + stdin.strip().replace("\n", " | "))
            if self.dry_run:
                return
            proc = subprocess.run(argv, input=stdin, text=True,
                                  capture_output=True)
            if proc.stdout:
                self._tail(proc.stdout)
            if proc.returncode != 0:
                self._tail(proc.stderr)
                raise BackendError(
                    f"команда завершилась с кодом {proc.returncode}: {shown}")
        elif kind == "file":
            _, path, content, mode = op
            self.log(f"запись {path}")
            if not self.dry_run:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                os.chmod(path, mode)
        elif kind == "call":
            self.log(f"* {getattr(op[1], '__name__', 'действие')}")
            if not self.dry_run:
                op[1]()

    @staticmethod
    def _tail(text: str, lines: int = 8) -> None:
        parts = [l for l in text.splitlines() if l.strip()]
        for l in parts[-lines:]:
            print(l)  # stdout уходит в журнал потока установщика
