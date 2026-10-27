"""
wallpaper_data.py
Fetches next-race data, full championship standings, and circuit SVG from public APIs.
Returns a WallpaperData dataclass ready for template injection.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

BASE = "https://api.jolpi.ca/ergast/f1"
# Pin the map data revision so the API remains reproducible if its default branch changes.
TRACK_ATLAS_BASE = (
    "https://raw.githubusercontent.com/tobi/track-atlas/"
    "8c12ac414ea74ffe4a3ef74b294a2eafab7ee60d/tracks"
)

# Map country name (from API) → ISO 3166-1 alpha-2 code (for flag images)
COUNTRY_ISO_MAP: dict[str, str] = {
    "Australia":              "AU",
    "Bahrain":                "BH",
    "China":                  "CN",
    "Saudi Arabia":           "SA",
    "Japan":                  "JP",
    "USA":                    "US",
    "United States":          "US",
    "Italy":                  "IT",
    "Monaco":                 "MC",
    "Canada":                 "CA",
    "Spain":                  "ES",
    "Austria":                "AT",
    "UK":                     "GB",
    "United Kingdom":         "GB",
    "Hungary":                "HU",
    "Belgium":                "BE",
    "Netherlands":            "NL",
    "Singapore":              "SG",
    "Azerbaijan":             "AZ",
    "Mexico":                 "MX",
    "Brazil":                 "BR",
    "UAE":                    "AE",
    "United Arab Emirates":   "AE",
    "Qatar":                  "QA",
    "Portugal":               "PT",
    "Turkey":                 "TR",
    "Russia":                 "RU",
    "South Korea":            "KR",
    "Germany":                "DE",
    "France":                 "FR",
    "Argentina":              "AR",
    "South Africa":           "ZA",
}

# Map Jolpica circuit IDs to Track Atlas track slugs.
CIRCUIT_TRACK_MAP: dict[str, str] = {
    "albert_park":   "melbourne",
    "americas":      "circuit-of-the-americas",
    "bahrain":       "bahrain",
    "baku":          "baku",
    "catalunya":     "barcelona",
    "hungaroring":   "hungaroring",
    "imola":         "imola",
    "interlagos":    "interlagos",
    "jeddah":        "jeddah",
    "losail":        "losail",
    "marina_bay":    "singapore",
    "miami":         "miami",
    "monaco":        "monaco",
    "monza":         "monza",
    "mugello":       "mugello",
    "portimao":      "portimao",
    "red_bull_ring": "red-bull-ring",
    "rodriguez":     "mexico-city",
    "shanghai":      "shanghai",
    "silverstone":   "silverstone",
    "spa":           "spa-francorchamps",
    "suzuka":        "suzuka",
    "vegas":         "las-vegas",
    "villeneuve":    "montreal",
    "yas_marina":    "yas-marina",
    "zandvoort":     "zandvoort",
}


def _circuit_svg_from_geojson(geojson: dict) -> str:
    """Render a GeoJSON circuit outline as a compact, CSS-styled SVG."""
    feature = next(
        (
            item for item in geojson.get("features", [])
            if item.get("properties", {}).get("role") == "outline"
            and item.get("geometry", {}).get("type") == "LineString"
        ),
        None,
    )
    coordinates = feature["geometry"].get("coordinates", []) if feature else []
    if len(coordinates) < 2:
        raise ValueError("Circuit GeoJSON has no usable outline.")

    points = [(float(point[0]), float(point[1])) for point in coordinates]
    center_lat = sum(latitude for _, latitude in points) / len(points)
    longitude_scale = math.cos(math.radians(center_lat))
    projected = [(longitude * longitude_scale, latitude) for longitude, latitude in points]
    min_x = min(x for x, _ in projected)
    max_x = max(x for x, _ in projected)
    min_y = min(y for _, y in projected)
    max_y = max(y for _, y in projected)

    width, height, padding = 180, 220, 12
    track_width, track_height = max_x - min_x, max_y - min_y
    if track_width <= 0 or track_height <= 0:
        raise ValueError("Circuit GeoJSON outline has no area.")
    scale = min((width - padding * 2) / track_width, (height - padding * 2) / track_height)
    offset_x = (width - track_width * scale) / 2
    offset_y = (height - track_height * scale) / 2
    path_points = [
        f"{offset_x + (x - min_x) * scale:.1f},{height - offset_y - (y - min_y) * scale:.1f}"
        for x, y in projected
    ]
    path_data = "M " + " L ".join(path_points)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 180 220">'
        f'<path d="{path_data}" stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg>"
    )


# Ordered session fields to check on the race object (Race itself is at the top level)
SESSION_FIELDS: list[tuple[str, str]] = [
    ("Free Practice 1",   "FirstPractice"),
    ("Sprint Qualifying", "SprintQualifying"),
    ("Free Practice 2",   "SecondPractice"),
    ("Sprint",            "Sprint"),
    ("Qualifying",        "Qualifying"),
]


@dataclass
class SessionTime:
    label: str
    local_dt: datetime
    is_past: bool
    is_race: bool = False


@dataclass
class DriverStanding:
    position: str
    code: str
    name: str
    team: str
    points: str
    team_id: str = ""


@dataclass
class ConstructorStanding:
    position: str
    name: str
    points: str
    con_id: str = ""


@dataclass
class WallpaperData:
    race_name: str
    circuit_name: str
    country: str
    country_iso: str
    round_number: str
    year: str
    race_date_local: datetime
    sessions: list[SessionTime]
    driver_standings: list[DriverStanding]
    constructor_standings: list[ConstructorStanding]
    circuit_svg: str
    local_tz_name: str


def _get_json(url: str) -> dict:
    for attempt in range(3):
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException:
            if attempt == 2:
                raise
            delay = 5 * (attempt + 1)
            print(f"      [warn] API request failed; retrying in {delay}s: {url}")
            time.sleep(delay)
    raise RuntimeError(f"Unable to fetch JSON after retries: {url}")


def _parse_utc(date: str, time: str | None) -> datetime:
    """Parse a Jolpica date + optional time string into a UTC-aware datetime."""
    time = time or "00:00:00Z"
    raw = f"{date}T{time}".replace("Z", "+00:00")
    return datetime.fromisoformat(raw)


def _to_local(utc_dt: datetime, local_tz) -> datetime:
    return utc_dt.astimezone(local_tz)


def _get_local_tz() -> ZoneInfo | None:
    """Get the local timezone as a ZoneInfo object for proper abbreviations."""
    try:
        import time
        if hasattr(time, "tzname") and time.tzname[0]:
            # On Windows, time.tzname gives e.g. ('Pacific Standard Time', 'Pacific Daylight Time')
            # Map common Windows timezone names to IANA identifiers
            _WIN_TO_IANA = {
                "Pacific Standard Time": "America/Los_Angeles",
                "Mountain Standard Time": "America/Denver",
                "Central Standard Time": "America/Chicago",
                "Eastern Standard Time": "America/New_York",
                "Alaska Standard Time": "America/Anchorage",
                "Hawaiian Standard Time": "Pacific/Honolulu",
                "GMT Standard Time": "Europe/London",
                "Central European Standard Time": "Europe/Berlin",
                "India Standard Time": "Asia/Kolkata",
                "China Standard Time": "Asia/Shanghai",
                "Tokyo Standard Time": "Asia/Tokyo",
                "AUS Eastern Standard Time": "Australia/Sydney",
            }
            win_name = time.tzname[0]
            iana_key = _WIN_TO_IANA.get(win_name)
            if iana_key:
                return ZoneInfo(iana_key)
    except Exception:
        pass
    return None


def fetch_wallpaper_data() -> WallpaperData | None:
    local_tz = _get_local_tz() or datetime.now(timezone.utc).astimezone().tzinfo
    now_local = datetime.now(local_tz)

    # ── Next race ──────────────────────────────────────────────────────────────
    next_race_data = _get_json(f"{BASE}/current/next.json")
    races = next_race_data["MRData"]["RaceTable"]["Races"]
    if not races:
        print("  [warn] No upcoming race found in API response — skipping update.")
        return None
    race = races[0]

    race_name: str    = race["raceName"]
    circuit_name: str = race["Circuit"]["circuitName"]
    circuit_id: str   = race["Circuit"]["circuitId"]
    country: str      = race["Circuit"]["Location"]["country"]
    round_number: str = race["round"]
    year: str         = race.get("season", str(datetime.now().year))
    country_iso: str  = COUNTRY_ISO_MAP.get(country, "")

    race_utc        = _parse_utc(race["date"], race.get("time"))
    race_date_local = _to_local(race_utc, local_tz)

    # ── Sessions ───────────────────────────────────────────────────────────────
    sessions: list[SessionTime] = []
    for label, field_name in SESSION_FIELDS:
        session_info = race.get(field_name)
        if session_info is None:
            continue
        session_date = session_info.get("date")
        session_time = session_info.get("time")
        if not session_date:
            continue
        utc_dt   = _parse_utc(session_date, session_time)
        local_dt = _to_local(utc_dt, local_tz)
        is_past  = local_dt < now_local
        sessions.append(SessionTime(label=label, local_dt=local_dt, is_past=is_past, is_race=False))

    # Race date/time lives at the top-level of the race object, not in a sub-object
    race_is_past = race_date_local < now_local
    sessions.append(SessionTime(
        label="Race",
        local_dt=race_date_local,
        is_past=race_is_past,
        is_race=True,
    ))

    # ── Driver standings (all) ─────────────────────────────────────────────────
    driver_data = _get_json(f"{BASE}/current/driverStandings.json")
    driver_entries = driver_data["MRData"]["StandingsTable"]["StandingsLists"][0]["DriverStandings"]
    driver_standings: list[DriverStanding] = []
    for entry in driver_entries:
        driver       = entry["Driver"]
        constructors = entry.get("Constructors") or []
        team         = constructors[0]["name"] if constructors else ""
        team_id      = constructors[0].get("constructorId", "") if constructors else ""
        driver_standings.append(DriverStanding(
            position=entry.get("position") or entry.get("positionText", "?"),
            code=driver.get("code", driver["familyName"][:3].upper()),
            name=f"{driver['givenName']} {driver['familyName']}",
            team=team,
            points=entry["points"],
            team_id=team_id,
        ))

    # ── Constructor standings (all) ────────────────────────────────────────────
    constructor_data    = _get_json(f"{BASE}/current/constructorStandings.json")
    constructor_entries = constructor_data["MRData"]["StandingsTable"]["StandingsLists"][0]["ConstructorStandings"]
    constructor_standings: list[ConstructorStanding] = []
    for entry in constructor_entries:
        constructor_standings.append(ConstructorStanding(
            position=entry.get("position") or entry.get("positionText", "?"),
            name=entry["Constructor"]["name"],
            points=entry["points"],
            con_id=entry["Constructor"].get("constructorId", ""),
        ))

    # ── Circuit SVG ────────────────────────────────────────────────────────────
    circuit_svg = ""
    track_slug = CIRCUIT_TRACK_MAP.get(circuit_id)
    if track_slug is None:
        print(f"      [warn] No circuit map configured for circuit ID '{circuit_id}'.")
    else:
        geojson_url = f"{TRACK_ATLAS_BASE}/{track_slug}/raw/layers/gp.geojson"
        try:
            response = requests.get(geojson_url, timeout=10)
            response.raise_for_status()
            circuit_svg = _circuit_svg_from_geojson(response.json())
        except (requests.exceptions.RequestException, ValueError, KeyError, TypeError) as exc:
            print(f"      [warn] Circuit map fetch failed ({geojson_url}): {exc}")

    # ── Timezone abbreviation (PST / PDT / EST etc.) ───────────────────────────
    local_tz_name = now_local.strftime("%Z")

    return WallpaperData(
        race_name=race_name,
        circuit_name=circuit_name,
        country=country,
        country_iso=country_iso,
        round_number=round_number,
        year=year,
        race_date_local=race_date_local,
        sessions=sessions,
        driver_standings=driver_standings,
        constructor_standings=constructor_standings,
        circuit_svg=circuit_svg,
        local_tz_name=local_tz_name,
    )


if __name__ == "__main__":
    data = fetch_wallpaper_data()
    if data is None:
        print("No upcoming race data.")
    else:
        print(f"Race: {data.race_name}")
        print(f"Drivers: {len(data.driver_standings)}, Constructors: {len(data.constructor_standings)}")
