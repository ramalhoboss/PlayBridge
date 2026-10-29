# Building PlayBridge from source

## Layout

    app/                    Python receiver and desktop interface
      assets/               App icon and control icons
      playbridge.py         Entry point and audio/video transport
      playbridge_ui.py      English console-style interface
      gdi_presenter.py      Windows DIB presentation
      video_convert.py      Deterministic conversion rounding
    payload/
      stream-av3.c          Firmware-13.60 native capture sender
      av-wire.h             Packet framing
    tools/
      build_payload.py      Configurable LLVM/SDK build wrapper
      make_assets.py        Recreate app artwork
    tests/
      test_border_conversion.py
    PlayBridge.spec         PyInstaller single-EXE recipe
    PlayBridge.elf          Reference payload used by the release

The sources call native modules already on the console. Firmware dumps and extracted console modules are not included or required as build inputs.

## Python environment — Windows x64

The published binary uses Python 3.12. Install a 64-bit Python 3.12 environment, then run these commands from the repository root:

    python -m venv .venv
    .venv\Scripts\python.exe -m pip install -r requirements-build.txt

The dependency versions match the development build. They are not vendored into this source tree. PLAYBRIDGE_DEPS is an optional path to an existing dependency directory; normal pip-based installations do not need it.

## Run the app

    .venv\Scripts\python.exe app\playbridge.py

The root PlayBridge.elf is used when running from source. Configure your own console IP in Connection settings. The source retains the release's initial development IP as a fallback; saved settings or --host override it.

    .venv\Scripts\python.exe app\playbridge.py --host 192.168.1.100

For a UI preview that does not contact the PS5:

    .venv\Scripts\python.exe app\playbridge.py --preview --seconds 15

The preview opens an audio device but does not receive video/audio. Do not interpret its empty audio callbacks as a live-stream failure.

## Compile the ELF

Required external tools:

- LLVM with clang, ld.lld and llvm-readobj.
- A compatible ps5-payload-sdk tree. The development setup used SDK v0.45, containing target/include, target/lib and ldscripts/elf_x86_64.x.

Set the paths for your machine; these are examples:

    .venv\Scripts\python.exe tools\build_payload.py --sdk C:\SDK\ps5-payload-sdk --llvm "C:\Program Files\LLVM\bin"

Alternatively, set PS5_PAYLOAD_SDK and put the LLVM tools on PATH. Output defaults to the repository-root PlayBridge.elf. To keep the reference ELF untouched while testing:

    .venv\Scripts\python.exe tools\build_payload.py --sdk C:\SDK\ps5-payload-sdk --llvm "C:\Program Files\LLVM\bin" --output build\PlayBridge.elf

The payload is explicitly restricted to firmware 13.60 / 0x13600007. Changing that guard alone does not port the native interfaces or module offsets to other firmware.

## Build the Windows EXE

    .venv\Scripts\python.exe -m PyInstaller --noconfirm PlayBridge.spec

The result is dist\PlayBridge.exe. The recipe includes the root ELF, application artwork and required Python/native dependency data. It uses installed packages, not paths to the original development PC.

The packaged EXE extracts its bundled runtime at launch. No separate Python installation is needed on the recipient PC. This is a self-contained application build, not a bit-for-bit reproducibility claim across different SDK/compiler/library builds.

## Recreate the artwork

    .venv\Scripts\python.exe tools\make_assets.py

## Run the conversion regression test

    .venv\Scripts\python.exe tests\test_border_conversion.py

The test checks six output sizes and RGB24/BGR0 paths using a synthetic uniform frame, then writes build\validation-border-conversion.json. The old-path defect is reported as a diagnostic; whether it reproduces depends on the FFmpeg build and hardware. The corrected path must not introduce bright pixels.

## Release provenance

The source addition makes development paths configurable and supports locating the ELF at the repository root. Capture parameters, firmware guard, packet framing, audio handling and the v1.1.1 border fix retain the released implementation. Third-party source and build information are linked from THIRD-PARTY-NOTICES.md.

Developed by [ramalhoboss](https://github.com/ramalhoboss) · [@nuno_leugim_10 on X](https://x.com/nuno_leugim_10).
