"""从 CHANGELOG.md 抽取指定版本的段落，写成 release_notes.md。

用法: python scripts/extract_notes.py v0.1.1      # 或 0.1.1
段落缺失或为空时退出码 1 —— 让发布流程直接失败，避免发一个没有说明的版本。
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"
OUTPUT = pathlib.Path.cwd() / "release_notes.md"


def extract(version: str, text: str) -> str:
    pattern = re.compile(
        rf"^##\s*\[{re.escape(version)}\][^\n]*\n(.*?)(?=^##\s*\[|\Z)",
        re.S | re.M,
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python scripts/extract_notes.py <version>", file=sys.stderr)
        return 2

    version = sys.argv[1].strip().lstrip("v")
    body = extract(version, CHANGELOG.read_text(encoding="utf-8"))
    if not body:
        print(f"CHANGELOG.md 缺少 [{version}] 段落或段落为空，请先补写发布说明", file=sys.stderr)
        return 1

    OUTPUT.write_text(body + "\n", encoding="utf-8")
    print(f"已生成 release_notes.md（{len(body)} 字符）")
    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
