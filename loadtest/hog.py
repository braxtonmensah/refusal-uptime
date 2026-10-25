"""Hold memory until the host has about TARGET_MB available, then keep it until killed.

Reproduces the memory condition observed on the measured laptop (about 1 GB free) on a clean runner.
usage: python hog.py <target_free_mb> <status_file>
"""
import ctypes
import os
import sys
import time

TARGET = int(sys.argv[1]) * 1024 * 1024
STATUS = sys.argv[2]
CHUNK = 128 * 1024 * 1024


def available():
    if os.name == "nt":
        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MS()
        m.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return m.ullAvailPhys
    with open("/proc/meminfo") as fh:
        for line in fh:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    return 0


held = []
start = available()
while available() - CHUNK > TARGET:
    b = bytearray(CHUNK)
    for i in range(0, CHUNK, 4096):  # touch every page so it is resident, not just reserved
        b[i] = 1
    held.append(b)
with open(STATUS, "w") as fh:
    fh.write(f"start_avail_mb={start // 2**20} held_mb={len(held) * CHUNK // 2**20} avail_mb={available() // 2**20}\n")
while True:
    time.sleep(5)
