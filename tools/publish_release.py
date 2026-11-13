"""Publishes the Windows build as a GitHub release, so installed copies offer it with their UPDATE button.

    py -3.12 tools/build_windows.py      # builds dist/ for the version in refpad/__init__.py
    py -3.12 tools/publish_release.py    # creates release vX.Y.Z and uploads the three files

It uploads RefPad-Setup-X.Y.Z.exe, RefPad-X.Y.Z-windows-x64.zip and its .sha256 (the in-app updater needs the
zip and the checksum), with the notes in release-notes/X.Y.Z.md (shown in the update window).

It signs in to GitHub with the same login `git push` uses (Git Credential Manager), or with the GITHUB_TOKEN
environment variable if that is set. Run it again to replace the files of an existing release.
"""
import hashlib
import json
import os
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


def git(*args) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


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
        with urllib.request.urlopen(req, timeout=600) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        if e.code == 404 and method == "GET":
            return None
        sys.exit(f"GitHub said {e.code} for {method} {url}: {e.read().decode(errors='replace')[:400]}")


def main():
    v = __version__
    tag = f"v{v}"
    files = [DIST / f"RefPad-Setup-{v}.exe", DIST / f"RefPad-{v}-windows-x64.zip",
             DIST / f"RefPad-{v}-windows-x64.zip.sha256"]
    for f in files:
        if not f.exists():
            sys.exit(f"Missing {f}. Run tools/build_windows.py first.")
    zip_sha = hashlib.sha256(files[1].read_bytes()).hexdigest()
    if not files[2].read_text(encoding="utf-8").strip().lower().startswith(zip_sha):
        sys.exit("The .sha256 file doesn't match the zip; build again with tools/build_windows.py.")
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
        print(f"Updating existing release {tag}")

    existing = {a["name"]: a["id"] for a in rel.get("assets", [])}
    for f in files:
        if f.name in existing:
            call("DELETE", f"{API}/releases/assets/{existing[f.name]}", tok)
        ctype = {"exe": "application/vnd.microsoft.portable-executable", "zip": "application/zip"}.get(
            f.suffix.lstrip("."), "text/plain")
        print(f"Uploading {f.name} ({f.stat().st_size / 1e6:.1f} MB)…")
        call("POST", f"{UPLOADS}/releases/{rel['id']}/assets?name={f.name}", tok, data=f.read_bytes(), ctype=ctype)

    final = call("GET", f"{API}/releases/{rel['id']}", tok)
    names = sorted(a["name"] for a in final.get("assets", []))
    print(f"Done: {final['html_url']}")
    print("Files:", ", ".join(names))
    print("Installed copies offer this update within a day, or at once with ⋮ → Check for updates.")


if __name__ == "__main__":
    main()
