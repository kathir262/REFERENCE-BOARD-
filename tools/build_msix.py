"""Builds the Microsoft Store package (MSIX) of RefPad for Windows.

    py -3.12 tools/build_windows.py      # first: builds dist/RefPad
    py -3.12 tools/build_msix.py         # then: dist/RefPad-<version>.msix

The package needs the identity Microsoft gives your app in Partner Center (Product management ->
Product identity). Put those values in tools/windows/store.json (see microsoft-store/README.md):

    {
      "identity_name": "12345YourName.RefPad",
      "publisher": "CN=1A2B3C4D-....",
      "publisher_display_name": "Your publisher name"
    }

Without that file, `--test` builds a package with placeholder values, only to check that packaging works.
The Store signs the package itself when you upload it, so no code-signing certificate is needed.

The Store copy never updates itself: RefPad sees that it runs as a Store package and leaves updates to the Store.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from refpad import __version__  # noqa: E402
from make_win_icon import tile  # noqa: E402

DIST = Path(os.environ.get("REFPAD_DIST") or ROOT / "dist")
APP = DIST / "RefPad"
STAGE = ROOT / "build" / "msix"
CONFIG = ROOT / "tools" / "windows" / "store.json"
TILE_BG = (18, 18, 21, 255)     # the icon's own dark background, so tiles look like one piece

MANIFEST = """<?xml version="1.0" encoding="utf-8"?>
<Package
  xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
  xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
  xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
  IgnorableNamespaces="uap rescap">

  <Identity Name="{identity_name}" Publisher="{publisher}" Version="{version}" ProcessorArchitecture="x64" />

  <Properties>
    <DisplayName>{display_name}</DisplayName>
    <PublisherDisplayName>{publisher_display_name}</PublisherDisplayName>
    <Logo>Assets\\StoreLogo.png</Logo>
    <Description>Reference board, timed gesture practice and PDF reader for artists.</Description>
  </Properties>

  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.17763.0" MaxVersionTested="10.0.26100.0" />
  </Dependencies>

  <Resources>
    <Resource Language="en-us" />
  </Resources>

  <Applications>
    <Application Id="RefPad" Executable="RefPad\\RefPad.exe" EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements
        DisplayName="{display_name}"
        Description="Reference board, timed gesture practice and PDF reader for artists"
        BackgroundColor="transparent"
        Square150x150Logo="Assets\\Square150x150Logo.png"
        Square44x44Logo="Assets\\Square44x44Logo.png">
        <uap:DefaultTile Wide310x150Logo="Assets\\Wide310x150Logo.png" ShortName="RefPad">
          <uap:ShowNameOnTiles>
            <uap:ShowOn Tile="square150x150Logo" />
            <uap:ShowOn Tile="wide310x150Logo" />
          </uap:ShowNameOnTiles>
        </uap:DefaultTile>
      </uap:VisualElements>
      <Extensions>
        <uap:Extension Category="windows.fileTypeAssociation">
          <uap:FileTypeAssociation Name="refpad">
            <uap:DisplayName>RefPad board</uap:DisplayName>
            <uap:Logo>Assets\\Square44x44Logo.png</uap:Logo>
            <uap:SupportedFileTypes>
              <uap:FileType>.refpad</uap:FileType>
            </uap:SupportedFileTypes>
          </uap:FileTypeAssociation>
        </uap:Extension>
      </Extensions>
    </Application>
  </Applications>

  <Capabilities>
    <rescap:Capability Name="runFullTrust" />
  </Capabilities>
