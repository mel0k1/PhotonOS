#!/usr/bin/env python3
"""CI smoke-test PhotonOS: загрузка live-ISO в QEMU (TCG, headless) со
скриншотами через QMP и serial-диагностикой.

Использование:
    python3 ci_boot.py --iso dist/PhotonOS-live-amd64-YYYYMMDD.iso \
        --mode bios --outdir out/bios
    python3 ci_boot.py --iso ... --mode efi --outdir out/efi   # OVMF

Что делает:
  1. Стартует qemu-system-x86_64: q35, TCG, 2G RAM, cdrom=ISO, serial через
     unix-chardev (в лог), QMP-сокет для команд.
  2. Ждёт маркер загрузки в serial (по умолчанию «Reached target Graphical
     Interface» от systemd на console=ttyS0).
  3. После маркера каждые 20с снимает скриншоты (screendump, формат png —
     с фолбэком на ppm+ImageMagick) и ждёт телеметрии photon-diag
     («PID lxqt-session» в serial) — признак живой LXQt-сессии.
  4. Проверяет, что скриншоты содержат изображение (средняя яркость и доля
     ярких пикселей), а не чёрный экран.
  5. Через serial-шелл (autologin anon) выполняет диагностические команды
     (systemctl --failed, pgrep панелей) — вывод в serial.log.
  6. Пишет result.json; код возврата 0 = PASS, 3 = FAIL.

QEMU: формат скриндампа png доступен с 7.1 (ubuntu-latest имеет 8.x);
для старых версий — фолбэк ppm + convert (ImageMagick).
"""
import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time

MARKER_DEFAULT = r"Reached target Graphical Interface"
DIAG_LXQT = re.compile(rb"(?m)^\d+\s+lxqt-session\b")
OVMF_CANDIDATES = (
    "/usr/share/ovmf/OVMF.fd",
    "/usr/share/OVMF/OVMF.fd",
    "/usr/share/ovmf/OVMF.ms.fd",
    "/usr/share/qemu/OVMF.fd",
)


def log(msg):
    print(f"[ci-boot {time.strftime('%H:%M:%S')}] {msg}", flush=True)


class QMP:
    """Минимальный QMP-клиент поверх unix-сокета."""

    def __init__(self, path, timeout=30):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        self.sock.connect(path)
        self.f = self.sock.makefile("rwb")
        greeting = self.f.readline()
        if not greeting.startswith(b"{"):
            raise RuntimeError(f"QMP: нет приветствия: {greeting[:80]!r}")
        self.f.write(b'{"execute":"qmp_capabilities"}\n')
        self.f.flush()
        self._recv_reply()

    def _recv_reply(self):
        """Читает строки, пропуская события, до return/error."""
        while True:
            line = self.f.readline()
            if not line:
                raise RuntimeError("QMP: сокет закрыт")
            msg = json.loads(line)
            if "return" in msg or "error" in msg:
                return msg
            # {"event": ...} — игнорируем

    def cmd(self, name, **args):
        payload = {"execute": name}
        if args:
            payload["arguments"] = args
        self.f.write(json.dumps(payload).encode() + b"\n")
        self.f.flush()
        msg = self._recv_reply()
        if "error" in msg:
            raise RuntimeError(f"QMP {name}: {msg['error']}")
        return msg.get("return")

    def screendump_ppm(self, base):
        """Скриншот в PPM (формат по умолчанию, есть в любом QEMU)."""
        ppm = base + ".ppm"
        self.cmd("screendump", filename=ppm)
        return ppm

    def quit(self):
        try:
            self.cmd("quit")
        except Exception:
            pass


def ppm_stats(path):
    """(средняя яркость 0..1, доля пикселей ярче 0.45) для PPM P6."""
    if path.endswith(".ppm"):
        with open(path, "rb") as fh:
            data = fh.read()
        # заголовок: P6, затем w h maxval (с комментариями)
        pos = 2
        vals = []
        while len(vals) < 3:
            while pos < len(data) and data[pos : pos + 1].isspace():
                pos += 1
            if data[pos : pos + 1] == b"#":
                pos = data.index(b"\n", pos) + 1
                continue
            start = pos
            while pos < len(data) and not data[pos : pos + 1].isspace():
                pos += 1
            vals.append(int(data[start:pos]))
        pos += 1  # одиночный whitespace после maxval
        w, h, maxv = vals
        px = data[pos:]
        stride = w * 3
        lum = []
        for y in range(0, h, 4):
            row = px[y * stride : (y + 1) * stride]
            for x in range(0, w, 4):
                o = x * 3
                if o + 2 < len(row):
                    r, g, b = row[o], row[o + 1], row[o + 2]
                    lum.append((r + g + b) / (3.0 * maxv))
        if not lum:
            return 0.0, 0.0
        mean = sum(lum) / len(lum)
        bright = sum(1 for v in lum if v > 0.45) / len(lum)
        return mean, bright
    # не-PPM (аварийный фолбэк): средняя через ImageMagick, ярких нет
    conv = shutil.which("convert") or shutil.which("magick")
    if not conv:
        return 0.0, 0.0
    try:
        out = subprocess.run(
            [conv, path, "-colorspace", "Gray", "-format", "%[fx:mean]", "info:"],
            capture_output=True, text=True, timeout=30,
        )
        return float(out.stdout.strip()), -1.0
    except Exception:
        return 0.0, 0.0


