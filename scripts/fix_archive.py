"""既存の archive.json / latest.json の壊れたレコードを修復するスクリプト。

usage:
    python scripts/fix_archive.py          # ドライラン（変更内容を表示するだけ）
    python scripts/fix_archive.py --apply  # 実際にファイルを書き換える
"""
import json
import os
import sys
import io

# Windows での UnicodeEncodeError 回避
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from table_utils import convert_tables_in_report

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE_PATH = os.path.join(BASE, "docs", "data", "archive.json")
LATEST_PATH = os.path.join(BASE, "docs", "data", "latest.json")

apply_mode = "--apply" in sys.argv


def fix_file(path):
    """JSONファイル内の report_text を修復する"""
    if not os.path.exists(path):
        print(f"  スキップ: {path} が見つかりません")
        return False

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    changed = False

    if isinstance(data, list):
        for entry in data:
            stamp = entry.get("stamp", "???")
            original = entry.get("report_text", "")
            fixed = convert_tables_in_report(original)
            if fixed != original:
                print(f"\n  [修復] stamp={stamp}")
                orig_lines = original.split('\n')
                fix_lines = fixed.split('\n')
                for i, (o, f_) in enumerate(zip(orig_lines, fix_lines)):
                    if o != f_:
                        print(f"    行{i+1} 変更前: {o[:100]}")
                        print(f"    行{i+1} 変更後: {f_[:100]}")
                if len(fix_lines) != len(orig_lines):
                    print(f"    行数: {len(orig_lines)} → {len(fix_lines)}")
                entry["report_text"] = fixed
                changed = True
            else:
                print(f"  [正常] stamp={stamp}")
    elif isinstance(data, dict):
        original = data.get("report_text", "")
        fixed = convert_tables_in_report(original)
        if fixed != original:
            stamp = data.get("stamp", "???")
            print(f"\n  [修復] stamp={stamp}")
            data["report_text"] = fixed
            changed = True
        else:
            print(f"  [正常] stamp={data.get('stamp', '???')}")

    if changed and apply_mode:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  ✓ {path} を更新しました")

    return changed


print("=" * 60)
print("archive.json / latest.json 修復ツール")
print("=" * 60)
if not apply_mode:
    print("【ドライラン】変更内容の確認のみ。実際に書き換えるには --apply を付けてください\n")

print(f"\n--- {ARCHIVE_PATH} ---")
archive_changed = fix_file(ARCHIVE_PATH)

print(f"\n--- {LATEST_PATH} ---")
latest_changed = fix_file(LATEST_PATH)

if not archive_changed and not latest_changed:
    print("\n修復が必要なレコードはありませんでした。")
elif not apply_mode:
    print("\n上記の変更を適用するには: python scripts/fix_archive.py --apply")
else:
    print("\n修復完了。")
