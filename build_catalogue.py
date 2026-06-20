#!/usr/bin/env python3
"""Add ORION (12) and AURA CLOUD (13) model spreads to the Napcat catalogue,
matching the existing 2-page template, and update contents / page numbers."""
import fitz

SRC = "/root/.claude/uploads/d8e3356b-8c1c-5dd9-9a3b-57502bc2c67b/a80ee2da-Napcat_Catalogue_.pdf"
OUT = "Napcat_Catalogue_Updated.pdf"

YELLOW = (0xfd/255, 0xd8/255, 0x2a/255)
YELLOW2 = (0xfe/255, 0xd8/255, 0x2b/255)   # big number / footer text
DARK = (0x12/255, 0x12/255, 0x12/255)
BLACK = (0x11/255, 0x11/255, 0x11/255)
WHITE = (1, 1, 1)
GREY = (0x3a/255, 0x3a/255, 0x3a/255)

FONTS = {
    "pb": ("Poppins-Bold", "/tmp/fonts/Poppins-Bold.ttf"),
    "pl": ("Poppins-Light", "/tmp/fonts/Poppins-Light.ttf"),
    "pm": ("Poppins-Medium", "/tmp/fonts/Poppins-Medium.ttf"),
    "pr": ("Poppins-Regular", "/tmp/fonts/Poppins-Regular.ttf"),
}
_FB = {k: fitz.Font(fontfile=v[1]) for k, v in FONTS.items()}


def reg(page):
    for k, (name, path) in FONTS.items():
        page.insert_font(fontname=name, fontfile=path)


def tlen(text, fk, size):
    return _FB[fk].text_length(text, size)


def txt(page, x, y, s, fk, size, color=DARK):
    page.insert_text((x, y), s, fontname=FONTS[fk][0], fontsize=size, color=color)


def txt_right(page, xr, y, s, fk, size, color=DARK):
    page.insert_text((xr - tlen(s, fk, size), y), s, fontname=FONTS[fk][0], fontsize=size, color=color)


def txt_center(page, xc, y, s, fk, size, color=DARK):
    page.insert_text((xc - tlen(s, fk, size) / 2, y), s, fontname=FONTS[fk][0], fontsize=size, color=color)


def txt_tracked(page, x, y, s, fk, size, tracking, color=DARK):
    """Letter-spaced text (small-caps style headers)."""
    cx = x
    for ch in s:
        page.insert_text((cx, y), ch, fontname=FONTS[fk][0], fontsize=size, color=color)
        cx += tlen(ch, fk, size) + tracking
    return cx


def wrap(text, fk, size, maxw):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if tlen(t, fk, size) <= maxw:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def rrect(page, r, color, radius=0.07):
    page.draw_rect(fitz.Rect(r), color=None, fill=color, radius=radius)


# ───────────────────────── WHITE (exploded) page ─────────────────────────

