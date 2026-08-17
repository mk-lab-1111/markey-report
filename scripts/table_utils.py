"""report_text 内のテーブル（Markdown / HTML）を箇条書きに変換し、
Markdown記法の除去・ラベル改行・定型見出しの補完も行うユーティリティ。
main.py と fix_archive.py から共通で利用する。"""
import re


# ---------------------------------------------------------------------------
#  Markdown記法の除去
# ---------------------------------------------------------------------------
def _strip_markdown(text):
    """**太字** / *斜体* / __下線__ / _斜体_ などのMarkdown記法を除去する。
    記法だけ消してテキストは残す。"""
    # **text** or __text__（太字）
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    # *text* or _text_（斜体）— ただし単語中のアンダースコアは誤検出しやすいので
    # 前後がスペース or 行頭末 or 日本語の場合のみ
    text = re.sub(r'(?<=[\s\u3000\u3001-\u9fff])_(.+?)_(?=[\s\u3000\u3001-\u9fff]|$)', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    # ~~取り消し線~~
    text = re.sub(r'~~(.+?)~~', r'\1', text)
    return text


# ---------------------------------------------------------------------------
#  定型見出しを SECTION: に昇格
# ---------------------------------------------------------------------------
_HEADING_KEYWORDS = [
    'Executive Summary',
]

def _promote_known_headings(lines):
    """定型の見出し語がSECTION:になっていない場合に昇格させる。"""
    result = []
    for line in lines:
        stripped = line.strip()
        promoted = False
        for kw in _HEADING_KEYWORDS:
            if stripped.startswith(kw) and not stripped.startswith('SECTION:'):
                result.append('SECTION: ' + stripped)
                promoted = True
                break
        if not promoted:
            result.append(line)
    return result


# ---------------------------------------------------------------------------
#  ラベル付き項目を改行で分割
# ---------------------------------------------------------------------------

# 【…】 形式のラベルの直前に改行を挿入
# 条件: 10文字以上のテキストの後に、日本語のみ1〜4文字の【ラベル】が来る場合
# → プロダクト名（【フラット35】等）や番号直後（1. 【特集】等）を誤分割しない
_BRACKET_LABEL_RE = re.compile(
    r'(?<=.{10})'                                 # 前に十分なテキストがある
    r'(?=【[ぁ-んァ-ヶー一-龥]{1,4}】)'            # 日本語1〜4文字の【ラベル】
)

# 「短い語＋全角/半角コロン」形式のラベルの直前に改行を挿入
# 直前が句読点・括弧閉じ等の文末記号であることを必須とする
_COLON_LABEL_RE = re.compile(
    r'(?<=[。.!！）\)】：:])'                        # 直前が文末記号またはコロン（連続ラベル対応）
    r'(?=[ぁ-んァ-ヶー一-龥・]{2,12}[：:])'         # ラベル本体 + コロン（空白は任意）
)

def _split_labels(text):
    """行内に連結されたラベル付き項目を改行で分割する。"""
    lines = text.split('\n')
    result = []
    for line in lines:
        stripped = line.strip()
        # SECTION: / TITLE: / DATE: / --- / ■ 等の構造行は触らない
        if (stripped.startswith('SECTION:') or stripped.startswith('TITLE:')
                or stripped.startswith('DATE:') or stripped == '---'
                or stripped.startswith('■')):
            result.append(line)
            continue

        # 【…】 形式のラベル直前で改行
        tmp = _BRACKET_LABEL_RE.sub('\n', stripped)
        # コロンラベル直前で改行
        tmp = _COLON_LABEL_RE.sub('\n', tmp)

        split_lines = tmp.split('\n')
        result.extend(s for s in split_lines if s.strip())
    return '\n'.join(result)


def _shorten_header(h):
    """冗長なヘッダー名を短縮する（読みやすさ優先）"""
    # 括弧内の補足説明を除去  例「7月単月受注（対前年同月比）」→「7月単月受注」
    short = re.sub(r'（[^）]*）', '', h).strip()
    short = re.sub(r'\([^)]*\)', '', short).strip()
    # 「主な動向・分析ポイント」→「主な動向」
    short = re.sub(r'[・/／].*$', '', short).strip()
    # 冗長な修飾語を除去  「7月単月受注」→「7月受注」
    short = short.replace('単月', '')
    # 十分短ければそのまま、長ければ短縮版を使う
    return short if len(short) <= 15 else short[:15]


def _convert_md_table_block(lines):
    """Markdownテーブル行のリストを箇条書きに変換する。
    1行目をヘッダー、2行目がセパレータ(---)なら除去、残りをデータ行として扱う。
    ヘッダー行がない（セパレータがない）場合は全行をデータ行として扱う。"""
    if not lines:
        return []

    def parse_row(line):
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        return [c for c in cells if c]

    rows = [parse_row(l) for l in lines]
    if not rows:
        return []

    # セパレータ行の検出（--- のみの行）
    sep_idx = None
    for i, row in enumerate(rows):
        if all(re.match(r'^[-:]+$', c) for c in row):
            sep_idx = i
            break

    if sep_idx is not None and sep_idx > 0:
        headers = rows[sep_idx - 1]
        data_rows = rows[sep_idx + 1:]
    elif sep_idx == 0:
        headers = None
        data_rows = rows[1:]
    else:
        if len(rows) > 1 and len(rows[0]) >= 2:
            headers = rows[0]
            data_rows = rows[1:]
        else:
            return lines

    result = []
    for row in data_rows:
        if not row:
            continue
        if headers and len(headers) >= 2 and len(row) >= 2:
            parts = []
            for i in range(1, min(len(headers), len(row))):
                label = _shorten_header(headers[i])
                parts.append(f"{label} {row[i]}")
            result.append(f"{row[0]}：{'／'.join(parts)}")
        elif len(row) >= 2:
            result.append(f"{row[0]}：{'／'.join(row[1:])}")
        else:
            result.append(row[0])
    return result


def _convert_html_tables(text):
    """HTMLの<table>タグをMarkdownテーブルと同様に箇条書きへ変換する"""
    if '<table' not in text.lower():
        return text

    def _table_to_lines(match):
        table_html = match.group(0)
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL | re.IGNORECASE)
        parsed = []
        for row_html in rows:
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row_html, re.DOTALL | re.IGNORECASE)
            cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            if cells:
                parsed.append(cells)
        if len(parsed) < 2:
            return '\n'.join(' '.join(r) for r in parsed)

        headers = parsed[0]
        result = []
        for row in parsed[1:]:
            if not row:
                continue
            if len(headers) >= 2 and len(row) >= 2:
                parts = []
                for i in range(1, min(len(headers), len(row))):
                    label = _shorten_header(headers[i])
                    parts.append(f"{label} {row[i]}")
                result.append(f"{row[0]}：{'／'.join(parts)}")
            elif len(row) >= 2:
                result.append(f"{row[0]}：{'／'.join(row[1:])}")
            else:
                result.append(row[0])
        return '\n'.join(result)

    text = re.sub(r'<table[^>]*>.*?</table>', _table_to_lines, text, flags=re.DOTALL | re.IGNORECASE)
    return text


