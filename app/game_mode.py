"""Gaming Mode: the console's games on the PC, each with its art filling the window, and no console menu in the way."""
import math,threading,time
import tkinter as tk
from collections import OrderedDict
from datetime import datetime
import customtkinter as ctk
from PIL import Image,ImageTk
from console_control import game_detail
from gdi_presenter import GdiPresenter
from luxury_theme import Bezel,LuxButton,dark_title_bar,heading,BG,CARD,TEXT
import scene

SHELVES=(('all','All games'),('played','Most played'),('name','A to Z'),('ps5','PS5 games'),('ps4','PS4 games'))
KEY_HINTS=(('←  →','Move'),('Enter','{action}'),('F6','Live view'),('Type','Search'))
PAD_HINTS=(('cross','{action}'),('circle','Back'),('square','Refresh'),('L1','Previous tab'),('R1','Next tab'))
def load_icon(path,side=None):
 if path is None:return None
 try:
  with Image.open(path) as source:
   image=source.convert('RGB');return image.resize((side,side),Image.Resampling.BILINEAR) if side else image
 except (OSError,ValueError):return None
def load_picture(path,fit):
 """A picture for the page, asking the file for no more detail than the size needs."""
 if path is None:return None
 try:
  with Image.open(path) as source:
   source.draft('RGB',fit);return source.convert('RGB')
 except (OSError,ValueError):return None
def shelf_games(games,shelf='all',text=''):
 """The games on one shelf whose names hold the text. The console's own order is last played first."""
 text=text.strip().lower();prefix={'ps5':'PPSA','ps4':'CUSA'}.get(shelf,'')
 found=[game for game in games if game['title'].startswith(prefix) and text in game['name'].lower()]
 if shelf=='name':return sorted(found,key=lambda game:game['name'].lower())
 if shelf=='played':return sorted(found,key=lambda game:-(game.get('seconds') or 0))
 return found
