# PlayBridge 1.2 — capture and stream options

## New controls

- Camera button or **F8**: save a PNG at the decoded source frame's native size, without window bars or UI controls.
- Record button or **F9**: arm/stop an MP4 recording with console audio. Recording waits for an H.264 IDR frame, then copies H.264/AAC packets without re-encoding.
- Folder button: open the capture library. Default location: **Videos/PlayBridge**, with Screenshots and Recordings subfolders.
- Settings: choose another capture folder, a quality profile and automatic reconnect.

## Quality targets

| Profile | Console bitrate target | PC presentation |
|---|---:|---|
| Data saver | 4 Mbit/s | Limited to about 30 fps |
| Balanced | 8 Mbit/s | Source cadence, nominal 60 fps |
| High quality | 12 Mbit/s | Source cadence, nominal 60 fps |

These profiles retain the tested 1080p capture path. The data-saver limit is a PC presentation limit: it is not a claim of native 30 fps capture. It intentionally replaces more decoded display frames to reduce conversion/upload work. Recordings preserve the source packet timing and are not limited by the PC presentation cap. Bitrates are encoder targets, not a guarantee of constant network usage.

Bitrate changes apply on the next connection. The new ELF acknowledges the capture request; the UI labels it as a target. An older manually loaded ELF can still stream, but the app shows that its profile is not confirmed.

## Automatic reconnect

When enabled, unexpected disconnects trigger retries after 2, 4 and then up to 8 seconds. Automatic mode reuploads the embedded ELF; manual mode waits for a separately loaded payload. Disconnect and closing the app cancel retries.

A recording is finalized when the connection ends. It does not silently combine media across separate capture sessions. Start another recording after recovery.

## Recording behaviour

- Console audio is recorded even when local playback is muted or its volume is reduced.
- Starting may wait until the next keyframe. If no complete video/audio start arrives, no finished MP4 is created.
- Packet writing runs on a separate worker, with queue limits of 240 packets and 32 MiB. An overloaded disk stops recording with a message instead of silently allowing an unbounded queue.
- Normal stop/close finalizes the MP4. A forced process termination or power loss may leave an unfinished partial file.
- Captures are local files; nothing is uploaded automatically.

## Validation

Seven automated tests cover valid H.264/AAC MP4 output, waiting for a later keyframe, cancellation without media, bounded-queue failure, native-sized PNG output, reconnect and manual cancellation.

Live tests on the owner's PS5 13.60 confirmed the acknowledged 4/8/12 Mbit/s targets, decoded video/audio and PNG captures. MP4 recordings were reopened and decoded for both video and audio. A forced socket interruption recovered into a second capture session, and the interrupted recording was finalized as a playable MP4. The new ELF was also tested with the previous 1.1.1 PC receiver.

The tests verify functionality and data flow; they do not establish every title/device combination, long-session stability, perfect A/V synchronization or total end-to-end latency. The presentation cap and final packaged-app UI are checked separately from headless capture tests.
