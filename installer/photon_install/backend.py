"""Бэкенд установки PhotonOS: разметка -> копия live-squashfs -> GRUB -> fstab.

Чистый python без Qt: мастер вызывает Installer из рабочего потока, прогресс -
через колбэки. Шаг = список операций ("cmd"/"file"/"call"); в dry-run они
только логируются. Источник - squashfs live-образа: система 1:1 с live-ISO,
без сети. Пароли в журнал не попадают (stdin маскируется).
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field

from . import disk as _disk
from .settings import InstallSettings

TARGET = "/target"
LOG_PATH = "/tmp/photon-installer.log"
SRC_MOUNT = "/run/photon-src"


def boot_mode() -> str:
    """Режим загрузки live-сессии: efi (есть /sys/firmware/efi) или bios."""
    return "efi" if os.path.isdir("/sys/firmware/efi") else "bios"

# Где live-boot монтирует носитель, и как называется корневой squashfs.
SQUASHFS_CANDIDATES = [
    "/run/live/medium/live/filesystem.squashfs",
    "/lib/live/mount/medium/live/filesystem.squashfs",
    "/run/live/medium/*.squashfs",
    "/lib/live/mount/medium/*.squashfs",
]

# Каталоги-псевдофайловые системы: из squashfs не копируются, создаются пустыми.
PSEUDO_DIRS = [
    ("proc", 0o555), ("sys", 0o555), ("dev", 0o755), ("run", 0o755),
    ("tmp", 0o1777), ("media", 0o755), ("mnt", 0o755), ("live", 0o755),
]

# Файлы, которые установщик перезаписывает сам (из squashfs не нужны).
COPY_EXCLUDES = [
    "./proc", "./sys", "./dev", "./run", "./tmp", "./media", "./mnt",
    "./live", "./target",
    "./etc/fstab", "./etc/hostname", "./etc/hosts", "./etc/resolv.conf",
    "./etc/machine-id", "./var/lib/dbus/machine-id",
]

# Live-специфика установленной системе не нужна: live-механика
# (загрузка со squashfs) и утилита автотестов.
PURGE_PKGS = ["live-boot", "live-config", "live-tools", "user-setup", "xdotool"]

# Десктоп-стек для варианта «Без окружения»: копия squashfs всегда полная,
# поэтому DE снимается dpkg-очисткой уже в /target (офлайн, без сети).
DESKTOP_PKGS = [
    "sddm", "lxqt-core", "lxqt-panel", "lxqt-runner", "lxqt-session",
    "lxqt-archiver", "lxqt-powermanagement", "lxqt-policykit", "lxqt-sudo",
    "pcmanfm-qt", "qterminal", "lximage-qt", "openbox", "obconf-qt",
    "picom", "xdg-desktop-portal-lxqt", "xdg-desktop-portal-gtk",
    "papirus-icon-theme", "arc-theme", "qt6ct", "qt6-style-kvantum",
    "lxqt-themes", "network-manager-gnome",
    "xserver-xorg", "xserver-xorg-video-all", "xserver-xorg-input-libinput",
    "xserver-xorg-core",
]

USER_GROUPS = "sudo,audio,video,storage,input,cdrom,netdev"

LANGS = {"ru": "ru_RU.UTF-8", "en": "en_US.UTF-8"}
LOCALES = ["en_US.UTF-8 UTF-8", "ru_RU.UTF-8 UTF-8"]


class BackendError(RuntimeError):
    pass


def part_path(disk_name: str, index: int) -> str:
    """sda -> sda3; nvme0n1 -> nvme0n1p3; mmcblk0 -> mmcblk0p3."""
    sep = "p" if disk_name[-1].isdigit() else ""
    return f"/dev/{disk_name}{sep}{index}"


def find_squashfs() -> str | None:
    """Поиск корневого squashfs live-носителя."""
    for pattern in SQUASHFS_CANDIDATES:
        hits = sorted(glob.glob(pattern))
        for hit in hits:
            if os.path.isfile(hit) and os.path.getsize(hit) > 0:
                return hit
    return None


@dataclass
class Installer:
    settings: InstallSettings
    dry_run: bool = False
    log_path: str = LOG_PATH

    # колбэки: on_step(key, i, total), on_log(text), on_done()
    on_step: object = None
    on_log: object = None
    on_done: object = None

    steps: list = field(default_factory=list, init=False)
    _log_fh: object = None

    # EFI или BIOS — определяется по live-сессии один раз
    @property
    def mode(self) -> str:
        if not hasattr(self, "_mode"):
            self._mode = boot_mode()
        return self._mode

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

        steps = [
            ("part", "Разметка диска (sfdisk)", self._ops_partition(d)),
            ("mkfs", "Файловые системы", self._ops_mkfs(d)),
            ("mount", "Монтирование /target", self._ops_mount(d)),
            ("copy", "Копирование системы на диск", self._ops_copy()),
            ("chroot", "Подготовка chroot (/proc, /dev, /sys)", self._ops_bind()),
            ("clean", "Очистка live-компонентов", self._ops_clean()),
            ("fstab", "fstab и точки монтирования", self._ops_fstab(d)),
            ("config", "Настройка системы", self._ops_config()),
            ("users", "Пользователи и пароли", self._ops_users()),
            ("boot", f"Загрузчик GRUB ({self.mode.upper()})",
             self._ops_bootloader(d)),
            ("kernel", "Initramfs (update-initramfs)", self._ops_initramfs()),
            ("umount", "Размонтирование", self._ops_umount(d)),
        ]
        return steps

    def step_title(self, steps: list, key: str) -> str:
        for k, t, _ in steps:
            if k == key:
                return t
        return key

    # ── разделы ─────────────────────────────────────────────────────────
    def _root_part(self, d) -> str:
        # EFI: ESP=1, swap=2 (если есть) → корень последний;
        # BIOS (MBR): swap=1 → корень последний, ESP нет
        if self.mode == "efi":
            return part_path(d.name, 3 if self.settings.swap else 2)
        return part_path(d.name, 2 if self.settings.swap else 1)

    def _esp_part(self, d):
        return part_path(d.name, 1) if self.mode == "efi" else None

    def _swap_part(self, d):
        n = 2 if self.mode == "efi" else 1
        return part_path(d.name, n) if self.settings.swap else None

    # ── операции по шагам ───────────────────────────────────────────────
    def _ops_partition(self, d) -> list:
        s = self.settings
        if self.mode == "efi":
            lines = ["label: gpt",
                     "size=512MiB, type=U, bootable"]
            if s.swap:
                lines.append("size=4GiB, type=S")
            lines.append("type=L")
        else:
            # MBR: GRUB core.img живёт в post-MBR gap, ESP не нужен
            lines = ["label: dos"]
            if s.swap:
                lines += ["size=4GiB, type=S", "type=L, bootable"]
            else:
                lines.append("type=L, bootable")
        script = "\n".join(lines) + "\n"
        # wipefs ДО sfdisk: после разметки он обнулил бы подпись EFI PART свежего GPT
        return [("cmd", ["wipefs", "-a", "-f", d.path], None),
                ("cmd", ["sfdisk", "-f", d.path], script)]

    def _ops_mkfs(self, d) -> list:
        s = self.settings
        ops = []
        idx = 1
        if self.mode == "efi":
            ops.append(("cmd", ["mkfs.vfat", "-F32", "-n", "ESP",
                                part_path(d.name, 1)], None))
            idx = 2
        if s.swap:
            ops.append(("cmd", ["mkswap", "-L", "swap",
                                part_path(d.name, idx)], None))
            ops.append(("cmd", ["swapon", part_path(d.name, idx)], None))
            idx += 1
        ops.append(("cmd", ["mkfs.ext4", "-F", "-L", "photon",
                            part_path(d.name, idx)], None))
        return ops

    def _ops_mount(self, d) -> list:
        ops = [
            ("cmd", ["mkdir", "-p", TARGET], None),
            ("cmd", ["mount", "-o", "defaults,noatime",
                     self._root_part(d), TARGET], None),
        ]
        if self.mode == "efi":
            ops += [("cmd", ["mkdir", "-p", f"{TARGET}/boot/efi"], None),
                    ("cmd", ["mount", self._esp_part(d),
                             f"{TARGET}/boot/efi"], None)]
        return ops

    def _ops_copy(self) -> list:
        """Squashfs live-образа -> /target (tar-поток с исключениями)."""
        src_sq = find_squashfs()
        if src_sq is None and not self.dry_run:
            raise BackendError(
                "не найден filesystem.squashfs live-носителя "
                "(запускать из live-сессии PhotonOS/Debian)")
        shown = src_sq or "/run/live/medium/live/filesystem.squashfs"
        ops = [
            ("cmd", ["mkdir", "-p", SRC_MOUNT], None),
            ("cmd", ["mount", "-o", "loop,ro", shown, SRC_MOUNT], None),
            ("call", self._copy_rootfs),
            ("call", self._copy_kernel),
        ]
        return ops

    def _copy_kernel(self) -> None:
        """В squashfs /boot исключён: ядро и initrd берём с live-носителя,
        без них grub-mkconfig не найдёт ядро, а update-initramfs не соберёт
        initrd (фаза -u требует существующий файл)."""
        ver = subprocess.run(["uname", "-r"], capture_output=True,
                             text=True).stdout.strip()
        src_dir = os.path.dirname(find_squashfs()
                                  or "/run/live/medium/live/filesystem.squashfs")
        os.makedirs(f"{TARGET}/boot", exist_ok=True)
        for src, dst in (("vmlinuz", f"/boot/vmlinuz-{ver}"),
                         ("initrd", f"/boot/initrd.img-{ver}")):
            shutil.copyfile(os.path.join(src_dir, src), TARGET + dst)
        self.log(f"ядро {ver} скопировано в /target/boot")

    def _copy_rootfs(self) -> None:
        excludes = []
        for ex in COPY_EXCLUDES:
            excludes += ["--exclude", ex]
        p1 = subprocess.Popen(
            ["tar", "-C", SRC_MOUNT, "-cf", "-", *excludes, "."],
            stdout=subprocess.PIPE)
        p2 = subprocess.Popen(["tar", "-C", TARGET, "-xf", "-"],
                              stdin=p1.stdout)
        p1.stdout.close()
        p2.communicate()
        if p1.wait() != 0 or p2.returncode != 0:
            raise BackendError("копирование rootfs не удалось (tar)")
        # каталоги-точки монтирования, исключённые из копии
        for name, mode in PSEUDO_DIRS:
            path = os.path.join(TARGET, name)
            os.makedirs(path, exist_ok=True)
            os.chmod(path, mode)
        self.log(f"скопирована live-система из {SRC_MOUNT} -> {TARGET}")

    def _ops_bind(self) -> list:
        return [
            ("cmd", ["mount", "-t", "proc", "proc", f"{TARGET}/proc"], None),
            ("cmd", ["mount", "--rbind", "/dev", f"{TARGET}/dev"], None),
            ("cmd", ["mount", "--make-rslave", f"{TARGET}/dev"], None),
            ("cmd", ["mount", "--rbind", "/sys", f"{TARGET}/sys"], None),
            ("cmd", ["mount", "--make-rslave", f"{TARGET}/sys"], None),
        ]

    def _ops_clean(self) -> list:
        """Live-механика в установленной системе не нужна."""
        ops = [
            ("cmd", ["chroot", TARGET, "dpkg", "--purge", *PURGE_PKGS], None),
            ("call", self._clean_runtime),
        ]
        if self.settings.de == "none":
            ops.append(("call", self._purge_desktop))
        elif not self.settings.mail:
            ops.append(("call", self._purge_mail))
        return ops

    def _purge_desktop(self) -> None:
        """«Без окружения»: снимаем десктоп-стек (только установленные)."""
        todo = []
        for pkg in DESKTOP_PKGS:
            r = subprocess.run(["chroot", TARGET, "dpkg-query", "-W", "-f=${Status}",
                                pkg], capture_output=True, text=True)
            if r.returncode == 0 and "install ok installed" in r.stdout:
                todo.append(pkg)
        if not todo:
            self.log("десктоп-стек уже отсутствует")
            return
        self.log("снимается окружение: " + " ".join(todo))
        r = subprocess.run(["chroot", TARGET, "dpkg", "--purge", *todo],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise BackendError("dpkg --purge (окружение): "
                               + (r.stderr or r.stdout)[-400:])
        # дисплейный менеджер ушёл вместе с пакетом — сносим алиас на всякий случай
        dm = f"{TARGET}/etc/systemd/system/display-manager.service"
        if os.path.lexists(dm):
            os.unlink(dm)
        self.log("окружение снято, система остаётся консольной")

    def _purge_mail(self) -> None:
        """Почта снята в мастере - удаляем Claws Mail, если он в образе."""
        r = subprocess.run(["chroot", TARGET, "dpkg-query", "-W", "-f=${Status}",
                            "claws-mail"], capture_output=True, text=True)
        if r.returncode != 0 or "install ok installed" not in r.stdout:
            return
        r = subprocess.run(["chroot", TARGET, "dpkg", "--purge", "claws-mail"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise BackendError("dpkg --purge (claws-mail): "
                               + (r.stderr or r.stdout)[-400:])
        self.log("почтовый клиент claws-mail удалён (выбор мастера)")

    def _clean_runtime(self) -> None:
        # photon-diag — серийная диагностика live-сессии, на диске не нужна
        diag = f"{TARGET}/etc/systemd/system/multi-user.target.wants/photon-diag.service"
        if os.path.lexists(diag):
            os.unlink(diag)
            self.log("photon-diag.service отключён")
        # sudo без пароля — только для live-юзера, на диске не нужен
        live_sudo = f"{TARGET}/etc/sudoers.d/photon-live"
        if os.path.lexists(live_sudo):
            os.unlink(live_sudo)
            self.log("sudoers-правило live-сессии удалено")
        # machine-id перегенерируется при первой загрузке
        mid = f"{TARGET}/etc/machine-id"
        with open(mid, "w") as f:
            pass
        dbus_mid = f"{TARGET}/var/lib/dbus/machine-id"
        if os.path.lexists(dbus_mid):
            os.unlink(dbus_mid)
        os.symlink("/etc/machine-id", dbus_mid)
        self.log("machine-id очищен (перегенерация при первой загрузке)")

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
            if self.mode == "efi":
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

    def _ops_config(self) -> list:
        s = self.settings
        ops = []

        def hostname() -> None:
            with open(f"{TARGET}/etc/hostname", "w") as f:
                f.write(s.hostname + "\n")
            with open(f"{TARGET}/etc/hosts", "w") as f:
                f.write("127.0.0.1  localhost\n")
                f.write(f"127.0.1.1  {s.hostname}  {s.hostname}.localdomain\n")
                f.write("::1  localhost ip6-localhost ip6-loopback\n")
        ops.append(("call", hostname))

        def locales() -> None:
            lang = LANGS.get(s.lang, LANGS["en"])
            # /etc/locale.gen: обе локали раскомментированы
            path = f"{TARGET}/etc/locale.gen"
            lines = []
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    lines = f.readlines()
            out = []
            for line in lines:
                stripped = line.lstrip("#").strip()
                if stripped and any(stripped.startswith(l.split()[0])
                                    for l in LOCALES):
                    out.append(stripped + "\n")
                else:
                    out.append(line)
            have = {l.lstrip("#").split()[0] for l in out if l.split()}
            for loc in LOCALES:
                if loc.split()[0] not in have:
                    out.append(loc + "\n")
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(out)
            with open(f"{TARGET}/etc/default/locale", "w") as f:
                f.write(f"LANG={lang}\n")
            with open(f"{TARGET}/etc/environment", "w") as f:
                f.write(f"LANG={lang}\n")
            self.log(f"локаль системы: {lang}")
        ops.append(("call", locales))
        ops.append(("cmd", ["chroot", TARGET, "locale-gen"], None))

        def timezone() -> None:
            with open(f"{TARGET}/etc/timezone", "w") as f:
                f.write(s.tz + "\n")
        ops.append(("call", timezone))
        if s.tz:
            ops.append(("cmd", ["chroot", TARGET, "ln", "-sf",
                                f"/usr/share/zoneinfo/{s.tz}",
                                "/etc/localtime"], None))

        def keyboard() -> None:
            variant = f"\nXKBVARIANT={s.variant}" if s.variant else ""
            content = (f"# PhotonOS: /etc/default/keyboard"
                       f" (сгенерирован установщиком)\n"
                       f"XKBMODEL=pc105\nXKBLAYOUT={s.layout}{variant}\n")
            with open(f"{TARGET}/etc/default/keyboard", "w") as f:
                f.write(content)
            self.log(f"раскладка: {s.layout} {s.variant or ''}".rstrip())
        ops.append(("call", keyboard))
        return ops

    def _ops_users(self) -> list:
        s = self.settings
        ops = [("call", self._ensure_groups),
               ("cmd", ["chroot", TARGET, "useradd", "-m", "-s", "/bin/bash",
                        "-G", USER_GROUPS, s.username], None),
               ("cmd", ["chroot", TARGET, "chpasswd"],
                f"root:{s.password}\n{s.username}:{s.password}\n")]
        return ops

    def _ensure_groups(self) -> None:
        """Минимальная база Debian (variant=apt) не создаёт часть групп
        (sudo, audio, video, storage, cdrom) — useradd -G на отсутствующей
        группе падает с кодом 6. Создаём отсутствующие."""
        missing = []
        for g in USER_GROUPS.split(","):
            r = subprocess.run(["chroot", TARGET, "getent", "group", g],
                               capture_output=True, text=True)
            if r.returncode != 0 or not r.stdout.strip():
                missing.append(g)
        if not missing:
            self.log("все группы пользователя на месте")
            return
        self.log("создаются группы: " + " ".join(missing))
        for g in missing:
            subprocess.run(["chroot", TARGET, "groupadd", "-f", g],
                           check=True)

    def _grub_serial(self) -> None:
        """Серийная консоль в установленной системе: отладка на железе и CI;
        systemd-getty-generator сам поднимет getty на ttyS0."""
        path = f"{TARGET}/etc/default/grub"
        value = 'GRUB_CMDLINE_LINUX="console=tty0 console=ttyS0,115200"'
        lines = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                lines = f.readlines()
        out, done = [], False
        for line in lines:
            if line.startswith("GRUB_CMDLINE_LINUX="):
                out.append(value + "\n")
                done = True
            else:
                out.append(line)
        if not done:
            out.append(value + "\n")
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(out)

    def _ops_bootloader(self, d=None) -> list:
        if self.mode == "efi":
            install = ("cmd", ["chroot", TARGET, "grub-install",
                               "--target=x86_64-efi",
                               "--efi-directory=/boot/efi",
                               "--bootloader-id=PhotonOS", "--recheck"], None)
            tail = [("call", self._efi_fallback)]
        else:
            # BIOS: модули i386-pc (grub-pc-bin) уже в образе, ставим в MBR
            install = ("cmd", ["chroot", TARGET, "grub-install",
                               "--target=i386-pc", self.settings.disk], None)
            tail = []
        return [install,
                ("call", self._grub_serial),
                ("cmd", ["chroot", TARGET, "grub-mkconfig", "-o",
                         "/boot/grub/grub.cfg"], None),
                *tail]

    def _efi_fallback(self) -> None:
        """Страховка: копия grubx64.efi по пути EFI/boot/bootx64.efi —
        её находит fallback-скан прошивки, если запись NVRAM потерялась."""
        src = f"{TARGET}/boot/efi/EFI/PhotonOS/grubx64.efi"
        dst_dir = f"{TARGET}/boot/efi/EFI/boot"
        dst = f"{dst_dir}/bootx64.efi"
        if os.path.isfile(src):
            os.makedirs(dst_dir, exist_ok=True)
            with open(src, "rb") as a, open(dst, "wb") as b:
                b.write(a.read())
            self.log("fallback: EFI/boot/bootx64.efi записан")
        else:
            self.log("fallback: grubx64.efi не найден (некритично)")

    def _ops_initramfs(self) -> list:
        def gen() -> None:
            # после purge live-пакетов триггер мог и удалить initrd — тогда -c
            r = subprocess.run(["chroot", TARGET, "update-initramfs",
                                "-u", "-k", "all"], capture_output=True,
                               text=True)
            if r.returncode != 0:
                self.log("update-initramfs -u не отработал, пробую -c")
                r = subprocess.run(["chroot", TARGET, "update-initramfs",
                                    "-c", "-k", "all"], capture_output=True,
                                   text=True)
            if r.returncode != 0:
                raise BackendError("update-initramfs завершился с ошибкой: "
                                   + (r.stderr or r.stdout)[-400:])
            self.log("initramfs пересобран (без live-хуков)")
        return [("call", gen)]

    def _ops_umount(self, d) -> list:
        return [("cmd", ["swapoff", "-a"], None),
                ("cmd", ["umount", "-R", TARGET], None),
                ("cmd", ["umount", SRC_MOUNT], None),
                ("cmd", ["rmdir", SRC_MOUNT], None)]

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
