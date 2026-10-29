"""Invoice rendering. One layout function draws onto a tiny canvas interface, and two backends
(Pillow for PNG, ReportLab for PDF) implement it, so the image and the PDF always match."""
from __future__ import annotations

import io
from pathlib import Path

FONTS = Path(__file__).parent / "static" / "fonts"
W, H = 595, 842  # A4 in points
INK, MUTED, LINE, SOFT = (17, 17, 17), (107, 114, 128), (225, 228, 232), (245, 246, 248)
STAMP = {"PAID": (22, 130, 74), "PARTIALLY PAID": (180, 110, 10), "DUE": (30, 30, 30), "OVERDUE": (190, 40, 40), "DRAFT": (120, 120, 120)}


def inr(n) -> str:
    return "₹" + format(int(round(n or 0)), ",")


def _qr_matrix(text: str):
    try:
        import segno
        q = segno.make(text, error="m", micro=False)
        return [[bool(c) for c in row] for row in q.matrix]
    except Exception:
        return None


def _wrap(measure, text: str, width: float):
    out = []
    for para in str(text).split("\n"):
        line = ""
        for word in para.split(" "):
            t = (line + " " + word).strip()
            if measure(t) <= width or not line:
                line = t
            else:
                out.append(line)
                line = word
        out.append(line)
    return out


