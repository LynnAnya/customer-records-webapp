"""PDF export of selected customers, with an embedded Thai font.

Only plain text is drawn: no HTML, SVG or images. That keeps customer-typed
text away from the fpdf2 features behind CVE-2026-114609 and CVE-2026-114610,
and resource loading is switched off as a second guard.
"""

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from django.utils.formats import date_format
from fpdf import FPDF
from fpdf.enums import ResourceAccessPolicy
from fpdf.fonts import FontFace

from customers.models import Customer
from customers.visibility import export_values

FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
FONT = "Sarabun"  # SIL Open Font License; has Thai, Latin letters and digits
INK = (16, 26, 58)
MUTED = (85, 96, 127)
HEAD_FILL = (227, 232, 255)
# Share of the page width: no., name, license plate, bank, account number.
COLUMN_WIDTHS = (7, 28, 25, 18, 22)


class _CustomerPDF(FPDF):
    def footer(self) -> None:
        self.set_y(-12)
        self.set_font(FONT, size=9)
        self.set_text_color(*MUTED)
        self.cell(0, 6, f"หน้า {self.page_no()} / {{nb}}", align="C")


def build_customers_pdf(
    customers: Sequence[Customer], *, generated_at: datetime, generated_by: str
) -> bytes:
    """A4 table of the given customers. Fields come from `export_values`,
    the same list the copy text uses, so the PDF never contains a phone."""
    pdf = _CustomerPDF(orientation="portrait", format="A4")
    pdf.resource_access_policy = ResourceAccessPolicy.NONE
    pdf.set_margins(12, 14, 12)
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_font(FONT, "", FONT_DIR / "Sarabun-Regular.ttf")
    pdf.add_font(FONT, "B", FONT_DIR / "Sarabun-Bold.ttf")
    pdf.set_title("รายชื่อลูกค้า")
    pdf.add_page()

    pdf.set_font(FONT, "B", 18)
    # Shaping places Thai vowels and tone marks correctly (needs uharfbuzz).
    pdf.set_text_shaping(True)
    pdf.set_text_color(*INK)
    pdf.cell(0, 10, "รายชื่อลูกค้า", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(FONT, size=10)
    pdf.set_text_color(*MUTED)
    printed = date_format(generated_at, "j F Y H:i")
    pdf.cell(
        0,
        6,
        f"จำนวน {len(customers)} ราย   พิมพ์เมื่อ {printed}   โดย {generated_by}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(3)

    rows = [export_values(customer) for customer in customers]
    headings = ["ลำดับ", *(label for label, _value in rows[0])] if rows else []
    headings = ["ชื่อ-นามสกุล" if text == "ชื่อ" else text for text in headings]

    pdf.set_font(FONT, size=11)
    pdf.set_text_color(*INK)
    pdf.set_draw_color(213, 219, 234)
    with pdf.table(
        col_widths=COLUMN_WIDTHS,
        text_align=("CENTER", "LEFT", "LEFT", "LEFT", "LEFT"),
        headings_style=FontFace(emphasis="BOLD", color=INK, fill_color=HEAD_FILL),
        line_height=7,
        padding=1.5,
    ) as table:
        table.row(headings)
        for number, row in enumerate(rows, start=1):
            table.row([str(number), *(str(value) for _label, value in row)])

    return bytes(pdf.output())
