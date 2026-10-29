# Third-party notices

PlayBridge bundles components that retain their own copyright and license terms. Installed package license texts are preserved in [third-party-licenses](third-party-licenses/). This document does not replace those licenses.

| Component | Bundled version | Project/source |
|---|---|---|
| CPython | 3.12 runtime | https://github.com/python/cpython |
| PyAV | 19.0.2 | https://github.com/PyAV-Org/PyAV |
| FFmpeg shared libraries | 9.0.2 | https://ffmpeg.org/download.html and https://github.com/FFmpeg/FFmpeg |
| NumPy | 2.3.5 | https://github.com/numpy/numpy |
| CustomTkinter | 6.0.0 | https://github.com/TomSchimansky/CustomTkinter |
| Pillow | 12.3.0 | https://github.com/python-pillow/Pillow |
| sounddevice / PortAudio | sounddevice 0.5.6 | https://github.com/spatialaudio/python-sounddevice and https://github.com/PortAudio/portaudio |
| CFFI | 2.1.1 | https://github.com/python-cffi/cffi |
| darkdetect | 0.8.0 | https://github.com/albertosottile/darkdetect |
| PyInstaller bootloader | 6.22.3 | https://github.com/pyinstaller/pyinstaller |

The bundled libavutil reports **LGPL version 3 or later**. Its build also includes external codec libraries; those libraries have separate licenses. Do not infer the licensing of every bundled DLL from libavutil's reported string. PyAV's wheel build sources are available from the PyAV project; consult upstream build information for the corresponding FFmpeg and external-library sources.

The PyInstaller bootloader has a distribution exception described in its bundled COPYING.txt. Windows system APIs (GDI/WASAPI) are called at runtime. The PS5 homebrew payload calls console-owned native interfaces; no Sony firmware dumps or extracted proprietary PS5 system modules are included in these downloads.

PlayStation and PS5 are trademarks of Sony Interactive Entertainment. PlayBridge is independent and is not endorsed by Sony. App artwork and custom interface icons were created for this project.
