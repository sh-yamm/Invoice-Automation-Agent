"""Render every Mermaid diagram in docs/diagrams/*.mmd to a PNG beside it, for the README.

The README shows images rather than ```mermaid blocks: GitHub draws Mermaid inside a cross-site frame that
privacy browsers and blockers often block ("Unable to render rich display"). An image shows everywhere.

    py -3.11 scripts/render_diagrams.py            # all diagrams
    py -3.11 scripts/render_diagrams.py 04-pipeline  # one

Needs Playwright with Chromium (pip install playwright; python -m playwright install chromium) and internet
access for the Mermaid script. Prints each image's width in CSS pixels; the README uses it as the img width.
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DIAGRAMS = ROOT / "docs" / "diagrams"
MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.esm.min.mjs"
ELK = "https://cdn.jsdelivr.net/npm/@mermaid-js/layout-elk@0.1.7/dist/mermaid-layout-elk.esm.min.mjs"
PAGE = f"""<!doctype html><html><head><meta charset="utf-8">
<style>body{{margin:0;background:#fff;font-family:Inter,"Segoe UI",Arial,sans-serif}}
#card{{display:inline-block;padding:20px;background:#fff}}</style></head>
<body><div id="card"></div><script type="module">
import mermaid from "{MERMAID}"; import elk from "{ELK}";
mermaid.registerLayoutLoaders(elk); window.mermaid = mermaid;
</script></body></html>"""
CONFIG = {"startOnLoad": False, "theme": "base", "fontFamily": "Inter, Segoe UI, Arial, sans-serif",
          "themeVariables": {"primaryColor": "#FFFFFF", "primaryBorderColor": "#B9A794", "primaryTextColor": "#2E1F17",
                             "lineColor": "#7A6555", "fontSize": "15px", "clusterBkg": "#FDF8F2",
                             "clusterBorder": "#E2CDB8",
                             # pie slices, timeline sections and bar colour
                             "pie1": "#B5502C", "pie2": "#2B5FD9", "pie3": "#1F7F55", "pie4": "#B26A0E",
                             "pie5": "#7A3FC8", "pie6": "#8A7262", "pieStrokeColor": "#FFFFFF",
                             "pieSectionTextColor": "#FFFFFF", "pieOuterStrokeColor": "#FFFFFF",
                             "cScale0": "#FBEEDB", "cScale1": "#E6EDFC", "cScale2": "#E1F2EA",
                             "cScale3": "#ECE6FA", "cScale4": "#F9E3E1",
                             "xyChart": {"plotColorPalette": "#B5502C", "backgroundColor": "#FFFFFF"}},
          "flowchart": {"htmlLabels": True, "curve": "basis", "padding": 12},
          "sequence": {"actorMargin": 24, "width": 120, "boxMargin": 8, "messageMargin": 28}}


def render(names: list[str]) -> None:
    sources = sorted(DIAGRAMS.glob("*.mmd"))
    if names:
        sources = [s for s in sources if s.stem in names]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1200}, device_scale_factor=2)
        page.set_content(PAGE)
        page.wait_for_function("window.mermaid !== undefined", timeout=60_000)
        page.evaluate(f"mermaid.initialize({json.dumps(CONFIG)})")
        for src in sources:
            result = page.evaluate("""async (code) => {
                const card = document.getElementById('card');
                const { svg } = await mermaid.render('d' + Date.now(), code);
                card.innerHTML = svg;
                const el = card.querySelector('svg');
                const box = el.viewBox.baseVal;           // the diagram's natural size
                const w = Math.min(box.width, 1400);
                el.style.maxWidth = 'none';
                el.setAttribute('width', w);
                el.setAttribute('height', box.height * w / box.width);
                return card.getBoundingClientRect().width;
            }""", src.read_text(encoding="utf-8"))
            out = src.with_suffix(".png")
            page.locator("#card").screenshot(path=str(out))
            print(f"{src.stem}: {round(result)} px wide -> {out.relative_to(ROOT)}")
        browser.close()


if __name__ == "__main__":
    render(sys.argv[1:])
