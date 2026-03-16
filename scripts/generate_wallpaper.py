"""
generate_wallpaper.py
Fetches F1 data, renders the HTML template via Playwright headless Chromium,
and sets the result as the desktop wallpaper.

Supports: Windows, macOS, Linux (GNOME, KDE, XFCE, i3/feh)

Usage:
    python3 scripts/generate_wallpaper.py
"""
from __future__ import annotations

import os
import platform
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from wallpaper_data import (
    ConstructorStanding,
    DriverStanding,
    SessionTime,
    WallpaperData,
    fetch_wallpaper_data,
)

PLATFORM = platform.system()  # "Windows" | "Darwin" | "Linux"

# Team colors keyed by Jolpica constructorId
TEAM_COLORS: dict[str, str] = {
    "mercedes":      "#00D2BE",
    "ferrari":       "#DC0000",
    "mclaren":       "#FF8000",
    "red_bull":      "#3671C6",
    "haas":          "#B6BABD",
    "rb":            "#6692FF",
    "audi":          "#900000",
    "alpine":        "#0090FF",
    "williams":      "#005AFF",
    "cadillac":      "#CCCCCC",
    "aston_martin":  "#229971",
    "racing_bulls":  "#6692FF",
    "sauber":        "#52C832",
    "kick_sauber":   "#52C832",
}

PROJECT_ROOT  = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = PROJECT_ROOT / "dashboard" / "wallpaper_template.html"
SNIPPETS_DIR  = PROJECT_ROOT / "dashboard" / "snippets"
OUTPUT_DIR    = PROJECT_ROOT / "data" / "wallpaper"
OUTPUT_PNG    = OUTPUT_DIR / "wallpaper_current.png"
RENDER_HTML   = OUTPUT_DIR / "wallpaper_render.html"


# ── Date / time helpers ────────────────────────────────────────────────────────

def _ordinal(n: int) -> str:
    """Return the ordinal string for an integer (1 → '1st', 11 → '11th', etc.)."""
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    return {1: f"{n}st", 2: f"{n}nd", 3: f"{n}rd"}.get(n % 10, f"{n}th")


def _fmt_time_parts(dt: datetime) -> tuple[str, str, str, str]:
    """Extract formatted time components shared by both date-format functions."""
    hour   = str(int(dt.strftime("%I")))  # Strip leading zero from 12-hour clock
    minute = dt.strftime("%M")
    ampm   = dt.strftime("%p")
    tz     = dt.strftime("%Z")
    return hour, minute, ampm, tz


def _fmt_session_time(dt: datetime) -> str:
    """Format a session datetime as 'Wed 16th Mar · 3:00 PM PST'."""
    hour, minute, ampm, tz = _fmt_time_parts(dt)
    day_ord = _ordinal(dt.day)
    return f"{dt.strftime('%a')} {day_ord} {dt.strftime('%b')} · {hour}:{minute} {ampm} {tz}"


def _fmt_race_date(dt: datetime) -> str:
    """Format the race datetime as 'Sunday, 16th March 2025 · 3:00 PM PST'."""
    hour, minute, ampm, tz = _fmt_time_parts(dt)
    day_ord = _ordinal(dt.day)
    return f"{dt.strftime('%A')}, {day_ord} {dt.strftime('%B %Y')} · {hour}:{minute} {ampm} {tz}"


# ── HTML snippet loader ────────────────────────────────────────────────────────

def _load_snippet(name: str) -> str:
    """Read an HTML snippet file from the snippets directory."""
    return (SNIPPETS_DIR / name).read_text(encoding="utf-8").strip()


# ── HTML builders ──────────────────────────────────────────────────────────────

def _build_sessions_html(sessions: list[SessionTime]) -> str:
    """Fill the session_row snippet for each session and join into a list."""
    snippet = _load_snippet("session_row.html")
    rows: list[str] = []
    for session in sessions:
        if session.is_past:
            css_class = "past"
        elif session.is_race:
            css_class = "race-day"
        else:
            css_class = ""
        rows.append(
            snippet
            .replace("{CSS_CLASS}", css_class)
            .replace("{LABEL}",     session.label)
            .replace("{TIME}",      _fmt_session_time(session.local_dt))
        )
    return "\n".join(rows)


def _build_driver_standings_html(standings: list[DriverStanding]) -> str:
    """Fill the driver_row snippet for each driver standing."""
    snippet = _load_snippet("driver_row.html")
    rows: list[str] = []
    for standing in standings:
        rows.append(
            snippet
            .replace("{LEADER_CLASS}", " leader" if standing.position == "1" else "")
            .replace("{POSITION}",     standing.position)
            .replace("{TEAM_COLOR}",   TEAM_COLORS.get(standing.team_id, "#555566"))
            .replace("{CODE}",         standing.code)
            .replace("{NAME}",         standing.name)
            .replace("{TEAM}",         standing.team)
            .replace("{POINTS}",       standing.points)
        )
    return "\n".join(rows)


