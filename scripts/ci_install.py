#!/usr/bin/env python3
"""e2e-тест установки PhotonOS: live-ISO -> photon-installer --auto ->
загрузка установленной системы с диска.

Фаза 1: QEMU (BIOS или EFI/OVMF) с чистым виртуальным диском; в live-сессии
по serial пишется /tmp/photon-auto.conf и запускается
`sudo photon-installer --auto ...` с выводом в ttyS0. REBOOT=yes +
-no-reboot -> QEMU завершается сам.

Фаза 2: QEMU стартует снова, уже с диска; критерий - login-промпт getty на
ttyS0 (console=ttyS0 установщик прописывает в GRUB_CMDLINE_LINUX) и нечёрные
кадры через QMP.

    python3 scripts/ci_install.py --iso dist/...iso --mode bios --outdir out/install

result.json: 0 = PASS, 3 = FAIL.
"""
import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_boot import QMP, SerialWatch, find_ovmf, log, ppm_stats

AUTO_CONF = ("DISK=/dev/vda\nUSERNAME=user\nPASSWORD=photon123\n"
             "FULLNAME=Test User\nHOSTNAME=photon-e2e\nTZ=Europe/Moscow\n"
             "LOCALE=ru\nSWAP=no\nDE=lxqt\nMAIL=no\nREBOOT=yes\n")
# фаза 1: маркеры вывода auto-установщика в ttyS0
INSTALL_OK = re.compile("Установка завершена успешно".encode())
INSTALL_ERR = re.compile("(ОШИБКА:|AUTO-RC=[1-9])".encode())
# фаза 2: getty на ttyS0 установленной системы (hostname из AUTO_CONF)
LOGIN_PROMPT = re.compile("(?m)^photon-e2e login:".encode())


def connect_qmp(run: str, timeout: int = 60):
    for _ in range(timeout):
        try:
            return QMP(f"{run}/qmp.sock")
        except (OSError, RuntimeError):
            time.sleep(1)
    raise RuntimeError("QMP-сокет не подключился")


def shot(qmp, shots: str, tag: str, i: int, result: dict, best: dict,
         t0: float) -> None:
    base = os.path.join(shots, f"{tag}-{i:03d}")
    try:
        ppm = qmp.screendump_ppm(base)
    except Exception as exc:
        log(f"скриншот не удался: {exc}")
        return
    mean, bright = ppm_stats(ppm)
    path = ppm
    conv = shutil.which("convert") or shutil.which("magick")
    if conv:
        rc = subprocess.run([conv, ppm, base + ".png"], capture_output=True)
        if rc.returncode == 0 and os.path.getsize(base + ".png") > 0:
            os.unlink(ppm)
            path = base + ".png"
    result["shots"].append({"n": i, "t": int(time.time() - t0),
                            "file": os.path.basename(path),
                            "mean": round(mean, 4), "bright": round(bright, 4)})
    if mean + bright > best["mean"] + best["bright"]:
        best.update(mean=mean, bright=bright, path=path)


def start_qemu(qemu, iso, mode, disk_img, run, with_iso: bool, outdir: str):
    log_path = os.path.join(outdir, "qemu1.log" if with_iso else "qemu2.log")
    cmd = [
        qemu, "-machine", "q35", "-accel", "tcg,thread=multi", "-cpu", "max",
        "-m", "2048", "-smp", "2", "-display", "none", "-vga", "std",
        "-device", "virtio-rng-pci", "-no-reboot",
        "-drive", f"file={disk_img},if=virtio,format=qcow2",
        "-chardev", f"socket,id=ser0,path={run}/serial.sock,server=on,wait=off",
        "-serial", "chardev:ser0",
        "-qmp", f"unix:{run}/qmp.sock,server=on,wait=off",
        "-nic", "user,model=e1000",
    ]
    if with_iso:
        cmd += ["-cdrom", os.path.abspath(iso), "-boot", "d"]
    if mode == "efi":
        ovmf = find_ovmf()
        if not ovmf:
            raise RuntimeError("OVMF.fd не найден (apt install ovmf)")
        cmd += ["-bios", ovmf]
    log("QEMU: " + " ".join(cmd))
    qlog = open(log_path, "wb")
    proc = subprocess.Popen(cmd, stdout=qlog, stderr=qlog,
                            start_new_session=True)
    return proc, qlog


