"""Опрос дисков через lsblk и план авто-разметки.

Функции не зависят от Qt — тестируются отдельно (см. scripts/installer_tests.py).
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field

MIB = 1024 * 1024
GIB = 1024 * MIB

LSBLK_ARGS = [
    "lsblk", "-Jb", "-o",
    "NAME,PATH,SIZE,TYPE,FSTYPE,MOUNTPOINT,LABEL,MODEL,VENDOR,SERIAL,ROTA,RM",
]


@dataclass
class PartInfo:
    name: str
    size: int
    fstype: str = ""
    mountpoint: str = ""
    label: str = ""


@dataclass
class DiskInfo:
    path: str
    name: str
    size: int
    model: str = ""
    vendor: str = ""
    serial: str = ""
    rota: bool = True
    removable: bool = False
    parts: list = field(default_factory=list)

    @property
    def size_h(self) -> str:
        return human_size(self.size)

    @property
    def has_data(self) -> bool:
        # «есть данные»: любая таблица разделов с разелами или файловая система
        return bool(self.parts) or self._top_fs

    def describe(self) -> str:
        bits = [self.path, self.size_h]
        if self.model:
            bits.append(self.model.strip())
        bits.append("SSD" if not self.rota else "HDD")
        if self.removable:
            bits.append("USB")
        return " · ".join(bits)


# файловая система прямо на диске (без разделов)
def _top_fs(disk_node: dict) -> str:
    return disk_node.get("fstype") or ""


def human_size(n: int) -> str:
    """Человекочитаемый размер: Б / МиБ / ГиБ / ТиБ."""
    n = int(n)
    for unit, factor in (("ТиБ", 1024 * GIB), ("ГиБ", GIB), ("МиБ", MIB)):
        if n >= factor:
            value = n / factor
            return f"{value:.0f} {unit}" if value >= 10 else f"{value:.1f} {unit}"
    return f"{n} Б"


def parse_lsblk_json(text: str) -> list:
    """Текст lsblk -J -> список DiskInfo (только type=disk)."""
    tree = json.loads(text)
    disks = []
    for node in tree.get("blockdevices", []):
        _walk(node, disks)
    return [d for d in disks if d.path]


def _walk(node: dict, out: list) -> None:
    if node.get("type") == "disk":
        parts = []
        for child in node.get("children") or []:
            if child.get("type") == "part":
                parts.append(PartInfo(
                    name=child.get("name", ""),
                    size=int(child.get("size") or 0),
                    fstype=child.get("fstype") or "",
                    mountpoint="".join(child.get("mountpoint") or "") or "",
                    label=child.get("label") or "",
                ))
        d = DiskInfo(
            path=node.get("path") or "",
            name=node.get("name") or "",
            size=int(node.get("size") or 0),
            model=(node.get("model") or "").strip(),
            vendor=(node.get("vendor") or "").strip(),
            serial=(node.get("serial") or "").strip(),
            rota=str(node.get("rota", "1")) == "1",
            removable=str(node.get("rm", "0")) == "1",
            parts=parts,
        )
        d._top_fs = _top_fs(node)  # noqa: SLF001 — внутренний признак
        out.append(d)
    for child in node.get("children") or []:
        _walk(child, out)


def list_disks(fake: bool = False) -> list:
    """Опрос системы; fake=True — встроенный пример (для разработки/тестов)."""
    if fake:
        return parse_lsblk_json(FAKE_LSBLK)
    proc = subprocess.run(LSBLK_ARGS, capture_output=True, text=True, check=True)
    return parse_lsblk_json(proc.stdout)


def auto_plan(disk_size: int, swap: bool, mode: str = "efi") -> list:
    """План авто-разметки: EFI - GPT с ESP 512 МиБ, BIOS - MBR без ESP;
    + swap 4 ГиБ + корень = остальное."""
    esp = 512 * MIB if mode == "efi" else 0
    swp = 4 * GIB if swap else 0
    root = disk_size - esp - swp
    if swap and root < 4 * GIB:      # диск мал — жертвуем swap
        swp, root = 0, disk_size - esp
    plan = [{"role": "esp", "size": esp, "fs": "vfat"}] if esp else []
    if swp:
        plan.append({"role": "swap", "size": swp, "fs": "swap"})
    plan.append({"role": "root", "size": root, "fs": "ext4"})
    return plan


FAKE_LSBLK = r"""
{
   "blockdevices": [
      {"name":"sda","path":"/dev/sda","size":256060514304,"type":"disk",
       "fstype":null,"mountpoint":null,"label":null,"model":"Samsung SSD 860","vendor":"ATA",
       "serial":"S4EWNX0N","rota":"0","rm":"0",
       "children":[
          {"name":"sda1","path":"/dev/sda1","size":536870912,"type":"part",
           "fstype":"vfat","mountpoint":"/boot/efi","label":null},
          {"name":"sda2","path":"/dev/sda2","size":255521800192,"type":"part",
           "fstype":"ext4","mountpoint":null,"label":"old-root"}
      ]},
      {"name":"sdb","path":"/dev/sdb","size":15502147584,"type":"disk",
       "fstype":null,"mountpoint":null,"label":null,"model":"DataTraveler 3.0","vendor":"Kingston",
       "serial":"60A44C42","rota":"0","rm":"1"},
      {"name":"nvme0n1","path":"/dev/nvme0n1","size":1000204886016,"type":"disk",
       "fstype":null,"mountpoint":null,"label":null,"model":"WDC PC SN730","vendor":null,
       "serial":"0019E1","rota":"0","rm":"0",
       "children":[
          {"name":"nvme0n1p1","path":"/dev/nvme0n1p1","size":104857600,"type":"part",
           "fstype":"ntfs","mountpoint":null,"label":"System"},
          {"name":"nvme0n1p2","path":"/dev/nvme0n1p2","size":999957393408,"type":"part",
           "fstype":"ntfs","mountpoint":null,"label":"Windows"}
      ]}
   ]
}
"""
