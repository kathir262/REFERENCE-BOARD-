"""Tests for RefPad for Windows: board layout, saving, undo, the updater's safety checks and toolbar fitting.

    py -3.12 -m pytest tests
"""
import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from refpad import paths
from refpad.core import store, updater
from refpad.core.store import BoardItem, Pose, State


def _items(sizes):
    out = []
    for i, (w, h) in enumerate(sizes):
        name = f"t{i}.jpg"
        (paths.IMG / name).write_bytes(b"x")
        it = BoardItem(name, w, h)
        it.fit_new()
        out.append(it)
    return out


def _no_overlap(items):
    rects = [it.bounds() for it in items]
    for a in range(len(rects)):
        for b in range(a + 1, len(rects)):
            inter = rects[a].intersected(rects[b])
            assert inter.width() < 0.5 or inter.height() < 0.5, (a, b)


SIZES = [(1600, 1200), (900, 1400), (2000, 800), (600, 600), (1200, 1800), (800, 1000)] * 4


def test_new_images_never_overlap(app):
    st = State()
    st.items.clear()
    for it in _items(SIZES):
        st.add_items([it])
    _no_overlap(st.items)


def test_arrange_makes_tidy_rows(app):
    st = State()
    st.items.clear()
    st.add_items(_items(SIZES))
    st.auto_arrange()
    _no_overlap(st.items)
    tops = sorted({round(it.bounds().top()) for it in st.items})
    assert 2 <= len(tops) < len(st.items)   # several rows, not one long line or one column


def test_board_is_saved_and_loaded(app):
    st = State()
    st.items.clear()
    st.add_items(_items([(1000, 800), (500, 900)]))
    st.items[0].flip, st.items[1].rot, st.items[1].gray = True, 3, True
    st.practice = [Pose("file", r"C:\pics\a.jpg"), Pose("pdf", r"C:\books\b.pdf", 7)]
    st.interval = 120
    st.open_doc(r"C:\books\b.pdf", 40)
    st.mode = store.PDF
    st.save_now()
    again = State()
    assert [it.to_json() for it in again.items] == [it.to_json() for it in st.items]
    assert [p.to_json() for p in again.practice] == [p.to_json() for p in st.practice]
    assert again.interval == 120 and again.mode == store.PDF
    assert again.doc.title == "b" and again.doc.pages == 40


def test_delete_and_undo_restore_order(app):
    st = State()
    st.items.clear()
    st.add_items(_items([(100, 100)] * 4))
    before = list(st.items)
    seen = []
    st.status.connect(lambda text, busy, undo: seen.append((text, undo)))
    st.remove_items([before[1], before[2]])
    assert len(st.items) == 2 and seen[-1][0] == "2 images deleted"
    seen[-1][1]()
    assert st.items == before


def test_recent_pdfs_are_capped_and_deduplicated(app):
    st = State()
    st.docs.clear()
    for i in range(14):
        st.open_doc(rf"C:\books\book{i}.pdf")
    st.open_doc(r"C:\BOOKS\book5.pdf")   # same file, different case
    assert len(st.docs) == store.MAX_DOCS
    assert st.doc.title == "book5" and sum(d.title == "book5" for d in st.docs) == 1


# ----------------------------------------------------------------------------- updater

def _release(tag, assets, prerelease=False):
    return {"tag_name": tag, "draft": False, "prerelease": prerelease, "body": "notes", "html_url": "https://github.com/x",
            "assets": [{"name": n, "browser_download_url": f"https://github.com/dl/{n}", "size": 10} for n in assets]}


def test_picks_newest_verified_windows_release():
    rels = [
        _release("v1.4.0", ["RefPad-1.4.0-windows-x64.zip"]),                                   # no checksum: ignored
        _release("v1.3.5", ["RefPad-1.3.5-windows-x64.zip", "RefPad-1.3.5-windows-x64.zip.sha256"], prerelease=True),
        _release("v1.3.0", ["RefPad-1.3.0-windows-x64.zip", "RefPad-1.3.0-windows-x64.zip.sha256", "app-release.aab"]),
        _release("v1.2.1", ["RefPad-1.2.1-windows-x64.zip", "RefPad-1.2.1-windows-x64.zip.sha256"]),
        _release("android-1.9", ["ReferenceBoard.apk"]),
    ]
    rel = updater.pick_release(rels, (1, 2, 0))
    assert rel.version == (1, 3, 0) and rel.sha_url.endswith(".sha256")
    assert updater.pick_release(rels, (1, 3, 0)) is None


