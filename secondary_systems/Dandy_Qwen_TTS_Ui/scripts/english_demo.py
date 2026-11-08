"""Make the installed Qwen demo English-only; rerun after upgrading qwen-tts."""
from pathlib import Path
import ast
import re
import shutil
import sysconfig


def main():
    path = Path(sysconfig.get_path("purelib")) / "qwen_tts/cli/demo.py"
    source = path.read_text(encoding="utf-8")
    # The upstream UI supplies English text followed by Chinese translations.
    han = r"[\u3400-\u4dbf\u4e00-\u9fff]"
    localized = re.sub(r" ?\([^()\n]*" + han + r"[^()\n]*\)", "", source)
    localized = "\n".join(
        line for line in localized.split("\n") if not re.search(han, line)
    )
    localized = localized.replace(
        'label="Use x-vector only"',
        'label="Use x-vector only (no reference text needed; reduced quality)"',
    )
    ast.parse(localized)
    if localized != source:
        backup = path.with_suffix(".py.pre-english.bak")
        if not backup.exists():
            shutil.copy2(path, backup)
        path.write_text(localized, encoding="utf-8")
    print(f"English-only Qwen UI verified: {path}")


if __name__ == "__main__":
    main()
