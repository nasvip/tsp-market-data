"""本地复刻面板的 plugin.yaml 校验（backend/app/data_providers/custom/packages.py）。

避免再出现「usage_notes 必须是文本列表」这类导入期才暴露的格式错误。
用法: python scripts/validate_manifest.py
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

NAME = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
VERSION = re.compile(r"\d+\.\d+\.\d+(?:[a-zA-Z0-9.+-]*)\Z")
ENTRY = re.compile(r"[a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)*:[a-zA-Z_]\w*\Z")
DATASETS = {"daily", "adj_factor", "minute", "full_minute", "realtime", "depth5", "financial"}
TEXT_FIELDS = (
    "display_name", "description", "api_key_env", "homepage",
    "key_manage_url", "author", "billing", "billing_note", "install_hint",
)


def validate(doc):
    errors = []

    def fail(msg):
        errors.append(msg)

    if not isinstance(doc, dict):
        return ["plugin.yaml 必须是对象"]

    if not NAME.fullmatch(str(doc.get("name", ""))):
        fail("name 必须是小写字母开头的字母、数字、下划线")
    if not VERSION.fullmatch(str(doc.get("version", ""))):
        fail("version 必须是有效版本，例如 1.0.0")
    if type(doc.get("plugin_api_version")) is not int or doc["plugin_api_version"] != 1:
        fail("仅支持 plugin_api_version: 1")

    for field in ("entry", "check"):
        if field == "entry" or doc.get(field):
            if not ENTRY.fullmatch(str(doc.get(field, ""))):
                fail(f"{field} 应使用包内相对模块引用，例如 provider:MyProvider")

    datasets = doc.get("datasets")
    if not isinstance(datasets, list) or not datasets or any(
        not isinstance(x, str) or x not in DATASETS for x in datasets
    ):
        fail("datasets 必须声明已支持的数据集")

    for key in TEXT_FIELDS:
        if key in doc and (not isinstance(doc[key], str) or len(doc[key]) > 4000):
            fail(f"{key} 必须是文本且不超过 4000 字符")

    for key in ("homepage_label", "key_manage_label"):
        if key in doc and (not isinstance(doc[key], str) or len(doc[key]) > 200):
            fail(f"{key} 必须是文本且不超过 200 字符")

    if doc.get("api_key_env") and not re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", doc["api_key_env"]):
        fail("api_key_env 必须是大写环境变量名")

    for key in ("homepage", "key_manage_url"):
        if doc.get(key) and not doc[key].startswith("https://"):
            fail(f"{key} 必须使用 HTTPS")

    if "usage_notes" in doc and (
        not isinstance(doc["usage_notes"], list)
        or any(not isinstance(x, str) for x in doc["usage_notes"])
    ):
        fail("usage_notes 必须是文本列表")

    if doc.get("runtime", "none") not in ("none", "python"):
        fail("外部安装暂只支持 none/python 运行时")

    if doc.get("hidden"):
        fail("外部安装的插件不能隐藏卡片")

    # entry 指向的模块文件必须存在
    entry = str(doc.get("entry", ""))
    if ":" in entry:
        module = entry.split(":")[0].replace(".", "/")
        if not (ROOT / f"{module}.py").exists() and not (ROOT / module / "__init__.py").exists():
            fail(f"entry 模块不存在: {module}.py")

    return errors


def main():
    import yaml  # 仅开发期依赖

    doc = yaml.safe_load((ROOT / "plugin.yaml").read_text(encoding="utf-8"))
    errors = validate(doc)
    if errors:
        print("plugin.yaml 校验失败：")
        for e in errors:
            print("  -", e)
        return 1
    print("plugin.yaml 校验通过")
    print(f"  name={doc['name']} version={doc['version']} datasets={doc['datasets']}")
    print(f"  usage_notes={len(doc.get('usage_notes', []))} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
