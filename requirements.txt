"""
Wordレポート生成モジュール
Geminiが出力したテキストを、A4縦のきれいなWord文書に変換する。
レイアウトの見た目を変えたい場合のみ、このファイルを編集する。
"""
from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


def _set_cell_border_bottom(paragraph, color="2E75B6", size="6"):
    """段落の下に区切り線を引く"""
    p = paragraph._p
    pPr = p.get_or_add_pPr()
    pbdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), size)
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), color)
    pbdr.append(bottom)
    pPr.append(pbdr)


def parse_report_text(text):
    """Geminiの構造化出力をパースする"""
    data = {"title": "", "date": "", "sections": [], "closing": ""}
    current_section = None
    mode = None

    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("TITLE:"):
            data["title"] = line.replace("TITLE:", "").strip()
        elif line.startswith("DATE:"):
            data["date"] = line.replace("DATE:", "").strip()
        elif line.startswith("SECTION:"):
            current_section = {"heading": line.replace("SECTION:", "").strip(), "items": []}
            data["sections"].append(current_section)
            mode = "section"
        elif line.startswith("CLOSING:"):
            mode = "closing"
        elif line.strip() == "---":
            continue
        elif mode == "closing":
            if line.strip():
                data["closing"] += line + "\n"
        elif mode == "section" and current_section is not None:
            if line.startswith("■"):
                current_section["items"].append({"head": line.replace("■", "").strip(), "body": ""})
            elif line.strip() and current_section["items"]:
                current_section["items"][-1]["body"] += line + "\n"

    return data


def build_report_docx(text, sender, output_path):
    """パースしたデータからWord文書を生成する"""
    data = parse_report_text(text)
    doc = Document()

    # --- A4縦・余白設定 ---
    section = doc.sections[0]
    section.page_height = Cm(29.7)
    section.page_width = Cm(21.0)
    section.top_margin = Cm(2.5)
    section.bottom_margin = Cm(2.5)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)

    # --- 既定フォント ---
    style = doc.styles["Normal"]
    style.font.name = "游ゴシック"
    style.element.rPr.rFonts.set(qn("w:eastAsia"), "游ゴシック")
    style.font.size = Pt(10.5)

    # --- タイトル ---
    title_p = doc.add_paragraph()
    title_run = title_p.add_run(data["title"] or "市場環境変化への各社対応事例")
    title_run.font.size = Pt(16)
    title_run.font.bold = True
    title_run.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)
    _set_cell_border_bottom(title_p)

    # --- 日付 ---
    if data["date"]:
        date_p = doc.add_paragraph()
        date_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        date_run = date_p.add_run(data["date"])
        date_run.font.size = Pt(9)
        date_run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    doc.add_paragraph()

    # --- 各セクション ---
    for sec in data["sections"]:
        h = doc.add_paragraph()
        h_run = h.add_run(sec["heading"])
        h_run.font.size = Pt(12.5)
        h_run.font.bold = True
        h_run.font.color.rgb = RGBColor(0x2E, 0x75, 0xB6)
        h.paragraph_format.space_before = Pt(10)
        h.paragraph_format.space_after = Pt(4)

        for item in sec["items"]:
            ip = doc.add_paragraph()
            ir = ip.add_run("■ " + item["head"])
            ir.font.size = Pt(10.5)
            ir.font.bold = True
            ip.paragraph_format.space_before = Pt(6)
            ip.paragraph_format.space_after = Pt(2)

            if item["body"].strip():
                bp = doc.add_paragraph()
                br = bp.add_run(item["body"].strip())
                br.font.size = Pt(10.5)
                bp.paragraph_format.left_indent = Cm(0.5)
                bp.paragraph_format.line_spacing = 1.3

    # --- 締め ---
    if data["closing"].strip():
        doc.add_paragraph()
        cp = doc.add_paragraph()
        cr = cp.add_run(data["closing"].strip())
        cr.font.size = Pt(10)
        cr.font.color.rgb = RGBColor(0x44, 0x44, 0x44)
        cp.paragraph_format.line_spacing = 1.3

    # --- 署名 ---
    doc.add_paragraph()
    sig_p = doc.add_paragraph()
    _set_cell_border_bottom(sig_p, color="CCCCCC", size="4")
    for txt in [sender["company"], "代表　" + sender["name"], sender["hp"]]:
        sp = doc.add_paragraph()
        sr = sp.add_run(txt)
        sr.font.size = Pt(9)
        sr.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
        sp.paragraph_format.space_after = Pt(0)

    doc.save(output_path)
    return output_path
