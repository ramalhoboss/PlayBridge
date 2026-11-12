"""Pages over PlayBridge's own picture: Settings, with a menu on the left, and Media, a grid; panels float and scroll over it.
Tk cannot see through a widget, so the panels are opaque and the picture shows around them; their shadows and rims are drawn with transparency, which the canvas blends."""
import functools
import tkinter as tk
import customtkinter as ctk
import numpy as np
from PIL import Image,ImageDraw,ImageFilter,ImageTk
from luxury_theme import BG,CARD,GOLD,MUTED,TEXT,rounded_mask,tint
from scene import no_art

BICUBIC=Image.Resampling.BICUBIC
RAIL=340;FOOT=92;MARGIN=40;RADIUS=16;SHADOW=18;GAP=20;PAD=22
# Panels sit side by side once each can be this wide, up to four across; a lone column stops at COLUMN, a column among others at WIDEST.
NARROWEST=480;COLUMN=860;WIDEST=820

def light_map(size,rail):
 """How much of the art shows at each point: little under the menu, more on the right, and none at the very bottom, where the Save button sits on black. Worked out small, because nothing in it is sharp."""
 y,x=np.mgrid[0:90,0:160];u=x/159;v=y/89;edge=min(.9,rail/max(size[0],1))
 across=np.clip((u-edge*.55)/(1-edge*.55),0,1)**.9*.62+.08
 top=1-np.clip(1-v/.22,0,1)**2*.35;bottom=np.clip((1-v)/.16,0,1)**1.4
 light=Image.fromarray((np.clip(across*top*bottom,0,1)*255).astype('uint8'),'L').resize(size,BICUBIC)
 return np.asarray(light,dtype=np.float32)[...,None]/255
def backdrop(size,rail):
 """The whole page: the same picture behind every page, whatever game was played, dimmed where the words and panels sit."""
 width,height=size
 picture=np.asarray(no_art(size),dtype=np.float32)*light_map(size,rail)
 # Fine noise, because a slow ramp in so few steps of dark shows bands.
 noise=np.asarray(Image.effect_noise((width,height),3.0),dtype=np.float32)[...,None]-128
 return Image.fromarray(np.clip(picture+noise*.04,0,255).astype('uint8'),'RGB')
BLUE=(92,120,255)
@functools.lru_cache(maxsize=24)
def panel(width,height,radius,shadow,colour=BLUE):
 """A panel with a soft shadow below it and a rim lit from above, on nothing: the canvas blends it over the art."""
 full=(width+2*shadow,height+2*shadow);image=Image.new('RGBA',full,(0,0,0,0))
 dark=Image.new('L',full);ImageDraw.Draw(dark).rounded_rectangle((shadow,shadow+6,shadow+width,shadow+height+6),radius,fill=170)
 image.putalpha(dark.filter(ImageFilter.GaussianBlur(shadow/2.2)))
 glow=Image.new('L',full);ImageDraw.Draw(glow).rounded_rectangle((shadow,shadow,shadow+width,shadow+min(height,90)),radius,fill=60)
 halo=Image.new('RGBA',full,colour+(0,));halo.putalpha(glow.filter(ImageFilter.GaussianBlur(shadow/1.6)));image.alpha_composite(halo)
 # The rim: the accent, strongest at the top left, as if lit from there.
 y,x=np.mgrid[0:height,0:width];light=np.clip(1-(y/max(height,1))*.75-(x/max(width,1))*.35,0,1)
 rim=(30+light*150).astype('uint8')
 tone=np.empty((height,width,3),dtype=np.float32);mix=light[...,None]*.35
 tone[:]=np.array(colour,dtype=np.float32);tone=tone*(1-mix)+255*mix
 card=Image.fromarray(np.concatenate([tone.astype('uint8'),np.zeros((height,width,1),'uint8')],2),'RGBA');card.putalpha(Image.fromarray(rim,'L'));card.putalpha(Image.fromarray(np.minimum(np.asarray(rounded_mask((width,height),0,radius)),rim),'L'))
 card.paste(Image.new('RGBA',(width,height),CARD),(0,0),rounded_mask((width,height),1,radius-1))
 image.alpha_composite(card,(shadow,shadow));return image
