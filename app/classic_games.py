"""The Games page exactly as 1.5.x drew it, inside the Qt window. Its pictures come from scene.py and are put together as game_mode.GameShelf
put them together: a background thread draws the parts, this thread lays them out, and while only the row moves only the row's band is shown
again. The Qt page shows the result one picture pixel to one screen pixel and passes the pointer back, so every hit, hover and animation is the
classic one. What the page says comes from the shell's Shelf, the same state the keyboard, the controller and the sounds already use.
The game's art is the one part the window draws itself: sharp, a little larger than the page, leaning with the pointer under a clear picture
of everything else, with its frosted copy in the glass."""
import math,threading,time
from collections import OrderedDict
from PIL import Image,ImageChops
from PySide6.QtCore import Property,QRect,QSize,QTimer,Qt,Signal
from PySide6.QtGui import QImage,QPainter
from PySide6.QtQuick import QQuickPaintedItem
import library_view,scene
from library_view import ViewChoice
from game_mode import HIDDEN_SHELF,KEY_HINTS,PAD_HINTS,SHELVES,ago_text,empty_line,game_cards,game_line,load_icon,load_picture,status_text,total_cards,trophy_card,trophy_rows,trophy_total_card
SHELF_NAMES=dict(SHELVES+(HIDDEN_SHELF,))
# What the keys and the controller do while the trophy list is open.
LIST_KEY_HINTS=(('↑  ↓','Move'),('Enter','Guide'),('PgUp  PgDn','Page'),('Esc','Close'))
LIST_PAD_HINTS=(('cross','Guide'),('circle','Close'),('L1','Page up'),('R1','Page down'))

def lay(base,sprite,x,y):
 """A picture with clear parts laid over another at x, y, the part outside it left off."""
 left=max(0,-x);top=max(0,-y);right=min(sprite.width,base.width-x);bottom=min(sprite.height,base.height-y)
 if right>left and bottom>top:base.alpha_composite(sprite,(x+left,y+top),(left,top,right,bottom))
def qt_round(value):return math.floor(value+.5)
def texture_units(pixels,ratio):
 """The textureSize, in the window's units, for which Qt makes a texture exactly this many pixels wide: it makes it round(size × ratio)."""
 base=round(pixels/ratio)
 return next((size for size in (base,base-1,base+1) if qt_round(size*ratio)==pixels),base)
def whole_units(units,ratio):
 """The nearest size from units up whose pixels at this screen scale are a whole number, so a picture of it lies on the screen's pixels."""
 return next((size for size in range(units,units+8) if abs(size*ratio-round(size*ratio))<1e-6),units)
def qt_picture(picture):
 """A finished PIL picture as a Qt one of its own, made on the drawing thread."""
 picture=picture.convert('RGB');data=picture.tobytes();return QImage(data,picture.width,picture.height,picture.width*3,QImage.Format.Format_RGB888).convertToFormat(QImage.Format.Format_RGB32)

class ClassicFrame(QQuickPaintedItem):
 """The page's picture on screen, clear where the art shows. Painting only copies what the drawing already finished, so it costs the render
 thread almost nothing. glass says where the window shows the frosted art, in the window's units."""
 view=None
 glassChanged=Signal()
 def __init__(self,parent=None):
  super().__init__(parent);self.boxes=[]
  self.setOpaquePainting(False);self.setMipmap(False);self.setAntialiasing(False);self.setFillColor(Qt.GlobalColor.transparent)
  if ClassicFrame.view is not None:ClassicFrame.view.frame=self
 def paint(self,painter):
  view=ClassicFrame.view
  if view is not None:view.paint_into(painter,self)
 def set_glass(self,boxes):
  if boxes!=self.boxes:self.boxes=boxes;self.glassChanged.emit()
 glass=Property('QVariantList',lambda self:self.boxes,notify=glassChanged)

class ClassicArt(QQuickPaintedItem):
 """The art behind the page (role 'art') or its frosted copy (role 'frost'), in one of two slots, so that a new game's art can fade in over
 the last one. The page sets their place; their size is the picture's, one picture pixel to one screen pixel for the art."""
 view=None
 slotChanged=Signal();roleChanged=Signal();shownChanged=Signal()
 def __init__(self,parent=None):
  super().__init__(parent);self.place=0;self.kind='art';self.on=False;self.picture=None
  self.setOpaquePainting(True);self.setMipmap(False);self.setAntialiasing(False)
  if ClassicArt.view is not None:ClassicArt.view.arts.append(self)
 def set_slot(self,value):
  if value!=self.place:self.place=value;self.slotChanged.emit()
  self.take()
 def set_role(self,value):
  if value!=self.kind:self.kind=value;self.roleChanged.emit()
  self.take()
 slot=Property(int,lambda self:self.place,set_slot,notify=slotChanged)
 role=Property(str,lambda self:self.kind,set_role,notify=roleChanged)
 shown=Property(bool,lambda self:self.on,notify=shownChanged)
 def take(self):
  """Takes its slot's picture from the page, and whether that slot is the one in front."""
  view=ClassicArt.view
  if view is None:return
  entry=view.scenery[self.place];picture=entry[1 if self.kind=='art' else 2] if entry else None;on=entry is not None and view.front==self.place
  if picture is not self.picture:
   self.picture=picture
   if picture is not None:
    # The frost is a quarter of the art's size and the window enlarges it, smoothly; the art is shown pixel for pixel.
    r=view.ratio;grow=4 if self.kind=='frost' else 1
    self.setTextureSize(QSize(texture_units(picture.width(),r),texture_units(picture.height(),r)));self.setImplicitWidth(picture.width()*grow/r);self.setImplicitHeight(picture.height()*grow/r)
   self.update()
  if on!=self.on:self.on=on;self.shownChanged.emit()
 def paint(self,painter):
  # Copied to the texture as it is, which is the picture's size: Qt's own scale for the window would resample it.
  if self.picture is None:return
  device=painter.device();painter.resetTransform()
  if (device.width(),device.height())==(self.picture.width(),self.picture.height()):painter.drawImage(0,0,self.picture)
  else:painter.drawImage(QRect(0,0,device.width(),device.height()),self.picture)

