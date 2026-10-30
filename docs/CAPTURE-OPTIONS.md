# PlayBridge capture and stream options

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
| Very high | 16 Mbit/s | Source cadence, nominal 60 fps |
| Ultra | 20 Mbit/s | Source cadence, nominal 60 fps |
| Maximum | 30 Mbit/s | Source cadence, nominal 60 fps |

These profiles retain the tested 1080p capture path. The data-saver limit is a PC presentation limit: it is not a claim of native 30 fps capture. It intentionally replaces more decoded display frames to reduce conversion/upload work. Recordings preserve the source packet timing and are not limited by the PC presentation cap. Bitrates are encoder targets, not a guarantee of constant network usage.

Bitrate changes apply on the next connection. The new ELF acknowledges the capture request; the UI labels it as a target. An older manually loaded ELF can still stream, but the app shows that its profile is not confirmed.

## 1440p and 4K profiles (experimental)

| Resolution | Bitrate targets | PS5 video output needed |
|---|---:|---|
| 2560×1440, 60 fps | 20, 30 or 50 Mbit/s | 1440p or 4K |
| 3840×2160, 60 fps | 40, 60 or 80 Mbit/s | 4K |

The capture follows the console's video output, so these profiles need a display that accepts that resolution, with the PS5 set to use it. Window scaling or a higher bitrate does not replace this: on a 1080p output the firmware refuses a higher capture with `0x81950008`.

The payload reads the output mode before opening the capture. If the output is too low it streams the highest resolution that output allows, lowers the bitrate to that resolution's limit (30 Mbit/s for 1080p, 50 Mbit/s for 1440p) and the status bar says so. If the firmware still refuses, or no encoder resource is free, the payload steps down the same way and the status bar shows the refusal code; `0xffffffff` means no encoder resource.

Software decoding at these sizes uses frame threads, which add 1 frame of delay at 1440p and 2 at 4K (about 17 and 33 ms at 60 fps). If the PC still cannot keep up, video packets are dropped until the next keyframe, so audio and the connection continue. Image quality on screen is also limited by the PC display: a 1080p monitor shows the image scaled down, while PNG and MP4 captures keep the native size.

Use an HDMI cable rated for 4K at 60 Hz. On the test setup, a cable that worked at 1080p gave no picture at 2160p, and a different cable fixed it.

**Validation:** on the owner's PS5 13.60 with a 4K output (output mode `0x13c`), all six profiles were acknowledged and streamed at their native size at 60 fps, with no stalls, console overruns or errors, on the console's menus at about 1–9 Mbit/s. At 4K, those menus had about five times more detail above the 1080p limit than the same frame passed through 1080p, so the capture is not a scaled 1080p image. A coded 2560×1440 or 3840×2160 stream still does not prove that a given game renders at that resolution.

Live test on the owner's PS5 13.60 with a 1080p output, on the mostly static home screen: all six 1080p profiles were acknowledged and streamed 1920×1080 with audio. Requests for 1440p and 4K stepped down to 1080p, gave the output notice and capped the bitrate at 30 Mbit/s. The firmware-refusal step down did not run, because the output check stopped those requests first.

**Encoder frame budget:** the encoder skips frames after any frame larger than its byte budget, and a frame costing N budgets loses N-1 frames. This matched all 37 keyframes measured in a live game. With a budget of one frame's share of the bitrate, a 200 KB keyframe at 8 Mbit/s lost 11 frames (a 200 ms stall), and frames just over the budget held some scenes at about 35 fps. The budget is now 1 MiB at every resolution, because rate control holds the bitrate without it. On a live 1080p capture, 1.5 MB was accepted and `Start` refused 2 MiB with `0x80c78000`.

Results on the same console:

- With the character running in a game, the 1 MiB budget held 60 fps with no stalls, console overruns or errors. The stream received about 8.2 Mbit/s on the 8 Mbit/s profile, 18.8 on the 20 Mbit/s profile and 23–25 on the 30 Mbit/s profile.
- With the character standing still, all six 1080p profiles held 60 fps with no stalls, console overruns or errors, at about 4–7 Mbit/s.
- Frame-threaded decoding also ran on this real 1080p stream and closed cleanly.

On the same console with a 4K output and the character running in a game, in runs of about 14 seconds each:

| Resolution | Target | Received | Capture rate |
|---|---:|---:|---:|
| 3840×2160 | 80 Mbit/s | 68.6 Mbit/s | 60 fps |
| 3840×2160 | 60 Mbit/s | 53.3 Mbit/s | 60 fps |
| 3840×2160 | 40 Mbit/s | 38.3 Mbit/s | 60 fps |
| 2560×1440 | 50 Mbit/s | 29.0 Mbit/s | 60 fps |
| 2560×1440 | 30 Mbit/s | 25.0 Mbit/s | 60 fps |

