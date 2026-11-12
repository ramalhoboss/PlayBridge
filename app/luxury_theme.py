"""PlayBridge's look, the same as the library's: black, frosted cards with a hairline rim, white type and gold only as a small accent. With optional local artwork.
All Tk operations run on the UI thread. Animation stops when video is visible.
"""
import ctypes, functools, math, os, sys
import tkinter as tk
from pathlib import Path
import customtkinter as ctk
from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFont, ImageTk

BG = '#000000'
STAGE = '#000000'
PANEL = '#0A0A0A'
CARD = '#141414'
FIELD = '#0C0C0C'
RAISED = '#232323'
LINE = '#2A2A2A'
# White at a quarter on the dark card, as the library's glass has it.
RIM = '#4A4A4A'
GOLD = '#D4AF37'
GOLD_HOVER = '#F3D778'
GOLD_SOFT = '#EBD48E'
INK = '#101010'
TEXT = '#FFFFFF'
MUTED = '#BDBDBD'
DISABLED = '#6F6F6F'

def apply_theme():
    """Dark defaults for the widgets the app uses, so none that names no colour falls back to the stock blue."""
    ctk.set_appearance_mode('dark')
    ctk.set_default_color_theme('blue')
    colours = {
        'CTk': {'fg_color': BG},
        'CTkToplevel': {'fg_color': BG},
        'CTkFrame': {'fg_color': CARD, 'top_fg_color': RAISED},
        'CTkButton': {'fg_color': CARD, 'hover_color': RAISED, 'border_width': 0, 'text_color': TEXT, 'text_color_disabled': DISABLED},
        'CTkLabel': {'text_color': TEXT},
        'CTkEntry': {'fg_color': FIELD, 'border_width': 0, 'text_color': TEXT, 'placeholder_text_color': MUTED},
        'CTkSwitch': {'fg_color': RAISED, 'progress_color': GOLD, 'button_color': TEXT, 'button_hover_color': GOLD_SOFT, 'text_color': TEXT, 'text_color_disabled': DISABLED},
        'CTkSlider': {'fg_color': RAISED, 'progress_color': GOLD, 'button_color': TEXT, 'button_hover_color': GOLD_HOVER},
        'CTkOptionMenu': {'fg_color': FIELD, 'button_color': FIELD, 'button_hover_color': RAISED, 'text_color': TEXT, 'text_color_disabled': DISABLED},
        'CTkScrollbar': {'button_color': RAISED, 'button_hover_color': RIM},
        'CTkScrollableFrame': {'label_fg_color': BG},
        'DropdownMenu': {'fg_color': CARD, 'hover_color': RAISED, 'text_color': TEXT},
    }
    for widget, values in colours.items():
        ctk.ThemeManager.theme[widget].update(values)

