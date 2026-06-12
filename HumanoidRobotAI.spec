# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['E:\\Codex\\humanoid robot\\launcher.py'],
    pathex=[],
    binaries=[],
    datas=[('E:\\Codex\\humanoid robot\\main.py', '.'), ('E:\\Codex\\humanoid robot\\main_rpi.py', '.'), ('E:\\Codex\\humanoid robot\\robot_hardware.py', '.'), ('E:\\Codex\\humanoid robot\\arm_servo_test.py', '.'), ('E:\\Codex\\humanoid robot\\face_servo_test.py', '.'), ('E:\\Codex\\humanoid robot\\.env.example', '.')],
    hiddenimports=['zoneinfo', 'winreg', 'ctypes', 'urllib.request', 'urllib.parse', 'urllib.error', 'email.mime.text', 'email.mime.multipart'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'pandas', 'notebook', 'IPython'],
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
    name='HumanoidRobotAI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
