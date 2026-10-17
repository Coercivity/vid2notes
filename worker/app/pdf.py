from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from app.imaging import normalize_paper

DPI = 150
PAGE_WIDTH = 1240
PAGE_HEIGHT = 1754
MARGIN = 70
GAP = 30


def _to_pil(fragment: np.ndarray, width: int, height: int) -> Image.Image:
    h, w = fragment.shape[:2]
    interpolation = cv2.INTER_AREA if width < w else cv2.INTER_CUBIC
    resized = cv2.resize(fragment, (width, height), interpolation=interpolation)
    return Image.fromarray(cv2.cvtColor(resized, cv2.COLOR_BGR2RGB))


def compose(fragments: list[np.ndarray]) -> list[Image.Image]:
    content_width = PAGE_WIDTH - 2 * MARGIN
    content_height = PAGE_HEIGHT - 2 * MARGIN
    pages: list[Image.Image] = []
    page = Image.new("RGB", (PAGE_WIDTH, PAGE_HEIGHT), "white")
    y = MARGIN

    for fragment in fragments:
        fragment = normalize_paper(fragment)
        h, w = fragment.shape[:2]
        scale = min(content_width / w, content_height / h)
        width, height = max(1, int(w * scale)), max(1, int(h * scale))
        if y + height > PAGE_HEIGHT - MARGIN and y > MARGIN:
            pages.append(page)
            page = Image.new("RGB", (PAGE_WIDTH, PAGE_HEIGHT), "white")
            y = MARGIN
        page.paste(_to_pil(fragment, width, height), ((PAGE_WIDTH - width) // 2, y))
        y += height + GAP

    if y > MARGIN:
        pages.append(page)
    return pages


def save_pdf(pages: list[Image.Image], path: Path) -> None:
    pages[0].save(path, "PDF", resolution=DPI, save_all=True, append_images=pages[1:])