def stop_qemu(qmp, proc, qlog) -> None:
    try:
        qmp.quit()
    except Exception:
        pass
    time.sleep(2)
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
    qlog.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso", required=True)
    ap.add_argument("--mode", choices=("bios", "efi"), default="bios")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--disk-size", default="20G")
    ap.add_argument("--timeout-install", type=int, default=2700,
                    help="лимит фазы установки, сек (TCG медленный)")
    ap.add_argument("--timeout-boot", type=int, default=600,
                    help="лимит ожидания загрузки с диска, сек")
    args = ap.parse_args()

    for tool in ("qemu-system-x86_64", "qemu-img"):
        if not shutil.which(tool):
            log(f"ОШИБКА: {tool} не найден")
            return 2
    qemu = shutil.which("qemu-system-x86_64")

    os.makedirs(args.outdir, exist_ok=True)
    run = os.path.join(args.outdir, "run")
    os.makedirs(run, exist_ok=True)
    shots = os.path.join(args.outdir, "shots")
    os.makedirs(shots, exist_ok=True)
    disk_img = os.path.join(args.outdir, "disk.qcow2")

    result = {"mode": args.mode, "iso": os.path.basename(args.iso),
              "shots": []}
    best = {"mean": -1.0, "bright": -1.0, "path": None}
    t0 = time.time()

    # ---- фаза 1: live-сессия + автоустановка ---------------------------
    subprocess.run(["qemu-img", "create", "-f", "qcow2", disk_img,
                    args.disk_size], check=True, capture_output=True)
    proc, qlog = start_qemu(qemu, args.iso, args.mode, disk_img, run,
                            with_iso=True, outdir=args.outdir)
    watcher = SerialWatch(f"{run}/serial.sock",
                          os.path.join(args.outdir, "serial1.log"))
    if not watcher.connect():
        log("ОШИБКА: serial-сокет не подключился")
        proc.terminate()
        return 2
    watcher.start()
    qmp = connect_qmp(run)

    n_shots = 0
    marker_at = None
    while time.time() - t0 < 900 and marker_at is None:
        if proc.poll() is not None:
            break
        # diag_ok = lxqt-session в телеметрии photon-diag: сессия жива
        if watcher.diag_ok.is_set():
            marker_at = time.time() - t0
            break
        n_shots += 1
        shot(qmp, shots, "boot", n_shots, result, best, t0)
        time.sleep(4)

    result["marker_at_sec"] = round(marker_at, 1) if marker_at else None
    if marker_at is None:
        log("маркер загрузки live не пойман")
        result["verdict"] = "FAIL"
        result["why"] = "live marker timeout"
        stop_qemu(qmp, proc, qlog)
        _dump(result, args.outdir)
        return 3

    # дать сессии устаканиться, потом конфиг и установка (вывод - в ttyS0)
    time.sleep(45)
    log("запускаю автоустановку через serial")
    watcher.send("\nprintf %s " + shlex.quote(AUTO_CONF)
                 + " > /tmp/photon-auto.conf\n")
    time.sleep(1)
    watcher.send("\nsudo photon-installer --auto /tmp/photon-auto.conf"
                 " >/dev/ttyS0 2>&1\n")

    install_ok = install_err = False
    dead = False
    t1 = time.time()
    while time.time() - t1 < args.timeout_install:
        if proc.poll() is not None:
            dead = True                      # reboot при REBOOT=yes
            log(f"QEMU завершился сам, код {proc.returncode}")
            break
        txt = watcher.text()
        if INSTALL_ERR.search(txt):
            install_err = True
            break
        if INSTALL_OK.search(txt):
            install_ok = True
            break
        if time.time() - t1 > 120 and n_shots < 40:
            n_shots += 1
            shot(qmp, shots, "inst", n_shots, result, best, t0)
        time.sleep(5)

    if not (install_ok or install_err) and not dead:
        log("лимит ожидания установки")
    result["install_ok"] = bool(install_ok)
    result["install_err"] = bool(install_err)
    result["install_sec"] = round(time.time() - t1, 0)
    if not install_ok:
        result["verdict"] = "FAIL"
        result["why"] = ("установка не завершилась: "
                         + ("QEMU умер" if dead else
                            ("ошибка установщика" if install_err
                             else "таймаут")))
        if proc.poll() is None:
            stop_qemu(qmp, proc, qlog)
        _dump(result, args.outdir)
        return 3

    # дать дойти до reboot; с -no-reboot QEMU выйдет сам
    for _ in range(30):
        if proc.poll() is not None:
            dead = True
            break
        time.sleep(2)
    if proc.poll() is None:
        stop_qemu(qmp, proc, qlog)

    # ---- фаза 2: загрузка установленной системы с диска ----------------
    for f in ("serial.sock", "qmp.sock"):
        p = os.path.join(run, f)
        if os.path.exists(p):
            os.unlink(p)
    proc2, qlog2 = start_qemu(qemu, args.iso, args.mode, disk_img, run,
                              with_iso=False, outdir=args.outdir)
    watcher2 = SerialWatch(f"{run}/serial.sock",
                           os.path.join(args.outdir, "serial2.log"))
    watcher2.ok_re = LOGIN_PROMPT
    watcher2.end_re = None
    if not watcher2.connect():
        log("ОШИБКА: serial-сокет (фаза 2) не подключился")
        proc2.terminate()
        return 2
    watcher2.start()
    qmp2 = connect_qmp(run)

    boot_ok = False
    t2 = time.time()
    while time.time() - t2 < args.timeout_boot:
        if proc2.poll() is not None:
            log(f"QEMU (фаза 2) завершился, код {proc2.returncode}")
            break
        if watcher2.diag_ok.is_set():
            boot_ok = True
            break
        n_shots += 1
        shot(qmp2, shots, "disk", n_shots, result, best, t0)
        time.sleep(10)

    result["boot_ok"] = boot_ok
    result["login_prompt_sec"] = round(time.time() - t2, 0) if boot_ok else None
    result["best_shot"] = (os.path.basename(best["path"])
                           if best["path"] else None)
    result["best_mean"] = round(best["mean"], 4)
    result["best_bright"] = round(best["bright"], 4)
    pix_ok = best["mean"] > 0.03 and best["bright"] > 0.004
    result["pixel_ok"] = pix_ok
    ok = boot_ok and pix_ok
    result["verdict"] = "PASS" if ok else "FAIL"
    if not ok:
        result["why"] = f"boot_ok={boot_ok} pixel_ok={pix_ok}"
    stop_qemu(qmp2, proc2, qlog2)

    log(f"ВЕРДИКТ: {result['verdict']} — "
        + json.dumps(result, ensure_ascii=False)[:400])
    _dump(result, args.outdir)
    return 0 if result["verdict"] == "PASS" else 3


def _dump(result: dict, outdir: str) -> None:
    with open(os.path.join(outdir, "result.json"), "w") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    best = result.get("best_shot")
    if best:
        for s in result["shots"]:
            if s["file"] == best:
                src = os.path.join(outdir, "shots", best)
                if os.path.exists(src):
                    shutil.copyfile(src, os.path.join(outdir, "best.png"))
                break


if __name__ == "__main__":
    sys.exit(main())
