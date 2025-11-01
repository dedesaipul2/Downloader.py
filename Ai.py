#!/usr/bin/env python3
# UltraProMax v7.1 - HYPER MODE (FINAL)
# Universal downloader UI (Termux-friendly)
# Features: compact neon logo (A), auto-resize, matrix-lite, yt-dlp support,
# batch downloads, auto-detect platform, ffmpeg handling, safe storage.

import os
import sys
import time
import re
import shutil
import socket
import threading
import random

# optional third-party libs
try:
    import requests
except Exception:
    requests = None

try:
    import yt_dlp
except Exception:
    yt_dlp = None

from concurrent.futures import ThreadPoolExecutor, as_completed

# =========================
# Config
# =========================
APP_NAME = "UltraProMax"
LOG_FILE = "download_log.txt"
SAFE_DOWNLOAD_DIR = os.path.expanduser("~/storage/shared/Download/UltraProMax")
LOCAL_FALLBACK = os.path.join(os.getcwd(), "Download_Media")
MAX_RETRIES = 3
FAST_DEFAULT_WORKERS = 3

# =========================
# Colors & helpers
# =========================
CSI = "\033["
def fg(code): return CSI + str(code) + "m"
RESET = fg(0)
COL_H = fg(96); COL_A = fg(93); COL_M = fg(95); COL_G = fg(92)
COL_R = fg(91); COL_W = fg(97); COL_DIM = fg(90)

def clear():
    os.system("clear")

def term_size():
    try:
        cols, rows = shutil.get_terminal_size()
        return cols, rows
    except:
        return 80, 24

def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")

def write_log(msg):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{now()}] {msg}\n")
    except:
        pass

def clean_filename(s):
    if not s:
        return "unknown"
    return re.sub(r'[\\/*?:"<>|]', "", str(s))[:200]

def human_bytes(n):
    try:
        n = float(n)
    except:
        return "0B"
    for unit in ["B","KB","MB","GB","TB"]:
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"

# =========================
# Storage & system helpers
# =========================
def storage_ready():
    return os.path.exists(os.path.expanduser("~/storage/shared"))

def ensure_storage():
    if storage_ready():
        try:
            os.makedirs(SAFE_DOWNLOAD_DIR, exist_ok=True)
            return SAFE_DOWNLOAD_DIR
        except:
            pass
    os.makedirs(LOCAL_FALLBACK, exist_ok=True)
    return LOCAL_FALLBACK

def has_internet(host="8.8.8.8", port=53, timeout=3):
    try:
        socket.setdefaulttimeout(timeout)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((host, port))
        s.close()
        return True
    except:
        return False

def is_ffmpeg_installed():
    return shutil.which("ffmpeg") is not None

def try_install_ffmpeg():
    if is_ffmpeg_installed():
        print(COL_G + "ffmpeg already installed." + RESET)
        return True
    print(COL_A + "Attempting to install ffmpeg via pkg (Termux)..." + RESET)
    code = os.system("pkg install ffmpeg -y")
    ok = code == 0 and is_ffmpeg_installed()
    if ok:
        print(COL_G + "ffmpeg installed." + RESET)
    else:
        print(COL_R + "ffmpeg not installed. Run: pkg install ffmpeg" + RESET)
    return ok

# =========================
# Platform detection
# =========================
PLATFORM_KEYWORDS = {
    "tiktok": ["tiktok.com", "vt.tiktok.com", "vm.tiktok.com", "t.tiktok.com"],
    "instagram": ["instagram.com", "instagr.am"],
    "facebook": ["facebook.com", "fb.watch", "m.facebook.com", "fbcdn"],
    "twitter": ["twitter.com", "x.com", "x.co", "video.twimg"],
    "youtube": ["youtube.com", "youtu.be"],
    "capcut": ["capcut.com"],
    "reddit": ["reddit.com"],
    "pinterest": ["pinterest.com"],
    "snackvideo": ["snackvideo.com"],
    "kwai": ["kwai.com"],
    "douyin": ["douyin.com"],
    "likee": ["likee"],
}

