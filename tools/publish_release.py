"""Publishes RefPad as a GitHub release, so installed copies offer it with their UPDATE button.

    py -3.12 tools/build_windows.py                     # Windows: dist/ for the version in refpad/__init__.py
    cd android && gradlew assembleDirectRelease         # Android: the website APK (signed with your private key)
    py -3.12 tools/publish_release.py                   # creates release vX.Y.Z and uploads everything

Uploaded files:
- RefPad-Setup-X.Y.Z.exe, RefPad-X.Y.Z-windows-x64.zip and .sha256   (Windows installer + in-app updater)
- RefPad-X.Y.Z-android.apk and .sha256                                 (Android website version + in-app updater)
- RefPad-Setup.exe and RefPad-Android.apk                              (same files under fixed names, for the
  website's one-click links: https://github.com/<repo>/releases/latest/download/RefPad-Android.apk)

Notes come from release-notes/X.Y.Z.md (shown in the update window). `--only windows` or `--only android`
publishes just one platform (adding it to an existing release). It signs in with the same login `git push`
uses (Git Credential Manager), or GITHUB_TOKEN if set. Run it again to replace the files of a release.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from refpad import GITHUB_REPO, __version__  # noqa: E402

DIST = Path(os.environ.get("REFPAD_DIST") or ROOT / "dist")
API = f"https://api.github.com/repos/{GITHUB_REPO}"
UPLOADS = f"https://uploads.github.com/repos/{GITHUB_REPO}"
APK_BUILD = ROOT / "android/app/build/outputs/apk/direct/release/ReferenceBoard-directRelease.apk"


def git(*args) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def token() -> str:
    if os.environ.get("GITHUB_TOKEN"):
        return os.environ["GITHUB_TOKEN"]
    out = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                         cwd=ROOT, capture_output=True, text=True,
                         env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    for line in out.stdout.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    sys.exit("No GitHub login found. Push once with git (it saves the login), or set GITHUB_TOKEN.")


def call(method: str, url: str, tok: str, body=None, data: bytes = None, ctype: str = None):
    headers = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "RefPad-release-script"}
    if body is not None:
        data = json.dumps(body).encode()
        ctype = "application/json"
    if ctype:
        headers["Content-Type"] = ctype
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        if e.code == 404 and method == "GET":
            return None
        sys.exit(f"GitHub said {e.code} for {method} {url}: {e.read().decode(errors='replace')[:400]}")


def windows_files(v: str) -> list:
    setup = DIST / f"RefPad-Setup-{v}.exe"
    zip_ = DIST / f"RefPad-{v}-windows-x64.zip"
    sha = DIST / f"RefPad-{v}-windows-x64.zip.sha256"
    for f in (setup, zip_, sha):
        if not f.exists():
            sys.exit(f"Missing {f}. Run tools/build_windows.py first.")
    if not sha.read_text(encoding="utf-8").strip().lower().startswith(sha256(zip_)):
        sys.exit("The Windows .sha256 file doesn't match the zip; build again with tools/build_windows.py.")
    fixed = DIST / "RefPad-Setup.exe"
    shutil.copyfile(setup, fixed)
    return [setup, zip_, sha, fixed]


def android_files(v: str) -> list:
    gradle = (ROOT / "android/app/build.gradle").read_text(encoding="utf-8")
    m = re.search(r'versionName\s+"([^"]+)"', gradle)
    if not m or m.group(1) != v:
        sys.exit(f"android/app/build.gradle has versionName {m.group(1) if m else '?'}, not {v}: make them the same.")
    if not (ROOT / "android/keystore.properties").exists():
        sys.exit("No private Android key (android/keystore.properties): run tools/make_android_key.py first.")
    if not APK_BUILD.exists():
        sys.exit(f"Missing {APK_BUILD}. Run: cd android && gradlew assembleDirectRelease")
    if APK_BUILD.stat().st_mtime < (ROOT / "android/keystore.properties").stat().st_mtime:
        sys.exit("The APK was built before the private key existed: build it again (gradlew assembleDirectRelease).")
    apk = DIST / f"RefPad-{v}-android.apk"
    DIST.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(APK_BUILD, apk)
    sha = DIST / f"{apk.name}.sha256"
    sha.write_text(f"{sha256(apk)}  {apk.name}\n", encoding="utf-8")
    fixed = DIST / "RefPad-Android.apk"
    shutil.copyfile(apk, fixed)
    return [apk, sha, fixed]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["windows", "android"])
    ap.add_argument("--version", help="release version (default: refpad/__init__.py); e.g. an Android-only fix")
    args = ap.parse_args()
    v = args.version or __version__
    tag = f"v{v}"
    files = []
    if args.only != "android":
        files += windows_files(v)
    if args.only != "windows":
        files += android_files(v)
    if args.only == "android" and (DIST / "RefPad-Setup.exe").exists():
        # The website's Windows button points at the newest release; keep the current installer there too.
        files.append(DIST / "RefPad-Setup.exe")
    notes_file = ROOT / "release-notes" / f"{v}.md"
    if not notes_file.exists():
        sys.exit(f"Write the release notes first: {notes_file}")
    notes = notes_file.read_text(encoding="utf-8").strip()

    # The release points at the current commit, which must already be on GitHub.
    head = git("rev-parse", "HEAD")
    git("fetch", "-q", "origin")
    if subprocess.run(["git", "merge-base", "--is-ancestor", head, "origin/main"], cwd=ROOT).returncode != 0:
        sys.exit("This commit isn't on GitHub yet: push it first (git push origin main).")

    tok = token()
    rel = call("GET", f"{API}/releases/tags/{tag}", tok)
    if rel is None:
        rel = call("POST", f"{API}/releases", tok, {
            "tag_name": tag, "target_commitish": head, "name": f"RefPad {v}", "body": notes,
            "draft": False, "prerelease": False, "make_latest": "true"})
        print(f"Created release {tag}")
    else:
        rel = call("PATCH", f"{API}/releases/{rel['id']}", tok, {"name": f"RefPad {v}", "body": notes,
                                                                    "draft": False, "prerelease": False})
        print(f"Updating release {tag}")

    existing = {a["name"]: (a["id"], a["size"]) for a in rel.get("assets", [])}
    types = {".exe": "application/vnd.microsoft.portable-executable", ".zip": "application/zip",
             ".apk": "application/vnd.android.package-archive"}
    for f in files:
        if f.name in existing:
            if existing[f.name][1] == f.stat().st_size and f.suffix != ".sha256":
                print(f"{f.name} is already there")
                continue
            call("DELETE", f"{API}/releases/assets/{existing[f.name][0]}", tok)
        print(f"Uploading {f.name} ({f.stat().st_size / 1e6:.1f} MB)...", flush=True)
        call("POST", f"{UPLOADS}/releases/{rel['id']}/assets?name={f.name}", tok, data=f.read_bytes(),
             ctype=types.get(f.suffix, "text/plain"))

    final = call("GET", f"{API}/releases/{rel['id']}", tok)
    print(f"Done: {final['html_url']}")
    print("Files:", ", ".join(sorted(a["name"] for a in final.get("assets", []))))
    print(f"One-click links: https://github.com/{GITHUB_REPO}/releases/latest/download/RefPad-Android.apk")
    print(f"                 https://github.com/{GITHUB_REPO}/releases/latest/download/RefPad-Setup.exe")


if __name__ == "__main__":
    main()
