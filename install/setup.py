"""
F1 Desktop Wallpaper — One-Command Setup
=========================================
Run this once after cloning the repo:

    python install/setup.py

What it does:
  1. Installs Python dependencies (requests, playwright, tzlocal)
  2. Downloads the Playwright Chromium browser
  3. Downloads Titillium Web fonts and builds the HTML template
  4. Generates and sets your first F1 wallpaper immediately
  5. Registers a Windows Task Scheduler task so the wallpaper
     updates automatically at every login and daily at 9 AM
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT   = Path(__file__).resolve().parent.parent  # install/ → project root
PYTHON = sys.executable

REQUIREMENTS       = ROOT / "install" / "requirements_wallpaper.txt"
FETCH_FONTS_SCRIPT = ROOT / "scripts" / "_fetch_fonts.py"
WRITE_TEMPLATE_SCRIPT = ROOT / "scripts" / "_write_template.py"
GENERATE_SCRIPT    = ROOT / "scripts" / "generate_wallpaper.py"
AUTO_UPDATE_SCRIPT = ROOT / "scripts" / "setup_auto_update.py"


def run_step(cmd: list, show_cmd: bool = False) -> None:
    """Run a subprocess step and exit with its return code on failure."""
    if show_cmd:
        print(f"    $ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"\n  ERROR: step failed (exit {result.returncode}). See output above.")
        sys.exit(result.returncode)


def main() -> None:
    print()
    print("=" * 58)
    print("   F1 Desktop Wallpaper  —  Setup")
    print("=" * 58)

    # ── Step 1: Python dependencies ───────────────────────────────────────────
    print("\n[1/5] Installing Python dependencies…")
    run_step([PYTHON, "-m", "pip", "install", "--quiet", "-r", str(REQUIREMENTS)], show_cmd=True)
    print("      Done.")

    # ── Step 2: Playwright Chromium ───────────────────────────────────────────
    print("\n[2/5] Downloading Playwright Chromium browser…")
    run_step([PYTHON, "-m", "playwright", "install", "chromium"], show_cmd=True)
    print("      Done.")

    # ── Step 3: Fonts + template ──────────────────────────────────────────────
    print("\n[3/5] Downloading Titillium Web fonts and building HTML template…")
    run_step([PYTHON, str(FETCH_FONTS_SCRIPT)], show_cmd=True)
    run_step([PYTHON, str(WRITE_TEMPLATE_SCRIPT)], show_cmd=True)
    print("      Done.")

    # ── Step 4: First wallpaper ───────────────────────────────────────────────
    print("\n[4/5] Generating your first F1 wallpaper…")
    run_step([PYTHON, str(GENERATE_SCRIPT)], show_cmd=True)
    print("      Wallpaper set!")

    # ── Step 5: Auto-update ───────────────────────────────────────────────────
    print("\n[5/5] Registering auto-update job…")
    run_step([PYTHON, str(AUTO_UPDATE_SCRIPT)], show_cmd=True)

    # ── Done ──────────────────────────────────────────────────────────────────
    print()
    print("=" * 58)
    print("   Setup complete!")
    print()
    print("   Your desktop now shows the next F1 race.")
    print("   The wallpaper updates automatically after each race:")
    print("     • Every time you log in to Windows")
    print("     • Every day at 9:00 AM")
    print()
    print("   To update manually:")
    print("     python scripts/generate_wallpaper.py")
    print("=" * 58)
    print()


if __name__ == "__main__":
    main()