def detect_platform(url):
    u = (url or "").lower()
    for name, keys in PLATFORM_KEYWORDS.items():
        for k in keys:
            if k in u:
                return name.capitalize()
    return "Unknown/yt-dlp"

# =========================
# yt-dlp helpers & progress
# =========================
print_lock = threading.Lock()

def progress_hook_factory(label):
    def hook(d):
        status = d.get("status")
        if status == "downloading":
            pct = d.get("_percent_str", "0%").strip()
            spd = d.get("_speed_str", "--")
            eta = d.get("_eta_str", "--")
            with print_lock:
                sys.stdout.write(f"\r{COL_H}[{label}] {pct} | {spd} | ETA {eta}{RESET}")
                sys.stdout.flush()
        elif status == "finished":
            with print_lock:
                sys.stdout.write(f"\r{COL_G}[{label}] finished. Finalizing...{RESET}\n")
                sys.stdout.flush()
    return hook

def build_ydl_opts(mode, quality, out_folder, label):
    if mode == "video":
        if quality == "best":
            fmt = "best[ext=mp4]/bestvideo+bestaudio/best"
        else:
            fmt = f"best[ext=mp4][height<={quality}]/bestvideo[height<={quality}]+bestaudio/best"
    else:
        fmt = "bestaudio/best"
    opts = {
        "format": fmt,
        "outtmpl": os.path.join(out_folder, "%(title)s.%(ext)s"),
        "noplaylist": False,
        "progress_hooks": [progress_hook_factory(label)],
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "restrictfilenames": False,
        "cachedir": False
    }
    if mode == "audio":
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192"
        }]
    return opts

def save_metadata(info, folder):
    try:
        title = clean_filename(info.get("title") or info.get("id") or "unknown")
        desc = info.get("description", "")
        thumb = info.get("thumbnail")
        if desc:
            with open(os.path.join(folder, f"{title}_caption.txt"), "w", encoding="utf-8") as f:
                f.write(desc)
        if thumb and requests:
            try:
                r = requests.get(thumb, timeout=15)
                if r.status_code == 200:
                    with open(os.path.join(folder, f"{title}_thumbnail.jpg"), "wb") as imf:
                        imf.write(r.content)
            except:
                pass
    except:
        pass

# =========================
# Core download
# =========================
def download_single(url, mode="video", quality="best", out_folder=None, retries=MAX_RETRIES):
    url = str(url or "").strip()
    folder = out_folder or ensure_storage()
    platform = detect_platform(url)
    label = (platform[:12] or "item")
    if not has_internet():
        print(COL_R + "No internet connection." + RESET)
        write_log(f"NO_INTERNET | {url}")
        return {"url": url, "status": "no_internet"}
    if not url:
        print(COL_R + "Empty URL." + RESET)
        return {"url": url, "status": "invalid"}
    if yt_dlp is None:
        print(COL_R + "yt-dlp not installed. Install with: pip install yt-dlp" + RESET)
        return {"url": url, "status": "no_yt_dlp"}

    attempt = 0
    last_err = None

    if mode == "audio" and not is_ffmpeg_installed():
        try_install_ffmpeg()

    while attempt < retries:
        attempt += 1
        try:
            print(COL_A + f"Detected: {platform} | Attempt {attempt}/{retries} | URL: {url}" + RESET)
            ydl_opts = build_ydl_opts(mode, quality, folder, label)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
            if info:
                save_metadata(info, folder)
                title = clean_filename(info.get("title") or info.get("id") or "file")
                write_log(f"OK | {title} | {url}")
                print("\n" + COL_G + f"Download finished: {title}" + RESET)
                return {"url": url, "status": "ok", "title": title}
            else:
                write_log(f"NO_INFO | {url}")
                return {"url": url, "status": "no_info"}
        except Exception as e:
            last_err = str(e)
            write_log(f"ERR attempt:{attempt} | {url} | {last_err}")
            print("\n" + COL_R + f"Error attempt {attempt}: {last_err}" + RESET)
            time.sleep(1 + attempt)
            continue
    write_log(f"FAIL | {url} | {last_err}")
    return {"url": url, "status": "fail", "error": last_err}