def layout(c, d: dict) -> None:
    """Draw invoice dict `d` on canvas `c`. Coordinates are top-left based points."""
    L, R = 40, W - 40
    c.rect(0, 0, W, 96, INK)
    c.text(L, 30, "INVOICE", 24, True, (255, 255, 255))
    c.text(L, 62, d["number"], 11, False, (210, 210, 210))
    c.text(R, 30, d["from"]["name"], 12, True, (255, 255, 255), "r")
    c.text(R, 50, "via Synera", 9, False, (200, 200, 200), "r")

    y = 120
    c.text(L, y, "BILLED TO", 8, True, MUTED)
    c.text(L + 290, y, "FROM", 8, True, MUTED)
    to, fr = d["to"], d["from"]
    ty = y + 16
    for i, ln in enumerate([to["name"], to["email"]]):
        c.text(L, ty + i * 14, ln, 10.5 if i == 0 else 9.5, i == 0, INK if i == 0 else MUTED)
    c.text(L, ty + 34, "PROJECT", 7.5, True, MUTED)
    for j, w in enumerate(_wrap(c.measure_fn(9.5, True), d["project_title"], 240)[:2]):
        c.text(L, ty + 46 + j * 13, w, 9.5, True, INK)
    fy = y + 16
    flines = [fr["name"]] + [x for x in [fr.get("business_name"), fr.get("address"), fr.get("email"), fr.get("phone")] if x]
    if fr.get("gstin"):
        flines.append("GSTIN " + fr["gstin"])
    if fr.get("pan"):
        flines.append("PAN " + fr["pan"])
    flines.append("" if fr.get("gstin") else "Not registered under GST. No GST charged.")
    for i, ln in enumerate([x for x in flines if x]):
        for j, w in enumerate(_wrap(c.measure_fn(9.5, i == 0), ln, 240)):
            c.text(L + 290, fy, w, 10.5 if i == 0 else 9.5, i == 0, INK if i == 0 else MUTED)
            fy += 14

    # meta box
    my = max(ty + 76, fy) + 8
    c.rect(L, my, R - L, 46, SOFT)
    cols = [("Issued", d["issued"]), ("Due", d["due"]), ("Status", d["status"])]
    for i, (k, v) in enumerate(cols):
        x = L + 12 + i * 175
        c.text(x, my + 14, k.upper(), 7.5, True, MUTED)
        c.text(x, my + 30, v, 10, True, STAMP.get(v, INK) if k == "Status" else INK)

    # line items
    y = my + 66
    c.rect(L, y, R - L, 22, INK)
    c.text(L + 10, y + 7, "DESCRIPTION", 8, True, (255, 255, 255))
    c.text(R - 10, y + 7, "AMOUNT", 8, True, (255, 255, 255), "r")
    y += 22
    for i, it in enumerate(d["items"]):
        if i % 2:
            c.rect(L, y, R - L, 20, SOFT)
        lab = it["label"]
        while c.measure(lab, 9.5, False) > 360 and len(lab) > 4:
            lab = lab[:-2]
        c.text(L + 10, y + 5, lab + ("…" if lab != it["label"] else ""), 9.5, False, INK)
        if it.get("note"):
            c.text(L + 380, y + 6, it["note"], 7.5, False, MUTED)
        c.text(R - 10, y + 5, inr(it["amount"]), 9.5, False, INK, "r")
        y += 20
    c.line(L, y + 2, R, y + 2, LINE)
    y += 14

    # totals
    ty0 = y
    for k, v, strong in d["totals"]:
        c.text(R - 150, y, k, 10 if not strong else 11, strong, INK if strong else MUTED, "r")
        c.text(R - 10, y, v, 10 if not strong else 12, strong, INK, "r")
        y += 20 if not strong else 24

    # payments
    y += 6
    c.text(L, y, "PAYMENTS RECEIVED", 8, True, MUTED)
    y += 16
    if d["payments"]:
        for p in d["payments"]:
            c.text(L, y, f"{p['kind'].title()}  ·  {p['at']}  ·  {p['method']}", 9, False, INK)
            c.text(R, y, inr(p["amount"]), 9, True, INK, "r")
            y += 13
            c.text(L, y, "Ref " + p["ref"], 8, False, MUTED, mono=True)
            y += 17
    else:
        c.text(L, y, "No payment received yet.", 9, False, MUTED)
        y += 18

    # terms
    y += 4
    c.line(L, y, R, y, LINE)
    y += 12
    c.text(L, y, "TERMS", 8, True, MUTED)
    y += 14
    for ln in _wrap(c.measure_fn(8.5, False), d["terms"], 330):
        c.text(L, y, ln, 8.5, False, MUTED)
        y += 12

    # verification block (bottom)
    by = H - 128
    c.line(L, by - 10, R, by - 10, LINE)
    qr = _qr_matrix(d["verify_url"])
    if qr:
        n = len(qr)
        cell = 84 / (n + 4)
        c.rect(R - 92, by - 2, 92, 92, (255, 255, 255), outline=LINE)
        for r, row in enumerate(qr):
            for k, on in enumerate(row):
                if on:
                    c.rect(R - 92 + 4 + k * cell + (92 - 8 - n * cell) / 2, by - 2 + 4 + r * cell + (92 - 8 - n * cell) / 2, cell + 0.2, cell + 0.2, INK)
    c.text(L, by, "VERIFY THIS INVOICE", 8, True, MUTED)
    vy = by + 14
    for ln in _wrap(c.measure_fn(8.5, False), "Scan the code or open the link to check this invoice, its status and every payment reference on Synera. "
                    "A screenshot of a payment is not proof; the payment references above are.", 380):
        c.text(L, vy, ln, 8.5, False, INK)
        vy += 12
    c.text(L, vy + 4, d["verify_url"], 7.5, False, MUTED, mono=True)
    c.text(L, vy + 18, "Document hash " + d["hash"][:40] + "…", 7.5, False, MUTED, mono=True)
    c.text(L, H - 26, f"Generated by Synera · {d['generated']} · Computer-generated invoice, valid without signature.", 7.5, False, MUTED)

    col = STAMP.get(d["status"], INK)
    if d["status"] in ("PAID", "OVERDUE"):
        c.stamp(L + 170, ty0 + 20, d["status"], col)


