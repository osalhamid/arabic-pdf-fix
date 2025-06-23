#!/usr/bin/env python3
"""
fix_arabic_pdf.py
  python fix_arabic_pdf.py  input.pdf
Creates:  input-readable.pdf
"""
import sys, re, io, fitz                 # PyMuPDF
from bs4 import BeautifulSoup            # BeautifulSoup4
from bidi.algorithm import get_display   # python-bidi
import arabic_reshaper
from reportlab.pdfgen.canvas import Canvas
from PIL import Image
from pathlib import Path
import subprocess, tempfile, os

# ----- helper: run ocrmypdf to get HOCR + images -----
def ocr_to_hocr(src, hocr, img_pdf):
    subprocess.run([
        "ocrmypdf", "-l", "ara", "--rotate-pages", "--deskew",
        "--force-ocr", "--sidecar", hocr, src, img_pdf
    ], check=True)

# ----- helper: parse HOCR into per-page word list -----
def parse_hocr(hocr_path):
    pages = []
    soup = BeautifulSoup(open(hocr_path, encoding="utf8"), "html.parser")
    for page in soup.select(".ocr_page"):
        words=[]
        for w in page.select(".ocrx_word"):
            m = re.search(r"bbox (\d+) (\d+) (\d+) (\d+)", w["title"])
            if not m: continue
            x0,y0,x1,y1 = map(int, m.groups())
            vis  = w.get_text(strip=True)
            if vis:
                log = get_display(arabic_reshaper.reshape(vis))
                words.append(((x0,y0,x1,y1), log))
        pages.append(words)
    return pages

# -------------- main --------------
if len(sys.argv)!=2:
    print("Usage: python fix_arabic_pdf.py input.pdf"); sys.exit(1)

inp = Path(sys.argv[1]).resolve()
out = inp.with_stem(inp.stem + "-readable")
with tempfile.TemporaryDirectory() as tmp:
    hocr   = Path(tmp)/"scan.hocr"
    imgpdf = Path(tmp)/"scan-img.pdf"
    ocr_to_hocr(inp, hocr, imgpdf)

    words  = parse_hocr(hocr)
    doc    = fitz.open(imgpdf)
    while len(words)<doc.page_count: words.append([])

    canvas = Canvas(out)
    for i in range(doc.page_count):
        pg   = doc.load_page(i)
        pix  = pg.get_pixmap(dpi=300)
        pil  = Image.open(io.BytesIO(pix.tobytes("png")))
        W,H  = pg.rect.width, pg.rect.height
        canvas.setPageSize((W,H))
        canvas.drawInlineImage(pil,0,0,W,H)

        canvas.setFillColorRGB(1,1,1,alpha=0); canvas.setFont("Helvetica",1)
        for (x0,y0,x1,y1),txt in words[i]:
            canvas.drawString(x0, H-y1, txt)
        canvas.showPage()
    canvas.save()

print("✅ wrote", out.name)
