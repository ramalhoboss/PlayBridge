# Changelog

## v1.2.0 — development preview
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
