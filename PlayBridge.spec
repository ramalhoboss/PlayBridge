# Build with: python -m PyInstaller --noconfirm PlayBridge.spec
from pathlib import Path
import os,sys
from PyInstaller.utils.hooks import collect_all
root=Path(SPECPATH)
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
datas=[];binaries=[];hidden=[]
for name in ('customtkinter','av','_sounddevice_data'):
 d,b,h=collect_all(name);datas+=d;binaries+=b;hidden+=h
if not (root/'PlayBridge.elf').is_file():raise RuntimeError('Build or download PlayBridge.elf into the repository root first.')
a=Analysis([str(root/'app/playbridge.py')],pathex=[str(root/'app')],binaries=binaries,
 datas=datas+[(str(root/'app/assets'),'assets'),(str(root/'PlayBridge.elf'),'.')],
 hiddenimports=hidden+['playbridge_ui','console_control','game_mode','scene','sound_board','pad_input','gdi_presenter','d3d11_presenter','graphics_card','audio_output','keep_awake','screen_rate','network_link','mic_mix','settings_look','payload_sender','live_broadcast','console_captures','frame_pacing','video_convert','hang_watch','sounddevice','_sounddevice','_cffi_backend'],
 excludes=['PySide6','PyQt5','PyQt6','matplotlib','pandas','scipy','IPython','pytest'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,a.binaries,a.datas,[],name='PlayBridge',console=False,debug=False,strip=False,upx=False,
 icon=str(root/'app/assets/playbridge.ico'),version=str(root/'app/version.txt'))
