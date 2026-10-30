# Changelog

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
