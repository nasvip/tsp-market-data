"""无 pytest 环境下的测试跑分器：行情与财务两个测试文件一起跑。"""
import importlib.util
import pathlib
import sys
import traceback

ROOT = pathlib.Path(__file__).resolve().parent.parent
FILES = ["test_quote.py", "test_finance.py"]

total = 0
failed = 0
for name in FILES:
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), ROOT / "tests" / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tests = sorted((n, f) for n, f in vars(module).items()
                   if n.startswith("test_") and callable(f))
    print(f"--- {name} ({len(tests)}) ---")
    for test_name, fn in tests:
        total += 1
        try:
            fn()
            print(f"  PASS  {test_name}")
        except Exception:
            failed += 1
            print(f"  FAIL  {test_name}")
            traceback.print_exc()

print(f"\n{total - failed}/{total} passed")
sys.exit(1 if failed else 0)