def build_white(page, m):
    reg(page)
    page.draw_rect(page.rect, color=None, fill=WHITE)
    page.draw_rect(fitz.Rect(0, 0, 595.28, 7), color=None, fill=YELLOW)
    # logo
    page.insert_image(fitz.Rect(46, 42, 146, 102), filename="assets/logo_dark.png")
    # header tick + collection line
    page.draw_rect(fitz.Rect(46, 128, 68, 131), color=None, fill=BLACK)
    cx = txt_tracked(page, 76, 130.5, "THE COLLECTION", "pm", 8, 2.6)
    txt_tracked(page, cx + 4, 130.5, "·  %s / 13" % m["num"], "pm", 8, 2.6)
    # name + tagline + underline
    txt(page, 46, 163, m["name"], "pb", 33)
    txt(page, 46, 191, '"%s"' % m["tagline"], "pr", 11.5)
    page.draw_rect(fitz.Rect(46, 206, 102, 210), color=None, fill=YELLOW)
    # big number (right aligned)
    txt_right(page, 550, 168, m["num"], "pb", 120, YELLOW2)
    # render
    page.insert_image(fitz.Rect(*m["render_rect"]), filename=m["render"], keep_proportion=True)
    # INSIDE THE BUILD
    txt_tracked(page, 350, 246, "INSIDE THE BUILD", "pm", 9, 2.4)
    page.draw_rect(fitz.Rect(350, 254, 376, 257), color=None, fill=BLACK)
    tops = [276, 331, 387, 443, 499]
    n = len(m["layers"])
    # center the block if fewer than 5 layers
    for i, (label, sub) in enumerate(m["layers"]):
        ct = tops[i]
        page.draw_circle((360, ct + 10), 10, color=None, fill=YELLOW)
        txt_center(page, 360, ct + 13.5, str(i + 1), "pb", 9.5, DARK)
        if i < n - 1:
            sh = page.new_shape()
            sh.draw_line((360, ct + 22), (360, ct + 54))
            sh.finish(color=DARK, width=0.8, dashes="[0.6 2.2] 0")
            sh.commit()
        if sub:
            txt(page, 380, ct + 6, label, "pm", 10.5)
            txt(page, 380, ct + 20, sub, "pl", 9)
        else:
            txt(page, 380, ct + 5, label, "pm", 10.5)
    # stat cards
    cards = [
        ("COMFORT", m["comfort"], None),
        ("FIRMNESS", m["firmness"], m["firm_fill"]),
        ("WARRANTY", m["warranty"], None),
        ("THICKNESS", m["thickness_white"], None),
    ]
    xs = [46, 174, 303, 431]
    for (lbl, val, bars), x in zip(cards, xs):
        rrect(page, (x, 630, x + 118, 722), BLACK, radius=0.06)
        page.draw_rect(fitz.Rect(x + 14, 649, x + 30, 652), color=None, fill=YELLOW)
        txt_tracked(page, x + 14, 665, lbl, "pm", 7, 1.8, YELLOW2)
        txt(page, x + 14, 681, val, "pb", 10.5, WHITE)
        if bars is not None:
            bx = x + 14
            for k in range(10):
                col = YELLOW if k < bars else GREY
                page.draw_rect(fitz.Rect(bx, 705, bx + 7, 710), color=None, fill=col)
                bx += 9.4
    # build line
    txt_tracked(page, 46, 738, "BUILD", "pm", 7, 1.6)
    txt(page, 88, 737, m["build"], "pr", 8.5)
    # footer
    page.draw_rect(fitz.Rect(532, 802, 549, 819), color=None, fill=BLACK)
    txt_center(page, 540.5, 813, m["page"], "pb", 7.5, YELLOW2)


# ───────────────────────── YELLOW (description) page ─────────────────────────