class ClassicShelf:
 SPEED=15;TURN_STEPS=10;PICTURES=120;QUIET_AFTER=.09;FADE=.28;REST_YAW=math.radians(-5);FADE_LIMIT=3_700_000
 def __init__(self,state,link,animations=lambda:True):
  self.state=state;self.link=link;self.animations=animations;self.frame=None
  # Room on the right of the top row for the window's own buttons, in pixels, while the window has no title bar.
  self.inset=0
  self.surface=None;self.ratio=1.0;self.size=None;self.painted=True;self.presented_at=0
  self.titles=None;self.target=0;self.position=0.0;self.seen=None;self.revision=None
  self.shown=False;self.layout=None;self.last_step=0;self.stale=False
  self.timer=QTimer();self.timer.setSingleShot(True);self.timer.setTimerType(Qt.TimerType.PreciseTimer);self.timer.timeout.connect(self.step)
  self.resize_timer=QTimer();self.resize_timer.setSingleShot(True);self.resize_timer.timeout.connect(self.arrange)
  self.tilt=[self.REST_YAW,0.0];self.tilt_goal=[self.REST_YAW,0.0];self.hover=None;self.paths={};self.moving=OrderedDict();self.buttons={};self.menu_box=None;self.menu_rows=[]
  self.page=None;self.page_key=None;self.fade_from=None;self.fade_at=0;self.under=None;self.clean=None;self.words=None;self.words_key=None;self.words_at=0;self.live=None;self.live_key=None;self.live_fresh=False;self.top=None;self.top_key=None;self.top_hits={};self.foot=None;self.foot_key=None;self.glows={}
  self.ready=OrderedDict();self.wanted=[];self.near=0;self.moved_at=0;self.lock=threading.Lock();self.wake=threading.Event();self.fresh=False
  self.panel_first=0;self.panel_box=None;self.panel_layer=None
  # The art in its two slots, each (what it was drawn from, the art, its frost), and the slot in front.
  self.arts=[];self.scenery=[None,None];self.front=-1;self.scenery_key=None
  # The grid and the list: how far the sheet is scrolled, in rows, where it is going, where the focus's light stands (column and row, as
  # numbers between cells while it glides), the view the layout was made for, and whether the sheet has to be shown again.
  self.scroll=0.0;self.scroll_goal=0.0;self.spot=[0.0,0.0];self.view_key=None;self.band_dirty=False;self.fades={}
  threading.Thread(target=self.work,name='Library pictures',daemon=True).start()

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
   # A whole page, or a game's art, is thousands of tiles' worth of memory.
   for kind in ('page','scenery'):
    pages=[old for old in self.ready if old[0]==kind and old not in keep]
    for old in pages[:max(0,len(pages)-2)]:del self.ready[old]
  return value
 def finished(self,key):
  """Whether the drawing thread is done with this, and what it made: None when the drawing failed."""
  with self.lock:return key in self.ready,self.ready.get(key)
 def peek(self,key):
  with self.lock:return self.ready.get(key)
 def path(self,title):
  if title not in self.paths:self.paths[title]=self.link.icon(title)
  return self.paths[title]
 def art_path(self,title):
  key=('art',title)
  if key not in self.paths:self.paths[key]=self.link.art(title)
  return self.paths[key]
 def when(self,path):
  """When a picture's file last changed, read once for each change of the library: the console can replace an icon or art under the same name, and a drawing made from the old one must not be shown again."""
  key=('when',path)
  if key not in self.paths:
   try:self.paths[key]=path.stat().st_mtime_ns if path else 0
   except OSError:self.paths[key]=0
  return self.paths[key]
 def faces_job(self,game,side):
  title=game['title'];path=self.path(title);name=game['name']
  return ('faces',side,title,path,self.when(path)),lambda:scene.cover_faces(load_icon(path),side,name)
 def tile_job(self,game,side=None,light=scene.SMALL_LIGHT):
  title=game['title'];path=self.path(title);name=game['name'];side=side or self.layout.small
  if light==scene.SMALL_LIGHT:return ('tile',side,title,path,self.when(path)),lambda:scene.flat_tile(load_icon(path),side,name)
  return ('tile',side,light,title,path,self.when(path)),lambda:scene.flat_tile(load_icon(path),side,name,light)
 def choice(self):
  return getattr(self.state,'options',None) or ViewChoice()
 def badge(self,game):
  """What the marks on a game's tile say: (open, PS4, trophy progress or None, platinum), or None with the marks off or nothing to say."""
  if not self.choice().badges:return None
  title=game['title'];key=('trophy',title)
  if key not in self.paths:
   found=getattr(self.link,'trophy_set',None);found=found(title) if found else None
   self.paths[key]=(found['tally']['progress'],bool(found['tally']['platinum'])) if found and found['known'] else (None,False)
  progress,platinum=self.paths[key];marks=(title==self.state.running,title.startswith('CUSA'),progress,platinum)
  return marks if any(mark not in (None,False) for mark in marks) else None
 def trophy_cell(self,title):
  """The list's trophies column for a game: (share 0-1, words, platinum), or None when the PC knows no set for it."""
  key=('tcell',title)
  if key not in self.paths:
   found=getattr(self.link,'trophy_set',None);found=found(title) if found else None;cell=None
   if found and found['known']:
    tally=found['tally'];cell=(1.0 if tally['platinum'] else tally['progress']/100,'Platinum' if tally['platinum'] else f"{tally['earned']} / {tally['total']}  ·  {tally['progress']}%",bool(tally['platinum']))
   elif found:cell=(0.0,f"{found['tally']['total']} trophies",False)
   self.paths[key]=cell
  return self.paths[key]
 def badge_job(self,side,marks):
  return ('badge',side,marks),lambda:scene.tile_badges(side,*marks)
 def grid_name_job(self,game,focused):
  layout=self.layout;width=round(layout.step_x-round(8*layout.unit));name=game['name']
  return ('gname',name,width,layout.name_size,focused),lambda:scene.grid_name(name,width,layout.name_size,focused)
 def list_job(self,game,focused):
  """One game's row in the list, with its details as the page knows them now."""
  layout=self.layout;title=game['title'];path=self.path(title);state=self.state;name=game['name']
  note=game_line(game,state.running,state.waiting) if title in (state.running,state.waiting) else '';cards=game_cards(game);seconds=game.get('seconds')
  played=ago_text(game['played']).capitalize() if seconds and game.get('played') else '—' if seconds else 'Never'
  cells=dict(kind={'PPSA':'PS5 game','CUSA':'PS4 game'}.get(title[:4],'App'),played=played,time=cards[0][1] if seconds else '—',size=cards[1][1])
  trophies=self.trophy_cell(title)
  return ('lrow',layout.row,layout.inner,title,name,note,tuple(sorted(cells.items())),trophies,focused,path,self.when(path)),lambda:scene.list_row(layout,load_icon(path),name,note,cells,trophies,focused)
 def rest_job(self,game):
  faces=self.faces_job(game,self.layout.focus)
  return ('rest',faces[0]),lambda:scene.render_cover(self.made(*faces),self.REST_YAW,0.0,quality=scene.BICUBIC)
 def name_job(self,game):
  layout=self.layout;name=game['name'];return ('name',layout.width,layout.height,name),lambda:scene.name_line(layout,name)
 def page_job(self,game):
  """Everything on the page that stays put for one game, over the art: a clear picture."""
  layout=self.layout;size=(layout.width,layout.height);state=self.state
  if layout.view!='row':
   name,line=(game['name'],game_line(game,state.running,state.waiting)) if game else ('Your games',empty_line(self.link,state.text,state.shelf))
   return ('page',size,self.view_key,name,line),lambda:scene.sheet_layer(layout,name,line)
  if game is None:
   name='Your games';line=empty_line(self.link,state.text,state.shelf);cards=total_cards(self.link.games)
   extra=trophy_total_card(self.link.trophy_totals([game['title'] for game in self.link.games]))
  else:
   name=game['name'];line=game_line(game,state.running,state.waiting);cards=game_cards(game);extra=trophy_card(self.link.trophy_set(game['title']))
  return ('page',size,name,line,cards,extra),lambda:scene.library_layer(layout,name,line,cards,extra)
 def scenery_job(self,game):
  """The game's art for the window to move under the page, and its frost for the glass."""
  # A little larger than the page, in whole units of the window where its scale allows, so that the art lies on the screen's pixels.
  layout=self.layout;r=self.ratio;size=tuple(qt_round(whole_units(math.ceil(side/r*scene.SCENERY_ROOM),r)*r) for side in (layout.width,layout.height))
  art=cover=None
  if game is not None:art=self.art_path(game['title']);cover=self.path(game['title'])
  def make():
   picture=scene.scenery(load_picture(art,size),load_icon(cover),size);return (picture.size,qt_picture(picture),qt_picture(scene.frost(picture)))
  return ('scenery',size,art,self.when(art),cover,self.when(cover)),make
 def live_job(self):
  layout=self.layout;state=self.state;info=state.info;fps=info.get('fps');stream=(min(1,fps/60) if fps else 0,str(round(fps)) if fps else '—',info.get('picture') or 'No picture yet',info.get('bitrate') or '—')
  open_name=self.link.game_name(state.running) if state.running else 'No game open';cpu,soc=info.get('cpu'),info.get('soc')
  console=('Console',f'CPU {cpu}°' if cpu else 'Not connected' if not self.link.online else '—','  ·  '.join(part for part in (f'SoC {soc}°' if soc else '',open_name) if part))
  return ('live',layout.width,layout.height,stream,console),lambda:scene.live_cards(layout,stream,console)
 def plan(self):
  """Tells the drawing thread what the page needs next, nearest first. Every tile in view comes before any page: a tile takes about
  6 ms and a page 100 to 250 ms, and the far tiles used to wait behind three pages and stay blank while the row moved."""
  if self.layout is None or not self.shown:return
  if self.layout.view!='row':self.plan_sheet();return
  layout=self.layout;games=self.state.games;target=self.target;focus=self.focused();near=[];later=[self.page_job(focus),self.scenery_job(focus),self.live_job()]
  if focus:near+=[self.rest_job(focus),self.name_job(focus),self.faces_job(focus,layout.half)]
  across=(layout.width-layout.margin)//(layout.small+layout.gap)+3
  for reach in range(1,across+1):
   for index in (target+reach,target-reach if reach<4 else -1):
    if 0<=index<len(games):
     game=games[index];near.append(self.tile_job(game))
     if reach==1:near+=[self.faces_job(game,layout.half),self.name_job(game)];later+=[self.rest_job(game),self.page_job(game),self.scenery_job(game)]
  # Once the row is still, the tiles a screen further each way, so a run along the row finds them drawn.
  for reach in range(across+1,2*across+1):
   for index in (target+reach,target-reach):
    if 0<=index<len(games):later.append(self.tile_job(games[index]))
  for index in range(max(0,target-across),min(len(games),target+across+1)):
   marks=self.badge(games[index]) if index!=target else None
   if marks:later.insert(0,self.badge_job(layout.small,marks))
  with self.lock:self.wanted=near+later;self.near=len(near)
  self.wake.set();self.schedule()
 def plan_sheet(self):
  """The same for the grid and the list: the games in sight, nearest the focus first, then the page, then the games a screen further."""
  layout=self.layout;games=self.state.games;target=self.target;focus=self.focused();grid=layout.view=='grid';near=[];later=[self.page_job(focus),self.scenery_job(focus)]
  shown=library_view.in_sight(layout,len(games),self.scroll_goal);columns=layout.columns
  def distance(index):return max(abs(index%columns-target%columns),abs(index//columns-target//columns)) if grid else abs(index-target)
  around=sorted(set(shown)|{index for index in (target-1,target+1,target-columns,target+columns) if 0<=index<len(games)},key=distance)
  if focus and grid:near.append(self.faces_job(focus,layout.lift_side))
  for index in around:
   game=games[index]
   if grid:
    near.append(self.tile_job(game,layout.side));near.append(self.tile_job(game,layout.side,1.0))
    if self.choice().names:near+=[self.grid_name_job(game,False),self.grid_name_job(game,True)] if distance(index)<=1 else [self.grid_name_job(game,False)]
    marks=self.badge(game)
    if marks:near.append(self.badge_job(layout.side,marks))
   else:near+=[self.list_job(game,False)]+([self.list_job(game,True)] if distance(index)<=1 else [])
  # The pages and the art of the games one step away, as the row draws them for its neighbours.
  steps=(1,columns) if grid else (1,)
  later+=[job(games[index]) for change in steps for index in (target+change,target-change) if 0<=index<len(games) for job in (self.page_job,self.scenery_job)] if focus else []
  rows=layout.rows_shown*columns;low=max(0,shown.start-rows) if shown else 0;high=min(len(games),(shown.stop if shown else 0)+rows)
  for index in [*range(shown.stop if shown else 0,high),*range(low,shown.start if shown else 0)]:
   later.append(self.tile_job(games[index],layout.side) if grid else self.list_job(games[index],False))
  with self.lock:self.wanted=near+later;self.near=len(near)
  self.wake.set();self.schedule()

 # What the shell calls.
 def show(self,on):
  if on==self.shown:return
  # While the page shows with no game open, the link reads the art, music and trophies it is still missing.
  self.shown=on;self.link.browsing=on
  if on:
   self.seen=None;self.layout=None;self.refresh();self.arrange()
  else:
   self.timer.stop();self.hover=None
   if self.state.menu:self.state.menu=None
   self.state.panel=None
 def focused(self):
  games=self.state.games;return games[self.target] if 0<=self.target<len(games) else None
 def refresh(self):
  """After anything on the shelf may have changed. Only what changed is drawn again: a new focus moves the row, anything else redraws the page."""
  state=self.state;now=time.perf_counter()
  if self.revision!=self.link.revision:self.revision=self.link.revision;self.paths.clear()
  titles=tuple(game['title'] for game in state.games)
  if titles!=self.titles:
   self.titles=titles;self.target=state.target;self.position=float(state.target);self.stale=True
   if self.layout is not None and self.layout.view!='row':self.place_focus()
  elif state.target!=self.target:self.target=state.target;self.moved_at=now
  menu=state.menu;info=state.info;panel=state.panel
  seen=(state.running,state.waiting,state.line,state.notice,state.shelf,state.text,state.searching,state.exit_label,time.strftime('%H:%M'),tuple(info.get(key) for key in ('name','state','pad')),
   (menu['kind'],menu['selected'],tuple(menu['items'])) if menu else None,self.link.online,(panel['title'],panel['selected'],self.link.revision) if panel else None)
  if seen!=self.seen:self.seen=seen;self.stale=True
  self.plan();self.schedule()
 def resize(self,width,height,ratio):
  """The page's size on screen, in the window's units, and how many of the screen's pixels each holds."""
  self.ratio=max(.5,float(ratio) or 1.0);size=(max(1,qt_round(float(width)*self.ratio)),max(1,qt_round(float(height)*self.ratio)))
  if size!=self.size:self.size=size;self.resize_timer.start(50)
 def action_text(self):return self.state.action_text()

 # The pointer, in the window's units.
 def pointer_at(self,x,y):
  """Follows the pointer. True when it is over something to click."""
  x*=self.ratio;y*=self.ratio;hit=self.hit_at(x,y)
  if hit!=self.hover:
   # Only the bars and buttons look different under the pointer.
   if (self.hover or ('tile',))[0]!='tile' or (hit or ('tile',))[0]!='tile':self.stale=True
   if hit and hit[0]=='menu' and self.state.menu:self.state.menu['selected']=hit[1]
   self.hover=hit;self.schedule()
  layout=self.layout
  if layout and layout.view!='row' and hit!=self.hover_seen:self.hover_seen=hit;self.band_dirty=True;self.schedule()
  if layout and self.animations() and layout.view!='list':
   if layout.view=='grid':cx,cy=library_view.cell(layout,self.target,self.scroll);side=layout.lift_side;rest=0.0
   else:cx,cy,side,_=scene.tile_pose(0,layout);rest=self.REST_YAW
   across=(x-cx)/side;down=(y-cy)/side
   goal=[rest*.4-across*math.radians(24),down*math.radians(16)] if abs(across)<=.8 and abs(down)<=.8 else [rest,0.0]
   if goal!=self.tilt_goal:self.tilt_goal=goal;self.schedule()
  return bool(hit) and hit[0] not in ('away','panel')
 hover_seen=None
 def rest_yaw(self):return 0.0 if self.layout is not None and self.layout.view=='grid' else self.REST_YAW
 def lean(self,x,y):
  """The right stick tilts the focused tile as the pointer does over it, x and y from -1 to 1."""
  if self.layout is None or not self.animations() or self.layout.view=='list':return
  rest=self.rest_yaw();goal=[rest*.4-x*.8*math.radians(24),y*.8*math.radians(16)] if x or y else [rest,0.0]
  if goal!=self.tilt_goal:self.tilt_goal=goal;self.schedule()
 def pointer_left(self):
  self.tilt_goal=[self.rest_yaw(),0.0]
  if self.hover_seen:self.hover_seen=None;self.band_dirty=True
  if self.hover:self.hover=None;self.stale=True
  self.schedule();return False
 def released(self,x,y):
  """What a click there does: ('menu', row), ('panel', trophy), ('away', 0), ('tile', index), ('action', 0), ('more', 0), ('top', key) or None."""
  return self.hit_at(x*self.ratio,y*self.ratio)
 def visible(self):
  """The tiles that can be on screen, nearest the ends first for drawing."""
  layout=self.layout
  if layout.view!='row':return library_view.in_sight(layout,len(self.state.games),self.scroll)
  step=layout.small+layout.gap
  low=max(0,math.floor(self.position-(layout.margin+layout.small)/step)-1);high=min(len(self.state.games)-1,math.ceil(self.position+(layout.width-layout.margin-layout.focus)/step)+1)
  return range(low,high+1)
 def hit_at(self,x,y):
  layout=self.layout
  if layout is None:return None
  if self.state.menu:
   box=self.menu_box
   if box and box[0]<=x<box[2] and box[1]<=y<box[3]:
    for index,(top,bottom) in enumerate(self.menu_rows):
     if top<=y-box[1]<bottom:return ('menu',index)
   return ('away',0)
  if self.state.panel:
   box=self.panel_box
   if box and box[0]<=x<box[2] and box[1]<=y<box[3]:
    fit,top,row=scene.trophy_fit(layout);index=self.panel_first+int((y-top)//row) if y>=top else -1
    found=self.link.trophy_set(self.state.panel['title']);count=len(found['trophies']) if found else 0
    # Off the rows (the heading, the edges) is None: on the list, but no trophy.
    return ('panel',index if 0<=index<count and index<self.panel_first+fit else None)
   return ('away',0)
  for key,(x0,y0,x1,y1) in self.top_hits.items():
   if x0<=x<x1 and y0<=y<y1:return ('top',key)
  if layout.pill_y<=y<layout.pill_y+layout.pill:
   if layout.pill_x<=x<layout.pill_x+layout.pill_width and self.action_text():return ('action',0)
   if layout.option_x<=x<layout.option_x+layout.pill and self.focused():return ('more',0)
  if layout.view!='row':
   index=library_view.hit(layout,x,y,len(self.state.games),self.scroll);return ('tile',index) if index is not None else None
  if layout.row_y<=y<layout.row_y+layout.focus and self.state.games:
   for index in self.visible():
    cx,cy,side,_=scene.tile_pose(index-self.position,layout)
    if abs(x-cx)<=side/2 and abs(y-cy)<=side/2:return ('tile',index)
  return None

 # Putting the page on screen.
 def present(self,picture,x,y):
  """Copies a finished part of the page onto the picture the screen shows, and asks for only that part to be shown again."""
  if self.surface is None:return
  if picture.mode!='RGBA':picture=picture.convert('RGBA')
  # The part takes the place of what was there, clear parts included.
  data=picture.tobytes();part=QImage(data,picture.width,picture.height,picture.width*4,QImage.Format.Format_RGBA8888)
  painter=QPainter(self.surface);painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source);painter.drawImage(x,y,part);painter.end()
  self.painted=False;self.presented_at=time.perf_counter()
  if self.frame is not None:
   r=self.ratio;left=math.floor(x/r);top=math.floor(y/r)
   self.frame.update(QRect(left,top,math.ceil((x+picture.width)/r)-left+1,math.ceil((y+picture.height)/r)-top+1))
 def paint_into(self,painter,frame):
  # Called by the render thread while this thread waits, so the picture never changes under it.
  # The texture has the screen's pixels: the picture is copied to it untouched. Painted at the window's scale, it was enlarged into a
  # texture 1.25 times too big and shrunk again on a screen scaled to 125%, which softened it.
  self.painted=True
  if self.surface is not None:painter.resetTransform();painter.drawImage(0,0,self.surface)
 def arrange(self):
  if self.size is None or not self.shown:return
  width,height=self.size;choice=self.choice()
  if min(width,height)<120:return
  same=self.layout is not None and (self.layout.width,self.layout.height)==(width,height)
  if same and choice.key()==self.view_key:self.show_all();return
  changed=same and self.under is not None and self.page_key is not None
  self.page=self.under.resize((width,height),scene.BILINEAR) if self.under is not None else Image.new('RGBA',(width,height))
  self.surface=QImage(width,height,QImage.Format.Format_ARGB32_Premultiplied);self.surface.fill(Qt.GlobalColor.transparent)
  if self.frame is not None:self.frame.setTextureSize(QSize(texture_units(width,self.ratio),texture_units(height,self.ratio)))
  self.present(self.page,0,0)
  self.view_key=choice.key();self.layout=library_view.arranged(scene.page_layout(width,height,library_view.ROW_SCALE[choice.size]),choice)
  self.moving.clear();self.page_key=None;self.fade_from=None;self.under=None;self.words=None;self.words_key=None;self.live=None;self.live_key=None;self.top_key=None;self.foot_key=None;self.buttons.clear();self.glows.clear();self.panel_layer=None;self.stale=True
  # The shelf moves through the grid by its columns and pages by the rows in sight.
  self.state.columns=getattr(self.layout,'columns',1);self.state.page_rows=getattr(self.layout,'rows_shown',5)
  self.place_focus();self.fades.clear();self.hover_seen=None
  # The last view fades into the new one, as a new game's page does.
  if changed:self.page_key=('changed',)
  self.plan();self.schedule()
 def relayout(self):
  """After the view or the tile size changed."""
  if self.shown:self.arrange()
 def place_focus(self):
  """Puts the sheet's scroll and the focus's light on the focused game at once, with the tilt at rest."""
  layout=self.layout;self.tilt=[self.rest_yaw(),0.0];self.tilt_goal=list(self.tilt)
  if layout is None or layout.view=='row':return
  count=len(self.state.games);target=max(0,self.target);columns=layout.columns
  self.spot=[float(target%columns),float(target//columns)];self.scroll=self.scroll_goal=float(library_view.first_row(layout,target//columns,0,count))
 def schedule(self,delay=1):
  if not self.timer.isActive() and self.shown:self.last_step=self.last_step or time.perf_counter();self.timer.start(delay)
 def step(self):
  if not self.shown or self.layout is None:return
  now=time.perf_counter()
  # No new picture before the screen has taken the last one: drawing faster than the screen shows only costs time.
  if not self.painted and now-self.presented_at<.05:self.timer.start(2);return
  passed=min(.05,now-self.last_step);self.last_step=now;moving=False;smooth=self.animations()
  gap=self.target-self.position
  if self.layout.view!='row':
   moving=self.glide(passed,smooth,now)
   if gap:self.position=float(self.target)
  elif gap:
   self.moved_at=now;self.position=float(self.target) if not smooth or abs(gap)<.004 else self.position+gap*(1-math.exp(-passed*self.SPEED));moving=True
  if not moving and self.tilt!=self.tilt_goal:
   for part in (0,1):
    gap=self.tilt_goal[part]-self.tilt[part];self.tilt[part]=self.tilt_goal[part] if not smooth or abs(gap)<.003 else self.tilt[part]+gap*(1-math.exp(-passed*11))
   moving=True
  fresh,self.fresh=self.fresh,False;self.adopt(now)
  fading=self.fade_from is not None;naming=now-self.words_at<.16;waiting=bool(self.state.waiting);dirty,self.band_dirty=self.band_dirty,False
  if fading or self.stale or self.under is None:self.stale=False;self.live_fresh=False;self.paint(now)
  # The trophy list lies over the live cards, so with it open they cannot be shown alone.
  elif self.live_fresh and self.layout.view=='row':self.paint(now) if self.state.panel else self.paint_live()
  # A menu lies over the row, and in the grid and the list the trophy list lies over the sheet, so with one open the row cannot be shown alone.
  elif moving or fresh or naming or waiting or dirty:self.paint(now) if self.state.menu or self.state.panel and self.layout.view!='row' else self.paint_row()
  with self.lock:pending=any(job[0] not in self.ready for job in self.wanted)
  if moving or fading or naming or fresh:self.schedule(4)
  elif waiting:self.schedule(80)
  elif pending or now-self.moved_at<self.QUIET_AFTER:self.schedule(30)
 def adopt(self,now):
  """Starts showing what the drawing thread has finished. The page changes only once the row has come to rest, so a run along the row does not fade through every game on the way."""
  focus=self.focused();row=self.layout.view=='row'
  if row:
   key=self.name_job(focus)[0] if focus else None;words=self.peek(key) if key else None
   if key!=self.words_key and (words is not None or key is None):self.words=words;self.words_key=key;self.words_at=now if self.animations() else 0
   key=self.live_job()[0];live=self.peek(key)
   if live is not None and key!=self.live_key:self.live=live;self.live_key=key;self.live_fresh=True
  if now-self.moved_at<self.QUIET_AFTER:return
  # The words and the art change together, once both are drawn: the window fades its art as long as this fades the words.
  key=self.page_job(focus)[0];art_key=self.scenery_job(focus)[0]
  if key==self.page_key and art_key==self.scenery_key:return
  (page_done,page),(art_done,art)=self.finished(key),self.finished(art_key)
  if not (page_done and art_done):return
  if page is not None and key!=self.page_key:
   self.fade_from=self.page if self.page_key is not None and self.animations() and page.width*page.height<=self.FADE_LIMIT else None;self.fade_at=now;self.page=page;self.page_key=key;self.stale=True
  if art_key!=self.scenery_key:self.scenery_key=art_key;self.put_scenery((art_key,art[1],art[2]) if art else None)
 def put_scenery(self,entry):
  """The new art goes in the slot behind, which then comes to the front: the window fades it in over the last one."""
  back=1-self.front if self.front in (0,1) else 0;self.scenery[back]=entry;self.front=back if entry else -1
  for item in list(self.arts):
   try:item.take()
   except RuntimeError:self.arts.remove(item)
 def show_all(self):
  if self.under is not None and self.shown:self.present(self.under,0,0)
 def tile_picture(self,game,offset):
  """A tile's picture where it is: flat in the row, in 3D in the focus, following the pointer, and swinging on its axis on the way between the two. The swing is drawn small and enlarged, since nobody can see the detail while it moves."""
  layout=self.layout;title=game['title'];path=self.path(title);reach=abs(offset);changed=self.when(path);faces_key=('faces',layout.focus,title,path,changed)
  if reach>=.995:
   picture=self.peek(('tile',layout.small,title,path,changed));return (picture,-(layout.small//2),-(layout.small//2)) if picture is not None else None
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
   faces=self.peek(('faces',layout.half,title,path,changed))
   if faces is None:return rest
   share=step/self.TURN_STEPS;sprite,left,top=scene.render_cover(faces,scene.turn_of(sign*share)+self.REST_YAW*(1-share),0.0,1-share);scale=scene.tile_pose(share,layout)[2]/faces['side']
   sprite=scene.dimmed(sprite.resize((round(sprite.width*scale),round(sprite.height*scale)),scene.BILINEAR),1-(1-scene.SMALL_LIGHT)*share);picture=(sprite,round(left*scale),round(top*scale));self.remember(key,picture)
  return picture
 def remember(self,key,picture):
  self.moving[key]=picture
  if len(self.moving)>160:self.moving.popitem(last=False)
 def glow(self,reach,side=None):
  """The light around the focused tile, fading as it leaves."""
  step=round((1-reach)*8);side=side or self.layout.focus;key=(side,step)
  if key not in self.glows:
   light=scene.focus_glow(side).copy();light.putalpha(light.getchannel('A').point([value*step//8 for value in range(256)]));self.glows[key]=light
  return self.glows[key]
 def draw_row(self,band):
  """The tiles and the focused game's name on a copy of the row's band."""
  layout=self.layout;top=layout.band_y;games=self.state.games
  if layout.view=='grid':self.draw_grid(band);return
  if layout.view=='list':self.draw_list(band);return
  if games:
   for index in sorted(self.visible(),key=lambda index:-abs(index-self.position)):
    offset=index-self.position;cx,cy,side,reach=scene.tile_pose(offset,layout);picture=self.tile_picture(games[index],offset)
    if picture is None:continue
    if reach<1:
     light=self.glow(reach);lay(band,light,round(cx-light.width/2),round(cy-light.height/2)-top)
    sprite,left,up=picture;lay(band,sprite,round(cx)+left,round(cy)+up-top)
    marks=self.badge(games[index]) if reach>=.995 else None
    picture=self.peek(self.badge_job(layout.small,marks)[0]) if marks else None
    if picture is not None:lay(band,picture,round(cx)-layout.small//2,round(cy)-layout.small//2-top)
  if self.words is not None:
   sprite,x,y=self.words;share=(time.perf_counter()-self.words_at)/.16
   if share<1:sprite=sprite.copy();sprite.putalpha(sprite.getchannel('A').point([int(value*max(0,share)) for value in range(256)]))
   lay(band,sprite,x,y-top)
 # The grid and the list.
 def glide(self,passed,smooth,now):
  """Moves the focus's light and the sheet's scroll toward the focused game. True while anything moved."""
  layout=self.layout;count=len(self.state.games);target=max(0,min(self.target,count-1)) if count else 0;columns=layout.columns
  goal=[float(target%columns),float(target//columns)] if layout.view=='grid' else [0.0,float(target)]
  self.scroll_goal=float(library_view.first_row(layout,target//columns if layout.view=='grid' else target,round(self.scroll_goal),count))
  moved=False;share=1-math.exp(-passed*self.SPEED*1.15)
  for part in (0,1):
   gap=goal[part]-self.spot[part]
   if gap:self.spot[part]=goal[part] if not smooth or abs(gap)<.004 else self.spot[part]+gap*share;moved=True
  gap=self.scroll_goal-self.scroll
  if gap:self.scroll=self.scroll_goal if not smooth or abs(gap)<.004 else self.scroll+gap*(1-math.exp(-passed*self.SPEED*.8));moved=True
  if moved:self.moved_at=now;self.plan_sheet() if abs(gap)>.004 else None
  return moved
 def edge_fade(self,size):
  """The sheet's edges, where a row scrolling out of sight fades away: an alpha ramp the size of the band."""
  if size not in self.fades:
   # The list's rows go out of sight under its column captions; the grid's in the sheet's own margin.
   layout=self.layout;unit=layout.unit;height=size[1];bottom=layout.inner[3]-layout.band_y
   start,end=(layout.rows_top-round(6*unit)-layout.band_y,layout.rows_top-layout.band_y) if layout.view=='list' else (0,layout.inner[1]-layout.band_y)
   ramp=Image.new('L',(1,height))
   ramp.putdata([round(255*max(0.0,min(1.0,(y-start)/max(1,end-start),(height-y)/max(1,height-bottom)))) for y in range(height)])
   self.fades[size]=ramp.resize(size,scene.BILINEAR)
  return self.fades[size]
 def lift_picture(self,game,lift,hovering):
  """A grid tile on its way up to the focus or down from it: as large and as bright as its share of the way."""
  layout=self.layout;side=layout.side
  if lift<=.02:
   picture=self.peek(self.tile_job(game,side,1.0 if hovering else scene.SMALL_LIGHT)[0]) or self.peek(self.tile_job(game,side)[0])
   return (picture,-(side//2),-(side//2)) if picture is not None else None
  title=game['title'];path=self.path(title);faces=self.peek(('faces',layout.lift_side,title,path,self.when(path)))
  if lift>=.98 and faces is not None:
   yaw=round(math.degrees(self.tilt[0]));pitch=round(math.degrees(self.tilt[1]))
   if (yaw,pitch)==(0,0):return faces['ringed'],-(faces['side']//2)-scene.FACE_MARGIN,-(faces['side']//2)-scene.FACE_MARGIN
   key=('tilt',layout.lift_side,title,path,yaw,pitch);picture=self.moving.get(key)
   if picture is None:picture=scene.render_cover(faces,math.radians(yaw),math.radians(pitch));self.remember(key,picture)
   return picture
  step=max(1,min(8,round(lift*8)));key=('lift',side,title,path,step);picture=self.moving.get(key)
  if picture is None:
   bright=self.peek(self.tile_job(game,side,1.0)[0])
   if bright is None:return None
   share=step/8;grown=round(side+(layout.lift_side-side)*share);sprite=bright.resize((grown,grown),scene.BICUBIC)
   sprite=scene.dimmed(sprite,scene.SMALL_LIGHT+(1-scene.SMALL_LIGHT)*share) if share<1 else sprite;picture=(sprite,-(grown//2),-(grown//2));self.remember(key,picture)
  return picture
 def draw_grid(self,band):
  """The grid's tiles on a copy of the sheet's band: the focused one larger, lit and leaning with the pointer, the light gliding from game
  to game; the names under the tiles and the marks on them; the rows that scroll out of sight fading at the sheet's edges."""
  layout=self.layout;top=layout.band_y;games=self.state.games;columns=layout.columns;sx,sy=self.spot;hover=self.hover_seen[1] if self.hover_seen and self.hover_seen[0]=='tile' else None
  content=Image.new('RGBA',band.size);choice=self.choice();shown=self.visible()
  def lift_of(index):
   reach=max(abs(index%columns-sx),abs(index//columns-sy));share=max(0.0,1-reach);return share*share*(3-2*share)
  for index in sorted(shown,key=lift_of):
   game=games[index];lift=lift_of(index);cx,cy=library_view.cell(layout,index,self.scroll);picture=self.lift_picture(game,lift,index==hover)
   if lift>.02:
    light=self.glow(1-lift,layout.lift_side);lay(content,light,round(cx-light.width/2),round(cy-light.height/2)-top)
   if picture is not None:sprite,left,up=picture;lay(content,sprite,round(cx)+left,round(cy)+up-top)
   grown=layout.side+(layout.lift_side-layout.side)*lift
   marks=self.badge(game) if lift<.98 else None
   badge=self.peek(self.badge_job(layout.side,marks)[0]) if marks else None
   if badge is not None:lay(content,badge,round(cx-layout.side/2),round(cy-layout.side/2)-top)
   if choice.names:
    name=self.peek(self.grid_name_job(game,lift>.5)[0]) or self.peek(self.grid_name_job(game,False)[0])
    if name is not None:lay(content,name,round(cx-name.width/2),round(cy+grown/2+layout.name_room/2-name.height/2)-top)
  content.putalpha(ImageChops.multiply(content.getchannel('A'),self.edge_fade(content.size)));band.alpha_composite(content);self.scroll_bar(band)
 def draw_list(self,band):
  """The list's rows on a copy of the sheet's band, the light under the focused row gliding from row to row."""
  layout=self.layout;top=layout.band_y;games=self.state.games;x0=layout.inner[0];width=layout.inner[2]-x0;content=Image.new('RGBA',band.size)
  hover=self.hover_seen[1] if self.hover_seen and self.hover_seen[0]=='tile' else None
  if games:
   if hover is not None and hover!=self.target:
    faint=self.faint_bar(width,layout.row);lay(content,faint,x0,round(layout.rows_top+(hover-self.scroll)*layout.row)-top)
   light=scene.list_focus(width,layout.row,round(layout.unit,3));lay(content,light,x0,round(layout.rows_top+(self.spot[1]-self.scroll)*layout.row)-top)
   for index in self.visible():
    game=games[index];focused=abs(index-self.spot[1])<.5
    picture=self.peek(self.list_job(game,focused)[0]) or self.peek(self.list_job(game,not focused)[0])
    if picture is not None:lay(content,picture,x0,round(layout.rows_top+(index-self.scroll)*layout.row)-top)
  content.putalpha(ImageChops.multiply(content.getchannel('A'),self.edge_fade(content.size)));band.alpha_composite(content);self.scroll_bar(band)
 def scroll_bar(self,band):
  """A slim bar at the sheet's right edge while more rows are out of sight than in it: where the sheet is, and how much of it shows."""
  layout=self.layout;total=library_view.rows_total(layout,len(self.state.games));shown=layout.rows_shown
  if total<=shown:return
  unit=layout.unit;width=max(3,round(4*unit));x=layout.sheet[2]-round(11*unit)-width
  top=(layout.rows_top if layout.view=='list' else layout.inner[1])-layout.band_y;span=layout.inner[3]-layout.band_y-top
  thumb=max(width*4,round(span*shown/total));at=round((span-thumb)*max(0.0,min(1.0,self.scroll/(total-shown))))
  key=('scroll',width,span,thumb,at)
  if key not in self.glows:
   for old in [old for old in self.glows if old[0]=='scroll']:del self.glows[old]
   self.glows[key]=scene.coloured((width,span),[((255,255,255,26),lambda d:d.rounded_rectangle((0,0,width-1,span-1),width/2,fill=255)),((255,255,255,150),lambda d:d.rounded_rectangle((0,at,width-1,at+thumb-1),width/2,fill=255))])
  lay(band,self.glows[key],x,top)
 def faint_bar(self,width,height):
  key=('faint',width,height)
  if key not in self.glows:
   unit=self.layout.unit;self.glows[key]=scene.coloured((width,height),[((255,255,255,16),lambda d:d.rounded_rectangle((0,0,width-1,height-1),round(12*unit),fill=255))])
  return self.glows[key]
 def paint_row(self):
  layout=self.layout;band=self.clean.copy();self.draw_row(band);self.under.paste(band,(0,layout.band_y));self.present(band,0,layout.band_y)
 def paint(self,now):
  """The whole page over the art: the words and cards, the bars, then the row."""
  layout=self.layout;frame=self.page.copy()
  if self.fade_from is not None:
   share=(now-self.fade_at)/self.FADE
   if share>=1 or self.fade_from.size!=frame.size:self.fade_from=None
   else:frame=Image.blend(self.fade_from,frame,share*share*(3-2*share))
  if self.live is not None and layout.view=='row':lay(frame,self.live,layout.cards[2][0],layout.cards_y)
  for picture,(x,y) in self.overlays(now):lay(frame,picture,x,y)
  self.clean=frame.crop((0,layout.band_y,layout.width,layout.band_y+layout.band_height));band=self.clean.copy();self.draw_row(band);frame.paste(band,(0,layout.band_y))
  self.panel_box=None
  if self.state.panel:self.trophy_list(frame)
  if self.state.menu:
   picture,(x,y)=self.menu_picture();lay(frame,picture,x,y)
  else:self.menu_box=None;self.menu_rows=[]
  self.under=frame;self.present(frame,0,0);self.show_glass()
 def show_glass(self):
  """Tells the window where the glass is, in its own units, for the frosted art to show there."""
  if self.frame is None or self.layout is None:return
  layout=self.layout;extra=self.page_key[5] if self.page_key and len(self.page_key)>5 else None
  boxes=scene.glass_boxes(layout,extra) if layout.view=='row' else [(layout.sheet,layout.sheet_radius)]
  if self.panel_box:boxes.append((self.panel_box,round(18*layout.unit)))
  r=self.ratio;self.frame.set_glass([dict(x=x0/r,y=y0/r,w=(x1-x0)/r,h=(y1-y0)/r,r=radius/r) for (x0,y0,x1,y1),radius in boxes])
 def trophy_list(self,frame):
  """The open trophy list, scrolled so that the chosen trophy shows."""
  layout=self.layout;panel=self.state.panel;found=self.link.trophy_set(panel['title'])
  if found is None:self.state.panel=None;return
  title,line,rows=trophy_rows(found);fit=scene.trophy_fit(layout)[0];selected=max(0,min(len(rows)-1,panel['selected']))
  if selected<self.panel_first:self.panel_first=selected
  elif selected>=self.panel_first+fit:self.panel_first=selected-fit+1
  self.panel_first=max(0,min(self.panel_first,max(0,len(rows)-fit)))
  # It takes the place of the page under it, whose words would show through its glass.
  key=(title,line,tuple(rows),selected,self.panel_first,layout.width,layout.height)
  if self.panel_layer is None or self.panel_layer[0]!=key:self.panel_layer=(key,*scene.trophy_layer(layout,title,line,rows,selected,self.panel_first))
  box=scene.trophy_box(layout);frame.paste(self.panel_layer[1],box[:2],self.panel_layer[2]);self.panel_box=box
 def paint_live(self):
  """Only the two cards whose readings change while the page stands still."""
  layout=self.layout;self.live_fresh=False;x,y=layout.cards[2][0],layout.cards_y;part=self.page.crop((x,y,x+self.live.width,y+self.live.height));lay(part,self.live,0,0);self.under.paste(part,(x,y));self.present(part,x,y)
 def overlays(self,now):
  layout=self.layout;parts=[(self.top_picture(),(0,layout.bar_y)),(self.foot_picture(),(0,layout.hints_y))];text=self.action_text()
  if text:parts.append((self.action_picture(text,now),(layout.pill_x,layout.pill_y)))
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
  layout=self.layout;menu=self.state.menu;picture,rows=scene.drop_menu(menu['items'],menu['selected'],layout.unit)
  if menu['kind']=='power':x=layout.width-layout.margin-self.inset-picture.width;y=layout.bar_y+layout.bar+round(10*layout.unit)
  elif menu['kind'] in ('view','psn'):
   button=self.top_hits.get(menu['kind']);x=(button[2] if button else layout.width-layout.margin-self.inset)-picture.width;y=layout.bar_y+layout.bar+round(10*layout.unit)
  # In the grid and the list the buttons stand at the top, so their menu opens under them.
  elif layout.view!='row':x=layout.option_x+layout.pill-picture.width;y=layout.pill_y+layout.pill+round(10*layout.unit)
  else:x=layout.option_x;y=layout.pill_y-picture.height-round(10*layout.unit)
  self.menu_box=(x,y,x+picture.width,y+picture.height);self.menu_rows=rows;return picture,(x,y)
 def top_picture(self):
  layout=self.layout;state=self.state;info=state.info;hover=self.hover[1] if self.hover and self.hover[0]=='top' else None
  values=dict(status=status_text(info),online=info.get('state')=='online',clock=time.strftime('%H:%M'),shelf=SHELF_NAMES.get(state.shelf,'All games'),pad=bool(info.get('pad')),hover=hover,search=state.text,searching=state.searching,inset=self.inset,
   views=True,viewing=bool(state.menu and state.menu['kind']=='view'),tabs=(('games','Games'),('live','Live'),('media','Media'),('friends','Friends'),('trophies','Trophies'),('stats','Stats'),('files','Files')),unread=getattr(state,'unread',0),
   psn=getattr(state,'psn',None));key=tuple(sorted(values.items()))
  if key!=self.top_key:self.top_key=key;self.top,self.top_hits=scene.top_bar(layout,values)
  return self.top
 def foot_picture(self):
  state=self.state;action=self.action_text();action=action if action in ('Resume','Connect','Open') else 'Play';key=(bool(state.info.get('pad')),state.line,state.notice,action,bool(state.panel))
  if key!=self.foot_key:
   hints=(LIST_PAD_HINTS if key[0] else LIST_KEY_HINTS) if key[4] else (PAD_HINTS if key[0] else library_view.hints(self.layout.view,KEY_HINTS))
   self.foot_key=key;self.foot=scene.hint_bar(self.layout,tuple((mark,label.format(action=action)) for mark,label in hints),state.notice or state.line,bool(state.notice))
  return self.foot
