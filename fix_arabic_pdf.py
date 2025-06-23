#!/usr/bin/env python3
"""
fix_arabic_pdf.py
=================
Run inside GitHub Actions *or* locally:

    python fix_arabic_pdf.py scan.pdf
    # └─► produces scan-readable.pdf alongside the original

Creates a PDF whose invisible text layer is in logical RTL order, so
search/copy‑paste work for Arabic.

External tooling required: **ocrmypdf** + Tesseract with the Arabic
language pack.
"""

from __future__ import annotations

import io
import re
import sys
import tempfile
from pathlib import Path
from subprocess import run  # nosec B404

import fitz                         # PyMuPDF
from bidi.algorithm import get_display
from bs4 import BeautifulSoup
import arabic_reshaper
from reportlab.pdfgen.canvas import Canvas
from PIL import Image


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #
def _ocr_to_hocr(src: str, hocr: str, img_pdf: str) -> None:
    """Run OCRmyPDF once to obtain a HOCR side‑car + image‑only PDF."""
    run(
        [
            "ocrmypdf",
            "-l",
            "ara",
            "--rotate-pages",
            "--deskew",
            "--force-ocr",
            "--sidecar",
            hocr,
            src,
            img_pdf,
        ],
        check=True,
    )


def _parse_hocr(hocr_path: Path) -> list[list[tuple[tuple[int, int, int, int], str]]]:
    """Return page‑wise list of (bbox, logical_text)."""
    pages: list[list[tuple[tuple[int, int, int, int], str]]] = []
    with hocr_path.open(encoding="utf8") as fh:
        soup = BeautifulSoup(fh, "html.parser")

    for page in soup.select(".ocr_page"):
        words_on_page: list[tuple[tuple[int, int, int, int], str]] = []
        for word in page.select(".ocrx_word"):
            m = re.search(r"bbox (\d+) (\d+) (\d+) (\d+)", word["title"])
            if not m:
                continue
            x0, y0, x1, y1 = map(int, m.groups())
            vis_txt = word.get_text(strip=True)
            if not vis_txt:
                continue
            logical = get_display(arabic_reshaper.reshape(vis_txt))
            words_on_page.append(((x0, y0, x1, y1), logical))
        pages.append(words_on_page)

    return pages


# --------------------------------------------------------------------------- #
# Main                                                                        #
# --------------------------------------------------------------------------- #
def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("Usage: python fix_arabic_pdf.py scan.pdf")

    inp = Path(sys.argv[1]).resolve()
    if not inp.is_file():
        sys.exit(f"File not found: {inp}")

    out: str = str(inp.with_stem(inp.stem + "-readable"))  # **plain str**
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        hocr = tmp / "scan.hocr"
        img_pdf = tmp / "scan-img.pdf"

        _ocr_to_hocr(str(inp), str(hocr), str(img_pdf))

        pages_words = _parse_hocr(hocr)
        doc = fitz.open(img_pdf)

        # Safety: ensure same length
        while len(pages_words) < doc.page_count:
            pages_words.append([])

        canv = Canvas(out)  # ReportLab wants a str path
        for page_idx, pg in enumerate(doc.pages()):
            pix = pg.get_pixmap(dpi=300)
            pil_img = Image.open(io.BytesIO(pix.tobytes("png")))

            w, h = pg.rect.width, pg.rect.height
            canv.setPageSize((w, h))
            canv.drawInlineImage(pil_img, 0, 0, w, h)

            # Invisible logical text
            canv.setFillColorRGB(1, 1, 1, alpha=0)
            canv.setFont("Helvetica", 1)
            for (x0, y0, _x1, y1), txt in pages_words[page_idx]:
                canv.drawString(x0, h - y1, txt)

            canv.showPage()

        canv.save()

    print(f"✅  created {out}")


if __name__ == "__main__":
    main()
