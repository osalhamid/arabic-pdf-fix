#!/usr/bin/env python3
"""
fix_arabic_pdf.py – create scan-readable.pdf with logical RTL text.

Usage:
    python fix_arabic_pdf.py  scan.pdf
    # → produces scan-readable.pdf next to the original

External tools required (already in requirements.txt):
    ocrmypdf, tesseract-ocr-ara, pymupdf, reportlab, pillow,
    arabic-reshaper, python-bidi, beautifulsoup4
"""

from __future__ import annotations
import io, re, sys, tempfile, subprocess
from pathlib import Path

import fitz                          # PyMuPDF
from bidi.algorithm import get_display
from bs4 import BeautifulSoup
import arabic_reshaper
from reportlab.pdfgen.canvas import Canvas
from PIL import Image


# --------------------------------------------------------------------------- #
def _ocr_to_hocr(src: str, hocr: str, img_pdf: str) -> None:
    """Run OCRmyPDF once to get HOCR + image-only PDF."""
    subprocess.run(
        [
            "ocrmypdf",
            "-l", "ara",
            "--rotate-pages",
            "--deskew",
            "--force-ocr",
            "--sidecar", hocr,
            src, img_pdf,
        ],
        check=True,
    )


def _parse_hocr(hocr_path: Path):
    """Return list[list[(bbox, logical_text)]] page-by-page."""
    pages: list[list[tuple[tuple[int, int, int, int], str]]] = []
    soup = BeautifulSoup(hocr_path.read_text(encoding="utf8"), "html.parser")

    for page in soup.select(".ocr_page"):
        words = []
        for w in page.select(".ocrx_word"):
            m = re.search(r"bbox (\d+) (\d+) (\d+) (\d+)", w["title"])
            if not m:
                continue
            x0, y0, x1, y1 = map(int, m.groups())
            vis = w.get_text(strip=True)
            if not vis:
                continue
            logical = get_display(arabic_reshaper.reshape(vis))
            words.append(((x0, y0, x1, y1), logical))
        pages.append(words)

    return pages


# --------------------------------------------------------------------------- #
def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("Usage: python fix_arabic_pdf.py scan.pdf")

    inp = Path(sys.argv[1]).resolve()
    if not inp.is_file():
        sys.exit(f"File not found: {inp}")

    out: str = str(inp.with_stem(inp.stem + "-readable"))  # ensure plain str

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        hocr   = tmp / "scan.hocr"
        imgpdf = tmp / "scan-img.pdf"

        _ocr_to_hocr(str(inp), str(hocr), str(imgpdf))

        pages_words = _parse_hocr(hocr)
        doc = fitz.open(imgpdf)

        while len(pages_words) < doc.page_count:
            pages_words.append([])

        canv = Canvas(out)                      # ReportLab needs str
        for pg_idx, pg in enumerate(doc.pages()):
            pix = pg.get_pixmap(dpi=300)
            pil = Image.open(io.BytesIO(pix.tobytes("png")))

            W, H = pg.rect.width, pg.rect.height
            canv.setPageSize((W, H))
            canv.drawInlineImage(pil, 0, 0, W, H)

            canv.setFillColorRGB(1, 1, 1, alpha=0)  # invisible text
            canv.setFont("Helvetica", 1)
            for (x0, y0, _x1, y1), txt in pages_words[pg_idx]:
                canv.drawString(x0, H - y1, txt)

            canv.showPage()

        canv.save()

    print("✅ created", out)


if __name__ == "__main__":
    main()
