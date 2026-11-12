# Build with: python -m PyInstaller --noconfirm PlayBridge.spec
# The Qt Quick look (app/qt_shell.py and app/qml), the one PlayBridge opens with, goes in with only the parts of Qt it uses.
# PLAYBRIDGE_QT=0 leaves Qt out for a smaller EXE that has only the classic Tk window.
from pathlib import Path
import os,re,sys
from PyInstaller.utils.hooks import collect_all
root=Path(SPECPATH)
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
qt=os.environ.get('PLAYBRIDGE_QT','1')!='0'
datas=[];binaries=[];hidden=[]
for name in ('customtkinter','av','_sounddevice_data'):
 d,b,h=collect_all(name);datas+=d;binaries+=b;hidden+=h
# Some Python builds patch ssl.py to read a .pem file kept beside it. The EXE needs that file as well, or every HTTPS request, update
# checks included, fails in it. A standard Python has none.
import ssl
datas+=[(str(pem),'.') for pem in Path(ssl.__file__).parent.glob('*.pem')]
if not (root/'PlayBridge.elf').is_file():raise RuntimeError('Build or download PlayBridge.elf into the repository root first.')
a=Analysis([str(root/'app/playbridge.py')],pathex=[str(root/'app')],binaries=binaries,
 datas=datas+[(str(root/'app/assets'),'assets'),(str(root/'PlayBridge.elf'),'.')]+([(str(root/'app/qml'),'qml')] if qt else []),
 hiddenimports=hidden+['playbridge_ui','console_control','game_mode','scene','sound_board','pad_input','gdi_presenter','d3d11_presenter','graphics_card','audio_output','keep_awake','screen_rate','network_link','mic_mix','settings_look','payload_sender','live_broadcast','console_captures','frame_pacing','video_convert','hang_watch','updater','app_version','sounddevice','_sounddevice','_cffi_backend']
  +(['qt_shell','qt_models','PySide6.QtCore','PySide6.QtGui','PySide6.QtQml','PySide6.QtQuick'] if qt else []),
 excludes=(['PySide6'] if not qt else ['PySide6.QtWidgets','PySide6.QtWebEngineCore','PySide6.Qt3DCore'])+['PyQt5','PyQt6','matplotlib','pandas','scipy','IPython','pytest'],noarchive=False)
# The ssl module must load the OpenSSL that came with this Python. A shell with another OpenSSL of the same file name early on its
# PATH (Git Bash puts MSYS2's there) would otherwise have that one bundled, and every HTTPS request, update checks included, would
# fail in the EXE.
python_dlls=Path(sys.base_prefix)/'DLLs'
def own_openssl(entry):
 name=Path(entry[0]).name
 if name.lower().startswith(('libssl-','libcrypto-')) and (python_dlls/name).is_file():return (entry[0],str(python_dlls/name))+tuple(entry[2:])
 return entry
a.binaries=[own_openssl(entry) for entry in a.binaries]
if qt:
 # Qt brings every style, 3D, PDF and the designer tools along; the window uses the Basic style, Effects, Shapes and Dialogs, and reads PNG and JPEG.
 unused=re.compile(r'(?i)PySide6[\\/](qml[\\/](QtQuick[\\/](Controls[\\/](FluentWinUI3|Fusion|Imagine|Material|Universal|Windows|Native|designer)|Particles|Pdf|Scene2D|Scene3D|Timeline|VectorImage|VirtualKeyboard|LocalStorage|NativeStyle|tooling)|QtTest|Qt[\\/]labs)'
  r'|plugins[\\/](designer|qmltooling|sqldrivers|vectorimageformats|tls|networkinformation|generic|platforminputcontexts|styles|iconengines|imageformats[\\/]q(pdf|tiff|tga|wbmp|icns|svg|webp))'
  r'|plugins[\\/]platforms[\\/]q(direct2d|minimal|offscreen)|translations[\\/])'
  # The Qt libraries themselves land at the top of the bundle.
  r'|(^|[\\/])(Qt6(Quick3D|Pdf|VirtualKeyboard|QuickParticles|QuickTimeline|Designer|Help|Lottie|Labs|QmlCompiler|QmlDesignSupport|QuickTest|Test|Sql|UiTools|QuickVectorImage|QuickShapesDesignHelpers|QuickControls2(FluentWinUI3|Fusion|Imagine|Material|Universal|Windows|Native)|QuickNativeStyle|SvgWidgets|OpenGLWidgets|QuickWidgets|Widgets)\w*|opengl32sw)\.dll$')
 a.binaries=[entry for entry in a.binaries if not unused.search(entry[0])];a.datas=[entry for entry in a.datas if not unused.search(entry[0])]
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,a.binaries,a.datas,[],name='PlayBridge',console=False,debug=False,strip=False,upx=False,
 icon=str(root/'app/assets/playbridge.ico'),version=str(root/'app/version.txt'))
