"""
setup_auto_update.py
Registers an auto-update job so the F1 wallpaper refreshes automatically
at every login and once daily at 9 AM.

  Windows  → Windows Task Scheduler
  macOS    → launchd (~/Library/LaunchAgents plist)
  Linux    → crontab (daily) + ~/.config/autostart (login)

Run once (called automatically by setup.py):
    python scripts/setup_auto_update.py

To remove later:
  Windows:  schtasks /Delete /TN F1WallpaperAutoUpdate /F
  macOS:    launchctl unload ~/Library/LaunchAgents/com.f1wallpaper.autoupdate.plist
  Linux:    crontab -e  (delete the F1Wallpaper line)
            rm ~/.config/autostart/f1-wallpaper.desktop
"""
from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path

PLATFORM     = platform.system()
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT       = PROJECT_ROOT / "scripts" / "generate_wallpaper.py"
TASK_NAME    = "F1WallpaperAutoUpdate"

# Use the project venv Python if it exists, otherwise fall back to current interpreter
_venv_bin    = "Scripts" if PLATFORM == "Windows" else "bin"
_venv_exe    = "python.exe" if PLATFORM == "Windows" else "python"
_venv_python = PROJECT_ROOT / ".venv" / _venv_bin / _venv_exe
PYTHON       = str(_venv_python) if _venv_python.exists() else sys.executable


# ── Windows ───────────────────────────────────────────────────────────────────

def _setup_windows() -> None:
    launcher_path = PROJECT_ROOT / "scripts" / "run_wallpaper.bat"
    log_path = PROJECT_ROOT / "data" / "wallpaper" / "wallpaper.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    launcher_path.write_text(
        f'@echo off\ncd /d "{PROJECT_ROOT}"\n"{PYTHON}" "{SCRIPT}" >> "{log_path}" 2>&1\n',
        encoding="utf-8",
    )

    # Try PowerShell first (supports logon + daily triggers in one task).
    # Falls back to schtasks for daily-only if PowerShell is blocked by policy.
    ps_script = f"""
$ErrorActionPreference = "Stop"
try {{
    $action   = New-ScheduledTaskAction -Execute '"{launcher_path}"'
    $atLogon  = New-ScheduledTaskTrigger -AtLogOn
    $daily    = New-ScheduledTaskTrigger -Daily -At "09:00"
    $settings = New-ScheduledTaskSettingsSet `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
        -StartWhenAvailable `
        -MultipleInstances IgnoreNew
    $principal = New-ScheduledTaskPrincipal `
        -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
        -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask `
        -TaskName   "{TASK_NAME}" `
        -Action     $action `
        -Trigger    $atLogon, $daily `
        -Settings   $settings `
        -Principal  $principal `
        -Force | Out-Null
    Write-Host "OK"
}} catch {{
    Write-Host "FAILED: $_"
}}
"""
    result = subprocess.run(
        ["powershell", "-NonInteractive", "-NoProfile", "-Command", ps_script],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and "OK" in result.stdout:
        print(f"  Task Scheduler: '{TASK_NAME}' registered (logon + daily 9 AM).")
        print(f"  To remove: schtasks /Delete /TN {TASK_NAME} /F")
        return

    # PowerShell failed — fall back to schtasks for daily-only trigger
    print(f"  [warn] PowerShell registration failed, trying schtasks fallback…")
    if result.stderr.strip():
        print(f"         {result.stderr.strip()}")
    fallback = subprocess.run(
        ["schtasks", "/Create", "/TN", TASK_NAME,
         "/TR", str(launcher_path), "/SC", "DAILY", "/ST", "09:00", "/F"],
        capture_output=True, text=True,
    )
    if fallback.returncode == 0:
        print(f"  Task Scheduler: '{TASK_NAME}' registered (daily 9 AM only — logon trigger requires admin).")
        print(f"  To remove: schtasks /Delete /TN {TASK_NAME} /F")
    else:
        print(f"  [error] schtasks also failed:\n{fallback.stderr.strip()}")
        print(f"  Run setup_auto_update.py as Administrator to register the task.")


# ── macOS ─────────────────────────────────────────────────────────────────────

def _setup_macos() -> None:
    plist_dir  = Path.home() / "Library" / "LaunchAgents"
    plist_path = plist_dir / "com.f1wallpaper.autoupdate.plist"
    plist_dir.mkdir(parents=True, exist_ok=True)

    log_path = PROJECT_ROOT / "data" / "wallpaper" / "launchd.log"
    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.f1wallpaper.autoupdate</string>
    <key>ProgramArguments</key>
    <array>
        <string>{PYTHON}</string>
        <string>{SCRIPT}</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>   <integer>9</integer>
        <key>Minute</key> <integer>0</integer>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log_path}</string>
    <key>StandardErrorPath</key>
    <string>{log_path}</string>