# =========================
# Batch manager
# =========================
def batch_download(urls, mode="video", quality="best", fast_mode=False, workers=FAST_DEFAULT_WORKERS):
    results = []
    urls = [u for u in urls if u]
    if not urls:
        return results
    if fast_mode and len(urls) > 1:
        print(COL_A + f"Fast mode: {workers} workers..." + RESET)
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(download_single, u, mode, quality): u for u in urls}
            for fut in as_completed(futures):
                try:
                    res = fut.result()
                except Exception as e:
                    res = {"url": futures[fut], "status": "fail", "error": str(e)}
                results.append(res)
    else:
        for u in urls:
            results.append(download_single(u, mode, quality))
    return results

# =========================
# UI v7.1 - Logo A (compact)
# =========================
ASCII_LOGO_A = [
r"██████╗ ██╗   ██╗██╗   ██╗████████╗██████╗  ██████╗ ",
r"██╔══██╗██║   ██║██║   ██║╚══██╔══╝██╔══██╗██╔════╝ ",
r"██████╔╝██║   ██║██║   ██║   ██║   ██████╔╝██║  ███╗",
r"██╔══██╗██║   ██║██║   ██║   ██║   ██╔══██╗██║   ██║",
r"██████╔╝╚██████╔╝╚██████╔╝   ██║   ██║  ██║╚██████╔╝",
r"╚═════╝  ╚═════╝  ╚═════╝    ╚═╝   ╚═╝  ╚═╝ ╚═════╝",
r"",
r"       UltraProMax  •  V7.1 HYPER MODE  •  UNIVERSAL DOWNLOADER",
r"         Futuristic • Neon • Matrix • Gradient • LiveStats",
]

GRADIENT_SEQ = [36, 95, 35, 34, 96, 93, 91]

