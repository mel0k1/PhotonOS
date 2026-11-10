#!/usr/bin/env python3
"""Быстрая EFI-проверка live-сессии под OVMF (без полной установки).

Грузит live-ISO в QEMU/OVMF и на serial-автологине (anon) проверяет цепочку,
которую использует установщик в EFI-режиме:
  A. efibootmgr - EFI-переменные доступны (нужно для grub-install EFI);
  B. GPT+ESP на чистом virtio-диске (sfdisk+mkfs.vfat+mount);
  C. grub-install --target=x86_64-efi --no-nvram на этот раздел.
Полный e2e установки - scripts/ci_install.py; этот скрипт - отладка за ~3 мин.

    python3 scripts/efi_sanity.py --iso dist/....iso
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_boot import SerialWatch, find_ovmf, log

PROMPT = re.compile(r"anon@[a-z0-9-]+:~\$".encode())


def wait_prompt(watcher, t0, limit=480):
    while time.time() - t0 < limit:
        if PROMPT.search(watcher.text()):
            return True
        time.sleep(2)
    return False


def run_cmd(watcher, cmd, tag, t0, limit=150):
    """Одна строка: cmd; echo PX<tag>:$? - без очереди из нескольких send.

    Несколько send подряд readline смешивает (bracketed paste), одна строка
    с маркером в конце выполняется детерминированно.
    """
    marker = f"PX{tag}"
    watcher.send(cmd + f"; echo {marker}:$?\n")
    pat = re.compile((marker + r":(\d+)").encode())
    deadline = time.time() + limit
    while time.time() < deadline:
        m = pat.search(watcher.text())
        if m:
            return int(m.group(1))
        time.sleep(2)
    return -1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso", required=True)
    ap.add_argument("--outdir", default="/tmp/efi-sanity")
    args = ap.parse_args()
    out = args.outdir
    os.makedirs(out, exist_ok=True)
    blank = f"{out}/blank.qcow2"

    qemu = shutil.which("qemu-system-x86_64")
    if not qemu:
        log("qemu-system-x86_64 не найден")
        return 2
    ovmf = find_ovmf()
    if not ovmf:
        log("OVMF.fd не найден (apt install ovmf или PHOTON_OVMF=путь)")
        return 2
    subprocess.run(["qemu-img", "create", "-f", "qcow2", blank, "2G"],
                   check=True, capture_output=True)
    cmd = [
        qemu, "-machine", "q35", "-accel", "tcg,thread=multi", "-cpu", "max",
        "-m", "2048", "-smp", "2", "-display", "none", "-vga", "std",
        "-no-reboot", "-nic", "user,model=e1000",
        "-cdrom", os.path.abspath(args.iso), "-boot", "d",
        "-drive", f"file={blank},if=virtio,format=qcow2",
        "-chardev", f"socket,id=ser0,path={out}/serial.sock,server=on,wait=off",
        "-serial", "chardev:ser0",
        "-qmp", f"unix:{out}/qmp.sock,server=on,wait=off",
        "-bios", ovmf,
    ]
    qlog = open(f"{out}/qemu.log", "wb")
    proc = subprocess.Popen(cmd, stdout=qlog, stderr=qlog,
                            start_new_session=True)
    watcher = SerialWatch(f"{out}/serial.sock", f"{out}/serial.log")
    watcher.end_re = None
    if not watcher.connect():
        log("serial-сокет не подключился")
        proc.terminate()
        return 2
    watcher.start()
    t0 = time.time()
    log("жду автологин на ttyS0 ...")
    if not wait_prompt(watcher, t0):
        log("промпт не пойман")
        proc.terminate()
        return 3
    log(f"промпт за {time.time()-t0:.0f}с")

    # A: efibootmgr (то же, что зовёт grub-install без --no-nvram)
    rcA = run_cmd(watcher,
                  "sudo timeout 30 efibootmgr >/tmp/eb.log 2>&1; "
                  "head -6 /tmp/eb.log",
                  "EB", t0, limit=90)
    log(f"A) efibootmgr rc={rcA} (124 = подвис)")

    # B: разметка + grub-install --no-nvram на реальном разделе
    # (единственный virtio-диск в ВМ - /dev/vda)
    part = ("printf 'label: gpt\\ntype=uefi, size=64MiB\\n' | "
            "sudo sfdisk /dev/vda >/dev/null 2>&1")
    rcB0 = run_cmd(watcher, part, "FD", t0)
    log(f"B0) sfdisk rc={rcB0}")
    mkfs = ("sudo mkfs.vfat -n TESTESP /dev/vda1 >/dev/null 2>&1; "
            "sudo mkdir -p /mnt/t; sudo mount /dev/vda1 /mnt/t")
    rcB1 = run_cmd(watcher, mkfs, "MK", t0)
    log(f"B1) mkfs+mount rc={rcB1}")
    gi = ("sudo grub-install --target=x86_64-efi --efi-directory=/mnt/t "
          "--boot-directory=/mnt/t --bootloader-id=photon-test --no-nvram "
          ">/tmp/gi.log 2>&1")
    rcB2 = run_cmd(watcher, gi, "GI", t0, limit=330)
    log(f"B2) grub-install --no-nvram rc={rcB2}")

    # C: результат
    rcC = run_cmd(watcher,
                  "ls /mnt/t/EFI/photon-test/ /mnt/t/grub/ 2>&1 | head -6; "
                  "tail -2 /tmp/gi.log",
                  "LS", t0, limit=60)

    proc.terminate()
    txt = watcher.text().decode(errors="replace")
    lines = [l for l in txt.splitlines()
             if re.search(r"PX\w+:\d+", l) or "grubx64" in l
             or "Boot" in l or "grub-install" in l]
    print("--- релевантные строки serial:")
    for l in lines[-25:]:
        print("   ", l.strip()[:130])

    ok = rcB2 == 0 and rcB0 == 0 and rcB1 == 0
    log("ИТОГ: " + ("PASS" if ok else f"FAIL (B0={rcB0} B1={rcB1} B2={rcB2})")
        + f" [A={rcA} efibootmgr]")
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())
