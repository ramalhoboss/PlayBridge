"""PlayBridge in Qt Quick: the pages, settings, keys and controller of the Tk window, drawn on the graphics card with glass, depth and motion.
The stream, the console link and the captures stay the Player's own. This file shows them and passes on what is chosen; the pages are in qml/."""
import ctypes,hashlib,ipaddress,os,queue,socket,sys,threading,time
from ctypes import wintypes
from pathlib import Path
from PySide6.QtCore import QAbstractListModel,QCoreApplication,QEvent,QModelIndex,QObject,QRect,QSize,Qt,QTimer,QUrl,Property,Signal,Slot
from PySide6.QtGui import QCursor,QDesktopServices,QGuiApplication,QIcon,QWindow
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
import sounddevice as sd
import graphics_card,live_broadcast,mic_mix,payload_sender,updater,video_encoders
from qt_models import PAGES,Shelf,capture_card,controller_text,file_url,library_info,message_line,session_view
from console_control import CLOSE,GameFlow,POWER_OFF,REBOOT,REST,console_line,menu_in_front,running_title
from desktop_features import capture_items,remember_console,saved_consoles,video_thumbnail
from frame_pacing import CAPTURE_FRAME,FrameTimer,HitchWatch,RefreshClock
from game_mode import KEY_HINTS,PAD_HINTS,power_items,status_text
from hang_watch import HangWatch
from keep_awake import BatteryHint,KeepAwake
from pad_input import CONSOLE_PAD_READY,PadBridge
from screen_rate import ScreenRate
from sound_board import SoundBoard

QML=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))/'qml'
user32=ctypes.WinDLL('user32',use_last_error=True)
user32.GetClientRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)];user32.IsIconic.argtypes=[wintypes.HWND]
user32.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
user32.GetDC.argtypes=[wintypes.HWND];user32.GetDC.restype=wintypes.HDC;user32.ReleaseDC.argtypes=[wintypes.HWND,wintypes.HDC]
user32.FillRect.argtypes=[wintypes.HDC,ctypes.POINTER(wintypes.RECT),wintypes.HANDLE]
gdi32=ctypes.WinDLL('gdi32');gdi32.GetStockObject.restype=wintypes.HANDLE
HWND_TOPMOST,HWND_NOTOPMOST=wintypes.HWND(-1),wintypes.HWND(-2);NO_MOVE_SIZE=0x0001|0x0002|0x0010
TABS=PAGES
REPLAY_LENGTHS={'Off':0,'Last 30 seconds':30,'Last 60 seconds':60,'Last 2 minutes':120}
DEFAULT_MIC='Windows default microphone'
SECTIONS=(('console','Console','Address, favourites, connection and power'),('picture','Picture','Quality, graphics card, video output and upscaling'),('captures','Captures','Instant replay, files and diagnostics'),
 ('sound','Sound','Music and sounds on the Games page'),('live','Streaming','Twitch, YouTube, any RTMP server, or OBS on this PC'),('look','Appearance','Gaming Mode, motion and the look of PlayBridge'),
 ('updates','Updates','New versions of PlayBridge from GitHub'))
LIVE_HINTS={'twitch':'Twitch recommends at most 6 Mbps, so the Data saver profile suits it best. Higher profiles work on many channels.','youtube':'YouTube takes every 1080p profile. The key travels over an encrypted connection.',
 'custom':'Enter the server address and, if your service gives it separately, the stream key.','obs':f'In OBS, add a Media Source, untick Local File, and enter udp://127.0.0.1:{live_broadcast.OBS_PORT} as the input. Then select Go live here.'}

def client_size(hwnd):
 rect=wintypes.RECT();user32.GetClientRect(hwnd,ctypes.byref(rect));return max(1,rect.right-rect.left),max(1,rect.bottom-rect.top)

class VideoSurface(QWindow):
 """A native window of its own inside the main one, for the swap chain: Qt Quick never draws on it, so the two never fight over it.
 The presenters ask it what they asked Tk's widgets: its handle and its size in pixels, both safe from any thread."""
 def __init__(self,parent,shell):
  super().__init__(parent);self.shell=shell;self.exposed=[]
  # Keys stay with the main window, where the shortcuts are, even after a click on the picture.
  self.setFlags(Qt.WindowType.Widget|Qt.WindowType.WindowDoesNotAcceptFocus);self.handle=int(self.winId())
 def winfo_id(self):return self.handle
 def winfo_width(self):return client_size(self.handle)[0]
 def winfo_height(self):return client_size(self.handle)[1]
 def bind(self,event,command,add=None):
  if event=='<Expose>':self.exposed.append(command)
 def exposeEvent(self,event):
  for command in self.exposed:command(None)
 def clear(self):
  """Black over the whole window, for the memory output, which only draws where the frame lands."""
  dc=user32.GetDC(self.handle)
  if dc:
   rect=wintypes.RECT(0,0,*client_size(self.handle));user32.FillRect(dc,ctypes.byref(rect),gdi32.GetStockObject(4));user32.ReleaseDC(self.handle,dc)
 def mouseDoubleClickEvent(self,event):self.shell.act('video_double',None)
 def mouseMoveEvent(self,event):self.shell.pointer_moved()
 def mousePressEvent(self,event):self.shell.pointer_moved();self.parent().requestActivate()

class GameModel(QAbstractListModel):
 """The row of games. Rows that keep their place change in place, so the list keeps its focus and motion."""
 ROLES=('title','name','kind','cover','art')
 def __init__(self):super().__init__();self.rows=[]
 def roleNames(self):return {int(Qt.ItemDataRole.UserRole)+index:name.encode() for index,name in enumerate(self.ROLES)}
 def rowCount(self,parent=QModelIndex()):return 0 if parent.isValid() else len(self.rows)
 def data(self,index,role=int(Qt.ItemDataRole.DisplayRole)):
  at=int(role)-int(Qt.ItemDataRole.UserRole)
  if not index.isValid() or not 0<=index.row()<len(self.rows) or not 0<=at<len(self.ROLES):return None
  return self.rows[index.row()].get(self.ROLES[at])
 def replace(self,rows):
  if [row['title'] for row in rows]==[row['title'] for row in self.rows]:
   changed=[index for index,(old,new) in enumerate(zip(self.rows,rows)) if old!=new];self.rows=rows
   for index in changed:self.dataChanged.emit(self.index(index),self.index(index))
  else:self.beginResetModel();self.rows=rows;self.endResetModel()

