"""
wallpaper_data.py
Fetches next-race data, full championship standings, and circuit SVG from public APIs.
Returns a WallpaperData dataclass ready for template injection.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import requests
from tzlocal import get_localzone

BASE = "https://api.jolpi.ca/ergast/f1"
# julesr0y/f1-circuits-svg: white-stroke SVGs, reliable source
SVG_BASE = "https://raw.githubusercontent.com/julesr0y/f1-circuits-svg/main/circuits/white"

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

# Map Jolpica circuitId → filename stem in julesr0y repo (latest layout version)
CIRCUIT_SVG_MAP: dict[str, str] = {
    "albert_park":   "melbourne-2",
    "americas":      "austin-1",
    "bahrain":       "bahrain-3",
    "baku":          "baku-1",
    "catalunya":     "catalunya-6",
    "hungaroring":   "hungaroring-3",
    "imola":         "imola-3",
    "interlagos":    "interlagos-2",
    "istanbul":      "istanbul-1",
    "jeddah":        "jeddah-1",
    "losail":        "lusail-1",
    "marina_bay":    "marina-bay-4",
    "miami":         "miami-1",
    "monaco":        "monaco-6",
    "monza":         "monza-7",
    "mugello":       "mugello-1",
    "nurburgring":   "nurburgring-4",
    "portimao":      "portimao-1",
    "red_bull_ring": "spielberg-3",
    "rodriguez":     "mexico-city-3",
    "shanghai":      "shanghai-1",
    "silverstone":   "silverstone-8",
    "sochi":         "sochi-1",
    "spa":           "spa-francorchamps-4",
    "suzuka":        "suzuka-2",
    "vegas":         "las-vegas-1",
    "villeneuve":    "montreal-6",
    "yas_marina":    "yas-marina-2",
    "yeongam":       "yeongam-1",
    "zandvoort":     "zandvoort-4",
}

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
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    return response.json()


def _parse_utc(date: str, time: str | None) -> datetime:
    """Parse a Jolpica date + optional time string into a UTC-aware datetime."""
    time = time or "00:00:00Z"
    raw = f"{date}T{time}".replace("Z", "+00:00")
    return datetime.fromisoformat(raw)


def _to_local(utc_dt: datetime, local_tz) -> datetime:
    return utc_dt.astimezone(local_tz)


def fetch_wallpaper_data() -> WallpaperData:
    local_tz = get_localzone()
    now_local = datetime.now(local_tz)

    # ── Next race ──────────────────────────────────────────────────────────────
    next_race_data = _get_json(f"{BASE}/current/next.json")
    race = next_race_data["MRData"]["RaceTable"]["Races"][0]

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
    try:
        # Fall back to a kebab-case guess if the circuit ID isn't in the map
        svg_stem = CIRCUIT_SVG_MAP.get(circuit_id, f"{circuit_id.replace('_', '-')}-1")
        svg_url  = f"{SVG_BASE}/{svg_stem}.svg"
        svg_response = requests.get(svg_url, timeout=10)
        if svg_response.status_code == 200:
            circuit_svg = svg_response.text
        else:
            print(f"      [warn] Circuit SVG not found ({svg_response.status_code}): {svg_url}")
    except Exception as exc:
        print(f"      [warn] Circuit SVG fetch failed: {exc}")

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
    print(f"Race: {data.race_name}")
    print(f"Drivers: {len(data.driver_standings)}, Constructors: {len(data.constructor_standings)}")
