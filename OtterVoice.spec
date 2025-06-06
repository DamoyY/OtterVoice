# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['G:\\OneDrive\\1\\OneDrive - 8nb78w\\OtterVoice\\OtterVoice.py'],
    pathex=[],
    binaries=[],
    datas=[('G:\\OneDrive\\1\\OneDrive - 8nb78w\\OtterVoice\\image__2__o6e_icon.ico', '.'), ('G:\\OneDrive\\1\\OneDrive - 8nb78w\\OtterVoice\\notification_call.wav', '.'), ('G:\\OneDrive\\1\\OneDrive - 8nb78w\\OtterVoice\\notification_hangup.wav', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['numpy', 'PIL'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='OtterVoice',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['G:\\OneDrive\\1\\OneDrive - 8nb78w\\OtterVoice\\image__2__o6e_icon.ico'],
)