# ---- Pillow backend -------------------------------------------------------------------------
class PNGCanvas:
    def __init__(self, scale: float = 2.5):
        from PIL import Image, ImageDraw
        self.s = scale
        self.img = Image.new("RGB", (int(W * scale), int(H * scale)), "white")
        self.d = ImageDraw.Draw(self.img)
        self._f = {}

    def font(self, size, bold=False, mono=False):
        from PIL import ImageFont
        k = (round(size * self.s), bold, mono)
        if k not in self._f:
            name = "DejaVuSansMono.ttf" if mono else ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")
            p = FONTS / name
            if mono and not p.exists():
                p = FONTS / "DejaVuSans.ttf"
            self._f[k] = ImageFont.truetype(str(p), k[0])
        return self._f[k]

    def measure(self, t, size, bold=False, mono=False):
        return self.font(size, bold, mono).getlength(t) / self.s

    def measure_fn(self, size, bold):
        return lambda t: self.measure(t, size, bold)

    def rect(self, x, y, w, h, fill, outline=None):
        s = self.s
        self.d.rectangle([x * s, y * s, (x + w) * s, (y + h) * s], fill=fill, outline=outline)

    def line(self, x1, y1, x2, y2, col):
        s = self.s
        self.d.line([x1 * s, y1 * s, x2 * s, y2 * s], fill=col, width=max(1, int(s * 0.6)))

    def text(self, x, y, t, size, bold=False, col=INK, align="l", mono=False):
        f = self.font(size, bold, mono)
        w = f.getlength(t)
        px = x * self.s - (w if align == "r" else 0)
        self.d.text((px, y * self.s), t, font=f, fill=col)

    def stamp(self, x, y, label, col):
        from PIL import Image, ImageDraw
        s = self.s
        f = self.font(30, True)
        tw = int(f.getlength(label)) + 40
        th = int(30 * s * 1.5)
        layer = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ld.rounded_rectangle([2, 2, tw - 3, th - 3], radius=12, outline=col + (200,), width=int(s * 2))
        ld.text((20, int(s * 7)), label, font=f, fill=col + (200,))
        layer = layer.rotate(10, expand=True, resample=Image.BICUBIC)
        self.img.paste(layer, (int(x * s - layer.width / 2), int(y * s)), layer)

    def png(self) -> bytes:
        b = io.BytesIO()
        self.img.save(b, "PNG", optimize=True, dpi=(300, 300))
        return b.getvalue()


# ---- ReportLab backend ----------------------------------------------------------------------
class PDFCanvas:
    def __init__(self, title: str):
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfgen import canvas
        for n, f in (("DV", "DejaVuSans.ttf"), ("DVB", "DejaVuSans-Bold.ttf")):
            if n not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(n, str(FONTS / f)))
        self.pm = pdfmetrics
        self.buf = io.BytesIO()
        self.c = canvas.Canvas(self.buf, pagesize=(W, H))
        self.c.setTitle(title)
        self.c.setAuthor("Synera")

    @staticmethod
    def _c(col):
        return tuple(v / 255 for v in col)

    def measure(self, t, size, bold=False, mono=False):
        return self.pm.stringWidth(t, "DVB" if bold else "DV", size)

    def measure_fn(self, size, bold):
        return lambda t: self.measure(t, size, bold)

    def rect(self, x, y, w, h, fill, outline=None):
        c = self.c
        c.setFillColorRGB(*self._c(fill))
        if outline:
            c.setStrokeColorRGB(*self._c(outline))
        c.rect(x, H - y - h, w, h, fill=1, stroke=1 if outline else 0)

    def line(self, x1, y1, x2, y2, col):
        self.c.setStrokeColorRGB(*self._c(col))
        self.c.setLineWidth(0.6)
        self.c.line(x1, H - y1, x2, H - y2)

    def text(self, x, y, t, size, bold=False, col=INK, align="l", mono=False):
        c = self.c
        c.setFillColorRGB(*self._c(col))
        c.setFont("DVB" if bold else "DV", size * (0.92 if mono else 1))
        base = H - y - size * 0.82
        (c.drawRightString if align == "r" else c.drawString)(x, base, t)

    def stamp(self, x, y, label, col):
        c = self.c
        c.saveState()
        c.translate(x, H - y - 20)
        c.rotate(-10)
        c.setStrokeColorRGB(*self._c(col))
        c.setFillColorRGB(*self._c(col))
        c.setLineWidth(2)
        w = self.measure(label, 22, True) + 28
        c.roundRect(-w / 2, -8, w, 38, 8, stroke=1, fill=0)
        c.setFont("DVB", 22)
        c.drawCentredString(0, 2, label)
        c.restoreState()

    def pdf(self) -> bytes:
        self.c.showPage()
        self.c.save()
        return self.buf.getvalue()


def render_png(d: dict) -> bytes:
    c = PNGCanvas()
    layout(c, d)
    return c.png()


def render_pdf(d: dict) -> bytes:
    c = PDFCanvas(f"Invoice {d['number']}")
    layout(c, d)
    return c.pdf()