def test_only_github_https_is_accepted():
    updater._check_host("https://github.com/a/b")
    updater._check_host("https://objects.githubusercontent.com/x")
    for bad in ("http://github.com/a", "https://github.com.evil.example/a", "https://example.com/a", "file:///C:/x"):
        with pytest.raises(updater.UpdateError):
            updater._check_host(bad)


class _Resp(io.BytesIO):
    def __init__(self, data, url):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}
        self._url = url

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


@pytest.fixture
def fake_install(tmp_path, monkeypatch):
    app_dir = tmp_path / "Programs" / "RefPad"
    (app_dir / "_internal").mkdir(parents=True)
    (app_dir / "RefPad.exe").write_bytes(b"old")
    monkeypatch.setattr(paths, "install_dir", lambda: app_dir)
    monkeypatch.setattr(paths, "is_frozen", lambda: True)
    return app_dir


def _serve(monkeypatch, zip_bytes, sha_text):
    def fake_open(url, timeout=15):
        updater._check_host(url)
        return _Resp(sha_text.encode() if url.endswith(".sha256") else zip_bytes, url)
    monkeypatch.setattr(updater, "_open", fake_open)
    return updater.Release((9, 0, 0), "", "https://github.com/dl/RefPad-9.0.0-windows-x64.zip", len(zip_bytes),
                           "https://github.com/dl/RefPad-9.0.0-windows-x64.zip.sha256", "https://github.com/x")


def test_download_verifies_and_unpacks(fake_install, monkeypatch):
    data = _zip({"RefPad/RefPad.exe": b"new", "RefPad/_internal/lib.dll": b"dll", "RefPad/Install RefPad.cmd": b"@echo"})
    rel = _serve(monkeypatch, data, hashlib.sha256(data).hexdigest() + "  RefPad-9.0.0-windows-x64.zip\n")
    new_dir = updater.download(rel)
    assert (new_dir / "RefPad.exe").read_bytes() == b"new"
    assert new_dir.parent == fake_install.parent / "RefPad.update"


def test_download_rejects_wrong_checksum(fake_install, monkeypatch):
    data = _zip({"RefPad/RefPad.exe": b"new", "RefPad/_internal/lib.dll": b"dll"})
    rel = _serve(monkeypatch, data, "0" * 64)
    with pytest.raises(updater.UpdateError, match="checksum"):
        updater.download(rel)
    assert not (fake_install.parent / "RefPad.update").exists()


def test_download_rejects_unsafe_paths(fake_install, monkeypatch):
    data = _zip({"RefPad/RefPad.exe": b"new", "RefPad/_internal/x": b"x", "../../evil.txt": b"boom"})
    rel = _serve(monkeypatch, data, hashlib.sha256(data).hexdigest())
    with pytest.raises(updater.UpdateError, match="unsafe"):
        updater.download(rel)
    assert not (fake_install.parent.parent / "evil.txt").exists()


def test_never_self_updates_a_shared_folder(fake_install):
    assert updater.can_self_update()
    (fake_install / "My holiday photos").mkdir()   # e.g. RefPad unpacked straight onto the Desktop
    assert not updater.can_self_update()


def test_version_parsing():
    assert updater.parse_version("v1.10.2") == (1, 10, 2)
    assert updater.parse_version("1.3") == (1, 3, 0)
    assert updater.parse_version("1.10.0") > updater.parse_version("1.9.9")


# ----------------------------------------------------------------------------- UI

def test_toolbar_moves_tools_into_more_when_narrow(app):
    from PySide6.QtWidgets import QWidget
    from refpad.ui.widgets import AdaptiveToolbar, ToolButton, make_action
    host = QWidget()
    tb = AdaptiveToolbar(compact=True, floating=False, parent=host)
    tools = [tb.add(ToolButton(make_action(host, f"T{i}", "add"), True), i if i > 1 else None) for i in range(10)]
    tb.finish()
    full = tb.fit(10_000)
    assert tb.more.isHidden() and all(not t.isHidden() for t in tools)
    need = tb.fit(full // 2)
    assert need <= full // 2 and not tb.more.isHidden()
    assert not tools[0].isHidden() and not tools[1].isHidden()   # never-hide tools stay
    assert tools[2].isHidden()                                    # lowest rank goes first


def test_settings_survive_restart():
    from refpad.settings import Settings
    s = Settings()
    s["chime"] = False
    s["float_opacity"] = 0.7
    again = Settings()
    assert again["chime"] is False and again["float_opacity"] == 0.7
    json.loads(Path(paths.SETTINGS_FILE).read_text())  # valid JSON on disk
