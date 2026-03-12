"""
Builds dashboard/wallpaper_template.html from its source file.

Reads the source HTML (wallpaper_template_src.html), embeds the F1 logo
and Titillium Web fonts as base64 data URIs, and writes the result to
wallpaper_template.html for use by generate_wallpaper.py.

Run whenever the source HTML, logo, or fonts change:
    python scripts/_write_template.py

To (re)download the font files first:
    python scripts/_fetch_fonts.py
"""
import base64
import pathlib

ROOT          = pathlib.Path(__file__).resolve().parent.parent
LOGO_PATH     = ROOT / "data" / "wallpaper" / "f1_logo.png"
FONTS_DIR     = ROOT / "data" / "fonts"
SOURCE_PATH   = ROOT / "dashboard" / "wallpaper_template_src.html"
TEMPLATE_PATH = ROOT / "dashboard" / "wallpaper_template.html"

# Font weights to embed: placeholder token → filename in data/fonts/
FONT_FILES = {
    "FONT_400_PLACEHOLDER": "titillium-400.ttf",
    "FONT_600_PLACEHOLDER": "titillium-600.ttf",
    "FONT_700_PLACEHOLDER": "titillium-700.ttf",
}


def build_data_uri(path: pathlib.Path, mime: str) -> str:
    """Read a binary file and return a base64-encoded data URI."""
    encoded = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{encoded}"


def main() -> None:
    html = SOURCE_PATH.read_text(encoding="utf-8")

    # Embed F1 logo
    html = html.replace("F1_LOGO_URI_PLACEHOLDER", build_data_uri(LOGO_PATH, "image/png"))

    # Embed each font weight
    for placeholder, filename in FONT_FILES.items():
        html = html.replace(placeholder, build_data_uri(FONTS_DIR / filename, "font/ttf"))

    TEMPLATE_PATH.write_text(html, encoding="utf-8")
    print("Template written:", len(html), "bytes")


if __name__ == "__main__":
    main()
