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
    return "%s-%02d.sim.local" % (
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
            out.append(hsv(grad[0] + (grad[1] - grad[0]) * i / max(1, bw - 1)) + "█")
        else:
            out.append(GRAY + "░")
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
    sub = "v%s  |  VISUAL SIMULATION ONLY" % VERSION
    pr(CYAN + sub.center(W) + RST)
    pr(gradient_line("═", W, 0.5))


def boot():
    clear()
    w(HIDE)
    try:
        show_logo(True)
        pr()
        mods = ["core.render", "matrix.engine", "net.sim", "crypto.sim", "geo.sim", "audio.bell", "ui.rgb"]
        for m in mods:
            log("loading module %-14s" % m, "*", CYAN)
            nap(0.06)
        progress("INITIALIZING", 1.6)
        log("sandbox  : ENABLED  (no real network / device access)", "+", GREEN)
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
    section("FAKE IP SCANNER", CYAN)
    W = width()
    rng = random.choice(["192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "10.%d.0.0/16" % random.randint(0, 255)])
    log("target range : %s  (SIMULATED)" % rng, "*", CYAN)
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
    section("FAKE PORT SCANNER", BLUE)
    target = target or fake_ip()
    log("target : %s  (SIMULATED)" % target, "*", CYAN)
    log("mac    : %s" % fake_mac(), "*", CYAN)
    log("scan   : SYN-sim, %d ports" % len(PORTS), "*", CYAN)
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
    log("%d open ports found (fictional)" % op, "+", GREEN)
    beep("ok")


# ----------------------------------------------------------------------------
# 4. Password decryption (fictional)
# ----------------------------------------------------------------------------
@sim
def decrypt_password():
    section("FAKE PASSWORD DECRYPTION", PURPLE)
    pw = fake_password()
    n = len(pw)
    log("hash type : SIM-SHA256", "*", CYAN)
    log("hash      : %s" % hx(32), "*", CYAN)
    log("wordlist  : phantom.dic (virtual)", "*", CYAN)
    log("rate      : %.1f GH/s (imaginary)" % random.uniform(1.5, 9.9), "*", CYAN)
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
    pr("%s(random fictional string - no real password involved)%s" % (GRAY, RST))
    beep("ok")


# ----------------------------------------------------------------------------
# 5. Firewall bypass
# ----------------------------------------------------------------------------
@sim
def firewall_bypass():
    section("FAKE FIREWALL BYPASS", RED)
    target = fake_ip()
    log("target firewall : %s (SIMULATED)" % target, "*", CYAN)
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
    section("FAKE SYSTEM BREACH", RED)
    ip = fake_ip()
    W = width()
    script = [
        ("resolving gateway %s" % ip, "*"),
        ("opening covert channel on port %d" % random.randint(1024, 65000), "*"),
        ("negotiating session key %s" % hx(16), "*"),
        ("injecting payload stub (inert)", "?"),
        ("exploit module loaded: phantom.sim.%s" % hx(4), "#"),
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
    for cmd, out in [("whoami", "root"), ("id", "uid=0(root) gid=0(root)"), ("ls /vault", "ledger.db  archive/  keys.sim  mail.idx")]:
        w("%sroot@%s:~# %s" % (RED, ip, RST))
        typewrite(cmd, WHITE, 0.03)
        pr(GREEN + out + RST)
        nap(0.2)
    pr()
    pr("%s(scripted text only - nothing was accessed)%s" % (GRAY, RST))


# ----------------------------------------------------------------------------
# 7. Database download
# ----------------------------------------------------------------------------
@sim
def db_download():
    section("FAKE DATABASE DOWNLOAD", GREEN)
    tables = ["users_vault", "ledger", "audit_log", "sessions", "archive", "mail_index", "telemetry"]
    random.shuffle(tables)
    tables = tables[:random.randint(4, 6)]
    log("source : db://%s/vault  (SIMULATED)" % fake_ip(), "*", CYAN)
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
    pr("%s(nothing was downloaded - this is only an animation)%s" % (GRAY, RST))
    beep("done")


# ----------------------------------------------------------------------------
# 8. Satellite connection
# ----------------------------------------------------------------------------
@sim
def satellite():
    section("FAKE SATELLITE CONNECTION", BLUE)
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
    log("SATELLITE LINK ESTABLISHED (simulated)", "+", GREEN)
    beep("ok")


# ----------------------------------------------------------------------------
# 9. GPS tracking (fictional radar)
# ----------------------------------------------------------------------------
@sim
def gps_tracking():
    section("FAKE GPS TRACKING", ORANGE)
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
    pr("%s(random fictional coordinates - no location was accessed)%s" % (GRAY, RST))
    beep("ok")


# ----------------------------------------------------------------------------
# 10. CPU / RAM monitor
# ----------------------------------------------------------------------------
@sim
def cpu_ram_monitor(seconds=12):
    section("FAKE CPU / RAM MONITOR", GREEN)
    W = width()
    bw = max(8, W - 18)
    cores = [random.randint(10, 60) for _ in range(8)]
    ram = random.randint(35, 60)
    swap = random.randint(5, 25)
    temp = random.randint(42, 58)
    procs = ["phantomd", "cryptsim", "netghost", "matrixd", "shadowsh", "scand"]
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
    pr("%s(all numbers are random - your real CPU/RAM is not read)%s" % (GRAY, RST))


# ----------------------------------------------------------------------------
# 11. Network traffic
# ----------------------------------------------------------------------------
@sim
def network_traffic(seconds=12):
    section("FAKE NETWORK TRAFFIC", CYAN)
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
    pr("%s(simulated traffic - no packets were captured)%s" % (GRAY, RST))


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
    section("FAKE ENCRYPTION", PURPLE)
    text = text or "NEON PHANTOM ONLINE"
    key = os.urandom(8)
    log("cipher : PHANTOM-256 (toy XOR, for show only)", "*", CYAN)
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
    pr("%s(toy cipher - never use it to protect real data)%s" % (GRAY, RST))
    beep("ok")


@sim
def decrypt_message():
    section("FAKE DECRYPTION", PURPLE)
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
    log("unknown scan from %s (simulated)" % fake_ip(), "!", RED)
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
    log("clearance : LEVEL 9 (fictional)", "#", PURPLE)
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
        ("TARGET", fake_ip() + " (fictional)"),
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
    pr(GRAY + "all stats are fictional - this was a simulation" + RST)
    beep("done")


# ----------------------------------------------------------------------------
# 17. Random hacker commands (invented tool names, scripted output)
# ----------------------------------------------------------------------------
CMD_BANK = [
    ("ghostmap --stealth {ip}", ["mapping 1024 vectors...", "fingerprint: NP-OS %s" % "7.2", "done in 0.42s"]),
    ("neonbrute --target {ip} --mode sim", ["loading dictionary (virtual)", "threads: 64", "candidate pool exhausted: 0 real attempts"]),
    ("cipherx --decode {hash}", ["block 1/4 ok", "block 2/4 ok", "block 3/4 ok", "block 4/4 ok"]),
    ("phantom-tunnel up --hops 5", ["hop 1 ok", "hop 2 ok", "hop 3 ok", "hop 4 ok", "hop 5 ok", "tunnel: ACTIVE"]),
    ("shadowsh --inject payload.sim", ["payload is inert", "queue: 0", "status: simulated"]),
    ("tracewipe --all", ["buffers cleared: %d" % 128, "logs rotated"]),
    ("vaultscan --deep {ip}", ["indexing...", "%d objects catalogued" % 4096, "report: vault.rpt"]),
    ("sigforge --spoof {mac}", ["signature rewritten", "header checksum: ok"]),
    ("matrixd --daemon", ["pid %d" % 4242, "listening on virtual:0"]),
    ("relay-hop --rotate", ["new exit node: N%02d" % 17, "latency 83ms"]),
]


@sim
def random_commands(count=None):
    section("RANDOM HACKER COMMANDS", GREEN)
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
    section("FAKE SECURE CONNECT", BLUE)
    target = target or fake_ip()
    log("target : %s  (SIMULATED - no socket opened)" % target, "*", CYAN)
    for s in ["resolving route", "TLS handshake (virtual)", "exchanging keys", "building tunnel"]:
        progress(s, random.uniform(0.5, 1.0))
    log("tunnel ID : %s" % hx(12), "*", CYAN)
    log("CONNECTED to %s (simulated)" % target, "+", GREEN)
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
    pr("%s%-12s%s %sACTIVE (SIM)%s" % (GRAY, "vpn", RST, GREEN, RST))
    pr("%s%-12s%s %d circuits (SIM)" % (GRAY, "tor", RST, random.randint(3, 9)))
    pr("%s%-12s%s %sGHOST%s" % (GRAY, "mode", RST, PURPLE, RST))
    for lbl in ["cpu", "ram", "net", "shield"]:
        v = random.randint(10, 95)
        pr("%s%-8s%s %s %s%3d%%%s" % (GRAY, lbl, RST, mbar(v, bw), WHITE, v, RST))
    pr("%s(all values fictional)%s" % (GRAY, RST))


# ----------------------------------------------------------------------------
# Automatic hacker mode
# ----------------------------------------------------------------------------
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
        ("scan", "fake IP scan   (scan ports = port scan)"),
        ("portscan", "fake port scan"),
        ("decrypt", "fake password cracking (decrypt msg = decrypt last message)"),
        ("encrypt [text]", "fake encryption of text"),
        ("connect [ip]", "fake secure connection"),
        ("matrix", "matrix rain (Ctrl+C to stop)"),
        ("gps", "fake GPS tracking"),
        ("status", "fake system status"),
        ("download", "fake database download"),
        ("satellite", "fake satellite link"),
        ("firewall", "fake firewall bypass"),
        ("breach", "fake system breach"),
        ("monitor", "fake CPU/RAM monitor"),
        ("traffic", "fake network traffic"),
        ("hash [text]", "hash generator"),
        ("alert", "fake security alert"),
        ("access", "access granted screen"),
        ("mission", "mission complete screen"),
        ("run", "random hacker commands"),
        ("loading", "loading animations"),
        ("rgb", "RGB effects"),
        ("auto", "automatic hacker mode"),
        ("whoami", "show operator name"),
        ("sound on|off", "toggle bell sounds"),
        ("banner", "show logo"),
        ("clear", "clear screen"),
        ("exit", "back to main menu"),
    ]
    for c, d in rows:
        pr("  %s%-15s%s %s%s%s" % (GREEN, c, RST, GRAY, d, RST))
    pr("%s  Nothing here touches a real network or device.%s" % (YELLOW, RST))


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
        S.first_run = False
    except Exception:
        S.first_run = True


def save_config():
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump({"username": S.username, "sound": S.sound, "speed": S.speed}, f)
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
    pr(GRAY + "  (it was all a simulation)" + RST)
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