"""What the Qt pages show, worked out without Qt so that it can be tested: the Games shelf, the line at the bottom of the window
and the session panel's readings. The Qt window only draws what these give it."""
import time
from datetime import datetime
from pathlib import Path
from console_control import console_line,degrees as console_degrees
from desktop_features import clock_text,format_bytes
from game_mode import HIDDEN_SHELF,SHELVES,empty_line,game_cards,game_line,power_items,shelf_games,total_cards
import library_view,live_broadcast

SHELF_NAMES=dict(SHELVES+(HIDDEN_SHELF,))
PAGES=('games','live','media','friends','trophies','stats','files')

def file_url(path):
 """A picture for Qt Quick. The time the file last changed goes with it, so a file the console replaced under the same name is read again."""
 if not path:return ''
 path=Path(path)
 try:changed=path.stat().st_mtime_ns
 except OSError:return ''
 return path.resolve().as_uri()+f'?v={changed}'

def game_kind(title):
 return {'PPSA':'PS5 game','CUSA':'PS4 game'}.get(title[:4],'App')

class Shelf:
 """The Games page without its pictures: which games show, the one in focus, the menu and the search.
 actions: name -> command, as in the Tk page. cue(name) plays a sound."""
 MUSIC_AFTER=.9
 def __init__(self,link,actions,cue=lambda name:None,clock=time.perf_counter):
  self.link=link;self.actions=actions;self.cue=cue;self.clock=clock
  self.shelf='all';self.text='';self.searching=False;self.games=[];self.target=0;self.menu=None
  self.running='';self.waiting=None;self.line='';self.notice='';self.info={};self.exit_label='';self.revision=None
  self.settle_at=None;self.tiles_version=0
  # The trophy list over the page: {title, selected}, or None.
  self.panel=None
  # How the page lays out the games, and the grid's columns and the rows in sight, which the page sets once it knows its size.
  self.options=library_view.ViewChoice();self.columns=1;self.page_rows=5
 def focused(self):
  return self.games[self.target] if 0<=self.target<len(self.games) else None
 def sync(self,running,waiting,line,notice=''):
  """A few times a second. True when the shelf's games changed and the tiles have to be read again."""
  self.running,self.waiting,self.line,self.notice=running,waiting,line,notice
  if self.revision!=self.link.revision:
   self.revision=self.link.revision;self.refilter();return True
  return False
 def refilter(self):
  game=self.focused();title=game['title'] if game else None;hidden=self.hidden()
  if self.shelf=='hidden' and not hidden or self.shelf not in self.shelf_keys():self.shelf='all'
  games=shelf_games(self.link.games,self.shelf,self.text,hidden)
  self.games=games;self.tiles_version+=1
  self.target=next((index for index,game in enumerate(self.games) if game['title']==title),0)
  self.settle_later()
 def hidden(self):
  return getattr(self.link,'hidden',None) or set()
 def shelf_keys(self):
  """The shelves up and down go through. The Apps shelf is there only when the PS5 has homebrew apps, the hidden one only while a game is hidden."""
  apps=any(game.get('app') for game in self.link.games)
  return [key for key,_ in SHELVES if key!='apps' or apps]+([HIDDEN_SHELF[0]] if self.hidden() else [])
 def set_shelf(self,key):
  if key!=self.shelf and key in self.shelf_keys():self.shelf=key;self.refilter();self.cue('move')
 def next_shelf(self,change):
  keys=self.shelf_keys();at=keys.index(self.shelf) if self.shelf in keys else 0;self.set_shelf(keys[(at+change)%len(keys)])
 def go_to(self,index):
  if index!=self.target and 0<=index<len(self.games):self.target=index;self.cue('move');self.settle_later()
 def go_to_title(self,title):
  self.shelf='all';self.text='';self.searching=False;self.refilter()
  self.go_to(next((index for index,game in enumerate(self.games) if game['title']==title),self.target))
 def move(self,change):
  if self.panel:self.scroll(change);return
  if not self.games:return
  at=max(0,min(len(self.games)-1,self.target+change))
  if at==self.target:self.cue('edge')
  else:self.go_to(at)
 def wheel(self,change):
  """A turn of the mouse wheel: along the row or the list, or a row of the grid at a time."""
  if self.panel:self.scroll(change);return
  move=library_view.wheel_for(self.options.view,change,self.target,len(self.games),self.columns)
  if move[0]=='to':self.go_to(move[1])
  elif self.games:self.cue('edge')
 def settle_later(self):
  """The game's art is read first, and its music starts once the row has been still for a moment, so a quick run along the row plays nothing."""
  game=self.focused();self.link.focus=game['title'] if game else '';self.settle_at=self.clock()+self.MUSIC_AFTER
 def settled(self):
  """Once, when the row has been still long enough: the game whose music should play, or '' for none."""
  if self.settle_at is None or self.clock()<self.settle_at:return None
  self.settle_at=None;game=self.focused();return game['title'] if game else ''
 def action_text(self):
  """What the big button says. Empty when there is nothing for it to do."""
  game=self.focused();title=game['title'] if game else ''
  if title and title==self.waiting:return 'Starting'
  if title and title==self.running:return 'Resume'
  if self.link.online:return ('Open' if game.get('app') else 'Play') if game else ''
  return 'Connecting' if self.info.get('state')=='connecting' else 'Connect'
 def choose(self):
  text=self.action_text();game=self.focused()
  if text=='Connect':self.cue('accept');self.run('connect')
  elif game is None or text in ('Connecting',''):self.cue('edge')
  else:self.cue('accept');self.run('open',game['title'])
 def run(self,name,*values):
  command=self.actions.get(name)
  if command is not None:command(*values)
 def navigate(self,event):
  """A move from the keyboard or the controller. True if the page used it."""
  if self.menu:
   if event in ('up','down'):self.menu['selected']=(self.menu['selected']+(1 if event=='down' else -1))%len(self.menu['items']);self.cue('move')
   elif event=='accept':self.menu_choose(self.menu['selected'])
   return True
  if self.panel:
   changes={'up':-1,'down':1,'left':-1,'right':1,'previous':-6,'next':6}
   if event in changes:self.scroll(changes[event])
   elif event=='accept':self.guide()
   return True
  # The row moves along and its shelf changes up and down; the grid moves both ways; the list moves up and down and its shelf changes sideways.
  move=library_view.move_for(self.options.view,event,self.target,len(self.games),self.columns,self.page_rows)
  if move is not None:
   if move[0]=='to':self.go_to(move[1])
   elif move[0]=='edge':self.cue('edge')
   else:self.next_shelf(move[1])
  elif event=='accept':self.choose()
  elif event=='refresh':self.link.refresh();self.cue('move')
  else:return False
  return True
 def dismiss(self):
  """Closes what is open on the page: the menu, the trophy list, then the search. True if there was something."""
  if self.menu:self.menu=None;self.cue('back');return True
  if self.panel:self.panel=None;self.cue('back');return True
  if self.searching or self.text:self.stop_search();self.cue('back');return True
  return False
 def open_menu(self,kind,items=None):
  if kind=='power':items=power_items(self.link.online,self.running,self.exit_label)
  # The PSN menu under the player's picture: its rows come from the PSN side.
  elif kind=='psn':items=list(items or [])
  elif kind=='view':items=library_view.menu_items(self.options,SHELF_NAMES[self.shelf])
  else:
   game=self.focused();title=game['title'] if game else ''
   items=([('close','Close game')] if self.running else [])+([('trophies','Trophies')] if title and self.trophies(title) else [])
   items+=([('show','Show game') if title in self.hidden() else ('hide','Hide game')] if title else [])+[('view_menu','View options'),('refresh','Refresh library'),('live','Live view')]
  if not items:self.notice='Connect to your PS5 first.';self.cue('edge');return
  self.menu=dict(kind=kind,items=items,selected=0);self.cue('move')
 def menu_choose(self,index):
  if not self.menu or not 0<=index<len(self.menu['items']):return
  key=self.menu['items'][index][0]
  if self.menu['kind']=='view':self.view_choose(key,index);return
  self.menu=None;self.cue('accept');game=self.focused()
  if key=='view_menu':self.open_menu('view')
  elif key=='refresh':self.link.refresh()
  elif key in ('hide','show'):
   if game:self.link.set_hidden(game['title'],key=='hide');self.revision=self.link.revision;self.refilter()
  elif key=='trophies':
   if game:self.panel=dict(title=game['title'],selected=0)
  else:self.run(key)
 def view_choose(self,key,index):
  """A choice in the View menu. A new view closes the menu; the others change in place, so you can try each and see it at once."""
  options=self.options
  if key.startswith('view:'):
   self.menu=None;self.cue('accept')
   if key[5:]!=options.view:options.view=key[5:];self.run('view_changed')
   return
  if key=='shelf':self.next_shelf(1)
  else:
   self.cue('accept')
   if key=='size':options.next_size()
   elif key=='names':options.names=not options.names
   elif key=='badges':options.badges=not options.badges
   self.run('view_changed')
  items=library_view.menu_items(options,SHELF_NAMES[self.shelf]);self.menu=dict(kind='view',items=items,selected=min(index,len(items)-1))
 def trophies(self,title):
  found=getattr(self.link,'trophy_set',None);return found(title) if found else None
 def guide(self):
  """The chosen trophy's guide, opened by the window in this PC's browser: ('trophy_guide', the game's name, the trophy)."""
  found=self.trophies(self.panel['title']) if self.panel else None;rows=found['trophies'] if found else []
  if not rows:self.cue('edge');return
  row=rows[max(0,min(len(rows)-1,self.panel['selected']))];name=getattr(self.link,'game_name',None)
  self.cue('accept');self.run('trophy_guide',(name(self.panel['title']) if name else '') or found.get('name') or '',row)
 def scroll(self,change):
  """Moves along the trophy list, stopping at its ends."""
  found=self.trophies(self.panel['title']);count=len(found['trophies']) if found else 0
  at=max(0,min(count-1,self.panel['selected']+change))
  if at==self.panel['selected']:self.cue('edge')
  else:self.panel['selected']=at;self.cue('move')
 def type_text(self,text):
  """What was typed on the page goes into the search, as on the Tk page."""
  text=''.join(char for char in text if char.isprintable())
  if not text or len(self.text)>=40:return
  self.text=(self.text+text)[:40];self.searching=True;self.refilter()
 def erase(self):
  if self.text:self.text=self.text[:-1];self.searching=True;self.refilter()
 def start_search(self):self.searching=True
 def stop_search(self):
  self.text='';self.searching=False;self.refilter()
 def tiles(self):
  """The row, for the window's list. Only read again when tiles_version changes."""
  return [dict(title=game['title'],name=game['name'],kind='Homebrew app' if game.get('app') else game_kind(game['title']),cover=file_url(self.link.icon(game['title'])),art=file_url(self.link.art(game['title']))) for game in self.games]
 def view(self):
  """Everything else the page says, a few times a second."""
  game=self.focused();shelves=[dict(key=key,label=SHELF_NAMES[key]) for key in self.shelf_keys()]
  if game is None:
   name='Your games';line=empty_line(self.link,self.text,self.shelf);cards=total_cards(self.link.games)
  else:
   name=game['name'];line=game_line(game,self.running,self.waiting);cards=game_cards(game)
  menu=None
  if self.menu:menu=dict(kind=self.menu['kind'],selected=self.menu['selected'],items=[dict(key=key,label=label) for key,label,*_ in self.menu['items']])
  return dict(shelf=self.shelf,shelfName=SHELF_NAMES[self.shelf],shelves=shelves,text=self.text,searching=self.searching,focus=self.target,count=len(self.games),
   title=game['title'] if game else '',name=name,line=line,kind=game_kind(game['title']) if game else '',cards=[dict(title=a,value=b,note=c) for a,b,c in cards],
   action=self.action_text(),running=self.running,waiting=self.waiting or '',status=self.line,notice=self.notice,menu=menu,more=bool(game))