class Shell(QObject):
 """What the pages show, each part with its own change signal so that only what reads it is redone, and everything they ask for."""
 pageChanged=Signal();gamingChanged=Signal();fullscreenChanged=Signal();miniChanged=Signal();topChanged=Signal();barChanged=Signal();messageChanged=Signal();stageChanged=Signal()
 shelfChanged=Signal();dockChanged=Signal();mediaChanged=Signal();settingsChanged=Signal();dialogChanged=Signal();popupChanged=Signal();consoleCapturesChanged=Signal();lookChanged=Signal();parallaxChanged=Signal()
 navigate=Signal(str)
 page=Property(str,lambda self:self.values['page'],notify=pageChanged)
 gaming=Property(bool,lambda self:self.values['gaming'],notify=gamingChanged)
 fullscreen=Property(bool,lambda self:self.values['fullscreen'],notify=fullscreenChanged)
 mini=Property(bool,lambda self:self.values['mini'],notify=miniChanged)
 top=Property('QVariantMap',lambda self:self.values['top'],notify=topChanged)
 bar=Property('QVariantMap',lambda self:self.values['bar'],notify=barChanged)
 message=Property('QVariantMap',lambda self:self.values['message'],notify=messageChanged)
 stage=Property('QVariantMap',lambda self:self.values['stage'],notify=stageChanged)
 shelf=Property('QVariantMap',lambda self:self.values['shelf'],notify=shelfChanged)
 dock=Property('QVariantMap',lambda self:self.values['dock'],notify=dockChanged)
 media=Property('QVariantMap',lambda self:self.values['media'],notify=mediaChanged)
 settings=Property('QVariantMap',lambda self:self.values['settings'],notify=settingsChanged)
 dialog=Property('QVariantMap',lambda self:self.values['dialog'],notify=dialogChanged)
 popup=Property('QVariantMap',lambda self:self.values['popup'],notify=popupChanged)
 consoleCaptures=Property('QVariantMap',lambda self:self.values['consoleCaptures'],notify=consoleCapturesChanged)
 look=Property('QVariantMap',lambda self:self.values['look'],notify=lookChanged)
 parallax=Property('QVariantMap',lambda self:self.values['parallax'],notify=parallaxChanged)

 def __init__(self,app,core):
  super().__init__()
  self.app=app;self.core=core;saved=core.config()
  self.values=dict(page='',gaming=False,fullscreen=False,mini=False,top={},bar={},message={},stage={},shelf={},dock={},media={},settings={},dialog={},popup={},consoleCaptures={},look={},parallax={'x':0.0,'y':0.0})
  self.flow=GameFlow();self.back_page='games';self.menu_was_in_front=False;self.seen_status=None;self.revealed_at=0;self.opened_title='';self.opened_at=0;self.first_status=True;self.top_info={}
  self.dialog_command=None;self.has_video=False;self.mini_place=None;self.session_wanted=bool(saved.get('session_panel',False));self.dock_visible=False;self.window_width=1540
  self.sounds=SoundBoard(lambda:app.stats.get('output_device'),saved.get('sound_music',True),saved.get('sound_cues',True),saved.get('sound_level',.6))
  self.actions=dict(open=self.start_game,close=self.close_game,connect=self.connect_toggle,live=lambda:self.show_page('live'),media=lambda:self.show_page('media'),settings=lambda:self.show_page('settings'),
   fullscreen=lambda:self.set_gaming(not self.values['gaming']),rest=self.rest_console,off=self.power_off_console,reboot=self.reboot_console,soft_reset=self.soft_reset,recovery=self.recovery_console,exit=lambda:self.set_gaming(False))
  self.shelf_state=Shelf(app.link,self.actions,self.sounds.play);self.games=GameModel()
  self.pad=PadBridge(lambda:app.args.host,app.stop)
  self.diagnostic=bool(saved.get('diagnostic',False));self.match_on=bool(saved.get('match_refresh',True));self.animations=bool(saved.get('animations',True))
  self.say_text=('','plain');self.say_until=None;self.update_seen=-1;self.scan_results=queue.Queue();self.discovered={};self.scanning=False;self.scan_status='Find your PS5 or enter its IP address above.';self.found_label='Select a console'
  self.favourite_status=('Save this IP and quality profile for next time.','plain');self.payload_status=('Sends any ELF to the loader your exploit opened on port 9021. A payload runs with full access to the PS5, so send only files you trust.','plain')
  self.payload_results=queue.Queue();self.live_status=None;self.encoders=None;self.encoder_results=queue.Queue();self.section='console';self.typed_host=None;self.typed_profile=None
  # Text the window puts in the address and name fields, as when a console is found: a new version each time, so the field takes it once.
  self.fill=dict(host='',name='',version=0)
  # Read once: the cards and what the screen offers do not change while PlayBridge runs.
  self.found_cards=graphics_card.cards();self.mic_names=[name for _,name in mic_mix.inputs(sd)]
  threading.Thread(target=lambda:self.encoder_results.put((video_encoders.for_files(),video_encoders.for_live())),name='PlayBridge encoders',daemon=True).start()
  # The Media page reads the folder and makes the stills on a thread of its own.
  self.media_filter='All';self.media_number=0;self.media_items=[];self.media_generation=0;self.media_results=queue.Queue();self.media_status='Reading your captures…';self.thumbs={}
  self.thumb_folder=core.STATE/'thumbnails'
  self.ps5=None;self.ps5_answers=queue.Queue()
  self.audio_outputs()

 # Values for the pages.
 def put(self,name,value):
  if self.values.get(name)!=value:self.values[name]=value;getattr(self,name+'Changed').emit()

 @Slot(str,'QVariant')
 def act(self,name,value=None):
  """Everything the pages ask for comes through here: act('screenshot'), act('volume',0.5)."""
  command=getattr(self,'do_'+name,None)
  if command is None:return
  try:command(value)
  except Exception as error:
   self.app.event(f'Qt action {name} failed: {type(error).__name__}: {str(error)[:120]}');self.app.notify(f'That did not work: {error}')

 @Slot(float,float,float,float)
 def placeVideo(self,x,y,width,height):
  """Where the picture goes in the window, in the window's own units, from the live page."""
  self.video_rect=QRect(round(x),round(y),max(1,round(width)),max(1,round(height)))
  if self.video is not None and self.video.geometry()!=self.video_rect:self.video.setGeometry(self.video_rect)

 # The window and the video.
 def build(self,engine):
  app=self.app;core=self.core
  self.engine=engine;self.window=engine.rootObjects()[0];self.hwnd=int(self.window.winId());self.video_rect=QRect(0,0,1,1);self.video=None
  self.presenter=None;self.direct=False
  if app.renderer=='d3d11':
   try:
    from d3d11_presenter import D3D11Presenter
    self.video=VideoSurface(self.window,self);self.video.setGeometry(self.video_rect)
    self.presenter=D3D11Presenter(self.video,core.config().get('sharpen',False),core.config().get('fsr',False),app.adapter,core.config().get('vrr',False));self.direct=True
   except Exception:self.presenter=None;app.use_gdi()
  if not self.direct:
   from gdi_presenter import GdiPresenter
   app.renderer='gdi'
   if self.video is None:self.video=VideoSurface(self.window,self);self.video.setGeometry(self.video_rect)
   self.presenter=GdiPresenter(self.video)
  self.refresh=RefreshClock(app.stop)
  self.vrr_on=self.direct and self.presenter.tearing
  self.vrr_state='on' if self.vrr_on else 'fixed screen' if getattr(self.presenter,'fixed_screen',False) else 'unsupported' if core.config().get('vrr',False) else 'off'
  def next_due():
   with app.lock:return app.pacer.due()
  # Never two frames closer than one refresh, and never so far apart that 60 fps could not keep up.
  self.clock=FrameTimer(app.stop,next_due,spacing=lambda:min(self.refresh.period,.75*CAPTURE_FRAME)) if self.vrr_on else self.refresh
  self.shown_at=None;self.hitches=HitchWatch();self.paint_took=0;self.seen_presented=0
  if self.direct:self.clock.after=self.paint
  self.watch=HangWatch(threading.get_ident(),app.stop);self.awake=KeepAwake();self.rate=ScreenRate();self.battery=BatteryHint()
  self.last_tick=time.perf_counter();self.rate_at=self.last_tick;self.rate_frames=0;self.fps=0;self.last_info=0;self.info_at=0;self.recording_at=None;self.decoded_mark=0;self.decoded_rate=0;self.history=[];self.history_at=0
  self.cursor_at=time.perf_counter();self.cursor_hidden=False
  self.timer=QTimer(self);self.timer.setTimerType(Qt.TimerType.PreciseTimer);self.timer.timeout.connect(self.tick);self.timer.start(2 if not self.direct else 8)

  self.pad.start()
  QTimer.singleShot(1,lambda:self.set_gaming(True) if core.config().get('gaming_mode',False) else self.show_page('games'))
  # A microphone left on stays on, and says so when it opens.
  if core.config().get('mic_on',False):QTimer.singleShot(800,lambda:self.set_microphone(True))
  self.refresh_settings();self.refresh_look()
 def note_shown(self,done):
  # The time between two frames on screen: 16.7 ms each on a steady screen, and 13.9 then 20.8 on a 144 Hz one, which is the judder.
  last,self.shown_at=self.shown_at,done
  if last is not None and done-last<.25:self.app.timings.add('shown_gap_ms',(done-last)*1000)
  self.hitches.shown(done,self.refresh.period,done-self.app.started)
 def paint(self):
  """On the refresh clock's thread, so nothing in the window's own loop can delay a frame."""
  app=self.app;output=self.presenter;clock=self.clock
  try:
   now=time.perf_counter();seconds=clock.elapsed(now)
   with app.lock:missing=app.pacer.missing;item=app.pacer.advance(seconds,now) if seconds else None;missing=app.pacer.missing!=missing
   self.hitches.refresh(round(seconds/clock.period),missing,self.paint_took>clock.period)
   if item is None:output.refresh();return
   image,arrived,prepared=item;paint_at=time.perf_counter();app.timings.add('prepared_slot_wait_ms',(paint_at-prepared)*1000)
   if output.draw(image):
    done=time.perf_counter();self.note_shown(done);app.timings.add('presenter_upload_ms',(done-paint_at)*1000);app.timings.add('receive_to_present_ms',(done-arrived)*1000);app.stats['video_presented']+=1;app.stats['last_frame_to_ui_ms']=round((done-arrived)*1000,1)
    if self.vrr_on:clock.last=done
   else:self.hitches.unpresented()
  except Exception as error:output.failed=error
  finally:self.paint_took=time.perf_counter()-now
 def leave_direct(self):
  """This PC cannot keep the GPU output going, so the picture carries on through memory, on the same window."""
  from gdi_presenter import GdiPresenter
  self.clock.after=None;self.direct=False;self.video.hide()
  # The swap chain has to go with its window: the memory output draws on a new one.
  old=self.video;self.video=VideoSurface(self.window,self);self.video.setGeometry(self.video_rect);old.destroy()
  self.presenter=GdiPresenter(self.video);self.app.use_gdi();self.timer.setInterval(2)
  if self.vrr_on:self.vrr_on=False;self.vrr_state='off';self.refresh.elapsed(time.perf_counter())
 def video_wanted(self):
  return self.values['page']=='live' and self.has_video
 def tick(self):
  app=self.app;core=self.core
  if app.stop.is_set():self.close();return
  now=time.perf_counter()
  # A window that stops answering shows in the timeline, so a frozen picture can be told apart from a stream that stopped.
  stuck=self.watch.beat()
  if now-self.last_tick>.3:app.event(f'Window busy for {round((now-self.last_tick)*1000)} ms on the {self.values["page"]} page'+(f', in {stuck}' if stuck else ''))
  self.last_tick=now
  if app.args.seconds and now-app.started>=app.args.seconds:self.close();return
  vw,vh=client_size(self.video.handle) if self.video.isVisible() else (max(1,round(self.video_rect.width()*self.window.devicePixelRatio())),max(1,round(self.video_rect.height()*self.window.devicePixelRatio())))
  app.render_size=(vw,vh)
  if self.direct and self.presenter.failed:self.leave_direct()
  page=self.values['page']
  if self.direct:
   item=None;self.presenter.wanted=(vw,vh)
   with app.lock:queue_ms=len(app.pcm)/192
  else:
   seconds=self.refresh.elapsed(now)
   with app.lock:missing=app.pacer.missing;item=app.pacer.advance(seconds,now) if seconds else None;queue_ms=len(app.pcm)/192;missing=app.pacer.missing!=missing
   self.hitches.refresh(0,missing,False)
   if item and (item[0].width>vw or item[0].height>vh):item=None
  # While PlayBridge connects again on its own, as when a game closes, the last picture stays on screen until the new one arrives.
  if not app.worker.is_alive() and self.has_video:
   self.has_video=False;self.presenter.frame=None
  if self.direct:
   presented=app.stats['video_presented']
   if presented!=self.seen_presented:self.rate_frames+=presented-self.seen_presented;self.seen_presented=presented
   # The video window shows as soon as a picture waits for it, because the presenter makes its swap chain only on a window that shows.
   if not self.has_video and self.presenter.frame is not None and app.connection_state=='Connected' and app.worker.is_alive():self.has_video=True
  elif item:
   if not self.has_video:self.has_video=True;self.video.show();self.video.clear()
   image,arrived,prepared=item;paint_at=time.perf_counter();app.timings.add('prepared_slot_wait_ms',(paint_at-prepared)*1000)
   if self.presenter.frame is not None and (image.width,image.height)!=(self.presenter.frame.width,self.presenter.frame.height):self.video.clear()
   self.presenter.draw(image)
   done=time.perf_counter();self.note_shown(done);app.timings.add('presenter_upload_ms',(done-paint_at)*1000);app.timings.add('receive_to_present_ms',(done-arrived)*1000);app.stats['video_presented']+=1;app.stats['last_frame_to_ui_ms']=round((done-arrived)*1000,1);self.rate_frames+=1
  else:self.presenter.refresh()
  wanted=self.video_wanted()
  if wanted!=self.video.isVisible():
   self.video.setGeometry(self.video_rect);self.video.setVisible(wanted)
  if not self.pad.events.empty():self.pad_event(self.pad.events.get_nowait())
  if app.link.status is not self.seen_status:self.seen_status=app.link.status;self.follow_console(now)
  self.follow_pointer(now)
  self.follow_stick()
  if page=='games':
   title=self.shelf_state.settled()
   if title is not None:self.sounds.want_track(app.link.music_file(title) if title else None)
  if now-self.rate_at>=1:self.each_second(now)
  if now-self.last_info>.25:self.each_quarter(now,queue_ms)
  self.poll_queues()
 def each_second(self,now):
  app=self.app;core=self.core
  decoded=app.stats.get('video_decoded',0);self.decoded_rate=(decoded-self.decoded_mark)/(now-self.rate_at);self.decoded_mark=decoded
  self.fps=self.rate_frames/(now-self.rate_at);app.stats['presented_fps']=round(self.fps,1);self.rate_frames=0;self.rate_at=now
  # What the screen side looked like, to tell a PC that stutters from one that does not.
  app.stats['refresh_hz']=round(1/self.refresh.period,1);app.stats['vrr']=self.vrr_state;app.stats['hitches']=dict(self.hitches.counts);app.stats['hitch_log']=list(self.hitches.log)
  if self.direct:app.stats['present_timeouts']=self.presenter.timeouts;app.stats['cross_card']=self.presenter.cross;app.stats['frames_in_flight']=self.presenter.flight
  app.stats['screen_rate']=self.rate.label();app.stats['screen_rate_check']=self.rate.note;app.stats['controller_link']=self.pad.link(time.monotonic());app.stats['ui']='qt'
  # What the app cannot fix itself, it says, once a session and only when frames are really being lost.
  wanted_fps=core.PROFILES[app.args.profile].get('playback_fps') or (app.capture_info or {}).get('fps_target') or 60
  streaming=app.connection_state=='Connected' and app.worker.is_alive()
  hint=self.battery.second(streaming,app.stats['presented_fps'],wanted_fps);app.stats['on_battery']=self.battery.on
  if hint:app.notify(hint);app.notice_until=now+15
  app.snapshot()
 def each_quarter(self,now,queue_ms):
  app=self.app;core=self.core;self.last_info=now;page=self.values['page']
  app.poll_capture_events();active=app.worker.is_alive();linked=app.connection_state=='Connected' and active
  iconic=bool(user32.IsIconic(self.hwnd))
  # While a session runs the display and the PC stay on, unless the window is minimized.
  self.awake.want(linked and not iconic)
  # A screen whose rate does not fit 60 fps gets one that does, but only while the game fills it.
  switched=self.rate.want(self.match_on and not self.vrr_on and linked and not iconic and (page=='live' or self.rate.changed is not None),self.hwnd)
  if switched:app.notify(f'Screen set from {switched[0]} to {switched[1]} Hz while the game streams, so every frame shows for the same time.')
  with app.metrics_lock:health=app.metrics.summary()
  if app.recorder.active and app.recorder.state=='recording':
   if self.recording_at is None:self.recording_at=now
  elif not app.recorder.active:self.recording_at=None
  self.place_session()
  self.sounds.want_music(page=='games' and not (self.flow.waiting or self.flow.after_close))
  self.pad.sending=CONSOLE_PAD_READY and app.link.online and page=='live'
  playing=running_title(app.link.status);readings=console_line(app.link.status)
  if now-self.info_at>=1:
   self.info_at=now;self.top_info=library_info((app.console or {}).get('name'),app.link.online,active,linked,health,self.decoded_rate,self.pad.name,app.link.status)
   self.shelf_state.info=self.top_info
  line='  ·  '.join(part for part in ('Menu open on your PS5' if self.menu_was_in_front else '',self.pad.name) if part) if app.link.online else 'Waiting for your PS5…'
  if self.shelf_state.sync(playing,self.flow.waiting or self.flow.after_close,line,app.notice if now<app.notice_until else app.error or ''):self.games.replace(self.shelf_state.tiles())
  self.show_shelf()
  self.put('top',dict(tab=page if page in TABS else '',selected='settings' if page=='settings' else '',status=status_text(self.top_info),online=self.top_info.get('state')=='online',clock=time.strftime('%H:%M'),pad=bool(self.top_info.get('pad')),info=self.top_info))
  on_air=app.broadcast.active
  self.put('bar',dict(muted=app.muted,volume=round(app.volume,3),recording=bool(app.recorder.active),onAir=bool(on_air),active=active,linked=linked,host=app.console_label(),outputs=[name for _,name in self.outputs] or ['No audio device'],output=self.device_label(app.output_name) or 'No sound output',
   session=self.dock_visible,micOn=bool(app.microphone.on),live=app.broadcast.state=='live',liveText=('Live on '+app.broadcast.name+' for '+live_broadcast.clock(app.broadcast.elapsed())+'.') if app.broadcast.state=='live' else ''))
  if self.dock_visible:
   if now-self.history_at>=1:
    rate=health.get('received_mbps') if linked else None
    if self.history_at:self.history.extend([None]*min(59,max(0,int(now-self.history_at)-1)))
    self.history_at=now;self.history=(self.history+[rate])[-60:]
   self.put('dock',session_view(app,health,self.fps,queue_ms,linked,now,now-self.recording_at if self.recording_at is not None else None,app.link.game_name(playing) if playing else 'No game open' if app.link.online else 'Not connected',readings,self.history))
  # The video keeps arriving behind the other pages, so coming back shows a waiting screen only if no frame turns up.
  waiting=not self.has_video and page=='live' and now-self.revealed_at>1
  self.put('stage',dict(waiting=waiting,text=app.error or ('Connecting to your console…' if active else 'Open Payload Manager on your PS5, then connect.'),video=self.has_video))
  text,tone=message_line(app,core,health,linked,active,now,self.recording_at,self.pad,controller_text(self.pad,time.monotonic()) if self.pad.sending else '',self.fps,queue_ms,self.diagnostic)
  self.put('message',dict(text=text,tone=tone))
  if page=='settings':self.refresh_settings()
 def poll_queues(self):
  while not self.scan_results.empty():self.finish_scan(*self.scan_results.get_nowait())
  while not self.payload_results.empty():self.finish_payload(*self.payload_results.get_nowait())
  if self.encoders is None and not self.encoder_results.empty():self.encoders=self.encoder_results.get_nowait();self.refresh_settings()
  while not self.media_results.empty():self.finish_media(*self.media_results.get_nowait())
  while not self.ps5_answers.empty():self.ps5_answer(*self.ps5_answers.get_nowait())
  if self.app.updates.revision!=self.update_seen:self.update_seen=self.app.updates.revision;self.refresh_settings()
  if self.say_until is not None and time.perf_counter()>self.say_until:self.say_until=None;self.say_text=('','plain');self.refresh_settings()
 def close(self):
  if getattr(self,'closed',False):return
  self.closed=True;self.timer.stop();self.awake.want(False);self.rate.want(False,0);self.app.microphone.close();self.app.stop.set();self.sounds.close()
  if self.values['mini'] and self.mini_place:self.core.save_config(mini_geometry=self.geometry_text())
  QGuiApplication.quit()

 # The pointer, hidden over the picture after a pause in full screen, and the art that follows it on the Games page.
 def pointer_moved(self):
  self.cursor_at=time.perf_counter()
  if self.cursor_hidden:self.cursor_hidden=False;self.window.unsetCursor();self.video.unsetCursor()
 def follow_pointer(self,now):
  hide=self.values['fullscreen'] and self.values['page']=='live' and now-self.cursor_at>2.5
  if hide and not self.cursor_hidden:self.cursor_hidden=True;self.window.setCursor(Qt.CursorShape.BlankCursor);self.video.setCursor(Qt.CursorShape.BlankCursor)
 def follow_stick(self):
  """The right stick leans the Games page's art, as the pointer does, while the controller is on the page."""
  state=getattr(self.pad,'state',None)
  if state is None or self.values['page']!='games' or not self.animations:return
  x=(state.rx-128)/128;y=(state.ry-128)/128
  x=0.0 if abs(x)<.2 else max(-1.0,min(1.0,x));y=0.0 if abs(y)<.2 else max(-1.0,min(1.0,y))
  self.put('parallax',{'x':round(x,2),'y':round(y,2)})

 # Pages.
 def show_page(self,name):
  page=self.values['page']
  if name==page:return
  self.close_popup()
  # The small window holds only the picture, so any other page brings the full window back.
  if self.values['mini'] and name!='live':self.small_window()
  if name=='media':self.open_media()
  games_shown=name=='games'
  if name in ('media','settings') and page in ('games','live'):self.back_page=page
  # The game's sound carries on behind Media and Settings, where only the picture is out of sight.
  self.app.video_hidden=name!='live';self.app.sound_hidden=games_shown;self.pad.navigating=name!='live'
  if name=='live':self.revealed_at=time.perf_counter()
  else:
   self.has_video=False;self.last_info=0
   if self.presenter:self.presenter.frame=None
  self.sounds.show(games_shown);self.put('page',name)
  if name=='settings':self.refresh_settings()
  if games_shown:self.shelf_state.settle_later()
  self.last_info=0
 def show_games(self,on):self.show_page('games' if on else 'live')
 def next_tab(self,step):
  page=self.values['page'];return TABS[(TABS.index(page)+step)%len(TABS)] if page in TABS else 'games'
 def set_gaming(self,on):
  self.put('gaming',on);self.pad.ps_leaves=on
  if on!=self.values['fullscreen']:self.full()
  # Leaving Gaming Mode stays on whichever page was showing.
  if on:self.show_games(True)
  self.shelf_state.exit_label='Exit Gaming Mode' if on else ''
 def full(self):
  if self.values['mini']:self.small_window()
  on=not self.values['fullscreen'];self.put('fullscreen',on)
  # Back from full screen to the state before it: a maximized window comes back maximized.
  if on:self.was_maximized=self.window.visibility()==QWindow.Visibility.Maximized;self.window.showFullScreen()
  elif getattr(self,'was_maximized',False):self.window.showMaximized()
  else:self.window.showNormal()
  self.pointer_moved();self.place_session()
 def place_session(self):
  # The session panel belongs to the live view, and only if the window has room for it.
  visible=self.session_wanted and self.values['page']=='live' and not self.values['fullscreen'] and not self.values['mini'] and self.window.width()>=1180
  if visible!=self.dock_visible:self.dock_visible=visible;self.last_info=0
 def geometry_text(self):
  g=self.window.geometry();return f'{g.width()}x{g.height()}+{g.x()}+{g.y()}'
 def small_window(self):
  """Only the picture, in a small window above every other one: Ctrl+M or its button, and again to come back."""
  import re
  window=self.window
  if not self.values['mini']:
   if self.values['gaming']:self.set_gaming(False)
   if self.values['fullscreen']:self.full()
   if self.values['page']!='live':self.show_page('live')
   self.mini_place=(window.geometry(),window.visibility()==QWindow.Visibility.Maximized)
   if self.mini_place[1]:window.showNormal()
   self.put('mini',True);window.setMinimumSize(QSize(320,180))
   screen=window.screen().availableGeometry();place=self.core.config().get('mini_geometry');found=re.fullmatch(r'(\d+)x(\d+)\+(-?\d+)\+(-?\d+)',place) if isinstance(place,str) else None
   if found and 160<=int(found[1])<=2000 and 90<=int(found[2])<=1200 and screen.left()<=int(found[3])<screen.right()-100 and screen.top()<=int(found[4])<screen.bottom()-100:
    width,height,x,y=map(int,found.groups())
   else:width,height=480,270;x=screen.right()-width-28;y=screen.bottom()-height-80
   window.setGeometry(x,y,width,height)
   # Above every other window, set on the window itself: changing Qt's flags would make a new native window and lose the swap chain.
   user32.SetWindowPos(self.hwnd,HWND_TOPMOST,0,0,0,0,NO_MOVE_SIZE)
  else:
   self.core.save_config(mini_geometry=self.geometry_text());geometry,zoomed=self.mini_place
   user32.SetWindowPos(self.hwnd,HWND_NOTOPMOST,0,0,0,0,NO_MOVE_SIZE)
   self.put('mini',False);window.setMinimumSize(QSize(900,620));window.setGeometry(geometry)
   if zoomed:window.showMaximized()
  self.place_session()

 # The console.
 def follow_console(self,now):
  """Runs once for each status, so the console's menu leaves the screen as soon as the status shows it."""
  app=self.app;playing=running_title(app.link.status);gaming=self.values['gaming']
  if app.link.online:
   change=self.flow.update(playing,now)
   if change in ('started','closed'):app.event('Game '+change+' on the PS5')
   if change=='started':self.opened_title=playing;self.opened_at=now;self.show_games(False)
   elif change=='closed':
    # A game opened from the library comes back to it, and one that died at once says so instead of leaving the console's menu on screen.
    if self.opened_title and now-self.opened_at<5:self.say(app.link.game_name(self.opened_title)+' closed as soon as it started.')
    if gaming or self.opened_title:self.show_games(True)
    self.opened_title=''
   elif change=='launch':
    if not app.link.launch(self.flow.waiting,self.launched):self.flow.waiting=None
   elif change=='failed':self.say('The PS5 did not start the game.')
   if self.first_status:
    # Connecting while a game is already open goes straight to it.
    self.first_status=False
    if playing:
     self.shelf_state.go_to_title(playing);self.games.replace(self.shelf_state.tiles())
     if not menu_in_front(app.link.status):self.show_games(False)
  covered=menu_in_front(app.link.status)
  # Someone in Media or Settings stays there, whatever the console's menu does.
  if gaming and covered!=self.menu_was_in_front and self.values['page'] in ('games','live'):
   if covered:self.show_games(True)
   # The console names the game again while its menu is still fading out.
   elif playing:QTimer.singleShot(300,self.reveal_game)
  self.menu_was_in_front=covered
 def say(self,text):
  self.app.notify(text);self.sounds.play('error')
 def ask_first(self,title,text,action,command):
  self.dialog_command=command;self.put('dialog',dict(title=title,text=text,action=action))
 def do_dialog_accept(self,_):
  command,self.dialog_command=self.dialog_command,None;self.put('dialog',{})
  if command:command()
 def do_dialog_cancel(self,_):self.dialog_command=None;self.put('dialog',{})
 def close_game(self):
  title=running_title(self.app.link.status)
  if not title:self.app.notify('No game is open.');return
  def close():
   # The console's menu comes back as the game goes, and in Gaming Mode it never reaches the screen.
   if self.values['gaming']:self.show_games(True)
   self.app.link.send(CLOSE)
  self.ask_first('Close this game?',self.app.link.game_name(title)+' closes on your PS5. Anything not saved in the game is lost.','Close game',close)
 def soft_reset(self):
  title=running_title(self.app.link.status)
  if not title:self.app.notify('No game is open.');return
  def again():
   if self.values['gaming']:self.show_games(True)
   self.flow.replace(title,time.perf_counter());self.app.link.send(CLOSE)
  self.ask_first('Restart this game?',self.app.link.game_name(title)+' closes and starts again. Anything not saved in the game is lost.','Restart game',again)
 def rest_console(self):self.ask_first('Put your PS5 to rest?','The game stops and this session ends. You may need to load your exploit again when the PS5 comes back.','Rest',lambda:self.app.console_power(REST))
 def reboot_console(self):self.ask_first('Reboot your PS5?','The game stops and this session ends. You will need to load your exploit again when the PS5 comes back.','Reboot',lambda:self.app.console_power(REBOOT))
 def power_off_console(self):self.ask_first('Turn off your PS5?','The game stops and this session ends. You will need to load your exploit again next time.','Turn off',lambda:self.app.console_power(POWER_OFF))
 def recovery_console(self):
  # The flag that asks for Safe Mode shares its values with the ones that format the console, so PlayBridge never writes it.
  self.ask_first('Recovery (Safe Mode)','Safe Mode starts from the console itself. Turn the PS5 off here, hold its power button until the second beep, about 7 seconds, and connect the controller with a USB cable.\n\nTo leave, choose Restart PS5. Never choose Update System Software or any reset: PlayBridge needs firmware 13.60. Load your exploit again afterwards.','Turn off',lambda:self.app.console_power(POWER_OFF))
 def start_game(self,title):
  # An open game comes back at once. Another game has to wait until this one has closed.
  app=self.app;running=running_title(app.link.status)
  if title==running:
   # Nothing on the PC can bring a game forward while the console shows its menu.
   if self.values['gaming'] and menu_in_front(app.link.status):self.say('Your PS5 is showing its menu. Press the PS button on your controller to go back to the game.')
   else:self.show_games(False)
   return
  if title in (self.flow.waiting,self.flow.after_close):return
  if not app.link.online:self.say('Connect to your PS5 first.');return
  def launch():
   self.flow.launch(title,time.perf_counter())
   if not app.link.launch(title,self.launched):self.flow.waiting=None;self.say('The PS5 is not connected.')
  if not running:launch();return
  def replace():self.flow.replace(title,time.perf_counter());app.link.send(CLOSE)
  self.ask_first('Switch games?',app.link.game_name(running)+' closes first. Anything not saved in it is lost.','Switch',replace)
 def launched(self,result):
  if result:self.flow.waiting=None;self.say(f'The PS5 did not start the game ({result:#010x}).')
 def reveal_game(self):
  # In Gaming Mode the console's menu stays on the TV, whether no game is open or the menu covers one.
  if self.values['gaming'] and (not running_title(self.app.link.status) or menu_in_front(self.app.link.status)):return
  self.show_games(False)
 def disconnect(self):
  app=self.app;app.intentional_disconnect=True
  if app.sock:
   try:app.sock.shutdown(socket.SHUT_RDWR)
   except OSError:pass
 def connect_toggle(self):
  if self.app.worker.is_alive():self.disconnect()
  else:self.app.restart()
 def toggle_live(self):
  app=self.app
  if app.broadcast.active:app.end_live();return
  saved=self.core.config();kind=saved.get('live_service');key=live_broadcast.unseal(saved.get('live_key',''));server=saved.get('live_server','')
  ready=kind=='obs' or kind in ('twitch','youtube') and key or kind=='custom' and server
  if not ready:self.show_page('settings');self.section='live';self.say_line('Choose where to go live, then select Go live.');return
  problem=app.go_live(kind,key,server)
  if problem:self.say(problem)
 def set_microphone(self,on):
  """Your voice in recordings, instant replays and Go live. The choice is kept, and a microphone that will not open says why."""
  app=self.app;core=self.core
  if on and not app.microphone.open(core.config().get('mic_device','')):
   core.save_config(mic_on=False);app.notify('Microphone could not open: '+app.microphone.error);app.notice_until=time.perf_counter()+15;self.refresh_settings();return
  if not on:app.microphone.close()
  core.save_config(mic_on=on)
  app.notify(f'Microphone on: {app.microphone.name}. Your voice goes into recordings, replays and Go live.' if on else 'Microphone off.');self.refresh_settings()

 # The controller and the keys.
 def pad_event(self,event):
  if self.values['dialog']:
   if event=='accept':self.do_dialog_accept(None)
   elif event in ('back','leave'):self.do_dialog_cancel(None)
   return
  if self.values['popup']:self.popup_answer(event);return
  if self.values['consoleCaptures']:
   if event in ('back','leave'):self.do_ps5_close(None)
   else:self.navigate.emit(event)
   return
  page=self.values['page']
  if page=='games':
   if event in ('back','leave'):
    if self.shelf_state.dismiss():self.show_shelf()
    elif running_title(self.app.link.status):self.reveal_game()
   # The shoulder buttons go through the tabs, as they do on the console.
   elif event=='next' and not self.shelf_state.menu:self.show_page(self.next_tab(1))
   elif event=='previous' and not self.shelf_state.menu:self.show_page(self.next_tab(-1))
   else:self.shelf_state.navigate(event);self.show_shelf()
  elif page=='live':
   if event=='leave':self.show_games(True)
  elif event in ('back','leave'):self.show_page(self.back_page)
  elif event=='next':self.show_page(self.next_tab(1))
  elif event=='previous':self.show_page(self.next_tab(-1))
  elif event in ('up','down','left','right','accept'):self.navigate.emit(event)
 def do_key(self,key):
  """The keys that are the same on every page."""
  page=self.values['page']
  if key=='escape':
   if self.values['dialog']:self.do_dialog_cancel(None)
   elif self.values['popup']:self.close_popup()
   elif self.values['consoleCaptures']:self.do_ps5_close(None)
   elif page=='games' and self.shelf_state.dismiss():self.show_shelf()
   elif page in ('media','settings'):self.show_page(self.back_page)
   elif self.values['gaming']:self.set_gaming(False)
   elif self.values['mini']:self.small_window()
   elif self.values['fullscreen']:self.full()
  elif key=='f11':self.full()
  elif key=='session':self.toggle_session()
  elif key=='media':self.show_page('media')
  elif key=='settings':self.show_page('settings')
  elif key=='screenshot':self.app.take_screenshot()
  elif key=='record':self.app.toggle_recording()
  elif key=='replay':self.app.save_replay()
  elif key=='mic':self.set_microphone(not self.app.microphone.on)
  elif key=='f6':self.reveal_game() if page=='games' else self.show_games(True)
  elif key=='gaming':self.set_gaming(not self.values['gaming'])
  elif key=='mini':self.small_window()
  elif key=='live':self.toggle_live()
 def do_nav(self,event):
  """Arrows, Enter and Page Up/Down on the Games page and in menus."""
  if self.values['popup']:self.popup_answer(event);return
  if self.values['page']=='games':self.shelf_state.navigate(event);self.show_shelf()
 def toggle_session(self):
  self.session_wanted=not self.dock_visible;self.core.save_config(session_panel=self.session_wanted)
  if self.session_wanted and self.values['page']!='live':self.show_page('live')
  self.place_session()

 # The Games page.
 def show_shelf(self):
  view=self.shelf_state.view();view['hints']=[dict(key=key,text=text.format(action=view['action'] or 'Select')) for key,text in KEY_HINTS];view['padHints']=[dict(key=key,text=text.format(action=view['action'] or 'Select')) for key,text in PAD_HINTS]
  view['online']=self.app.link.online;view['info']=self.top_info;view['refreshing']=bool(self.app.link.refreshing)
  # The picture behind the page: the game's art, or its cover when it has none.
  title=view['title'];view['art']=file_url(self.app.link.art(title)) if title else '';view['cover']=file_url(self.app.link.icon(title)) if title else ''
  self.put('shelf',view)
 def do_move(self,change):self.shelf_state.move(int(change));self.show_shelf()
 def do_go(self,index):
  index=int(index)
  if index==self.shelf_state.target:self.shelf_state.choose()
  else:self.shelf_state.go_to(index)
  self.show_shelf()
 def do_choose(self,_):self.shelf_state.choose();self.show_shelf()
 def do_shelf(self,key):self.shelf_state.set_shelf(key);self.games.replace(self.shelf_state.tiles());self.show_shelf()
 def do_more(self,_):self.shelf_state.open_menu('more');self.show_shelf()
 def do_menu_choose(self,index):
  if self.values['popup']:self.popup_choose(int(index))
  else:self.shelf_state.menu_choose(int(index));self.show_shelf()
 def do_menu_close(self,_):
  if self.values['popup']:self.close_popup()
  elif self.shelf_state.dismiss():self.show_shelf()
 def do_type(self,text):
  before=self.shelf_state.tiles_version;self.shelf_state.type_text(str(text))
  if before!=self.shelf_state.tiles_version:self.games.replace(self.shelf_state.tiles())
  self.show_shelf()
 def do_erase(self,_):
  before=self.shelf_state.tiles_version;self.shelf_state.erase()
  if before!=self.shelf_state.tiles_version:self.games.replace(self.shelf_state.tiles())
  self.show_shelf()
 def do_search(self,on):
  if on:self.show_games(True);self.shelf_state.start_search()
  else:self.shelf_state.stop_search();self.games.replace(self.shelf_state.tiles())
  self.show_shelf()
 def do_tab(self,key):
  """The top bar's tabs and buttons."""
  self.sounds.play('accept')
  if key=='games':self.show_games(True)
  elif key=='power':self.power_menu()
  elif key=='search':self.do_search(not (self.shelf_state.searching or self.shelf_state.text) or self.values['page']!='games')
  # On the live view this is plain fullscreen. Elsewhere it is the library's button.
  elif key=='fullscreen' and self.values['page']=='live':self.full()
  elif key in self.actions:self.actions[key]()
 def power_menu(self):
  if self.values['page']=='games':self.shelf_state.open_menu('power');self.show_shelf();return
  items=power_items(self.app.link.online,running_title(self.app.link.status),'Exit Gaming Mode' if self.values['gaming'] else '')
  if not items:self.say('Connect to your PS5 first.');return
  self.sounds.play('move');self.put('popup',dict(kind='power',selected=0,items=[dict(key=key,label=label) for key,label in items]))
 def popup_answer(self,event):
  popup=dict(self.values['popup'])
  if event in ('up','down'):popup['selected']=(popup['selected']+(1 if event=='down' else -1))%len(popup['items']);self.sounds.play('move');self.put('popup',popup)
  elif event=='accept':self.popup_choose(popup['selected'])
  elif event in ('back','leave'):self.close_popup();self.sounds.play('back')
 def popup_choose(self,index):
  items=self.values['popup'].get('items',[]);self.close_popup()
  if 0<=index<len(items):self.sounds.play('accept');self.actions[items[index]['key']]()
 def close_popup(self):self.put('popup',{})

 # The footer.
 def device_label(self,name):
  return (name or '').replace('Altifalantes','Speakers').replace('Auscultadores','Headphones').replace('Saída digital','Digital output')
 def audio_outputs(self):
  apis=sd.query_hostapis();devices=sd.query_devices();self.devices=devices;self.apis=apis
  self.outputs=[(index,self.device_label(device['name'])) for index,device in enumerate(devices) if device['max_output_channels']>=2 and apis[device['hostapi']]['name']=='Windows WASAPI']
 def do_output(self,label):
  app=self.app
  # An output that will not open is not saved, so the next start does not try it first.
  index=next((index for index,name in self.outputs if name==label),None)
  if index is None:return
  if app.open_audio(index):self.core.save_config(output=self.devices[index]['name']+' ['+self.apis[self.devices[index]['hostapi']]['name']+']')
  self.sounds.reopen();self.last_info=0
 def do_mute(self,_):self.app.muted=not self.app.muted;self.last_info=0
 def do_volume(self,value):self.app.volume=max(0.0,min(1.0,float(value)))
 def do_screenshot(self,_):self.app.take_screenshot()
 def do_record(self,_):self.app.toggle_recording();self.last_info=0
 def do_replay(self,_):self.app.save_replay()
 def do_mini(self,_):self.small_window()
 def do_live(self,_):self.toggle_live();self.last_info=0
 def do_session(self,_):self.toggle_session()
 def do_connect(self,_):self.connect_toggle();self.last_info=0
 def do_page(self,name):
  if name in TABS or name=='settings':self.show_page(name)
 def do_video_double(self,_):
  if self.values['mini']:self.small_window()
  else:self.full()
 def do_pointer(self,_):self.pointer_moved()
 def do_power(self,key):
  if key in self.actions:self.actions[key]()
 def do_export(self,url):
  path=QUrl(str(url)).toLocalFile() if str(url).startswith('file:') else str(url)
  if path:self.app.export_diagnostics(path)

 # Settings: every setting applies the moment it changes, except the address, which waits for Save or Enter.
 def say_line(self,text,tone='plain',keep=False):
  """The line under Console and Picture. A confirmation fades after a few seconds; a problem, or an address waiting for Save, stays."""
  self.say_text=(text,tone);self.say_until=None if tone=='error' or keep or not text else time.perf_counter()+6;self.refresh_settings()
 def reopen_line(self):self.say_line('Saved. It takes effect the next time PlayBridge opens.','news')
 def refresh_settings(self):
  app=self.app;core=self.core;saved=core.config();profiles=core.PROFILES
  favourites=saved_consoles(saved,profiles);match=next((item for item in favourites if item['host']==app.args.host),None)
  found=self.found_cards;automatic='Automatic: '+graphics_card.label(graphics_card.automatic(found),found) if len(found)>1 else ''
  kept_card=saved.get('graphics_card',graphics_card.AUTOMATIC);names=[item['name'] for item in found]
  if not hasattr(self,'vrr_supported'):
   # Only where the screen can follow it: a screen with a fixed rate would tear, so the switch would do nothing there.
   try:from d3d11_presenter import screen_varies,tearing_supported;self.vrr_supported=self.direct and tearing_supported() and screen_varies(self.presenter.hwnd) is not False
   except Exception:self.vrr_supported=False
  vrr_supported=self.vrr_supported;mics=self.mic_names;kept_mic=saved.get('mic_device','')
  files_encoder,live_encoder=self.encoders if self.encoders else (False,False)
  if self.encoders is None:compact_note=live_note='Looking for this PC\'s video encoders…'
  else:
   compact_note='This PC has no encoder for this, so recordings stay as the PS5 made them.' if files_encoder is None else f'After each recording or replay is saved, PlayBridge makes its video again with {video_encoders.NAMES.get(files_encoder,files_encoder)}, at about a third of the size, and keeps the sound as it is. It works only while no stream plays, and the original goes to the Recycle Bin once the new file has been checked.'
   live_note='This PC\'s graphics card makes neither HEVC nor AV1, so the stream always goes as the PS5 sent it.' if live_encoder is None else f'{video_encoders.NAMES.get(live_encoder,live_encoder)} makes the video again at about a quarter of the PS5\'s bitrate (4K at about {video_encoders.bitrate(live_encoder,2160,live=True)//1_000_000} Mbps), for a slower upload. It uses the graphics card\'s encoder, not the processor.'
  service=saved.get('live_service') if saved.get('live_service') in live_broadcast.SERVICES else 'twitch'
  live_status=self.live_status or (LIVE_HINTS[service],'plain')
  if app.broadcast.state=='live':live_status=('Live on '+app.broadcast.name+' for '+live_broadcast.clock(app.broadcast.elapsed())+'.','news')
  self.put('settings',dict(
   section=self.section,sections=[dict(key=key,label=label,note=note) for key,label,note in SECTIONS],line=dict(text=self.say_text[0],tone=self.say_text[1]),fill=self.fill,
   host=app.args.host,favourites=[item['name']+' · '+item['host'] for item in favourites],consoleName=match['name'] if match else '',
   found=list(self.discovered) or (['No console found'] if self.scan_status.startswith('No console') else ['Select a console']),foundLabel=self.found_label,scanning=self.scanning,scanStatus=self.scan_status,
   favouriteStatus=dict(text=self.favourite_status[0],tone=self.favourite_status[1]),reconnect=bool(app.args.auto_reconnect),manual=bool(app.args.connect_only),notices=bool(saved.get('ps5_notices',False)),
   recent=[self.payload_label(item) for item in self.recent_payloads()] or ['No payload sent yet'],payloadStatus=dict(text=self.payload_status[0],tone=self.payload_status[1]),
   profiles=[value['name'] for value in profiles.values()],profile=profiles[app.args.profile]['name'],cardSummary=graphics_card.summary(app.graphics()),
   cards=([automatic]+names) if len(found)>1 else [],card=(kept_card if kept_card in names else automatic) if len(found)>1 else '',
   diagnostic=self.diagnostic,gpuOutput=bool(saved.get('direct_video',True)),matchRefresh=self.match_on,direct=self.direct,sharpen=bool(self.presenter.sharpen) if self.direct else False,fsr=bool(self.presenter.fsr) if self.direct else False,
   vrrSupported=vrr_supported,vrr=bool(saved.get('vrr',False)),
   replayLengths=list(REPLAY_LENGTHS),replay=next((label for label,seconds in REPLAY_LENGTHS.items() if seconds==app.replay.seconds),'Last 60 seconds'),
   mic=bool(app.microphone.on),mics=[DEFAULT_MIC]+mics,micDevice=kept_mic if kept_mic in mics else DEFAULT_MIC,micLevel=float(app.mic_mix.level),micMax=float(mic_mix.LEVEL_MAX),
   captureFolder=str(app.capture_folder()),compact=bool(saved.get('compact_recordings',False)),compactNote=compact_note,compactProgress=app.compactor.status(),
   services=list(live_broadcast.SERVICES.values()),service=live_broadcast.SERVICES[service],serviceKey=service,server=saved.get('live_server','') if isinstance(saved.get('live_server'),str) else '',
   key=live_broadcast.unseal(saved.get('live_key','')),compressible=service in live_broadcast.COMPRESSIBLE,compress=bool(saved.get('live_compress',False)),compressNote=live_note,
   liveStatus=dict(text=live_status[0],tone=live_status[1]),liveActive=bool(app.broadcast.active),
   music=bool(self.sounds.music_on),cues=bool(self.sounds.effects_on),level=float(self.sounds.volume),gamingOnStart=bool(saved.get('gaming_mode',False)),animations=self.animations,qt=saved.get('ui','qt')=='qt',
   update=dict(app.updates.status(),text=app.updates.text(),source=not getattr(sys,'frozen',False))))
 def refresh_look(self):
  backdrop=self.core.STATE/'qt'/'backdrop.png'
  if not backdrop.is_file():
   try:
    from scene import no_art
    backdrop.parent.mkdir(parents=True,exist_ok=True);no_art((1920,1080)).save(backdrop)
   except Exception:backdrop=None
  self.put('look',dict(animations=self.animations,backdrop=file_url(backdrop) if backdrop else '',icons=(self.core.HERE/'assets').resolve().as_uri()+'/'))
 def do_section(self,key):
  if key in dict((k,0) for k,_,_ in SECTIONS):self.section=key;self.refresh_settings()
 def save(self,typed=None,reach=False,profile=None):
  """Keeps what Console and Picture say the moment it changes. reach: the user asked for this console, so PlayBridge connects to it when it is not connected yet."""
  app=self.app;core=self.core;typed=(typed if typed is not None else self.typed_host or app.args.host).strip()
  try:ipaddress.IPv4Address(typed)
  except ValueError:self.say_line('Enter a valid IPv4 address, such as 192.168.1.20.' if typed else 'Enter your PS5\'s IP address.','error');return
  chosen_profile=profile or self.typed_profile or app.args.profile;self.typed_profile=None;before=(app.args.host,app.args.connect_only,app.args.profile,app.args.auto_reconnect)
  running=app.worker.is_alive();new_host=typed!=app.args.host;new_profile=chosen_profile!=app.args.profile
  # A new connection sends the ELF again, so only a new address, a new profile while connected, or an asked-for console starts one.
  connect=new_host or (new_profile and running) or (reach and not running)
  # A new address from the user is kept from now on, even when another PS5 answers.
  if new_host:app.follow=False
  app.args.host,app.args.profile=typed,chosen_profile;self.typed_host=None
  core.save_config(host=app.args.host,host_auto=app.follow,connect_only=app.args.connect_only,profile=app.args.profile,auto_reconnect=app.args.auto_reconnect)
  name=core.PROFILES[chosen_profile]['name']
  if connect:self.say_line(f'Reconnecting with {name}…' if new_profile and not new_host else f'Connecting to the PS5 at {typed}…','news')
  elif new_profile:self.say_line(f'Saved. {name} is used the next time you connect.')
  elif before!=(app.args.host,app.args.connect_only,app.args.profile,app.args.auto_reconnect):self.say_line('Saved.')
  elif reach:self.say_line(f'Saved. Already connected to the PS5 at {typed}.' if app.connection_state=='Connected' else f'Saved. Still connecting to the PS5 at {typed}…')
  self.refresh_settings()
  if not connect:return
  self.disconnect()
  def connect_when_ready():
   if app.stop.is_set():return
   if app.worker.is_alive():QTimer.singleShot(100,connect_when_ready)
   else:app.restart()
  QTimer.singleShot(100,connect_when_ready)
 def do_host_save(self,text):self.save(str(text),True)
 def do_host_left(self,text):
  """Leaving the address field: nothing waits when it is the address in use; a new one waits for Save, and a wrong one says so."""
  typed=str(text).strip();self.typed_host=typed
  if typed==self.app.args.host:self.say_line('')
  else:
   try:ipaddress.IPv4Address(typed);self.say_line(f'Press Save to connect to {typed}.','news',keep=True)
   except ValueError:self.say_line('Enter a valid IPv4 address, such as 192.168.1.20.','error')
 def do_favourite(self,label):
  favourites={item['name']+' · '+item['host']:item for item in saved_consoles(self.core.config(),self.core.PROFILES)}
  item=favourites.get(label)
  if item is None:return
  # Its profile applies at once, as the profile menu does; a different address waits for Save, and Save then uses both.
  self.put_fields(item['host'],item['name'])
  if item['host']==self.app.args.host:self.save(item['host'],profile=item['profile'])
  else:
   self.typed_host=item['host'];self.typed_profile=item['profile']
   self.say_line(f"Press Save to connect to {item['host']}.",'news',keep=True)
 def put_fields(self,host,name=None):
  self.fill=dict(host=host,name=self.fill['name'] if name is None else name,version=self.fill['version']+1);self.refresh_settings()
 def do_scan(self,typed):
  if self.scanning:return
  self.scanning=True;self.scan_status='Searching the local network…';preferred=str(typed or self.app.args.host).strip();self.refresh_settings()
  def work():
   from console_discovery import discover
   try:self.scan_results.put((discover(preferred),None))
   except Exception:self.scan_results.put(([],'Network scan failed. You can still enter the IP manually.'))
  threading.Thread(target=work,name='Console discovery',daemon=True).start()
 def finish_scan(self,items,problem):
  self.scanning=False;self.discovered={item['name']+' · '+item['ip']:item['ip'] for item in items}
  if self.discovered:
   label=next(iter(self.discovered));self.found_label=label;self.scan_status='Choose your console above, then press Save to connect.' if len(self.discovered)>1 else 'Found it. Press Save to connect.'
   self.typed_host=self.discovered[label];self.put_fields(self.typed_host)
  else:self.found_label='No console found';self.scan_status=problem or 'No console found. Enter the IP manually; check Payload Manager.'
  self.refresh_settings()
 def do_found(self,label):
  if label in self.discovered:
   self.found_label=label;self.typed_host=self.discovered[label];self.say_line(f'Press Save to connect to {self.typed_host}.','news',keep=True);self.put_fields(self.typed_host)
 def do_favourite_save(self,value):
  value=dict(value or {})
  try:items=remember_console(self.core.config(),str(value.get('name','')),str(value.get('host','')),self.app.args.profile,self.core.PROFILES)
  except ValueError:self.favourite_status=('Enter a valid console IP address.','error');self.refresh_settings();return
  self.core.save_config(consoles=items);self.favourite_status=('Favourite saved with this quality profile.','news');self.refresh_settings()
 def do_reconnect(self,on):self.app.args.auto_reconnect=bool(on);self.save()
 def do_manual(self,on):
  self.app.args.connect_only=bool(on);self.core.save_config(connect_only=bool(on));self.say_line('Saved. Used the next time PlayBridge connects.')
 def do_notices(self,on):self.core.save_config(ps5_notices=bool(on));self.say_line('Saved. Used the next time PlayBridge connects.')
 def recent_payloads(self):return [item for item in self.core.config().get('recent_payloads',[]) if isinstance(item,str)]
 def payload_label(self,path):return Path(path).name+'  ·  '+(Path(path).parent.name or str(Path(path).parent))
 def do_payload_recent(self,label):
  path=next((item for item in self.recent_payloads() if self.payload_label(item)==label),None)
  if path:self.send_file(path)
 def do_payload_file(self,url):
  path=QUrl(str(url)).toLocalFile() if str(url).startswith('file:') else str(url)
  if path:self.send_file(path)
 def send_file(self,path):
  typed=(self.typed_host or self.app.args.host).strip()
  try:ipaddress.IPv4Address(typed)
  except ValueError:self.payload_status=('Enter a valid console IP address above first.','error');self.refresh_settings();return
  try:data=payload_sender.read_payload(path)
  except payload_sender.PayloadError as problem:self.payload_status=(str(problem),'error');self.refresh_settings();return
  name=Path(path).name
  def send():
   self.core.save_config(recent_payloads=payload_sender.remember(self.recent_payloads(),path));self.payload_status=(f'Sending {name}…','plain');self.refresh_settings()
   def work():
    try:payload_sender.send_payload(typed,data);self.payload_results.put((name,typed,None))
    except payload_sender.PayloadError as problem:self.payload_results.put((name,typed,str(problem)))
   threading.Thread(target=work,name='PlayBridge payload',daemon=True).start()
  self.ask_first('Send this payload?',f'{name}  ·  {payload_sender.size_label(len(data))}\nto the PS5 at {typed}.\n\nIt runs with full access to the console. Send only files you trust.','Send',send)
 def finish_payload(self,name,typed,problem):
  if problem:self.payload_status=(problem,'error')
  else:self.payload_status=(f'{name} reached the loader on {typed}.','news');self.app.notify(f'{name} sent to the PS5.')
  self.refresh_settings()
 def do_profile(self,label):
  chosen=next((key for key,value in self.core.PROFILES.items() if value['name']==label),None)
  if chosen:self.save(profile=chosen)
 def do_card(self,label):
  self.core.save_config(graphics_card=graphics_card.AUTOMATIC if str(label).startswith('Automatic: ') else label);self.reopen_line()
 def do_diagnostic(self,on):self.diagnostic=bool(on);self.core.save_config(diagnostic=self.diagnostic);self.refresh_settings()
 def do_gpu_output(self,on):self.core.save_config(direct_video=bool(on));self.reopen_line()
 def do_match(self,on):self.match_on=bool(on);self.core.save_config(match_refresh=self.match_on);self.refresh_settings()
 def do_sharpen(self,on):
  if self.direct:self.presenter.sharpen=bool(on);self.core.save_config(sharpen=bool(on));self.refresh_settings()
 def do_fsr(self,on):
  if self.direct:self.presenter.fsr=bool(on);self.core.save_config(fsr=bool(on));self.refresh_settings()
 def do_vrr(self,on):self.core.save_config(vrr=bool(on));self.reopen_line()
 def do_replay_length(self,label):
  if label in REPLAY_LENGTHS:self.app.replay.resize(REPLAY_LENGTHS[label]);self.core.save_config(replay_seconds=REPLAY_LENGTHS[label]);self.refresh_settings()
 def do_mic(self,on):self.set_microphone(bool(on))
 def do_mic_device(self,label):
  self.core.save_config(mic_device='' if label==DEFAULT_MIC else label)
  if self.app.microphone.on:self.set_microphone(True)
  self.refresh_settings()
 def do_mic_level(self,value):self.app.mic_mix.level=max(0.0,min(float(mic_mix.LEVEL_MAX),float(value)))
 def do_mic_level_done(self,_):self.core.save_config(mic_level=round(self.app.mic_mix.level,2))
 def do_capture_folder(self,url):
  folder=QUrl(str(url)).toLocalFile() if str(url).startswith('file:') else str(url)
  if folder:self.core.save_config(capture_folder=folder);self.app.notify('Capture folder updated.');self.refresh_settings()
 def do_compact(self,on):
  self.core.save_config(compact_recordings=bool(on))
  if on:self.app.compactor.resume(self.core.config().get('compact_waiting',[]))
  self.refresh_settings()
 def do_live_service(self,label):
  kind=next((key for key,name in live_broadcast.SERVICES.items() if name==label),None)
  if kind:self.core.save_config(live_service=kind);self.live_status=None;self.refresh_settings()
 def do_live_check(self,value):
  """Says what is wrong with the key or the address while it is typed, before Go live is pressed. An empty field waits."""
  if self.app.broadcast.active:return
  value=dict(value or {});kind=self.values['settings'].get('serviceKey','twitch');key=str(value.get('key','')).strip();server=str(value.get('server','')).strip()
  try:
   if key or (kind=='custom' and len(server)>=10):live_broadcast.destination(kind,key or 'k',server)
  except ValueError as problem:self.live_status=(str(problem),'error');self.refresh_settings();return
  self.live_status=None;self.refresh_settings()
 def do_live_go(self,value):
  app=self.app
  if app.broadcast.active:app.end_live();self.live_status=('The live stream ended.','plain');self.refresh_settings();return
  value=dict(value or {});kind=self.values['settings'].get('serviceKey','twitch');key=str(value.get('key','')).strip();server=str(value.get('server','')).strip()
  # The key is kept encrypted for this Windows user.
  self.core.save_config(live_service=kind,live_server=server,live_key=live_broadcast.seal(key))
  problem=app.go_live(kind,key,server)
  self.live_status=(problem,'error') if problem else ('Waiting for the next keyframe…','plain');self.refresh_settings()
 def do_live_compress(self,on):self.core.save_config(live_compress=bool(on));self.refresh_settings()
 def do_music(self,on):self.sounds.set_music(bool(on));self.core.save_config(sound_music=bool(on));self.refresh_settings()
 def do_cues(self,on):self.sounds.effects_on=bool(on);self.core.save_config(sound_cues=bool(on));self.sounds.play('move');self.refresh_settings()
 def do_library_volume(self,value):self.sounds.volume=max(0.0,min(1.0,float(value)))
 def do_library_volume_done(self,_):self.core.save_config(sound_level=self.sounds.volume)
 def do_gaming_on_start(self,on):self.core.save_config(gaming_mode=bool(on));self.refresh_settings()
 def do_animations(self,on):self.animations=bool(on);self.core.save_config(animations=self.animations);self.refresh_settings();self.refresh_look()
 def do_qt(self,on):self.core.save_config(ui='qt' if on else 'tk');self.reopen_line()
 # Updates.
 def do_update_check(self,value):self.app.updates.check_now()
 def do_update_auto(self,on):self.app.updates.set_automatic(on);self.core.save_config(update_auto=bool(on));self.refresh_settings()
 def do_update_install(self,value):
  if self.app.updates.status()['installable']:self.app.restart_after_update=True;self.close()
 def do_update_page(self,value):QDesktopServices.openUrl(QUrl(self.app.updates.page or f'https://github.com/{updater.REPOSITORY}/releases/latest'))
 def do_cue(self,name):self.sounds.play(str(name))

 # The Media page.
 def open_media(self):self.media_number=0;self.load_media(True)
 def do_media_filter(self,label):
  if label in ('All','Photos','Videos'):self.media_filter=label;self.open_media()
 def do_media_refresh(self,_):self.open_media()
 def do_media_move(self,step):self.media_number=max(0,self.media_number+int(step));self.load_media(False)
 def do_media_open(self,path):
  try:os.startfile(str(path))
  except OSError:self.media_status='Unable to open this capture. Check its default app.';self.put('media',dict(self.values['media'],status=self.media_status))
 def do_media_folder(self,_):self.app.open_captures()
 def load_media(self,again):
  self.media_generation+=1;generation=self.media_generation;kind=self.media_filter;number=self.media_number;previous=list(self.media_items)
  try:folder=self.app.capture_folder()
  except OSError:self.media_status='Unable to read the capture folder.';self.media_items=[];self.show_media([]);return
  self.media_status='Loading captures…';self.put('media',dict(self.values['media'],status=self.media_status,busy=True,filter=kind))
  def work():
   try:
    items=capture_items(folder,kind) if again else previous;cards=[]
    for item in items[number*12:(number+1)*12]:
     card=capture_card(item);card['still']=self.still(item);cards.append(card)
    self.media_results.put((generation,items,cards,None))
   except Exception:self.media_results.put((generation,[],[],'Unable to read the capture folder.'))
  threading.Thread(target=work,name='Capture library',daemon=True).start()
 def still(self,item):
  """A small picture of a capture: a photo as it is, a recording's still saved once beside the settings."""
  if item.kind=='Photos':return file_url(item.path)
  key=hashlib.sha1(f'{item.path}|{item.modified}'.encode('utf8')).hexdigest()[:20];target=self.thumb_folder/(key+'.jpg')
  if not target.is_file():
   still=video_thumbnail(item.path)
   if still is None:return ''
   try:self.thumb_folder.mkdir(parents=True,exist_ok=True);still.save(target,quality=88)
   except OSError:return ''
  return file_url(target)
 def finish_media(self,generation,items,cards,error):
  if generation!=self.media_generation:return
  self.media_items=items;pages=max(1,(len(items)+11)//12);self.media_status=error or f'{len(items)} recent capture{"" if len(items)==1 else "s"} · Page {self.media_number+1} of {pages}'
  self.show_media(cards,pages)
 def show_media(self,cards,pages=None):
  pages=pages or max(1,(len(self.media_items)+11)//12)
  self.put('media',dict(cards=cards,status=self.media_status,busy=False,filter=self.media_filter,previous=self.media_number>0,next=self.media_number+1<pages,empty=not self.media_items))

 # The PS5's own captures, listed through the payload and copied on request into the capture folder.
 def do_ps5_open(self,_):
  import console_captures
  self.cc=console_captures;self.ps5=dict(found=[],chosen=set(),busy=False)
  self.put('consoleCaptures',dict(open=True,status='Asking your PS5…',rows=[],busy=False,canNew=False,canChosen=False))
  if not self.app.link.work(lambda sock:console_captures.find_captures(sock,name_of=self.app.link.game_name),lambda result:self.ps5_answers.put(('found',result))):
   self.ps5_view(status='Connect to your PS5 first. The list comes through PlayBridge\'s connection.')
 def ps5_view(self,**changes):
  if self.ps5 is None:return
  view=dict(self.values['consoleCaptures']);view.update(changes);found=self.ps5['found']
  view['busy']=self.ps5['busy'];view['canNew']=bool(found) and not self.ps5['busy'];view['canChosen']=not self.ps5['busy'] and bool(self.ps5['chosen'])
  self.put('consoleCaptures',view)
 def ps5_answer(self,kind,value):
  if self.ps5 is None:return
  if kind=='found':
   if not isinstance(value,tuple):self.ps5_view(status='The PS5 did not answer.');return
   found,old=value;self.ps5['found']=found
   if old:self.ps5_view(status='Your PS5 runs an older PlayBridge payload. Reconnect so that PlayBridge sends the current one.');return
   if not found:self.ps5_view(status='No screenshots or clips were found on your PS5.');return
   self.ps5_rows();photos=sum(c['kind']=='Photos' for c in found)
   self.ps5_view(status=f'{photos} photos and {len(found)-photos} clips on your PS5.'+(' The 400 newest are listed.' if len(found)>400 else ''))
  elif kind=='progress':self.ps5_view(status=value)
  elif kind=='done':
   done,failed=value;self.ps5['busy']=False;self.ps5_rows()
   self.ps5_view(status=f'{done} copied to your capture folder.'+(f' {failed} could not be read.' if failed else ''))
   if done and self.values['page']=='media':self.open_media()
 def ps5_rows(self):
  from datetime import datetime
  folder=self.app.capture_folder();rows=[]
  for capture in self.ps5['found'][:400]:
   when=datetime.fromtimestamp(capture['modified']).strftime('%d %b %Y  %H:%M');done='  ·  On this PC' if self.cc.copied(capture,folder) else ''
   rows.append(dict(path=capture['path'],name=capture['name'],chosen=capture['path'] in self.ps5['chosen'],detail=f"{capture['folder']}  ·  {'Photo' if capture['kind']=='Photos' else 'Clip'}  ·  {self.cc.size_label(capture['size'])}  ·  {when}{done}"))
  self.ps5_view(rows=rows)
 def do_ps5_toggle(self,path):
  if self.ps5 is None:return
  chosen=self.ps5['chosen'];chosen.symmetric_difference_update({str(path)});self.ps5_rows()
 def do_ps5_copy_new(self,_):
  if self.ps5:self.ps5_copy([c for c in self.ps5['found'] if not self.cc.copied(c,self.app.capture_folder())])
 def do_ps5_copy_chosen(self,_):
  if self.ps5:self.ps5_copy([c for c in self.ps5['found'] if c['path'] in self.ps5['chosen']])
 def ps5_copy(self,captures):
  if self.ps5['busy'] or not captures:
   if not captures:self.ps5_view(status='Everything listed is already on this PC.')
   return
  self.ps5['busy']=True;folder=self.app.capture_folder();total=len(captures);self.ps5_view()
  def job(sock):
   done=failed=0
   for index,capture in enumerate(captures,1):
    def progress(got,size,index=index,name=capture['name']):
     if got==size or got%(1<<22)<65536:self.ps5_answers.put(('progress',f'Copying {index} of {total}: {name}  ·  {got*100//max(size,1)}%'))
    if self.cc.copy_capture(sock,capture,folder,progress):done+=1
    else:failed+=1
   return done,failed
  # Clips can take minutes. The console's status waits for each file, so the video keeps its place first.
  if not self.app.link.work(job,lambda result:self.ps5_answers.put(('done',result if isinstance(result,tuple) else (0,total)))):
   self.ps5['busy']=False;self.ps5_view(status='Connect to your PS5 first.')
 def do_ps5_close(self,_):self.ps5=None;self.put('consoleCaptures',{})

def run_qt(app):
 """Opens the Qt window and runs it until it closes. Raises ImportError or RuntimeError when Qt cannot start, so the Tk window can open instead."""
 core=sys.modules[app.__class__.__module__]
 # The window's own graphics are Direct3D 11, the same as the video's, and nothing in it waits for the screen's refresh but its own drawing.
 os.environ.setdefault('QSG_RHI_BACKEND','d3d11')
 QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
 gui=QGuiApplication.instance() or QGuiApplication(sys.argv[:1]);gui.setApplicationName('PlayBridge');gui.setWindowIcon(QIcon(str(core.HERE/'assets'/'playbridge.ico')))
 shell=Shell(app,core);engine=QQmlApplicationEngine()
 engine.rootContext().setContextProperty('shell',shell);engine.rootContext().setContextProperty('gameModel',shell.games)
 shell.refresh_look();engine.addImportPath(str(QML));engine.load(QUrl.fromLocalFile(str(QML/'Main.qml')))
 if not engine.rootObjects():raise RuntimeError('The Qt window could not load its pages.')
 # The first place of the window, as the Tk one: centred in the screen's free area, a little room around it.
 window=engine.rootObjects()[0];free=(window.screen() or gui.primaryScreen()).availableGeometry()
 width,height=min(1540,free.width()-80),min(920,free.height()-110);window.setGeometry(free.x()+(free.width()-width)//2,free.y()+max(20,(free.height()-height)//2),width,height)
 shell.build(engine)
 if not window.isVisible():window.show()
 gui.exec()
 shell.close()
 # The pages go first, while the shell they read is still there; then the engine, then the shell.
 for root in engine.rootObjects():root.deleteLater()
 QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
 shell.engine=shell.window=None;engine.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