def ago_text(played,now=None):
 """How long ago, in words."""
 days=int(((now or time.time())-played)//86400)
 if days<1:return 'today'
 if days==1:return 'yesterday'
 if days<60:return f'{days} days ago'
 return f'{days//30} months ago' if days<730 else f'{days//365} years ago'
def time_text(seconds):
 """Play time as it is said: 25 min, 3½ h, 21 h."""
 if seconds<3600:return f'{max(1,seconds//60)} min'
 halves=round(seconds/1800);return f'{halves//2}½ h' if halves%2 and halves<200 else f'{round(seconds/3600):,} h'
def size_text(size):
 if not isinstance(size,int) or size<=0:return '—'
 return f'{size/1e6:.0f} MB' if size<1e9 else f'{size/1e9:.1f} GB' if size<1e11 else f'{size/1e9:.0f} GB'
def game_line(game,running='',waiting=None,now=None):
 """The line under the focused game's name."""
 if game['title']==waiting:return 'Starting on your PS5'
 if game['title']==running:return 'Open on your PS5'
 seconds=game.get('seconds')
 if not seconds:return 'Not played on this console yet'
 return f"Played {ago_text(game['played'],now)}  ·  {time_text(seconds)} played" if game.get('played') else time_text(seconds)+' played'
def game_cards(game):
 """What the two cards that belong to a game say. Nothing here is estimated: the console keeps all of it."""
 kind={'PPSA':'PS5 game','CUSA':'PS4 game'}.get(game['title'][:4],'App');seconds=game.get('seconds')
 try:installed=datetime.fromtimestamp(game['installed']).strftime('%d %b %Y') if game.get('installed') else ''
 except (OSError,OverflowError,ValueError):installed=''
 return (('Your time',time_text(seconds) if seconds else 'Not played',f"Last played {ago_text(game['played'])}" if seconds and game.get('played') else 'On this console'),('On your PS5',size_text(game.get('size')),'  ·  '.join(part for part in (kind,installed) if part)))
def total_cards(games):
 """The same two cards with no game in focus."""
 return (('Your time',f'{sum(game.get("seconds") or 0 for game in games)//3600:,} h',f'Across {len(games)} games'),('On your PS5',f'{len(games)} games',size_text(sum(game.get('size') or 0 for game in games))))
def status_text(info):
 """What the top bar says about the console."""
 name=info.get('name') or 'PS5';return {'online':name+'  ·  Online','connecting':'Connecting to '+name}.get(info.get('state','offline'),'Not connected')
def power_items(online,running,exit_label=''):
 """What the power button offers. All of it goes through the console, and a soft reset needs a game to restart."""
 items=[]
 if online:items=([('soft_reset','Soft reset (restart game)')] if running else [])+[('rest','Rest mode'),('reboot','Reboot PS5'),('off','Turn off PS5'),('recovery','Recovery (Safe Mode)')]
 return items+([('exit',exit_label)] if exit_label else [])
def empty_line(link,searching):
 if link.games:return 'No game matches that name.' if searching else 'No games on this shelf.'
 if not link.online:return 'Connect to your PS5 and your games will appear here.'
 return 'Reading your games…' if link.refreshing else 'No games were found on this PS5.'

class ConfirmDialog:
 """Asks before anything that could lose progress or end the session. Answers the mouse, the keyboard and the controller."""
 current=None
 def __init__(self,parent,title,text,action,command,height=230):
  ConfirmDialog.close();ConfirmDialog.current=self;self.command=command
  self.window=window=ctk.CTkToplevel(parent);window.title('PlayBridge');window.configure(fg_color=BG);dark_title_bar(window);window.resizable(False,False);window.transient(parent)
  x=parent.winfo_rootx()+(parent.winfo_width()-460)//2;y=parent.winfo_rooty()+(parent.winfo_height()-height)//2;window.geometry(f'460x{height}+{max(0,x)}+{max(0,y)}')
  box=Bezel(window,fill=CARD,outer=BG,radius=14);box.pack(fill='both',expand=True,padx=14,pady=14)
  heading(box.body,title,22).pack(anchor='w',padx=18,pady=(16,8))
  ctk.CTkLabel(box.body,text=text,text_color=TEXT,font=('Segoe UI',12),wraplength=380,justify='left').pack(anchor='w',padx=18)
  buttons=tk.Frame(box.body,bg=CARD);buttons.pack(side='bottom',fill='x',padx=14,pady=12)
  LuxButton(buttons,'Cancel',self.cancel,width=120,height=36,radius=18,behind=CARD).pack(side='right')
  LuxButton(buttons,action,self.accept,width=150,height=36,radius=18,behind=CARD,tone='main').pack(side='right',padx=(0,8))
  window.protocol('WM_DELETE_WINDOW',self.cancel);window.bind('<Return>',lambda _:self.accept());window.bind('<Escape>',lambda _:self.cancel());window.after(80,window.focus_force)
 def accept(self):
  command=self.command;ConfirmDialog.close();command()
 def cancel(self):ConfirmDialog.close()
 @classmethod
 def close(cls):
  dialog,cls.current=cls.current,None
  if dialog is not None and dialog.window.winfo_exists():dialog.window.destroy()

class PopMenu:
 """A short list under a button, in a small window of its own so that it can lie over the video without touching it. Answers the mouse, the keys and the controller."""
 current=None;SEE_THROUGH='#010101'
 def __init__(self,parent,items,right,top,unit,choose):
  PopMenu.close();PopMenu.current=self;self.parent=parent;self.items=items;self.unit=unit;self.choose=choose;self.selected=0;self.rows=[];self.picture=None
  self.window=window=tk.Toplevel(parent);window.overrideredirect(True);window.configure(bg=self.SEE_THROUGH);window.attributes('-topmost',True);window.attributes('-transparentcolor',self.SEE_THROUGH)
  self.canvas=tk.Canvas(window,bg=self.SEE_THROUGH,highlightthickness=0,borderwidth=0);self.canvas.pack();self.item=self.canvas.create_image(0,0,anchor='nw');self.draw()
  window.geometry(f'+{right-self.picture.width()}+{top}')
  self.canvas.bind('<Motion>',self.pointer);self.canvas.bind('<ButtonRelease-1>',self.released)
  window.bind('<Up>',lambda _:self.answer('up'));window.bind('<Down>',lambda _:self.answer('down'));window.bind('<Return>',lambda _:self.answer('accept'));window.bind('<Escape>',lambda _:self.answer('back'));window.bind('<FocusOut>',lambda _:PopMenu.close())
  window.after(30,window.focus_force)
 def draw(self):
  image,self.rows=scene.drop_menu(self.items,self.selected,self.unit);flat=Image.new('RGB',image.size,self.SEE_THROUGH);flat.paste(image,(0,0),image)
  self.picture=ImageTk.PhotoImage(flat,master=self.canvas);self.canvas.configure(width=image.width,height=image.height);self.canvas.itemconfigure(self.item,image=self.picture)
 def row_at(self,y):
  return next((index for index,(top,bottom) in enumerate(self.rows) if top<=y<bottom),None)
 def pointer(self,event):
  row=self.row_at(event.y)
  if row is not None and row!=self.selected:self.selected=row;self.draw()
 def released(self,event):
  row=self.row_at(event.y)
  if row is not None:self.selected=row;self.answer('accept')
 def answer(self,event):
  if event in ('up','down'):self.selected=(self.selected+(1 if event=='down' else -1))%len(self.items);self.draw()
  elif event=='accept':
   key=self.items[self.selected][0];parent=self.parent;choose=self.choose;PopMenu.close();parent.focus_force();choose(key)
  elif event in ('back','leave'):
   parent=self.parent;PopMenu.close();parent.focus_force()
 @classmethod
 def close(cls):
  menu,cls.current=cls.current,None
  if menu is not None and menu.window.winfo_exists():menu.window.destroy()

class TopStrip(tk.Canvas):
 """The library's top bar over the other pages, as one picture drawn again only when something in it changes, never for a video frame."""
 def __init__(self,parent,press):
  super().__init__(parent,bg=BG,highlightthickness=0,borderwidth=0,height=60)
  self.press=press;self.values={};self.hover=None;self.hits={};self.drawn=None;self.picture=None;self.layout=None;self.item=self.create_image(0,0,anchor='nw')
  self.bind('<Configure>',lambda _:self.draw(),add='+');self.bind('<Motion>',self.pointer,add='+');self.bind('<Leave>',self.pointer_left,add='+');self.bind('<ButtonRelease-1>',self.released,add='+')
 def show(self,**values):
  self.values=values;self.draw()
 def draw(self):
  # The same size as on the library's page, so that nothing in the bar moves between pages.
  width=self.winfo_width();height=self.winfo_toplevel().winfo_height()
  if min(width,height)<120:return
  key=(width,height,self.hover,tuple(sorted(self.values.items())))
  if key==self.drawn:return
  self.drawn=key;self.layout=scene.page_layout(width,height);bar,self.hits=scene.top_bar(self.layout,dict(self.values,hover=self.hover));total=self.layout.bar_y+bar.height;image=Image.new('RGB',(width,total),BG);image.paste(bar,(0,self.layout.bar_y),bar)
  self.picture=ImageTk.PhotoImage(image,master=self);self.itemconfigure(self.item,image=self.picture)
  if self.winfo_reqheight()!=total:self.configure(height=total)
 def hit_at(self,x,y):
  return next((key for key,(x0,y0,x1,y1) in self.hits.items() if x0<=x<x1 and y0<=y<y1),None)
 def pointer(self,event):
  hit=self.hit_at(event.x,event.y)
  if hit!=self.hover:self.hover=hit;self.configure(cursor='hand2' if hit else '');self.draw()
 def pointer_left(self,_=None):
  if self.hover:self.hover=None;self.draw()
 def released(self,event):
  hit=self.hit_at(event.x,event.y)
  if hit:self.press(hit)

class GameShelf(tk.Frame):
 """The library page as one picture: a background thread draws its parts, this thread puts them together and shows them through the video's fast path. While only the row moves, only the row's band is shown again, and a reading that changes shows only its own card. Hidden, it uses no time at all."""
 SPEED=15;TURN_STEPS=10;PICTURES=120;QUIET_AFTER=.09;FADE=.28;MUSIC_AFTER=900;REST_YAW=math.radians(-5);FADE_LIMIT=3_700_000
 def __init__(self,parent,link,actions,sounds=None,animations=lambda:True):
  # No background, so Tk never paints here: a canvas fills itself black on any change, even of its cursor, and takes the page with it. Without a size to ask for, the grid would never place it.
  super().__init__(parent,bg='',width=378,height=265,highlightthickness=0,borderwidth=0,takefocus=1)
  self.link=link;self.actions=actions;self.sounds=sounds;self.animations=animations;self.present=GdiPresenter(self)
  self.games=[];self.target=0;self.position=0.0;self.shelf='all';self.text='';self.searching=False;self.running='';self.waiting=None;self.line='';self.notice='';self.revision=-1;self.exit_label='';self.clock='';self.info={}
  self.shown=False;self.layout=None;self.timer=None;self.resize_timer=None;self.expose_timer=None;self.music_timer=None;self.last_step=0;self.stale=False
  self.tilt=[self.REST_YAW,0.0];self.tilt_goal=[self.REST_YAW,0.0];self.hover=None;self.paths={};self.moving=OrderedDict();self.buttons={};self.menu=None
  self.page=None;self.page_key=None;self.fade_from=None;self.fade_at=0;self.under=None;self.clean=None;self.words=None;self.words_key=None;self.words_at=0;self.live=None;self.live_key=None;self.live_fresh=False;self.top=None;self.top_key=None;self.top_hits={};self.foot=None;self.foot_key=None;self.glows={}
  self.ready=OrderedDict();self.wanted=[];self.near=0;self.moved_at=0;self.lock=threading.Lock();self.wake=threading.Event();self.fresh=False
  threading.Thread(target=self.work,name='Library pictures',daemon=True).start()
  self.bind('<Configure>',self.resized,add='+');self.bind('<Expose>',self.exposed,add='+');self.bind('<Motion>',self.pointer,add='+');self.bind('<Leave>',self.pointer_left,add='+')
  self.bind('<ButtonRelease-1>',self.released,add='+');self.bind('<MouseWheel>',lambda event:self.move(-1 if event.delta>0 else 1),add='+');self.bind('<Key>',self.typed,add='+')

 # The drawing thread.
 def work(self):
  while True:
   self.wake.wait()
   # While the row moves, only what is about to be seen is drawn, so the two threads do not take turns on the one interpreter.
   busy=time.perf_counter()-self.moved_at<self.QUIET_AFTER
   with self.lock:
    job=next((job for job in (self.wanted[:self.near] if busy else self.wanted) if job[0] not in self.ready),None)
    idle=job is None and not busy
    if idle:self.wake.clear()
   if job is None:
    if not idle:time.sleep(.01)
    continue
   try:self.made(*job)
   except Exception:
    with self.lock:self.ready[job[0]]=None
   self.fresh=True
 def made(self,key,make):
  with self.lock:
   if key in self.ready:return self.ready[key]
  value=make()
  with self.lock:
   self.ready[key]=value;keep={job[0] for job in self.wanted}
   for old in [old for old in self.ready if old not in keep][:max(0,len(self.ready)-self.PICTURES)]:del self.ready[old]
   # A whole page is thousands of tiles' worth of memory.
   pages=[old for old in self.ready if old[0]=='page' and old not in keep]
   for old in pages[:max(0,len(pages)-2)]:del self.ready[old]
  return value
 def peek(self,key):
  with self.lock:return self.ready.get(key)
 def path(self,title):
  if title not in self.paths:self.paths[title]=self.link.icon(title)
  return self.paths[title]
 def art_path(self,title):
  key=('art',title)
  if key not in self.paths:self.paths[key]=self.link.art(title)
  return self.paths[key]
 def faces_job(self,game,side):
  title=game['title'];path=self.path(title);name=game['name']
  return ('faces',side,title,path),lambda:scene.cover_faces(load_icon(path),side,name)
 def tile_job(self,game):
  title=game['title'];path=self.path(title);name=game['name'];side=self.layout.small
  return ('tile',side,title,path),lambda:scene.flat_tile(load_icon(path),side,name)
 def rest_job(self,game):
  faces=self.faces_job(game,self.layout.focus)
  return ('rest',faces[0]),lambda:scene.render_cover(self.made(*faces),self.REST_YAW,0.0,quality=scene.BICUBIC)
 def name_job(self,game):
  layout=self.layout;name=game['name'];return ('name',layout.width,layout.height,name),lambda:scene.name_line(layout,name)
 def page_job(self,game):
  layout=self.layout;size=(layout.width,layout.height)
  if game is None:
   name='Your games';line=empty_line(self.link,self.text);cards=total_cards(self.link.games);art=cover=None
  else:
   name=game['name'];line=game_line(game,self.running,self.waiting);cards=game_cards(game);art=self.art_path(game['title']);cover=self.path(game['title'])
  return ('page',size,name,line,cards,art,cover),lambda:scene.library_page(load_picture(art,size),load_icon(cover),layout,name,line,cards)
 def live_job(self):
  layout=self.layout;info=self.info;fps=info.get('fps');stream=(min(1,fps/60) if fps else 0,str(round(fps)) if fps else '—',info.get('picture') or 'No picture yet',info.get('bitrate') or '—')
  open_name=self.link.game_name(self.running) if self.running else 'No game open';cpu,soc=info.get('cpu'),info.get('soc')
  console=('Console',f'CPU {cpu}°' if cpu else 'Not connected' if not self.link.online else '—','  ·  '.join(part for part in (f'SoC {soc}°' if soc else '',open_name) if part))
  return ('live',layout.width,layout.height,stream,console),lambda:scene.live_cards(layout,stream,console)
 def plan(self):
  """Tells the drawing thread what the page needs next, nearest first."""
  if self.layout is None or not self.shown:return
  layout=self.layout;focus=self.focused();near=[];later=[self.page_job(focus),self.live_job()]
  if focus:near+=[self.rest_job(focus),self.name_job(focus),self.faces_job(focus,layout.half)]
  across=(layout.width-layout.margin)//(layout.small+layout.gap)+3
  for reach in range(1,across+1):
   for index in (self.target+reach,self.target-reach if reach<4 else -1):
    if 0<=index<len(self.games):
     game=self.games[index];(near if reach<4 else later).append(self.tile_job(game))
     if reach==1:near+=[self.faces_job(game,layout.half),self.name_job(game)];later+=[self.rest_job(game),self.page_job(game)]
  with self.lock:self.wanted=near+later;self.near=len(near)
  self.wake.set();self.schedule()

 # What the rest of the app calls.
 def show(self,on):
  self.shown=on;self.link.browsing=on
  if on:
   self.focus_set();self.resized();self.revision=-1;self.sync(self.running,self.waiting,self.line,self.notice);self.plan();self.schedule();self.settle_later()
  else:
   self.menu=None
   if self.timer is not None:self.after_cancel(self.timer);self.timer=None
 def focused(self):
  return self.games[self.target] if 0<=self.target<len(self.games) else None
 def sync(self,running,waiting,line,notice=''):
  """Called a few times a second while showing: nothing is drawn unless something changed."""
  now=(running,waiting,line,notice);changed=now!=(self.running,self.waiting,self.line,self.notice);self.running,self.waiting,self.line,self.notice=now;clock=time.strftime('%H:%M')
  if clock!=self.clock:self.clock=clock;self.stale=True;self.schedule()
  if self.revision!=self.link.revision:
   self.revision=self.link.revision;self.paths.clear();self.refilter();return
  if changed:self.stale=True;self.plan()
 def set_info(self,info):
  """What the top bar and the live cards say. They are redrawn only if something changed."""
  if info!=self.info:
   # The readings only touch their own two cards, once they are drawn.
   if any(info.get(key)!=self.info.get(key) for key in ('name','state','pad')):self.stale=True
   self.info=info;self.plan()
 def set_exit(self,label):
  self.exit_label=label
 def refilter(self):
  title=self.focused()['title'] if self.focused() else None;games=shelf_games(self.link.games,self.shelf,self.text);same=[game['title'] for game in games]==[game['title'] for game in self.games];self.games=games
  self.target=next((index for index,game in enumerate(self.games) if game['title']==title),0)
  if not same:self.position=float(self.target)
  self.stale=True;self.plan();self.settle_later()
 def set_shelf(self,key):
  if key!=self.shelf:
   self.shelf=key;self.refilter();self.cue('move')
 def go_to(self,index):
  if index!=self.target and 0<=index<len(self.games):
   self.target=index;self.moved_at=time.perf_counter();self.plan();self.cue('move');self.settle_later()
 def go_to_title(self,title):
  self.shelf='all';self.text='';self.refilter();self.go_to(next((index for index,game in enumerate(self.games) if game['title']==title),self.target));self.stale=True;self.schedule()
 def move(self,change):
  if not self.games:return
  at=max(0,min(len(self.games)-1,self.target+change))
  if at==self.target:self.cue('edge')
  else:self.go_to(at)
 def settle_later(self):
  """A game's art is read first and its music starts once the row has been still for a moment, so a quick run along the row plays nothing."""
  game=self.focused();self.link.focus=game['title'] if game else ''
  if self.music_timer is not None:self.after_cancel(self.music_timer)
  self.music_timer=self.after(self.MUSIC_AFTER,self.settled)
 def settled(self):
  self.music_timer=None;game=self.focused()
  if self.sounds is not None and self.shown:self.sounds.want_track(self.link.music_file(game['title']) if game else None)
 def action_text(self):
  """What the big button says. Empty when there is nothing for it to do."""
  game=self.focused();title=game['title'] if game else ''
  if title and title==self.waiting:return 'Starting'
  if title and title==self.running:return 'Resume'
  if self.link.online:return 'Play' if game else ''
  return 'Connecting' if self.info.get('state')=='connecting' else 'Connect'
 def choose(self):
  text=self.action_text();game=self.focused()
  if text=='Connect':self.cue('accept');self.run('connect')
  elif game is None or text=='Connecting':self.cue('edge')
  else:self.cue('accept');self.run('open',game['title'])
 def run(self,name,*values):
  command=self.actions.get(name)
  if command is not None:command(*values)
 def cue(self,name):
  if self.sounds is not None:self.sounds.play(name)
 def navigate(self,event):
  """A move from the keyboard or the controller. True if the page used it."""
  if self.menu:
   if event in ('up','down'):self.menu['selected']=(self.menu['selected']+(1 if event=='down' else -1))%len(self.menu['items']);self.cue('move');self.stale=True;self.schedule()
   elif event=='accept':self.menu_choose(self.menu['selected'])
   return True
  moves={'left':-1,'right':1,'previous':-5,'next':5}
  if event in moves:self.move(moves[event])
  elif event in ('up','down'):
   keys=[key for key,_ in SHELVES];self.set_shelf(keys[(keys.index(self.shelf)+(1 if event=='down' else -1))%len(keys)])
  elif event=='accept':self.choose()
  elif event=='refresh':self.link.refresh();self.cue('move')
  else:return False
  return True
 def dismiss(self):
  """Closes what is open on the page. True if there was something."""
  if self.menu:self.menu=None;self.cue('back');self.stale=True;self.schedule();return True
  return False
 def open_menu(self,kind):
  if kind=='power':items=power_items(self.link.online,self.running,self.exit_label)
  else:items=([('close','Close game')] if self.running else [])+[('refresh','Refresh library'),('live','Live view')]
  if not items:self.notice='Connect to your PS5 first.';self.cue('edge');self.stale=True;self.schedule();return
  self.menu=dict(kind=kind,items=items,selected=0,box=None,rows=[]);self.cue('move');self.stale=True;self.schedule()
 def menu_choose(self,index):
  key=self.menu['items'][index][0];self.menu=None;self.stale=True;self.schedule();self.cue('accept')
  if key=='refresh':self.link.refresh()
  else:self.run(key)

 # Pointer and keys.
 def typed(self,event):
  if event.state&0x20004:return None
  if event.keysym=='Escape' and (self.text or self.searching):self.stop_search();return 'break'
  if event.keysym=='BackSpace':
   if self.text:self.text=self.text[:-1];self.searching=True;self.refilter()
   return 'break'
  if len(event.char)==1 and event.char.isprintable() and len(self.text)<40:self.text+=event.char;self.searching=True;self.refilter();return 'break'
  return None
 def start_search(self):
  self.searching=True;self.stale=True;self.schedule()
 def stop_search(self):
  self.text='';self.searching=False;self.refilter()
 def pointer(self,event):
  hit=self.hit_at(event.x,event.y)
  if hit!=self.hover:
   # Only the bars and buttons look different under the pointer.
   if (self.hover or ('tile',))[0]!='tile' or (hit or ('tile',))[0]!='tile':self.stale=True
   if hit and hit[0]=='menu':self.menu['selected']=hit[1]
   self.hover=hit;self.configure(cursor='hand2' if hit and hit[0]!='away' else '');self.schedule()
  layout=self.layout
  if layout and self.animations():
   cx,cy,side,_=scene.tile_pose(0,layout);across=(event.x-cx)/side;down=(event.y-cy)/side
   goal=[self.REST_YAW*.4-across*math.radians(24),down*math.radians(16)] if abs(across)<=.8 and abs(down)<=.8 else [self.REST_YAW,0.0]
   if goal!=self.tilt_goal:self.tilt_goal=goal;self.schedule()
 def pointer_left(self,_=None):
  self.tilt_goal=[self.REST_YAW,0.0]
  if self.hover:self.hover=None;self.stale=True
  self.schedule()
 def visible(self):
  """The tiles that can be on screen, nearest the ends first for drawing."""
  layout=self.layout;step=layout.small+layout.gap
  low=max(0,math.floor(self.position-(layout.margin+layout.small)/step)-1);high=min(len(self.games)-1,math.ceil(self.position+(layout.width-layout.margin-layout.focus)/step)+1)
  return range(low,high+1)
 def hit_at(self,x,y):
  layout=self.layout
  if layout is None:return None
  if self.menu:
   box=self.menu['box']
   if box and box[0]<=x<box[2] and box[1]<=y<box[3]:
    for index,(top,bottom) in enumerate(self.menu['rows']):
     if top<=y-box[1]<bottom:return ('menu',index)
   return ('away',0)
  for key,(x0,y0,x1,y1) in self.top_hits.items():
   if x0<=x<x1 and y0<=y<y1:return ('top',key)
  if layout.pill_y<=y<layout.pill_y+layout.pill:
   if layout.margin<=x<layout.margin+layout.pill_width and self.action_text():return ('action',0)
   if layout.option_x<=x<layout.option_x+layout.pill and self.focused():return ('more',0)
  if layout.row_y<=y<layout.row_y+layout.focus and self.games:
   for index in self.visible():
    cx,cy,side,_=scene.tile_pose(index-self.position,layout)
    if abs(x-cx)<=side/2 and abs(y-cy)<=side/2:return ('tile',index)
  return None
 def released(self,event):
  self.focus_set();kind,value=self.hit_at(event.x,event.y) or (None,None)
  if kind=='menu':self.menu_choose(value)
  elif kind=='away':self.dismiss()
  elif kind=='tile':
   if value==self.target:self.choose()
   else:self.go_to(value)
  elif kind=='action':self.choose()
  elif kind=='more':self.open_menu('more')
  elif kind=='top':
   if value=='search':
    if self.searching or self.text:self.stop_search()
    else:self.start_search()
   elif value=='shelf':self.navigate('down')
   elif value=='power':self.open_menu('power')
   elif value!='games':self.cue('accept');self.run(value)

 # Putting the page together.
 def resized(self,_=None):
  if self.resize_timer is not None:self.after_cancel(self.resize_timer)
  self.resize_timer=self.after(50,self.arrange)
 def arrange(self):
  self.resize_timer=None;width,height=self.winfo_width(),self.winfo_height()
  if min(width,height)<120 or not self.shown:return
  if self.layout is not None and (self.layout.width,self.layout.height)==(width,height):self.show_all();return
  self.page=self.under.resize((width,height),scene.BILINEAR) if self.under is not None else Image.new('RGB',(width,height),BG);self.present.picture(self.page,0,0)
  self.layout=scene.page_layout(width,height);self.moving.clear();self.page_key=None;self.fade_from=None;self.under=None;self.words=None;self.words_key=None;self.live=None;self.live_key=None;self.top_key=None;self.foot_key=None;self.buttons.clear();self.glows.clear();self.stale=True
  self.plan();self.schedule()
 def schedule(self,delay=1):
  if self.timer is None and self.shown:self.last_step=self.last_step or time.perf_counter();self.timer=self.after(delay,self.step)
 def step(self):
  self.timer=None
  if not self.shown or self.layout is None:return
  now=time.perf_counter();passed=min(.05,now-self.last_step);self.last_step=now;moving=False;smooth=self.animations()
  gap=self.target-self.position
  if gap:
   self.moved_at=now;self.position=float(self.target) if not smooth or abs(gap)<.004 else self.position+gap*(1-math.exp(-passed*self.SPEED));moving=True
  elif self.tilt!=self.tilt_goal:
   for part in (0,1):
    gap=self.tilt_goal[part]-self.tilt[part];self.tilt[part]=self.tilt_goal[part] if not smooth or abs(gap)<.003 else self.tilt[part]+gap*(1-math.exp(-passed*11))
   moving=True
  fresh,self.fresh=self.fresh,False;self.adopt(now)
  fading=self.fade_from is not None;naming=now-self.words_at<.16;waiting=bool(self.waiting)
  if fading or self.stale or self.under is None:self.stale=False;self.live_fresh=False;self.paint(now)
  elif self.live_fresh:self.paint_live()
  # A menu lies over the row, so with one open the row cannot be shown alone.
  elif moving or fresh or naming or waiting:self.paint(now) if self.menu else self.paint_row()
  with self.lock:pending=any(job[0] not in self.ready for job in self.wanted)
  if moving or fading or naming or fresh:self.schedule(4)
  elif waiting:self.schedule(80)
  elif pending or now-self.moved_at<self.QUIET_AFTER:self.schedule(30)
 def adopt(self,now):
  """Starts showing what the drawing thread has finished. The page changes only once the row has come to rest, so a run along the row does not fade through every game on the way."""
  focus=self.focused();key=self.name_job(focus)[0] if focus else None;words=self.peek(key) if key else None
  if key!=self.words_key and (words is not None or key is None):self.words=words;self.words_key=key;self.words_at=now if self.animations() else 0
  key=self.live_job()[0];live=self.peek(key)
  if live is not None and key!=self.live_key:self.live=live;self.live_key=key;self.live_fresh=True
  if now-self.moved_at<self.QUIET_AFTER:return
  key=self.page_job(focus)[0];page=self.peek(key)
  if page is not None and key!=self.page_key:
   self.fade_from=self.page if self.page_key is not None and self.animations() and page.width*page.height<=self.FADE_LIMIT else None;self.fade_at=now;self.page=page;self.page_key=key;self.stale=True
 def exposed(self,_=None):
  if self.shown and self.expose_timer is None:self.expose_timer=self.after_idle(self.after_expose)
 def after_expose(self):
  self.expose_timer=None;self.show_all()
 def show_all(self):
  if self.under is not None and self.shown:self.present.picture(self.under,0,0)
 def tile_picture(self,game,offset):
  """A tile's picture where it is: flat in the row, in 3D in the focus, following the pointer, and swinging on its axis on the way between the two. The swing is drawn small and enlarged, since nobody can see the detail while it moves."""
  layout=self.layout;title=game['title'];path=self.path(title);reach=abs(offset);faces_key=('faces',layout.focus,title,path)
  if reach>=.995:
   picture=self.peek(('tile',layout.small,title,path));return (picture,-(layout.small//2),-(layout.small//2)) if picture is not None else None
  rest=self.peek(('rest',faces_key))
  if reach<.005:
   yaw=round(math.degrees(self.tilt[0]));pitch=round(math.degrees(self.tilt[1]))
   if rest is not None and (yaw,pitch)==(round(math.degrees(self.REST_YAW)),0):return rest
   key=('tilt',faces_key,yaw,pitch);picture=self.moving.get(key)
   if picture is None:
    faces=self.peek(faces_key)
    if faces is None:return rest
    picture=scene.render_cover(faces,math.radians(yaw),math.radians(pitch));self.remember(key,picture)
   return picture
  sign=1 if offset>0 else -1;step=max(1,min(self.TURN_STEPS-1,round(reach*self.TURN_STEPS)));key=('turn',faces_key,sign,step);picture=self.moving.get(key)
  if picture is None:
   faces=self.peek(('faces',layout.half,title,path))
   if faces is None:return rest
   share=step/self.TURN_STEPS;sprite,left,top=scene.render_cover(faces,scene.turn_of(sign*share)+self.REST_YAW*(1-share),0.0,1-share);scale=scene.tile_pose(share,layout)[2]/faces['side']
   sprite=scene.dimmed(sprite.resize((round(sprite.width*scale),round(sprite.height*scale)),scene.BILINEAR),1-(1-scene.SMALL_LIGHT)*share);picture=(sprite,round(left*scale),round(top*scale));self.remember(key,picture)
  return picture
 def remember(self,key,picture):
  self.moving[key]=picture
  if len(self.moving)>160:self.moving.popitem(last=False)
 def glow(self,reach):
  """The light around the focused tile, fading as it leaves."""
  step=round((1-reach)*8)
  if step not in self.glows:
   light=scene.focus_glow(self.layout.focus).copy();light.putalpha(light.getchannel('A').point([value*step//8 for value in range(256)]));self.glows[step]=light
  return self.glows[step]
 def draw_row(self,band):
  """The tiles and the focused game's name on a copy of the row's band."""
  layout=self.layout;top=layout.band_y
  if self.games:
   for index in sorted(self.visible(),key=lambda index:-abs(index-self.position)):
    offset=index-self.position;cx,cy,side,reach=scene.tile_pose(offset,layout);picture=self.tile_picture(self.games[index],offset)
    if picture is None:continue
    if reach<1:
     light=self.glow(reach);band.paste(light,(round(cx-light.width/2),round(cy-light.height/2)-top),light)
    sprite,left,up=picture;band.paste(sprite,(round(cx)+left,round(cy)+up-top),sprite)
  if self.words is not None:
   sprite,x,y=self.words;share=(time.perf_counter()-self.words_at)/.16
   band.paste(sprite,(x,y-top),sprite if share>=1 else sprite.getchannel('A').point([int(value*max(0,share)) for value in range(256)]))
 def paint_row(self):
  layout=self.layout;band=self.clean.copy();self.draw_row(band);self.under.paste(band,(0,layout.band_y));self.present.picture(band,0,layout.band_y)
 def paint(self,now):
  """The whole page: the art, everything over it, then the row."""
  layout=self.layout;frame=self.page.copy()
  if self.fade_from is not None:
   share=(now-self.fade_at)/self.FADE
   if share>=1 or self.fade_from.size!=frame.size:self.fade_from=None
   else:frame=Image.blend(self.fade_from,frame,share*share*(3-2*share))
  if self.live is not None:frame.paste(self.live,(layout.cards[2][0],layout.cards_y),self.live)
  for picture,place in self.overlays(now):frame.paste(picture,place,picture)
  self.clean=frame.crop((0,layout.band_y,layout.width,layout.band_y+layout.band_height));band=self.clean.copy();self.draw_row(band);frame.paste(band,(0,layout.band_y))
  if self.menu:
   picture,place=self.menu_picture();frame.paste(picture,place,picture)
  self.under=frame;self.present.picture(frame,0,0)
 def paint_live(self):
  """Only the two cards whose readings change while the page stands still."""
  layout=self.layout;self.live_fresh=False;x,y=layout.cards[2][0],layout.cards_y;part=self.page.crop((x,y,x+self.live.width,y+self.live.height));part.paste(self.live,(0,0),self.live);self.under.paste(part,(x,y));self.present.picture(part,x,y)
 def overlays(self,now):
  layout=self.layout;parts=[(self.top_picture(),(0,layout.bar_y)),(self.foot_picture(),(0,layout.hints_y))];text=self.action_text()
  if text:parts.append((self.action_picture(text,now),(layout.margin,layout.pill_y)))
  if self.focused():parts.append((self.button_picture('more'),(layout.option_x,layout.pill_y)))
  return parts
 def button_picture(self,mark):
  hovering=(self.hover or ('',))[0]==mark;key=('round',mark,hovering);picture=self.buttons.get(key)
  if picture is None:picture=self.buttons[key]=scene.round_button(self.layout.pill,mark,hovering)
  return picture
 def action_picture(self,text,now):
  layout=self.layout;starting=text=='Starting';hovering=(self.hover or ('',))[0]=='action';enabled=text!='Connecting'
  key=(text,hovering,enabled,int(now*12)%12 if starting else None);picture=self.buttons.get(key)
  if picture is None:
   if len(self.buttons)>32:self.buttons.clear()
   picture=self.buttons[key]=scene.play_pill(layout.pill_width,layout.pill,text,hovering,enabled,key[3]*30 if starting else None)
  return picture
 def menu_picture(self):
  layout=self.layout;menu=self.menu;picture,rows=scene.drop_menu(menu['items'],menu['selected'],layout.unit)
  if menu['kind']=='power':x=layout.width-layout.margin-picture.width;y=layout.bar_y+layout.bar+round(10*layout.unit)
  else:x=layout.option_x;y=layout.pill_y-picture.height-round(10*layout.unit)
  menu['box']=(x,y,x+picture.width,y+picture.height);menu['rows']=rows;return picture,(x,y)
 def top_picture(self):
  layout=self.layout;info=self.info;hover=self.hover[1] if self.hover and self.hover[0]=='top' else None
  values=dict(status=status_text(info),online=info.get('state')=='online',clock=self.clock,shelf=dict(SHELVES)[self.shelf],pad=bool(info.get('pad')),hover=hover,search=self.text,searching=self.searching);key=tuple(sorted(values.items()))
  if key!=self.top_key:self.top_key=key;self.top,self.top_hits=scene.top_bar(layout,values)
  return self.top
 def foot_picture(self):
  action=self.action_text();action=action if action in ('Resume','Connect') else 'Play';key=(bool(self.info.get('pad')),self.line,self.notice,action)
  if key!=self.foot_key:
   self.foot_key=key;self.foot=scene.hint_bar(self.layout,tuple((mark,label.format(action=action)) for mark,label in (PAD_HINTS if key[0] else KEY_HINTS)),self.notice or self.line,bool(self.notice))
  return self.foot