@functools.lru_cache(maxsize=16)
def pill(width,height,strength):
 """The frosted mark behind the chosen item in the menu, with a gold bar at its edge."""
 image=Image.new('RGBA',(width,height),(255,255,255,0));image.putalpha(rounded_mask((width,height),0,height/2).point(lambda value:value*strength//255))
 if strength>20:ImageDraw.Draw(image).rounded_rectangle((0,height*.26,4,height*.74),2,fill=GOLD)
 return image

class GlassPage(tk.Frame):
 """Settings sections, each a list of panels. card() returns a frame to fill, as a plain card did; open() shows a section."""
 def __init__(self,parent,title='Settings'):
  super().__init__(parent,bg=BG);self.title=title;self.factor=ctk.ScalingTracker.get_widget_scaling(parent)
  self.scenery=tk.Canvas(self,bg=BG,highlightthickness=0,borderwidth=0);self.scenery.place(x=0,y=0,relwidth=1,relheight=1)
  self.view=tk.Canvas(self.scenery,bg=BG,highlightthickness=0,borderwidth=0,yscrollincrement=1)
  self.footer=tk.Frame(self,bg=BG)
  self.sections={};self.order=[];self.current=None;self.hovered=None;self.size=None;self.key=None;self.pictures={};self.backdrop=None;self.timer=None;self.top=0;self.height=0;self.heights=None;self.watch_timer=None;self.footer_on=False;self.view_size=(10,10);self.colour=BLUE
  self.wrapping=[];self.wrap_width=None
  self.picture_item=self.scenery.create_image(0,0,anchor='nw');self.view_picture=self.view.create_image(0,0,anchor='nw')
  self.bind('<Configure>',lambda _:self.later(),add='+')
  self.bind_all('<MouseWheel>',self.wheel,add='+')
 def unit(self,value):return round(value*self.factor)
 def section(self,key,label,icon=None,subtitle=''):
  self.sections[key]={'label':label,'icon':icon,'subtitle':subtitle,'cards':[]};self.order.append(key);return key
 def card(self,key,title=None):
  u=self.unit;shell=tk.Frame(self.view,bg=CARD);inner=tk.Frame(shell,bg=CARD);inner.pack(fill='x',padx=u(PAD),pady=(u(18),u(14)))
  if title:ctk.CTkLabel(inner,text=title,font=('Segoe UI Semibold',22),text_color=TEXT).pack(anchor='w',pady=(0,12))
  self.sections[key]['cards'].append(shell);shell.bind('<Configure>',lambda _:self.watch(),add='+');return inner
 def wrap(self,label):
  """A label whose lines follow the width of its panel, which changes with the window and the number of columns."""
  self.wrapping.append(label);return label
 def columns(self,width):
  """How many panels side by side and how wide each is, for a view this wide."""
  u=self.unit;room=width-u(2*SHADOW);gap=u(GAP)
  count=max(1,min(4,(room+gap)//(u(NARROWEST)+gap)))
  if count==1:return 1,min(room,u(COLUMN))
  return count,min(u(WIDEST),(room-(count-1)*gap)//count)
 def fit_text(self,pixels):
  value=max(120,round(pixels/self.factor))
  if value==self.wrap_width:return
  self.wrap_width=value
  for label in self.wrapping:
   try:label.configure(wraplength=value)
   except tk.TclError:pass
 def open(self,key):
  self.current=key;self.top=0;self.view.yview_moveto(0);self.draw_menu();self.layout()
 def show_footer(self,on):
  """The line that says what a change did, for the sections whose changes reach the connection or the next start."""
  self.footer_on=on;self.later(0)
 def refresh(self):
  """Called when the page is shown."""
  self.later(0)
 def later(self,delay=40):
  if self.timer is not None:self.after_cancel(self.timer)
  self.timer=self.after(delay,self.redraw)
 def redraw(self):
  self.timer=None;width,height=self.winfo_width(),self.winfo_height()
  if min(width,height)<50:return
  if (width,height)!=self.key:
   self.key=(width,height);self.backdrop=backdrop((width,height),self.unit(RAIL))
   self.pictures['page']=ImageTk.PhotoImage(self.backdrop,master=self);self.scenery.itemconfigure(self.picture_item,image=self.pictures['page'])
  rail,foot,margin=self.unit(RAIL),self.unit(FOOT),self.unit(MARGIN)
  # Kept here, because the canvas reports its new size only after Tk has drawn it.
  self.view_size=(max(10,width-rail-margin),max(10,height-foot));self.view.place(x=rail,y=0,width=self.view_size[0],height=self.view_size[1])
  if self.footer_on:self.footer.place(x=self.unit(48),y=height-foot+self.unit(18))
  else:self.footer.place_forget()
  self.pictures['view']=ImageTk.PhotoImage(self.backdrop.crop((rail,0,width-margin,height-foot)),master=self);self.view.itemconfigure(self.view_picture,image=self.pictures['view'])
  self.draw_menu();self.layout()
 def draw_menu(self):
  canvas=self.scenery;canvas.delete('menu')
  if self.backdrop is None:return
  u=self.unit;x=u(48)
  canvas.create_text(x,u(64),text=self.title,anchor='w',fill=TEXT,font=('Segoe UI Semilight',36),tags='menu')
  for index,key in enumerate(self.order):
   item=self.sections[key];y=u(140)+index*u(62);tag=f'item:{key}';chosen=key==self.current
   strength=46 if chosen else 22 if key==self.hovered else 0
   if strength:
    picture=ImageTk.PhotoImage(pill(u(272),u(52),strength),master=self);self.pictures[tag]=picture;canvas.create_image(x-u(12),y,image=picture,anchor='w',tags=('menu',tag))
   else:canvas.create_rectangle(x-u(12),y-u(26),x+u(260),y+u(26),outline='',fill='',tags=('menu',tag))
   if item['icon'] is not None:
    key_icon=(tag,chosen);picture=self.pictures.get(key_icon)
    if picture is None:picture=self.pictures[key_icon]=ImageTk.PhotoImage(tint(item['icon'],TEXT if chosen else MUTED).resize((u(24),u(24)),Image.Resampling.LANCZOS),master=self)
    canvas.create_image(x+u(8),y,image=picture,anchor='w',tags=('menu',tag))
   canvas.create_text(x+u(46),y,text=item['label'],anchor='w',fill=TEXT if chosen else MUTED,font=('Segoe UI Semibold' if chosen else 'Segoe UI',17),tags=('menu',tag))
   canvas.tag_bind(tag,'<Button-1>',lambda _,key=key:self.choose(key));canvas.tag_bind(tag,'<Enter>',lambda _,key=key:self.hover(key));canvas.tag_bind(tag,'<Leave>',lambda _:self.hover(None))
 choose_hook=None
 def choose(self,key):
  if self.choose_hook:self.choose_hook(key)
  else:self.open(key)
 def hover(self,key):
  if key!=self.hovered:self.hovered=key;self.scenery.configure(cursor='hand2' if key else '');self.draw_menu()
 def layout(self):
  view=self.view;view.delete('content')
  for key in [key for key in self.pictures if key[0]=='panel']:del self.pictures[key]
  if self.current is None or self.backdrop is None:return
  u=self.unit;item=self.sections[self.current];width,view_height=self.view_size;count,column=self.columns(width)
  if column<u(200):return
  x=u(SHADOW);y=u(40)
  view.create_text(x+2,y+2,text=item['label'],anchor='w',fill='#000000',font=('Segoe UI Semilight',32),tags='content')
  view.create_text(x,y,text=item['label'],anchor='w',fill=TEXT,font=('Segoe UI Semilight',32),tags='content')
  if item['subtitle']:view.create_text(x,y+u(42),text=item['subtitle'],anchor='w',fill=MUTED,font=('Segoe UI',14),tags='content')
  y+=u(82 if item['subtitle'] else 52)
  inset=max(2,round(u(RADIUS)*.35));self.fit_text(column-2*inset-2*u(PAD))
  view.update_idletasks()
  # Each panel goes under the shortest column, so the columns end close together.
  tops=[y]*count
  for number,shell in enumerate(item['cards']):
   height=shell.winfo_reqheight()+2*inset;place=tops.index(min(tops));left=x+place*(column+u(GAP));top=tops[place]
   picture=self.pictures[('panel',number)]=ImageTk.PhotoImage(panel(column,height,u(RADIUS),u(SHADOW),self.colour),master=self)
   view.create_image(left-u(SHADOW),top-u(SHADOW),image=picture,anchor='nw',tags='content')
   view.create_window(left+inset,top+inset,window=shell,anchor='nw',width=column-2*inset,tags='content')
   tops[place]=top+height+u(GAP)
  self.heights=tuple(shell.winfo_reqheight() for shell in item['cards']);self.height=max(tops)+u(24);view.configure(scrollregion=(0,0,width,max(self.height,view_height)));self.pin()
 def watch(self):
  """A panel whose content grew or shrank moves the ones below it. Laying out moves every panel, so only a real change in height lays out again."""
  if self.watch_timer is None:self.watch_timer=self.after(60,self.check)
 def check(self):
  self.watch_timer=None
  if self.current is not None and tuple(shell.winfo_reqheight() for shell in self.sections[self.current]['cards'])!=self.heights:self.layout()
 def pin(self):
  """The art stays put while the panels scroll over it."""
  self.view.coords(self.view_picture,0,self.view.canvasy(0));self.view.tag_lower(self.view_picture)
 def wheel(self,event):
  if not self.winfo_ismapped() or not str(event.widget).startswith(str(self.view)):return
  if self.height<=self.view_size[1]:return
  self.view.yview_scroll(-round(event.delta/120*self.unit(48)),'units');self.pin()

class GlassBoard(tk.Frame):
 """Equal panels in a grid over the picture, under a header and above a footer that stay put: the Media page.
 The buttons in the header and footer sit on the picture itself, so each one is given the piece of it behind it."""
 TOP=168;FOOT=80;SIDE=52;SMALLEST=380;LARGEST=460
 def __init__(self,parent,title,subtitle):
  super().__init__(parent,bg=BG);self.title=title;self.subtitle=subtitle;self.factor=ctk.ScalingTracker.get_widget_scaling(parent)
  self.scenery=tk.Canvas(self,bg=BG,highlightthickness=0,borderwidth=0);self.scenery.place(x=0,y=0,relwidth=1,relheight=1)
  self.view=tk.Canvas(self.scenery,bg=BG,highlightthickness=0,borderwidth=0,yscrollincrement=1)
  self.picture_item=self.scenery.create_image(0,0,anchor='nw');self.view_picture=self.view.create_image(0,0,anchor='nw')
  self.pictures={};self.key=None;self.backdrop=None;self.colour=BLUE;self.timer=None;self.watch_timer=None;self.cards=[];self.heights=None
  self.buttons={'top':[],'left':[],'right':[],'foot':[]};self.items={};self.status_text='';self.height=0;self.view_size=(10,10);self.shape=None
  # Called when the number or the width of the columns changes, so the panels can be filled again at their new size.
  self.resized=None
  self.bind('<Configure>',lambda _:self.later(),add='+');self.bind_all('<MouseWheel>',self.wheel,add='+')
 def unit(self,value):return round(value*self.factor)
 def add(self,button,where):
  """A button made on .scenery: top is the header's first row on the right, left and right its second row, foot the footer on the right."""
  self.buttons[where].append(button);self.items[button]=self.scenery.create_window(0,0,window=button,anchor='nw');return button
 def status(self,text):
  self.status_text=text;self.scenery.itemconfigure('status',text=text)
 def refresh(self):
  """Called when the page is shown."""
  self.later(0)
 def later(self,delay=40):
  if self.timer is not None:self.after_cancel(self.timer)
  self.timer=self.after(delay,self.redraw)
 def grid_size(self):
  """How many panels across, and how wide each one is."""
  u=self.unit;room=self.view_size[0]-u(2*SHADOW);gap=u(GAP)
  count=max(1,(room+gap)//(u(self.SMALLEST)+gap))
  return count,max(u(160),min(u(self.LARGEST),(room-(count-1)*gap)//count))
 def redraw(self):
  self.timer=None;width,height=self.winfo_width(),self.winfo_height()
  if min(width,height)<50:return
  if (width,height)!=self.key:
   self.key=(width,height);self.backdrop=backdrop((width,height),self.unit(self.SIDE*3))
   self.pictures['page']=ImageTk.PhotoImage(self.backdrop,master=self);self.scenery.itemconfigure(self.picture_item,image=self.pictures['page'])
  u=self.unit;left=u(self.SIDE-SHADOW);top=u(self.TOP);foot=u(self.FOOT)
  self.view_size=(max(10,width-2*left),max(10,height-top-foot));self.view.place(x=left,y=top,width=self.view_size[0],height=self.view_size[1])
  self.pictures['view']=ImageTk.PhotoImage(self.backdrop.crop((left,top,left+self.view_size[0],top+self.view_size[1])),master=self);self.view.itemconfigure(self.view_picture,image=self.pictures['view'])
  self.draw_words(width,height);self.place_buttons(width,height)
  shape=self.grid_size()
  if shape!=self.shape and self.resized is not None:self.shape=shape;self.resized()
  else:self.shape=shape;self.layout()
 def draw_words(self,width,height):
  c=self.scenery;c.delete('words');u=self.unit;side=u(self.SIDE)
  c.create_text(side+2,u(50)+2,text=self.title,anchor='w',fill='#000000',font=('Segoe UI Semilight',30),tags='words')
  c.create_text(side,u(50),text=self.title,anchor='w',fill=TEXT,font=('Segoe UI Semilight',30),tags='words')
  c.create_text(side,u(92),text=self.subtitle,anchor='w',fill=MUTED,font=('Segoe UI',13),tags='words')
  c.create_text(side,height-u(self.FOOT)/2,text=self.status_text,anchor='w',fill=MUTED,font=('Segoe UI',12),tags=('words','status'))
 def place_buttons(self,width,height):
  u=self.unit;side=u(self.SIDE);gap=u(10)
  def row(buttons,middle,right):
   x=width-side if right else side
   for button in (reversed(buttons) if right else buttons):
    w,h=button.winfo_reqwidth(),button.winfo_reqheight()
    if right:x-=w
    y=round(middle-h/2);self.scenery.coords(self.items[button],x,y)
    button.set_under(self.backdrop.crop((x,y,x+w,y+h)))
    x=x-gap if right else x+w+gap
  row(self.buttons['top'],u(58),True);row(self.buttons['left'],u(136),False);row(self.buttons['right'],u(136),True);row(self.buttons['foot'],height-u(self.FOOT)/2,True)
 def clear(self):
  for shell,_ in self.cards:shell.destroy()
  self.cards=[];self.heights=None;self.view.delete('content');self.view.yview_moveto(0)
 def card(self,span=False):
  """A frame to fill, on a panel of the grid; span takes a whole row."""
  shell=tk.Frame(self.view,bg=CARD);self.cards.append((shell,span));shell.bind('<Configure>',lambda _:self.watch(),add='+');return shell
 def layout(self):
  view=self.view;view.delete('content')
  for key in [key for key in self.pictures if key[0]=='panel']:del self.pictures[key]
  if self.backdrop is None:return
  u=self.unit;count,column=self.grid_size();width,view_height=self.view_size;gap=u(GAP);inset=max(2,round(u(RADIUS)*.35))
  view.update_idletasks()
  # Rows first, so the panels of a row share one height.
  rows=[];row=[]
  for shell,span in self.cards:
   if span and row:rows.append(row);row=[]
   row.append((shell,span))
   if span or len(row)==count:rows.append(row);row=[]
  if row:rows.append(row)
  y=u(SHADOW);number=0
  for row in rows:
   height=max(shell.winfo_reqheight() for shell,_ in row)+2*inset
   for index,(shell,span) in enumerate(row):
    w=count*column+(count-1)*gap if span else column;x=u(SHADOW)+index*(column+gap)
    picture=self.pictures[('panel',number)]=ImageTk.PhotoImage(panel(w,height,u(RADIUS),u(SHADOW),self.colour),master=self);number+=1
    view.create_image(x-u(SHADOW),y-u(SHADOW),image=picture,anchor='nw',tags='content')
    view.create_window(x+inset,y+inset,window=shell,anchor='nw',width=w-2*inset,tags='content')
   y+=height+gap
  self.heights=tuple(shell.winfo_reqheight() for shell,_ in self.cards);self.height=y+u(8);view.configure(scrollregion=(0,0,width,max(self.height,view_height)));self.pin()
 def watch(self):
  if self.watch_timer is None:self.watch_timer=self.after(60,self.check)
 def check(self):
  self.watch_timer=None
  if self.cards and tuple(shell.winfo_reqheight() for shell,_ in self.cards)!=self.heights:self.layout()
 def pin(self):
  self.view.coords(self.view_picture,0,self.view.canvasy(0));self.view.tag_lower(self.view_picture)
 def wheel(self,event):
  if not self.winfo_ismapped() or not str(event.widget).startswith(str(self.view)):return
  if self.height<=self.view_size[1]:return
  self.view.yview_scroll(-round(event.delta/120*self.unit(48)),'units');self.pin()