def _build_constructor_standings_html(standings: list[ConstructorStanding]) -> str:
    """Fill the constructor_row snippet for each constructor standing."""
    snippet = _load_snippet("constructor_row.html")
    rows: list[str] = []
    for standing in standings:
        rows.append(
            snippet
            .replace("{LEADER_CLASS}", " leader" if standing.position == "1" else "")
            .replace("{POSITION}",     standing.position)
            .replace("{TEAM_COLOR}",   TEAM_COLORS.get(standing.con_id, "#555566"))
            .replace("{NAME}",         standing.name)
            .replace("{POINTS}",       standing.points)
        )
    return "\n".join(rows)


def _prepare_circuit_svg(raw_svg: str) -> str:
    """Ensure the SVG has a viewBox and no explicit width/height so CSS controls sizing."""
    svg = raw_svg
    if 'viewBox' not in svg:
        width_match  = re.search(r'<svg[^>]+width="([^"]+)"',  svg)
        height_match = re.search(r'<svg[^>]+height="([^"]+)"', svg)
        if width_match and height_match:
            svg = svg.replace(
                '<svg ',
                f'<svg viewBox="0 0 {width_match.group(1)} {height_match.group(1)}" ',
                1,
            )
    svg = re.sub(r'\s+width="[^"]*"',  '', svg, count=1)
    svg = re.sub(r'\s+height="[^"]*"', '', svg, count=1)
    return svg


def _inject_template(template: str, data: WallpaperData) -> str:
    sessions_html = _build_sessions_html(data.sessions)
    driver_html   = _build_driver_standings_html(data.driver_standings)
    con_html      = _build_constructor_standings_html(data.constructor_standings)

    if data.circuit_svg.strip():
        circuit_svg_html = _prepare_circuit_svg(data.circuit_svg)
    else:
        circuit_svg_html = _load_snippet("circuit_unavailable.html")

    replacements = {
        "{{RACE_NAME}}":                  data.race_name,
        "{{CIRCUIT_NAME}}":               data.circuit_name,
        "{{COUNTRY}}":                    data.country,
        "{{COUNTRY_ISO}}":                data.country_iso,
        "{{COUNTRY_ISO_LOWER}}":          data.country_iso.lower(),
        "{{ROUND_NUMBER}}":               data.round_number,
        "{{YEAR}}":                       data.year,
        "{{RACE_DATE_LOCAL}}":            _fmt_race_date(data.race_date_local),
        "{{LOCAL_TZ_NAME}}":              data.local_tz_name,
        "{{CIRCUIT_SVG}}":                circuit_svg_html,
        "{{SESSIONS_HTML}}":              sessions_html,
        "{{DRIVER_STANDINGS_HTML}}":      driver_html,
        "{{CONSTRUCTOR_STANDINGS_HTML}}": con_html,
    }

    result = template
    for token, value in replacements.items():
        result = result.replace(token, value)
    return result


# ── Playwright render ──────────────────────────────────────────────────────────

def render_png(html_path: Path, output_path: Path,
               viewport_w: int = 1920, viewport_h: int = 1080) -> None:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": viewport_w, "height": viewport_h},
            device_scale_factor=2,  # 2x → high-DPI output
        )
        page.goto(html_path.as_uri(), wait_until="networkidle")
        page.screenshot(path=str(output_path), full_page=False)
        browser.close()


# ── Wallpaper setters (per platform) ──────────────────────────────────────────

def _set_wallpaper_windows(png_path: Path) -> None:
    import ctypes
    import winreg

    abs_path = str(png_path.resolve())

    # Set background fill color (#0f1117) in registry and immediately via SetSysColors
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Control Panel\Colors",
            0, winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, "Background", 0, winreg.REG_SZ, "15 17 23")
        colorref = 15 | (17 << 8) | (23 << 16)
        ctypes.windll.user32.SetSysColors(
            1,
            (ctypes.c_int    * 1)(1),
            (ctypes.c_uint32 * 1)(colorref),
        )
    except Exception as exc:
        print(f"      [warn] bg color: {exc}")

    # Wallpaper fit mode: scale to fill width (style 6), no tiling
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop",
            0, winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, "WallpaperStyle", 0, winreg.REG_SZ, "6")
            winreg.SetValueEx(key, "TileWallpaper",  0, winreg.REG_SZ, "0")
    except Exception as exc:
        print(f"      [warn] wallpaper style: {exc}")

    # SPI_SETDESKWALLPAPER = 20, SPIF_UPDATEINIFILE | SPIF_SENDCHANGE = 3
    result = ctypes.windll.user32.SystemParametersInfoW(20, 0, abs_path, 3)
    if not result:
        raise OSError(f"SystemParametersInfoW failed: {abs_path}")


