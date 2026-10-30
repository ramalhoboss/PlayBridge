# PlayBridge gaming desktop

## Navigation

- **Live** maximizes the video area by hiding the performance dock.
- **Media** opens the local capture library. Photos and MP4 recordings can be filtered, paged, refreshed and opened in the system's default app. Thumbnails are read in a background worker, and a recording's thumbnail is a still from a quarter of the way in. The library lists up to 120 newest captures from the app's Screenshots and Recordings folders. Empty files, symbolic links and unfinished .partial.mp4 recordings are excluded.
- **Stats** toggles the session dock with decoded dimensions, presented FPS, PC receive-to-presentation timing, received media Mbps history, audio queue, session time, received bytes and recording state. Missing measurements remain blank. PC timings are not end-to-end console latency.
- **Setup** includes network discovery, manual IPv4, quality selection and named favourite consoles. Each favourite stores its IP and quality profile. Saving a favourite does not change the active stream; select it and save connection settings to apply it.

The dock collapses below 1180 logical pixels, and fullscreen hides the navigation and dock. The mouse cursor hides after 2.5 seconds without movement in fullscreen and returns on movement.

## Shortcuts

| Shortcut | Action |
|---|---|
| F8 | Native-frame PNG screenshot |
| F9 | Start or stop packet-copy MP4 recording |
| F11 / double-click video | Fullscreen |
| Escape | Leave fullscreen |
| Ctrl+L | Capture library |
| Ctrl+I | Performance dock |
| Ctrl+, | Settings |

## Artwork and motion

The PlayBridge ambient scene uses an original procedural gradient, waves and orbit animation, plus its own brand emblem. Ambient rendering stops while video is displayed. Motion is optional and its preference persists.

The build and this repository include only original assets. Optional local artwork is described in the [visual theme](VISUAL-THEME.md). No console code or fonts were copied.

The desktop adds no controller, microphone, HDR or wake functionality. Capture capabilities are those of the payload and the console's video output; see [capture options](CAPTURE-OPTIONS.md).
