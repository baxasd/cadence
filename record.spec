# PyInstaller spec — one-folder build of the Cadence RealSense recorder.
# Build with:  pyinstaller record.spec
# Output:      dist/CadenceRecorder/CadenceRecorder.exe  (distribute the whole folder)

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []

# pyrealsense2 ships a native .pyd plus RealSense DLLs; InquirerPy/prompt_toolkit
# resolve some modules lazily. Pull each in wholesale so nothing is missed.
for pkg in ("pyrealsense2", "InquirerPy"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["record.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CadenceRecorder",
    console=True,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="CadenceRecorder",
)
