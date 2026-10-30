"""Local desktop features. No console APIs or extracted implementation code."""
from dataclasses import dataclass
from pathlib import Path
import heapq, ipaddress

@dataclass(frozen=True)
class CaptureItem:
    path: Path
    kind: str
    size: int
    modified: float

def capture_items(folder, kind='All', limit=120):
    root = Path(folder).resolve()
    def records():
        for name, suffix, label in (('Screenshots', '.png', 'Photos'), ('Recordings', '.mp4', 'Videos')):
            if kind not in ('All', label):
                continue
            directory = root / name
            if directory.is_symlink():
                continue
            try:
                for path in directory.iterdir():
                    if path.suffix.lower() != suffix or path.name.lower().endswith('.partial.mp4') or path.is_symlink():
                        continue
                    try:
                        if not path.is_file() or path.resolve().parent != directory.resolve():
                            continue
                        stat = path.stat()
                        if stat.st_size:
                            yield CaptureItem(path, label, stat.st_size, stat.st_mtime)
                    except OSError:
                        continue
            except (FileNotFoundError, NotADirectoryError):
                continue
    return heapq.nlargest(max(0, min(int(limit), 240)), records(), key=lambda item: (item.modified, item.path.name))

def saved_consoles(settings, profiles):
    result = []
    entries = settings.get('consoles', [])
    if not isinstance(entries, list):
        return result
    seen = set()
    for item in entries:
        if not isinstance(item, dict):
            continue
        try:
            host = str(ipaddress.IPv4Address(item.get('host', '')))
        except (ValueError, TypeError, ipaddress.AddressValueError):
            continue
        if host in seen:
            continue
        seen.add(host)
        profile = item.get('profile', 'balanced')
        result.append({'name': str(item.get('name', 'PS5')).strip()[:40] or 'PS5', 'host': host,
                       'profile': profile if profile in profiles else 'balanced'})
        if len(result) == 12:
            break
    return result

def remember_console(settings, name, host, profile, profiles):
    host = str(ipaddress.IPv4Address(host.strip()))
    if profile not in profiles:
        raise ValueError('Choose a supported quality profile.')
    item = {'name': name.strip()[:40] or 'My PS5', 'host': host, 'profile': profile}
    return [item] + [c for c in saved_consoles(settings, profiles) if c['host'] != host][:11]

def format_bytes(value):
    value = max(0, value)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if value < 1024 or unit == 'TB':
            return f'{value:.1f} {unit}' if unit != 'B' else f'{value:.0f} B'
        value /= 1024

def clock_text(seconds):
    seconds = max(0, int(seconds))
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    return f'{h:02}:{m:02}:{s:02}'

def video_thumbnail(path, size=(300, 170)):
    """A still from a quarter of the way into a recording, or None if it cannot be read."""
    import av
    try:
        with av.open(str(path)) as container:
            stream = container.streams.video[0]
            if container.duration:
                container.seek(container.duration//4)
            for frame in container.decode(stream):
                image = frame.to_image()
                image.thumbnail(size)
                return image
    except (av.error.FFmpegError, OSError, ValueError, IndexError):
        pass
    return None

class CursorHider:
    """Hides the pointer after a pause while active. It changes the window's cursor, and only when it differs: configuring the video canvas makes Tk repaint it over the picture."""
    def __init__(self, window, delay=2500):
        self.window = window
        self.delay = delay
        self.active = False
        self.shape = ''
        self.timer = None
    def moved(self, _=None):
        self.apply('')
        if self.timer is not None:
            self.window.after_cancel(self.timer)
            self.timer = None
        if self.active:
            self.timer = self.window.after(self.delay, self.hide)
    def hide(self):
        self.timer = None
        if self.active:
            self.apply('none')
    def apply(self, shape):
        if shape != self.shape:
            self.shape = shape
            self.window.configure(cursor=shape)