def _get_macos_screen_size() -> tuple[int, int] | None:
    """Return (width, height) in logical pixels using Finder bounds."""
    try:
        result = subprocess.run(
            ["osascript", "-e",
             'tell application "Finder" to return bounds of window of desktop'],
            capture_output=True, text=True, check=True,
        )
        parts = [p.strip() for p in result.stdout.strip().split(",")]
        w, h = int(parts[2]), int(parts[3])
        return (w, h) if w > 0 and h > 0 else None
    except Exception:
        return None


def _set_wallpaper_macos(png_path: Path) -> None:
    abs_path = str(png_path.resolve())
    # Simple one-liner — avoids picture scale syntax errors on macOS 13+.
    # The image is pre-rendered at the screen's aspect ratio so macOS default
    # fill behavior displays it perfectly with no cropping.
    script = (
        'tell application "System Events" to '
        f'set picture of every desktop to POSIX file "{abs_path}"'
    )
    subprocess.run(["osascript", "-e", script], check=True)


def _set_wallpaper_linux(png_path: Path) -> None:
    abs_path    = str(png_path.resolve())
    desktop_env = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    session_env = os.environ.get("DESKTOP_SESSION",     "").lower()

    if any(de in desktop_env or de in session_env for de in ("gnome", "unity", "budgie")):
        uri = f"file://{abs_path}"
        subprocess.run(["gsettings", "set", "org.gnome.desktop.background",
                        "picture-uri", uri])
        subprocess.run(["gsettings", "set", "org.gnome.desktop.background",
                        "picture-uri-dark", uri])
        subprocess.run(["gsettings", "set", "org.gnome.desktop.background",
                        "picture-options", "zoom"])
    elif "kde" in desktop_env or "kde" in session_env or "plasma" in desktop_env or "plasma" in session_env:
        subprocess.run(["plasma-apply-wallpaperimage", abs_path])
    elif "xfce" in desktop_env or "xfce" in session_env:
        subprocess.run(["xfconf-query", "--channel", "xfce4-desktop",
                        "--property", "/backdrop/screen0/monitor0/workspace0/last-image",
                        "--set", abs_path])
    else:
        # Generic fallback — feh works in most minimal/tiling WMs
        result = subprocess.run(["feh", "--bg-fill", abs_path])
        if result.returncode != 0:
            print(f"      [warn] Could not set wallpaper automatically.")
            print(f"      PNG saved to: {abs_path}")


def set_wallpaper(png_path: Path) -> None:
    try:
        if PLATFORM == "Windows":
            _set_wallpaper_windows(png_path)
        elif PLATFORM == "Darwin":
            _set_wallpaper_macos(png_path)
        elif PLATFORM == "Linux":
            _set_wallpaper_linux(png_path)
        else:
            print(f"      [warn] Unsupported platform '{PLATFORM}'.")
            print(f"      PNG saved to: {png_path.resolve()}")
    except Exception as exc:
        print(f"      [warn] Could not set wallpaper automatically: {exc}")
        if PLATFORM == "Darwin":
            print("      To fix: System Settings → Privacy & Security → Automation")
            print("      → enable Terminal (or your shell) to control System Events.")
        print(f"      Wallpaper PNG saved to: {png_path.resolve()}")
        print("      You can set it manually as your desktop background.")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    print("[1/4] Fetching F1 data from Jolpica API…")
    data = fetch_wallpaper_data()
    if data is None:
        print("      Skipping wallpaper generation (no upcoming race data).")
        return
    print(f"      Race: {data.race_name} (Round {data.round_number})")
    print(f"      Drivers: {len(data.driver_standings)}  |  Constructors: {len(data.constructor_standings)}")

    print("[2/4] Injecting data into HTML template…")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    template_text = TEMPLATE_PATH.read_text(encoding="utf-8")
    filled_html   = _inject_template(template_text, data)
    RENDER_HTML.write_text(filled_html, encoding="utf-8")

    # On macOS, match the screen's aspect ratio so the image fills the display
    # perfectly regardless of whether it's 16:9, 16:10, etc.
    viewport_w, viewport_h = 1920, 1080
    if PLATFORM == "Darwin":
        screen = _get_macos_screen_size()
        if screen:
            viewport_h = round(1920 * screen[1] / screen[0])

    # Delete the old PNG before rendering so macOS always sees a fresh file at
    # the same path — otherwise System Events skips the update (path unchanged).
    if OUTPUT_PNG.exists():
        OUTPUT_PNG.unlink()

    out_w, out_h = viewport_w * 2, viewport_h * 2
    print(f"[3/4] Rendering PNG via Playwright ({out_w}×{out_h})…")
    render_png(RENDER_HTML, OUTPUT_PNG, viewport_w, viewport_h)
    print(f"      Saved: {OUTPUT_PNG}")

    print(f"[4/4] Setting desktop wallpaper ({PLATFORM})…")
    set_wallpaper(OUTPUT_PNG)
    print("      Done.")


if __name__ == "__main__":
    main()