def convert_tables_in_report(text):
    """report_text内のMarkdownテーブルとHTMLテーブルを箇条書きに変換する。
    また、Markdown記法の除去・定型見出しの補完・ラベル改行も行う。"""
    # 0) Markdown記法（**太字** 等）を除去
    text = _strip_markdown(text)

    # 1) HTMLテーブルを変換
    text = _convert_html_tables(text)

    # 2) Markdownテーブルを変換
    lines = text.split('\n')
    result = []
    table_buf = []
    in_table = False

    for line in lines:
        stripped = line.strip()
        is_table_line = (bool(stripped)
                         and stripped.startswith('|')
                         and stripped.endswith('|')
                         and stripped.count('|') >= 3)

        if is_table_line:
            table_buf.append(stripped)
            in_table = True
        else:
            if in_table and table_buf:
                converted = _convert_md_table_block(table_buf)
                result.extend(converted)
                table_buf = []
                in_table = False
            result.append(line)

    if table_buf:
        converted = _convert_md_table_block(table_buf)
        result.extend(converted)

    # 3) SECTION: 行が60文字を超えていたら本文行に降格する
    final = []
    for line in result:
        stripped = line.strip()
        if stripped.startswith('SECTION:'):
            section_text = stripped[len('SECTION:'):].strip()
            if len(section_text) > 60:
                final.append(section_text)
            else:
                final.append(stripped)
        else:
            final.append(line)

    # 4) 定型見出し語を SECTION: に昇格
    final = _promote_known_headings(final)

    # 5) ラベル付き項目を改行で分割
    text = _split_labels('\n'.join(final))

    # 6) ラベルだけで本文が空の行を除去（読み手の混乱を防ぐ）
    _empty_label = re.compile(
        r'^(?:[ぁ-んァ-ヶー一-龥・]{2,12}[：:]|【[^】]{1,20}】)$'
    )
    text = '\n'.join(
        line for line in text.split('\n')
        if not _empty_label.match(line.strip())
    )

    return text
