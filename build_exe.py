import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
TMP = os.path.join(tempfile.gettempdir(), "opencode")
WORK = os.path.join(TMP, "exe_build")

EDITOR_SRC = os.path.join(ROOT, "chrome_report_edit_v1.41.py")
GENERATOR_SRC = os.path.join(ROOT, "chrome_report_v1.4.py")

EDITOR_OLD = """    global BASE
    BASE = os.path.realpath(args.dir or os.path.dirname(
        os.path.abspath(__file__)))"""

EDITOR_NEW = """    global BASE
    BASE = os.path.realpath(args.dir or (
        os.path.dirname(os.path.abspath(sys.executable))
        if getattr(sys, "frozen", False)
        else os.path.dirname(os.path.abspath(__file__))))"""


def build_exe(name, source):
    os.makedirs(WORK, exist_ok=True)
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile", "--console", "--clean", "--noconfirm",
        "--name", name,
        "--distpath", ROOT,
        "--workpath", os.path.join(WORK, name),
        "--specpath", os.path.join(WORK, name),
        source,
    ]
    print("RUN:", " ".join(cmd))
    subprocess.check_call(cmd)
    assert os.path.isfile(os.path.join(ROOT, name + ".exe")), name + ".exe missing"


def frozen_copy():
    with open(EDITOR_SRC, "r", encoding="utf-8") as fh:
        src = fh.read()
    assert src.count(EDITOR_OLD) == 1, "frozen-guard anchor not found exactly once"
    frozen = src.replace(EDITOR_OLD, EDITOR_NEW)
    os.makedirs(TMP, exist_ok=True)
    path = os.path.join(TMP, "chrome_report_edit_v1.41_frozen.py")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(frozen)
    return path


def main():
    build_exe("chrome_report_v1.4", GENERATOR_SRC)
    editor_src = frozen_copy()
    try:
        build_exe("chrome_report_edit_v1.41", editor_src)
    finally:
        os.remove(editor_src)
    print("Done. Deliveries in %s" % ROOT)


if __name__ == "__main__":
    main()