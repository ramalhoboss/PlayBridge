# Changelog

## v1.9.0 — 2026-11-17
- Pair a phone with its camera. Settings → Phone shows a QR code beside the six-digit code. A phone that points its camera at it opens the page and pairs at once. The QR code holds the same code, so it works once and only while the code is shown.
- More, on the phone page. A paired phone's More button has three tabs. Games lists your games and starts one on the PS5, and asks first when another game is open; it needs Play on your PS5. Captures shows the screenshots and recordings on this PC, to watch on the phone and save to it, each through an address that works only while it is in use. Log shows what PlayBridge noted in this session. On a TV or a Steam Deck at /tv, More works with the arrows, OK and Back, or a controller.
- Play time, in Settings → Console. A daily limit on playing through PlayBridge, kept with a PIN of four to eight digits, saved only as a salted hash. PlayBridge says when ten minutes and one minute are left. At the limit it ends the stream and does not connect again that day, unless the PIN adds time. Five wrong PINs wait a minute. It limits PlayBridge only; the PS5's own Family settings limit the console.
- Go back, in Settings → Updates. An update now keeps the version it replaces, and Go back puts that version back and opens it, with Update automatically turned off so it stays. Updating from 1.8.0 keeps 1.8.0.
- Check setup, in Settings → Console, and once on the first start. It looks at how this PC reaches the network (cable or Wi-Fi, and the link speed), whether the PS5 answers and its ELF loader is open, and the graphics card and the sound output, and says what to change.
- Search in Settings. Type in the box above the sections; a result opens its card and lights it up.
- Settings → Appearance:
  - Text and contrast: larger text on every page, in two sizes, and High contrast, with brighter words on darker panels. Until you choose, High contrast and Animations follow Windows' own settings.
  - Colour: an accent for buttons, rings and highlights (Gold, Sky, Teal, Coral, Violet or Silver), and a darker backdrop behind the pages and the Games page's art. The Games page's tiles take the accent the next time PlayBridge opens.
- Settings → Updates → Your settings saves PlayBridge's settings in one file and restores them, on this PC or another. Sign-ins, stream keys and keys stay out of the file, and restoring keeps this PC's own.
- After a session that did not close normally, as after a crash or a power cut, PlayBridge opens on the page it was on and offers Report a problem.
- Parts of Settings not yet tried on every setup are marked Beta. Away from home says that it is for this same PC when it leaves home.
- The README has a Privacy and security section: what leaves the PC, where to, and when.
- Fixed: when Windows was briefly too busy to send, a controller's last message could be lost and the controller stayed on the PS5 after you stopped playing. It is now sent again.
- The EXE's build checks that every package it takes in has its notice in third-party-licenses. The notices for packaging and typing_extensions were added.
- The payload is the same as in v1.8.0.

