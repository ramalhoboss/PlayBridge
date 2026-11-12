"""What the Qt pages show, worked out without Qt so that it can be tested: the Games shelf, the line at the bottom of the window
and the session panel's readings. The Qt window only draws what these give it."""
import time
from datetime import datetime
from pathlib import Path
from console_control import console_line
from desktop_features import clock_text,format_bytes
from game_mode import SHELVES,empty_line,game_cards,game_line,power_items,shelf_games,total_cards
import live_broadcast

SHELF_NAMES=dict(SHELVES)
PAGES=('games','live','media')

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
 def focused(self):
  return self.games[self.target] if 0<=self.target<len(self.games) else None
 def sync(self,running,waiting,line,notice=''):
  """A few times a second. True when the shelf's games changed and the tiles have to be read again."""
  self.running,self.waiting,self.line,self.notice=running,waiting,line,notice
  if self.revision!=self.link.revision:
   self.revision=self.link.revision;self.refilter();return True
  return False
 def refilter(self):
  game=self.focused();title=game['title'] if game else None
  games=shelf_games(self.link.games,self.shelf,self.text)
  self.games=games;self.tiles_version+=1
  self.target=next((index for index,game in enumerate(self.games) if game['title']==title),0)
  self.settle_later()
 def set_shelf(self,key):
  if key!=self.shelf and key in SHELF_NAMES:self.shelf=key;self.refilter();self.cue('move')
 def go_to(self,index):
  if index!=self.target and 0<=index<len(self.games):self.target=index;self.cue('move');self.settle_later()
 def go_to_title(self,title):
  self.shelf='all';self.text='';self.searching=False;self.refilter()
  self.go_to(next((index for index,game in enumerate(self.games) if game['title']==title),self.target))
 def move(self,change):
  if not self.games:return
  at=max(0,min(len(self.games)-1,self.target+change))
  if at==self.target:self.cue('edge')
  else:self.go_to(at)
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
  if self.link.online:return 'Play' if game else ''
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
  moves={'left':-1,'right':1,'previous':-5,'next':5}
  if event in moves:self.move(moves[event])
  elif event in ('up','down'):
   keys=[key for key,_ in SHELVES];self.set_shelf(keys[(keys.index(self.shelf)+(1 if event=='down' else -1))%len(keys)])
  elif event=='accept':self.choose()
  elif event=='refresh':self.link.refresh();self.cue('move')
  else:return False
  return True
 def dismiss(self):
  """Closes what is open on the page: the menu, then the search. True if there was something."""
  if self.menu:self.menu=None;self.cue('back');return True
  if self.searching or self.text:self.stop_search();self.cue('back');return True
  return False
 def open_menu(self,kind):
  if kind=='power':items=power_items(self.link.online,self.running,self.exit_label)
  else:items=([('close','Close game')] if self.running else [])+[('refresh','Refresh library'),('live','Live view')]
  if not items:self.notice='Connect to your PS5 first.';self.cue('edge');return
  self.menu=dict(kind=kind,items=items,selected=0);self.cue('move')
 def menu_choose(self,index):
  if not self.menu or not 0<=index<len(self.menu['items']):return
  key=self.menu['items'][index][0];self.menu=None;self.cue('accept')
  if key=='refresh':self.link.refresh()
  else:self.run(key)
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
  return [dict(title=game['title'],name=game['name'],kind=game_kind(game['title']),cover=file_url(self.link.icon(game['title'])),art=file_url(self.link.art(game['title']))) for game in self.games]
 def view(self):
  """Everything else the page says, a few times a second."""
  game=self.focused();shelves=[dict(key=key,label=label) for key,label in SHELVES]
  if game is None:
   name='Your games';line=empty_line(self.link,self.text);cards=total_cards(self.link.games)
  else:
   name=game['name'];line=game_line(game,self.running,self.waiting);cards=game_cards(game)
  menu=None
  if self.menu:menu=dict(kind=self.menu['kind'],selected=self.menu['selected'],items=[dict(key=key,label=label) for key,label in self.menu['items']])
  return dict(shelf=self.shelf,shelfName=SHELF_NAMES[self.shelf],shelves=shelves,text=self.text,searching=self.searching,focus=self.target,count=len(self.games),
   title=game['title'] if game else '',name=name,line=line,kind=game_kind(game['title']) if game else '',cards=[dict(title=a,value=b,note=c) for a,b,c in cards],
   action=self.action_text(),running=self.running,waiting=self.waiting or '',status=self.line,notice=self.notice,menu=menu,more=bool(game))

def library_info(console_name,online,active,linked,health,fps,pad_name,status):
 """What the top bar and the library's live cards say, as in the Tk window."""
 shown=bool(health.get('decoded_width')) and linked
 def degrees(name):
  return status[name] if isinstance(status.get(name),int) and status[name]>0 else None
 return dict(name=console_name or 'PS5',state='online' if online else 'connecting' if active else 'offline',pad=bool(pad_name),fps=round(fps) if shown and fps is not None else None,
  picture=f"{health['decoded_width']}×{health['decoded_height']}" if shown else '',bitrate=f"{health['received_mbps']:.0f} Mbps" if linked and health.get('received_mbps') is not None else '',
  cpu=degrees('cpu_c'),soc=degrees('soc_c'))

def message_line(app,core,health,linked,active,now,recording_at,pad,controller_lines,fps,queue_ms,diagnostic):
 """The line at the bottom of the window and how it looks: 'error', 'news' or 'plain'. The same words as the Tk window."""
 dimensions=f"{health['decoded_width']} × {health['decoded_height']}" if health['decoded_width'] else 'Waiting for video'
 info=app.error or (dimensions+'  ·  Stereo' if linked else app.connection_state if active else 'Ready to connect')
 if linked:
  confirmed=app.capture_info and app.capture_info.get('confirmed');info+='  ·  '+(str(app.capture_info.get('fps_target'))+' fps target / '+str(app.capture_info.get('bitrate_target',0)//1000000)+' Mbps' if confirmed else 'Legacy payload: quality profile not confirmed')
 notice=core.resolution_notice(app.capture_info)
 if linked and notice:info+='  ·  '+notice
 if linked and health['received_mbps'] is not None:info+=f"  ·  {health['received_mbps']:.1f} Mbps received"
 if linked and app.decoder_name=='gpu':info+='  ·  GPU decoding'
 elif linked and health['decoded_width'] and (app.capture_info or {}).get('resolution',4)>=5:info+='  ·  Processor decoding'
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
 if not pad.name:return '  ·  No controller on this PC'
 if link in ('waiting','starting'):return '  ·  Controller starting…'
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