def tint(image, colour):
    """The image in one colour, keeping its shape and shading."""
    image = image.convert('RGBA')
    alpha = image.getchannel('A')
    shade = image.convert('L')
    peak = Image.composite(shade, Image.new('L', image.size), alpha).getextrema()[1] or 255
    return Image.merge('RGBA', [shade.point([min(255, value*part//peak) for value in range(256)]) for part in ImageColor.getrgb(colour)] + [alpha])

def rounded_mask(size, inset, radius):
    """A rounded rectangle as a mask, at any fraction of a pixel. Curves are drawn at eight times the size, because that is where a thin line looks rough; straight edges need no such work."""
    width, height = size
    radius = max(radius, 0)
    reach = math.ceil(inset+radius)+1
    if min(width, height) <= 2*reach:
        mask = Image.new('L', (width*8, height*8))
        ImageDraw.Draw(mask).rounded_rectangle((inset*8, inset*8, (width-inset)*8-1, (height-inset)*8-1), radius*8, fill=255)
        return mask.reduce(8)
    tile = Image.new('L', (reach*8, reach*8))
    draw = ImageDraw.Draw(tile)
    start, middle = inset*8, (inset+radius)*8
    draw.ellipse((start, start, 2*middle-start, 2*middle-start), fill=255)
    draw.rectangle((middle, start, reach*8, reach*8), fill=255)
    draw.rectangle((start, middle, reach*8, reach*8), fill=255)
    tile = tile.reduce(8)
    top = tile.crop((reach-1, 0, reach, reach)).resize((width-2*reach, reach))
    side = tile.crop((0, reach-1, reach, reach)).resize((reach, height-2*reach))
    across, down = Image.Transpose.FLIP_LEFT_RIGHT, Image.Transpose.FLIP_TOP_BOTTOM
    mask = Image.new('L', size, 255)
    mask.paste(top, (reach, 0))
    mask.paste(top.transpose(down), (reach, height-reach))
    mask.paste(side, (0, reach))
    mask.paste(side.transpose(across), (width-reach, reach))
    mask.paste(tile, (0, 0))
    mask.paste(tile.transpose(across), (width-reach, 0))
    mask.paste(tile.transpose(down), (0, height-reach))
    mask.paste(tile.transpose(across).transpose(down), (width-reach, height-reach))
    return mask

def bezel_image(size, fill=PANEL, outer=BG, radius=16, thickness=1, ring=False):
    """A card with a hairline rim, on the colour behind it. A ring is the gold rim of the control the keys or the controller are on."""
    image = Image.new('RGB', size, outer)
    image.paste(GOLD if ring else RIM, mask=rounded_mask(size, 0, radius))
    edge = max(thickness*2, 2) if ring else thickness
    image.paste(fill, mask=rounded_mask(size, edge, radius-edge))
    return image

class Bezel(tk.Canvas):
    """A card with a hairline rim. Its content goes in .body. The picture is redrawn only when the size changes, never for video frames."""
    def __init__(self, parent, fill=PANEL, outer=BG, radius=16, thickness=1, **options):
        factor = ctk.ScalingTracker.get_widget_scaling(parent)
        options = {name: round(value*factor) for name, value in options.items()}
        super().__init__(parent, bg=outer, highlightthickness=0, borderwidth=0, **options)
        self.fill = fill
        self.outer = outer
        self.radius = radius*factor
        self.thickness = thickness*factor
        self.inset = math.ceil(self.thickness+self.radius*.3)
        self.drawn = None
        self.timer = None
        self.picture = None
        self.ring = False
        self.item = self.create_image(0, 0, anchor='nw')
        self.body = tk.Frame(self, bg=fill)
        self.body.pack(fill='both', expand=True, padx=self.inset, pady=self.inset)
        self.bind('<Configure>', self.resized, add='+')
    def resized(self, _=None):
        if self.timer is not None:
            self.after_cancel(self.timer)
        self.timer = self.after(40, self.draw)
    def draw(self):
        self.timer = None
        size = (self.winfo_width(), self.winfo_height())
        if (size, self.ring) != self.drawn and min(size) > 2:
            self.drawn = (size, self.ring)
            self.picture = ImageTk.PhotoImage(bezel_image(size, self.fill, self.outer, self.radius, self.thickness, self.ring), master=self)
            self.itemconfigure(self.item, image=self.picture)
    def set_ring(self, on):
        if on != self.ring:
            self.ring = on
            self.draw()

@functools.lru_cache(maxsize=16)
def bold_font(pixels):
    try:
        return ImageFont.truetype('segoeuib.ttf', pixels)
    except OSError:
        return None

def heading(parent, text, pixels, **options):
    """A page's or a dialog's title: large and light, as the library sets a game's name."""
    return ctk.CTkLabel(parent, text=text, font=('Segoe UI Semilight', pixels), text_color=TEXT, **options)

def rim_menu(parent, behind=CARD, **options):
    """An option menu in a hairline rim. Returns the rim, to place, and the menu."""
    rim = Bezel(parent, fill=FIELD, outer=behind, radius=8)
    menu = ctk.CTkOptionMenu(rim.body, **options)
    menu.pack(fill='x')
    return rim, menu

def rim_field(parent, behind=CARD, **options):
    """A text entry in a hairline rim. Returns the rim, to place, and the entry."""
    rim = Bezel(parent, fill=FIELD, outer=behind, radius=8)
    field = ctk.CTkEntry(rim.body, fg_color=FIELD, border_width=0, **options)
    field.pack(fill='x')
    return rim, field

def thin_scrollbar(frame):
    frame._scrollbar.configure(width=10)

@functools.lru_cache(maxsize=16)
def label_font(pixels):
    return ImageFont.truetype('seguisb.ttf', pixels) if os.path.isfile(os.path.join(os.environ.get('WINDIR', ''), 'Fonts', 'seguisb.ttf')) else bold_font(pixels) or ImageFont.load_default(pixels)

def button_image(size, text='', icon=None, tone='plain', hovering=False, selected=False, enabled=True, behind=PANEL, radius=12, text_size=12, icon_size=20, text_colour=None, compound='left', factor=1, align='middle', focused=False):
    """A button as one picture: its face, a hairline rim, its icon and its label. The main action is solid white and turns gold under the pointer, as the library's Play does.
    The button the keys or the controller are on looks as it does under the pointer and wears a gold ring."""
    width, height = size
    hovering = hovering or focused
    # behind is one colour, or the piece of a picture the button sits on.
    image = behind.convert('RGB').resize(size) if isinstance(behind, Image.Image) else Image.new('RGB', size, behind)
    whole, inner = rounded_mask(size, 0, radius), rounded_mask(size, factor, radius-factor)
    ink = text_colour or TEXT if enabled else DISABLED
    if tone == 'main':
        image.paste(GOLD_HOVER if hovering and enabled else '#FAFAFA' if enabled else '#8A8A8A', mask=whole)
        ink = INK
    elif tone != 'ghost' or selected or hovering:
        if tone != 'ghost' or selected:
            image.paste(RIM if enabled else LINE, mask=whole)
        else:
            image.paste(RAISED, mask=whole)
        if tone == 'danger':
            face = '#8A2F43' if hovering else '#722637'
        else:
            face = RAISED if hovering or selected else CARD
        image.paste(face, mask=inner)
    draw = ImageDraw.Draw(image)
    font = label_font(text_size)
    text_width = draw.textlength(text, font=font) if text else 0
    small = icon.resize((icon_size, icon_size), Image.Resampling.LANCZOS) if icon is not None else None
    if compound == 'top' and small is not None:
        top = (height-icon_size-round(6*factor)-text_size)//2
        image.paste(small, ((width-icon_size)//2, top), small)
        draw.text((width/2, top+icon_size+round(6*factor)+text_size/2), text, font=font, fill=ink, anchor='mm')
    else:
        gap = round(7*factor) if small is not None and text else 0
        x = round(16*factor) if align == 'left' else (width-(icon_size if small is not None else 0)-gap-text_width)/2
        if small is not None:
            image.paste(small, (int(x), (height-icon_size+1)//2), small)
            x += icon_size+gap
        if text:
            draw.text((x, height/2), text, font=font, fill=ink, anchor='lm')
    if focused:
        ring = max(2, round(2*factor))
        draw.rounded_rectangle((0, 0, width-1, height-1), radius, outline=GOLD, width=ring)
    return image

class LuxButton(tk.Canvas):
    """A button drawn as one picture. Pictures are kept by appearance, so restyling it with what it already shows draws nothing."""
    def __init__(self, parent, text='', command=None, icon=None, width=40, height=40, radius=12, text_size=12, icon_size=20, behind=PANEL, tone='plain', compound='left', selected=False, enabled=True, text_colour=None, clickable=True, align='middle'):
        self.factor = ctk.ScalingTracker.get_widget_scaling(parent)
        super().__init__(parent, width=round(width*self.factor), height=round(height*self.factor), bg=behind, highlightthickness=0, borderwidth=0, cursor='hand2' if clickable and enabled else '')
        self.text = text
        self.command = command
        self.icon = icon
        self.radius = round(radius*self.factor)
        self.text_size = round(text_size*self.factor)
        self.icon_size = round(icon_size*self.factor)
        self.behind = behind
        self.tone = tone
        self.compound = compound
        self.selected = selected
        self.enabled = enabled
        self.text_colour = text_colour
        self.clickable = clickable
        self.align = align
        self.hovering = False
        self.focused = False
        self.under = None
        self.pictures = {}
        self.item = self.create_image(0, 0, anchor='nw')
        self.bind('<Configure>', lambda _: self.draw(), add='+')
        if clickable:
            self.bind('<Enter>', lambda _: self.hover(True), add='+')
            self.bind('<Leave>', lambda _: self.hover(False), add='+')
            self.bind('<ButtonRelease-1>', self.released, add='+')
    def restyle(self, **look):
        changed = False
        for name, value in look.items():
            current = getattr(self, name)
            if current is not value and current != value:
                setattr(self, name, value)
                changed = True
        if changed:
            if 'enabled' in look and self.clickable:
                self.configure(cursor='hand2' if self.enabled else '')
            self.draw()
    def set_under(self, image):
        """The picture behind a button that sits on art rather than on one colour: its corners, and a ghost button's face, show it."""
        if image is not self.under:
            self.under = image
            self.pictures.clear()
            self.draw()
    def hover(self, on):
        self.hovering = on
        self.draw()
    def released(self, event):
        if self.enabled and self.command is not None and 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height():
            self.command()
    def draw(self):
        size = (self.winfo_width(), self.winfo_height())
        if min(size) < 2:
            return
        hovering = self.hovering and self.enabled
        key = (size, self.text, id(self.icon), self.tone, hovering, self.selected, self.enabled, self.text_colour, self.focused)
        if key not in self.pictures:
            behind = self.under if self.under is not None else self.behind
            self.pictures[key] = ImageTk.PhotoImage(button_image(size, self.text, self.icon, self.tone, hovering, self.selected, self.enabled, behind, self.radius, self.text_size, self.icon_size, self.text_colour, self.compound, self.factor, self.align, self.focused), master=self)
        self.itemconfigure(self.item, image=self.pictures[key])

def dark_title_bar(window):
    """On Windows 11, a black title bar and a thin grey window border. Older Windows ignores the request."""
    def apply():
        try:
            hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
            for attribute, colour in ((34, RIM), (35, BG), (36, TEXT)):
                red, green, blue = ImageColor.getrgb(colour)
                value = ctypes.c_int(red | green << 8 | blue << 16)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value), 4)
            # A new dialog gets the toolkit's blue icon 200 ms after it opens.
            if isinstance(window, ctk.CTkToplevel):
                window.iconbitmap(str(Path(__file__).resolve().parent/'assets'/'playbridge.ico'))
        except (AttributeError, OSError, tk.TclError):
            pass
    window.after(400, apply)

def skin_path(name):
    roots = []
    if os.environ.get('PLAYBRIDGE_LOCAL_SKIN'):
        roots.append(Path(os.environ['PLAYBRIDGE_LOCAL_SKIN']))
    roots.append(Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / 'local_skin')
    return next((root / name for root in roots if (root / name).is_file()), None)

def local_image(name):
    path = skin_path(name)
    if path:
        try:
            with Image.open(path) as source:
                return source.convert('RGBA')
        except (OSError, ValueError):
            pass
    return None

def spinner_frames(canvas):
    """A white arc with a fading tail, turned from one large drawing so every step stays smooth."""
    mask = Image.new('L', (256, 256))
    draw = ImageDraw.Draw(mask)
    for step in range(48):
        draw.arc((8, 8, 247, 247), step*5, step*5+6, fill=255*(step+1)//48, width=14)
    frames = []
    for turn in range(24):
        art = Image.new('RGBA', (32, 32), TEXT)
        art.putalpha(mask.rotate(-turn*15, resample=Image.Resampling.BICUBIC).reduce(8))
        frames.append(ImageTk.PhotoImage(art, master=canvas))
    return frames

class AmbientScene:
    """The waiting screen: the library's page with no game behind it. No rendering or timer is attached to the live video path."""
    def __init__(self, canvas, animations=True):
        self.canvas = canvas
        self.animations = animations
        self.active = False
        self.size = None
        self.key = None
        self.status = None
        self.background = None
        self.turn = None
        self.spinner = spinner_frames(canvas)
        self.bg = canvas.create_image(0, 0, anchor='nw', tags='ambient')
        self.subtitle = canvas.create_text(0, 0, text='', fill=MUTED, font=('Segoe UI', 13), anchor='w', justify='left', tags='ambient')
        self.loader = canvas.create_image(0, 0, tags='ambient')
        canvas.itemconfigure('ambient', state='hidden')
    def show(self, active, status, now):
        c = self.canvas
        if not active:
            if self.active:
                c.itemconfigure('ambient', state='hidden')
            self.active = False
            return
        if not self.active:
            self.active = True
            c.itemconfigure('ambient', state='normal')
            c.tag_raise('ambient')
        size = (max(1, c.winfo_width()), max(1, c.winfo_height()))
        if size != self.key:
            self.key = size
            self.background = ImageTk.PhotoImage(self.backdrop(size), master=c)
            c.itemconfigure(self.bg, image=self.background)
        if size != self.size:
            self.size = size
            x, y = size[0]*.06, size[1]*.62
            c.coords(self.subtitle, x, y)
            c.itemconfigure(self.subtitle, width=max(200, size[0]*.55))
            c.coords(self.loader, x+16, y+52)
        if status != self.status:
            self.status = status
            c.itemconfigure(self.subtitle, text=status)
        turn = int(now*16) % 24 if self.animations else 0
        if turn != self.turn:
            self.turn = turn
            c.itemconfigure(self.loader, image=self.spinner[turn])
    @staticmethod
    def backdrop(size):
        """The same picture as behind Settings and Media, whatever game was played."""
        from scene import grain, no_art, ui_font
        image = ImageChops.add(no_art(size), grain(size), 1, -128)
        pixels = round(min(size[1]/1000, size[0]/1500)*66)
        ImageDraw.Draw(image).text((size[0]*.06, size[1]*.62-pixels*1.05), 'A new way to play', font=ui_font(max(22, pixels), 'semilight'), fill=TEXT, anchor='lm')
        return image