def print_gradient(text, width):
    out = ""
    n = len(GRADIENT_SEQ)
    for i, ch in enumerate(text):
        color = GRADIENT_SEQ[(i * n) // max(1, len(text))]
        out += fg(color) + ch
    out += RESET
    if len(text) < width:
        pad = (width - len(text)) // 2
        print(" " * pad + out)
    else:
        print(out)

def strip_ansi(s):
    return re.sub(r'\x1b\[[0-9;]*m', '', s)

def center_text(text, width):
    s = strip_ansi(text)
    if len(s) >= width:
        return text[:width]
    pad = (width - len(s)) // 2
    return " " * pad + text + " " * (width - pad - len(s))

def animated_logo(seconds=1.2):
    cols, rows = term_size()
    w = min(80, max(40, cols - 4))
    lines = ASCII_LOGO_A
    end = time.time() + seconds
    while time.time() < end:
        clear()
        for ln in lines:
            color = random.choice([COL_H, COL_M, COL_A, COL_G])
            trimmed = ln if len(strip_ansi(ln)) <= w else ln[:w]
            print(center_text(color + trimmed + RESET, w))
        time.sleep(0.11)
    clear()
    for ln in lines:
        print(center_text(COL_A + ln + RESET, w))

def matrix_lite(duration=1.0, width=40):
    cols = min(width, max(20, term_size()[0]//2))
    end = time.time() + duration
    while time.time() < end:
        line = ""
        for i in range(cols):
            if random.random() > 0.97:
                line += fg(32) + chr(random.randint(33, 126)) + RESET
            else:
                line += " "
        sys.stdout.write("\r" + line)
        sys.stdout.flush()
        time.sleep(0.03)
    print()

def getch(prompt="Select: "):
    try:
        import termios, tty
        sys.stdout.write(fg(95) + prompt + RESET)
        sys.stdout.flush()
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x03":
                raise KeyboardInterrupt
            sys.stdout.write("\n")
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except Exception:
        return input(fg(95) + prompt + RESET).strip()

_stats_stop = threading.Event()
_stats_data = {"down": 0, "tasks": 0}

def stats_worker():
    while not _stats_stop.is_set():
        try:
            path = SAFE_DOWNLOAD_DIR if os.path.exists(SAFE_DOWNLOAD_DIR) else os.getcwd()
            total = 0
            files_count = 0
            for root, _, files in os.walk(path):
                for f in files:
                    try:
                        total += os.path.getsize(os.path.join(root, f))
                        files_count += 1
                    except:
                        pass
            _stats_data["down"] = total
            _stats_data["tasks"] = files_count
        except:
            pass
        time.sleep(2.0)

def uptime_str():
    try:
        if os.path.exists("/proc/uptime"):
            with open("/proc/uptime","r") as f:
                s = float(f.readline().split()[0])
                h = int(s // 3600); m = int((s%3600)//60)
                return f"{h}h{m}m"
    except:
        pass
    return "n/a"

# =========================
# Main menu v7.1
# =========================
def main_menu_v7_1():
    global COL_H, COL_A, COL_M, COL_G, COL_R, COL_W, COL_DIM

    missing = []
    if yt_dlp is None:
        missing.append("yt-dlp (pip install yt-dlp)")
    if requests is None:
        missing.append("requests (pip install requests) [optional]")
    if missing:
        print(COL_R + "Missing libs: " + ", ".join(missing) + RESET)
        time.sleep(1.0)

    _stats_stop.clear()
    t = threading.Thread(target=stats_worker, daemon=True)
    t.start()

    theme = "dark"
    animated_logo(1.0)

    while True:
        clear()
        cols, rows = term_size()
        w = max(60, min(100, cols - 6))

        # lightweight matrix flicker occasionally
        if random.random() < 0.1:
            matrix_lite(duration=0.5, width=min(40, w//2))

        header = f"{APP_NAME} • v7.1 HYPER MODE • UNIVERSAL DOWNLOADER"
        print_gradient(header.center(w), w)

        for ln in ASCII_LOGO_A[:6]:
            print(center_text(COL_M + ln + RESET, w))

        print()
        print(COL_DIM + "─" * w + RESET)
        stats_line = f" Uptime: {uptime_str()} | Storage: {'Yes' if storage_ready() else 'No'} | Files: {_stats_data.get('tasks',0)} | Size: {human_bytes(_stats_data.get('down',0))}"
        print(COL_G + stats_line.center(w) + RESET)
        print(COL_DIM + "─" * w + RESET)

        left = [
            ("1", "Download Video (MP4)"),
            ("2", "Download Audio (MP3)"),
            ("A", "Auto Download (Detect & Download)"),
            ("3", "Multi Download (Paste)"),
        ]
        right = [
            ("4", "Load links from .txt"),
            ("5", "Fast Mode (Threads)"),
            ("6", "Download from RAW URL"),
            ("7", "Install ffmpeg"),
        ]
        col_w = (w - 6) // 2
        for i in range(max(len(left), len(right))):
            l = left[i] if i < len(left) else ("","")
            r = right[i] if i < len(right) else ("","")
            left_text = f"[{l[0]}] {l[1]}".ljust(col_w)
            right_text = f"[{r[0]}] {r[1]}".ljust(col_w)
            print(COL_A + left_text + RESET + "  " + COL_H + right_text + RESET)

        print(COL_DIM + "─" * w + RESET)
        print(COL_M + "[q] Quit  [t] Toggle Theme  [g] Glow Logo  [u] Update Script" + RESET)
        print(COL_DIM + "─" * w + RESET)

        ch = getch("Select: ").strip()
        if not ch:
            continue
        ch_low = ch.lower()
        if ch_low in ("q",):
            _stats_stop.set()
            print(COL_DIM + "Exiting..." + RESET)
            time.sleep(0.2)
            break
        if ch_low == "t":
            theme = "light" if theme == "dark" else "dark"
            if theme == "light":
                COL_H, COL_A, COL_M, COL_G, COL_R, COL_W, COL_DIM = fg(34), fg(35), fg(36), fg(32), fg(31), fg(97), fg(90)
            else:
                COL_H, COL_A, COL_M, COL_G, COL_R, COL_W, COL_DIM = fg(96), fg(93), fg(95), fg(92), fg(91), fg(97), fg(90)
            continue
        if ch_low == "g":
            animated_logo(0.8)
            continue
        if ch_low == "u":
            if requests is None:
                print(COL_R + "requests not installed. Install via: pip install requests" + RESET)
                time.sleep(1)
                continue
            raw = input("Enter raw URL for update (or blank to cancel): ").strip()
            if raw:
                try:
                    r = requests.get(raw, timeout=20)
                    if r.status_code == 200:
                        path = os.path.realpath(__file__)
                        bak = path + ".bak"
                        shutil.copyfile(path, bak)
                        with open(path, "w", encoding="utf-8") as fw:
                            fw.write(r.text)
                        print(COL_G + "Updated. Restarting..." + RESET)
                        time.sleep(1)
                        os.execv(sys.executable, ['python3'] + sys.argv)
                    else:
                        print(COL_R + "Invalid update URL." + RESET)
                except Exception as e:
                    print(COL_R + "Update failed: " + str(e) + RESET)
            time.sleep(1)
            continue

        # Handlers
        if ch_low == "1":
            url = input("Masukkan link (any supported site): ").strip()
            q = input("Kualitas (best/360/720/1080/2160): ").strip() or "best"
            download_single(url, "video", q)
            input("ENTER to continue...")
            continue

        if ch_low == "2":
            url = input("Masukkan link (any supported site): ").strip()
            download_single(url, "audio", "best")
            input("ENTER to continue...")
            continue

        if ch_low == "a":
            print(COL_A + "Auto Mode: paste links one per line. Type DONE to start." + RESET)
            ls = []
            while True:
                l = input("> ").strip()
                if not l: continue
                if l.lower() == "done": break
                ls.append(l)
            if not ls:
                print(COL_R + "No links provided." + RESET)
                time.sleep(1)
                continue
            for link in ls:
                p = detect_platform(link)
                mode = "video"
                quality = "best"
                print(COL_H + f"Auto-detected {p} -> downloading as {mode.upper()}" + RESET)
                download_single(link, mode, quality)
            input("ENTER to continue...")
            continue

        if ch_low == "3":
            print("Paste links (one per line). Type DONE when finished.")
            ls=[]
            while True:
                l = input("> ").strip()
                if l.lower() == "done": break
                if l: ls.append(l)
            batch_download(ls, "video", "best", fast_mode=False)
            input("ENTER...")
            continue

        if ch_low == "4":
            fn = input("Path to .txt file: ").strip()
            if not os.path.exists(fn):
                print(COL_R + "File not found!" + RESET); time.sleep(1); continue
            with open(fn, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
            batch_download(lines, "video", "best", fast_mode=False)
            input("ENTER...")
            continue

        if ch_low == "5":
            print("Fast Mode: paste links then DONE.")
            ls=[]
            while True:
                l = input("> ").strip()
                if l.lower()=="done": break
                if l: ls.append(l)
            w = input("Workers (default 3): ").strip()
            try: w = int(w) if w else 3
            except: w = 3
            batch_download(ls, "video", "best", fast_mode=True, workers=w)
            input("ENTER...")
            continue

        if ch_low == "6":
            raw = input("Raw URL (pastebin/raw): ").strip()
            if requests is None:
                print(COL_R + "requests not installed. Install via pip install requests" + RESET)
                time.sleep(1); continue
            try:
                r = requests.get(raw, timeout=20)
                if r.status_code == 200:
                    lines = [l.strip() for l in r.text.splitlines() if l.strip()]
                    batch_download(lines, "video", "best", fast_mode=False)
                else:
                    print(COL_R + f"Failed to fetch list ({r.status_code})" + RESET)
            except Exception as e:
                print(COL_R + "Error: " + str(e) + RESET)
            input("ENTER...")
            continue

        if ch_low == "7":
            print("Internet:", has_internet()); input("ENTER..."); continue

        if ch_low == "8":
            try_install_ffmpeg(); input("ENTER..."); continue

        print(COL_R + "Unknown option." + RESET)
        time.sleep(0.5)

# =========================
# Entrypoint
# =========================
if __name__ == "__main__":
    ensure_storage()
    try:
        main_menu_v7_1()
    except KeyboardInterrupt:
        print("\n" + COL_DIM + "Interrupted. Bye." + RESET)