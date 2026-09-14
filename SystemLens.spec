# Rebuild with: python -m PyInstaller --noconfirm SystemLens.spec
from PyInstaller.utils.hooks import collect_data_files

analysis = Analysis(
    ['desktop_entry.py'],
    pathex=[],
    binaries=[],
    datas=collect_data_files('webview') + [('systemlens/static', 'systemlens/static')],
    hiddenimports=['webview.platforms.winforms', 'webview.platforms.edgechromium'],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'pytest'],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz, analysis.scripts, analysis.binaries, analysis.datas, [],
    name='SystemLens',
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon='systemlens/static/systemlens.ico',
)
