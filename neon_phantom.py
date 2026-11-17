#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEON//PHANTOM v1.0 - Advanced Fake Hacker Terminal Simulator
=============================================================
ENTERTAINMENT ONLY. Everything on screen is a visual simulation.

  * No network access of any kind (no sockets, no HTTP, nothing).
  * No Wi-Fi / IP scanning, no camera, microphone, GPS or location access.
  * No file-system scanning, no password collection.
  * All IPs, GPS coordinates, CPU/RAM/network numbers are random fiction.
    Fake IPs are drawn from documentation / private ranges only
    (192.0.2.x, 198.51.100.x, 203.0.113.x, 10.x, 172.16.x, 192.168.x).

The only file it ever touches is its own tiny settings file:
    ~/.neon_phantom.json   (username + sound + speed)

Python 3.6+ standard library only. Works in Android Termux (no root).
"""

import atexit
import colorsys
import functools
import hashlib
import json
import math
import os
import random
import shutil
import sys
import textwrap
import time

try:
    import readline  # noqa: F401  (command history in the console, optional)
except Exception:
    pass

VERSION = "1.0"
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".neon_phantom.json")

# ----------------------------------------------------------------------------
# Colors / terminal helpers
# ----------------------------------------------------------------------------
RST = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
HIDE = "\033[?25l"
SHOW = "\033[?25h"


def rgb(r, g, b):
    return "\033[38;2;%d;%d;%dm" % (r, g, b)


def bg(r, g, b):
    return "\033[48;2;%d;%d;%dm" % (r, g, b)


def hsv(h, s=1.0, v=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return rgb(int(r * 255), int(g * 255), int(b * 255))


GREEN = rgb(0, 255, 80)
RED = rgb(255, 40, 60)
BLUE = rgb(60, 130, 255)
PURPLE = rgb(185, 80, 255)
CYAN = rgb(0, 240, 255)
YELLOW = rgb(255, 220, 0)
WHITE = rgb(240, 240, 240)
GRAY = rgb(110, 115, 125)
ORANGE = rgb(255, 140, 0)
PINK = rgb(255, 60, 200)
PALETTE = [GREEN, CYAN, BLUE, PURPLE, PINK, RED]
GRADS = [(0.50, 0.92), (0.25, 0.55), (0.00, 0.35), (0.78, 1.05)]


class State(object):
    username = "GHOST"
    sound = True
    speed = 1.0          # multiplier for waiting time (lower = faster)
    last_cipher = None   # hex string
    last_key = None      # hex string
    last_plain = None
    ops = 0
    started = time.time()
    first_run = True
    length = 2.5         # operation length multiplier


S = State()


def w(s=""):
    sys.stdout.write(s)


def flush():
    try:
        sys.stdout.flush()
    except Exception:
        pass


def pr(s=""):
    sys.stdout.write(s + "\n")


def nap(t):
    """Sleep scaled by the user's speed setting."""
    if t > 0:
        flush()
        time.sleep(t * S.speed)


def width():
    cols = shutil.get_terminal_size((50, 24)).columns
    return max(30, min(cols, 80))


def term_size():
    sz = shutil.get_terminal_size((50, 24))
    return max(30, sz.columns), max(12, sz.lines)


def clear():
    w("\033[2J\033[H")
    flush()


def pause(msg="[ Press Enter to continue ]"):
    try:
        input("\n" + GRAY + msg + RST + " ")
    except EOFError:
        pass


def beep(kind="tick"):
    """Optional sound: terminal bell. In Termux it may vibrate or ring
    depending on the Termux bell setting."""
    if not S.sound:
        return
    patterns = {
        "tick": [0.0],
        "ok": [0.10, 0.0],
        "alert": [0.12, 0.12, 0.12, 0.0],
        "scan": [0.0],
        "done": [0.08, 0.08, 0.0],
    }
    for gap in patterns.get(kind, [0.0]):
        w("\a")
        flush()
        if gap:
            time.sleep(gap)


def sim(fn):
    """Decorator: hides cursor during a simulation and always restores it."""
    @functools.wraps(fn)
    def wrapper(*a, **k):
        S.ops += 1
        w(HIDE)
        try:
            return fn(*a, **k)
        finally:
            w(SHOW + RST)
            flush()
    return wrapper


@atexit.register
def _restore_terminal():
    try:
        w(SHOW + RST)
        flush()
    except Exception:
        pass


# ----------------------------------------------------------------------------
# Fake data generators (all fictional)
# ----------------------------------------------------------------------------
def hx(n):
    return "".join(random.choice("0123456789abcdef") for _ in range(n))


def fake_ip():
    r = random.randint(0, 5)
    if r == 0:
        return "192.0.2.%d" % random.randint(1, 254)
    if r == 1:
        return "198.51.100.%d" % random.randint(1, 254)
    if r == 2:
        return "203.0.113.%d" % random.randint(1, 254)
    if r == 3:
        return "10.%d.%d.%d" % (random.randint(0, 255), random.randint(0, 255), random.randint(1, 254))
    if r == 4:
        return "172.%d.%d.%d" % (random.randint(16, 31), random.randint(0, 255), random.randint(1, 254))
    return "192.168.%d.%d" % (random.randint(0, 255), random.randint(1, 254))


def fake_mac():
    return ":".join(hx(2) for _ in range(6))


def fake_host():
    return "%s-%02d.corp.local" % (
        random.choice(["node", "gate", "core", "vault", "relay", "edge", "proxy", "db", "mail", "cam", "hub"]),
        random.randint(1, 99))


def fake_password():
    return "%s%s%d%s" % (
        random.choice(["Ghost", "Phantom", "Neon", "Cipher", "Shadow", "Vortex", "Zero", "Specter", "Nova", "Rogue"]),
        random.choice("_@#-"),
        random.randint(10, 9999),
        random.choice("!$%*"))


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def human_size(mb):
    if mb >= 1024:
        return "%.2f GB" % (mb / 1024.0)
    return "%.1f MB" % mb


# ----------------------------------------------------------------------------
# Drawing helpers
# ----------------------------------------------------------------------------
def tag(t):
    colors = {"+": GREEN, "*": CYAN, "!": RED, "-": GRAY, "?": YELLOW, "#": PURPLE}
    return "%s[%s%s%s%s]%s" % (GRAY, colors.get(t, GREEN), t, RST, GRAY, RST)


def log(msg, t="+", color=GREEN, delay=0.0):
    pr("%s %s%s%s" % (tag(t), color, msg, RST))
    nap(delay)


def typewrite(text, color=GREEN, delay=0.012, newline=True):
    w(color)
    for ch in text:
        w(ch)
        flush()
        time.sleep(delay * S.speed * random.uniform(0.4, 1.6))
    w(RST)
    if newline:
        w("\n")
    flush()


def section(title, color=CYAN):
    W = width()
    pr()
    pr("%s┌%s┐%s" % (color, "─" * (W - 2), RST))
    pr("%s│%s%s%s%s%s│%s" % (color, RST, BOLD, WHITE, title.center(W - 2), color, RST))
    pr("%s└%s┘%s" % (color, "─" * (W - 2), RST))


def rainbow(text, offset=0.0, step=0.04):
    out = []
    for i, ch in enumerate(text):
        out.append(hsv(offset + i * step) + ch)
    return "".join(out) + RST


def gradient_line(ch="═", length=None, offset=0.0):
    length = length or width()
    return "".join(hsv(offset + i / float(length)) + ch for i in range(length)) + RST


def bar_str(pct, bw, grad):
    filled = int(bw * pct / 100.0)
    out = []
    for i in range(bw):
        if i < filled:
            out.append(hsv(grad[0] + (grad[1] - grad[0]) * i / max(1, bw - 1)) + CUR_BAR[0])
        else:
            out.append(GRAY + CUR_BAR[1])
    return "".join(out) + RST


def mbar(pct, bw):
    """Small level bar: green -> yellow -> red."""
    filled = int(bw * pct / 100.0)
    col = GREEN if pct < 55 else (YELLOW if pct < 80 else RED)
    return col + "█" * filled + GRAY + "░" * (bw - filled) + RST


