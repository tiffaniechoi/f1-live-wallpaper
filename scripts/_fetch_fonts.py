"""
Downloads Titillium Web font weights (400, 600, 700) from Google Fonts
and saves them as TTF files in data/fonts/.

Run once to populate the fonts directory:
    python scripts/_fetch_fonts.py
"""
import pathlib
import requests

FONT_URLS = {
    "titillium-400.ttf": "https://fonts.gstatic.com/s/titilliumweb/v19/NaPecZTIAOhVxoMyOr9n_E7fRMQ.ttf",
    "titillium-600.ttf": "https://fonts.gstatic.com/s/titilliumweb/v19/NaPDcZTIAOhVxoMyOr9n_E7ffBzCKIw.ttf",
    "titillium-700.ttf": "https://fonts.gstatic.com/s/titilliumweb/v19/NaPDcZTIAOhVxoMyOr9n_E7ffHjDKIw.ttf",
}

FONTS_DIR = pathlib.Path(__file__).resolve().parent.parent / "data" / "fonts"


def main() -> None:
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    for filename, url in FONT_URLS.items():
        dest = FONTS_DIR / filename
        if dest.exists():
            print(f"  Already exists: {filename}")
            continue
        print(f"  Downloading {filename}...")
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        dest.write_bytes(response.content)
        print(f"  Saved: {dest}")


if __name__ == "__main__":
    main()
