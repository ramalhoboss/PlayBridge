# Changelog

## v1.4.2 — 2026-11-04
- FSR 1 upscaling, a switch in Settings → Picture, off by default. When the screen is larger than the stream, the GPU video output enlarges the picture with AMD FidelityFX Super Resolution 1 (EASU), and Sharpen picture uses its sharpening (RCAS). The colour is converted at the stream's own size first, because FSR works in RGB. At the same size or smaller, the output is unchanged.
- On the owner's RX 6600, enlarging 1080p to 4K took about 3.0 ms of GPU time per frame against 3.6 ms with the previous bicubic scaling, and 3.5 against 4.0 ms with sharpening. On PS5 captures reduced to 1080p and enlarged again, the result measured about the same as before, with slightly cleaner text edges. It has not yet been compared on a live PS5 stream.
- AMD's FSR 1 code is under the MIT license, included in third-party-licenses/amd-fsr1.
- The payload is unchanged from v1.4.0.

## v1.4.1 — 2026-11-04
- An IP address typed in Settings is always the one PlayBridge uses. In v1.4.0, when nothing answered at the saved address and exactly one PS5 answered the network search, PlayBridge switched to that console and saved its address over the typed one, so a wrong or test address still connected to the console on the network.
- PlayBridge still finds the console by itself while no address has been typed, and still follows it to a new address given by the router. Installs from v1.4.0 keep that behaviour until an address is typed.
- When the connection fails, the message names the address that was tried, and the address of a PS5 that answered instead, if one did.
- The payload is unchanged from v1.4.0.

## v1.4.0 — 2026-11-02
- Games page. During a session the payload opens a control port, 9077, and the PC reads the console's installed games: title, cover, the game's own music where it has one, play time, last played and size. Covers and music are kept on the PC. On the owner's PS5, a library of 54 games read all its covers and music.
- Play launches the selected game, and the page changes to Live when its picture arrives, about 1.1 seconds after the click on the owner's PS5. Resume returns to the running game, and Close game closes it after asking. Rows for all games, most played, A to Z, PS5 and PS4 games, and search by typing.
- Gaming Mode: the games fullscreen on the PC. When the console's own menu comes to the front, the PC shows the games instead, and the TV still shows the PS5.
- Console status: the game in front, and CPU and SoC temperature. Power: rest mode (confirmed on the console), soft reset (close the game and launch it again), reboot and turn off (not yet run on a console), each behind a question. Recovery explains how to start Safe Mode from the console itself; PlayBridge never starts Safe Mode.
- Direct3D 11 video output is the default. The GPU decodes the video and the picture stays on it for colour conversion, scaling, optional sharpening and presentation. On the owner's PS5 over Wi-Fi, against GDI: 0.22–0.23 instead of 1.29–1.43 processor cores, 59.8–59.9 instead of 59.7–59.9 screen updates per second, and a 95th-percentile frame interval of 17.2–17.4 instead of 18.3–18.4 ms. If Direct3D 11 fails, PlayBridge returns to GDI by itself, and a switch in Settings turns it off.
- The refresh clock learns the monitor's refresh length only from intervals close to one refresh, and leaves out the first, partial interval after a start or a pause. A missed refresh used to stretch the length for about two seconds, so the clock ran fast and frames were skipped in clusters. In local runs of 30 seconds, skipped frames went from 1, 2 and 28 to 0, 0 and 1. Not yet measured on the console.
- Instant replay keeps the last 30 seconds, 60 seconds or 2 minutes of the stream in PC memory, up to 1 GB, and F10 saves it as an MP4 without re-encoding.
- New one-window design: Games, Live and Media in a top bar with search, Settings, fullscreen and power. Settings is a page with Console, Picture, Captures, Sound and Appearance. Black frosted cards with a hairline rim, white type and gold as a small accent.
- The library has quiet background music and navigation sounds made by the app, or the game's own music. They play on their own output, only while the games are on screen, with their own switches and volume.
- Session panel (Ctrl+I) with the frame rate, source size, PC timing, the console's game, a 60-second bitrate graph and diagnostics export.
- Sharper picture on the GDI output: area averaging when shrinking to half size or less, bicubic otherwise, and full chroma interpolation, which also fixes a picture about 2 levels too dark.
- The payload opens the capture again, up to three times, after certain read errors or 3 seconds without video, instead of ending the session.
- Before sending the ELF, PlayBridge asks the console for its state, and stops with a message if it is resting or runs a firmware other than 13.60.
- A controller on the PC can move around the Games page. It is not sent to the console: a virtual controller on the console is not available yet.