</dict>
</plist>
"""
    plist_path.write_text(plist_content, encoding="utf-8")

    # Unload any existing version first, then load the updated plist
    subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
    result = subprocess.run(
        ["launchctl", "load", str(plist_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"  [warn] launchctl: {result.stderr.strip()}")
        return
    print(f"  launchd: plist loaded from {plist_path}")
    print(f"  To remove: launchctl unload {plist_path} && rm {plist_path}")


# ── Linux ─────────────────────────────────────────────────────────────────────

def _setup_linux() -> None:
    # 1. Daily cron job at 9 AM
    cron_line = f'0 9 * * * "{PYTHON}" "{SCRIPT}"  # F1Wallpaper\n'
    existing_cron = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    current_entries = existing_cron.stdout if existing_cron.returncode == 0 else ""
    if "F1Wallpaper" not in current_entries:
        new_crontab = current_entries.rstrip("\n") + "\n" + cron_line
        subprocess.run(["crontab", "-"], input=new_crontab, text=True, check=True)
        print("  crontab: daily 9 AM job added.")
    else:
        print("  crontab: job already present.")

    # 2. Login autostart via XDG .desktop file
    autostart_dir = Path.home() / ".config" / "autostart"
    autostart_dir.mkdir(parents=True, exist_ok=True)
    desktop_file = autostart_dir / "f1-wallpaper.desktop"
    desktop_file.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=F1 Wallpaper Auto-Update\n"
        f'Exec="{PYTHON}" "{SCRIPT}"\n'
        "Hidden=false\n"
        "NoDisplay=false\n"
        "X-GNOME-Autostart-enabled=true\n",
        encoding="utf-8",
    )
    print(f"  autostart: {desktop_file}")
    print("  To remove: crontab -e  (delete F1Wallpaper line)")
    print(f"             rm {desktop_file}")


# ── Dependencies ──────────────────────────────────────────────────────────────

def _install_dependencies() -> None:
    venv_dir    = PROJECT_ROOT / ".venv"
    venv_python = venv_dir / _venv_bin / _venv_exe

    if not venv_dir.exists():
        print("  Creating virtual environment…")
        result = subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"  [error] venv creation failed:\n{result.stderr.strip()}")
            return
        print(f"  Virtual environment created at {venv_dir}")

    requirements = PROJECT_ROOT / "install" / "requirements_wallpaper.txt"
    if not requirements.exists():
        print(f"  [warn] requirements file not found: {requirements}")
        return
    print("  Installing Python dependencies…")
    pip_result = subprocess.run(
        [str(venv_python), "-m", "pip", "install", "-r", str(requirements)],
        capture_output=True, text=True,
    )
    if pip_result.returncode != 0:
        print(f"  [error] pip install failed:\n{pip_result.stderr.strip()}")
    else:
        print("  Dependencies installed.")

    print("  Installing Playwright Chromium browser…")
    pw_result = subprocess.run(
        [str(venv_python), "-m", "playwright", "install", "chromium"],
        capture_output=True, text=True,
    )
    if pw_result.returncode != 0:
        print(f"  [error] playwright install failed:\n{pw_result.stderr.strip()}")
    else:
        print("  Playwright Chromium installed.")


# ── Dispatcher ────────────────────────────────────────────────────────────────

def main() -> None:
    _install_dependencies()
    print(f"  Platform: {PLATFORM}")
    if PLATFORM == "Windows":
        _setup_windows()
    elif PLATFORM == "Darwin":
        _setup_macos()
    elif PLATFORM == "Linux":
        _setup_linux()
    else:
        print(f"  [warn] Unsupported platform '{PLATFORM}' — skipping auto-update setup.")
        print(f"  Run manually: python \"{SCRIPT}\"")


if __name__ == "__main__":
    main()