</Package>
"""

TEST_IDENTITY = {
    "identity_name": "RefPad.PackagingTest",
    "publisher": "CN=RefPad Packaging Test",
    "publisher_display_name": "RefPad (packaging test)",
}


def sdk_tool(name: str) -> Path:
    """The newest x64 copy of a Windows SDK tool (makeappx.exe, makepri.exe)."""
    base = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Windows Kits" / "10" / "bin"
    found = sorted(base.glob(f"10.*/x64/{name}"), key=lambda p: [int(x) for x in p.parent.parent.name.split(".")])
    if not found:
        sys.exit(f"{name} not found. Install the Windows 10/11 SDK (it comes with Visual Studio, or on its own).")
    return found[-1]


def square(size: int, unplated: bool = False) -> Image.Image:
    """The app icon as a rounded tile; 'unplated' (taskbar, Start list) has no square background around it."""
    return tile(size) if unplated or size <= 48 else _on_plate(tile(round(size * 0.78)), size, size)


def _on_plate(icon: Image.Image, w: int, h: int) -> Image.Image:
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(icon, ((w - icon.width) // 2, (h - icon.height) // 2), icon)
    return out


def wide(w: int, h: int) -> Image.Image:
    return _on_plate(tile(round(h * 0.7)), w, h)


def make_assets(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    for scale in (100, 125, 150, 200, 400):
        k = scale / 100
        square(round(44 * k)).save(folder / f"Square44x44Logo.scale-{scale}.png")
        square(round(150 * k)).save(folder / f"Square150x150Logo.scale-{scale}.png")
        wide(round(310 * k), round(150 * k)).save(folder / f"Wide310x150Logo.scale-{scale}.png")
        tile(round(50 * k)).save(folder / f"StoreLogo.scale-{scale}.png")
    # Exact pixel sizes for the taskbar, Start list and file icons (sharp instead of scaled).
    for size in (16, 20, 24, 30, 32, 36, 40, 48, 60, 64, 72, 80, 96, 256):
        tile(size).save(folder / f"Square44x44Logo.targetsize-{size}.png")
        tile(size).save(folder / f"Square44x44Logo.targetsize-{size}_altform-unplated.png")
        tile(size).save(folder / f"Square44x44Logo.targetsize-{size}_altform-lightunplated.png")


def main():
    test = "--test" in sys.argv
    if CONFIG.exists():
        ident = json.loads(CONFIG.read_text(encoding="utf-8"))
        missing = [k for k in ("identity_name", "publisher", "publisher_display_name") if not ident.get(k)]
        if missing:
            sys.exit(f"{CONFIG} is missing: {', '.join(missing)}")
    elif test:
        ident = dict(TEST_IDENTITY)
        print("No tools/windows/store.json: building a TEST package with placeholder identity values.")
    else:
        sys.exit(f"Missing {CONFIG}. Copy the values from Partner Center (see microsoft-store/README.md), "
                 f"or run with --test to check packaging only.")
    if not (APP / "RefPad.exe").exists():
        sys.exit(f"{APP / 'RefPad.exe'} not found. Run tools/build_windows.py first.")

    parts = [int(x) for x in __version__.split(".")]
    version = ".".join(str(x) for x in (parts + [0, 0, 0])[:3]) + ".0"   # the Store needs the last part to be 0
    values = dict(ident, version=version, display_name=ident.get("display_name") or "RefPad")

    print("Staging", STAGE)
    if STAGE.exists():
        shutil.rmtree(STAGE)
    shutil.copytree(APP, STAGE / "RefPad")
    make_assets(STAGE / "Assets")
    (STAGE / "AppxManifest.xml").write_text(MANIFEST.format(**values), encoding="utf-8")

    # resources.pri lets Windows pick the right icon size for each place it shows one.
    makepri = sdk_tool("makepri.exe")
    cfg = ROOT / "build" / "priconfig.xml"
    subprocess.run([str(makepri), "createconfig", "/cf", str(cfg), "/dq", "en-US", "/pv", "10.0.0", "/o"],
                   check=True, stdout=subprocess.DEVNULL)
    subprocess.run([str(makepri), "new", "/pr", str(STAGE), "/cf", str(cfg), "/mn", str(STAGE / "AppxManifest.xml"),
                    "/of", str(STAGE / "resources.pri"), "/o"], check=True, stdout=subprocess.DEVNULL)

    suffix = "-TEST" if ident is not None and ident.get("identity_name") == TEST_IDENTITY["identity_name"] else ""
    out = DIST / f"RefPad-{__version__}{suffix}.msix"
    makeappx = sdk_tool("makeappx.exe")
    subprocess.run([str(makeappx), "pack", "/d", str(STAGE), "/p", str(out), "/o"], check=True,
                   stdout=subprocess.DEVNULL)
    print(f"Built {out}  ({out.stat().st_size / 1e6:.1f} MB, package version {version})")
    if suffix:
        print("This TEST package has placeholder identity values: don't upload it. Add tools/windows/store.json.")


if __name__ == "__main__":
    main()
