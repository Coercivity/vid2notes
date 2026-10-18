import re
from io import BytesIO
from pathlib import Path

import verovio
from pypdf import PdfWriter

OPTIONS = {
    "pageWidth": 2100,
    "pageHeight": 2970,
    "pageMarginTop": 80,
    "pageMarginBottom": 80,
    "pageMarginLeft": 80,
    "pageMarginRight": 80,
    "scale": 45,
    "adjustPageHeight": False,
    "breaks": "auto",
    "footer": "none",
    "header": "auto",
}


RESOURCES = Path(verovio.__file__).parent / "data"
METRONOME = re.compile(r"<metronome[^>]*>.*?<per-minute>([^<]*)</per-minute>\s*</metronome>", re.DOTALL)


def _plain_tempo(musicxml: str) -> str:
    return METRONOME.sub(lambda m: f"<words>{m.group(1).strip()} BPM</words>", musicxml)


def render_svg_pages(musicxml: str) -> list[str]:
    musicxml = _plain_tempo(musicxml)
    toolkit = verovio.toolkit(False)
    toolkit.setResourcePath(str(RESOURCES))
    toolkit.setOptions(OPTIONS)
    if not toolkit.loadData(musicxml):
        raise ValueError("Unable to load MusicXML")
    return [toolkit.renderToSVG(page) for page in range(1, toolkit.getPageCount() + 1)]


def render_pdf(musicxml_path: Path, pdf_path: Path) -> int:
    import cairosvg

    pages = render_svg_pages(musicxml_path.read_text(encoding="utf-8"))
    writer = PdfWriter()
    for svg in pages:
        writer.append(BytesIO(cairosvg.svg2pdf(bytestring=svg.encode("utf-8"))))
    with pdf_path.open("wb") as output:
        writer.write(output)
    return len(pages)