def build_yellow(page, m):
    reg(page)
    page.draw_rect(page.rect, color=None, fill=YELLOW)
    page.draw_rect(fitz.Rect(0, 0, 595.28, 7), color=None, fill=BLACK)
    # top-right black triangle
    sh = page.new_shape()
    sh.draw_polyline([(595.28, 7), (485.28, 7), (595.28, 117)])
    sh.finish(color=None, fill=BLACK)
    sh.commit()
    # logo (yellow-bg variant)
    page.insert_image(fitz.Rect(61, 41, 131, 103), filename="assets/logo_yellow.png")
    # header
    page.draw_rect(fitz.Rect(46, 128, 68, 131), color=None, fill=BLACK)
    cx = txt_tracked(page, 76, 130.5, "THE COLLECTION", "pm", 8, 2.6)
    txt_tracked(page, cx + 4, 130.5, "·  %s / 13" % m["num"], "pm", 8, 2.6)
    # name
    txt(page, 46, 165, m["name"], "pb", 27)
    # headline (may wrap)
    hlines = wrap(m["headline"], "pb", 19, 503)
    hy = 198
    for ln in hlines:
        txt(page, 46, hy, ln, "pb", 19)
        hy += 26
    uy = hy - 18
    page.draw_rect(fitz.Rect(46, uy, 102, uy + 4), color=None, fill=BLACK)
    # body paragraphs
    by = uy + 33
    for para in m["paras"]:
        for ln in wrap(para, "pr", 10.3, 503):
            txt(page, 46, by, ln, "pr", 10.3)
            by += 17
        by += 10
    # two-column lists
    ly = by + 8
    txt_tracked(page, 46, ly, "WHO IT'S FOR", "pm", 9, 2.6)
    txt_tracked(page, 311, ly, "WHY YOU'LL LOVE IT", "pm", 9, 2.6)
    ly += 30
    for col_x, items in [(46, m["who"]), (311, m["love"])]:
        yy = ly
        for it in items:
            page.draw_rect(fitz.Rect(col_x, yy - 7, col_x + 6, yy - 1), color=None, fill=DARK)
            for j, ln in enumerate(wrap(it, "pr", 9.5, 215 if col_x == 46 else 230)):
                txt(page, col_x + 14, yy if j == 0 else yy + 13, ln, "pr", 9.5)
            yy += 19 + (13 if len(wrap(it, "pr", 9.5, 215)) > 1 else 0)
    # bottom black bar
    page.draw_rect(fitz.Rect(0, 712, 595.28, 798), color=None, fill=BLACK)
    cols = [("AVAILABLE THICKNESSES", m["thickness_full"], 46),
            ("WARRANTY", m["warranty"], 214),
            ("COMFORT FEEL", m["comfort"], 382)]
    for lbl, val, x in cols:
        txt_tracked(page, x, 738, lbl, "pm", 7, 1.6, YELLOW2)
        txt(page, x, 757, val, "pb", 12.5, WHITE)
    # footer
    page.draw_rect(fitz.Rect(532, 802, 549, 819), color=None, fill=BLACK)
    txt_center(page, 540.5, 813, m["page"], "pb", 7.5, YELLOW2)


# ───────────────────────── Model data ─────────────────────────

ORION = {
    "num": "12", "name": "ORION", "page": "28",
    "tagline": "Designed to Lift, Aligned to Heal",
    "headline": "Designed to lift, aligned to heal.",
    "comfort": "Medium Firm", "firmness": "7.5", "firm_fill": 8,
    "warranty": "8 Years", "thickness_white": '6" · 8" · 10"',
    "thickness_full": '6" · 8" · 10"',
    "build": "Top quilted / Eurotop finish / Tight top",
    "render": "assets/render_orion.png", "render_rect": (57, 306, 325, 554),
    "layers": [
        ("Quilted Premium Knitted Fabric", None),
        ("GOLS Certified Latex", "25 mm"),
        ("Ortho HR Foam", "25 mm"),
        ("Independent Pocketed Springs", "100 mm – 150 mm"),
        ("Antiskid Fabric", None),
    ],
    "paras": [
        "Orion is built around a single promise – a sleeping surface that lifts you "
        "into perfect alignment and lets your spine recover while you rest. At its core "
        "sit independent pocketed springs that move one at a time, answering every curve "
        "of your body and isolating motion so a restless partner never disturbs your sleep.",
        "Above the springs, a layer of GOLS-certified natural latex and a dense Ortho HR "
        "foam plate work together to relieve pressure at the shoulders and hips while "
        "holding the lower back firmly in place. The result is a balanced medium-firm feel "
        "– supportive enough for back and stomach sleepers, yet forgiving enough to "
        "wake up genuinely pain-free.",
    ],
    "who": [
        "Back and stomach sleepers",
        "Anyone with lower-back or posture concerns",
        "Couples who want zero motion transfer",
        "Sleepers seeking a natural, breathable bed",
    ],
    "love": [
        "GOLS-certified natural latex comfort",
        "Independent pocketed-spring support",
        "Targeted orthopaedic spine alignment",
        "Cool, breathable Eurotop finish",
    ],
}

