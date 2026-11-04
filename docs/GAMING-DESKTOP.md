# PlayBridge desktop

## Pages

One window holds every page. The top bar has **Games**, **Live** and **Media** on the left, and the console's state, the time, search, Settings, fullscreen and power on the right.

- **Games** lists the games installed on the PS5, read through the payload's control port during a session. Each game shows its cover, title, when it was last played and for how long, and its size. The selected game's art fills the page, and four cards show your time, its size on the PS5, the stream and the console's temperature. **Play** launches the game and switches to **Live** when its picture arrives; **Resume** returns to a game that is already running. The **⋯** button closes the running game, refreshes the library or opens the Live view. Covers and music are saved on the PC, so the page opens quickly next time.
- **Live** shows the stream, with capture, replay, session and audio controls below it.
- **Media** lists local photos and MP4 recordings. They can be filtered, paged, refreshed and opened in the system's default app. Thumbnails are read in a background worker, and a recording's thumbnail is a still from a quarter of the way in. It lists up to 120 newest captures from the app's Screenshots and Recordings folders. Empty files, symbolic links and unfinished .partial.mp4 recordings are excluded.
- **Settings** has five sections: **Console** (address, Find console, favourites, connection and power), **Picture** (quality profile, performance stats, GPU video output, sharpening and FSR 1 upscaling), **Captures** (instant replay, capture folder and diagnostics export), **Sound** (the library's music, navigation sounds and their volume) and **Appearance** (Gaming Mode and animations).

The **session panel** (**Ctrl+I**) sits beside any page. It shows the frame rate, the source size, the PC's time from receiving a frame to presenting it, the game on the console with its close and power buttons, the received bitrate for the last 60 seconds, the audio buffer and the recording state. Missing measurements remain blank. PC timings are not end-to-end console latency.

Fullscreen hides the top bar. The mouse cursor hides after 2.5 seconds without movement in fullscreen and returns on movement.

## Gaming Mode

Gaming Mode opens the Games page fullscreen. While it is on, the PC never shows the console's own menu: when no game is open, or when the console's menu comes in front of a game, the PC shows the games instead, and the game's picture returns when it is back in front. The console is asked for the app in front about four times a second. The TV connected to the PS5 is not affected.

## Sounds

On the Games page, the app plays quiet background music of its own, or the selected game's own music when it has one, and short navigation sounds made by the app. They use their own audio output, opened only while the games are on screen, so a game's sound is never mixed with them. **Settings → Sound** turns each off and sets their volume.

## Shortcuts

| Shortcut | Action |
|---|---|
| F6 | Switch between the game's picture and the games |
| F8 | Native-frame PNG screenshot |
| F9 | Start or stop packet-copy MP4 recording |
| F10 | Save the instant replay |
| F11 / double-click video | Fullscreen |
| Escape | Leave fullscreen |
| Ctrl+G | Gaming Mode on or off |
| Ctrl+L | Media |
| Ctrl+I | Session panel |
| Ctrl+, | Settings |
| ← → / Page Up, Page Down | Move between games, one or five at a time |
| ↑ ↓ | Change the row of games |
| Enter | Play or resume the selected game |
| Typing | Search the games |

A controller connected to the PC can also move around the Games page. Its input is not sent to the console.

## Artwork and motion

The app draws its own waiting screen, tiles, cards, icons and sounds. Game covers and music come from your own console while you use the app. Motion is optional and its preference persists, and nothing is animated while video is showing.

The build and this repository include only original assets. Optional local artwork is described in the [visual theme](VISUAL-THEME.md). No console code or fonts were copied.

The desktop adds no microphone, HDR or wake functionality, and controller input is not forwarded to the console. Capture capabilities are those of the payload and the console's video output; see [capture options](CAPTURE-OPTIONS.md).