## v1.8.0 — 2026-11-16
- Play away from home. Settings → Console → Away from home, switched on at home with the PS5 on and nothing streaming, finds a way in from outside. It asks the router over UPnP to forward five ports to the PS5 for as long as the PS5 waits, uses Tailscale when a computer at home shares the home network through it, or says which ports to forward by hand. It then sends a payload that waits for this PC after each stream, for 6 to 72 hours (12 by default). The ELF loader's port is never forwarded. Away, Connect works as usual. The stream starts at the quality chosen for away (Balanced, 1080p60 at 8 Mbps, by default), steps down when the line loses too much, and goes back up after a few minutes without loss. The picture can travel over UDP with error correction. Switching it off at home ends the waiting payload and removes the router's forwards. Tried on a PS5 over the home network, not yet from outside it.
- An encrypted link to the PS5. Each PC makes its own key, kept encrypted for its Windows user, and puts it into the payload it sends. The picture and sound, the control link and the controllers then travel sealed with AES-256-GCM, and the payload answers only the PC whose key it holds. An ELF loaded by hand has no key and works as before. On a PS5, a keyed 4K60 stream at 80 Mbps ran for nine minutes without an error.
- Picture Studio, in Settings → Picture. When the window is larger than the picture, the graphics card's own super resolution enlarges it: NVIDIA RTX Video Super Resolution, or Intel's video super resolution. RTX Video HDR turns the PS5's SDR picture into HDR on an NVIDIA RTX card with Windows HDR on. FSR 1 and Sharpen moved here. Deband smooths the steps that compression leaves in skies, fog and shadows, and Compare before and after splits the picture in two. While a game runs, these settings can be kept as its own, and they come back each time it runs. If the card's video engine fails, it stops for the session and the picture carries on through the usual shaders. Not yet tried on NVIDIA or Intel cards.
- Go live sends to several services at once, each through a queue of its own, so one that is slow or refuses the stream never holds up the others. Kick joins the services, with its server address and stream key.
- Highlights. While a recording runs, PlayBridge notes each trophy and the busiest moments on the controller. The clip editor in Media shows them along with the loudest moments, makes a highlights reel from them, and makes vertical 9:16 clips, either cropped to the middle or with the whole picture over a blurred copy.
- Stats. Performance Lab shows each game's frame rate in each mode (30, 40, 60, 120 or unlocked), with its 1% and 0.1% lows and a curve, and makes a card to save or copy. PlayBridge Wrapped shows your year, with your longest run of days and the day you play most.
- PSN. Play this too, on a friend's row, starts the game they play when it is on your PS5, or searches the PlayStation Store for it. Trophies → Next up lists the trophies most players have and you do not, from the games you started and have not finished. It warns when a trophy's own description says it can be missed, and Missables searches for a guide.
- Settings → Updates gains three things:
  - Beta versions.
  - Report a problem opens a new GitHub issue with this PC's details filled in: the version, Windows, the graphics card, the stream settings and frame timings, with no addresses, names or files. PlayBridge sends nothing itself.
  - A performance check compares how long this PC takes for each frame with the version before, with the same settings.
- TVs and the Steam Deck. The phone page's address followed by /tv, opened in their browser, shows the game full screen and plays with a controller, a TV remote or a keyboard. It pairs like a phone.
- Rest mode. A PS5 found resting is waited for instead of refused. Once it wakes, if its ELF loader is gone, PlayBridge says the exploit must be loaded again. PlayBridge does not wake the PS5 itself.
- Fixed: choosing the DualSense microphone through the PS5 froze the payload until the console was restarted, because the PS5 stops a payload that opens the microphone. The payload no longer opens it. PlayBridge now says to connect the DualSense to the PC with a USB cable and choose its microphone instead.
- Fixed: in full screen, thin see-through strips at the left, right and bottom edges showed the window behind.
- Not yet tried on a console: away play from outside a home network, and the controller payload's encrypted link. Also not yet tried: Picture Studio on NVIDIA and Intel cards, and Go live to several real services at once or to Kick.
- The payload changed. Manual users should load the v1.8.0 ELF.

## v1.7.1 — 2026-11-15
- Update question. When a new version from GitHub is downloaded and checked, PlayBridge asks once: Restart and update now, or Later, and with Later it goes in when PlayBridge closes, as before. It never asks over the game's picture: on the live view, in fullscreen or in the small window it waits until you leave them, and it waits for an open question or menu to close. The classic window asks too. A copy run from source asks once for each version and offers the release page.
- New README screenshots of Settings, Live, Media and Streaming in the 1.7.0 look.
- The payload is the same as in v1.7.0.

