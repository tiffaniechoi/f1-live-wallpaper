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
PYTHON       = sys.executable
SCRIPT       = PROJECT_ROOT / "scripts" / "generate_wallpaper.py"
TASK_NAME    = "F1WallpaperAutoUpdate"


# ── Windows ───────────────────────────────────────────────────────────────────

def _setup_windows() -> None:
    launcher_path = PROJECT_ROOT / "scripts" / "run_wallpaper.bat"
    launcher_path.write_text(
        f'@echo off\ncd /d "{PROJECT_ROOT}"\n"{PYTHON}" "{SCRIPT}"\n',
        encoding="utf-8",
    )

    # PowerShell script registers two triggers: at logon and daily at 9 AM
    ps_script = f"""
$action   = New-ScheduledTaskAction -Execute '"{launcher_path}"'
$atLogon  = New-ScheduledTaskTrigger -AtLogOn
$daily    = New-ScheduledTaskTrigger -Daily -At "09:00"
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew
Register-ScheduledTask `
    -TaskName   "{TASK_NAME}" `
    -Action     $action `
    -Trigger    $atLogon, $daily `
    -Settings   $settings `
    -RunLevel   Highest `
    -Force | Out-Null
Write-Host "OK"
"""
    result = subprocess.run(
        ["powershell", "-NonInteractive", "-NoProfile", "-Command", ps_script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or "OK" not in result.stdout:
        print(f"  [warn] PowerShell error:\n{result.stderr.strip()}")
        return
    print(f"  Task Scheduler: '{TASK_NAME}' registered.")
    print(f"  To remove: schtasks /Delete /TN {TASK_NAME} /F")


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


# ── Dispatcher ────────────────────────────────────────────────────────────────

def main() -> None:
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
