# PlayBridge look

The whole app shares the Games page's look: black, frosted cards with a hairline rim, white type, and gold only as a small accent for focus, switches and the online mark. The colours are defined once in `app/luxury_theme.py`, and the pictures of the Games page are drawn in `app/scene.py` with PIL and NumPy, so the tests can draw them without a window.

- **Games page:** the selected game's art fills the window. A game without art has its cover far out of focus behind, and large and sharp on the right. The tiles are drawn as small 3D cards, and the four cards under the title are frosted glass: what is behind them blurred and darkened, with a hairline rim. A new picture is drawn only when the selection, the page size or the data changes, and nothing is drawn while the page is still.
- **Other pages:** Settings, Media and the Live waiting screen float frosted panels over one picture of PlayBridge's own: near black, with blue light from the top right and violet low on the right (`scene.no_art`). It stays the same whatever game was played last. Settings flows its panels into one to four columns with the window's width. Buttons are drawn as one picture each, and a button that is told to show what it already shows draws nothing.
- **Type:** Windows' DIN-like face for the large titles where it is available, otherwise Segoe UI.
- **Window:** on Windows 11 the title bar is black and the window border a thin grey; older Windows keeps its own.
- **Video:** the video sits on pure black, and in fullscreen it covers everything else. Animation stops as soon as video is presented, nothing is redrawn for video frames, and no decorative filter is applied to the video. The optional sharpening on the GPU output is a picture setting, not decoration.
- **Motion:** the moving tiles and the waiting screen can be turned off in **Settings → Appearance**, and that preference persists.

## Optional local artwork and music

PlayBridge ships only original artwork and sound. The waiting screen, tiles, cards, icons, background music and navigation sounds are made by the app. Game covers and music come from your own console while you use it.

The app can also load your own files from a folder named by the PLAYBRIDGE_LOCAL_SKIN environment variable. The recognized files are heart.png and trophy.png, which are tinted when loaded, and sounds/ambient.flac, sounds/ambient.wav or sounds/ambient.ogg, which replaces the app's background music. The files themselves are not changed. Missing or unreadable files use the app's own artwork and music. This repository and its releases include no such files.