## v1.7.0 — 2026-11-15
- PlayStation Network. Settings → Connections → PlayStation Network signs in with the code Sony's own page shows after you sign in on playstation.com; the sign-in is kept encrypted for your Windows user and Sign out forgets it. The new Friends page shows your friends, who is online, what they play and on which console, with All, Online and Favourites. Add friend finds a player by online ID; friend requests can be sent, accepted, declined and taken back, and a friend removed. The top bar shows your avatar, your status and a PSN menu.
- PSN messages. Direct and group conversations, read and answered on the PC. Text and pictures go out (picked, pasted or dropped; turned upright, without location data, at up to 768 pixels on the long side, as the PlayStation App sends them), and the pictures, GIFs, stickers, videos and voice messages friends send are shown or played. Emoji reactions, copy, save a picture, delete your own message for everyone in the 10 minutes after sending it (PSN's limit), remove any message from this PC only, favourite and mute, and groups: create, rename, add people, take people out and leave. Friends see that you are typing and the conversation is marked as read on PSN. Message ids go into Sony's addresses encoded, as the App sends them.
- Alerts, each optional: a friend comes online, starts a game you watch, sends a message or a friend request. A Windows notification shows, and the taskbar button flashes while PlayBridge is not in front.
- Trophies. The trophies of the games on the PS5, read from the console's own files, and every game with trophies on PSN, PS4 games included. A friend's trophies beside yours, a guide for any trophy in your browser, hidden games, and a clip kept when a trophy unlocks.
- Stats: play time by session, week, game and year while PlayBridge was connected, beside the console's own total, with the trophies earned in each session.
- Play on your PS5. Up to four controllers connected to the PC, the PC keyboard and the mouse as the right stick play on the console, through PlayBridge-Controller.elf, a companion payload on UDP 9078 that PlayBridge sends by itself. A controller exists on the PS5 only while it is used, and the stream never waits for it. Controller profiles swap buttons, shoulders or sticks, invert a stick, add one-hand play, turbo and your own buttons, for every game or for one.
- Your phone. A phone on the same network pairs once with a six-digit code and gets the game's picture and sound in its browser, and a controller. Nothing is installed on the phone.
- Smooth motion. On a screen faster than the stream, such as 120 or 144 Hz, the graphics card makes the pictures between two frames from the motion between them. It stops for the session on a PC that cannot keep up. A stream whose frames come twice or three times (a game at 30 or 20 fps) is recognised, and the screen switches to 120 Hz where that suits the stream.
- On screen: a PS5 performance overlay (the game's frame rate, CPU and SoC temperatures and the power drawn), a speedrun timer that starts with a game and splits at each trophy (Ctrl+T by hand), a trophy as it unlocks, and Twitch chat, read anonymously, over the game and in the live stream.
- Captures: a clip editor in Media trims a recording to an MP4, a small MP4 or a GIF, without changing the recording. The DualSense's own microphone, heard through the PS5 on port 9079, can go into recordings, instant replays and Go live.
- Go live adds TikTok. Its server address and stream key are pasted for each live stream, as TikTok gives a new pair each time.
- Connections: Discord Rich Presence through the Discord app on this PC, and a Discord channel (a webhook) for screenshots, trophy clips and recordings. A control address for Stream Deck, Touch Portal and scripts, and an overlay for OBS, on 127.0.0.1:9095, each address starting with a secret made on this PC.
- PS5 tools. A payload shelf reads ELF files from the GitHub releases of a repository you choose. Files browses the PS5 through an FTP server a homebrew payload already runs (ports 2121, 1337 or 21), with drag-in and a preview. A game's saves are copied to the PC when it closes, or all at once; PlayBridge only reads them. The PS5's fan target can be lowered for every game or one, never above the console's own, and the console's own comes back on disconnect.
- The Games page is the classic library drawing again, with the game's art moving gently behind it, in Row, Grid or List view. The window has rounded corners and a shadow, without a Windows title bar.
- Power. Reboot and Turn off now ask the console the way apps do and report its real answer; Reboot was confirmed on a PS5. A confirmation opened from a menu row no longer closes by itself.
- Not yet tried on a console: the fan target, copying saves, the DualSense microphone and Files.
- The payload changed. Manual users should load the v1.7.0 ELF.

## v1.6.0 — 2026-11-12
- A new look, and the one PlayBridge now opens with: Qt Quick pages drawn on the graphics card, with frosted glass panels, page transitions and the focused game's art filling the window. The game tiles sit in a row at the top. The focused one is larger, has a soft gold glow behind it and turns in 3D towards the mouse or the right stick; the others stay flat. Covers are read at twice the size they are drawn and stay sharp while they turn. Settings → Appearance → Glass look turns it off and brings back the classic window at the next start, and PlayBridge opens the classic window by itself when Qt cannot start. While a game is on screen nothing in the window animates, so the window does not redraw over the picture.
- Automatic updates. PlayBridge looks for a new release on GitHub a few seconds after it opens and every six hours, downloads its PlayBridge.exe in the background at about 1.5 MB/s, so a stream keeps its speed, and keeps it only when its SHA-256 matches the release's SHA256SUMS.txt and it is a Windows program. The new version goes in when PlayBridge closes, or at once with Settings → Updates → Restart and update. Check now looks straight away, and Update automatically, on by default, turns the checks off. Run from source, PlayBridge only says that a new version is out. When a check or a download fails, Settings says why in a few words and %LOCALAPPDATA%/PlayBridge/update/update-error.log has the whole error.
- The game library is read again every time PlayBridge connects. An icon that changed on the console is fetched at once, and every other icon, picture and piece of music is checked again while you browse with no game open, so tiles no longer show pictures the console has replaced.
- Settings → Captures → Make recordings smaller, off by default. After a recording or replay is saved, and only while no stream is playing, its video is made again on the graphics card as HEVC or AV1, the sound is kept as it is, and the original goes to the Recycle Bin once the new file has been checked. In tests the files came out at about two thirds of the size.
- Go live → Smaller stream (HEVC or AV1), for YouTube and other RTMP servers, off by default. The video is made again on the graphics card, so 4K fits a slower upload. Twitch keeps H.264.
- The stream key has a Show and Hide button and is checked as you type. A pasted rtmp address is pointed out.
- Settings apply as soon as they change. Only the console's IP address waits for Save or Enter; Find console and the list of consoles found fill the field.
- With the keyboard or a controller, a gold ring shows where you are on Settings and Media, and left on Settings reaches the list of sections.
- Settings → Console → Notices on the PS5, off by default: the console shows a notice when the stream starts and when it ends.
- Variable refresh rate now checks the screen. PlayBridge reads the screen's EDID, and only a screen that shows FreeSync, HDMI VRR or Adaptive-Sync gets frames the moment they are due. On a screen with a fixed rate the switch is hidden and every frame waits for the next refresh, even if the switch was left on: presenting at once there tore the picture whenever it moved. The stats say "fixed screen" when this happens.
- The payload reads sound into a 64 KB buffer. A sound packet larger than the old buffer used to stop the sound; one too large for an AAC frame is now counted and skipped.
- The source has the first parts of a separate controller payload. It is not in this release and stays off.
- The payload changed. Manual users should load the v1.6.0 ELF.

## v1.5.2 — 2026-11-06
- Variable refresh rate. A new switch in Settings → Picture, shown only where the graphics driver lets a window present at once. With it on, the GPU video output presents each frame at its own time on the stream's clock instead of on the next refresh, so a screen with G-Sync, FreeSync or Adaptive-Sync shows 60 fps evenly at 144 Hz. Two frames never go to the screen closer together than one refresh, so frames that the network held up and that arrive together do not tear. While it is on, PlayBridge leaves the screen's rate alone. It applies the next time PlayBridge opens and works best in full screen. It is off by default, because a screen without variable refresh can show tearing.
- Microphone. Settings → Captures → Microphone adds your voice to recordings, instant replays and Go live. While it is on, the console's AAC sound is decoded, your voice is added at its own volume, up to twice as loud, and the mix is encoded to AAC again. A menu chooses the microphone, F7 turns it on and off, and the status line shows MIC. A microphone whose clock runs a little fast or slow against the console's is kept between 40 and 120 ms behind. You do not hear yourself in PlayBridge. With the microphone off, the console's sound is copied untouched, as before.
- The stats and exported diagnostics say whether variable refresh is on, and how much voice was mixed, missing or dropped.
- The payload is unchanged from v1.5.0.

## v1.5.1 — 2026-11-06
- Sound on every PC. v1.5.0 did not open on a PC whose sound output mixes at another rate than the PS5's 48 kHz, with "Invalid sample rate". WASAPI now converts the rate itself. When the chosen output still refuses, PlayBridge tries the Windows default output through WASAPI, DirectSound and MME, and when none opens it streams the picture without sound and says why in the status line. Each refusal is written to audio-check.txt next to the preferences. An output that will not open is no longer saved as the choice.
- Laptops with two graphics cards. Windows' default card on such a laptop is the processor's graphics, so the NVIDIA or AMD card stayed idle. PlayBridge now decodes and draws on the card with the most memory of its own, and Settings → Picture → Graphics card, shown only where there is a choice, names another one. The change applies the next time PlayBridge opens.
- When the card that draws is not the one that drives the screen, as on most gaming laptops, every frame is copied across first. The GPU video output then keeps two frames in flight instead of one. On any PC, five frames in five seconds that the screen was not ready for add one more, up to three, for the rest of the session.
- Screens at 144 or 165 Hz. 60 fps judders there, because some frames stay up longer than others. While a game fills the window, PlayBridge switches the screen to the fastest rate that fits the stream, 120 or 60 Hz, and back when the stream ends or the window is minimized. Settings → Picture → Match the screen to the stream turns it off. The refresh clock learns the new rate after a switch.
- The display and the PC stay on while a session runs, unless the window is minimized. Playing with a controller never touches the PC, and Windows used to turn the screen off after its idle time.
- On battery, when frames keep falling short of the stream for a few seconds, PlayBridge says once a session that the battery may be holding the picture back.
- More in av3-stats.json, with the counts also in exported diagnostics, to explain a stutter on a PC nobody here can see: each frame that stayed up a refresh too long and why (a slow present, a frame that had not arrived, a busy paint thread), the time between frames on screen, where video stopped arriving for more than 50 ms, whether the PS5 is reached over Wi-Fi or a cable, the screen's refresh rate and any switch, frames in flight, and how long decoding waited for a keyframe after it fell behind.
- The payload is unchanged from v1.5.0.

## v1.5.0 — 2026-11-05
- Closing a game from the PS5 menu no longer ends the stream. The console stops every capture while its close screen is up, twice per close, and answered a reopen at once with busy (0x81950008), so the payload gave up after one try. It now asks for the capture's state and tries again every 16 ms for up to two seconds, as Remote Play does on 13.60, and the count of reopens starts again after 300 frames. On the owner's PS5 the session held through every game close tried, at 4K and at 1080p, with a pause of about a second.
- Faster first connect. The PS5 does not answer a connection to a port that is not open yet, and a half-open connection could reach the payload, close without sending options, and end the payload's wait; PlayBridge then kept trying for about 36 seconds. The payload now drops such a connection and listens for the rest of its minute, and PlayBridge tries for 10 seconds, half a second at a time. On the owner's PS5 it connected in 1.1 seconds.
- Media → From your PS5: the console's own screenshots and clips, listed through a new control command limited to /user/av_contents, and copied to the capture folder with Copy new or Copy selected. Copies are named after the game. Media also shows JPEG, WebP and WebM files.
- Go live (Ctrl+B, Settings → Streaming): the console's H.264 and AAC copied as they arrive to Twitch, YouTube over RTMPS, any RTMP server, or OBS on this PC as MPEG-TS on UDP 127.0.0.1:9100, without encoding again. The stream key is sealed with Windows DPAPI for the current user and never appears in messages, logs or diagnostics. Not yet run on a real Twitch or YouTube broadcast.
- Settings → Console → Send a payload sends any ELF up to 64 MB to the loader on port 9021 after a question, and keeps the five most recent files.
- Small window (Ctrl+M): only the picture, in a small window above every other window. Ctrl+M again, or a double-click, returns.
- New Settings and Media pages: frosted panels over PlayBridge's own blue and violet picture, in one to four columns, with larger text. Settings, Media and the Live waiting screen share that picture.
- Settings → Picture names the graphics card that decodes the stream and asks it which stream sizes it can decode. The card's model is included in exported diagnostics.
- Games page: every tile in view is drawn before any large game picture. A tile takes about 5–7 ms and a picture 100 ms at 1080p to about 250 ms at 4K, and tiles further along used to wait behind three pictures and stay blank while the row moved.
- GPU video output: the swap chain waits until the video window is shown with a real size. Made on the hidden window of one pixel, it showed the picture black, or enlarged from the middle, for the whole session in about one start in four.
- When the window stops answering, the session timeline names where its thread was. Each session keeps copies of the payload's logs in the ps5-logs folder next to the preferences.
- The payload changed. Manual users should load the v1.5.0 ELF.

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
