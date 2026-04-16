# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

ffpyplayer_datas = collect_data_files('ffpyplayer')
ffpyplayer_binaries = collect_dynamic_libs('ffpyplayer')
ffpyplayer_hiddenimports = collect_submodules('ffpyplayer')


a = Analysis(
    ['program.py'],
    pathex=[],
    binaries=ffpyplayer_binaries,
    datas=ffpyplayer_datas + [('assets\\thumbnail.ico', 'assets')],
    hiddenimports=ffpyplayer_hiddenimports + ['cv2'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='Hudl',
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
    icon=['assets\\thumbnail.ico'],
)