def library_info(console_name,online,active,linked,health,fps,pad_name,status):
 """What the top bar and the library's live cards say, as in the Tk window."""
 shown=bool(health.get('decoded_width')) and linked
 def degrees(name):return console_degrees(status,name)
 return dict(name=console_name or 'PS5',state='online' if online else 'connecting' if active else 'offline',pad=bool(pad_name),fps=round(fps) if shown and fps is not None else None,
  picture=f"{health['decoded_width']}×{health['decoded_height']}" if shown else '',bitrate=f"{health['received_mbps']:.0f} Mbps" if linked and health.get('received_mbps') is not None else '',
  cpu=degrees('cpu_c'),soc=degrees('soc_c'))

def message_line(app,core,health,linked,active,now,recording_at,pad,controller_lines,fps,queue_ms,diagnostic):
 """The line at the bottom of the window and how it looks: 'error', 'news' or 'plain'. The same words as the Tk window."""
 dimensions=f"{health['decoded_width']} × {health['decoded_height']}" if health['decoded_width'] else 'Waiting for video'
 info=app.error or (dimensions+'  ·  Stereo' if linked else app.connection_state if active else 'Ready to connect')
 if linked:
  confirmed=app.capture_info and app.capture_info.get('confirmed');info+='  ·  '+(str(app.capture_info.get('fps_target'))+' fps target / '+str(app.capture_info.get('bitrate_target',0)//1000000)+' Mbps' if confirmed else 'Legacy payload: quality profile not confirmed')
  game=getattr(getattr(app,'link',None),'game_fps',None)
  if game is not None:info+=f'  ·  Game {game:.0f} fps'
 notice=core.resolution_notice(app.capture_info)
 if linked and notice:info+='  ·  '+notice
 if linked and health['received_mbps'] is not None:info+=f"  ·  {health['received_mbps']:.1f} Mbps received"
 if linked and app.decoder_name=='gpu':info+='  ·  GPU decoding'
 elif linked and health['decoded_width'] and (app.capture_info or {}).get('resolution',4)>=5:info+='  ·  Processor decoding'
 if linked and app.stats.get('smooth_line'):info+='  ·  '+app.stats['smooth_line']
 if core.PROFILES[app.args.profile].get('playback_fps'):info+='  ·  30 fps PC playback'
 if app.microphone.on:info+='  ·  MIC'
 if pad.sending:info+=controller_lines
 if app.recorder.active:info+='  ·  '+(('REC '+str(int(now-recording_at))+' s') if recording_at is not None else 'Recording: '+app.recorder.state)
 if app.broadcast.state=='live':info+='  ·  LIVE '+live_broadcast.clock(app.broadcast.elapsed())+' on '+app.broadcast.name
 elif app.broadcast.active:info+='  ·  Going live…'
 if now<app.notice_until:info=app.notice
 if diagnostic:info+=f'   |   {fps:.0f} fps · PC {app.stats["last_frame_to_ui_ms"]:.1f} ms · audio queue {queue_ms:.0f} ms'
 return info,'error' if app.error else 'news' if now<app.notice_until else 'plain'

def controller_text(pad,now):
 """What the controller on the console adds to the bottom line while it is in use there."""
 link=pad.link(now)
 if not pad.name and not getattr(pad,'keys_on',False):return '  ·  No controller on this PC'
 if link in ('waiting','starting'):return '  ·  Controller starting…'
 if link=='full':return '  ·  Four controllers are in use on your PS5'
 if link=='failed':return f'  ·  Controller could not start ({pad.answer[1]&0xffffffff:08x})'
 if link=='refused':return f'  ·  Controller input refused ({pad.answer[1]&0xffffffff:08x})'
 if link=='unavailable':return '  ·  Controller unavailable'
 return ''

def session_view(app,health,fps,queue_ms,linked,now,recording_elapsed,game,readings,history):
 """The session panel: the same readings as the Tk one."""
 rate=health.get('received_mbps') if linked else None
 recording=('Recording  '+clock_text(recording_elapsed)) if recording_elapsed is not None else 'Recorder  '+app.recorder.state.capitalize()
 return dict(fps=round(fps) if linked else None,source=f"{health['decoded_width']} × {health['decoded_height']}" if linked and health['decoded_width'] else 'Awaiting video',
  latency=f"{app.stats['last_frame_to_ui_ms']:.1f} ms" if linked and app.stats.get('video_presented') else '—',rate=f'{rate:.1f} Mbps' if rate is not None else '—',
  history=[-1 if value is None else round(value,2) for value in history],game=game,readings=readings,
  details=['App session  '+clock_text(now-app.started),'Audio buffer  '+(f'{queue_ms:.0f} ms' if linked else '—'),'Received  '+format_bytes(app.stats.get('received_bytes',0)),recording])

def capture_card(item):
 """One capture on the Media page."""
 kind='photo' if item.kind=='Photos' else 'video'
 return dict(path=str(item.path),kind=kind,when=datetime.fromtimestamp(item.modified).strftime('%d %b %Y · %H:%M'),
  detail=(item.path.suffix[1:].upper().replace('JPEG','JPG') or ('PNG' if kind=='photo' else 'MP4'))+'  ·  '+format_bytes(item.size),action='Open photo' if kind=='photo' else 'Play recording')

def readings_line(status):return console_line(status)
