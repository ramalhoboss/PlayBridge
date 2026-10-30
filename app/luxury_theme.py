"""PlayBridge's black and gold theme and original ambient rendering, with optional local artwork.
All Tk operations run on the UI thread. Animation stops when video is visible.
"""
import ctypes, functools, math, os, random, sys, time
import tkinter as tk
from pathlib import Path
import customtkinter as ctk
from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFilter, ImageFont, ImageTk

BG = '#000000'
STAGE = '#000000'
PANEL = '#050403'
CARD = '#0D0B07'
RAISED = '#1C170C'
RAISED_HOVER = '#2C2410'
LINE = '#2C2410'
GOLD_LINE = '#6B5521'
GOLD_EDGE = '#B8922E'
GOLD = '#D4AF37'
GOLD_HOVER = '#F3D778'
GOLD_SOFT = '#EBD48E'
INK = '#0D0A03'
TEXT = '#F7F2E4'
MUTED = '#B3A484'

def apply_theme():
    """Black and gold defaults for the widgets the app uses, so none that names no colour falls back to the stock blue."""
    ctk.set_appearance_mode('dark')
    ctk.set_default_color_theme('blue')
    colours = {
        'CTk': {'fg_color': BG},
        'CTkToplevel': {'fg_color': BG},
        'CTkFrame': {'fg_color': CARD, 'top_fg_color': RAISED},
        'CTkButton': {'fg_color': CARD, 'hover_color': RAISED, 'border_width': 0, 'text_color': TEXT, 'text_color_disabled': '#6F6650'},
        'CTkLabel': {'text_color': TEXT},
        'CTkEntry': {'fg_color': CARD, 'border_width': 0, 'text_color': TEXT, 'placeholder_text_color': MUTED},
        'CTkSwitch': {'fg_color': RAISED, 'progress_color': GOLD, 'button_color': TEXT, 'button_hover_color': GOLD_SOFT, 'text_color': TEXT, 'text_color_disabled': '#6F6650'},
        'CTkSlider': {'fg_color': RAISED, 'progress_color': GOLD, 'button_color': GOLD, 'button_hover_color': GOLD_HOVER},
        'CTkOptionMenu': {'fg_color': CARD, 'button_color': RAISED, 'button_hover_color': RAISED_HOVER, 'text_color': TEXT, 'text_color_disabled': '#6F6650'},
        'CTkScrollbar': {'button_color': '#3A2E12', 'button_hover_color': GOLD_LINE},
        'CTkScrollableFrame': {'label_fg_color': CARD},
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

# Light and dark bands, as polished gold reflects.
METAL = ((0, '#FCF0B8'), (.22, '#E2BD52'), (.42, '#96701E'), (.58, '#F5DF90'), (.78, '#B88A26'), (1, '#7A5A15'))
BUTTON_METAL = ((0, '#FFF1B5'), (.42, '#E6C258'), (.62, '#C4962A'), (1, '#9C7419'))
BUTTON_METAL_HOVER = ((0, '#FFF8D6'), (.42, '#F3D778'), (.62, '#DDB143'), (1, '#B68C26'))
LETTER_METAL = ((0, '#FFF4C8'), (.45, '#E8C65C'), (.62, '#B98A2A'), (1, '#F0D684'))

def blend(stops, position):
    """The colour at a position from 0 to 1 along (position, colour) stops."""
    for (start, low), (end, high) in zip(stops, stops[1:]):
        if position <= end:
            mix = (position-start)/(end-start)
            return tuple(int(a+(b-a)*mix) for a, b in zip(ImageColor.getrgb(low), ImageColor.getrgb(high)))
    return ImageColor.getrgb(stops[-1][1])

def banded(stops, size):
    """Bands running from top to bottom."""
    strip = Image.new('RGB', (1, 64))
    strip.putdata([blend(stops, y/63) for y in range(64)])
    return strip.resize(size, Image.Resampling.BILINEAR)

@functools.lru_cache(maxsize=1)
def diagonal_metal():
    tile = Image.new('RGB', (96, 96))
    tile.putdata([blend(METAL, (x+y)/190) for y in range(96) for x in range(96)])
    return tile

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

def bezel_image(size, fill=PANEL, outer=BG, radius=16, thickness=1, glow=0):
    """A panel with a thin polished gold rim, and optionally a soft glow around it, on the colour behind it."""
    image = Image.new('RGB', size, outer)
    rim = rounded_mask(size, glow, radius)
    if glow:
        image.paste(GOLD, mask=rim.filter(ImageFilter.GaussianBlur(glow*.6)).point([value//5 for value in range(256)]))
    image.paste(diagonal_metal().resize(size, Image.Resampling.BILINEAR), mask=rim)
    image.paste(fill, mask=rounded_mask(size, glow+thickness, radius-thickness))
    return image

class Bezel(tk.Canvas):
    """A panel with a gold rim. Its content goes in .body. The picture is redrawn only when the size changes, never for video frames."""
    def __init__(self, parent, fill=PANEL, outer=BG, radius=16, thickness=1, glow=0, **options):
        factor = ctk.ScalingTracker.get_widget_scaling(parent)
        options = {name: round(value*factor) for name, value in options.items()}
        super().__init__(parent, bg=outer, highlightthickness=0, borderwidth=0, **options)
        self.fill = fill
        self.outer = outer
        self.radius = radius*factor
        self.thickness = thickness*factor
        self.glow = math.ceil(glow*factor)
        self.inset = self.glow+math.ceil(self.thickness+self.radius*.3)
        self.plain = False
        self.drawn = None
        self.timer = None
        self.picture = None
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
        if not self.plain and size != self.drawn and min(size) > 2:
            self.drawn = size
            self.picture = ImageTk.PhotoImage(bezel_image(size, self.fill, self.outer, self.radius, self.thickness, self.glow), master=self)
            self.itemconfigure(self.item, image=self.picture)
    def edge_to_edge(self, on):
        """Fullscreen: the content covers the rim."""
        self.plain = on
        self.body.pack_configure(padx=0 if on else self.inset, pady=0 if on else self.inset)
        self.resized()

@functools.lru_cache(maxsize=16)
def bold_font(pixels):
    try:
        return ImageFont.truetype('segoeuib.ttf', pixels)
    except OSError:
        return None

def gold_text(text, pixels):
    """Polished gold lettering at four times the size, to stay sharp on high-resolution screens. None without the font, so the caller can use plain text."""
    font = bold_font(pixels*4)
    if font is None:
        return None
    spacing = pixels*4//3
    box = ImageDraw.Draw(Image.new('L', (1, 1))).multiline_textbbox((0, 0), text, font=font, spacing=spacing)
    mask = Image.new('L', (box[2]+8, box[3]+8))
    ImageDraw.Draw(mask).multiline_text((0, 0), text, font=font, fill=255, spacing=spacing)
    art = banded(LETTER_METAL, mask.size).convert('RGBA')
    art.putalpha(mask)
    return art.crop(mask.getbbox())

def gold_label(parent, text, pixels, **options):
    """A label in polished gold lettering, or in plain gold without the font."""
    art = gold_text(text, pixels)
    if art is None:
        return ctk.CTkLabel(parent, text=text, font=('Segoe UI', pixels, 'bold'), text_color=GOLD, **options)
    return ctk.CTkLabel(parent, text='', image=ctk.CTkImage(art, size=(art.width//4, art.height//4)), **options)

def gold_menu(parent, behind=PANEL, **options):
    """An option menu in a thin gold rim. Returns the rim, to place, and the menu."""
    rim = Bezel(parent, fill=CARD, outer=behind, radius=8)
    menu = ctk.CTkOptionMenu(rim.body, **options)
    menu.pack(fill='x')
    return rim, menu

def gold_field(parent, behind=BG, **options):
    """A text entry in a thin gold rim. Returns the rim, to place, and the entry."""
    rim = Bezel(parent, fill=CARD, outer=behind, radius=8)
    field = ctk.CTkEntry(rim.body, fg_color=CARD, border_width=0, **options)
    field.pack(fill='x')
    return rim, field

def thin_scrollbar(frame):
    frame._scrollbar.configure(width=10)

def dot(colour):
    """A round status mark, large enough to reduce cleanly."""
    image = Image.new('RGBA', (64, 64))
    ImageDraw.Draw(image).ellipse((0, 0, 63, 63), fill=colour)
    return image

@functools.lru_cache(maxsize=16)
def label_font(pixels):
    return ImageFont.truetype('seguisb.ttf', pixels) if os.path.isfile(os.path.join(os.environ.get('WINDIR', ''), 'Fonts', 'seguisb.ttf')) else bold_font(pixels) or ImageFont.load_default(pixels)

def button_image(size, text='', icon=None, tone='plain', hovering=False, selected=False, enabled=True, behind=PANEL, radius=12, text_size=12, icon_size=20, text_colour=None, compound='left', factor=1):
    """A button as one picture: its face, a thin rim, its icon and its label."""
    width, height = size
    image = Image.new('RGB', size, behind)
    whole, inner = rounded_mask(size, 0, radius), rounded_mask(size, factor, radius-factor)
    ink = text_colour or TEXT if enabled else '#6F6650'
    if tone == 'gold':
        image.paste(GOLD_SOFT, mask=whole)
        image.paste(banded(BUTTON_METAL_HOVER if hovering else BUTTON_METAL, size), mask=inner)
        ink = INK
    elif tone != 'ghost' or selected or hovering:
        if enabled and (tone != 'ghost' or selected):
            image.paste(diagonal_metal().resize(size, Image.Resampling.BILINEAR), mask=whole)
        else:
            image.paste(GOLD_LINE, mask=whole)
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
        x = (width-(icon_size if small is not None else 0)-gap-text_width)/2
        if small is not None:
            image.paste(small, (int(x), (height-icon_size+1)//2), small)
            x += icon_size+gap
        if text:
            draw.text((x, height/2), text, font=font, fill=ink, anchor='lm')
    return image

class LuxButton(tk.Canvas):
    """A button drawn as one picture. Pictures are kept by appearance, so restyling it with what it already shows draws nothing."""
    def __init__(self, parent, text='', command=None, icon=None, width=40, height=40, radius=12, text_size=12, icon_size=20, behind=PANEL, tone='plain', compound='left', selected=False, enabled=True, text_colour=None, clickable=True):
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
        self.hovering = False
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
        key = (size, self.text, id(self.icon), self.tone, hovering, self.selected, self.enabled, self.text_colour)
        if key not in self.pictures:
            self.pictures[key] = ImageTk.PhotoImage(button_image(size, self.text, self.icon, self.tone, hovering, self.selected, self.enabled, self.behind, self.radius, self.text_size, self.icon_size, self.text_colour, self.compound, self.factor), master=self)
        self.itemconfigure(self.item, image=self.pictures[key])

def gold_title_bar(window):
    """On Windows 11, a black title bar and a gold window border. Older Windows ignores the request."""
    def apply():
        try:
            hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
            for attribute, colour in ((34, GOLD_EDGE), (35, BG), (36, GOLD_SOFT)):
                red, green, blue = ImageColor.getrgb(colour)
                value = ctypes.c_int(red | green << 8 | blue << 16)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(value), 4)
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

def gradient(size):
    # A small original raster, enlarged once on resize; never regenerated per frame. Fine noise hides the banding of so dark a ramp.
    w, h = 240, 120
    image = Image.new('RGB', (w, h))
    pixels = image.load()
    for y in range(h):
        for x in range(w):
            u, v = x / w, y / h
            glow = math.exp(-((u-.79)**2 / .05 + (v-.44)**2 / .14))
            ember = math.exp(-((u-.12)**2 / .16 + (v-.92)**2 / .05))
            pixels[x, y] = (int(1+44*glow+16*ember), int(1+31*glow+11*ember), int(8*glow+3*ember))
    noise = Image.effect_noise(size, 2.5)
    image = ImageChops.add(image.resize(size, Image.Resampling.BILINEAR), Image.merge('RGB', (noise, noise, noise)), 1, -128)
    # The rings belong to the background because Tk cannot smooth a canvas oval.
    for k, colour in enumerate(('#4A3A14', '#7A6124', '#B8922E')):
        reach = 77+k*22
        ring = Image.new('L', (reach*16, reach*16))
        ImageDraw.Draw(ring).ellipse((16, 16, reach*16-17, reach*16-17), outline=255, width=8)
        image.paste(colour, (round(size[0]*.79)-reach, round(size[1]*.44+5)-reach), ring.reduce(8))
    return image

def spinner_frames(canvas):
    """A gold arc with a fading tail, turned from one large drawing so every step stays smooth."""
    mask = Image.new('L', (256, 256))
    draw = ImageDraw.Draw(mask)
    for step in range(48):
        draw.arc((8, 8, 247, 247), step*5, step*5+6, fill=255*(step+1)//48, width=14)
    frames = []
    for turn in range(24):
        art = Image.new('RGBA', (32, 32), GOLD)
        art.putalpha(mask.rotate(-turn*15, resample=Image.Resampling.BICUBIC).reduce(8))
        frames.append(ImageTk.PhotoImage(art, master=canvas))
    return frames

class AmbientScene:
    """Idle canvas scene. No rendering or timer is attached to the live video path."""
    def __init__(self, canvas, animations=True):
        self.canvas = canvas
        self.animations = animations
        self.active = False
        self.size = None
        self.phase = 0
        self.last = 0
        self.status = None
        self.background = None
        self.spinner = spinner_frames(canvas)
        self.bg = canvas.create_image(0, 0, anchor='nw', tags='ambient')
        self.lines = [canvas.create_line(0, 0, 1, 1, fill=c, width=1, smooth=True, tags='ambient')
                      for c in ('#2E240E', '#3D3012', '#57451A', '#8A6D28', '#C9A441', '#6B5521', '#3D3012')]
        drift = random.Random(7)
        self.dust = [(canvas.create_oval(0,0,1,1,fill=drift.choice(('#6B5521','#A67C1E','#E8C75E')),outline='',tags='ambient'), drift.random(), drift.random(), drift.uniform(.6,1.7), drift.uniform(.4,1)) for _ in range(44)]
        self.brand = None
        try:
            with Image.open(Path(__file__).resolve().parent/'assets'/'playbridge.png') as art:
                self.brand = ImageTk.PhotoImage(art.convert('RGBA').resize((92,92),Image.Resampling.LANCZOS))
        except OSError:pass
        self.emblem=canvas.create_image(0,0,image=self.brand,tags='ambient')
        self.dots=[canvas.create_oval(0,0,1,1,fill='#E8C75E',outline='',tags='ambient') for _ in range(12)]
        self.badge=canvas.create_text(0,0,text='DIRECT STREAMING    /    H.264 + AAC',fill=GOLD_SOFT,font=('Segoe UI',9,'bold'),anchor='w',tags='ambient')
        self.mark = canvas.create_text(0, 0, text='Y O U R   C O N S O L E .   R E I M A G I N E D .', fill=GOLD, font=('Segoe UI', 12, 'bold'), tags='ambient')
        self.headings = {}
        self.title = canvas.create_image(0, 0, anchor='w', tags='ambient') if bold_font(12) else canvas.create_text(0, 0, text='A new way\nto play.', fill=TEXT, font=('Segoe UI', 27), tags='ambient')
        self.subtitle = canvas.create_text(0, 0, text='', fill=MUTED, font=('Segoe UI', 12), tags='ambient')
        self.loader = canvas.create_image(0, 0, tags='ambient')
        canvas.itemconfigure('ambient', state='hidden')
    def show(self, active, status, now):
        c = self.canvas
        if not active:
            if self.active:
                c.itemconfigure('ambient', state='hidden')
            self.active = False
            return
        first = not self.active
        self.active = True
        if first:
            c.itemconfigure('ambient', state='normal')
            c.tag_raise('ambient')
        size = (max(1, c.winfo_width()), max(1, c.winfo_height()))
        resized = size != self.size
        if resized:
            self.size = size
            self.background = ImageTk.PhotoImage(gradient(size))
            c.itemconfigure(self.bg, image=self.background)
            w, h = size
            x=w*.085;cy=h*.44
            c.coords(self.mark,x,cy-108);c.itemconfigure(self.mark,anchor='w',font=('Segoe UI',9,'bold'))
            c.coords(self.title,x,cy-20);self.set_heading(46 if w>=850 else 36)
            c.coords(self.subtitle,x,cy+100);c.itemconfigure(self.subtitle,anchor='w',width=max(200,w*.5),justify='left')
            c.coords(self.badge,x,h-40)
            c.coords(self.emblem,w*.79,cy+5)
            c.coords(self.loader,x+16,cy+150)
        if status != self.status:
            self.status = status
            c.itemconfigure(self.subtitle, text=status)
        if not (first or resized or self.animations and now-self.last >= .05):
            return
        self.last = now
        self.phase = now*.16 if self.animations else 0
        w, h = size
        for k, line in enumerate(self.lines):
            coords = []
            for j in range(49):
                x = w*j/48
                y = h*.78 + math.sin(j/48*math.pi*2.1+self.phase+k*.14)*h*.065 + k*7
                coords.extend((x, y))
            c.coords(line, *coords)
        for k,dot in enumerate(self.dots):
            angle=self.phase*.4+k*math.pi/6;r=75+(k%3)*22
            dx=w*.79+math.cos(angle)*r;dy=h*.44+5+math.sin(angle)*r
            c.coords(dot,dx-1.5,dy-1.5,dx+1.5,dy+1.5)
        for dot,left,rise,radius,speed in self.dust:
            dx=(left+math.sin(self.phase*.5*speed+left*9)*.012)*w;dy=h-((rise+self.phase*.4*speed)%1)*h
            c.coords(dot,dx-radius,dy-radius,dx+radius,dy+radius)
        c.itemconfigure(self.loader, image=self.spinner[int(now*16)%24 if self.animations else 0])

    def set_heading(self, points):
        c = self.canvas
        if c.type(self.title) == 'text':
            c.itemconfigure(self.title, anchor='w', justify='left', font=('Segoe UI', points, 'bold'))
            return
        if points not in self.headings:
            self.headings[points] = ImageTk.PhotoImage(gold_text('A new way\nto play.', int(points*c.winfo_fpixels('1p'))).reduce(4), master=c)
        c.itemconfigure(self.title, image=self.headings[points])

def fade_in(window, enabled):
    """One bounded entrance animation for settings; no ongoing main-window timer."""
    if not enabled:
        return
    try:
        window.attributes('-alpha', 0.0)
    except Exception:
        return
    def step(index=1):
        if not window.winfo_exists():
            return
        window.attributes('-alpha', min(1.0, index/8))
        if index < 8:
            window.after(16, step, index+1)
    window.after(0, step)