AURA = {
    "num": "13", "name": "AURA CLOUD", "page": "30",
    "tagline": "The Multi-Matrix System for Weightless, Pain-Free Rest",
    "headline": "The multi-matrix system for weightless, pain-free rest.",
    "comfort": "Soft", "firmness": "6.5", "firm_fill": 7,
    "warranty": "8 Years", "thickness_white": '6" · 8" · 10"',
    "thickness_full": '6" · 8" · 10"',
    "build": "Top quilted / Eurotop finish / Tight top",
    "render": "assets/render_aura.png", "render_rect": (60, 288, 322, 612),
    "layers": [
        ("Quilted Premium Knitted Fabric", None),
        ("Turmeric Memory Foam", "25 mm"),
        ("Ortho HR Foam", "25 mm"),
        ("Independent Pocketed Springs", "100 mm – 150 mm"),
        ("Antiskid Fabric", None),
    ],
    "paras": [
        "Aura Cloud layers four distinct comfort technologies into one weightless "
        "multi-matrix system, so pressure simply melts away the moment you lie down. "
        "A plush quilted top flows into turmeric-infused memory foam that cradles every "
        "contour while gently soothing the skin and keeping the surface fresh.",
        "Beneath the cloud-soft top, an Ortho HR foam plate and independent pocketed "
        "springs quietly take over the hard work – supporting your spine, absorbing "
        "movement and pushing back exactly where you need it. The effect is a soft, "
        "floating feel that never lets you sink too far, for deep, pain-free rest night "
        "after night.",
    ],
    "who": [
        "Side sleepers who love a plush feel",
        "Anyone with shoulder or hip pressure points",
        "Sleepers who run warm at night",
        "Couples sharing a bed",
    ],
    "love": [
        "Turmeric memory-foam comfort layer",
        "Weightless, cloud-like multi-matrix feel",
        "Pocketed springs that limit motion transfer",
        "Soft yet supportive spinal cradle",
    ],
}

# ───────────────────────── Assemble document ─────────────────────────

W, H = 595.2755737, 841.8897705

# new-page spec: (model, builder, footer page number)
NEW = [
    (ORION, build_white, "28"),
    (ORION, build_yellow, "29"),
    (AURA, build_white, "30"),
    (AURA, build_yellow, "31"),
]


def build_new_doc():
    nd = fitz.open()
    for m, builder, pno in NEW:
        m = dict(m)
        m["page"] = pno
        p = nd.new_page(width=W, height=H)
        builder(p, m)
    return nd


LEAD_COL = (0.07, 0.07, 0.07)


def leader(page, x0, y, x1=523):
    sh = page.new_shape()
    sh.draw_line((x0, y), (x1, y))
    sh.finish(color=LEAD_COL, width=0.6, dashes="[0.5 3] 0", lineCap=1)
    sh.commit()


def contents_row(page, num, name, sub, pageno, top):
    """Collection-style row (bold name + light subtitle)."""
    txt(page, 46, top + 10.2, num, "pb", 9)
    txt(page, 72, top + 9.3, name, "pb", 12.5)
    nx = 72 + tlen(name, "pb", 12.5) + 9
    sx = nx
    if sub:
        txt(page, nx, top + 10.4, sub, "pl", 8.5)
        sx = nx + tlen(sub, "pl", 8.5) + 8
    txt_right(page, 549, top + 9.5, pageno, "pb", 10)
    leader(page, sx, top + 10.6)


def care_row(page, num, name, pageno, top):
    """Care/warranty-style row (medium name, no subtitle)."""
    txt(page, 46, top + 8.6, num, "pb", 9)
    txt(page, 72, top + 8.0, name, "pm", 11)
    nx = 72 + tlen(name, "pm", 11) + 9
    txt_right(page, 549, top + 7.9, pageno, "pb", 10)
    leader(page, nx, top + 8.6)


