from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import os

def create_roll_level_pdf(path):
    c = canvas.Canvas(path, pagesize=A4)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, 800, "Packing & Weight List")
    c.setFont("Helvetica", 10)
    c.drawString(50, 780, "Packing List No. TEST-001-26")
    c.drawString(50, 765, "Contract No: W2-2600001")
    c.drawString(50, 750, "Date: 28-NOV-25")
    c.drawString(50, 735, "Net Weight: 500.00 KGS")
    c.drawString(50, 720, "D/A No: E000001")
    c.setFont("Helvetica-Bold", 9)
    c.drawString(50, 695, "Roll No  Shade              Width   Qty (MTR)  N Wt.(KGS)  Construction")
    c.setFont("Helvetica", 9)
    rows = [
        ("1", "R1832-8600 DK NAVY", "60.00", "100.00", "41.09", "14 RPCS*14 88*50"),
        ("2", "R1832-8600 DK NAVY", "60.00", "100.00", "41.09", "14 RPCS*14 88*50"),
        ("3", "R1832-8600 DK NAVY", "60.00", " 98.00", "40.24", "14 RPCS*14 88*50"),
    ]
    y = 680
    for row in rows:
        c.drawString(50, y, "  ".join(row))
        y -= 15
    c.drawString(50, y-10, "Sub Total: 298.00 MTR    Net Weight: 122.42 KGS")
    c.save()

def create_lot_level_pdf(path):
    c = canvas.Canvas(path, pagesize=A4)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, 800, "Orden de Envio / Packing List")
    c.setFont("Helvetica", 10)
    c.drawString(50, 780, "Number: 1.232.699")
    c.drawString(50, 765, "Order: 312696/1")
    c.drawString(50, 750, "Your Order: PO 137009")
    c.drawString(50, 735, "Delivery date: 09/10/2025")
    c.drawString(50, 720, "Nett Weight: 1.796,3")
    c.drawString(50, 705, "Article: TECHS NX260 HV (Ref. 8912 NAQUA 160 cm)")
    c.drawString(50, 690, "Your product: R15123300")
    c.setFont("Helvetica-Bold", 9)
    c.drawString(50, 665, "Lot          Piece   Metres")
    c.setFont("Helvetica", 9)
    rows = [("072168/002", "/1", "85,0"), ("", "/2", "82,0"), ("", "/3", "79,0")]
    y = 650
    for row in rows:
        c.drawString(50, y, f"{row[0]:15} {row[1]:8} {row[2]}")
        y -= 15
    c.save()

os.makedirs("test/samples", exist_ok=True)
create_roll_level_pdf("test/samples/roll_level.pdf")
create_lot_level_pdf("test/samples/lot_level.pdf")
print("Test PDFs created in test/samples/")
