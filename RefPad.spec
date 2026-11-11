# PyInstaller recipe for RefPad for Windows. Build with:  py -3.12 tools/build_windows.py
# A folder build (not one big .exe): it starts much faster and the in-app updater can replace it.

EXCLUDES = [
    # Qt modules RefPad doesn't use (keeps the download small and the app light)
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
    "PySide6.QtWebSockets", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQuick3D",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput", "PySide6.Qt3DLogic", "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras", "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtSpatialAudio",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs", "PySide6.QtGraphsWidgets",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtXml",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtUiTools", "PySide6.QtBluetooth", "PySide6.QtNfc",
    "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtSerialBus",
    "PySide6.QtTextToSpeech", "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtStateMachine",
    "PySide6.QtHttpServer", "PySide6.QtPdfWidgets", "PySide6.QtPrintSupport", "PySide6.QtConcurrent",
    "PySide6.QtDBus", "PySide6.QtNetworkAuth", "PySide6.QtSvgWidgets", "PySide6.QtAxContainer",
    # Python packages that are installed on the build PC but not used by the app
    "tkinter", "unittest", "pydoc", "PIL", "fitz", "pymupdf", "pymupdf4llm", "numpy", "setuptools", "pip",
]

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    datas=[("refpad/assets", "refpad/assets")],
    hiddenimports=["PySide6.QtSvg", "PySide6.QtPdf", "PySide6.QtNetwork"],
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RefPad",
    icon="refpad/assets/refpad.ico",
    version="build/version_info.txt",
    console=False,
    upx=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="RefPad", upx=False)