class SerialWatch(threading.Thread):
    """Читает serial-сокет QEMU, пишет в serial.log, следит за маркерами."""

    def __init__(self, path, logfile):
        super().__init__(daemon=True)
        self.path = path
        self.logfile = logfile
        self.sock = None
        self.buf = bytearray()          # весь поток (для финального regex)
        self.marker = threading.Event()
        self.marker_re = None
        self.diag_ok = threading.Event()
        self.diag_end = threading.Event()
        self.stopping = False

    def connect(self, timeout=60):
        deadline = time.time() + timeout
        while time.time() < deadline and not self.stopping:
            try:
                self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.sock.settimeout(1.0)
                self.sock.connect(self.path)
                return True
            except OSError:
                time.sleep(0.5)
        return False

    def send(self, text):
        if self.sock:
            try:
                self.sock.sendall(text.encode())
                return True
            except OSError:
                return False
        return False

    def run(self):
        fh = open(self.logfile, "ab", buffering=0)
        try:
            while not self.stopping:
                try:
                    chunk = self.sock.recv(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not chunk:
                    break
                fh.write(chunk)
                self.buf.extend(chunk)
                tail = bytes(self.buf[-8192:])
                if self.marker_re and not self.marker.is_set():
                    if self.marker_re.search(tail):
                        self.marker.set()
                if not self.diag_ok.is_set() and DIAG_LXQT.search(tail):
                    self.diag_ok.set()
                if b"CI-DIAG END" in tail:
                    self.diag_end.set()
        finally:
            fh.close()
            try:
                self.sock.close()
            except Exception:
                pass

    def text(self):
        return bytes(self.buf)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso", required=True)
    ap.add_argument("--mode", choices=("bios", "efi"), default="bios")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--timeout", type=int, default=1500,
                    help="лимит ожидания маркера загрузки, сек")
    ap.add_argument("--marker", default=MARKER_DEFAULT)
    ap.add_argument("--min-settle", type=int, default=90,
                    help="минимум сек после маркера до вердикта")
    ap.add_argument("--max-settle", type=int, default=300,
                    help="максимум сек ожидания телеметрии после маркера")
    ap.add_argument("--shots-every", type=int, default=20)
    ap.add_argument("--keep-vm", action="store_true",
                    help="не гасить QEMU (для отладки)")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    run = os.path.join(args.outdir, "run")
    os.makedirs(run, exist_ok=True)
    shots = os.path.join(args.outdir, "shots")
    os.makedirs(shots, exist_ok=True)

    qemu = shutil.which("qemu-system-x86_64")
    if not qemu:
        log("ОШИБКА: qemu-system-x86_64 не найден")
        return 2

    cmd = [
        qemu,
        "-machine", "q35", "-accel", "tcg,thread=multi", "-cpu", "max",
        "-m", "2048", "-smp", "2",
        "-display", "none", "-vga", "std",
        "-device", "virtio-rng-pci",
        "-no-reboot",
        "-cdrom", os.path.abspath(args.iso),
        "-boot", "d",
        "-chardev", f"socket,id=ser0,path={run}/serial.sock,server=on,wait=off",
        "-serial", "chardev:ser0",
        "-qmp", f"unix:{run}/qmp.sock,server=on,wait=off",
        "-nic", "user,model=e1000",
    ]
    if args.mode == "efi":
        ovmf = next((p for p in OVMF_CANDIDATES if os.path.exists(p)), None)
        if not ovmf:
            log("ОШИБКА: OVMF.fd не найден (apt install ovmf)")
            return 2
        cmd += ["-bios", ovmf]
        log(f"EFI firmware: {ovmf}")

    log("QEMU: " + " ".join(cmd))
    qemu_log = open(os.path.join(args.outdir, "qemu.log"), "wb")
    proc = subprocess.Popen(cmd, stdout=qemu_log, stderr=qemu_log,
                            start_new_session=True)

    watcher = SerialWatch(f"{run}/serial.sock",
                          os.path.join(args.outdir, "serial.log"))
    watcher.marker_re = re.compile(args.marker.encode())
    if not watcher.connect():
        log("ОШИБКА: serial-сокет не подключился")
        proc.terminate()
        return 2
    watcher.start()

    qmp = None
    for _ in range(60):
        try:
            qmp = QMP(f"{run}/qmp.sock")
            break
        except (OSError, RuntimeError):
            time.sleep(1)
    if qmp is None:
        log("ОШИБКА: QMP-сокет не подключился")
        proc.terminate()
        return 2

    result = {"mode": args.mode, "iso": os.path.basename(args.iso),
              "shots": []}
    shot_i = 0
    best = {"mean": -1.0, "bright": -1.0, "path": None}
    last_shot = [0.0]

    def elapsed():
        return time.time() - t0

    def ppm_to_png(base, ppm):
        """Конвертация для артефакта; возвращает итоговый файл."""
        conv = shutil.which("convert") or shutil.which("magick")
        if conv:
            png = base + ".png"
            rc = subprocess.run([conv, ppm, png], capture_output=True)
            if rc.returncode == 0 and os.path.exists(png) \
                    and os.path.getsize(png) > 0:
                os.unlink(ppm)
                return png
        return ppm

    def take_shot(tag):
        nonlocal shot_i, best
        shot_i += 1
        base = os.path.join(shots, f"{tag}-{shot_i:03d}")
        try:
            ppm = qmp.screendump_ppm(base)
        except Exception as exc:
            log(f"скриншот не удался: {exc}")
            return
        mean, bright = ppm_stats(ppm)
        path = ppm_to_png(base, ppm)
        result["shots"].append({"n": shot_i, "t": int(elapsed()),
                                "file": os.path.basename(path),
                                "mean": round(mean, 4),
                                "bright": round(bright, 4)})
        log(f"скриншот {os.path.basename(path)}: mean={mean:.3f} "
            f"bright={bright:.3f}")
        last_shot[0] = time.time()
        if mean + bright > best["mean"] + best["bright"]:
            best = {"mean": mean, "bright": bright, "path": path}

    t0 = time.time()

    try:
        # фаза 1: ждём маркер загрузки
        marker_at = None
        while elapsed() < args.timeout:
            if proc.poll() is not None:
                log(f"ОШИБКА: QEMU завершился сам, код {proc.returncode}")
                result["verdict"] = "FAIL"
                result["why"] = f"qemu exited rc={proc.returncode}"
                break
            if watcher.marker.is_set():
                marker_at = elapsed()
                break
            if time.time() - last_shot[0] >= args.shots_every:
                take_shot("boot")
            time.sleep(1)
        else:
            log("ОШИБКА: маркер загрузки не найден за timeout")
            result["verdict"] = "FAIL"
            result["why"] = "marker timeout"

        if marker_at is not None:
            result["marker_at_sec"] = round(marker_at, 1)
            log(f"маркер найден на {marker_at:.0f}-й секунде; "
                f"жду сессию LXQt (min {args.min_settle}с, "
                f"max {args.max_settle}с)")
            settle0 = time.time()
            while True:
                now = time.time() - settle0
                if now >= args.min_settle and watcher.diag_ok.is_set():
                    break
                if now >= args.max_settle:
                    log("телеметрия lxqt-session не поймана за max-settle")
                    break
                if proc.poll() is not None:
                    log(f"ОШИБКА: QEMU завершился сам, код {proc.returncode}")
                    break
                take_shot("desk")
                time.sleep(max(1, args.shots_every - 3))

            # фаза 3: serial-диагностика из live-шелла (autologin anon)
            log("отправляю CI-DIAG команды в serial")
            watcher.send(
                "\necho === CI-DIAG START ===; "
                "systemctl --no-pager --failed; "
                "pgrep -a -f 'lxqt-panel|pcmanfm-qt|picom|sddm'; "
                "echo === CI-DIAG END ===\n"
            )
            diag0 = time.time()
            while time.time() - diag0 < 60 and not watcher.diag_end.is_set():
                time.sleep(1)
            result["diag_answered"] = watcher.diag_end.is_set()

            # финальные кадры
            for _ in range(3):
                take_shot("final")
                time.sleep(4)

            result["diag_lxqt_session"] = bool(watcher.diag_ok.is_set())
            result["best_shot"] = (os.path.basename(best["path"])
                                   if best["path"] else None)
            result["best_mean"] = round(best["mean"], 4)
            result["best_bright"] = round(best["bright"], 4)
            pix_ok = best["mean"] > 0.03 and best["bright"] > 0.004
            result["pixel_ok"] = pix_ok
            ok = (watcher.diag_ok.is_set() and pix_ok
                  and best["path"] is not None)
            result["verdict"] = "PASS" if ok else "FAIL"
            if not ok:
                result["why"] = (
                    f"diag_lxqt={watcher.diag_ok.is_set()} "
                    f"pixel_ok={pix_ok} mean={best['mean']:.3f} "
                    f"bright={best['bright']:.4f}")

        if result.get("verdict") == "PASS":
            # лучший кадр — в корень outdir
            if best["path"]:
                shutil.copyfile(best["path"],
                                os.path.join(args.outdir, "best.png"))
        log(f"ВЕРДИКТ: {result.get('verdict')} — {json.dumps(result, ensure_ascii=False)[:400]}")
    finally:
        with open(os.path.join(args.outdir, "result.json"), "w") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
        if not args.keep_vm:
            qmp.quit()
            time.sleep(2)
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(10)
                except subprocess.TimeoutExpired:
                    proc.kill()
        qemu_log.close()

    return 0 if result.get("verdict") == "PASS" else 3


if __name__ == "__main__":
    sys.exit(main())