def rebuild_contents(page):
    # Erase the old CARE & WARRANTY block (subhead + 4 rows + leaders)
    page.add_redact_annot(fitz.Rect(40, 595, 556, 732), fill=YELLOW)
    page.apply_redactions()
    reg(page)
    # New collection rows 12 & 13
    contents_row(page, "12", "ORION", "Designed to Lift, Aligned to Heal", "28", 586.4)
    contents_row(page, "13", "AURA CLOUD", "The Multi-Matrix Comfort System", "30", 613.9)
    # CARE & WARRANTY subhead (shifted down to make room, kept clear of the
    # bottom-right corner triangle whose hypotenuse runs (465,842)->(595,712))
    sub_top = 653.0
    page.draw_rect(fitz.Rect(46, sub_top + 4.2, 68, sub_top + 7.4), color=None, fill=DARK)
    txt_tracked(page, 76, sub_top + 6, "CARE & WARRANTY", "pm", 8, 2.6)
    # Care rows with updated page numbers (+4)
    care_row(page, "01", "Mattress Warranty Coverage", "32", 676.0)
    care_row(page, "02", "Pillow Warranty & Care", "34", 700.0)
    care_row(page, "03", "Mattress Care Guide", "35", 724.0)
    care_row(page, "04", "Get in Touch", "36", 748.0)
    # Rebuild all clickable links
    for ln in list(page.get_links()):
        page.delete_link(ln)
    entries = [
        (161, 1), (187, 3), (213, 4),
        (283.9, 5), (311.4, 7), (338.9, 9), (366.4, 11), (393.9, 13),
        (421.4, 15), (448.9, 17), (476.4, 19), (503.9, 21), (531.4, 23),
        (558.9, 25), (586.4, 27), (613.9, 29),
        (676.0, 31), (700.0, 33), (724.0, 34), (748.0, 35),
    ]
    for top, tgt in entries:
        page.insert_link({"kind": fitz.LINK_GOTO, "from": fitz.Rect(40, top - 3, 555, top + 18),
                          "page": tgt, "to": fitz.Point(0, 0)})


def fix_footer(page, newno):
    """Redraw the footer page-number box with a new number, preserving its colours."""
    box = fitz.Rect(532, 802, 549, 819)
    boxfill, numcol = DARK, YELLOW2
    for dr in page.get_drawings():
        r = dr["rect"]
        if dr.get("fill") and 530 < r.x0 < 535 and 800 < r.y0 < 805:
            boxfill = tuple(dr["fill"])
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0:
            continue
        for l in b["lines"]:
            for s in l["spans"]:
                if s["bbox"][1] > 800:
                    numcol = tuple(((s["color"] >> 16) & 255, (s["color"] >> 8) & 255, s["color"] & 255))
                    numcol = tuple(c / 255 for c in numcol)
    page.add_redact_annot(box, fill=boxfill)
    page.apply_redactions()
    page.insert_font(fontname="Poppins-Bold", fontfile="/tmp/fonts/Poppins-Bold.ttf")
    w = _FB["pb"].text_length(newno, 7.5)
    page.insert_text((540.5 - w / 2, 812.3), newno, fontname="Poppins-Bold", fontsize=7.5, color=numcol)


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        nd = build_new_doc()
        nd.save("/tmp/test_new.pdf")
        for i in range(nd.page_count):
            nd[i].get_pixmap(matrix=fitz.Matrix(2, 2)).save(f"/tmp/cat/new{i}.png")
        print("test pages written")
        sys.exit()

    doc = fitz.open(SRC)

    # 1) Patch "/ 11" -> "/ 13" on every existing model spread (idx 5..26)
    for idx in range(5, 27):
        pg = doc[idx]
        bgcol = WHITE if (idx % 2 == 1) else YELLOW
        # change the final "1" of the "/ 11" denominator to "3" (redact old glyph)
        pg.add_redact_annot(fitz.Rect(231, 121, 237, 133), fill=bgcol)
        pg.apply_redactions()
        pg.insert_font(fontname="Poppins-Medium", fontfile="/tmp/fonts/Poppins-Medium.ttf")
        pg.insert_text((232, 131), "3", fontname="Poppins-Medium", fontsize=8, color=DARK)

    # 2) Insert the 4 new pages after NIRVANA (idx26), before Care & Warranty (idx27)
    nd = build_new_doc()
    doc.insert_pdf(nd, start_at=27)
    nd.close()

    # 3) Update footers on shifted Care & Warranty pages (now idx 31..35)
    for new_idx, newno in [(31, "32"), (32, "33"), (33, "34"), (34, "35"), (35, "36")]:
        fix_footer(doc[new_idx], newno)

    # 4) Rebuild the Contents page
    rebuild_contents(doc[2])

    doc.save(OUT, garbage=4, deflate=True)
    print("saved", OUT, "pages:", doc.page_count)