def progress(label, total=1.5, grad=None):
    """Animated 0% -> 100% colorful progress bar."""
    grad = grad or random.choice(GRADS)
    W = width()
    label = label[:max(6, W // 2)]
    bw = max(8, W - len(label) - 9)
    steps = max(8, int(total / 0.04))
    last = 0
    for i in range(steps + 1):
        if i == steps:
            pct = 100
        else:
            pct = clamp(int(i * 100.0 / steps + random.uniform(-2, 2)), last, 99)
        last = pct
        w("\r%s%s%s %s %s%3d%%%s\033[K" % (CYAN, label, RST, bar_str(pct, bw, grad), WHITE, pct, RST))
        flush()
        nap(total / steps * random.uniform(0.5, 1.5))
    w("\n")
    beep("tick")


GLYPH = "0123456789ABCDEFabcdef@#$%&*+=<>?/\\|"


def reveal(final, color=GREEN, prefix="", rounds=14, delay=0.02):
    """Scrambled characters resolve left-to-right into the final text."""
    n = len(final)
    for r in range(rounds + 1):
        k = int(n * r / float(rounds))
        scr = "".join(random.choice(GLYPH) for _ in range(n - k))
        w("\r%s%s%s%s%s%s%s\033[K" % (prefix, color, final[:k], DIM, random.choice(PALETTE), scr, RST))
        flush()
        time.sleep(delay * S.speed)
    w("\r%s%s%s%s\033[K\n" % (prefix, color, final, RST))
    flush()


class Live(object):
    """Redraw a block of lines in place."""

    def __init__(self):
        self.n = 0

    def draw(self, lines):
        if self.n:
            w("\033[%dA" % self.n)
        for ln in lines:
            w("\r" + ln + "\033[K\n")
        flush()
        self.n = len(lines)


# ----------------------------------------------------------------------------
# Logo / boot
# ----------------------------------------------------------------------------
LOGO_NEON = [
    r" _  _ ___ ___  _  _ ",
    r"| \| | __/ _ \| \| |",
    r"| .` | _| (_) | .` |",
    r"|_|\_|___\___/|_|\_|",
]
LOGO_PHANTOM = [
    r" ___ _  _   _   _  _ _____ ___  __  __ ",
    r"| _ \ || | /_\ | \| |_   _/ _ \|  \/  |",
    r"|  _/ __ |/ _ \| .` | | || (_) | |\/| |",
    r"|_| |_||_/_/ \_\_|\_| |_| \___/|_|  |_|",
]


def show_logo(animated=True):
    W = width()
    pr()
    if W >= 40:
        lines = [l.center(W) for l in LOGO_NEON] + [("//").center(W)] + [l.center(W) for l in LOGO_PHANTOM]
        for i, ln in enumerate(lines):
            pr(rainbow(ln, offset=i * 0.07, step=0.012))
            if animated:
                nap(0.05)
    else:
        pr(rainbow("NEON//PHANTOM".center(W), 0.0, 0.07))
    pr(gradient_line("═", W))
    sub = "v%s  |  SECURE TERMINAL" % VERSION
    pr(CYAN + sub.center(W) + RST)
    pr(gradient_line("═", W, 0.5))


def boot():
    clear()
    w(HIDE)
    try:
        show_logo(True)
        pr()
        mods = ["core.render", "matrix.engine", "net.core", "crypto.core", "geo.core", "audio.bell", "ui.rgb"]
        for m in mods:
            log("loading module %-14s" % m, "*", CYAN)
            nap(0.06)
        progress("INITIALIZING", 1.6)
        log("operator : %s" % S.username, "#", PURPLE)
        nap(0.4)
    finally:
        w(SHOW + RST)


# ----------------------------------------------------------------------------
# 1. Matrix rain
# ----------------------------------------------------------------------------
@sim
def matrix_rain(duration=15):
    W, H = term_size()
    W = min(W, 120)
    chars = "01ABCDEFabcdef0123456789@#$%&*+=<>?/\\|;:"
    base_colors = [(0, 255, 80)] * 7 + [(0, 220, 255), (185, 80, 255), (255, 60, 200)]

    def scale(c, f):
        return rgb(int(c[0] * f), int(c[1] * f), int(c[2] * f))

    cols = []
    for _ in range(W):
        base = random.choice(base_colors)
        cols.append({
            "y": random.randint(-H, 0),
            "len": random.randint(5, max(6, H // 2)),
            "p": random.uniform(0.45, 1.0),
            "c": base,
        })
    clear()
    end = time.time() + duration
    while time.time() < end:
        buf = []
        for x, c in enumerate(cols):
            if random.random() > c["p"]:
                continue
            c["y"] += 1
            y, ln, base = c["y"], c["len"], c["c"]

            def put(row, color, ch):
                if 1 <= row <= H - 1:
                    buf.append("\033[%d;%dH%s%s" % (row, x + 1, color, ch))

            put(y, "\033[1m" + rgb(235, 255, 240), random.choice(chars))
            put(y - 1, scale(base, 1.0), random.choice(chars))
            put(y - 4, scale(base, 0.6), random.choice(chars))
            put(y - ln // 2, scale(base, 0.3), random.choice(chars))
            put(y - ln, RST, " ")
            if y - ln > H:
                c["y"] = random.randint(-H // 2, 0)
                c["len"] = random.randint(5, max(6, H // 2))
                c["p"] = random.uniform(0.45, 1.0)
                c["c"] = random.choice(base_colors)
        w("".join(buf) + RST)
        flush()
        time.sleep(0.05 * S.speed)
    clear()


# ----------------------------------------------------------------------------
# 2. IP scanner (fictional hosts only)
# ----------------------------------------------------------------------------
@sim
def ip_scanner(count=None):
    section("IP ADDRESS SCANNER", CYAN)
    W = width()
    rng = random.choice(["192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "10.%d.0.0/16" % random.randint(0, 255)])
    log("target range : %s" % rng, "*", CYAN)
    log("mode         : stealth-sweep", "*", CYAN)
    pr()
    n = count or random.randint(14, 22)
    alive = filt = down = 0
    beep("scan")
    for _ in range(n):
        ip = fake_ip()
        w("\r%sprobing %s%-16s%s\033[K" % (GRAY, WHITE, ip, RST))
        nap(random.uniform(0.04, 0.14))
        st = random.choices(["ALIVE", "FILTERED", "DOWN"], [5, 2, 3])[0]
        ms = random.uniform(1, 180)
        if st == "ALIVE":
            alive += 1
            col, sym = GREEN, "●"
        elif st == "FILTERED":
            filt += 1
            col, sym = YELLOW, "◐"
        else:
            down += 1
            col, sym = RED, "○"
        line = "\r%s%s %-15s %-8s" % (col, sym, ip, st)
        if st != "DOWN":
            line += " %6.1fms" % ms
        else:
            line += "    ---  "
        if W >= 52 and st == "ALIVE":
            line += "  " + fake_host()
        w(line + RST + "\033[K\n")
        flush()
    progress("SWEEP COMPLETE", 0.6)
    pr()
    pr("%sSummary:%s  %sALIVE %d%s   %sFILTERED %d%s   %sDOWN %d%s" %
       (WHITE, RST, GREEN, alive, RST, YELLOW, filt, RST, RED, down, RST))
    beep("ok")


# ----------------------------------------------------------------------------
# 3. Port scan (fictional)
# ----------------------------------------------------------------------------
PORTS = [(21, "ftp"), (22, "ssh"), (23, "telnet"), (25, "smtp"), (53, "dns"), (80, "http"),
         (110, "pop3"), (143, "imap"), (443, "https"), (445, "smb"), (993, "imaps"),
         (1433, "mssql"), (3306, "mysql"), (3389, "rdp"), (5432, "postgres"),
         (5900, "vnc"), (6379, "redis"), (8080, "http-alt"), (8443, "https-alt"), (9200, "search")]


@sim
def port_scan(target=None):
    section("PORT SCANNER", BLUE)
    target = target or fake_ip()
    log("target : %s" % target, "*", CYAN)
    log("mac    : %s" % fake_mac(), "*", CYAN)
    log("scan   : SYN, %d ports" % len(PORTS), "*", CYAN)
    pr()
    pr("%s%-7s %-9s %-10s%s" % (GRAY, "PORT", "STATE", "SERVICE", RST))
    op = 0
    ports = list(PORTS)
    random.shuffle(ports)
    ports = sorted(ports[:random.randint(12, 18)])
    for i, (p, svc) in enumerate(ports):
        w("\r%sscanning port %-5d %s %3d%%%s\033[K" % (GRAY, p, "▮" * (i * 10 // len(ports)), i * 100 // len(ports), RST))
        nap(random.uniform(0.06, 0.16))
        st = random.choices(["open", "closed", "filtered"], [3, 5, 2])[0]
        if st == "open":
            op += 1
            col = GREEN
        elif st == "filtered":
            col = YELLOW
        else:
            col = RED
        w("\r%s%-7d %-9s %-10s%s\033[K\n" % (col, p, st, svc, RST))
        flush()
    progress("FINALIZING", 0.5)
    log("%d open ports found" % op, "+", GREEN)
    beep("ok")


# ----------------------------------------------------------------------------
# 4. Password decryption (fictional)
# ----------------------------------------------------------------------------
@sim
def decrypt_password():
    section("PASSWORD DECRYPTION", PURPLE)
    pw = fake_password()
    n = len(pw)
    log("hash type : SHA256", "*", CYAN)
    log("hash      : %s" % hx(32), "*", CYAN)
    log("wordlist  : phantom.dic", "*", CYAN)
    log("rate      : %.1f GH/s" % random.uniform(1.5, 9.9), "*", CYAN)
    pr()
    tries = 0
    for pos in range(n + 1):
        for _ in range(random.randint(5, 12)):
            tries += random.randint(2000, 90000)
            scr = "".join(random.choice(GLYPH) for _ in range(n - pos))
            w("\r  [%s%s%s%s%s%s] %s%s tries%s\033[K" %
              (GREEN, BOLD, pw[:pos], RST + DIM + random.choice(PALETTE), scr, RST + WHITE, GRAY, format(tries, ","), RST))
            flush()
            nap(0.025)
        beep("tick")
    w("\n")
    pr()
    pr("%s╔%s╗%s" % (GREEN, "═" * (n + 20), RST))
    pr("%s║  PASSWORD CRACKED: %s%s%s%s  ║%s" % (GREEN, BOLD, WHITE, pw, RST + GREEN, RST))
    pr("%s╚%s╝%s" % (GREEN, "═" * (n + 20), RST))
    beep("ok")


# ----------------------------------------------------------------------------
# 5. Firewall bypass
# ----------------------------------------------------------------------------
@sim
def firewall_bypass():
    section("FIREWALL BYPASS", RED)
    target = fake_ip()
    log("target firewall : %s" % target, "*", CYAN)
    stages = ["Fingerprinting rules", "Spoofing packet headers", "Rotating proxy chain",
              "Patching ACL table", "Masking MAC address", "Disabling IDS signatures"]
    for s in stages:
        progress(s, random.uniform(0.8, 1.6))
        if random.random() < 0.7:
            log("rule #%d  DROP -> ALLOW" % random.randint(100, 9999), "+", GREEN)
        if random.random() < 0.3:
            log("retrying with new key %s" % hx(8), "?", YELLOW)
    pr()
    hops = " %s▸%s " % (GRAY, RST)
    chain = hops.join("%sN%02d%s" % (random.choice(PALETTE), random.randint(1, 99), RST) for _ in range(5))
    log("proxy chain : ", "*", CYAN)
    pr("  " + chain)
    pr()
    beep("ok")
    for i in range(3):
        w("\r%s%s FIREWALL BYPASSED %s%s" % (bg(0, 120, 40) if i % 2 == 0 else "", WHITE, "" if i % 2 else "", RST))
        w("\033[K")
        flush()
        nap(0.25)
    w("\n")


# ----------------------------------------------------------------------------
# 6. System breach
# ----------------------------------------------------------------------------
@sim
def system_breach():
    section("SYSTEM BREACH", RED)
    ip = fake_ip()
    W = width()
    script = [
        ("resolving gateway %s" % ip, "*"),
        ("opening covert channel on port %d" % random.randint(1024, 65000), "*"),
        ("negotiating session key %s" % hx(16), "*"),
        ("injecting payload stub", "?"),
        ("exploit module loaded: phantom.exp.%s" % hx(4), "#"),
        ("bypassing authentication layer", "?"),
        ("escalating privileges", "?"),
        ("kernel handle acquired 0x%s" % hx(8), "+"),
        ("disabling audit daemon", "?"),
        ("clearing trace buffers", "*"),
        ("persistence node planted", "#"),
        ("mapping internal subnets", "*"),
    ]
    per = 8 if W < 60 else 16
    for i, (msg, t) in enumerate(script):
        w("%s " % tag(t))
        typewrite(msg, GREEN if t == "+" else CYAN, 0.01)
        nap(random.uniform(0.05, 0.2))
        if i % 3 == 2:
            for _ in range(random.randint(2, 4)):
                addr = random.randint(0, 0xFFFFFF)
                bts = [random.randint(0, 255) for _ in range(per)]
                hexs = " ".join("%02x" % b for b in bts)
                asc = "".join(chr(b) if 33 <= b < 127 else "." for b in bts)
                pr("%s%06x  %s%s  %s|%s|%s" % (GRAY, addr, PURPLE, hexs, GRAY, asc, RST))
                nap(0.05)
        if i in (3, 8):
            progress("working", random.uniform(0.6, 1.2))
    pr()
    beep("alert")
    pr(rainbow(" >>> ROOT SHELL OPENED <<< ".center(W), 0.0, 0.05))
    pr()
    for cmd, out in [("whoami", "root"), ("id", "uid=0(root) gid=0(root)"), ("ls /vault", "ledger.db  archive/  keys.vault  mail.idx")]:
        w("%sroot@%s:~# %s" % (RED, ip, RST))
        typewrite(cmd, WHITE, 0.03)
        pr(GREEN + out + RST)
        nap(0.2)
    pr()


# ----------------------------------------------------------------------------
# 7. Database download
# ----------------------------------------------------------------------------
@sim
def db_download():
    section("DATABASE DOWNLOAD", GREEN)
    tables = ["users_vault", "ledger", "audit_log", "sessions", "archive", "mail_index", "telemetry"]
    random.shuffle(tables)
    tables = tables[:random.randint(4, 6)]
    log("source : db://%s/vault" % fake_ip(), "*", CYAN)
    log("tables : %d" % len(tables), "*", CYAN)
    pr()
    total = 0.0
    for t in tables:
        size = random.uniform(8, 2400)
        total += size
        speed = random.uniform(8, 95)
        progress("%-11s %8s" % (t, human_size(size)), random.uniform(0.9, 1.9))
        log("%s  %.1f MB/s  sha:%s" % (t, speed, hx(10)), "+", GREEN)
    pr()
    pr("%s╔═ DOWNLOAD COMPLETE ═══════════%s" % (GREEN, RST))
    pr("%s║%s total   : %s%s" % (GREEN, RST, WHITE, human_size(total)))
    pr("%s║%s records : %s%s" % (GREEN, RST, WHITE, format(random.randint(10 ** 5, 9 * 10 ** 7), ",")))
    pr("%s║%s checksum: %s%s" % (GREEN, RST, WHITE, hx(24)))
    pr("%s╚═══════════════════════════════%s" % (GREEN, RST))
    beep("done")


# ----------------------------------------------------------------------------
# 8. Satellite connection
# ----------------------------------------------------------------------------
@sim
def satellite():
    section("SATELLITE CONNECTION", BLUE)
    sats = ["NP-SAT-01 ORION", "NP-SAT-07 VEGA", "NP-SAT-12 NOVA", "NP-SAT-19 LYRA", "NP-SAT-23 AURORA"]
    log("scanning orbital slots...", "*", CYAN)
    levels = " ▂▃▄▅▆▇█"
    best, best_sig = None, -1
    for s in sats:
        sig = random.randint(15, 98)
        nap(0.25)
        icon = levels[clamp(sig * 8 // 100, 1, 7)] * 3
        col = GREEN if sig > 66 else (YELLOW if sig > 40 else RED)
        pr("  %s%-18s %s%s %3d%%%s" % (WHITE, s, col, icon, sig, RST))
        if sig > best_sig:
            best, best_sig = s, sig
    pr()
    log("best link : %s (%d%%)" % (best, best_sig), "+", GREEN)
    steps = ["acquiring signal (AOS)", "locking carrier", "uplink handshake", "exchanging keys", "syncing clocks"]
    for st in steps:
        progress(st, random.uniform(0.6, 1.1))
    W = width()
    track = max(12, W - 8)
    for i in range(track * 2):
        pos = int((math.sin(i / 6.0) * 0.5 + 0.5) * (track - 1))
        row = [GRAY + "·"] * track
        row[pos] = YELLOW + "◉"
        w("\r%s[%s%s]%s \033[K" % (BLUE, "".join(row), BLUE, RST))
        flush()
        nap(0.02)
    w("\n")
    pr()
    log("uplink freq : %.3f GHz" % random.uniform(2.0, 14.5), "*", CYAN)
    log("azimuth/elev: %.1f / %.1f deg" % (random.uniform(0, 360), random.uniform(5, 88)), "*", CYAN)
    log("latency     : %d ms" % random.randint(180, 620), "*", CYAN)
    log("SATELLITE LINK ESTABLISHED", "+", GREEN)
    beep("ok")


# ----------------------------------------------------------------------------
# 9. GPS tracking (fictional radar)
# ----------------------------------------------------------------------------
@sim
def gps_tracking():
    section("GPS TRACKING", ORANGE)
    W = width()
    gw = min(W - 4, 41)
    if gw % 2 == 0:
        gw -= 1
    gh = 11
    lat = random.uniform(-55, 65)
    lon = random.uniform(-170, 175)
    tx, ty = random.randrange(2, gw - 2), random.randrange(2, gh - 2)
    steps = 34
    live = Live()
    for s in range(steps + 1):
        k = s / float(steps)
        if s == steps:
            px, py = tx, ty
        else:
            px = clamp(int(tx + random.randint(-gw // 3, gw // 3) * (1 - k)), 0, gw - 1)
            py = clamp(int(ty + random.randint(-gh // 3, gh // 3) * (1 - k)), 0, gh - 1)
        lines = [ORANGE + "┌" + "─" * gw + "┐" + RST]
        for y in range(gh):
            row = []
            for x in range(gw):
                if x == px and y == py:
                    row.append(RED + BOLD + "◉")
                elif x == px:
                    row.append(CYAN + DIM + "│")
                elif y == py:
                    row.append(CYAN + DIM + "─")
                else:
                    row.append(GRAY + "·")
            lines.append(ORANGE + "│" + RST + "".join(row) + RST + ORANGE + "│" + RST)
        lines.append(ORANGE + "└" + "─" * gw + "┘" + RST)
        jl = (1 - k) * random.uniform(-9, 9)
        jo = (1 - k) * random.uniform(-9, 9)
        lines.append("%sLAT %s%+9.4f   %sLON %s%+10.4f%s" % (GRAY, WHITE, lat + jl, GRAY, WHITE, lon + jo, RST))
        lines.append("%sSATS %s%d/14   %sSIGNAL %s%d%%%s" % (GRAY, WHITE, 4 + int(k * 9), GRAY, WHITE, int(30 + k * 66), RST))
        lines.append((GREEN + "TARGET LOCKED" if s == steps else YELLOW + "acquiring...") + RST)
        live.draw(lines)
        nap(0.07)
    beep("ok")


# ----------------------------------------------------------------------------
# 10. CPU / RAM monitor
# ----------------------------------------------------------------------------
@sim
def cpu_ram_monitor(seconds=12):
    section("CPU / RAM MONITOR", GREEN)
    W = width()
    bw = max(8, W - 18)
    cores = [random.randint(10, 60) for _ in range(8)]
    ram = random.randint(35, 60)
    swap = random.randint(5, 25)
    temp = random.randint(42, 58)
    procs = ["phantomd", "cryptd", "netghost", "matrixd", "shadowsh", "scand"]
    live = Live()
    end = time.time() + seconds
    while time.time() < end:
        lines = []
        for i in range(8):
            cores[i] = clamp(cores[i] + random.randint(-15, 18), 2, 100)
            lines.append("%sCPU%d %s %s%3d%%%s" % (GRAY, i, mbar(cores[i], bw), WHITE, cores[i], RST))
        ram = clamp(ram + random.randint(-3, 4), 20, 95)
        swap = clamp(swap + random.randint(-2, 2), 0, 60)
        temp = clamp(temp + random.randint(-2, 3), 38, 88)
        lines.append("%sRAM  %s %s%3d%%%s" % (CYAN, mbar(ram, bw), WHITE, ram, RST))
        lines.append("%sSWAP %s %s%3d%%%s" % (CYAN, mbar(swap, bw), WHITE, swap, RST))
        lines.append("%sTEMP %s%d C%s   %sLOAD %s%.2f %.2f %.2f%s" %
                     (PURPLE, WHITE, temp, RST, PURPLE, WHITE, random.uniform(0.2, 4), random.uniform(0.2, 3), random.uniform(0.2, 2.5), RST))
        for p in random.sample(procs, 3):
            lines.append("%s  %-10s pid %-5d cpu %s%4.1f%%%s" % (GRAY, p, random.randint(100, 9999), YELLOW, random.uniform(0.1, 40), RST))
        live.draw(lines)
        nap(0.3)


# ----------------------------------------------------------------------------
# 11. Network traffic
# ----------------------------------------------------------------------------
@sim
def network_traffic(seconds=12):
    section("NETWORK TRAFFIC", CYAN)
    W = width()
    sw = max(10, W - 22)
    spark = "▁▂▃▄▅▆▇█"
    rx = [random.randint(5, 40) for _ in range(sw)]
    tx = [random.randint(2, 25) for _ in range(sw)]
    live = Live()
    end = time.time() + seconds
    protos = ["TCP", "UDP", "TLS", "QUIC", "DNS"]
    while time.time() < end:
        rx = rx[1:] + [clamp(rx[-1] + random.randint(-20, 22), 1, 100)]
        tx = tx[1:] + [clamp(tx[-1] + random.randint(-15, 16), 1, 100)]

        def line(vals, col):
            return "".join(col + spark[min(7, v * 8 // 101)] for v in vals) + RST

        lines = [
            "%sRX %s %s%6.1f Mb/s%s" % (GREEN, line(rx, GREEN), WHITE, rx[-1] * 1.7, RST),
            "%sTX %s %s%6.1f Mb/s%s" % (PURPLE, line(tx, PURPLE), WHITE, tx[-1] * 1.2, RST),
            "%sPKTS/s %s%-7d %sDROP %s%.2f%%%s" % (GRAY, WHITE, random.randint(800, 9000), GRAY, WHITE, random.uniform(0, 1.5), RST),
            "%s%s%s" % (GRAY, "─" * (W - 1), RST),
        ]
        for _ in range(6):
            lines.append("%s%-4s %s%-15s%s>%s %-15s %s:%d%s" %
                         (random.choice(PALETTE), random.choice(protos), WHITE, fake_ip(), GRAY, WHITE, fake_ip(), CYAN, random.choice([22, 53, 80, 443, 8080, 3306]), RST))
        live.draw(lines)
        nap(0.35)


# ----------------------------------------------------------------------------
# 12. Hash generator
# ----------------------------------------------------------------------------
@sim
def hash_generator(text=None):
    section("RANDOM HASH GENERATOR", PURPLE)
    W = width()
    data = text.encode("utf-8") if text else os.urandom(32)
    if text:
        log("input : %s" % text[:40], "*", CYAN)
    else:
        log("input : %d random bytes" % 32, "*", CYAN)
    pr()
    for name in ("md5", "sha1", "sha256", "sha512"):
        digest = hashlib.new(name, data).hexdigest()
        pr("%s%s%s" % (YELLOW, name.upper(), RST))
        chunk = max(16, W - 4)
        for i in range(0, len(digest), chunk):
            reveal(digest[i:i + chunk], GREEN, "  ", 10, 0.015)
        beep("tick")
    pr()


# ----------------------------------------------------------------------------
# 13. Fake encryption / decryption (toy XOR so decrypt really reverses it)
# ----------------------------------------------------------------------------
def _xor_hex(data_bytes, key_bytes):
    return bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data_bytes))


@sim
def encrypt_text(text=None):
    section("ENCRYPTION", PURPLE)
    text = text or "NEON PHANTOM ONLINE"
    key = os.urandom(8)
    log("cipher : PHANTOM-256", "*", CYAN)
    log("key    : %s" % key.hex(), "*", CYAN)
    log("plain  : %s" % text[:60], "*", CYAN)
    pr()
    for r in range(1, 15, 2):
        progress("round %02d/14" % r, 0.25)
    cipher = _xor_hex(text.encode("utf-8"), key).hex()
    pr()
    pr("%sCIPHERTEXT:%s" % (YELLOW, RST))
    W = width()
    chunk = max(16, W - 4)
    for i in range(0, len(cipher), chunk):
        reveal(cipher[i:i + chunk], PURPLE, "  ", 12, 0.015)
    S.last_cipher, S.last_key, S.last_plain = cipher, key.hex(), text
    pr()
    log("saved in memory - run 'decrypt msg' or menu 15 -> 2 to decrypt", "+", GREEN)
    beep("ok")


@sim
def decrypt_message():
    section("DECRYPTION", PURPLE)
    if not S.last_cipher:
        log("no encrypted message yet - encrypt something first", "!", YELLOW)
        return
    log("key    : %s" % S.last_key, "*", CYAN)
    log("cipher : %s" % S.last_cipher[:W_SAFE()], "*", CYAN)
    pr()
    for r in range(1, 15, 2):
        progress("round %02d/14" % r, 0.25)
    plain = _xor_hex(bytes.fromhex(S.last_cipher), bytes.fromhex(S.last_key)).decode("utf-8", "replace")
    pr()
    w("%sPLAINTEXT:%s\n" % (YELLOW, RST))
    reveal(plain, GREEN, "  ", 14, 0.03)
    beep("ok")


def W_SAFE():
    return max(16, width() - 14)


# ----------------------------------------------------------------------------
# 14. Security alert
# ----------------------------------------------------------------------------
@sim
def security_alert():
    W = width()
    beep("alert")
    msgs = ["!! INTRUSION DETECTED !!", "!! TRACE ROUTINE ACTIVE !!", "!! COUNTERMEASURES ARMED !!"]
    for i in range(8):
        m = msgs[i % len(msgs)]
        if i % 2 == 0:
            w("%s%s%s%s%s\n" % (bg(200, 0, 30), BOLD, WHITE, m.center(W), RST))
        else:
            w("%s%s%s%s\n" % (RED, BOLD, m.center(W), RST))
        flush()
        if i % 2 == 0:
            beep("tick")
        nap(0.22)
    pr()
    log("unknown scan from %s" % fake_ip(), "!", RED)
    log("firewall integrity: %d%%" % random.randint(12, 48), "!", ORANGE)
    log("activating ghost mode", "?", YELLOW)
    for c in range(5, 0, -1):
        w("\r%s evading trace in %s%d%s ...\033[K" % (YELLOW, RED, c, YELLOW))
        flush()
        nap(0.5)
    w("\n")
    progress("rerouting", 1.0)
    log("ALERT CLEARED - ghost mode active", "+", GREEN)
    beep("ok")


# ----------------------------------------------------------------------------
# 15. Access granted
# ----------------------------------------------------------------------------
@sim
def access_granted():
    W = width()
    final = "A C C E S S   G R A N T E D"
    final = final if len(final) + 4 <= W else "ACCESS GRANTED"
    pr()
    log("authenticating operator %s" % S.username, "*", CYAN)
    for item in ["biometric check", "token verification", "clearance level", "session binding"]:
        progress(item, 0.6)
    pr()
    inner = len(final) + 4
    pr(GREEN + ("╔" + "═" * inner + "╗").center(W) + RST)
    n = len(final)
    for r in range(18):
        k = int(n * r / 17.0)
        scr = "".join(random.choice("#%&@$01") for _ in range(n - k))
        row = "║  %s  ║" % (final[:k] + scr)
        w("\r%s%s%s\033[K" % (random.choice([GREEN, CYAN, WHITE]), row.center(W), RST))
        flush()
        nap(0.05)
    w("\r" + GREEN + BOLD + ("║  %s  ║" % final).center(W) + RST + "\033[K\n")
    pr(GREEN + ("╚" + "═" * inner + "╝").center(W) + RST)
    pr()
    log("welcome, %s" % S.username, "+", GREEN)
    log("clearance : LEVEL 9", "#", PURPLE)
    beep("done")


# ----------------------------------------------------------------------------
# 16. Mission complete
# ----------------------------------------------------------------------------
@sim
def mission_complete():
    W = width()
    elapsed = int(time.time() - S.started)
    pr()
    for i in range(14):
        w("\r" + rainbow("M I S S I O N   C O M P L E T E".center(W), i * 0.08, 0.03) + "\033[K")
        flush()
        nap(0.12)
    w("\n")
    pr(gradient_line("═", W))
    rows = [
        ("OPERATOR", S.username),
        ("TARGET", fake_ip()),
        ("SESSION", "%02d:%02d:%02d" % (elapsed // 3600, elapsed % 3600 // 60, elapsed % 60)),
        ("OPERATIONS RUN", str(S.ops)),
        ("DATA EXTRACTED", human_size(random.uniform(500, 90000))),
        ("SYSTEMS OWNED", str(random.randint(3, 42))),
        ("TRACE RISK", "%d%%" % random.randint(0, 3)),
        ("RANK", random.choice(["PHANTOM", "SPECTER", "GHOST-ELITE", "ZERO-DAY LEGEND"])),
    ]
    for k, v in rows:
        pr("  %s%-15s%s %s%s%s" % (GRAY, k, RST, WHITE, v, RST))
        nap(0.12)
    pr(gradient_line("═", W, 0.5))
    beep("done")


# ----------------------------------------------------------------------------
# 17. Random hacker commands (invented tool names, scripted output)
# ----------------------------------------------------------------------------
CMD_BANK = [
    ("ghostmap --stealth {ip}", ["mapping 1024 vectors...", "fingerprint: NP-OS %s" % "7.2", "done in 0.42s"]),
    ("neonbrute --target {ip} --mode fast", ["loading dictionary", "threads: 64", "candidate pool exhausted: 1 match"]),
    ("cipherx --decode {hash}", ["block 1/4 ok", "block 2/4 ok", "block 3/4 ok", "block 4/4 ok"]),
    ("phantom-tunnel up --hops 5", ["hop 1 ok", "hop 2 ok", "hop 3 ok", "hop 4 ok", "hop 5 ok", "tunnel: ACTIVE"]),
    ("shadowsh --inject payload.bin", ["payload staged", "queue: 0", "status: delivered"]),
    ("tracewipe --all", ["buffers cleared: %d" % 128, "logs rotated"]),
    ("vaultscan --deep {ip}", ["indexing...", "%d objects catalogued" % 4096, "report: vault.rpt"]),
    ("sigforge --spoof {mac}", ["signature rewritten", "header checksum: ok"]),
    ("matrixd --daemon", ["pid %d" % 4242, "listening on :4242"]),
    ("relay-hop --rotate", ["new exit node: N%02d" % 17, "latency 83ms"]),
]


@sim
def random_commands(count=None):
    section("TERMINAL", GREEN)
    W = width()
    n = count or random.randint(6, 9)
    for _ in range(n):
        cmd, outs = random.choice(CMD_BANK)
        cmd = cmd.replace("{ip}", fake_ip()).replace("{hash}", hx(12)).replace("{mac}", fake_mac())
        w("%s%s@phantom%s:%s~%s$ %s" % (GREEN, S.username.lower(), WHITE, PURPLE, RED, RST))
        typewrite(cmd, WHITE, 0.025)
        for o in random.sample(outs, random.randint(1, len(outs))):
            pr("  %s%s%s" % (random.choice([CYAN, GREEN, GRAY]), o[:W - 4], RST))
            nap(0.12)
        beep("tick")
        nap(0.2)


# ----------------------------------------------------------------------------
# 18. Advanced loading animations
# ----------------------------------------------------------------------------
@sim
def loading_animations(per=1.3):
    section("ADVANCED LOADING ANIMATIONS", CYAN)
    W = width()
    brl = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def spinner(label):
        end = time.time() + per
        i = 0
        while time.time() < end:
            w("\r%s%s %s%s\033[K" % (hsv(i * 0.05), brl[i % len(brl)], WHITE, label))
            flush()
            nap(0.07)
            i += 1
        w("\r%s✔ %s%s\033[K\n" % (GREEN, WHITE, label))

    def dots(label):
        end = time.time() + per
        i = 0
        while time.time() < end:
            w("\r%s%s%s%s\033[K" % (CYAN, label, "." * (i % 4), RST))
            flush()
            nap(0.15)
            i += 1
        w("\r%s%s... done%s\033[K\n" % (GREEN, label, RST))

    def bounce(label):
        bw = max(10, W - len(label) - 8)
        end = time.time() + per
        i = 0
        while time.time() < end:
            p = i % (2 * (bw - 3))
            p = p if p < bw - 3 else 2 * (bw - 3) - p
            cells = [GRAY + " "] * bw
            for j in range(3):
                cells[p + j] = hsv(i * 0.03 + j * 0.1) + "█"
            w("\r%s%s %s[%s%s]%s\033[K" % (WHITE, label, BLUE, "".join(cells), BLUE, RST))
            flush()
            nap(0.025)
            i += 1
        w("\r%s%s [%s]%s\033[K\n" % (GREEN, label, "█" * bw, RST))

    def pulse(label):
        blocks = " ░▒▓█▓▒░"
        end = time.time() + per
        i = 0
        while time.time() < end:
            s = "".join(hsv(i * 0.04 + j * 0.08) + blocks[(i + j) % len(blocks)] for j in range(12))
            w("\r%s %s%s\033[K" % (s, WHITE, label))
            flush()
            nap(0.06)
            i += 1
        w("\r%s✔ %s%s\033[K\n" % (GREEN, WHITE, label))

    def hexstream(label):
        end = time.time() + per
        while time.time() < end:
            w("\r%s%s %s%s\033[K" % (PURPLE, hx(max(8, W - len(label) - 6)), WHITE, label))
            flush()
            nap(0.05)
        w("\r%s✔ %s%s\033[K\n" % (GREEN, WHITE, label))

    spinner("Spinner: establishing uplink")
    dots("Dots: syncing nodes")
    bounce("Scanner:")
    pulse("Pulse: charging core")
    hexstream("Stream: decoding")
    progress("Final bar", 1.0)


# ----------------------------------------------------------------------------
# 19. RGB terminal effects
# ----------------------------------------------------------------------------
@sim
def rgb_effects(seconds=5):
    section("RGB TERMINAL EFFECTS", PINK)
    W = width()
    text = ["NEON//PHANTOM".center(W), "R  G  B   M  O  D  E".center(W)]
    live = Live()
    end = time.time() + seconds / 2.0
    t = 0.0
    while time.time() < end:
        lines = []
        for y, ln in enumerate(text):
            lines.append("".join(hsv(x * 0.03 + t * 0.6 + y * 0.15) + ch for x, ch in enumerate(ln)) + RST)
        lines.append(gradient_line("█", W, t * 0.4))
        lines.append(gradient_line("▓", W, t * 0.4 + 0.3))
        lines.append(gradient_line("▒", W, t * 0.4 + 0.6))
        live.draw(lines)
        t += 0.08
        nap(0.04)
    live = Live()
    end = time.time() + seconds / 2.0
    pw = min(W, 60)
    while time.time() < end:
        lines = []
        for y in range(8):
            row = []
            for x in range(pw):
                v = math.sin(x / 5.0 + t) + math.sin(y / 2.0 + t * 1.3) + math.sin((x + y) / 6.0 - t)
                row.append(hsv(v / 6.0 + t * 0.1) + "█")
            lines.append("".join(row) + RST)
        live.draw(lines)
        t += 0.12
        nap(0.04)


# ----------------------------------------------------------------------------
# Connect (console) + status
# ----------------------------------------------------------------------------
@sim
def connect_sim(target=None):
    section("SECURE CONNECT", BLUE)
    target = target or fake_ip()
    log("target : %s" % target, "*", CYAN)
    for s in ["resolving route", "TLS handshake", "exchanging keys", "building tunnel"]:
        progress(s, random.uniform(0.5, 1.0))
    log("tunnel ID : %s" % hx(12), "*", CYAN)
    log("CONNECTED to %s" % target, "+", GREEN)
    beep("ok")


@sim
def status_sim():
    section("SYSTEM STATUS", GREEN)
    W = width()
    bw = max(8, W - 24)
    elapsed = int(time.time() - S.started)
    pr("%s%-12s%s %s" % (GRAY, "operator", RST, S.username))
    pr("%s%-12s%s NP-%04d" % (GRAY, "node", RST, random.randint(1000, 9999)))
    pr("%s%-12s%s %02d:%02d:%02d" % (GRAY, "uptime", RST, elapsed // 3600, elapsed % 3600 // 60, elapsed % 60))
    pr("%s%-12s%s %sACTIVE%s" % (GRAY, "vpn", RST, GREEN, RST))
    pr("%s%-12s%s %d circuits" % (GRAY, "tor", RST, random.randint(3, 9)))
    pr("%s%-12s%s %sGHOST%s" % (GRAY, "mode", RST, PURPLE, RST))
    for lbl in ["cpu", "ram", "net", "shield"]:
        v = random.randint(10, 95)
        pr("%s%-8s%s %s %s%3d%%%s" % (GRAY, lbl, RST, mbar(v, bw), WHITE, v, RST))


# ----------------------------------------------------------------------------
# Automatic hacker mode
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
# PRO OPERATION - split-screen "elite operator" workstation mode
#   fixed status header + footer, timestamped log stream in a scroll region,
#   multi-phase operation (recon -> enum -> exploit -> privesc -> persist ->
#   exfil -> cleanup). All text is scripted; nothing real is touched.
# ----------------------------------------------------------------------------
PHASES = ["RECON", "ENUM", "EXPLOIT", "PRIVESC", "PERSIST", "EXFIL", "CLEANUP"]
PHASE_SHORT = ["RC", "EN", "EX", "PE", "PS", "XF", "CL"]
CODE_A = ["SILENT", "CRIMSON", "HOLLOW", "BLACK", "VELVET", "IRON", "GHOST", "COLD", "NEON", "SHADOW"]
CODE_B = ["VORTEX", "HARVEST", "MERIDIAN", "LANTERN", "SPECTER", "TIDE", "FALCON", "CIPHER", "ORCHID", "ANVIL"]
LVL_COL = {"INFO": CYAN, "OK": GREEN, "WARN": YELLOW, "ALERT": RED, "CMD": PURPLE, "DATA": GRAY}
SVC_BANK = [
    (21, "ftp", "vsftpd 3.0.5"), (22, "ssh", "OpenSSH 8.9p1 Ubuntu"), (25, "smtp", "Postfix smtpd"),
    (53, "domain", "ISC BIND 9.18.12"), (80, "http", "nginx 1.22.1"), (110, "pop3", "Dovecot pop3d"),
    (143, "imap", "Dovecot imapd"), (443, "https", "nginx 1.22.1 (TLS 1.3)"), (445, "smb", "Samba 4.15.13"),
    (3306, "mysql", "MySQL 5.7.38"), (5432, "postgresql", "PostgreSQL 13.7"), (6379, "redis", "Redis 6.0.16"),
    (8080, "http-proxy", "Apache Tomcat 9.0.62"), (8443, "https-alt", "Jetty 10.0.11"), (9200, "elastic", "Elasticsearch 7.17"),
]
EXPLOITS = [
    ("web/deserialize_rce", "Unauthenticated request deserialization"),
    ("auth/token_forge", "Session token forgery on admin portal"),
    ("svc/buffer_stage", "Stack overflow in protocol parser"),
    ("file/path_walk", "Directory traversal in file endpoint"),
]
FILES = [("payroll_2026.db", 412), ("customers.sqlite", 1830), ("vpn_configs.tar", 38), ("audit_export.csv", 276),
         ("board_minutes.pdf", 14), ("source_snapshot.zip", 2210), ("mail_archive.pst", 3490), ("hr_records.xlsx", 96)]


CUR_BAR = ("█", "░")
SYM = {"INFO": "›", "OK": "✔", "WARN": "!", "ALERT": "✖", "CMD": "$", "DATA": "·"}
TAGTXT = {"INFO": " INFO ", "OK": "  OK  ", "WARN": " WARN ", "ALERT": "FAILED", "CMD": " EXEC ", "DATA": " DATA "}


class OpUI(object):
    """Split-screen operator console: fixed header/footer + scrolling log.
    Each scenario picks its own log style, colour theme and bar style."""

    def __init__(self, code, target, phases=None, scenario="", style="syslog", theme=None):
        sz = shutil.get_terminal_size((50, 24))
        self.cols = max(30, sz.columns)
        self.rows = max(12, sz.lines)
        self.code = code
        self.target = target
        self.phases = phases or list(zip(PHASES, PHASE_SHORT))
        self.scenario = scenario or "Network Intrusion"
        self.style = style
        self.theme = theme or ((70, 0, 25), (40, 0, 15), YELLOW)
        self.t0 = time.time()
        self.phase = -1
        self.sessions = 0
        self.rx = random.randint(1, 50)
        self.tx = random.randint(1, 20)

    # -- screen plumbing ----------------------------------------------------
    def _put(self, row, s):
        w("\0337\033[%d;1H%s%s\0338" % (row, s, RST))

    def start(self):
        clear()
        w("\033[3;%dr" % (self.rows - 1))
        self.header()
        self.footer()
        w("\033[%d;1H" % (self.rows - 1))
        flush()

    def stop(self):
        w("\033[r\033[%d;1H\n" % self.rows)
        w(SHOW + RST)
        flush()

    def header(self):
        hb, fb, acc = self.theme
        if self.cols >= 60:
            txt = " NEON//PHANTOM | %s | OP %s | TGT %s" % (self.scenario.upper(), self.code, self.target)
        else:
            txt = " OP %s | TGT %s" % (self.code, self.target)
        self._put(1, bg(*hb) + BOLD + WHITE + txt[:self.cols].ljust(self.cols))
        full = [p[0] for p in self.phases]
        short = [p[1] for p in self.phases]
        long_len = 1 + sum(len(x) for x in full) + 3 * (len(full) - 1)
        long_names = long_len <= self.cols
        names = full if long_names else short
        sep = " > " if long_names else " "
        base = bg(12, 12, 18)
        s = base + " "
        length = 1
        for i, nm in enumerate(names):
            if i < self.phase:
                col = GREEN
            elif i == self.phase:
                col = acc + BOLD
            else:
                col = GRAY
            s += col + nm + RST + base
            length += len(nm)
            if i < len(names) - 1:
                s += GRAY + sep + base
                length += len(sep)
        s += " " * max(0, self.cols - length)
        self._put(2, s)

    def footer(self):
        fb = self.theme[1]
        e = int(time.time() - self.t0)
        ph = self.phases[self.phase][0] if self.phase >= 0 else "INIT"
        self.rx += random.randint(0, 40)
        self.tx += random.randint(0, 15)
        txt = " %02d:%02d | %s | SESS:%d | RX %dK TX %dK | ^C ABORT" % (e // 60, e % 60, ph, self.sessions, self.rx, self.tx)
        self._put(self.rows, bg(*fb) + WHITE + txt[:self.cols].ljust(self.cols))

    # -- output primitives --------------------------------------------------
    def log(self, lvl, mod, msg, color=None, delay=None):
        col = LVL_COL[lvl]
        st = self.style if self.cols >= 52 else "arrow"
        ts = time.strftime("%H:%M:%S")
        sy = SYM[lvl]
        if st == "syslog":
            plain = "%s %-5s %-8s " % (ts, lvl, mod)
            colored = "%s%s%s %s%-5s%s %s%-8s%s " % (GRAY, ts, RST, col, lvl, RST, GRAY, mod, RST)
        elif st == "tree":
            plain = "├─ %s " % sy
            colored = "%s├─%s %s%s%s " % (GRAY, RST, col, sy, RST)
        elif st == "arrow":
            plain = "%s " % (sy * 2)
            colored = "%s%s%s " % (col, sy * 2, RST)
        elif st == "box":
            plain = "│ %-5s │ %-8s │ " % (lvl, mod)
            colored = "%s│%s %s%-5s%s %s│ %-8s │%s " % (GRAY, RST, col, lvl, RST, GRAY, mod, RST)
        elif st == "term":
            plain = "%s:~$ " % mod
            colored = "%s%s%s%s:~$%s " % (col, mod, RST, GRAY, RST)
        else:  # tag, systemd-like
            plain = "[%s] " % TAGTXT[lvl]
            colored = "%s[%s%s%s%s]%s " % (GRAY, col, TAGTXT[lvl], RST, GRAY, RST)
        avail = max(10, self.cols - len(plain) - 1)
        lines = textwrap.wrap(msg, avail) or [""]
        for i, l in enumerate(lines):
            pre = colored if i == 0 else " " * len(plain)
            pr(pre + (color or WHITE) + l + RST)
        self.footer()
        nap(delay if delay is not None else random.uniform(0.05, 0.3))

    def raw(self, text, color=WHITE, delay=0.06):
        pr(color + text[:self.cols - 1] + RST)
        nap(delay)

    def set_phase(self, i):
        self.phase = i
        self.header()
        pr()
        acc = self.theme[2]
        name = self.phases[i][0]
        n = len(self.phases)
        W = self.cols - 1
        st = self.style
        if st == "syslog":
            txt = "===== PHASE %d/%d : %s =====" % (i + 1, n, name)
        elif st == "tree":
            txt = ("┏━━ PHASE %d/%d ┫ %s ┣" % (i + 1, n, name)).ljust(W, "━")
        elif st == "arrow":
            txt = (">>> %s  [%d/%d] " % (name, i + 1, n)).ljust(W, "»")
        elif st == "box":
            txt = ("╔═[ %s %d/%d ]" % (name, i + 1, n)).ljust(W, "═")
        elif st == "term":
            txt = "# ---- %s (%d/%d) ----" % (name.lower(), i + 1, n)
        else:
            txt = "        -- %s --" % name
        pr(acc + BOLD + txt[:W] + RST)
        self.footer()
        nap(0.3)

    def shell(self, prompt, cmd, out=()):
        w(prompt + " ")
        typewrite(cmd, WHITE, 0.03)
        for o in out:
            pr(GRAY + o[:self.cols - 1] + RST)
            nap(random.uniform(0.04, 0.18))
        self.footer()

    def hexdump(self, lines=3):
        per = 8 if self.cols < 60 else 16
        for _ in range(lines):
            bts = [random.randint(0, 255) for _ in range(per)]
            hexs = " ".join("%02x" % b for b in bts)
            asc = "".join(chr(b) if 33 <= b < 127 else "." for b in bts)
            pr("%s%06x  %s%s  %s|%s|%s" % (GRAY, random.randint(0, 0xFFFFFF), PURPLE, hexs, GRAY, asc, RST))
            nap(0.04)

    def noise(self, chance=0.35):
        if random.random() < chance:
            self.log("WARN", "evasion", "IDS signature NP-IDS-%d matched on %s - evasion profile %s applied" %
                     (random.randint(1000, 9999), self.target, hx(4)), YELLOW)
            self.log("OK", "evasion", "alert suppressed (score %.2f)" % random.uniform(0.01, 0.2), GREEN)

    def stream(self, seconds, fn, lo=0.05, hi=0.3):
        """Call fn() repeatedly for `seconds` (scaled by the length setting)."""
        end = time.time() + seconds * S.length
        while time.time() < end:
            fn()
            if random.random() < 0.04:
                self.noise(1.0)
            nap(random.uniform(lo, hi))


def _live(ui, seconds, frame_fn, delay=0.12):
    live = Live()
    end = time.time() + seconds * S.length
    f = 0
    maxh = max(3, ui.rows - 5)
    while time.time() < end:
        live.draw(frame_fn(f)[:maxh])
        ui.footer()
        f += 1
        nap(delay)


def _prog(label, lo=3.0, hi=7.0):
    progress(label, max(0.4, random.uniform(lo, hi) * S.length))


def _summary(ui, extra):
    pr()
    el = int(time.time() - ui.t0)
    title = "OP %s - COMPLETE" % ui.code
    if len(title) + 2 > ui.cols - 4:
        title = "COMPLETE"
    box = [title, "type     : %s" % ui.scenario, "target   : %s" % ui.target,
           "duration : %02d:%02d" % (el // 60, el % 60)] + extra
    inner = min(ui.cols - 4, max(len(b) for b in box) + 2)
    pr(GREEN + "+" + "-" * inner + "+" + RST)
    for b in box:
        pr(GREEN + "|" + WHITE + (" " + b)[:inner].ljust(inner) + GREEN + "|" + RST)
        nap(0.1)
    pr(GREEN + "+" + "-" * inner + "+" + RST)
    beep("done")
    ui.footer()


# ---- small generators / banks ---------------------------------------------
def _sub():
    return random.choice(["vpn", "mail", "dev", "staging", "api", "portal", "git", "ci", "backup", "intranet", "db",
                          "files", "sso", "wiki", "grafana", "jenkins"]) + random.choice([".corp.local", ".corp.internal"])


def _user():
    return random.choice(["j.carter", "m.silva", "a.khan", "r.novak", "s.ito", "l.meyer", "t.owens", "d.park", "k.adams", "p.rossi"])


def _word(n):
    return "".join(random.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(n))


def _cnt(box, step):
    box[0] += step
    return box[0]


# ---- signature widgets (each draws a constant-height live block) ----------
def _w_spectrum(ui, seconds):
    n = max(10, min(ui.cols - 6, 48))
    vals = [random.random() for _ in range(n)]

    def fr(f):
        for i in range(n):
            vals[i] = clamp(vals[i] + random.uniform(-0.25, 0.25), 0.05, 1.0)
        lines = []
        for row in range(6, 0, -1):
            lines.append("  " + "".join((hsv(i / float(n) * 0.8) + "█") if vals[i] * 6 >= row else " " for i in range(n)) + RST)
        lines.append("%s  ch1%sch165  %d APs in range%s" % (GRAY, " " * max(1, n - 22), random.randint(6, 40), RST))
        return lines
    _live(ui, seconds, fr, 0.1)


def _w_pods(ui, seconds):
    cells = clamp((ui.cols - 9) // 2, 6, 24)
    state = [[0 for _ in range(cells)] for _ in range(4)]
    colors = {0: GREEN, 1: YELLOW, 2: RED}

    def fr(f):
        for r in state:
            for i in range(cells):
                if random.random() < 0.04:
                    r[i] = random.choice([0, 0, 0, 1, 2])
        lines = ["%snode-%02d %s%s" % (GRAY, k + 1, "".join(colors[c] + "■ " for c in r), RST) for k, r in enumerate(state)]
        flat = [c for r in state for c in r]
        lines.append("%srunning %s%d%s pending %s%d%s failed %s%d%s" % (GRAY, GREEN, flat.count(0), GRAY, YELLOW, flat.count(1), GRAY, RED, flat.count(2), RST))
        return lines
    _live(ui, seconds, fr, 0.15)


def _w_heat(ui, seconds):
    cells = clamp((ui.cols - 4) // 2, 8, 30)
    sev = [[random.choices([0, 1, 2, 3], [5, 3, 2, 1])[0] for _ in range(cells)] for _ in range(5)]
    cols = [GREEN, YELLOW, ORANGE, RED]

    def fr(f):
        cur = f % cells
        lines = []
        for r in sev:
            lines.append("  " + "".join((WHITE if i == cur else cols[v]) + "██" for i, v in enumerate(r)) + RST)
        lines.append("%s  scanned %d/%d hosts%s" % (GRAY, min(cells * 5, (f + 1) * 5), cells * 5, RST))
        return lines
    _live(ui, seconds, fr, 0.15)


def _w_regions(ui, seconds):
    regs = ["AMER", "EMEA", "APAC", "LATAM", "OCEA"]
    counts = [random.randint(100, 900) for _ in regs]
    bw = max(8, ui.cols - 22)

    def fr(f):
        lines = []
        for i, r in enumerate(regs):
            counts[i] += random.randint(0, 30)
            pct = min(100, counts[i] * 100 // max(counts) if max(counts) else 0)
            lines.append("%s%-5s %s %s%6d%s" % (CYAN, r, bar_str(pct, bw, (0.0, 0.35)), WHITE, counts[i], RST))
        lines.append("%s%d events/s | top vector: %s%s" % (GRAY, random.randint(20, 400), random.choice(["ssh", "http", "smb", "rdp"]), RST))
        return lines
    _live(ui, seconds, fr, 0.2)


def _w_devices(ui, seconds):
    devs = random.sample(["ip-camera", "thermostat", "door-ctrl", "nas", "printer", "smart-hub", "sensor-gw", "badge-reader"], 6)
    bw = max(6, ui.cols - 34)

    def fr(f):
        lines = []
        for d in devs:
            on = random.random() > 0.15
            sig = random.randint(25, 99)
            lines.append("%s%s%s %-12s %-14s %s %3d%%" % (GREEN if on else RED, "●" if on else "○", RST, d, fake_ip(), mbar(sig, bw), sig))
        return lines
    _live(ui, seconds, fr, 0.4)


def _w_gpu(ui, seconds, rows_=3):
    bw = max(8, ui.cols - 27)
    base = [random.randint(82, 98) for _ in range(rows_)]
    total = random.randint(5 * 10 ** 9, 9 * 10 ** 11)
    done = [0]

    def fr(f):
        done[0] += total // max(1, int(seconds * S.length * 8))
        pct = min(99, done[0] * 100 // total)
        lines = []
        rate = 0.0
        for g in range(rows_):
            util = clamp(base[g] + random.randint(-4, 4), 70, 100)
            r = random.uniform(2.0, 9.0)
            rate += r
            lines.append("%sGPU%d %s %3d%% %dC %4.1f GH/s%s" % (GRAY, g, mbar(util, bw), util, random.randint(62, 84), r, RST))
        lines.append("%sprogress %s %s%3d%%%s" % (GRAY, bar_str(pct, max(8, ui.cols - 20), (0.5, 0.92)), WHITE, pct, RST))
        lines.append("%stotal %s%.1f GH/s%s  %stested %s%s%s" % (GRAY, GREEN, rate, RST, GRAY, WHITE, format(done[0], ","), RST))
        lines.append("%scandidate %s%s%s" % (GRAY, PURPLE, _word(14), RST))
        return lines
    _live(ui, seconds, fr, 0.125)


OPS = ["mov", "push", "pop", "call", "xor", "cmp", "jne", "lea", "add", "sub", "test", "jmp"]
REGS = ["eax", "ebx", "ecx", "edx", "esi", "edi", "ebp", "esp"]


def _disasm(ui):
    op = random.choice(OPS)
    if op in ("call", "jne", "jmp"):
        args = "0x%06x" % random.randint(0x401000, 0x4FFFFF)
    elif op in ("push", "pop"):
        args = random.choice(REGS)
    else:
        args = "%s, %s" % (random.choice(REGS), random.choice(REGS + ["0x%x" % random.randint(0, 255), "[ebp-0x%x]" % random.randint(4, 64)]))
    col = RED if op in ("call", "jmp", "jne") else (CYAN if op in ("xor", "cmp", "test") else WHITE)
    pr("%s%06x  %s%-12s %s%-5s %s%s" % (GRAY, random.randint(0x401000, 0x4FFFFF), PURPLE, hx(8), col, op, WHITE, args[:max(5, ui.cols - 32)]))


CODE_LINES = ["def get_user(uid):", "    q = build_query(uid)", "    row = db.exec(q)", "    return render(row)",
              "if token == expected:", "    session.grant(role)", "buf = alloc(n)", "memcpy(buf, src, len)",
              "path = base + request.file", "data = open(path).read()", "for item in batch:", "    cache.put(item.id, item)",
              "resp = http.get(url)", "log.info(msg)", "return decode(blob)"]


def _codeline(ui, ctr, flag_chance=0.07):
    ctr[0] += random.randint(1, 4)
    ln = random.choice(CODE_LINES)
    if random.random() < flag_chance:
        pr("%s%4d |%s %s%s  %s<< NP-SAST-%03d%s" % (GRAY, ctr[0], RED, ln[:max(8, ui.cols - 26)], RST, RED, random.randint(1, 999), RST))
        return True
    pr("%s%4d |%s %s%s" % (GRAY, ctr[0], WHITE, ln[:ui.cols - 8], RST))
    return False


# ============================ SCENARIOS ======================================
def _sc_network(ui):
    host = fake_host()
    tgt = ui.target
    pre = ".".join(tgt.split(".")[:3])
    me = fake_ip()
    ui.set_phase(0)
    ui.log("INFO", "recon", "Target acquired: %s (%s)" % (host, tgt))
    ui.log("DATA", "recon", "AS%d | netblock %s.0/24 | hops %d" % (random.randint(1000, 64000), pre, random.randint(6, 14)))
    _prog("subdomain sweep")
    ui.stream(22, lambda: ui.log("DATA", "recon", "%-26s -> %s" % (_sub(), fake_ip()), GRAY), 0.08, 0.3)
    ui.log("OK", "recon", "%d live hosts mapped" % random.randint(8, 40), GREEN)
    ui.noise()
    ui.set_phase(1)
    ui.log("INFO", "scan", "SYN sweep %s  ports 1-65535  rate 8200 pps" % tgt)
    _prog("port sweep")
    svc = sorted(random.sample(SVC_BANK, 6))
    ui.raw("PORT     STATE  SERVICE     VERSION", GRAY)
    for p, name, ver in svc:
        pr(CYAN + ("%d/tcp" % p).ljust(9) + GREEN + "open".ljust(7) + YELLOW + name.ljust(12) + WHITE + ver[:max(0, ui.cols - 30)] + RST)
        nap(0.1)
    ui.stream(20, lambda: ui.log("DATA", "scan", "%s:%-5d %-9s rtt %dms" % (tgt, random.choice([21, 22, 80, 443, 3306, 8080]),
              random.choice(["open", "closed", "filtered"]), random.randint(1, 90)), GRAY), 0.05, 0.2)
    ui.log("ALERT", "vuln", "NP-2026-%04d CRITICAL CVSS 9.8 Unauthenticated deserialization" % random.randint(100, 9999), RED)
    ui.set_phase(2)
    mod, desc = random.choice(EXPLOITS)
    port = random.choice([p for p, _, _ in svc])
    ui.shell("%sphantom%s>%s" % (RED, WHITE, RST), "use exploit/phantom/%s" % mod)
    ui.shell("%sphantom%s>%s" % (RED, WHITE, RST), "show options", ["  RHOSTS    %s" % tgt, "  RPORT     %d" % port, "  LHOST     %s" % me, "  PAYLOAD   phantom/shell_reverse_tcp"])
    ui.shell("%sphantom%s>%s" % (RED, WHITE, RST), "run")
    for n in (1, 2, 3):
        ui.log("INFO", "exploit", "Sending stage %d/3 to %s:%d" % (n, tgt, port))
        _prog("stage %d upload" % n, 2, 5)
    ui.stream(14, lambda: ui.hexdump(1), 0.05, 0.15)
    ui.sessions += 1
    ui.log("OK", "exploit", "Session %d opened (%s -> %s:%d)" % (ui.sessions, me, tgt, port), GREEN + BOLD, 0.4)
    ui.set_phase(3)
    prm = "%swww-data@%s%s:%s/var/www%s$%s" % (GREEN, host.split(".")[0], WHITE, PURPLE, RED, RST)
    ui.shell(prm, "id", ["uid=33(www-data) gid=33(www-data) groups=33(www-data)"])
    ui.shell(prm, "uname -a", ["Linux %s 5.15.0-91-generic #101-Ubuntu SMP x86_64" % host.split(".")[0]])
    ui.stream(14, lambda: ui.log("DATA", "privesc", "checking %s" % random.choice(["SUID /usr/bin/%s" % _word(5), "cron job %s" % _word(6), "writable /etc/%s.d" % _word(4), "kernel module %s" % _word(5)]), GRAY), 0.1, 0.35)
    ui.log("WARN", "privesc", "Escalation vector NP-2026-%04d: writable service unit" % random.randint(100, 9999), YELLOW)
    _prog("escalating", 3, 6)
    ui.shell("%sroot@%s%s:%s/root%s#%s" % (RED, host.split(".")[0], WHITE, PURPLE, RED, RST), "id", ["uid=0(root) gid=0(root) groups=0(root)"])
    ui.log("OK", "privesc", "ROOT ACCESS CONFIRMED", GREEN + BOLD, 0.4)
    ui.set_phase(4)
    ui.log("INFO", "persist", "Registering service unit phantomd.service")
    ui.log("INFO", "persist", "Beacon every %d min, jitter %d%%" % (random.choice([5, 10, 15]), random.randint(10, 40)))
    _prog("implant deploy")
    ui.sessions += 1
    ui.log("OK", "persist", "Beacon check-in: session %d (id %s)" % (ui.sessions, hx(8)), GREEN)
    ui.set_phase(5)
    picks = random.sample(FILES, 5)
    for nm, mb in picks:
        ui.raw("%-9d /srv/data/%s" % (mb, nm), CYAN, 0.1)
    tot = [0.0]
    ui.stream(28, lambda: ui.log("DATA", "exfil", "chunk %s  %s  %.1f MB/s  total %s" % (hx(6), human_size(random.uniform(8, 64)), random.uniform(6, 48), human_size(_cnt(tot, random.uniform(8, 64)))), GRAY), 0.1, 0.35)
    ui.log("OK", "exfil", "Transfer complete: %s sha256 %s" % (human_size(tot[0]), hx(24)), GREEN + BOLD)
    ui.set_phase(6)
    ui.log("INFO", "cleanup", "Truncating auth/syslog entries for session window")
    ui.stream(10, lambda: ui.log("DATA", "cleanup", "removed artifact /tmp/.%s" % _word(8), GRAY), 0.15, 0.4)
    _prog("trace removal")
    ui.log("OK", "cleanup", "Residual footprint %.1f%%" % random.uniform(0.1, 1.9), GREEN)
    _summary(ui, ["sessions : %d" % ui.sessions, "data     : %s" % human_size(tot[0])])


def _sc_web(ui):
    host = "portal.corp.local"
    ui.set_phase(0)
    ui.log("INFO", "crawl", "Spidering https://%s/  depth 6  threads 16" % host)
    paths = ["/login", "/admin", "/api/v2/users", "/api/v2/orders", "/upload", "/reset", "/static/app.js", "/export", "/graphql", "/health", "/backup", "/search"]
    ui.stream(28, lambda: ui.log("DATA", "http", "%s %-26s %d  %3dms" % (random.choice(["GET ", "GET ", "POST"]), random.choice(paths) + ("?id=%d" % random.randint(1, 999) if random.random() < .4 else ""),
              random.choice([200, 200, 200, 301, 302, 403, 404]), random.randint(8, 420)), GRAY), 0.04, 0.18)
    ui.log("WARN", "crawl", "Directory listing enabled on /backup/", YELLOW)
    ui.set_phase(1)
    ui.log("INFO", "fuzz", "Mutating %d parameters across %d endpoints" % (random.randint(60, 180), len(paths)))
    _prog("parameter fuzzing")
    ui.stream(24, lambda: ui.log(random.choice(["DATA", "DATA", "WARN"]), "fuzz", "param=%s len=%-4d -> %d %s" % (random.choice(["q", "id", "file", "sort", "token"]), random.randint(1, 4000), random.choice([200, 200, 400, 500]), random.choice(["ok", "reflected", "error-leak", "ok"])), GRAY), 0.04, 0.2)
    ui.set_phase(2)
    ui.log("INFO", "inject", "Boolean/timing probes on parameter 'id'")
    ui.stream(22, lambda: ui.log(random.choice(["DATA", "DATA", "OK"]), "inject", "probe %-3d delta %5.2fs  %s" % (random.randint(1, 400), random.uniform(0, 5.2), random.choice(["no diff", "diff", "diff", "timing hit"])), GRAY), 0.06, 0.25)
    ui.log("ALERT", "inject", "Parameter 'id' injectable [boolean-based] DBMS: MySQL 5.7", RED)
    ui.raw("TABLE          ROWS", GRAY)
    for t in random.sample(["users", "orders", "sessions", "payments", "audit_log", "api_tokens"], 4):
        ui.raw("%-14s %s" % (t, format(random.randint(300, 900000), ",")), CYAN, 0.12)
    ui.set_phase(3)
    ui.log("INFO", "auth", "Recovering session signing material")
    _prog("key recovery")
    ui.shell("%sweb%s>%s" % (RED, WHITE, RST), "GET /admin", ["HTTP/1.1 200 OK", "x-role: superadmin"])
    ui.log("OK", "auth", "Administrator access granted", GREEN + BOLD)
    ui.set_phase(4)
    ui.log("INFO", "shell", "Uploading stager via /upload")
    _prog("upload", 3, 6)
    ui.stream(10, lambda: ui.hexdump(1), 0.05, 0.15)
    ui.sessions += 1
    ui.log("OK", "shell", "Callback received - session %d" % ui.sessions, GREEN + BOLD)
    ui.set_phase(5)
    n = random.randint(20000, 900000)
    ctr = [0]
    ui.stream(30, lambda: ui.log("DATA", "dump", "row %-8d | %-9s | %s" % (_cnt(ctr, random.randint(40, 400)), _user(), hx(24)), GRAY), 0.05, 0.2)
    ui.log("OK", "dump", "Extraction complete: %s rows" % format(n, ","), GREEN + BOLD)
    _summary(ui, ["records  : %s" % format(n, ","), "sessions : %d" % ui.sessions])


def _sc_wifi(ui):
    ui.set_phase(0)
    ui.log("INFO", "radio", "Monitor mode on wlan0mon, hopping channels 1-165")
    _w_spectrum(ui, 28)
    ui.raw("BSSID              CH  PWR ENC   SSID", GRAY)
    names = random.sample(["CorpGuest", "HQ-Secure", "Lobby-WiFi", "Staff_5G", "Conf-Room-AP", "IoT-Net", "Dev-Lab", "Cafe-Free"], 6)
    rows = [(fake_mac(), random.choice([1, 6, 11, 36, 40, 149]), -random.randint(30, 88), random.choice(["WPA2", "WPA2", "WPA3", "OPEN"]), n) for n in names]
    for r in rows:
        ui.raw("%s  %-3d %-4d %-5s %s" % r, CYAN, 0.12)
    tgt = random.choice([r for r in rows if r[3] != "OPEN"] or rows)
    ui.set_phase(1)
    ui.log("INFO", "radio", "Locking onto %s (%s) ch %d" % (tgt[4], tgt[0], tgt[1]))
    ui.stream(18, lambda: ui.log("DATA", "radio", "client %s  %d dBm  %d fps" % (fake_mac(), -random.randint(35, 85), random.randint(5, 400)), GRAY), 0.1, 0.3)
    ui.set_phase(2)
    ui.log("INFO", "capture", "Waiting for authentication exchange")
    for i in range(1, 5):
        _prog("EAPOL frame %d/4" % i, 3, 6)
    ui.log("OK", "capture", "Handshake captured (PMKID %s)" % hx(16), GREEN + BOLD)
    ui.set_phase(3)
    ui.log("INFO", "crack", "Offline attack: wordlist + rules")
    _w_gpu(ui, 40, 2)
    ui.log("OK", "crack", "KEY FOUND [ %s ]" % fake_password(), GREEN + BOLD, 0.4)
    ui.set_phase(4)
    ui.log("INFO", "access", "Associating with %s" % tgt[4])
    _prog("association")
    ip = "192.168.%d.%d" % (random.randint(0, 50), random.randint(20, 240))
    ui.log("OK", "access", "DHCP lease %s" % ip, GREEN)
    ui.stream(20, lambda: ui.log("DATA", "map", "%-15s %s  %s" % ("192.168.%s.%d" % (ip.split(".")[2], random.randint(2, 250)), fake_mac(), random.choice(["up", "up", "filtered"])), GRAY), 0.1, 0.3)
    _summary(ui, ["network  : %s" % tgt[4], "hosts    : %d" % random.randint(8, 60)])


def _sc_ad(ui):
    ui.set_phase(0)
    ui.log("INFO", "ldap", "Enumerating domain CORP.LOCAL")
    _prog("directory query")
    ous = ["Users", "Servers", "Workstations", "Service Accounts", "Finance", "Engineering", "IT-Admins", "HR"]
    k = [0]

    def tree():
        k[0] += 1
        ou = random.choice(ous)
        pr("%s%s %s%s%s (%d objects)" % (GRAY, "├── " if k[0] % 4 else "└── ", GREEN, ou, GRAY, random.randint(3, 400)) + RST)
        if random.random() < .6:
            pr("%s│   %s%s %s%s" % (GRAY, "├─ " if random.random() < .7 else "└─ ", CYAN, _user(), RST))
    pr(GREEN + "CORP.LOCAL" + RST)
    ui.stream(24, tree, 0.1, 0.35)
    ui.log("WARN", "ldap", "Service accounts with weak encryption: svc_sql, svc_backup", YELLOW)
    ui.set_phase(1)
    ui.log("INFO", "ticket", "Requesting service tickets for %d accounts" % random.randint(2, 6))
    ui.stream(16, lambda: ui.log("DATA", "ticket", "ticket svc_%s  enc=rc4  %s" % (random.choice(["sql", "backup", "web", "ci"]), hx(20)), GRAY), 0.15, 0.4)
    _prog("ticket cracking", 5, 9)
    ui.log("OK", "ticket", "Credential recovered: svc_backup", GREEN + BOLD)
    ui.set_phase(2)
    hops = ["WKS-%02d" % random.randint(1, 99) for _ in range(5)]
    for a, b in zip(hops, hops[1:]):
        ui.log("INFO", "lateral", "%s  ──▶  %s   (admin share reachable)" % (a, b), CYAN, 0.7)
        ui.stream(6, lambda: ui.log("DATA", "lateral", "token cache %s  %s" % (_user(), hx(10)), GRAY), 0.2, 0.5)
    ui.log("WARN", "lateral", "Privileged logon found: adm_it (Domain Admins)", YELLOW)
    ui.set_phase(3)
    ui.log("INFO", "domain", "Impersonating adm_it")
    _prog("privilege check")
    ui.log("OK", "domain", "Domain Admins / Enterprise Admins confirmed", GREEN + BOLD)
    ui.set_phase(4)
    n = random.randint(500, 9000)
    ctr = [0]
    ui.stream(26, lambda: ui.log("DATA", "sync", "replicated %-6d  %-14s %s" % (_cnt(ctr, random.randint(5, 60)), random.choice(["krbtgt", "Administrator", _user(), "svc_sql"]), hx(16)), GRAY), 0.08, 0.3)
    ui.log("OK", "sync", "Domain compromise complete (%s objects)" % format(n, ","), GREEN + BOLD)
    _summary(ui, ["objects  : %s" % format(n, ","), "domain   : CORP.LOCAL"])


def _sc_cloud(ui):
    ui.set_phase(0)
    ui.log("INFO", "recon", "Discovering public cloud assets for corp-prod")
    ui.stream(22, lambda: ui.log("DATA", "assets", "%-26s %-12s %s" % (random.choice(["corp-backup-prod", "corp-assets-cdn", "corp-logs-archive", "corp-dev-staging"]) + "-" + _word(3),
              random.choice(["storage", "compute", "function", "queue"]), random.choice(["private", "private", "public-read", "auth-only"])), GRAY), 0.1, 0.35)
    ui.log("WARN", "recon", "Access key leaked in repo history (id NPK-%s)" % hx(6).upper(), YELLOW)
    ui.set_phase(1)
    ui.log("INFO", "iam", "Validating leaked credentials")
    _prog("credential check")
    ui.log("OK", "iam", "Identity dev-ci-bot (3 policies)", GREEN)
    ui.stream(20, lambda: ui.log("DATA", "iam", "%-14s ──▶ %-14s trust: %s" % (random.choice(["dev-ci-bot", "ci-deploy", "build-agent"]), random.choice(["ci-deploy", "infra-admin", "read-only", "db-ops"]), random.choice(["allow", "allow", "deny"])), GRAY), 0.15, 0.4)
    ui.set_phase(2)
    ui.log("INFO", "privesc", "Chain: dev-ci-bot ▶ ci-deploy ▶ infra-admin")
    for r in ("ci-deploy", "infra-admin"):
        _prog("assume %s" % r, 3, 6)
        ui.log("OK", "privesc", "Assumed role %s" % r, GREEN)
    ui.log("ALERT", "privesc", "Administrator-equivalent permissions obtained", RED + BOLD)
    ui.set_phase(3)
    tot = [0.0]
    ui.stream(22, lambda: ui.log("DATA", "storage", "%-22s %s" % (random.choice(FILES)[0], human_size(random.uniform(10, 2000))), GRAY), 0.1, 0.35)
    ui.set_phase(4)
    ui.stream(30, lambda: ui.log("DATA", "sync", "part-%04d  %s  %.1f MB/s" % (random.randint(1, 9999), human_size(_cnt(tot, random.uniform(40, 300))), random.uniform(20, 120)), GRAY), 0.1, 0.3)
    ui.log("OK", "sync", "Transfer verified sha256 %s" % hx(24), GREEN + BOLD)
    _summary(ui, ["data     : %s" % human_size(tot[0]), "roles    : 3"])


def _sc_iot(ui):
    ui.set_phase(0)
    ui.log("INFO", "disc", "Sweeping 10.%d.0.0/16 for embedded devices" % random.randint(0, 255))
    _w_devices(ui, 28)
    ui.set_phase(1)
    ui.log("INFO", "finger", "Profiling device banners")
    ui.stream(18, lambda: ui.log("DATA", "finger", "%s  %-10s fw %d.%d.%d  %s" % (fake_ip(), random.choice(["Axion", "Nexa", "Gatewell", "Storix", "Homio"]), random.randint(1, 6), random.randint(0, 9), random.randint(0, 20), random.choice(["outdated", "current", "outdated"])), GRAY), 0.15, 0.4)
    ui.log("WARN", "finger", "Management interface exposed on 8080", YELLOW)
    ui.set_phase(2)
    ui.log("INFO", "access", "Testing vendor default credentials")
    ui.stream(16, lambda: ui.log("DATA", "access", "%s  try %-8s %s" % (fake_ip(), random.choice(["admin", "root", "user", "guest"]), random.choice(["denied", "denied", "denied", "ACCEPTED"])), GRAY), 0.15, 0.4)
    _prog("firmware dump", 4, 8)
    ui.sessions += 1
    ui.log("OK", "access", "Device shell opened - session %d" % ui.sessions, GREEN + BOLD)
    ui.set_phase(3)
    ui.log("INFO", "ctrl", "Establishing persistent control channel")
    ui.stream(20, lambda: ui.log("DATA", "ctrl", "heartbeat %s  rtt %dms" % (fake_ip(), random.randint(8, 250)), GRAY), 0.3, 0.7)
    _summary(ui, ["devices  : %d" % random.randint(6, 40), "sessions : %d" % ui.sessions])


def _sc_db(ui):
    ui.set_phase(0)
    ui.log("INFO", "probe", "Probing %s:3306" % ui.target)
    ui.stream(14, lambda: ui.log("DATA", "probe", "handshake variant %-3d -> %s" % (random.randint(1, 200), random.choice(["accepted", "reset", "tls-required"])), GRAY), 0.1, 0.3)
    ui.log("WARN", "probe", "MySQL 5.7.38 - remote root login not host-restricted", YELLOW)
    ui.set_phase(1)
    ui.log("INFO", "auth", "Credential attack against dbadmin")
    ui.stream(22, lambda: ui.log("DATA", "auth", "attempt %-6d  %s" % (random.randint(1, 99999), random.choice(["fail", "fail", "fail", "fail", "lockout-avoided"])), GRAY), 0.05, 0.2)
    ui.log("OK", "auth", "Authenticated as dbadmin", GREEN + BOLD)
    ui.set_phase(2)
    pr_ = "%smysql%s>%s" % (CYAN, WHITE, RST)
    ui.shell(pr_, "SHOW DATABASES;", ["+--------------------+", "| Database           |", "+--------------------+", "| corp_prod          |", "| corp_hr            |", "| billing            |", "+--------------------+"])
    cnt = random.randint(20000, 900000)
    ui.shell(pr_, "SELECT COUNT(*) FROM corp_prod.users;", ["+----------+", "| %-8d |" % cnt, "+----------+"])
    ui.set_phase(3)
    tot = 0.0
    for t in random.sample(["users", "orders", "payments", "audit_log", "sessions"], 4):
        mb = random.uniform(20, 1800)
        tot += mb
        _prog("%-9s %s" % (t, human_size(mb)), 4, 8)
        ui.stream(8, lambda: ui.log("DATA", "dump", "%s rows  %s" % (random.randint(1000, 9000), hx(12)), GRAY), 0.05, 0.2)
    ui.log("OK", "dump", "Dump complete: %s" % human_size(tot), GREEN + BOLD)
    _summary(ui, ["data     : %s" % human_size(tot)])


def _sc_crack(ui):
    ui.set_phase(0)
    algo = random.choice(["SHA256", "SHA512-crypt", "bcrypt", "NTLM", "MD5"])
    n = random.randint(800, 120000)
    ui.log("INFO", "load", "Loading %s hashes (%s)" % (format(n, ","), algo))
    _prog("building keyspace")
    ui.set_phase(1)
    _w_gpu(ui, 70, 3)
    ui.set_phase(2)
    rec = random.randint(max(1, n // 40), max(2, n // 6))
    ui.log("OK", "result", "Recovered %s/%s hashes (%.1f%%)" % (format(rec, ","), format(n, ","), rec * 100.0 / n), GREEN + BOLD)
    ui.stream(10, lambda: ui.raw("%s  %s" % (hx(16), fake_password()), PURPLE, 0.0), 0.2, 0.5)
    _summary(ui, ["algorithm: %s" % algo, "recovered: %s" % format(rec, ",")])


def _sc_soc(ui):
    ui.set_phase(0)
    ui.log("ALERT", "siem", "Rule NP-SOC-%d fired: anomalous outbound volume" % random.randint(1000, 9999), RED)
    ui.stream(24, lambda: ui.log(random.choice(["DATA", "DATA", "WARN"]), "siem", "event %-7d src %-15s %s" % (random.randint(1, 999999), fake_ip(), random.choice(["login ok", "login fail", "dns query", "file write", "outbound 443"])), GRAY), 0.06, 0.25)
    ui.set_phase(1)
    ui.log("WARN", "triage", "Severity HIGH | hosts %d | accounts %d" % (random.randint(1, 5), random.randint(1, 4)), YELLOW)
    ui.raw("INDICATOR                         TYPE", GRAY)
    ui.raw("%-33s ip" % fake_ip(), CYAN)
    ui.raw("%-33s sha256" % hx(24), CYAN)
    _w_regions(ui, 18)
    ui.set_phase(2)
    for m in ["Isolating host via network access control", "Blocking indicators on perimeter firewall", "Revoking %d active sessions" % random.randint(2, 9)]:
        ui.log("INFO", "contain", m)
        _prog("containment", 3, 6)
    ui.set_phase(3)
    ui.stream(18, lambda: ui.log("DATA", "erad", "removed %s" % random.choice(["scheduled task NP-%s" % _word(4), "service %s" % _word(6), "autorun key %s" % hx(6)]), GRAY), 0.15, 0.4)
    ui.set_phase(4)
    ui.log("INFO", "recover", "Restoring services from verified snapshot")
    _prog("restore", 5, 9)
    ui.log("OK", "recover", "Validation scan clean - incident closed", GREEN + BOLD)
    _summary(ui, ["severity : HIGH", "mttr     : %d min" % random.randint(12, 90)])


def _sc_forensics(ui):
    ui.set_phase(0)
    gb = random.choice([128, 256, 512, 1024])
    ui.log("INFO", "acquire", "Write-blocker engaged; imaging %d GB -> case-%s.dd" % (gb, hx(4).upper()))
    ctr = [0]
    ui.stream(30, lambda: ui.log("DATA", "image", "sector %-10d  %s  crc ok" % (_cnt(ctr, random.randint(20000, 90000)), hx(12)), GRAY), 0.08, 0.25)
    ui.log("OK", "acquire", "SHA256 verified %s" % hx(32), GREEN)
    ui.set_phase(1)
    ui.log("INFO", "carve", "Carving unallocated space (signature scan)")
    ui.stream(22, lambda: ui.hexdump(1), 0.08, 0.25)
    ui.raw("OFFSET        TYPE      SIZE", GRAY)
    for t in random.sample(["zip", "sqlite", "pdf", "jpg", "docx", "exe", "log"], 5):
        ui.raw("0x%08x  %-8s  %s" % (random.randint(0, 0xFFFFFFF), t, human_size(random.uniform(0.1, 400))), CYAN, 0.1)
    ui.set_phase(2)
    day = time.strftime("%Y-%m-%d")
    evs = ["first suspicious logon", "archive created in temp folder", "outbound transfer started", "service installed", "log entries removed", "session closed"]
    for i, e in enumerate(evs):
        ui.raw("%s %02d:%02d:%02d  %s" % (day, 1 + i * 2, random.randint(0, 59), random.randint(0, 59), e), PURPLE if i % 2 else CYAN, 0.5)
        ui.stream(4, lambda: ui.log("DATA", "tl", "artifact %s  %s" % (hx(8), random.choice(["registry", "prefetch", "event log", "browser"])), GRAY), 0.15, 0.4)
    ui.set_phase(3)
    _prog("attribution", 5, 9)
    ui.log("WARN", "attrib", "Overlap %d%% with group %s-%d" % (random.randint(55, 93), random.choice(["TA", "UNC", "FIN"]), random.randint(100, 999)), YELLOW)
    ui.set_phase(4)
    _prog("report build", 4, 8)
    ui.log("OK", "report", "report-%s.pdf sealed sha256 %s" % (hx(4), hx(16)), GREEN + BOLD)
    _summary(ui, ["image    : %d GB" % gb])


def _sc_malware(ui):
    ui.set_phase(0)
    sz = random.randint(80, 4200)
    ui.log("INFO", "sample", "Sample %s.bin (%d KB) sha256 %s" % (hx(6), sz, hx(24)))
    _prog("cell setup")
    ui.set_phase(1)
    ui.log("INFO", "static", "Entropy %.2f | packer: %s" % (random.uniform(6.2, 7.9), random.choice(["custom stub", "UPX-like", "none"])))
    ui.stream(30, lambda: _disasm(ui), 0.06, 0.2)
    ui.log("WARN", "static", "%d network imports, %d crypto routines" % (random.randint(3, 14), random.randint(1, 6)), YELLOW)
    ui.set_phase(2)
    ui.log("INFO", "dynamic", "Detonating in instrumented VM")
    ui.stream(30, lambda: ui.log(random.choice(["DATA", "WARN", "ALERT"]), "trace", random.choice(
        ["writes autorun location", "spawns child process", "connect relay-%s:443" % hx(3), "modifies scheduled task", "reads credential store", "creates mutex %s" % hx(6)]), None), 0.15, 0.5)
    ui.set_phase(3)
    score = random.randint(78, 99)
    ui.log("ALERT", "verdict", "MALICIOUS confidence %d/100" % score, RED + BOLD, 0.4)
    ui.log("INFO", "verdict", "Detection rule NP_RULE_%s generated" % hx(4).upper())
    ui.raw("IOC                               TYPE", GRAY)
    ui.raw("%-33s ip" % fake_ip(), CYAN)
    ui.raw("%-33s domain" % ("relay-%s.example-net.org" % hx(3)), CYAN)
    _summary(ui, ["verdict  : MALICIOUS (%d/100)" % score])


def _sc_intel(ui):
    ui.set_phase(0)
    ui.log("INFO", "feed", "Connecting to %d intelligence feeds" % random.randint(8, 20))
    ui.stream(22, lambda: ui.log("DATA", "feed", "%-14s +%-5d indicators  (%s)" % (random.choice(["osint-feed", "vendor-a", "isac-share", "honeynet", "gov-cert"]), random.randint(10, 4000), random.choice(["ip", "domain", "hash", "url"])), GRAY), 0.1, 0.35)
    ui.set_phase(1)
    _w_regions(ui, 24)
    ui.log("WARN", "corr", "%d internal hosts matched known malicious infrastructure" % random.randint(1, 9), YELLOW)
    ui.set_phase(2)
    ui.raw("INDICATOR         REPUTATION  LAST SEEN", GRAY)
    ui.stream(22, lambda: ui.raw("%-17s %-11s %dh ago" % (fake_ip(), random.choice(["malicious", "suspicious"]), random.randint(1, 72)), random.choice([RED, YELLOW]), 0.0), 0.15, 0.45)
    ui.set_phase(3)
    ui.log("ALERT", "alert", "Advisory ADV-2026-%04d published to SOC channel" % random.randint(100, 9999), RED + BOLD)
    _prog("blocklist push", 4, 8)
    ui.log("OK", "alert", "Blocklist pushed to %d enforcement points" % random.randint(4, 40), GREEN)
    _summary(ui, ["advisories: 1"])


def _sc_honeypot(ui):
    ui.set_phase(0)
    ui.log("INFO", "deploy", "Deploying %d decoy hosts (ssh, web, db)" % random.randint(3, 9))
    _prog("decoy rollout")
    ui.set_phase(1)
    ui.log("INFO", "lure", "Waiting for inbound probes")
    _w_regions(ui, 24)
    ui.set_phase(2)
    ui.stream(34, lambda: ui.log(random.choice(["WARN", "WARN", "ALERT"]), "capture", "%-15s %-6s login as '%s'" % (fake_ip(), random.choice(["ssh", "ftp", "mysql", "rdp"]), random.choice(["root", "admin", "oracle", "test", "postgres"])), None), 0.15, 0.5)
    ui.log("ALERT", "observe", "Interactive session from %s - recording" % fake_ip(), RED)
    for c in ["uname -a", "cat /etc/passwd", "wget payload", "history -c"]:
        ui.log("CMD", "session", "attacker> %s" % c, PURPLE, 0.8)
    ui.set_phase(3)
    _prog("campaign clustering", 5, 9)
    ui.log("OK", "analyze", "Blocklist updated with %d addresses" % random.randint(20, 400), GREEN)
    _summary(ui, ["sessions : %d" % random.randint(80, 900)])


def _sc_pcap(ui):
    ui.set_phase(0)
    ui.log("INFO", "capture", "Capturing on eth0, snaplen 65535")
    ui.raw("NO      SRC              DST              PROTO LEN", GRAY)
    ctr = [0]
    pc = {"TCP": CYAN, "TLS": GREEN, "DNS": YELLOW, "UDP": PURPLE, "HTTP": WHITE}

    def pkt():
        p = random.choice(list(pc))
        pr("%s%-7d %-16s %-16s %-5s %d" % (pc[p], _cnt(ctr, 1), fake_ip(), fake_ip(), p, random.randint(60, 1514)))
    ui.stream(34, pkt, 0.02, 0.09)
    ui.set_phase(1)
    ui.stream(20, lambda: ui.log("DATA", "dissect", "frame %-7d %s seq=%d ack=%d win=%d" % (random.randint(1, ctr[0] + 1), random.choice(["TCP", "TLS", "HTTP"]), random.randint(1, 10 ** 8), random.randint(1, 10 ** 8), random.randint(500, 65535)), GRAY), 0.05, 0.2)
    ui.set_phase(2)
    _prog("stream reassembly", 4, 8)
    ui.stream(14, lambda: ui.log("DATA", "streams", "stream %-4d %s -> %s  %s" % (random.randint(1, 600), fake_ip(), fake_ip(), human_size(random.uniform(0.1, 90))), GRAY), 0.1, 0.3)
    ui.set_phase(3)
    ui.log("WARN", "flags", "Periodic beaconing: %s every %d s" % (fake_ip(), random.choice([30, 60, 300])), YELLOW)
    ui.log("WARN", "flags", "Long DNS names to x%s.example-net.org (possible tunnelling)" % hx(3), YELLOW)
    ui.log("ALERT", "flags", "Cleartext credentials on port 21", RED)
    _summary(ui, ["packets  : %s" % format(ctr[0] * 37, ",")])


def _sc_fuzz(ui):
    ui.set_phase(0)
    ui.log("INFO", "target", "Instrumenting parser binary (coverage-guided)")
    _prog("instrumentation")
    ui.set_phase(1)
    st = {"execs": 0, "paths": 120, "crash": 0}
    bw = max(8, ui.cols - 22)

    def fr(f):
        st["execs"] += random.randint(80000, 220000)
        st["paths"] += random.randint(0, 9)
        if random.random() < 0.05:
            st["crash"] += 1
        cov = min(100, 30 + f // 4)
        return ["%sexecs %s%s%s %s%d/s%s" % (GRAY, WHITE, format(st["execs"], ","), RST, GREEN, random.randint(4000, 9000), RST),
                "%spaths %s%d%s  %scrashes %s%d%s" % (GRAY, WHITE, st["paths"], RST, GRAY, RED if st["crash"] else GREEN, st["crash"], RST),
                "%scoverage %s %s%3d%%%s" % (GRAY, bar_str(cov, bw, (0.25, 0.55)), WHITE, cov, RST),
                "%sinput %s%s%s" % (GRAY, PURPLE, hx(18), RST)]
    _live(ui, 60, fr, 0.1)
    ui.set_phase(2)
    c = max(st["crash"], 3)
    ui.log("ALERT", "crash", "%d unique crashes recorded" % c, RED)
    ui.set_phase(3)
    for i in range(c):
        ui.log("DATA", "triage", "crash_%d SIGSEGV site 0x%08x class: %s" % (i + 1, random.randint(0x400000, 0x7FFFFFF), random.choice(["heap overflow", "null deref", "use-after-free"])), GRAY, 0.5)
        _prog("minimising %d" % (i + 1), 3, 6)
    ui.log("OK", "triage", "Test cases saved; report drafted for vendor", GREEN)
    _summary(ui, ["executions: %s" % format(st["execs"], ","), "crashes  : %d" % c])


def _sc_api(ui):
    ui.set_phase(0)
    ui.log("INFO", "discover", "Importing schema, probing for undocumented routes")
    routes = ["/v2/users/{id}", "/v2/orders/{id}", "/v2/export", "/v1/admin/stats", "/v2/tokens", "/internal/debug"]
    ui.stream(24, lambda: ui.log("DATA", "route", "%s %-20s %d" % (random.choice(["GET ", "POST", "PUT ", "DEL "]), random.choice(routes), random.choice([200, 401, 403, 404, 200])), GRAY), 0.08, 0.25)
    ui.set_phase(1)
    ui.log("INFO", "authz", "Testing object/function-level authorisation")
    ui.stream(24, lambda: ui.log(random.choice(["DATA", "DATA", "WARN"]), "authz", "user_%04d -> /v2/orders/%d  %s" % (random.randint(1, 9999), random.randint(1, 99999), random.choice(["403", "403", "200 (!)"])), GRAY), 0.08, 0.25)
    ui.log("ALERT", "authz", "Broken object-level authorisation on /v2/orders/{id}", RED)
    ui.set_phase(2)
    ui.stream(18, lambda: ui.log("DATA", "limits", "burst %-4d req/s  -> %s" % (random.choice([50, 100, 250, 500]), random.choice(["200 x%d" % random.randint(50, 500), "429 throttled", "200 (no limit)"])), GRAY), 0.1, 0.3)
    ui.log("WARN", "limits", "No throttling on /v2/tokens", YELLOW)
    ui.set_phase(3)
    _prog("report", 4, 8)
    ui.log("OK", "report", "api-audit-%s.pdf generated" % hx(4), GREEN)
    _summary(ui, ["routes   : %d" % random.randint(30, 160)])


def _sc_k8s(ui):
    ui.set_phase(0)
    ui.log("INFO", "enum", "Connecting to cluster prod-%s" % hx(3))
    _w_pods(ui, 30)
    ui.set_phase(1)
    ui.raw("IMAGE                  CRIT HIGH", GRAY)
    ui.stream(24, lambda: ui.raw("%-22s %-4d %d" % (random.choice(["api-gateway", "auth-svc", "billing", "frontend", "worker", "cache"]) + ":" + str(random.randint(1, 5)) + "." + str(random.randint(0, 9)), random.randint(0, 6), random.randint(0, 20)), random.choice([YELLOW, WHITE, ORANGE]), 0.0), 0.2, 0.5)
    ui.set_phase(2)
    ui.log("WARN", "rbac", "Service account 'ci-runner' bound to cluster-admin", YELLOW)
    ui.log("WARN", "rbac", "%d pods running privileged" % random.randint(1, 8), YELLOW)
    ui.log("ALERT", "rbac", "Secrets unencrypted in namespace 'payments'", RED)
    _w_pods(ui, 14)
    ui.set_phase(3)
    _prog("benchmark mapping", 4, 8)
    ui.log("OK", "report", "Score %d/100 - remediation plan exported" % random.randint(38, 72), GREEN)
    _summary(ui, ["score    : %d/100" % random.randint(38, 72)])


def _sc_mobile(ui):
    ui.set_phase(0)
    ui.log("INFO", "unpack", "Unpacking app package (%d MB)" % random.randint(18, 140))
    _prog("unpack")
    ui.stream(14, lambda: ui.log("DATA", "unpack", "%s  %s" % (random.choice(["classes.dex", "resources.arsc", "lib/arm64/lib%s.so" % _word(4), "assets/%s.json" % _word(5)]), human_size(random.uniform(0.01, 12))), GRAY), 0.1, 0.3)
    ui.set_phase(1)
    ui.stream(26, lambda: ui.log(random.choice(["DATA", "DATA", "WARN"]), "static", random.choice(["permission %s" % random.choice(["CAMERA", "LOCATION", "STORAGE", "CONTACTS"]), "exported component %s" % _word(6), "hard-coded endpoint https://%s" % _sub(), "library %s v%d.%d" % (_word(5), random.randint(1, 9), random.randint(0, 9))]), None), 0.1, 0.35)
    ui.log("WARN", "static", "Backup flag enabled; debuggable build detected", YELLOW)
    ui.set_phase(2)
    ui.log("INFO", "runtime", "Instrumented run, proxying app traffic")
    ui.stream(26, lambda: ui.log("DATA", "traffic", "%s https://%s/%s  %d" % (random.choice(["GET", "POST"]), _sub(), _word(6), random.choice([200, 200, 401, 204])), GRAY), 0.08, 0.3)
    ui.log("ALERT", "runtime", "Session token stored in plaintext preferences", RED)
    ui.set_phase(3)
    _prog("report", 4, 8)
    ui.log("OK", "report", "Mobile security report ready", GREEN)
    _summary(ui, ["findings : %d" % random.randint(5, 14)])


def _sc_mail(ui):
    dom = "corp.local"
    ui.set_phase(0)
    ui.log("INFO", "dns", "Querying mail records for %s" % dom)
    checks = [("MX  mx1.%s prio 10" % dom, True), ("SPF  v=spf1 ... ~all", False), ("DKIM selector s1 (1024-bit)", False),
              ("DMARC  p=none", False), ("MTA-STS policy", False), ("TLS-RPT record", True), ("BIMI record", True)]
    for t, ok in checks:
        pr("  %s%s%s %s" % (GREEN if ok else RED, "✔" if ok else "✘", RST, t))
        nap(0.9)
    ui.stream(14, lambda: ui.log("DATA", "dns", "query %-28s %dms" % (random.choice(["_dmarc.", "s1._domainkey.", "_mta-sts.", ""]) + dom, random.randint(4, 90)), GRAY), 0.15, 0.4)
    ui.set_phase(1)
    ui.log("WARN", "policy", "DMARC 'none' - spoofed mail would be delivered", YELLOW)
    ui.log("WARN", "policy", "SPF soft-fail (~all); DKIM key length weak", YELLOW)
    ui.stream(18, lambda: ui.log("DATA", "policy", "sender %s  spf=%s dkim=%s dmarc=%s" % (_word(6) + "." + random.choice(["net", "org"]), random.choice(["pass", "softfail"]), random.choice(["pass", "none"]), random.choice(["none", "fail"])), GRAY), 0.15, 0.4)
    ui.set_phase(2)
    _prog("exposure scoring", 4, 8)
    ui.log("ALERT", "assess", "Domain exposure score %d/100" % random.randint(55, 88), RED)
    ui.set_phase(3)
    ui.log("OK", "report", "Recommend p=reject, -all, 2048-bit DKIM", GREEN)
    _summary(ui, ["domain   : %s" % dom])


def _sc_vuln(ui):
    ui.set_phase(0)
    hosts = random.randint(40, 600)
    ui.log("INFO", "scan", "Authenticated scan of %d hosts" % hosts)
    _w_heat(ui, 40)
    ui.set_phase(1)
    c, h, m, l = random.randint(2, 20), random.randint(10, 80), random.randint(30, 200), random.randint(50, 400)
    for nm, v, col in (("CRITICAL", c, RED), ("HIGH", h, ORANGE), ("MEDIUM", m, YELLOW), ("LOW", l, CYAN)):
        ui.raw("%-10s %-5d %s" % (nm, v, "█" * max(1, min(24, v // 6))), col, 0.5)
    ui.stream(18, lambda: ui.log("DATA", "rank", "%-14s %-12s CVSS %.1f" % ("NP-2026-%04d" % random.randint(1, 9999), random.choice(["CRITICAL", "HIGH", "MEDIUM"]), random.uniform(4, 9.9)), GRAY), 0.1, 0.3)
    ui.set_phase(2)
    ui.log("INFO", "validate", "Verifying %d critical findings" % c)
    _prog("validation", 5, 9)
    ui.log("OK", "validate", "%d confirmed, 2 dismissed" % max(1, c - 2), GREEN)
    ui.set_phase(3)
    _prog("report build", 4, 8)
    ui.log("OK", "report", "assessment-%s.pdf generated" % hx(4), GREEN)
    _summary(ui, ["hosts    : %d" % hosts, "critical : %d" % c])


def _sc_sast(ui):
    ui.set_phase(0)
    ui.log("INFO", "index", "Indexing repository (%s files, %s lines)" % (format(random.randint(800, 9000), ","), format(random.randint(90000, 900000), ",")))
    _prog("indexing")
    ui.set_phase(1)
    ctr = [0]
    flags = [0]
    ui.stream(40, lambda: flags.__setitem__(0, flags[0] + (1 if _codeline(ui, ctr) else 0)), 0.04, 0.16)
    ui.set_phase(2)
    ui.log("INFO", "taint", "Tracing untrusted input to sinks")
    ui.stream(20, lambda: ui.log("DATA", "taint", "source request.%s -> sink %s  [%s]" % (random.choice(["args", "body", "header"]), random.choice(["db.exec", "open()", "render()", "memcpy"]), random.choice(["sanitised", "sanitised", "UNSANITISED"])), GRAY), 0.1, 0.35)
    ui.log("ALERT", "taint", "%d unsanitised flows confirmed" % random.randint(2, 9), RED)
    ui.set_phase(3)
    _prog("report", 4, 8)
    ui.log("OK", "report", "sast-%s.sarif written (%d findings)" % (hx(4), flags[0] + 3), GREEN)
    _summary(ui, ["findings : %d" % (flags[0] + 3)])


def _sc_chain(ui):
    ui.set_phase(0)
    ui.log("INFO", "seed", "Seeding trace from address 0x%s" % hx(16))
    _prog("graph load")
    ui.set_phase(1)
    amt = [0.0]

    def tx():
        a = random.uniform(0.2, 40)
        amt[0] += a
        ui.log("DATA", "tx", "0x%s  %s ──▶ %s  %7.2f NPC" % (hx(8), "w_" + hx(4), "w_" + hx(4), a), GRAY)
    ui.stream(34, tx, 0.1, 0.35)
    ui.set_phase(2)
    ui.log("WARN", "cluster", "%d wallets share common funding source" % random.randint(8, 60), YELLOW)
    ui.stream(18, lambda: ui.log("DATA", "mixer", "hop %-3d  w_%s ──▶ w_%s  split %d-way" % (random.randint(1, 40), hx(4), hx(4), random.randint(2, 9)), GRAY), 0.15, 0.4)
    ui.set_phase(3)
    _prog("exchange matching", 4, 8)
    ui.log("ALERT", "match", "Funds reach exchange deposit address w_%s" % hx(4), RED)
    ui.log("OK", "report", "Trace report prepared for compliance team", GREEN)
    _summary(ui, ["traced   : %.1f NPC" % amt[0]])


def _sc_iam(ui):
    ui.set_phase(0)
    ui.log("INFO", "inv", "Inventorying accounts across directory and cloud")
    n = random.randint(800, 6000)
    ctr = [0]
    ui.stream(24, lambda: ui.log("DATA", "acct", "%-9s mfa=%-3s last-login %3dd  roles %d" % (_user(), random.choice(["on", "on", "off"]), random.randint(0, 400), random.randint(1, 6)), GRAY), 0.06, 0.22)
    ui.set_phase(1)
    ui.log("WARN", "risk", "%d accounts without MFA, %d stale > 180 days" % (random.randint(20, 300), random.randint(10, 200)), YELLOW)
    ui.stream(20, lambda: ui.log("WARN", "signin", "risky sign-in %s from %s  score %.1f" % (_user(), fake_ip(), random.uniform(5, 9.9)), YELLOW), 0.2, 0.5)
    ui.set_phase(2)
    ui.log("INFO", "priv", "Mapping privileged group membership")
    _prog("graph build", 4, 8)
    ui.log("ALERT", "priv", "%d service accounts hold admin rights without owner" % random.randint(3, 25), RED)
    ui.set_phase(3)
    ui.log("INFO", "fix", "Generating remediation tickets")
    _prog("tickets", 3, 6)
    ui.log("OK", "fix", "%d tickets opened, MFA enrolment campaign queued" % random.randint(10, 80), GREEN)
    _summary(ui, ["accounts : %s" % format(n, ",")])


# (key, name, phases, fn, log-style, (header bg, footer bg, accent), bar chars)
SCENARIOS = [
    ("network", "Network Intrusion", list(zip(PHASES, PHASE_SHORT)), _sc_network, "syslog", ((70, 0, 25), (40, 0, 15), YELLOW), ("█", "░")),
    ("web", "Web Application", [("CRAWL", "CR"), ("FUZZ", "FZ"), ("INJECT", "IN"), ("AUTH", "AU"), ("SHELL", "SH"), ("LOOT", "LT")], _sc_web, "arrow", ((0, 40, 100), (0, 20, 55), CYAN), ("▰", "▱")),
    ("wifi", "Wireless Audit", [("SCAN", "SC"), ("TARGET", "TG"), ("CAPTURE", "CP"), ("CRACK", "CK"), ("ACCESS", "AC")], _sc_wifi, "box", ((60, 0, 100), (35, 0, 65), PINK), ("▮", "▯")),
    ("ad", "Corporate Domain", [("ENUM", "EN"), ("TICKETS", "TK"), ("LATERAL", "LT"), ("DOMAIN", "DA"), ("SYNC", "SY")], _sc_ad, "tree", ((0, 70, 30), (0, 35, 15), GREEN), ("■", "□")),
    ("cloud", "Cloud Infrastructure", [("RECON", "RC"), ("IAM", "IA"), ("PRIVESC", "PE"), ("STORAGE", "ST"), ("EXFIL", "XF")], _sc_cloud, "term", ((0, 70, 80), (0, 35, 45), CYAN), ("=", "-")),
    ("iot", "IoT Network", [("DISCOVER", "DS"), ("FINGER", "FP"), ("ACCESS", "AC"), ("CONTROL", "CT")], _sc_iot, "tag", ((100, 45, 0), (55, 25, 0), ORANGE), ("●", "○")),
    ("db", "Database Breach", [("PROBE", "PR"), ("AUTH", "AU"), ("ENUM", "EN"), ("DUMP", "DP")], _sc_db, "syslog", ((90, 70, 0), (50, 40, 0), YELLOW), ("#", ".")),
    ("crack", "Cracking Cluster", [("LOAD", "LD"), ("ATTACK", "AT"), ("RESULT", "RS")], _sc_crack, "box", ((100, 0, 10), (60, 0, 5), RED), ("█", "▒")),
    ("soc", "Incident Response", [("DETECT", "DT"), ("TRIAGE", "TR"), ("CONTAIN", "CN"), ("ERADICATE", "ER"), ("RECOVER", "RV")], _sc_soc, "tag", ((0, 80, 70), (0, 40, 35), GREEN), ("▓", "░")),
    ("forensics", "Digital Forensics", [("ACQUIRE", "AQ"), ("CARVE", "CV"), ("TIMELINE", "TL"), ("ATTRIB", "AT"), ("REPORT", "RP")], _sc_forensics, "tree", ((50, 60, 80), (30, 35, 50), CYAN), ("▪", "·")),
    ("malware", "Malware Analysis Lab", [("SAMPLE", "SM"), ("STATIC", "ST"), ("DYNAMIC", "DY"), ("VERDICT", "VD")], _sc_malware, "term", ((90, 0, 90), (50, 0, 50), PINK), ("▮", "░")),
    ("intel", "Threat Intelligence", [("INGEST", "IN"), ("CORRELATE", "CR"), ("ENRICH", "EN"), ("ALERT", "AL")], _sc_intel, "arrow", ((0, 60, 90), (0, 30, 50), CYAN), ("◆", "◇")),
    ("honeypot", "Honeypot Monitor", [("DEPLOY", "DP"), ("LURE", "LR"), ("OBSERVE", "OB"), ("ANALYZE", "AN")], _sc_honeypot, "box", ((95, 80, 0), (55, 45, 0), YELLOW), ("◼", "◻")),
    ("pcap", "Packet Analysis", [("CAPTURE", "CP"), ("DISSECT", "DS"), ("STREAMS", "SR"), ("FLAGS", "FG")], _sc_pcap, "term", ((0, 90, 40), (0, 50, 20), GREEN), ("━", "╌")),
    ("fuzz", "Vulnerability Research", [("TARGET", "TG"), ("FUZZ", "FZ"), ("CRASH", "CR"), ("TRIAGE", "TR")], _sc_fuzz, "syslog", ((110, 0, 70), (65, 0, 40), PINK), ("▌", "░")),
    ("api", "API Security Audit", [("DISCOVER", "DS"), ("AUTHZ", "AZ"), ("LIMITS", "RL"), ("REPORT", "RP")], _sc_api, "arrow", ((70, 20, 120), (40, 10, 70), PURPLE), ("»", "·")),
    ("k8s", "Container / Cluster Audit", [("ENUM", "EN"), ("IMAGES", "IM"), ("RBAC", "RB"), ("REPORT", "RP")], _sc_k8s, "tag", ((20, 50, 130), (10, 25, 75), BLUE), ("▇", "░")),
    ("mobile", "Mobile App Audit", [("UNPACK", "UP"), ("STATIC", "ST"), ("RUNTIME", "RT"), ("REPORT", "RP")], _sc_mobile, "tree", ((110, 50, 0), (60, 28, 0), ORANGE), ("▰", "·")),
    ("mail", "Email Security Audit", [("DNS", "DN"), ("POLICY", "PL"), ("ASSESS", "AS"), ("REPORT", "RP")], _sc_mail, "box", ((0, 80, 100), (0, 45, 60), CYAN), ("▬", "▭")),
    ("vuln", "Vulnerability Assessment", [("SCAN", "SC"), ("RANK", "RK"), ("VALIDATE", "VL"), ("REPORT", "RP")], _sc_vuln, "arrow", ((120, 20, 20), (70, 10, 10), RED), ("▉", "░")),
    ("sast", "Source Code Audit", [("INDEX", "IX"), ("SCAN", "SC"), ("TAINT", "TN"), ("REPORT", "RP")], _sc_sast, "term", ((20, 90, 20), (10, 50, 10), GREEN), ("■", "▫")),
    ("chain", "Blockchain Tracing", [("SEED", "SD"), ("TRACE", "TR"), ("CLUSTER", "CL"), ("MATCH", "MT")], _sc_chain, "tree", ((120, 90, 0), (70, 50, 0), YELLOW), ("◈", "◇")),
    ("iam", "Identity & Access Review", [("INVENTORY", "IV"), ("RISK", "RK"), ("PRIVILEGE", "PV"), ("FIX", "FX")], _sc_iam, "tag", ((120, 30, 90), (70, 15, 50), PINK), ("▓", "▒")),
]


def pro_operation_once(key=None):
    global CUR_BAR
    scn = None
    for s in SCENARIOS:
        if key and s[0] == key:
            scn = s
    scn = scn or random.choice(SCENARIOS)
    code = "%s %s" % (random.choice(CODE_A), random.choice(CODE_B))
    ui = OpUI(code, fake_ip(), scn[2], scn[1], scn[4], scn[5])
    CUR_BAR = scn[6]
    S.ops += 1
    w(HIDE)
    ui.start()
    try:
        ui.log("INFO", "core", "NEON//PHANTOM operator console online - operator %s" % S.username, CYAN, 0.3)
        ui.log("INFO", "core", "Operation %s [%s] initialised, relay chain armed" % (code, scn[1]), CYAN, 0.3)
        scn[3](ui)
        nap(2.5)
    finally:
        ui.stop()
        CUR_BAR = ("█", "░")


def _auto_pro():
    old = S.length
    S.length = min(old, 0.3)
    try:
        pro_operation_once()
    finally:
        S.length = old


def pro_mode(key=None):
    """Continuous elite-operator mode. key=None cycles through every type."""
    bag = []
    try:
        while True:
            if key:
                pro_operation_once(key)
            else:
                if not bag:
                    bag = [s[0] for s in SCENARIOS]
                    random.shuffle(bag)
                pro_operation_once(bag.pop())
            clear()
            pr(GRAY + "acquiring next target..." + RST)
            nap(1.5)
    except KeyboardInterrupt:
        pass
    finally:
        w("\033[r" + SHOW + RST)
        flush()
    pr()
    log("operation aborted - returning to menu", "!", YELLOW)
    nap(0.8)


def operation_library():
    while True:
        clear()
        section("OPERATION LIBRARY", PURPLE)
        for i, s in enumerate(SCENARIOS, 1):
            pr("  %s%d%s) %s%s%s" % (GREEN, i, RST, WHITE, s[1], RST))
        pr("  %s0%s) Back" % (RED, RST))
        try:
            c = input("\n%soperation>%s " % (CYAN, RST)).strip()
        except EOFError:
            return
        if c in ("0", "", "q"):
            return
        if c.isdigit() and 1 <= int(c) <= len(SCENARIOS):
            pro_mode(SCENARIOS[int(c) - 1][0])


def auto_mode():
    pool = [
        lambda: matrix_rain(7),
        ip_scanner,
        port_scan,
        decrypt_password,
        firewall_bypass,
        system_breach,
        db_download,
        satellite,
        gps_tracking,
        lambda: cpu_ram_monitor(6),
        lambda: network_traffic(6),
        hash_generator,
        lambda: encrypt_text(random.choice(["TARGET LOCKED", "OPERATION NEON", "GHOST PROTOCOL", "VAULT KEY ROTATED"])),
        security_alert,
        random_commands,
        lambda: rgb_effects(4),
        lambda: loading_animations(0.8),
        access_granted,
        connect_sim,
        _auto_pro,
        mission_complete,
    ]
    clear()
    w(HIDE)
    pr(rainbow("AUTOMATIC HACKER MODE".center(width()), 0.0, 0.05))
    pr(GRAY + "Press Ctrl+C at any time to return to the menu".center(width()) + RST)
    nap(1.5)
    bag = []
    cycle = 0
    try:
        while True:  # runs until the user stops it
            if not bag:
                bag = list(pool)
                random.shuffle(bag)
            fn = bag.pop()
            cycle += 1
            clear()
            pr("%s AUTO %s| op:%s | cycle #%d | Ctrl+C = stop%s" % (GREEN, GRAY, S.username, cycle, RST))
            fn()
            nap(0.6)
    except KeyboardInterrupt:
        pass
    finally:
        w(SHOW + RST)
        flush()
    pr()
    log("automatic mode stopped - returning to menu", "!", YELLOW)
    nap(0.8)


# ----------------------------------------------------------------------------
# Command console
# ----------------------------------------------------------------------------
def console_help():
    section("COMMAND CONSOLE - HELP", CYAN)
    rows = [
        ("help", "show this help"),
        ("scan", "IP scan   (scan ports = port scan)"),
        ("portscan", "port scan"),
        ("decrypt", "password cracking (decrypt msg = decrypt last message)"),
        ("encrypt [text]", "encrypt text"),
        ("connect [ip]", "secure connection"),
        ("matrix", "matrix rain (Ctrl+C to stop)"),
        ("gps", "GPS tracking"),
        ("status", "system status"),
        ("download", "database download"),
        ("satellite", "satellite link"),
        ("firewall", "firewall bypass"),
        ("breach", "system breach"),
        ("monitor", "CPU/RAM monitor"),
        ("traffic", "network traffic"),
        ("hash [text]", "hash generator"),
        ("alert", "security alert"),
        ("access", "access granted screen"),
        ("mission", "mission complete screen"),
        ("run", "random hacker commands"),
        ("loading", "loading animations"),
        ("rgb", "RGB effects"),
        ("auto", "automatic hacker mode"),
        ("op [type]", "PRO OPERATION (op list = all types)"),
        ("whoami", "show operator name"),
        ("sound on|off", "toggle bell sounds"),
        ("banner", "show logo"),
        ("clear", "clear screen"),
        ("exit", "back to main menu"),
    ]
    for c, d in rows:
        pr("  %s%-15s%s %s%s%s" % (GREEN, c, RST, GRAY, d, RST))


def console():
    clear()
    show_logo(False)
    pr(CYAN + "Type 'help' for commands. 'exit' to leave." + RST)
    pr()

    def run(fn, *a):
        try:
            fn(*a)
        except KeyboardInterrupt:
            pr()
            log("interrupted", "!", YELLOW)

    while True:
        try:
            w("%s%s%s@%sneon-phantom%s:%s~%s# %s" % (GREEN, S.username.lower(), RED, CYAN, WHITE, PURPLE, RED, RST))
            flush()
            line = input().strip()
        except EOFError:
            pr()
            return
        except KeyboardInterrupt:
            pr()
            pr(GRAY + "(use 'exit' to leave the console)" + RST)
            continue
        if not line:
            continue
        parts = line.split()
        cmd, args = parts[0].lower(), parts[1:]
        rest = " ".join(args)
        if cmd in ("exit", "quit", "q"):
            return
        elif cmd == "help" or cmd == "?":
            console_help()
        elif cmd == "clear" or cmd == "cls":
            clear()
        elif cmd == "scan":
            run(port_scan if args and args[0].lower() == "ports" else ip_scanner)
        elif cmd == "portscan":
            run(port_scan)
        elif cmd == "decrypt":
            run(decrypt_message if args and args[0].lower() == "msg" else decrypt_password)
        elif cmd == "encrypt":
            run(encrypt_text, rest or None)
        elif cmd == "connect":
            run(connect_sim, rest or None)
        elif cmd == "matrix":
            run(matrix_rain, 20)
        elif cmd == "gps":
            run(gps_tracking)
        elif cmd == "status":
            run(status_sim)
        elif cmd == "download":
            run(db_download)
        elif cmd == "satellite":
            run(satellite)
        elif cmd == "firewall":
            run(firewall_bypass)
        elif cmd == "breach":
            run(system_breach)
        elif cmd == "monitor":
            run(cpu_ram_monitor, 15)
        elif cmd == "traffic":
            run(network_traffic, 15)
        elif cmd == "hash":
            run(hash_generator, rest or None)
        elif cmd == "alert":
            run(security_alert)
        elif cmd == "access":
            run(access_granted)
        elif cmd == "mission":
            run(mission_complete)
        elif cmd == "run":
            run(random_commands)
        elif cmd == "loading":
            run(loading_animations)
        elif cmd == "rgb":
            run(rgb_effects)
        elif cmd == "op":
            keys = [x[0] for x in SCENARIOS]
            if args and args[0].lower() in keys:
                pro_mode(args[0].lower())
            elif args and args[0].lower() == "list":
                pr(CYAN + "types: " + ", ".join(keys) + RST)
                continue
            else:
                pro_mode()
            clear()
        elif cmd == "auto":
            auto_mode()
            clear()
        elif cmd == "whoami":
            pr(GREEN + S.username + RST)
        elif cmd == "banner":
            show_logo(True)
        elif cmd == "sound":
            if args and args[0].lower() in ("on", "off"):
                S.sound = args[0].lower() == "on"
                save_config()
                pr("%ssound: %s%s" % (CYAN, "ON" if S.sound else "OFF", RST))
                beep("ok")
            else:
                pr("usage: sound on|off")
        else:
            pr("%s%s: command not found%s  %s(type 'help')%s" % (RED, cmd, RST, GRAY, RST))


# ----------------------------------------------------------------------------
# Settings / config
# ----------------------------------------------------------------------------
def load_config():
    try:
        with open(CONFIG_PATH, "r") as f:
            d = json.load(f)
        S.username = str(d.get("username", S.username))[:16] or "GHOST"
        S.sound = bool(d.get("sound", True))
        S.speed = float(d.get("speed", 1.0))
        S.length = float(d.get("length", 2.5))
        S.first_run = False
    except Exception:
        S.first_run = True


def save_config():
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump({"username": S.username, "sound": S.sound, "speed": S.speed, "length": S.length}, f)
    except Exception:
        pass


def clean_name(raw):
    name = "".join(c for c in raw.strip() if c.isalnum() or c in "_-")[:16]
    return name


def ask_username():
    try:
        raw = input("%sEnter hacker username (e.g. GHOST): %s" % (CYAN, RST))
    except EOFError:
        raw = ""
    name = clean_name(raw)
    if name:
        S.username = name
    save_config()


def settings_menu():
    while True:
        clear()
        section("SETTINGS", PURPLE)
        pr("  %s1%s) Hacker username : %s%s%s" % (GREEN, RST, WHITE, S.username, RST))
        pr("  %s2%s) Sound effects   : %s%s%s" % (GREEN, RST, WHITE, "ON" if S.sound else "OFF", RST))
        spd = {0.5: "FAST", 1.0: "NORMAL", 2.0: "SLOW"}.get(S.speed, "x%.1f" % S.speed)
        pr("  %s3%s) Animation speed : %s%s%s" % (GREEN, RST, WHITE, spd, RST))
        ln = {0.5: "QUICK (~1-2 min)", 2.5: "LONG (~3-10 min)", 6.0: "EXTENDED (~8-25 min)", 15.0: "MARATHON (~20-60 min)"}.get(S.length, "x%.2f" % S.length)
        pr("  %s5%s) Operation length: %s%s%s" % (GREEN, RST, WHITE, ln, RST))
        pr("  %s4%s) Test sound" % (GREEN, RST))
        pr("  %s0%s) Back" % (GREEN, RST))
        try:
            c = input("\n%ssettings>%s " % (CYAN, RST)).strip()
        except EOFError:
            return
        if c == "1":
            ask_username()
        elif c == "2":
            S.sound = not S.sound
            save_config()
        elif c == "3":
            S.speed = {1.0: 0.5, 0.5: 2.0}.get(S.speed, 1.0)
            save_config()
        elif c == "5":
            S.length = {0.5: 2.5, 2.5: 6.0, 6.0: 15.0}.get(S.length, 0.5)
            save_config()
        elif c == "4":
            beep("alert")
            pr(GREEN + "bell sent (depends on Termux bell setting)" + RST)
            nap(0.8)
        elif c == "0" or c == "":
            return


# ----------------------------------------------------------------------------
# Main menu
# ----------------------------------------------------------------------------
def menu_encrypt():
    clear()
    section("ENCRYPT / DECRYPT", PURPLE)
    pr("  %s1%s) Encrypt a message" % (GREEN, RST))
    pr("  %s2%s) Decrypt last message" % (GREEN, RST))
    c = input("\n%s>%s " % (CYAN, RST)).strip()
    if c == "1":
        t = input("%sText (Enter = default): %s" % (CYAN, RST)).strip()
        encrypt_text(t or None)
    elif c == "2":
        decrypt_message()
    else:
        return
    pause()


def menu_hash():
    clear()
    t = input("%sText to hash (Enter = random data): %s" % (CYAN, RST)).strip()
    hash_generator(t or None)
    pause()


def run_item(fn, wait=True):
    clear()
    try:
        fn()
        if wait:
            pause()
    except KeyboardInterrupt:
        w(SHOW + RST)
        pr()
        log("interrupted - back to menu", "!", YELLOW)
        nap(0.8)
    except EOFError:
        pass


MENU = [
    ("1", "AUTOMATIC HACKER MODE", lambda: auto_mode(), False),
    ("2", "Command Console", lambda: console(), False),
    ("3", "Matrix Code Rain", lambda: matrix_rain(20), False),
    ("4", "IP Address Scanner", lambda: ip_scanner(), True),
    ("5", "Port Scanner", lambda: port_scan(), True),
    ("6", "Password Decryption", lambda: decrypt_password(), True),
    ("7", "Firewall Bypass", lambda: firewall_bypass(), True),
    ("8", "System Breach", lambda: system_breach(), True),
    ("9", "Database Download", lambda: db_download(), True),
    ("10", "Satellite Connection", lambda: satellite(), True),
    ("11", "GPS Tracking", lambda: gps_tracking(), True),
    ("12", "CPU / RAM Monitor", lambda: cpu_ram_monitor(), True),
    ("13", "Network Traffic Monitor", lambda: network_traffic(), True),
    ("14", "Hash Generator", lambda: menu_hash(), False),
    ("15", "Encrypt / Decrypt", lambda: menu_encrypt(), False),
    ("16", "Security Alert", lambda: security_alert(), True),
    ("17", "Access Granted", lambda: access_granted(), True),
    ("18", "Mission Complete", lambda: mission_complete(), True),
    ("19", "Random Hacker Commands", lambda: random_commands(), True),
    ("20", "Loading Animations", lambda: loading_animations(), True),
    ("21", "RGB Effects", lambda: rgb_effects(), True),
    ("22", "Settings (username / sound)", lambda: settings_menu(), False),
    ("23", "PRO OPERATION (all types mix)", lambda: pro_mode(), False),
    ("24", "Operation Library (choose type)", lambda: operation_library(), False),
    ("0", "Exit", None, False),
]


def draw_menu():
    clear()
    show_logo(False)
    W = width()
    pr("%s operator: %s%s%s   sound: %s%s%s" %
       (GRAY, GREEN, S.username, GRAY, GREEN, "ON" if S.sound else "OFF", RST))
    pr("%s┌%s┐%s" % (CYAN, "─" * (W - 2), RST))
    for i, (k, label, fn, wait) in enumerate(MENU):
        col = RED if k == "0" else PALETTE[i % len(PALETTE)]
        pr("%s│%s %s%3s%s) %s%-*s%s%s│%s" % (CYAN, RST, col, k, RST, WHITE, W - 11, label, RST, CYAN, RST))
    pr("%s└%s┘%s" % (CYAN, "─" * (W - 2), RST))


def farewell():
    pr()
    pr(rainbow("  NEON//PHANTOM offline. Stay legal. Stay curious.", 0.1, 0.03))
    pr()


def main_menu():
    last_int = 0.0
    lookup = dict((k, (fn, wait)) for k, label, fn, wait in MENU)
    while True:
        draw_menu()
        try:
            choice = input("\n%sselect%s@%sphantom%s> %s" % (GREEN, GRAY, CYAN, PURPLE, RST)).strip().lower()
        except KeyboardInterrupt:
            now = time.time()
            if now - last_int < 2.0:
                farewell()
                return
            last_int = now
            pr()
            pr(YELLOW + "Press Ctrl+C again (or choose 0) to exit." + RST)
            nap(1.0)
            continue
        except EOFError:
            farewell()
            return
        if choice in ("0", "exit", "quit", "q"):
            farewell()
            return
        if choice in lookup:
            fn, wait = lookup[choice]
            run_item(fn, wait)
        elif choice:
            pr(RED + "Invalid option." + RST)
            nap(0.8)


def main():
    load_config()
    try:
        boot()
        if S.first_run:
            pr()
            ask_username()
        main_menu()
    except KeyboardInterrupt:
        w(SHOW + RST)
        farewell()
    finally:
        w(SHOW + RST)
        flush()


if __name__ == "__main__":
    main()