- None of these runs had stalls, dropped video, console overruns or errors. The largest keyframe was 434 KB, well under the 1 MiB budget. The 20 Mbit/s 1440p profile was not run in a game.
- The packaged app, with the audio queue and presentation described below, ran the 80 Mbit/s 4K profile in its window for five runs of about 30 seconds. The results are under **Presentation on the PC**. The last three runs had no dropped video or errors.
- A 20-second MP4 on the 80 Mbit/s 4K profile reopened as 3840×2160 at 59.94 fps, with 1191 frames, no missing frames, no decode errors and AAC audio of the same length. It took about 148 MB, or about 59 Mbit/s for that scene.

**Capture rate and game frame rate:** the 60 fps above is the rate of the captured stream, not of the game. In these scenes the game drew about 30 new pictures per second, so each picture was captured twice. This was the same at 1080p, 1440p and 4K. The capture itself did run at 60 fps: in three 4K recordings, a PS5 notice fading out changed on every frame while the game changed on every second frame. A game mode running at 60 fps has not been measured.

**Presentation on the PC:** frames now wait in a short queue and are painted one per monitor refresh, following their capture timestamps. If a frame is late the app waits for it, which leaves more margin for the next ones, and when the stream is steady again it gives that delay back. If the queue falls too far behind, frames are skipped instead of the delay growing.

With a 30 fps game, the ideal is for each picture to stay up for exactly 2 refreshes. On a 60 Hz monitor, in one 25-second run per resolution, this went from 70–76% to 97% of pictures at 4K and from 83–96% to 99% at 1080p. 1440p reached 99%, with no earlier figure to compare.

Checking the packaged app's window at every refresh, in runs of about 30 seconds:

| Profile | Runs | Screen updates per second | Refreshes with no update | Longest hold | Decoded frames not painted |
|---|---:|---:|---:|---:|---:|
| 4K, before | 1 | 50.9 | 15.1% | 67 ms | 9 of 1860 |
| 4K, now | 4 | 58.2–59.2 | 1.3–2.9% | 50–100 ms | 22–43 of about 1800 |
| 1080p, now | 2 | 59.7–59.8 | 0.2–0.4% | 50 ms | 3–5 of about 1800 |

The earlier 4K run used a larger window (1920×1009 against 1360×880) and a calmer scene (about 39 Mbit/s against 66–71). These are updates of the 60 fps stream, not new pictures from the game, which was drawing about 30 per second. The old path painted slightly more frames, but at uneven times.

A fifth 4K run was much worse: 52.8 updates per second, 11.9% of refreshes with no update, a 400 ms hold and 240 of 1799 frames not painted, ending at about 39 Mbit/s. It was the first launch after building the app. The cause was not found. It did not happen in the next four 4K runs, but it may happen again.

This is not free. From receiving a frame to painting it now takes about 40–43 ms at 1080p, 53 ms at 1440p and 49–62 ms at 4K, against about 5 ms at 4K before. A frame is stamped with the arrival of the packet that released it from the decoder, so these figures leave out the frame-thread delay (1 frame at 1440p, 2 at 4K), before and after. The end-to-end delay from the console to the screen has not been measured. Recordings and screenshots do not pass through this queue, so a screenshot can be a few frames newer than the picture on screen.

**Audio queue:** audio and video share one connection, so audio arrives late behind large frames: up to 130–180 ms at 4K and 60–70 Mbit/s, against under 20 ms on a calm 8 Mbit/s 1080p scene. The 1080p limits (trim above 60 ms, down to 40 ms) cut audio about every 3 seconds at 4K. Above 1080p the limits are now 160 and 120 ms. Over two 25-second runs each at 4K and 60–65 Mbit/s, trims fell from 9 to 1–2 per run, and short audio gaps fell to the level seen at 1080p. This is not free: the queue settled at about 105–140 ms at 4K and 72 ms at 1440p, against 40 ms before. Audio therefore trails the picture by more than at 1080p, partly offset by the frame-thread delay and the presentation queue above. The end-to-end A/V offset has not been measured.

**A longer session:** about 3.5 minutes on the 80 Mbit/s 4K profile received 3840×2160 at about 37 Mbit/s for that content and painted 12,219 of 12,582 decoded frames, with no connection error. Receiving a frame to painting it took about 55 ms on average over the last 1800 frames.

These runs do not establish long-session stability, and the PC's decoding margin depends on its CPU.

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

Automated tests cover valid H.264/AAC MP4 output, waiting for a later keyframe, cancellation without media, bounded-queue failure, native-sized PNG output, reconnect and manual cancellation.

Live tests on the owner's PS5 13.60 confirmed the acknowledged 4/8/12 Mbit/s targets, decoded video/audio and PNG captures. MP4 recordings were reopened and decoded for both video and audio. A forced socket interruption recovered into a second capture session, and the interrupted recording was finalized as a playable MP4. The new ELF was also tested with the previous 1.1.1 PC receiver.

The tests verify functionality and data flow; they do not establish every title/device combination, long-session stability, perfect A/V synchronization or total end-to-end latency. The presentation cap and final packaged-app UI are checked separately from headless capture tests.
