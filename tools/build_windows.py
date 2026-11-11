"""Builds RefPad for Windows and the release files for GitHub.

    py -3.12 tools/build_windows.py

Output in dist/:
    RefPad/                               the app (run RefPad/RefPad.exe)
    RefPad-<version>-windows-x64.zip      upload to a GitHub release
    RefPad-<version>-windows-x64.zip.sha256   upload too: the in-app updater refuses updates without it
"""
import hashlib
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
APP = DIST / "RefPad"


def version() -> str:
    text = (ROOT / "refpad/__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__\s*=\s*"([^"]+)"', text).group(1)


def write_version_info(v: str):
    nums = tuple(int(x) for x in v.split(".")) + (0,)
    (ROOT / "build").mkdir(exist_ok=True)
    (ROOT / "build/version_info.txt").write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums[:4]}, prodvers={nums[:4]}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('FileDescription', 'RefPad - reference board, gesture practice and PDF reader'),
      StringStruct('FileVersion', '{v}'),
      StringStruct('ProductName', 'RefPad'),
      StringStruct('ProductVersion', '{v}'),
      StringStruct('OriginalFilename', 'RefPad.exe'),
      StringStruct('InternalName', 'RefPad'),
      StringStruct('LegalCopyright', 'Free software, no ads'),
    ])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""", encoding="utf-8")


def prune():
    """Removes parts of Qt the app never loads."""
    internal = APP / "_internal"
    removed = 0
    patterns = [
        "PySide6/translations", "PySide6/opengl32sw.dll", "PySide6/plugins/platforms/qminimal.dll",
        "PySide6/plugins/platforms/qoffscreen.dll", "PySide6/plugins/platforms/qdirect2d.dll",
        "PySide6/plugins/imageformats/qpdf.dll", "PySide6/plugins/imageformats/qicns.dll",
        "PySide6/plugins/imageformats/qwbmp.dll", "PySide6/plugins/generic", "PySide6/plugins/networkinformation",
        "PySide6/plugins/platforminputcontexts", "PySide6/qml", "PySide6/Qt6Quick.dll", "PySide6/Qt6Qml.dll",
        "PySide6/Qt6QmlModels.dll", "PySide6/Qt6QmlMeta.dll", "PySide6/Qt6QmlWorkerScript.dll", "PySide6/Qt6OpenGL.dll",
        "PySide6/Qt6VirtualKeyboard.dll",
        # Qt's own TLS (RefPad's updater uses Python's HTTPS, which brings its own OpenSSL)
        "PySide6/plugins/tls", "libcrypto-3-x64.dll", "libssl-3-x64.dll",
    ]
    for rel in patterns:
        p = internal / rel
        if p.is_dir():
            removed += sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
            shutil.rmtree(p)
        elif p.exists():
            removed += p.stat().st_size
            p.unlink()
    return removed


def folder_size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def main():
    v = version()
    write_version_info(v)
    subprocess.check_call([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--log-level", "WARN",
                           "--distpath", str(DIST), "--workpath", str(ROOT / "build/pyinstaller"), str(ROOT / "RefPad.spec")],
                          cwd=ROOT)
    removed = prune()
    for name in ("Install RefPad.cmd", "Uninstall RefPad.cmd"):
        shutil.copy2(ROOT / "tools/windows" / name, APP / name)

    zip_path = DIST / f"RefPad-{v}-windows-x64.zip"
    zip_path.unlink(missing_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted(APP.rglob("*")):
            if f.is_file():
                z.write(f, Path("RefPad") / f.relative_to(APP))
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (DIST / (zip_path.name + ".sha256")).write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")

    print(f"RefPad {v}")
    print(f"  app folder: {folder_size(APP) / 1024 / 1024:.1f} MB (removed {removed / 1024 / 1024:.1f} MB of unused Qt)")
    print(f"  {zip_path.name}: {zip_path.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"  sha256: {digest}")


if __name__ == "__main__":
    main()