## v1.3.0 — 2026-10-30
- Experimental 1440p and 4K profiles. They need a console output at that resolution, step down when the firmware does not allow it, and report the step down in the status bar. On real hardware with a 4K output, all six profiles streamed at their native size on the console's menus. In a game, the 4K profiles kept a 60 fps stream at 38–69 Mbit/s and the 30 and 50 Mbit/s 1440p profiles at 25–29 Mbit/s, in short runs with no stalls or dropped video; the game itself was drawing about 30 fps. A 4K MP4 recording also reopened and decoded cleanly. The step down from a 1080p output was also run on real hardware.
- The encoder's frame budget is now 1 MiB. The old value, one 8 Mbit/s frame's share, made the encoder skip frames after every keyframe and lowered the frame rate. On real hardware, a larger budget took a game scene's stream from about 35 to 60 frames per second with no stalls.
- Above 1080p the audio queue can grow to 160 ms instead of 60 ms, because audio arrives late behind large frames. On real hardware at 4K this reduced audio trims from 9 to 1–2 in 25 seconds, at the cost of more audio delay.
- Video is now painted one frame per monitor refresh from a short queue, instead of as soon as each frame is ready. On real hardware, the share of game pictures shown for the right length of time rose from 70–76% to 97% at 4K and from 83–96% to 99% at 1080p, at the cost of more video delay (about 40–43 ms at 1080p and 49–62 ms at 4K from receiving a frame to painting it, against about 5 ms at 4K before). One of five 4K runs of the packaged app was much worse, with a 400 ms hold, for a reason not found.
- Video decoding moved off the socket thread, so a slow decoder drops video until the next keyframe instead of stalling audio or ending the session.
- Moving the mouse over the video no longer makes the picture flicker. In fullscreen the pointer hides after 2.5 seconds without movement.
- Pure black interface with thin gold bezels, polished gold headings and main buttons, and a gold logo. Rims and buttons are drawn as pictures, with curves calculated at eight times the size.
- Navigation for Live, Media, Stats and Setup, and a stats panel with source size, presented fps, PC timing and a 60-second bitrate graph.
- The capture library has filters and paging. Recordings show a still from the video instead of a placeholder.
- Find console looks for the PS5 on the local network, and favourites save named consoles with their quality profile.
- Export diagnostics saves a ZIP of measurements without IP addresses, device names, file paths or logs.

## v1.2.0 — 2026-10-29
- Native-resolution PNG screenshots and packet-copy H.264/AAC MP4 recording.
- Capture library and F8/F9 shortcuts.
- Bounded asynchronous recording queue and graceful finalization on disconnect.
- Automatic reconnect with cancellable backoff.
- Negotiated 4/8/12 Mbit/s targets and an explicitly local 30 fps presentation cap in Data saver.
- Backward-compatible capture protocol; older payload profiles are marked unconfirmed.

## v1.1.1
- Fixed blinking bright dashes at the left video edge with deterministic conversion rounding.
- Preserved native frame content, GDI video and WASAPI audio.
- Validated six conversion sizes and a real 20-second session.

## v1.1.0
- Console-inspired navy/blue interface and custom control icons.
- English labels, connection states, tooltips and user-facing connection errors.

## Initial development
- Combined native H.264/AAC capture.
- Automatic ELF deployment from the PC.
- Recent-frame presentation and bounded PCM buffering.
