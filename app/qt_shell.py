"""PlayBridge in Qt Quick: the pages, settings, keys and controller of the Tk window, drawn on the graphics card with glass, depth and motion.
The stream, the console link and the captures stay the Player's own. This file shows them and passes on what is chosen; the pages are in qml/."""
import ctypes,hashlib,ipaddress,os,queue,shutil,socket,subprocess,sys,threading,time
from ctypes import wintypes
from pathlib import Path
from PySide6.QtCore import QAbstractListModel,QCoreApplication,QEvent,QModelIndex,QObject,QRect,QSize,Qt,QTimer,QUrl,Property,Signal,Slot
from PySide6.QtGui import QCursor,QDesktopServices,QGuiApplication,QIcon,QImage,QWindow
from PySide6.QtQml import QQmlApplicationEngine,qmlRegisterType
from PySide6.QtQuick import QQuickWindow
import sounddevice as sd
import graphics_card,live_broadcast,mic_mix,payload_sender,phone_link,updater,video_encoders
from classic_games import ClassicArt,ClassicFrame,ClassicShelf
from qt_models import PAGES,Shelf,capture_card,controller_text,file_url,library_info,message_line,session_view
from console_control import CLOSE,GameFlow,POWER_OFF,REBOOT,REST,console_line,menu_in_front,running_title
from desktop_features import capture_items,remember_console,saved_consoles,video_thumbnail
from frame_pacing import CAPTURE_FRAME,FrameTimer,HitchWatch,RefreshClock
from game_mode import KEY_HINTS,PAD_HINTS,power_items,status_text
from hang_watch import HangWatch
from keep_awake import BatteryHint,KeepAwake
from pad_input import KEY_NAMES,KEYBOARD_HELP,PadBridge
from mouse_aim import MOUSE_HELP,AimProfiles,MouseAim,RawMouse,free_pointer,hold_pointer
import voice_note,fan_target,console_mic,library_view,twitch_chat,local_api,app_version,psn_link,friends_view,clip_editor,game_stats,pad_profiles,trophy_guides,payload_manager,ftp_files,psn_trophies
from functools import partial
from performance import reading,watts
from screen_rate import ScreenRate
from smooth_motion import NOTE as SMOOTH_NOTE,SmoothMotion
from performance import report_details
import hud
from run_timer import RunTimer,text as timer_text
from watch_alerts import Alerts
from desktop_notice import DesktopNotice
from sound_board import SoundBoard

QML=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))/'qml'
user32=ctypes.WinDLL('user32',use_last_error=True)
user32.GetClientRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)];user32.IsIconic.argtypes=[wintypes.HWND]
user32.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
user32.GetDC.argtypes=[wintypes.HWND];user32.GetDC.restype=wintypes.HDC;user32.ReleaseDC.argtypes=[wintypes.HWND,wintypes.HDC]
user32.FillRect.argtypes=[wintypes.HDC,ctypes.POINTER(wintypes.RECT),wintypes.HANDLE]
gdi32=ctypes.WinDLL('gdi32');gdi32.GetStockObject.restype=wintypes.HANDLE
HWND_TOPMOST,HWND_NOTOPMOST=wintypes.HWND(-1),wintypes.HWND(-2);NO_MOVE_SIZE=0x0001|0x0002|0x0010
user32.GetWindowLongW.argtypes=[wintypes.HWND,ctypes.c_int];user32.GetWindowLongW.restype=ctypes.c_long
user32.SetWindowLongW.argtypes=[wintypes.HWND,ctypes.c_int,ctypes.c_long];user32.SetWindowLongW.restype=ctypes.c_long
# The caption style, and SWP_NOSIZE|NOMOVE|NOZORDER|NOACTIVATE|FRAMECHANGED for Windows to draw the frame again with it.
GWL_STYLE=-16;WS_CAPTION=0x00C00000;FRAME_CHANGED=0x0001|0x0002|0x0004|0x0010|0x0020
# The three window buttons Qt draws in the top right corner, 46 wide each, and a little room before them.
CAPTION_BUTTONS=150
TABS=PAGES
REPLAY_LENGTHS={'Off':0,'Last 30 seconds':30,'Last 60 seconds':60,'Last 2 minutes':120}
DEFAULT_MIC='Windows default microphone'
# How long a chat message stays over the game when old ones fade.
CHAT_SECONDS=60
SECTIONS=(('console','Console','Address, favourites, connection and power'),('picture','Picture','Quality, graphics card, video output and upscaling'),('captures','Captures','Instant replay, files and diagnostics'),
 ('sound','Sound','Music and sounds on the Games page'),('live','Streaming','Twitch, YouTube, TikTok, any RTMP server, or OBS on this PC'),('connect','Connections','PSN, Discord, Twitch, Stream Deck and OBS'),('look','Appearance','Gaming Mode, motion and the look of PlayBridge'),
 ('phone','Phone','Watch and play from your phone\'s browser'),('updates','Updates','New versions of PlayBridge from GitHub'))
LIVE_HINTS={'twitch':'Twitch recommends at most 6 Mbps, so the Data saver profile suits it best. Higher profiles work on many channels.','youtube':'YouTube takes every 1080p profile. The key travels over an encrypted connection.',
 'tiktok':'TikTok gives a new server address and stream key each time you go live, in LIVE Center on its website, once your account has LIVE access with a stream key. Paste both here. It takes H.264, about 2.5 to 6 Mbps: the Data saver profile suits it. A landscape stream shows with bars or cropped on phones.',
 'custom':'Enter the server address and, if your service gives it separately, the stream key.','obs':f'In OBS, add a Media Source, untick Local File, and enter udp://127.0.0.1:{live_broadcast.OBS_PORT} as the input. Then select Go live here.'}

def keyboard_codes():
 """The window's key codes for the keyboard controller's keys."""
 special={'up':('Up',),'down':('Down',),'left':('Left',),'right':('Right',),'enter':('Return','Enter'),'space':('Space',),'backspace':('Backspace',),'tab':('Tab',),'home':('Home',)}
 return {int(getattr(Qt.Key,'Key_'+part).value):name for name in KEY_NAMES for part in special.get(name,(name.upper(),))}

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
 def mousePressEvent(self,event):
  self.shell.pointer_moved();self.parent().requestActivate()
  # The small window is all picture and has no title bar: dragging the picture moves it.
  if self.shell.values['mini'] and event.button()==Qt.MouseButton.LeftButton:self.parent().startSystemMove()

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

# Seconds a trophy that just unlocked stays in the overlay.
TROPHY_SHOWN=6
class Shell(QObject):
 """What the pages show, each part with its own change signal so that only what reads it is redone, and everything they ask for."""
 pageChanged=Signal();gamingChanged=Signal();fullscreenChanged=Signal();miniChanged=Signal();topChanged=Signal();barChanged=Signal();messageChanged=Signal();stageChanged=Signal()
 shelfChanged=Signal();dockChanged=Signal();mediaChanged=Signal();settingsChanged=Signal();dialogChanged=Signal();popupChanged=Signal();consoleCapturesChanged=Signal();lookChanged=Signal();parallaxChanged=Signal();classicChanged=Signal()
 keyPadChanged=Signal();frameChanged=Signal();friendsChanged=Signal();clipChanged=Signal();statsChanged=Signal();filesChanged=Signal();trophiesChanged=Signal()
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
 friends=Property('QVariantMap',lambda self:self.values['friends'],notify=friendsChanged)
 clip=Property('QVariantMap',lambda self:self.values['clip'],notify=clipChanged)
 stats=Property('QVariantMap',lambda self:self.values['stats'],notify=statsChanged)
 files=Property('QVariantMap',lambda self:self.values['files'],notify=filesChanged)
 trophies=Property('QVariantMap',lambda self:self.values['trophies'],notify=trophiesChanged)
 settings=Property('QVariantMap',lambda self:self.values['settings'],notify=settingsChanged)
 dialog=Property('QVariantMap',lambda self:self.values['dialog'],notify=dialogChanged)
 popup=Property('QVariantMap',lambda self:self.values['popup'],notify=popupChanged)
 consoleCaptures=Property('QVariantMap',lambda self:self.values['consoleCaptures'],notify=consoleCapturesChanged)
 look=Property('QVariantMap',lambda self:self.values['look'],notify=lookChanged)
 parallax=Property('QVariantMap',lambda self:self.values['parallax'],notify=parallaxChanged)
 classic=Property('QVariantMap',lambda self:self.values['classic'],notify=classicChanged)
 # The keys the live view hands to the controller on the PS5: none unless "Play on your PS5" is on.
 keyPad=Property('QVariantMap',lambda self:self.values['keyPad'],notify=keyPadChanged)
 # The strip at the top of a window without a title bar, and the width its buttons take on the right, in the window's units.
 frame=Property('QVariantMap',lambda self:self.values['frame'],notify=frameChanged)

 def __init__(self,app,core):
  super().__init__()
  self.app=app;self.core=core;saved=core.config()
  self.values=dict(page='',gaming=False,fullscreen=False,mini=False,top={},bar={},message={},stage={},shelf={},dock={},media={},settings={},dialog={},popup={},consoleCaptures={},look={},friends={},clip={},stats={},files={},trophies={},parallax={'x':0.0,'y':0.0},classic={},keyPad={'keys':[]},frame={'top':0,'buttons':0})
  self.flow=GameFlow();self.back_page='games';self.menu_was_in_front=False;self.seen_status=None;self.revealed_at=0;self.opened_title='';self.opened_at=0;self.first_status=True;self.top_info={}
  # menu_shown: the Qt menu's window is up. menu_chosen: the row picked in it, which runs once that window has gone (do_menu_closed).
  self.menu_shown=False;self.menu_chosen=None
  self.dialog_command=None;self.has_video=False;self.mini_place=None;self.session_wanted=bool(saved.get('session_panel',False));self.dock_visible=False;self.window_width=1540
  self.sounds=SoundBoard(lambda:app.stats.get('output_device'),saved.get('sound_music',True),saved.get('sound_cues',True),saved.get('sound_level',.6))
  self.actions=dict(open=self.start_game,close=self.close_game,connect=self.connect_toggle,live=lambda:self.show_page('live'),media=lambda:self.show_page('media'),friends=lambda:self.show_page('friends'),files=lambda:self.show_page('files'),trophies=lambda:self.show_page('trophies'),stats=lambda:self.show_page('stats'),settings=lambda:self.show_page('settings'),
   fullscreen=lambda:self.set_gaming(not self.values['gaming']),rest=self.rest_console,off=self.power_off_console,reboot=self.reboot_console,soft_reset=self.soft_reset,recovery=self.recovery_console,exit=lambda:self.set_gaming(False))
  self.actions['view_changed']=self.view_changed;self.actions['trophy_guide']=self.open_trophy_guide
  # The PSN menu under the player's picture in the top bar.
  self.actions.update(psn_friends=lambda:self.show_page('friends'),psn_messages=lambda:self.show_page('friends'),psn_trophies=lambda:self.show_page('trophies'),
   psn_settings=lambda:self.do_psn_settings(None),psn_refresh=self.psn_refresh_all,psn_sign_out=self.psn_sign_out_first)
  self.shelf_state=Shelf(app.link,self.actions,self.sounds.play);self.games=GameModel();self.shelf_state.options=library_view.ViewChoice.from_saved(saved)
  self.pad=PadBridge(lambda:app.args.host,app.stop,companion=core.companion_bytes,send_elf=payload_sender.send_payload)
  self.console_pad=bool(saved.get('console_pad',False));self.key_codes=keyboard_codes()
  # The mouse as the right stick while you aim, with each game's own settings.
  self.aim=MouseAim();self.pad.mouse=self.aim;self.aim_profiles=AimProfiles(core.STATE/'library'/'aim.json');self.raw_mouse=None;self.aiming=False
  # Phones: off until turned on in Settings › Phone. Only the hashes of paired phones' tokens are kept.
  hashes=saved.get('phone_tokens',[]);hashes=[item for item in hashes if isinstance(item,str)] if isinstance(hashes,list) else []
  self.pairing=phone_link.Pairing(hashes,lambda kept:core.save_config(phone_tokens=kept))
  self.phones=phone_link.PhoneServer(app.phone_feed,self.pairing,lambda:app.args.host,lambda:self.pad.attached,log=phone_link.PhoneLog(core.STATE/'phone-log.txt'))
  # A phone that plays needs the controller companion as much as this PC does.
  self.pad.wanted=self.phones.in_use
  if saved.get('phone_on',False):self.phones.start()
  self.diagnostic=bool(saved.get('diagnostic',False));self.match_on=bool(saved.get('match_refresh',True));self.animations=bool(saved.get('animations',True))
  self.say_text=('','plain');self.say_until=None;self.update_seen=-1;self.update_offered=None;self.scan_results=queue.Queue();self.discovered={};self.scanning=False;self.scan_status='Find your PS5 or enter its IP address above.';self.found_label='Select a console'
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
  # The Games page looks as it did in 1.5.x: the classic drawing makes the whole page and the window shows it pixel for pixel.
  self.classic_page=ClassicShelf(self.shelf_state,app.link,lambda:self.animations)
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
  self.float_frame();self.window.visibilityChanged.connect(lambda *_:QTimer.singleShot(0,self.float_frame))
  self.presenter=None;self.direct=False
  if app.renderer=='d3d11':
   try:
    from d3d11_presenter import D3D11Presenter
    self.video=VideoSurface(self.window,self);self.video.setGeometry(self.video_rect)
    self.presenter=D3D11Presenter(self.video,core.config().get('sharpen',False),core.config().get('fsr',False),app.adapter,core.config().get('vrr',False),core.config().get('smooth_motion',True));self.direct=True
   except Exception:self.presenter=None;app.use_gdi()
  if not self.direct:
   from gdi_presenter import GdiPresenter
   app.renderer='gdi'
   if self.video is None:self.video=VideoSurface(self.window,self);self.video.setGeometry(self.video_rect)
   self.presenter=GdiPresenter(self.video)
  self.refresh=RefreshClock(app.stop)
  # In-between pictures, on by default: they start by themselves once the screen is fast enough for them.
  self.smooth=SmoothMotion(app.stats,app.timings,core.config().get('smooth_motion',True));self.between_mark=0
  # The PS5's own numbers over the picture (F12).
  self.perf_overlay=bool(core.config().get('perf_overlay',False))
  # Alert me when: what the player asked to be told about, and the Windows notification that tells them.
  self.alerts=Alerts(core.config().get('alert_hot'));self.desktop_notice=None
  # The speedrun timer, the trophy that just unlocked (shown for a few seconds) and the game that was open at the last look.
  self.run_timer=RunTimer(core.STATE/'library'/'runs.json');self.timer_shown=bool(core.config().get('timer_shown',False));self.trophy_shown=None;self.last_playing=None
  # Local control for a Stream Deck, hotkeys and OBS: off until turned on in Settings › Connections.
  self.api=local_api.LocalApi(core.HERE/'assets');self.trophy_count=0;self.trophy_last=None
  if core.config().get('api_on',False):self.start_api()
  # PlayStation Network: friends, their alerts and messages. Signed out until the player pastes Sony's code in Settings › Connections.
  saved_psn=core.config();token=live_broadcast.unseal(saved_psn.get('psn_token','')) if isinstance(saved_psn.get('psn_token'),str) else ''
  try:until=float(saved_psn.get('psn_until',0) or 0)
  except (TypeError,ValueError):until=0
  self.psn=psn_link.Psn(core.STATE/'psn',(token or None,until if token else 0),self.keep_psn_token)
  self.psn.wants=friends_view.wants_from(saved_psn);self.psn.favourites=friends_view.favourites_from(saved_psn);self.psn.start()
  self.friends_filter='All';self.psn_problem='';self.psn_seen=None;self.friend_finder=False
  # The picture waiting to go to the open conversation: its file, whether PlayBridge made it (a pasted picture, deleted once done) and
  # the conversation it is for. None when there is none.
  self.chat_outgoing=None
  # Over the open conversation: its options card or the new-group card ('options', 'new' or ''), and the message whose reactions are
  # open to choose from ('' when none). Esc closes them first.
  self.chat_card='';self.chat_picking=''
  # A voice message plays on the game's sound output; a video opens in Windows' own player once PSN has sent it.
  self.voice=voice_note.VoiceNote(lambda:app.stats.get('output_device'));self.psn.on_media=self.media_ready
  # Trophies from PSN: the Trophies page, a friend's beside yours, and on the Games page the games whose trophies the console's files do not give.
  self.trophy_book=psn_trophies.TrophyBook(self.psn,core.STATE/'psn'/'trophies');self.psn.helpers.append(self.trophy_book);app.link.more_trophies=self.trophy_book
  self.trophy_filter='All';self.trophy_seen=None;self.trophy_shelf_seen=None
  # The clip editor in Media: one recording at a time; its work runs on threads that answer through clip_results.
  self.clip_results=queue.Queue();self.clip_job=0;self.clip_share=None;self.clip_stopping=threading.Event()
  # Your play, counted while PlayBridge is connected, for the Stats page.
  self.play_log=game_stats.PlayLog(core.STATE/'library'/'play.json');self.stats_year=None;self.stats_seen=None
  # Controller profiles: each game's own way to play with this PC's controller, applied on the PC before it is sent.
  self.pad_profiles=pad_profiles.PadProfiles(core.STATE/'library'/'controller.json');self.pad_profile_title=None
  # A shelf of PS5 payloads from a repository's releases, a developer loop that resends an ELF as it is built, and a read-only kernel log.
  self.payload_store=payload_manager.Store(core.STATE/'payloads');self.payload_shelf=payload_manager.Shelf(self.payload_store,saved_psn.get('payload_repo',''))
  self.dev_watch=None;self.dev_auto=False;self.dev_line=('','plain');self.klog=None;self.klog_lines=[];self.dev_at=0.0;self.dev_seen=None
  self.set_watch(str(saved_psn.get('dev_watch','') or ''))
  # The PS5's files, through an FTP server a homebrew payload already runs on the console; one connection, on its own thread.
  self.files_session=ftp_files.FileSession(self.files_host);self.files_path=str(saved_psn.get('files_path','/') or '/');self.files_entries=[]
  self.files_line=('','plain');self.files_selected='';self.files_loading=False;self.files_ready=False;self.files_saved='';self.files_share=None
  # A look at a file without copying it: {name, kind, text, image, cut, why, loading}, or None.
  self.files_preview=None;self.files_looks=0
  self.hud_at=0;self.hud_health={};self.hud_linked=False
  self.vrr_on=self.direct and self.presenter.tearing
  self.vrr_state='on' if self.vrr_on else 'fixed screen' if getattr(self.presenter,'fixed_screen',False) else 'unsupported' if core.config().get('vrr',False) else 'off'
  def next_due():
   with app.lock:return app.pacer.due(middle=self.smooth.active)
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
   now=time.perf_counter();seconds=clock.elapsed(now);period=self.refresh.period;pick=None
   with app.lock:
    missing=app.pacer.missing;ahead=self.smooth.ahead(output,period,app.pacer.spacing,self.vrr_on)
    item=app.pacer.advance(seconds,now,ahead) if seconds else None;missing=app.pacer.missing!=missing
    # A refresh between two frames shows a picture made from both, where the screen is fast enough for one.
    if item is None and ahead and seconds:pick=app.pacer.between(period,self.vrr_on)
   self.hitches.refresh(round(seconds/clock.period),missing,self.paint_took>clock.period)
   if item is None:
    if pick is not None and self.smooth.show(output,pick):
     # A new picture too: with a game's copies left out, the screen moves on at every refresh only through these.
     shown=time.perf_counter();self.hitches.shown(shown,period,shown-app.started)
     if self.vrr_on:clock.last=shown
    else:output.refresh()
    return
   image,arrived,prepared=item;paint_at=time.perf_counter();app.timings.add('prepared_slot_wait_ms',(paint_at-prepared)*1000)
   if output.draw(image):
    done=time.perf_counter();self.note_shown(done);app.timings.add('presenter_upload_ms',(done-paint_at)*1000);app.timings.add('receive_to_present_ms',(done-arrived)*1000);app.stats['video_presented']+=1;app.stats['last_frame_to_ui_ms']=round((done-arrived)*1000,1)
    if self.vrr_on:clock.last=done
   else:self.hitches.unpresented()
  except Exception as error:output.failed=error
  finally:self.paint_took=time.perf_counter()-now
 def smooth_wanted(self):
  """True while in-between pictures are on and could be made: the GPU output runs and the frames come from the graphics card."""
  output=self.presenter;frame=getattr(output,'frame',None)
  return bool(self.direct and self.smooth.on and self.smooth.stopped is None and getattr(output,'smooth_failed',None) is None and frame is not None and frame.format.name=='d3d11')
 def float_frame(self):
  """Windows 11 gives a window its rounded corners and shadow, and no light line along its edge, only while it keeps the caption
  style. Qt leaves that style out of a window without a title, and sets its own again after full screen, so it goes back on each time."""
  try:
   if self.window.visibility()!=QWindow.Visibility.FullScreen:
    style=user32.GetWindowLongW(self.hwnd,GWL_STYLE)&0xffffffff
    if style&WS_CAPTION!=WS_CAPTION:user32.SetWindowLongW(self.hwnd,GWL_STYLE,ctypes.c_long(style|WS_CAPTION).value);user32.SetWindowPos(self.hwnd,None,0,0,0,0,FRAME_CHANGED)
   top=self.window.safeAreaMargins().top();buttons=CAPTION_BUTTONS if top>0 else 0
  except Exception as error:self.app.event(f'Window frame not set: {type(error).__name__}');top=buttons=0
  self.put('frame',{'top':top,'buttons':buttons})
  if hasattr(self,'classic_page'):
   inset=round(buttons*self.window.devicePixelRatio()) if not (self.values['fullscreen'] or self.values['mini']) else 0
   if inset!=self.classic_page.inset:self.classic_page.inset=inset;self.classic_page.stale=True
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
  # A running timer shows tenths of a second, so the overlay is drawn again ten times a second while it runs.
  elif self.run_timer.state=='running' and self.timer_shown and now-self.hud_at>=.1:self.show_overlay(self.values['page'],self.hud_health,self.hud_linked)
  self.poll_queues()
 def each_second(self,now):
  self.offer_update()
  app=self.app;core=self.core
  decoded=app.stats.get('video_decoded',0);self.decoded_rate=(decoded-self.decoded_mark)/(now-self.rate_at);self.decoded_mark=decoded;self.second_at=self.rate_at
  self.fps=self.rate_frames/(now-self.rate_at);app.stats['presented_fps']=round(self.fps,1);self.rate_frames=0;self.rate_at=now
  # What the screen side looked like, to tell a PC that stutters from one that does not.
  app.stats['refresh_hz']=round(1/self.refresh.period,1);app.stats['vrr']=self.vrr_state;app.stats['hitches']=dict(self.hitches.counts);app.stats['hitch_log']=list(self.hitches.log)
  if self.direct:app.stats['present_timeouts']=self.presenter.timeouts;app.stats['cross_card']=self.presenter.cross;app.stats['frames_in_flight']=self.presenter.flight
  app.stats['screen_rate']=self.rate.label();app.stats['screen_rate_check']=self.rate.note;app.stats['controller_link']=self.pad.link(time.monotonic());app.stats['ui']='qt'
  app.stats['smooth_motion']=self.smooth.second(self.presenter,self.presenter.timeouts if self.direct else 0)
  app.repeats.wanted=self.direct and self.smooth.can_run(self.presenter);app.stats['repeat_frames']=app.repeats.state()
  self.watch_second()
  made=app.stats.get('between_presented',0);app.stats['between_fps']=round((made-self.between_mark)/max(.5,now-self.second_at),1);self.between_mark=made;self.second_at=now
  app.stats['smooth_line']=f'Smooth motion {1/self.refresh.period:.0f} Hz' if app.stats['between_fps']>=5 else ''
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
  # With smooth motion a screen that can go faster, as from 60 to 120 Hz, does, so there is a refresh between every two frames.
  faster=self.smooth_wanted()
  switched=self.rate.want((self.match_on or faster) and not self.vrr_on and linked and not iconic and (page=='live' or self.rate.changed is not None),self.hwnd,faster=faster,match=self.match_on)
  if switched and switched[1]>switched[0]:app.notify(f'Screen set from {switched[0]} to {switched[1]} Hz while the game streams, so PlayBridge can show a smooth picture between every two frames.')
  elif switched:app.notify(f'Screen set from {switched[0]} to {switched[1]} Hz while the game streams, so every frame shows for the same time.')
  with app.metrics_lock:health=app.metrics.summary()
  self.hud_health=health;self.hud_linked=linked;self.show_overlay(page,health,linked)
  if self.api.running:self.publish_status(linked)
  if app.recorder.active and app.recorder.state=='recording':
   if self.recording_at is None:self.recording_at=now
  elif not app.recorder.active:self.recording_at=None
  self.place_session()
  self.sounds.want_music(page=='games' and not (self.flow.waiting or self.flow.after_close))
  # "Play on your PS5": the controller and the keyboard play over the video, and the PS5 keeps this PC's controller on every page.
  self.pad.attached=self.console_pad and app.link.online;self.pad.keys_on=self.console_pad
  self.pad.sending=self.pad.attached and page=='live'
  if page!='live':self.pad.keyboard.clear()
  if not self.pad.sending:self.stop_aim()
  # Settings follows the copy of the saves and the fans as they go.
  fans=(self.fan_line(),app.microphone.state(),self.section=='connect' and repr((self.discord_view(),self.chat_settings(),self.psn_settings())))
  # Friends: the PSN thread reads faster while the page shows, and the page follows it.
  # The dot beside Friends: new messages and friend requests waiting.
  self.psn.focus(page=='friends');unread=sum(1 for group in list(self.psn.groups) if group.get('unread'))+len(self.psn.received);self.shelf_state.unread=unread
  chip,self.shelf_state.psn=self.psn_chip(app)
  if page=='friends':self.show_friends()
  if page=='trophies':self.show_trophies()
  if page=='stats':self.show_stats()
  self.ask_shelf_trophies(app.link)
  if page=='settings' and (app.link.saves.version!=getattr(self,'saves_seen',None) or fans!=getattr(self,'fans_seen',None)):
   self.saves_seen=app.link.saves.version;self.fans_seen=fans;self.refresh_settings()
  self.put('keyPad',dict(keys=sorted(self.key_codes) if self.pad.sending else []))
  playing=running_title(app.link.status);readings=console_line(app.link.status)
  self.follow_game(playing)
  if now-self.info_at>=1:
   self.info_at=now;self.top_info=library_info((app.console or {}).get('name'),app.link.online,active,linked,health,self.decoded_rate,self.pad.name,app.link.status)
   self.shelf_state.info=self.top_info
  line='  ·  '.join(part for part in ('Menu open on your PS5' if self.menu_was_in_front else '',self.pad.name) if part) if app.link.online else 'Waiting for your PS5…'
  if self.shelf_state.sync(playing,self.flow.waiting or self.flow.after_close,line,app.notice if now<app.notice_until else app.error or ''):self.games.replace(self.shelf_state.tiles())
  self.show_shelf()
  self.put('top',dict(unread=unread,tab=page if page in TABS else '',selected='settings' if page=='settings' else '',status=status_text(self.top_info),online=self.top_info.get('state')=='online',clock=time.strftime('%H:%M'),pad=bool(self.top_info.get('pad')),info=self.top_info,psn=chip))
  on_air=app.broadcast.active
  self.put('bar',dict(muted=app.muted,volume=round(app.volume,3),recording=bool(app.recorder.active),onAir=bool(on_air),active=active,linked=linked,host=app.console_label(),outputs=[name for _,name in self.outputs] or ['No audio device'],output=self.device_label(app.output_name) or 'No sound output',
   session=self.dock_visible,micOn=bool(app.microphone.on),live=app.broadcast.state=='live',liveText=('Live on '+app.broadcast.name+' for '+live_broadcast.clock(app.broadcast.elapsed())+'.') if app.broadcast.state=='live' else ''))
  if self.dock_visible:
   if now-self.history_at>=1:
    rate=health.get('received_mbps') if linked else None
    if self.history_at:self.history.extend([None]*min(59,max(0,int(now-self.history_at)-1)))
    self.history_at=now;self.history=(self.history+[rate])[-60:]
   last=app.link.performance.last_report
   self.put('dock',dict(self.alert_view(),**session_view(app,health,self.fps,queue_ms,linked,now,now-self.recording_at if self.recording_at is not None else None,app.link.game_name(playing) if playing else 'No game open' if app.link.online else 'Not connected',readings,self.history),lastGame=report_details(last) if last else []))
  # The video keeps arriving behind the other pages, so coming back shows a waiting screen only if no frame turns up.
  waiting=not self.has_video and page=='live' and now-self.revealed_at>1
  self.put('stage',dict(waiting=waiting,text=app.error or ('Connecting to your console…' if active else 'Open Payload Manager on your PS5, then connect.'),video=self.has_video))
  text,tone=message_line(app,core,health,linked,active,now,self.recording_at,self.pad,controller_text(self.pad,time.monotonic()) if self.pad.sending else '',self.fps,queue_ms,self.diagnostic)
  self.put('message',dict(text=text,tone=tone))
  if page=='settings':self.refresh_settings()
 def watch_second(self):
  """Alert me when: once a second, from the frames that arrived and the PS5's own readings."""
  app=self.app;linked=app.connection_state=='Connected' and app.worker.is_alive()
  rate=(app.capture_info or {}).get('bitrate_target');rate=rate/8 if type(rate) in (int,float) and rate>0 else None
  fired=self.alerts.second(app.motion.take(),rate,linked,app.link.performance.view())
  title=running_title(app.link.status) if app.link.online else '';self.play_log.see(title,app.link.game_name(title) if title else '')
  if title!=self.pad_profile_title:self.pad_profile_title=title;self.use_pad_profile()
  while not app.trophy_events.empty():
   title,earned=app.trophy_events.get_nowait();game=app.link.game_name(title);self.play_log.trophy(title,game,len(earned));named=[trophy['name'] for trophy in earned if trophy['name']]
   app.event(f'Trophies earned: {len(earned)}');app.notify(f'Trophy earned in {game}'+(': '+', '.join(named) if named else '.'));app.notice_until=time.perf_counter()+10
   fired+=self.alerts.trophies(game,earned);self.trophy_shown=(earned[-1],time.perf_counter()+TROPHY_SHOWN);self.trophy_count+=1;self.trophy_last=(earned[-1],time.time(),game)
   if self.run_timer.state=='running' and self.core.config().get('timer_trophies',True):
    for trophy in earned:self.run_timer.split(trophy['name'] or 'Trophy')
  for kind,title,text in fired+self.psn.take_alerts():self.deliver_alert(title,text)
  if self.desktop_notice is not None:self.desktop_notice.tick()
 def deliver_alert(self,title,text):
  """An alert on every screen the player may be looking at: the window, each phone, and Windows' own notifications."""
  # The line in the window is drawn without colour emoji, so they are left out of it.
  plain=' '.join(''.join(character for character in text if not hud.is_emoji(character)).split())
  app=self.app;app.event(f'Alert: {title}');app.notify(f'{title}. {plain}' if plain else f'{title}.');app.notice_until=time.perf_counter()+15
  if self.phones.running:self.phones.alert(title,text)
  if self.desktop_notice is None:self.desktop_notice=DesktopNotice(self.hwnd,self.core.HERE/'assets'/'playbridge.ico')
  try:
   if not self.desktop_notice.show(title,text):app.event('Windows notification not shown')
  except Exception as error:app.event(f'Windows notification not shown: {type(error).__name__}: {error}')
 def alert_view(self):
  alerts=self.alerts;wanted=alerts.wanted;state=alerts.state
  return dict(alertMoves=wanted['moves'],alertSlow=wanted['slow'],alertHot=wanted['hot'],alertTrophy=wanted['trophy'],hotAt=f'{alerts.hot_at} °C',alertTrophyState=state['trophy'] if wanted['trophy'] else '',
   alertMovesState=state['moves'] if wanted['moves'] else '',alertSlowState=state['slow'] if wanted['slow'] else '',alertHotState=state['hot'] if wanted['hot'] else '')
 def do_alert(self,value):
  kind,on=value;self.alerts.arm(str(kind),bool(on));self.last_info=0
 def do_trophy_clips(self,on):
  self.core.save_config(trophy_clips=bool(on));self.refresh_settings()
 def do_alert_hot(self,value):
  degrees=int(str(value).split()[0]);self.alerts.hot_at=degrees;self.core.save_config(alert_hot=degrees);self.last_info=0
 def show_overlay(self,page,health,linked):
  """The PS5's own numbers over the picture, redrawn four times a second while the overlay is on and the game shows. The graphics card
  draws it into the picture itself (d3d11_presenter), so there is no window over the video and full screen keeps its own flip."""
  app=self.app;output=self.presenter;now=time.perf_counter();self.hud_at=now
  trophy=self.trophy_shown[0] if self.trophy_shown and now<self.trophy_shown[1] else None
  timer=self.run_timer.view() if self.timer_shown else None;smooth=app.stats.get('between_fps',0)>=5;chat=self.chat_view();saved=self.core.config()
  screen_chat=chat if saved.get('chat_screen',True) else None;stream_chat=chat if saved.get('chat_stream',False) else None
  stream=dict(picture=f"{health['decoded_height']}p" if health.get('decoded_height') else None,mbps=health.get('received_mbps'),
   pc_ms=app.stats.get('last_frame_to_ui_ms') if app.stats.get('video_presented') else None,smooth=round(1/self.refresh.period) if smooth else None)
  try:
   if self.direct:
    wanted=(self.perf_overlay or timer is not None or trophy is not None or screen_chat is not None) and page=='live' and self.has_video and linked
    if wanted:output.set_overlay(hud.render(app.link.performance.view() if self.perf_overlay else None,stream,timer,trophy,None,scale=output.size[1]/1080 if output.size else 1,chat=screen_chat))
    elif output.hud_wanted is not None:output.set_overlay(None)
   # In a live stream made again, the same with the game's numbers and this PC's controller, at the stream's own size, and the chat
   # when it is chosen for the stream.
   if app.broadcast.active and app.broadcast.encoder and (saved.get('live_overlay',False) or stream_chat is not None):
    scale=(health.get('decoded_height') or 1080)/1080
    if saved.get('live_overlay',False):app.broadcast.overlay_image=hud.render(app.link.performance.view(),stream,timer,trophy,self.pad.state if self.pad.sending else None,scale=scale,chat=stream_chat)
    else:app.broadcast.overlay_image=hud.render(scale=scale,chat=stream_chat)
   elif app.broadcast.overlay_image is not None:app.broadcast.overlay_image=None
  except Exception as error:
   self.perf_overlay=self.timer_shown=False;app.broadcast.overlay_image=None
   if self.direct:output.set_overlay(None)
   app.event(f'Overlay not drawn: {type(error).__name__}: {error}');app.notify('The overlay could not be drawn on this PC, so it is off.')
 def follow_game(self,playing):
  """The timer starts by itself when a game opens on the PS5, once PlayBridge already watched the console without it."""
  if not self.app.link.online:self.last_playing=None;return
  if playing!=self.last_playing:
   if playing and self.last_playing is not None and self.timer_shown and self.core.config().get('timer_auto',True):
    self.run_timer.start(playing,self.app.link.game_name(playing));self.app.notify(f'Timer started: {self.app.link.game_name(playing)} opened.')
   self.last_playing=playing
 def do_timer(self,_=None):
  """Ctrl+T: starts the timer, and marks a split while it runs."""
  if not self.timer_shown:self.timer_shown=True;self.core.save_config(timer_shown=True);self.refresh_settings()
  if self.run_timer.state=='running':
   name,at,_=self.run_timer.split();self.app.notify(f'{name}: {timer_text(at)}')
  else:
   playing=running_title(self.app.link.status);self.run_timer.start(playing,self.app.link.game_name(playing) if playing else '')
  self.hud_at=0
 def do_timer_stop(self,_=None):
  """Ctrl+Shift+T: stops the timer, and clears it when it has stopped."""
  if self.run_timer.state=='running':
   best=self.run_timer.game_best().get('total');total=self.run_timer.stop()
   self.app.notify(f'Run: {timer_text(total)}'+(' · a new best' if best is None or total<best else f' · best {timer_text(best)}'))
  else:self.run_timer.reset()
  self.hud_at=0
 def do_timer_shown(self,on):
  self.timer_shown=bool(on);self.core.save_config(timer_shown=self.timer_shown);self.refresh_settings()
 def do_timer_auto(self,on):self.core.save_config(timer_auto=bool(on));self.refresh_settings()
 def do_timer_trophies(self,on):self.core.save_config(timer_trophies=bool(on));self.refresh_settings()
 def do_live_overlay(self,on):self.core.save_config(live_overlay=bool(on));self.refresh_settings()
 def poll_queues(self):
  for command in self.api.take():self.api_command(command)
  while not self.scan_results.empty():self.finish_scan(*self.scan_results.get_nowait())
  while not self.payload_results.empty():self.finish_payload(*self.payload_results.get_nowait())
  if self.encoders is None and not self.encoder_results.empty():self.encoders=self.encoder_results.get_nowait();self.refresh_settings()
  while not self.media_results.empty():self.finish_media(*self.media_results.get_nowait())
  while not self.clip_results.empty():self.finish_clip(*self.clip_results.get_nowait())
  if self.clip_share is not None and self.values['clip'].get('busy') and self.values['clip'].get('share')!=round(self.clip_share,2):self.put('clip',dict(self.values['clip'],share=round(self.clip_share,2)))
  while not self.ps5_answers.empty():self.ps5_answer(*self.ps5_answers.get_nowait())
  self.poll_developer()
  for answer in self.files_session.take():self.finish_files(answer)
  if self.files_session.busy in ('get','put') and self.values['page']=='files':
   progress=self.files_session.progress;share=round(progress[0]/progress[1],2) if progress and progress[1] else 0.0
   if share!=self.files_share:self.files_share=share;self.show_files()
  if self.app.updates.revision!=self.update_seen:self.update_seen=self.app.updates.revision;self.refresh_settings()
  if self.say_until is not None and time.perf_counter()>self.say_until:self.say_until=None;self.say_text=('','plain');self.refresh_settings()
  # The controller's and the phones' state change on their own (a code used or run out, a phone joining), so these two are redone
  # once a second while they show.
  if self.values['page']=='settings' and self.section in ('console','phone') and time.perf_counter()-getattr(self,'settings_at',0)>=1:
   self.settings_at=time.perf_counter();self.refresh_settings()
 def close(self):
  if getattr(self,'closed',False):return
  self.closed=True;self.timer.stop();self.phones.stop();self.api.stop();self.psn.stop();self.clip_stopping.set();self.play_log.close();self.stop_aim()
  if self.klog is not None:self.klog.stop()
  self.files_session.close()
  if self.raw_mouse is not None:self.raw_mouse.close()
  if self.desktop_notice is not None:self.desktop_notice.remove()
  self.awake.want(False);self.rate.want(False,0);self.app.microphone.close();self.app.stop.set();self.sounds.close()
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
  x=0.0 if abs(x)<.2 else max(-1.0,min(1.0,x));y=0.0 if abs(y)<.2 else max(-1.0,min(1.0,y));lean={'x':round(x,2),'y':round(y,2)}
  # The focused tile tilts with the stick too, as it does under the pointer.
  if lean!=self.values['parallax']:self.classic_page.lean(lean['x'],lean['y'])
  self.put('parallax',lean)

 # Pages.
 def show_page(self,name):
  page=self.values['page']
  if name==page:return
  self.close_popup()
  # The small window holds only the picture, so any other page brings the full window back.
  if self.values['mini'] and name!='live':self.small_window()
  if name=='media':self.open_media()
  if name=='friends':self.psn_seen=None;self.psn.focus(True);self.show_friends()
  if name=='stats':self.stats_seen=None;self.show_stats()
  if name=='files':self.files_list(self.files_path)
  self.trophy_book.watch(name=='trophies')
  if name=='trophies':self.trophy_seen=None;self.show_trophies()
  games_shown=name=='games'
  if name in ('media','settings','friends','trophies','stats','files') and page in ('games','live'):self.back_page=page
  # The game's sound carries on behind Media and Settings, where only the picture is out of sight.
  self.app.video_hidden=name!='live';self.app.sound_hidden=games_shown;self.pad.navigating=name!='live'
  if name=='live':self.revealed_at=time.perf_counter()
  else:
   self.has_video=False;self.last_info=0
   if self.presenter:self.presenter.frame=None
  self.sounds.show(games_shown);self.put('page',name);self.classic_page.show(games_shown)
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
 def ask_first(self,title,text,action,command,cancel='Cancel'):
  self.dialog_command=command;self.put('dialog',dict(title=title,text=text,action=action,cancel=cancel))
 def offer_update(self):
  """A new version from GitHub is asked about once, as soon as it is in: never over the game's picture, a menu or another question,
  which it waits for. A copy run from source asks once for each version, kept in the preferences."""
  ask=updater.prompt(self.app.updates.status(),source=not getattr(sys,'frozen',False))
  if not ask or ask['version']==self.update_offered:return
  if self.values['dialog'] or self.values['popup'] or self.menu_shown or self.values['fullscreen'] or self.values['mini'] or (self.values['page']=='live' and self.has_video):return
  self.update_offered=ask['version']
  if ask['kind']=='page':
   if self.core.config().get('update_offered')==ask['version']:return
   self.core.save_config(update_offered=ask['version']);command=lambda:self.do_update_page(None)
  else:command=lambda:self.do_update_install(None)
  self.app.event(f'Asked to update to PlayBridge {ask["version"]}');self.ask_first(ask['title'],ask['text'],ask['action'],command,ask['cancel'])
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
  ready=kind=='obs' or kind in ('twitch','youtube') and key or kind=='custom' and server or kind=='tiktok' and server and key
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
   elif event=='next' and not (self.shelf_state.menu or self.shelf_state.panel):self.show_page(self.next_tab(1))
   elif event=='previous' and not (self.shelf_state.menu or self.shelf_state.panel):self.show_page(self.next_tab(-1))
   else:self.shelf_state.navigate(event);self.show_shelf()
  elif page=='live':
   if event=='leave':self.show_games(True)
  # On Friends, the controller's back button closes what is open over the page first (the reactions, a card, the open conversation),
  # in the order Esc does.
  elif page=='friends' and event=='back':self.do_key('escape')
  elif event in ('back','leave'):self.show_page(self.back_page)
  elif event=='next':self.show_page(self.next_tab(1))
  elif event=='previous':self.show_page(self.next_tab(-1))
  elif event in ('up','down','left','right','accept'):self.navigate.emit(event)
 def do_key(self,key):
  """The keys that are the same on every page."""
  page=self.values['page']
  # Escape first lets go of the mouse while you aim.
  if key=='escape' and self.aiming:self.stop_aim();return
  if key=='escape':
   if self.values['dialog']:self.do_dialog_cancel(None)
   elif self.values['clip'] and not self.values['clip'].get('busy'):self.do_clip_close(None)
   elif self.values['popup']:self.close_popup()
   elif self.values['consoleCaptures']:self.do_ps5_close(None)
   elif page=='games' and self.shelf_state.dismiss():self.show_shelf()
   elif page=='friends' and self.friend_finder:self.do_friend_find_close(None)
   elif page=='friends' and self.chat_picking:self.do_psn_react_close(None)
   elif page=='friends' and self.chat_card:self.do_psn_card_close(None)
   elif page=='friends' and self.chat_outgoing:self.do_psn_picture_clear(None)
   elif page=='friends' and self.psn.thread_id:self.psn.close_chat()
   elif page=='trophies' and self.trophy_book.open:self.do_trophy_close(None)
   elif page=='files' and self.files_preview is not None:self.do_files_preview_close(None)
   elif page in ('media','settings','friends','trophies','stats','files'):self.show_page(self.back_page)
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
  elif key=='overlay':self.do_perf_overlay(not self.perf_overlay)
  elif key=='timer':self.do_timer()
  elif key=='timer_stop':self.do_timer_stop()
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
  self.put('shelf',view);self.classic_page.refresh()
 def do_move(self,change):self.shelf_state.wheel(int(change));self.show_shelf()
 def view_changed(self):
  """After the view, the tile size, the names or the marks changed, from the View menu, Settings or the keys: kept, and the page laid out again."""
  self.core.save_config(**self.shelf_state.options.saved());self.classic_page.relayout()
  if self.values['page']=='settings':self.refresh_settings()
 def do_games_view(self,label):
  key=next((key for key,name in library_view.VIEWS if name==label or key==label),None)
  if key and key!=self.shelf_state.options.view:self.shelf_state.options.view=key;self.sounds.play('accept');self.view_changed();self.show_shelf()
 def do_tile_size(self,label):
  key=next((key for key,name in library_view.SIZES if name==label),None)
  if key and key!=self.shelf_state.options.size:self.shelf_state.options.size=key;self.view_changed()
 def do_tile_names(self,on):self.shelf_state.options.names=bool(on);self.view_changed()
 def do_tile_badges(self,on):self.shelf_state.options.badges=bool(on);self.view_changed()
 def do_go(self,index):
  index=int(index)
  if index==self.shelf_state.target:self.shelf_state.choose()
  else:self.shelf_state.go_to(index)
  self.show_shelf()
 def do_choose(self,_):self.shelf_state.choose();self.show_shelf()
 def do_shelf(self,key):self.shelf_state.set_shelf(key);self.games.replace(self.shelf_state.tiles());self.show_shelf()
 def do_more(self,_):self.shelf_state.open_menu('more');self.show_shelf()
 def do_menu_choose(self,index):
  if self.values['popup']:self.popup_choose(int(index));return
  before=self.shelf_state.tiles_version;self.shelf_state.menu_choose(int(index))
  if before!=self.shelf_state.tiles_version:self.games.replace(self.shelf_state.tiles())
  self.show_shelf()
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
  elif key=='psn':self.psn_menu()
  elif key=='search':self.do_search(not (self.shelf_state.searching or self.shelf_state.text) or self.values['page']!='games')
  # On the live view this is plain fullscreen. Elsewhere it is the library's button.
  elif key=='fullscreen' and self.values['page']=='live':self.full()
  elif key in self.actions:self.actions[key]()
 def power_menu(self):
  if self.values['page']=='games':self.shelf_state.open_menu('power');self.show_shelf();return
  items=power_items(self.app.link.online,running_title(self.app.link.status),'Exit Gaming Mode' if self.values['gaming'] else '')
  if not items:self.say('Connect to your PS5 first.');return
  self.sounds.play('move');self.put('popup',dict(kind='power',selected=0,items=[dict(key=key,label=label) for key,label in items]))
 def psn_menu(self):
  """The PSN menu under the player's picture: friends, messages, trophies, settings, refresh and sign out, or a way to sign in."""
  summary=self.trophy_book.view().get('summary') or {}
  items=friends_view.menu_items(self.psn.view(),summary.get('level',0))
  if self.values['page']=='games':self.shelf_state.open_menu('psn',items);self.show_shelf();return
  self.sounds.play('move');self.put('popup',dict(kind='psn',selected=0,items=[dict(key=item[0],label=item[1],value=item[2] if len(item)>2 else '') for item in items]))
 def psn_refresh_all(self):self.do_psn_refresh(None);self.trophy_book.refresh()
 def psn_sign_out_first(self):
  self.ask_first('Sign out of PSN?','PlayBridge forgets your sign-in, your friends and the trophies it keeps. Your PSN account stays as it is.','Sign out',lambda:self.do_psn_signout(None))
 def psn_chip(self,app):
  """The player for the top bars: the Qt pages' (a picture address) and the Games page's (a file and when it changed)."""
  chip=friends_view.chip(self.psn.view(),app.playing_name(),self.psn_picture)
  path=self.core.STATE/'psn'/'pictures'/(self.psn.me.get('picture') or '_') if chip['picture'] else None
  try:stamp=path.stat().st_mtime if path else 0
  except OSError:path,stamp=None,0
  return chip,(chip['name'],chip['line'],chip['tone'],str(path) if path else '',stamp,chip['initial'])
 def popup_answer(self,event):
  popup=dict(self.values['popup'])
  if event in ('up','down'):popup['selected']=(popup['selected']+(1 if event=='down' else -1))%len(popup['items']);self.sounds.play('move');self.put('popup',popup)
  elif event=='accept':self.popup_choose(popup['selected'])
  elif event in ('back','leave'):self.close_popup();self.sounds.play('back')
 def popup_choose(self,index):
  items=self.values['popup'].get('items',[])
  chosen=self.actions[items[index]['key']] if 0<=index<len(items) else None
  if chosen:self.sounds.play('accept')
  # A row chosen in an open menu runs once the menu has gone (do_menu_closed). The menu may report that while it closes, so the row is
  # kept first.
  if self.menu_shown:self.menu_chosen=chosen;self.close_popup()
  else:
   self.close_popup()
   if chosen:chosen()
 def do_menu_shown(self,_):self.menu_shown=True
 def do_menu_closed(self,_):
  """The menu has closed: after a choice, a press outside it or Escape. A row chosen in it runs now, once the keyboard has left it."""
  self.menu_shown=False
  if self.values['popup']:self.close_popup()
  chosen,self.menu_chosen=self.menu_chosen,None
  if chosen:self.after_popups(chosen)
 def after_popups(self,command):
  """Runs command once no popup window has the keyboard. Qt shuts a window that opens while a closing menu's window still has it, which
  is how the confirmation for Reboot, Turn off, Recovery, Close game and Sign out vanished before anyone could answer. The keyboard
  leaves the menu just after it closes; Qt says when. If it never says, the command still runs half a second later rather than not at
  all."""
  app=QGuiApplication.instance();holder=app.focusWindow()
  if holder is not None and holder.type()==Qt.WindowType.Popup:
   waiting=[True]
   def run(*_):
    if not waiting[0]:return
    waiting[0]=False
    try:app.focusWindowChanged.disconnect(run)
    except (RuntimeError,TypeError):pass
    QTimer.singleShot(0,command)
   app.focusWindowChanged.connect(run);QTimer.singleShot(500,run);return
  QTimer.singleShot(0,command)
 def close_popup(self):self.put('popup',{})
 # The classic Games page: its size on screen, the pointer and clicks, answered as the 1.5.x page answered them.
 def do_classic_size(self,value):
  width,height,ratio=(float(part) for part in value);self.classic_page.resize(width,height,ratio)
 def do_classic_pointer(self,value):
  hand=self.classic_page.pointer_at(float(value[0]),float(value[1])) if value else self.classic_page.pointer_left()
  if hand!=bool(self.values['classic'].get('hand')):self.put('classic',dict(hand=hand))
 def do_classic_release(self,value):
  kind,what=self.classic_page.released(float(value[0]),float(value[1])) or (None,None);shelf=self.shelf_state
  if kind=='menu':self.do_menu_choose(what);return
  if kind=='away':shelf.menu=None;shelf.panel=None;self.sounds.play('back')
  elif kind=='panel':
   # A click picks a trophy; a click on the one already picked opens its guide.
   if not shelf.panel or what is None:pass
   elif what!=shelf.panel['selected']:shelf.panel['selected']=what;self.sounds.play('move')
   else:shelf.guide()
  elif kind=='tile':self.do_go(what);return
  elif kind=='action':self.do_choose(None);return
  elif kind=='more':self.do_more(None);return
  elif kind=='top':
   if what=='search':
    if shelf.searching or shelf.text:shelf.stop_search();self.games.replace(shelf.tiles())
    else:shelf.start_search()
   elif what=='shelf':shelf.next_shelf(1);self.games.replace(shelf.tiles())
   elif what=='power':shelf.open_menu('power')
   elif what=='psn':self.psn_menu();return
   elif what=='view':shelf.open_menu('view')
   elif what!='games' and what in self.actions:self.sounds.play('accept');self.actions[what]()
  self.show_shelf()

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
  # While you aim, the buttons are the controller's.
  if self.aiming:return
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
   consolePad=self.console_pad,keyboardHelp=KEYBOARD_HELP,padStatus=self.pad_status(),**self.phone_view(),**self.aim_view(),**self.pad_profile_view(),**self.fan_view(),**self.discord_view(),**self.chat_settings(),**self.api_view(),**self.psn_settings(),
   chatProblem=getattr(self,'chat_problem',''),
   recent=[self.payload_label(item) for item in self.recent_payloads()] or ['No payload sent yet'],payloadStatus=dict(text=self.payload_status[0],tone=self.payload_status[1]),**self.payloads_view(),
   profiles=[value['name'] for value in profiles.values()],profile=profiles[app.args.profile]['name'],cardSummary=graphics_card.summary(app.graphics()),
   cards=([automatic]+names) if len(found)>1 else [],card=(kept_card if kept_card in names else automatic) if len(found)>1 else '',
   diagnostic=self.diagnostic,perfOverlay=self.perf_overlay,timerShown=self.timer_shown,timerAuto=bool(saved.get('timer_auto',True)),timerTrophies=bool(saved.get('timer_trophies',True)),liveOverlay=bool(saved.get('live_overlay',False)),trophyClips=bool(saved.get('trophy_clips',True)),gpuOutput=bool(saved.get('direct_video',True)),matchRefresh=self.match_on,direct=self.direct,sharpen=bool(self.presenter.sharpen) if self.direct else False,fsr=bool(self.presenter.fsr) if self.direct else False,
   vrrSupported=vrr_supported,vrr=bool(saved.get('vrr',False)),smooth=bool(self.smooth.on) if self.direct else False,smoothState=self.smooth_note(),smoothNote=SMOOTH_NOTE,
   replayLengths=list(REPLAY_LENGTHS),replay=next((label for label,seconds in REPLAY_LENGTHS.items() if seconds==app.replay.seconds),'Last 60 seconds'),
   mic=bool(app.microphone.on),mics=[DEFAULT_MIC,console_mic.NAME]+mics,micDevice=kept_mic if kept_mic in mics or kept_mic==console_mic.NAME else DEFAULT_MIC,micState=app.microphone.state(),micLevel=float(app.mic_mix.level),micMax=float(mic_mix.LEVEL_MAX),
   captureFolder=str(app.capture_folder()),compact=bool(saved.get('compact_recordings',False)),compactNote=compact_note,compactProgress=app.compactor.status(),
   saveBackup=bool(app.link.saves.auto),savesBusy=bool(app.link.saves.busy()),savesStatus=app.link.saves.status or 'No saves copied in this session yet.',
   services=list(live_broadcast.SERVICES.values()),service=live_broadcast.SERVICES[service],serviceKey=service,server=saved.get('live_server','') if isinstance(saved.get('live_server'),str) else '',
   key=live_broadcast.unseal(saved.get('live_key','')),compressible=service in live_broadcast.COMPRESSIBLE,compress=bool(saved.get('live_compress',False)),compressNote=live_note,
   liveStatus=dict(text=live_status[0],tone=live_status[1]),liveActive=bool(app.broadcast.active),
   music=bool(self.sounds.music_on),cues=bool(self.sounds.effects_on),level=float(self.sounds.volume),gamingOnStart=bool(saved.get('gaming_mode',False)),animations=self.animations,qt=saved.get('ui','qt')=='qt',
   gamesViews=[name for _,name in library_view.VIEWS],gamesView=library_view.VIEW_NAMES[self.shelf_state.options.view],tileSizes=[name for _,name in library_view.SIZES],
   tileSize=library_view.SIZE_NAMES[self.shelf_state.options.size],tileNames=self.shelf_state.options.names,tileBadges=self.shelf_state.options.badges,
   update=dict(app.updates.status(),text=app.updates.text(),source=not getattr(sys,'frozen',False))))
 def start_api(self):
  """Starts local control on the port it had before, so the addresses in a Stream Deck keep working, or on the next free one."""
  saved=self.core.config();secret=saved.get('api_secret') if isinstance(saved.get('api_secret'),str) and len(saved.get('api_secret'))>=12 else local_api.new_secret()
  kept=saved.get('api_port') if type(saved.get('api_port')) is int and 1024<saved.get('api_port')<65500 else None
  port=self.api.start(secret,kept or local_api.PORT)
  if port is None:return False
  if port!=kept or secret!=saved.get('api_secret'):self.core.save_config(api_secret=secret,api_port=port)
  if kept and port!=kept:self.app.notify(f'Local control moved to port {port}: another program uses {kept}. Copy the new addresses in Settings › Connections.');self.app.notice_until=time.perf_counter()+15
  return True
 def api_command(self,name):
  """A command from local control, done as if its button had been pressed here."""
  self.app.event(f'Local control: {name}')
  if name=='mic':self.set_microphone(not self.app.microphone.on)
  elif name=='timer-stop':self.do_timer_stop()
  elif name in ('screenshot','record','replay','live','timer'):self.act(name)
 def publish_status(self,linked):
  """What local control hands out, four times a second: the game, its numbers, recording, live, the timer, the newest trophy and the chat."""
  app=self.app;view=app.link.performance.view();status=view['status'];title=running_title(app.link.status) if app.link.online else None
  parts=watts(status) if title else None;recording=bool(app.recorder.active and app.recorder.state=='recording');trophy=picture=None
  if self.trophy_last:
   earned,at,game=self.trophy_last;picture=earned.get('icon') or None
   trophy=dict(count=self.trophy_count,name=earned.get('name') or '',grade=earned.get('grade') or '',at=at,game=game,picture=bool(picture))
  chat=self.chat_view()
  self.api.publish(dict(app='PlayBridge',version=app_version.VERSION,now=time.time(),connected=bool(linked),console=bool(app.link.online),
   game=dict(title=title,name=app.link.game_name(title),since=app.presence_started) if title else None,
   fps=view['game_fps'] if title else None,lowest=view.get('lowest') if title else None,cpu=reading(status,'cpu_c') if title else None,soc=reading(status,'soc_c') if title else None,
   watts=round(sum(parts),1) if parts else None,recording=recording,recordingSeconds=round(time.perf_counter()-self.recording_at) if recording and self.recording_at else None,
   live=dict(state=app.broadcast.state,service=app.broadcast.name,seconds=round(app.broadcast.elapsed())) if app.broadcast.active else None,
   mic=bool(app.microphone.on),timer=self.run_timer.view() if self.timer_shown else None,trophy=trophy,
   chat=dict(channel=chat['channel'],messages=[{key:message[key] for key in ('id','name','colour','text','badges','kind','at')} for message in chat['messages']]) if chat else None),picture)
 def api_view(self):
  api=self.api;on=bool(self.core.config().get('api_on',False))
  state='On. Only programs on this PC can use these addresses.' if api.running else api.error if on else ''
  return dict(apiOn=on,apiRunning=api.running,apiAddress=api.address(),apiOverlay=api.address('overlay'),apiState=dict(text=state,tone='news' if api.running else 'error'))
 def do_api(self,on):
  self.core.save_config(api_on=bool(on))
  if on:self.start_api()
  else:self.api.stop()
  self.refresh_settings()
 def do_api_copy(self,which):
  if not self.api.running:return
  QGuiApplication.clipboard().setText(self.api.address('overlay' if which=='overlay' else ''))
  self.app.notify('The OBS overlay address is copied.' if which=='overlay' else 'The control address is copied. Add a command at its end, such as screenshot.')
 def do_api_open(self,_):
  if self.api.running:QDesktopServices.openUrl(QUrl(self.api.address()))
 def do_api_secret(self,_):
  """A new secret: every address made with the old one stops working."""
  self.core.save_config(api_secret=local_api.new_secret())
  if self.api.running:self.start_api()
  self.app.notify('Local control has a new secret. Paste the new addresses into your Stream Deck and OBS.');self.refresh_settings()
 def chat_view(self):
  """The chat panel's newest messages, or None when there is no channel or nothing to show."""
  app=self.app
  if not app.chat_channel:return None
  now=time.time();messages=app.chat.view(now,CHAT_SECONDS if self.core.config().get('chat_fade',True) else None)
  return dict(channel=app.chat_channel,messages=messages,now=now) if messages else None
 def chat_settings(self):
  saved=self.core.config();app=self.app;state=app.chat.text() if app.chat_channel else ''
  return dict(chatChannel=app.chat_channel,chatState=dict(text=state,tone='news' if state.startswith('Reading') else 'error' if 'suspended' in state else 'plain'),
   chatScreen=bool(saved.get('chat_screen',True)),chatStream=bool(saved.get('chat_stream',False)),chatFade=bool(saved.get('chat_fade',True)))
 def do_chat_channel(self,text):
  typed=str(text or '').strip();name=twitch_chat.channel_name(typed);app=self.app
  if typed and not name:self.chat_problem='A Twitch channel name has 4 to 25 letters, digits or underscores.';self.refresh_settings();return
  self.chat_problem='';app.chat_channel=name;self.core.save_config(twitch_chat=name);app.chat.poke();self.refresh_settings()
 def do_chat_screen(self,on):self.core.save_config(chat_screen=bool(on));self.refresh_settings()
 def do_chat_stream(self,on):self.core.save_config(chat_stream=bool(on));self.refresh_settings()
 def do_chat_fade(self,on):self.core.save_config(chat_fade=bool(on));self.refresh_settings()
 def discord_view(self):
  """Discord's two cards in Connections: the profile, and the channel that receives your captures."""
  app=self.app;chosen=app.discord;presence=app.presence;problem=getattr(self,'discord_problems',{})
  state=('',"plain")
  if problem.get('app'):state=(problem['app'],'error')
  elif chosen['app']:
   game=app.playing_name();text=presence.text(game)
   if presence.pipe is not None and not game:text+=' Your profile shows the game while one runs on your PS5.'
   state=(text or 'Looking for Discord on this PC…','news' if presence.pipe is not None else 'error' if 'refused' in text or 'not a number' in text else 'plain')
  hook=app.discord_hook;sent=problem.get('url') or hook.status
  if not sent and chosen['url']:sent='Ready. Your captures go to this channel as you save them.'
  if hook.working():sent='Sending to your channel…'+(' A clip is made again first, no faster than it plays while a stream is on.' if hook.current and hook.current[0] not in ('Screenshot','Test') else '')
  tone='error' if problem.get('url') or any(word in sent for word in ('not attached','Could not','no longer','refused','Paste','answered','busy')) else 'news' if sent else 'plain'
  return dict(discordApp=chosen['app'],discordState=dict(text=state[0],tone=state[1]),discordUrl=chosen['url'],discordShots=chosen['kinds']['Screenshot'],
   discordTrophies=chosen['kinds']['Trophy clip'],discordClips=chosen['kinds']['Replay'],discordStatus=dict(text=sent,tone=tone),discordReady=bool(chosen['url']))
 def do_discord_app(self,text):
  problems=getattr(self,'discord_problems',{});problems['app']=self.app.set_discord(app_id=str(text or ''));self.discord_problems=problems;self.refresh_settings()
 def do_discord_url(self,text):
  problems=getattr(self,'discord_problems',{});problems['url']=self.app.set_discord(url=str(text or ''));self.discord_problems=problems;self.refresh_settings()
 def do_discord_shots(self,on):self.app.set_discord(kind='discord_shots',on=bool(on));self.refresh_settings()
 def do_discord_trophies(self,on):self.app.set_discord(kind='discord_trophies',on=bool(on));self.refresh_settings()
 def do_discord_clips(self,on):self.app.set_discord(kind='discord_clips',on=bool(on));self.refresh_settings()
 def do_discord_test(self,_):
  problems=getattr(self,'discord_problems',{});problems['url']=self.app.discord_hook.test();self.discord_problems=problems;self.refresh_settings()
 def open_trophy_guide(self,game,trophy):
  """A trophy chosen in the trophy list: a search for its guide in this PC's browser."""
  QDesktopServices.openUrl(QUrl(trophy_guides.guide_url(game,trophy)));self.say_line(trophy_guides.guide_line(game,trophy))
 def do_discord_page(self,_):QDesktopServices.openUrl(QUrl('https://discord.com/developers/applications'))
 # PlayStation Network.
 def keep_psn_token(self,token,until):self.core.save_config(psn_token=live_broadcast.seal(token) if token else '',psn_until=until if token else 0)
 def psn_picture(self,name):return file_url(self.core.STATE/'psn'/'pictures'/name) if name else ''
 def psn_settings(self):return friends_view.settings(self.psn.view(),self.psn.wants,self.psn_problem,time.time())
 def show_friends(self):
  """The Friends page, put again only when something on it changed (the times on it move every half minute)."""
  view=self.psn.view();running=self.app.playing_name();playing=self.voice.playing
  # A picture chosen for a conversation that is no longer open is not sent anywhere else.
  if self.chat_outgoing and self.chat_outgoing['thread']!=view.get('thread'):self.drop_outgoing()
  # The options card is the open conversation's, and reactions are chosen for a message still shown.
  if self.chat_card=='options' and not view.get('thread'):self.chat_card=''
  if self.chat_picking and not any(m.get('id')==self.chat_picking for m in view.get('messages') or []):self.chat_picking=''
  outgoing=self.chat_outgoing;key=repr((view,running,playing,self.friend_finder,outgoing,self.friends_filter,self.chat_card,self.chat_picking,int(time.time()//30)))
  if key!=self.psn_seen:
   self.psn_seen=key
   picture=dict(image=file_url(outgoing['path']),name=outgoing['name']) if outgoing else None
   self.put('friends',dict(friends_view.page(view,time.time(),self.friends_filter,self.psn_picture,running,self.chat_picture,playing),finderOpen=self.friend_finder,outgoing=picture,
    chatCard=self.chat_card,picking=self.chat_picking))
 def chat_picture(self,name):return file_url(self.core.STATE/'psn'/'chat'/name) if name else ''
 def media_ready(self,kind,path,message_id):
  """A voice message or video PSN has sent, on the PSN thread: the voice message plays, the video opens in Windows' player."""
  if kind=='voice':
   problem=self.voice.play(message_id,path)
   if problem:self.app.notify(problem)
   return
  try:os.startfile(str(path))
  except OSError:self.app.notify('Windows has no player for this video.')
 def do_psn_media(self,message_id):
  message_id=str(message_id or '')
  if message_id and self.voice.playing==message_id:self.voice.stop();self.sounds.play('back');return
  self.psn.open_media(message_id);self.sounds.play('accept')
 def do_psn_picture_open(self,message_id):
  """A picture of the open conversation, whole, in Windows' own viewer."""
  message=next((m for m in list(self.psn.messages) if m.get('id')==str(message_id) and m.get('media')),None)
  path=self.psn.media_file(self.psn.media.get(message['media']['key'])) if message else None
  if path is not None:QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)));self.sounds.play('accept')
 # Friends: find a player by online ID, and the five changes.
 def do_friend_find_open(self,_):self.friend_finder=True;self.sounds.play('accept');self.show_friends()
 def do_friend_find(self,text):self.psn.find(str(text or ''));self.sounds.play('accept')
 def do_friend_find_close(self,_):self.friend_finder=False;self.psn.clear_find();self.sounds.play('back');self.show_friends()
 def friend_change(self,kind,key):
  key=str(key or '')
  if key.isdigit():self.psn.befriend(kind,key);self.sounds.play('accept')
 def do_friend_add(self,key):self.friend_change('add',key)
 def do_friend_accept(self,key):self.friend_change('accept',key)
 def do_friend_decline(self,key):self.friend_change('decline',key)
 def do_friend_cancel(self,key):self.friend_change('cancel',key)
 def do_friend_remove(self,key):
  key=str(key or '');name=self.psn.name_of(key) or 'This player'
  if key.isdigit():self.ask_first(f'Remove {name}?',f'{name} stops being your friend on PSN, on your PlayStation and in the PlayStation App too. You can send them a friend request again later.','Remove friend',lambda:self.friend_change('remove',key))
 def do_psn_connect(self,text):
  self.psn_problem=self.psn.sign_in(str(text or ''));self.refresh_settings()
 def do_psn_signout(self,_):
  self.psn.sign_out();self.psn_problem='';self.psn.favourites=set();self.core.save_config(psn_favourites=[])
  self.app.notify('Signed out of PSN. PlayBridge forgot your friends and your sign-in.');self.refresh_settings()
 def psn_want(self,key,setting,value):self.psn.wants=dict(self.psn.wants,**{key:value});self.core.save_config(**{setting:value});self.refresh_settings()
 def do_psn_online(self,on):self.psn_want('online','psn_online',bool(on))
 def do_psn_games(self,on):self.psn_want('games','psn_games',bool(on))
 def do_psn_messages(self,on):self.psn_want('messages','psn_messages',bool(on))
 def do_psn_requests(self,on):self.psn_want('requests','psn_requests',bool(on))
 def do_psn_favs_only(self,on):self.psn_want('favourites_only','psn_favourites_only',bool(on))
 def do_psn_watch(self,text):self.psn_want('watch','psn_watch',' '.join(str(text or '').split())[:200])
 def do_psn_signin_page(self,_):QDesktopServices.openUrl(QUrl(psn_link.SIGN_IN_PAGE))
 def do_psn_code_page(self,_):QDesktopServices.openUrl(QUrl(psn_link.NPSSO_PAGE))
 def do_psn_settings(self,_):self.section='connect';self.show_page('settings');self.refresh_settings()
 def do_psn_refresh(self,_):self.psn.refresh_now();self.sounds.play('accept')
 def do_friends_filter(self,name):
  if name in friends_view.FILTERS:self.friends_filter=name;self.sounds.play('move');self.show_friends()
 def do_friend_favourite(self,key):
  key=str(key);kept=set(self.psn.favourites)
  if not key.isdigit():return
  kept^={key};self.psn.favourites=kept;self.core.save_config(psn_favourites=sorted(kept));self.sounds.play('accept');self.show_friends()
 def do_friend_trophies(self,key):self.trophy_book.compare_with(str(key));self.sounds.play('accept');self.show_page('trophies')
 # Trophies from PSN.
 def ask_shelf_trophies(self,link):
  """The console games whose trophies the console's files do not give, asked about on PSN for the Games page: the PS4 games at once,
  the others once the console has read what it can this session."""
  key=(link.own_revision,bool(link.trophy_jobs),self.psn.state)
  if key==self.trophy_shelf_seen:return
  self.trophy_shelf_seen=key
  if self.psn.state!='on':return
  done=not link.trophy_jobs
  self.trophy_book.want_titles([game['title'] for game in link.games if not game.get('app') and (game['title'].startswith('CUSA') or done) and not (link.own_trophy_set(game['title']) or {}).get('known')])
 def trophy_icon(self,url):
  name=self.trophy_book.icon_file(url);return file_url(self.core.STATE/'psn'/'trophies'/'icons'/name) if name else ''
 def show_trophies(self):
  view=self.trophy_book.view();psn=self.psn.view();friends=[(friend['id'],friend['name']) for friend in psn['friends'] if friend.get('name')]
  key=repr((view['changes'],psn['state'],psn['problem'],self.trophy_filter,friends,psn['me'].get('name'),psn['me'].get('picture')))
  if key==self.trophy_seen:return
  self.trophy_seen=key;me=psn['me'];opened=view['open'] or {}
  # Pictures from Sony's image server: the games on the list and the open game's trophies.
  self.trophy_book.want_icons([((opened.get('title') or {}).get('icon',''))]+[row['icon'] for row in opened.get('rows',[]) if not row['hidden'] or row['earned']]+[title['icon'] for title in view['titles'][:120]])
  self.put('trophies',psn_trophies.page(psn['state'],view,friends,self.trophy_filter,self.trophy_icon,dict(name=me.get('name',''),picture=self.psn_picture(me.get('picture')))))
 def do_trophy_filter(self,name):
  if name in psn_trophies.FILTERS:self.trophy_filter=name;self.sounds.play('move');self.show_trophies()
 def do_trophy_open(self,key):self.trophy_book.show_set(str(key));self.sounds.play('accept');self.show_trophies()
 def do_trophy_close(self,_):self.trophy_book.close_set();self.sounds.play('back');self.show_trophies()
 def do_trophy_compare(self,name):
  name=str(name or '');found=next((friend['id'] for friend in self.psn.view()['friends'] if friend.get('name')==name),'')
  self.trophy_book.compare_with(found);self.sounds.play('accept');self.show_trophies()
 def do_trophy_refresh(self,_):self.trophy_book.refresh();self.sounds.play('accept')
 def do_trophy_guide(self,number):
  """A trophy chosen in an open game: a search for its guide, as on the Games page."""
  opened=self.values['trophies'].get('open') or {};row=next((row for row in opened.get('rows',[]) if row['id']==number),None)
  if row:self.open_trophy_guide(opened.get('name',''),dict(name='' if row['name']=='Hidden trophy' else row['name']))
 def do_friend_message(self,key):
  if self.friend_finder:self.friend_finder=False;self.psn.clear_find()
  self.psn.chat_with(str(key));self.sounds.play('accept')
 def do_psn_chat(self,group_id):self.psn.open_chat(str(group_id));self.sounds.play('accept')
 def do_psn_chat_close(self,_):self.psn.close_chat();self.sounds.play('back')
 def do_psn_send(self,text):
  thread=self.psn.thread_id;outgoing=self.chat_outgoing
  if thread and outgoing and outgoing['thread']==thread:
   # The picture goes with the words written under it, as one message.
   if self.psn.send_picture(thread,outgoing['path'],str(text or ''),outgoing['passing']):self.chat_outgoing=None;self.sounds.play('accept');self.show_friends()
   return
  if thread and self.psn.send(thread,str(text or '')):self.sounds.play('accept')
 # A picture for the open conversation: chosen in Windows' file window, dragged in from Explorer, or pasted (a screenshot, say).
 @Slot(result=bool)
 def clipboardPicture(self):
  """Whether what is copied is a picture (and not words), so Ctrl+V in the chat takes it as one."""
  data=QGuiApplication.clipboard().mimeData()
  return bool(data is not None and data.hasImage() and not data.hasText())
 def hold_outgoing(self,path,passing=False):
  thread=self.psn.thread_id
  if not thread:
   if passing:Path(path).unlink(missing_ok=True)
   return
  self.drop_outgoing();self.chat_outgoing=dict(path=str(path),name=Path(path).name if not passing else 'Pasted picture',passing=passing,thread=thread)
  self.sounds.play('accept');self.show_friends()
 def drop_outgoing(self):
  outgoing,self.chat_outgoing=self.chat_outgoing,None
  if outgoing and outgoing['passing']:Path(outgoing['path']).unlink(missing_ok=True)
 def do_psn_picture_file(self,url):
  path=QUrl(str(url)).toLocalFile() if str(url).startswith('file:') else str(url)
  if path and Path(path).is_file():self.hold_outgoing(path)
 def do_psn_picture_drop(self,urls):
  paths=[QUrl(str(url)).toLocalFile() if str(url).startswith('file:') else str(url) for url in (urls if isinstance(urls,(list,tuple)) else [urls])]
  chosen=next((path for path in paths if path and Path(path).is_file()),None)
  if chosen:self.hold_outgoing(chosen)
 def do_psn_picture_paste(self,_):
  image=QGuiApplication.clipboard().image()
  if image.isNull() or not self.psn.thread_id:return
  folder=self.core.STATE/'psn'/'outgoing';folder.mkdir(parents=True,exist_ok=True)
  path=folder/f'pasted-{int(time.time()*1000)}.png'
  if image.save(str(path),'PNG'):self.hold_outgoing(path,passing=True)
  else:self.app.notify('PlayBridge could not take the pasted picture.')
 def do_psn_picture_clear(self,_):self.drop_outgoing();self.sounds.play('back');self.show_friends()
 # What can be done to a message of the open conversation: react, copy, save its picture, delete it for everyone, take it off this PC.
 def chat_message(self,message_id):
  return next((m for m in list(self.psn.messages) if m.get('id')==str(message_id or '')),None) if self.psn.thread_id else None
 def do_psn_react_open(self,message_id):
  message=self.chat_message(message_id)
  if message is None:return
  self.chat_picking='' if self.chat_picking==message['id'] else message['id'];self.sounds.play('accept' if self.chat_picking else 'back');self.show_friends()
 def do_psn_react_close(self,_):self.chat_picking='';self.sounds.play('back');self.show_friends()
 def do_psn_react(self,value):
  """[message id, reaction id]: given, or taken back when it is the player's own."""
  try:message_id,reaction_id=(str(part) for part in value)
  except (TypeError,ValueError):return
  if self.chat_message(message_id) is not None and self.psn.react(self.psn.thread_id,message_id,reaction_id):self.chat_picking='';self.sounds.play('accept');self.show_friends()
 def do_psn_copy(self,message_id):
  message=self.chat_message(message_id)
  if message is None:return
  if message.get('kind')=='text':QGuiApplication.clipboard().setText(message.get('text') or '');self.psn.note('Copied the message.')
  else:
   path=self.psn.media_file(self.psn.media.get((message.get('media') or {}).get('key')));image=QImage(str(path)) if path else QImage()
   if image.isNull():self.psn.note('PlayBridge cannot copy this picture.','error');return
   QGuiApplication.clipboard().setImage(image);self.psn.note('Copied the picture. Paste it anywhere with Ctrl+V.')
  self.sounds.play('accept');self.show_friends()
 def do_psn_picture_save(self,value):
  """[message id, the file chosen in Windows' save window]: the kept picture copied there as it came from PSN."""
  try:message_id,url=(str(part) for part in value)
  except (TypeError,ValueError):return
  message=self.chat_message(message_id);kept=self.psn.media_file(self.psn.media.get(((message or {}).get('media') or {}).get('key')))
  target=Path(QUrl(url).toLocalFile() if url.startswith('file:') else url)
  if kept is None or not str(target):return
  if target.suffix.lower()!=kept.suffix.lower():target=target.with_name(target.name+kept.suffix)
  try:shutil.copyfile(kept,target)
  except OSError:self.psn.note('Windows did not let PlayBridge save the picture there. Choose another folder.','error')
  else:self.psn.note(f'Saved the picture as {target.name}.');self.sounds.play('accept')
  self.show_friends()
 def do_psn_delete(self,message_id):
  message=self.chat_message(message_id);thread=self.psn.thread_id
  if message is None or not message.get('mine'):return
  self.ask_first('Delete this message?','It is deleted for everyone in the conversation: on PSN, in the PlayStation App and on their PlayStation. This cannot be undone.',
   'Delete for everyone',lambda:self.psn.delete_message(thread,message['id']) and self.sounds.play('accept'))
 def do_psn_hide(self,message_id):
  message=self.chat_message(message_id);thread=self.psn.thread_id
  if message is None:return
  what='picture' if message.get('kind') in ('picture','gif','sticker') else 'voice message' if message.get('kind')=='voice' else 'video' if message.get('kind')=='video' else 'message'
  why='It is yours, but PSN lets you delete a message only in the 10 minutes after you send it.' if message.get('mine') else 'PSN lets people delete only the messages they sent.'
  def hide():self.psn.hide_message(thread,message['id']);self.sounds.play('accept');self.show_friends()
  self.ask_first(f'Remove this {what} from this PC?',f'PlayBridge stops showing it and deletes its copy from this PC. Everyone in the conversation still has it, on PSN too. {why}','Remove from this PC',hide)
 def do_psn_typing(self,_):
  if self.psn.thread_id:self.psn.typing(self.psn.thread_id)
 # The open conversation's options, and new groups.
 def chat_group(self):return next((g for g in list(self.psn.groups) if g['id']==self.psn.thread_id),None) if self.psn.thread_id else None
 def do_psn_options(self,_):
  if self.chat_group() is not None:self.chat_card='options';self.chat_picking='';self.sounds.play('accept');self.show_friends()
 def do_psn_group_new(self,_):self.chat_card='new';self.chat_picking='';self.sounds.play('accept');self.show_friends()
 def do_psn_card_close(self,_):self.chat_card='';self.sounds.play('back');self.show_friends()
 def group_change(self,kind,value=None):
  group=self.chat_group()
  if group is not None and self.psn.change_group(kind,group['id'],value):self.sounds.play('accept');self.show_friends()
 def do_psn_chat_favourite(self,_):
  group=self.chat_group()
  if group is not None:self.group_change('favourite',not group.get('favourite'))
 def do_psn_mute(self,_):
  group=self.chat_group()
  if group is not None:self.group_change('mute',not group.get('muted'))
 def do_psn_rename(self,text):self.group_change('rename',' '.join(str(text or '').split()))
 def do_psn_invite(self,ids):self.group_change('invite',[str(key) for key in (ids if isinstance(ids,(list,tuple)) else [ids]) if str(key).isdigit()])
 def do_psn_member_remove(self,key):
  key=str(key or '');group=self.chat_group()
  if group is None or key not in [p['id'] for p in group.get('people') or []]:return
  name=self.psn.name_of(key) or next((p['name'] for p in group['people'] if p['id']==key),'') or 'This player'
  self.ask_first(f'Take {name} out of the group?',f'{name} stops getting the messages of {group["name"]}. Someone in the group can add them again.','Take out',lambda:self.group_change('remove',key))
 def do_psn_leave(self,_):
  group=self.chat_group()
  if group is None:return
  def leave():self.chat_card='';self.group_change('leave')
  self.ask_first(f'Leave {group["name"]}?','You stop getting its messages, on PSN and your PlayStation too. Someone in the group can add you again.','Leave group',leave)
 def do_psn_group_create(self,value):
  """[friends' account numbers, the group's name]: a new group, open once PSN made it."""
  try:ids,name=value[0],str(value[1] or '')
  except (TypeError,IndexError,KeyError):return
  if self.psn.new_group([str(key) for key in ids or []],name):self.chat_card='';self.sounds.play('accept');self.show_friends()
 def pad_status(self):
  """Where this PC's controller on the PS5 stands, for Settings."""
  pad=self.pad
  if not self.console_pad:return ''
  if not self.app.link.online:return 'Connect to your PS5 to add this PC\'s controller.'
  answer=pad.answer if pad.heard_at is not None and time.monotonic()-pad.heard_at<=pad.SILENT else None
  if answer and answer[0]==1 and answer[3]:return f'Controller {answer[3]} on your PS5.'+('' if pad.name else ' No controller on this PC: the keyboard plays.')
  if answer and answer[0]==1:return "Ready. This PC's controller joins your PS5 with your first press in the live view."+('' if pad.name else ' No controller on this PC: the keyboard plays.')
  if answer and answer[0]==2:return 'The controller on your PS5 could not start ('+('four controllers are in use' if answer[1]&0xffffffff==0x50420005 else f'{answer[1]&0xffffffff:08x}')+').'
  if answer:return 'The controller on your PS5 is starting…'
  return pad.companion_note or 'Waiting for the controller payload on your PS5…'
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
 def do_console_pad(self,on):
  self.console_pad=bool(on);self.core.save_config(console_pad=self.console_pad)
  self.say_line('Your controller and keyboard play on your PS5 from the live view.' if on else 'Your controller and keyboard stay on this PC.','news');self.refresh_settings()
 def do_pad_key(self,value):
  """A key down or up in the live view: {key, down}."""
  name=self.key_codes.get(int((value or {}).get('key',0)))
  if name:(self.pad.keyboard.press if value.get('down') else self.pad.keyboard.release)(name,time.monotonic())
 def do_pad_keys_clear(self,_):self.pad.keyboard.clear();self.stop_aim()
 def aim_title(self):return running_title(self.app.link.status) or ''
 def do_video_tap(self,_):
  """A click on the picture with mouse aim on starts aiming."""
  if self.aiming or self.values['page']!='live' or not self.has_video or not self.core.config().get('mouse_aim',False):return
  if not self.console_pad:self.app.notify('Turn on Play on your PS5 in Settings › Console to aim with the mouse.');return
  if self.pad.sending:self.start_aim()
 def start_aim(self):
  """The pointer hides and stays in the middle of the window, and the mouse moves the right stick."""
  if self.raw_mouse is None:self.raw_mouse=RawMouse(self.aim,lambda:self.hwnd)
  if not self.raw_mouse.begin() or not self.raw_mouse.start():
   self.app.event(f'Mouse aim not started: {self.raw_mouse.error}');self.app.notify('Windows did not give PlayBridge the mouse, so it cannot aim.');return
  self.aim.start(self.aim_profiles.get(self.aim_title()));self.aiming=True
  QGuiApplication.setOverrideCursor(QCursor(Qt.CursorShape.BlankCursor));hold_pointer(self.hwnd)
  self.app.notify('Aiming with the mouse. Escape lets go.')
 def stop_aim(self):
  if not getattr(self,'aiming',False):return
  self.aiming=False;self.aim.stop()
  if self.raw_mouse is not None:self.raw_mouse.stop()
  free_pointer();QGuiApplication.restoreOverrideCursor()
 def do_mouse_aim(self,on):
  self.core.save_config(mouse_aim=bool(on))
  if not on:self.stop_aim()
  self.refresh_settings()
 def do_aim_value(self,value):
  """A setting moved: {name, value}, for the game running now, or for every game without its own when none runs."""
  value=dict(value or {});name=value.get('name')
  if name not in ('sensitivity','curve','deadzone','invert'):return
  profile=self.aim_profiles.set(self.aim_title(),**{name:value.get('value')});self.aim.set_profile(profile)
  if name=='invert':self.aim_profiles.save();self.refresh_settings()
 def do_aim_done(self,_):self.aim_profiles.save();self.refresh_settings()
 def fan_line(self):
  link=self.app.link;return fan_target.describe(link.status,link.online,link.fan_level(),link.fan_error)
 def fan_view(self):
  link=self.app.link;title=running_title(link.status);every=link.fans.get('')
  game=dict(name=link.game_name(title),level=fan_target.LABELS[link.fans.get(title)] if link.fans.own(title) else fan_target.SAME) if title else None
  return dict(fanText=self.fan_line(),fanLevels=list(fan_target.LABELS.values()),fanEvery=fan_target.LABELS[every],fanGame=game,fanGameLevels=[fan_target.SAME]+list(fan_target.LABELS.values()))
 def fan_pick(self,label):return next((key for key,text in fan_target.LABELS.items() if text==label),None)
 def do_fan_every(self,label):
  level=self.fan_pick(label)
  if level:self.app.link.fans.set('',level);self.app.link.fan_error=0;self.refresh_settings()
 def do_fan_game(self,label):
  title=running_title(self.app.link.status)
  if not title:return
  level=self.fan_pick(label)
  if level or label==fan_target.SAME:self.app.link.fans.set(title,level);self.app.link.fan_error=0;self.refresh_settings()
 # Controller profiles.
 def use_pad_profile(self):
  profile=self.pad_profiles.get(self.aim_title());self.pad.change=None if profile==pad_profiles.DEFAULT else partial(pad_profiles.apply,profile)
 def pad_profile_view(self):
  title=self.aim_title();profile=self.pad_profiles.get(title);own=self.pad_profiles.own(title)
  if title:name=self.app.link.game_name(title);note=f'This is {name}\'s profile.'+('' if own else ' It uses the one for every game until you change something.')
  else:note='This is the profile for every game without one of its own. Change it while a game runs to make that game\'s own.'
  labels=[pad_profiles.LABELS[key] for key in pad_profiles.BUTTONS]
  return dict(padProfile=dict(profile,forText=note,own=own,text=pad_profiles.describe(profile),hand=pad_profiles.HAND_NAMES[profile['one_hand']],rate=f"{profile['turbo_rate']} a second",
   pairs=[f'{pad_profiles.LABELS[a]} plays as {pad_profiles.LABELS[b]}' for a,b in profile['remap']],turboButtons=[dict(key=key,label=pad_profiles.LABELS[key],on=key in profile['turbo']) for key in pad_profiles.TURBO_BUTTONS]),
   padHands=list(pad_profiles.HAND_NAMES.values()),padRates=[f'{rate} a second' for rate in pad_profiles.RATES],padButtons=labels)
 def pad_profile_set(self,**changes):
  self.pad_profiles.set(self.aim_title(),**changes);self.use_pad_profile();self.refresh_settings()
 def do_pad_profile(self,value):
  """A switch or a choice in the profile card: {name, value}."""
  value=dict(value or {});name=value.get('name');chosen=value.get('value')
  if name in ('swap_face','swap_shoulders','swap_sticks','invert_ly','invert_ry'):self.pad_profile_set(**{name:bool(chosen)})
  elif name=='one_hand':
   hand=next((key for key,text in pad_profiles.HAND_NAMES.items() if text==chosen),None)
   if hand:self.pad_profile_set(one_hand=hand)
  elif name=='turbo_rate':
   rate=next((rate for rate in pad_profiles.RATES if f'{rate} a second'==chosen),None)
   if rate:self.pad_profile_set(turbo_rate=rate)
 def do_pad_turbo(self,key):
  turbo=list(self.pad_profiles.get(self.aim_title())['turbo'])
  if key in pad_profiles.TURBO_BUTTONS:self.pad_profile_set(turbo=[name for name in turbo if name!=key] if key in turbo else turbo+[key])
 def pad_key(self,label):return next((key for key,text in pad_profiles.LABELS.items() if text==label),None)
 def do_pad_pair_add(self,value):
  try:source,target=(self.pad_key(label) for label in value)
  except (TypeError,ValueError):return
  if not source or not target or source==target:self.say_line('Choose two different buttons.','error');return
  remap=[pair for pair in self.pad_profiles.get(self.aim_title())['remap'] if pair[0]!=source]
  self.pad_profile_set(remap=remap+[[source,target]])
 def do_pad_pair_remove(self,index):
  remap=list(self.pad_profiles.get(self.aim_title())['remap'])
  try:del remap[int(index)]
  except (TypeError,ValueError,IndexError):return
  self.pad_profile_set(remap=remap)
 def do_pad_profile_forget(self,_):
  self.pad_profiles.forget(self.aim_title());self.use_pad_profile();self.refresh_settings()
 def aim_view(self):
  title=self.aim_title();profile=self.aim_profiles.get(title)
  if title:own=self.aim_profiles.own(title);name=self.app.link.game_name(title);note=f'These are for {name}.'+('' if own else ' It uses the settings for every game until you change one.')
  else:note='These are for every game without settings of its own. Change them while a game runs to keep that game\'s own.'
  return dict(mouseAim=bool(self.core.config().get('mouse_aim',False)),mouseHelp=MOUSE_HELP,aim=dict(profile,forText=note))
 def do_phone(self,on):
  if on and not self.phones.start():self.say_line(self.phones.error,'error');self.refresh_settings();return
  if not on:self.phones.stop()
  self.core.save_config(phone_on=bool(on));self.refresh_settings()
 def do_phone_pair(self,_):
  if not self.phones.running:return
  self.pairing.new_code(time.monotonic());self.refresh_settings()
 def do_phone_disconnect(self,_):
  count=self.phones.disconnect()
  self.say_line(f'{count} phone'+('s' if count!=1 else '')+' disconnected. A phone connects again from its own page.' if count else 'No phone is connected.','news');self.refresh_settings()
 def do_phone_forget(self,_):
  # A phone that is forgotten is let go now too, not only at its next connection.
  self.pairing.forget();self.phones.disconnect();self.say_line('Every phone was forgotten and disconnected. Each one pairs again with a new code.','news');self.refresh_settings()
 def phone_view(self):
  """What Settings › Phone shows."""
  showing=self.pairing.showing(time.monotonic()) if self.phones.running else None;count=self.pairing.count();watching=self.phones.phones
  address=f'http://{phone_link.local_address(self.app.args.host)}:{self.phones.port}' if self.phones.running else ''
  state=self.app.phone_feed.error if self.phones.running and self.app.phone_feed.error else ('No phone is watching.' if not watching else f'{watching} phone'+('s' if watching>1 else '')+' watching'+(f', {self.app.phone_feed.mode}.' if self.app.phone_feed.mode else '.')) if self.phones.running else self.phones.error
  return dict(phoneOn=self.phones.running,phoneAddress=address,phoneCode=showing[0] if showing else '',phoneCodeLeft=showing[1] if showing else 0,
   phonePaired=f'{count} phone'+('s' if count!=1 else '')+' paired.' if count else 'No phone paired yet.',phoneState=state,phonePlay=bool(self.console_pad),
   phoneWatching=watching if self.phones.running else 0)
 # The PS5's files.
 def files_host(self):return (self.typed_host or self.app.args.host).strip()
 def files_list(self,path):
  self.files_loading=True;self.files_session.ask('list',path=path or '/');self.show_files()
 def files_entry(self,name):return next((entry for entry in self.files_entries if entry['name']==name),None)
 def show_files(self):
  """The Files page: where it stands, what is there, and what a copy has done so far."""
  session=self.files_session;path=self.files_path;busy=session.busy if session.busy in ('get','put') else ''
  progress=session.progress;share=progress[0]/progress[1] if busy and progress and progress[1] else 0.0
  crumbs=[dict(label='PS5',path='/')];walked=''
  for part in [part for part in path.split('/') if part]:walked+='/'+part;crumbs.append(dict(label=part,path=walked))
  entries=[dict(name=entry['name'],folder=bool(entry['folder'] or entry['link']),link=entry['link'],size='' if entry['folder'] or entry['link'] else ftp_files.size_text(entry['size']),
   when=ftp_files.when_text(entry['when']),selected=entry['name']==self.files_selected) for entry in self.files_entries[:3000]]
  if self.files_loading and not self.files_ready:empty='Looking for the FTP server on your PS5…'
  elif not self.files_ready:empty=self.files_line[0] or 'Start an FTP server on your PS5 from your homebrew menu. PlayBridge finds it on port 2121, 1337 or 21.'
  else:empty='' if entries else 'This folder is empty.'
  chosen=self.files_entry(self.files_selected)
  self.put('files',dict(path=path,crumbs=crumbs,places=[dict(label=label,path=place) for label,place in ftp_files.PLACES],entries=entries,count=len(entries),
   line=dict(text=self.files_line[0],tone=self.files_line[1]) if self.files_ready else dict(text='',tone='plain'),loading=self.files_loading,ready=self.files_ready,empty=empty,
   busy=busy,busyText=('Copying to your PC' if busy=='get' else 'Sending to your PS5' if busy=='put' else '')+(f'  ·  {ftp_files.size_text(progress[0])} of {ftp_files.size_text(progress[1])}' if busy and progress and progress[1] else ''),
   share=round(share,3),selected=self.files_selected if chosen else '',selectedFolder=bool(chosen and (chosen['folder'] or chosen['link'])),canUp=path!='/',
   server=f'FTP on port {self.files_session.port}' if self.files_ready and self.files_session.port else '',
   # Show on this PC belongs to the line about a copy just made, not to whatever came after it.
   saved=bool(self.files_saved) and self.files_line[0].startswith('Copied '),
   selectedPreview=bool(chosen and not (chosen['folder'] or chosen['link']) and ftp_files.preview_kind(chosen['name'],chosen['size'])),preview=self.files_preview))
 def finish_files(self,answer):
  kind=answer['kind'];ok=answer['ok']
  if kind=='list':
   self.files_loading=False
   if ok:
    value=answer['value'];moved=value['path']!=self.files_path;self.files_path=value['path'];self.files_entries=value['entries'];self.files_ready=True
    if moved or not self.files_entry(self.files_selected):self.files_selected=''
    if moved:self.files_line=('','plain');self.core.save_config(files_path=self.files_path)
   else:
    self.files_line=(answer['problem'],'error')
    if not self.files_entries:self.files_ready=False
  elif kind=='get':
   if ok:
    saved=Path(answer['value']['saved']);self.files_saved=str(saved);count=answer['value']['count']
    self.files_line=(f'Copied {saved.name} to Downloads\\PS5'+(f' ({count} files)' if count!=1 else '')+'.','news');self.app.notify(f'{saved.name} copied to Downloads\\PS5.')
   else:self.files_line=(answer['problem'],'error' if answer['problem']!='Stopped.' else 'plain')
  elif kind=='put':
   self.files_line=(f"Sent {answer['value']['count']} file"+('s' if answer['value']['count']!=1 else '')+' to the PS5.','news') if ok else (answer['problem'],'error')
   if answer.get('folder')==self.files_path:self.files_list(self.files_path)
  elif kind=='peek':
   if self.files_preview is None or self.files_preview.get('name')!=answer['name']:return
   if not ok:self.files_preview=dict(self.files_preview,loading=False,why=answer['problem'] if answer['problem']!='Stopped.' else 'Stopped.')
   else:self.files_preview=self.preview_view(answer['value'])
  elif kind in ('mkdir','rename','remove'):
   if ok:
    done=dict(mkdir='Made the folder {name}.',rename='Renamed to {name}.',remove='Deleted {name}.')[kind].format(name=answer['value']['name'])
    self.files_line=(done,'news');self.files_selected=answer['value']['name'] if kind!='remove' else ''
   else:self.files_line=(answer['problem'],'error')
   if answer.get('folder')==self.files_path:self.files_list(self.files_path)
  self.files_share=None;self.show_files()
 def do_files_go(self,path):self.files_line=('','plain');self.files_list(str(path or '/'))
 def do_files_up(self,_):
  if self.files_path!='/':self.files_list(ftp_files.parent(self.files_path))
 def do_files_refresh(self,_):self.files_list(self.files_path)
 def do_files_select(self,name):
  if self.files_entry(str(name)):self.files_selected=str(name);self.show_files()
 def do_files_open(self,name):
  """A folder opens; a text file or a picture is shown; another file is chosen (a second time copies it to the PC)."""
  entry=self.files_entry(str(name))
  if entry is None:return
  if entry['folder'] or entry['link']:self.sounds.play('accept');self.files_list(ftp_files.join(self.files_path,entry['name']))
  elif ftp_files.preview_kind(entry['name'],entry['size']):self.do_files_preview(entry['name'])
  elif self.files_selected==entry['name']:self.do_files_get(entry['name'])
  else:self.files_selected=entry['name'];self.show_files()
 def do_files_get(self,name):
  entry=self.files_entry(str(name or self.files_selected))
  if entry is None:return
  if self.files_session.busy in ('get','put'):self.files_line=('Wait for the copy that is running.','error');self.show_files();return
  self.files_line=('','plain');self.files_session.ask('get',path=ftp_files.join(self.files_path,entry['name']),folder=bool(entry['folder'] or entry['link']),size=entry['size']);self.show_files()
 def do_files_put(self,urls):
  """Files and folders from this PC (picked, or dropped on the page) into the folder on show."""
  paths=[QUrl(str(url)).toLocalFile() if str(url).startswith('file:') else str(url) for url in (urls if isinstance(urls,(list,tuple)) else [urls])]
  paths=[path for path in paths if path and (Path(path).is_file() or Path(path).is_dir())]
  if not paths:return
  if self.files_session.busy in ('get','put'):self.files_line=('Wait for the copy that is running.','error');self.show_files();return
  folder=self.files_path;taken=[Path(path).name for path in paths if self.files_entry(Path(path).name)]
  def send():self.files_line=('','plain');self.files_session.ask('put',files=paths,folder=folder);self.show_files()
  merged=any(Path(path).is_dir() for path in paths if Path(path).name in taken)
  if taken:self.ask_first('Replace on the PS5?',f"{', '.join(taken[:4])}{' and more' if len(taken)>4 else ''}\nalready in {folder} on the PS5. "+('Files with the same names are replaced.' if merged else 'Sending replaces '+('them' if len(taken)>1 else 'it')+'.'),'Replace',send)
  else:send()
 def do_files_mkdir(self,name):self.files_session.ask('mkdir',folder=self.files_path,name=str(name or '').strip())
 def do_files_rename(self,value):
  try:old,new=(str(part) for part in value)
  except (TypeError,ValueError):return
  if new.strip() and new.strip()!=old and self.files_entry(old):self.files_session.ask('rename',folder=self.files_path,old=old,new=new.strip())
 def do_files_remove(self,name):
  entry=self.files_entry(str(name or self.files_selected))
  if entry is None:return
  path=ftp_files.join(self.files_path,entry['name']);folder=entry['folder'] and not entry['link']
  def remove():self.files_session.ask('remove',folder=self.files_path,name=entry['name'],is_folder=folder)
  self.ask_first('Delete from the PS5?',f'{path}\n\n'+('Only an empty folder can be deleted. ' if folder else '')+'This cannot be undone.','Delete',remove)
 def do_files_preview(self,name):
  """A look at a text file or a picture on the PS5, read into memory, never kept as a copy."""
  entry=self.files_entry(str(name or self.files_selected))
  if entry is None or entry['folder'] or entry['link']:return
  kind=ftp_files.preview_kind(entry['name'],entry['size'])
  if not kind:self.files_line=(ftp_files.preview_of(entry['name'],b'')['why'] if not ftp_files.preview_kind(entry['name']) else f"{entry['name']} is too big to show here. Copy it to this PC to open it.",'error');self.show_files();return
  self.files_selected=entry['name'];self.files_preview=dict(name=entry['name'],kind=kind,size=ftp_files.size_text(entry['size']),loading=True,text='',image='',cut=False,why='')
  self.sounds.play('accept');self.files_session.ask('peek',path=ftp_files.join(self.files_path,entry['name']),name=entry['name'],look=kind,size=entry['size']);self.show_files()
 def preview_view(self,value):
  """What the preview shows, from the bytes read: the text, or the picture written to a file of its own in PlayBridge's folder for Qt to show."""
  shown=ftp_files.preview_of(value['name'],value['data'],value['cut']);base=dict(self.files_preview,loading=False)
  if shown['kind']=='text':return dict(base,text=shown['text'],cut=shown['cut'])
  if shown['kind']=='none':return dict(base,why=shown['why'])
  folder=self.core.STATE/'files-preview'
  try:
   shutil.rmtree(folder,ignore_errors=True);folder.mkdir(parents=True,exist_ok=True);self.files_looks+=1
   path=folder/f'look-{self.files_looks}{shown["ending"]}';path.write_bytes(value['data'])
  except OSError:return dict(base,why='PlayBridge could not keep the picture to show it.')
  return dict(base,image=file_url(path))
 def do_files_preview_close(self,_):
  if self.files_preview is None:return
  # The picture shown was only ever kept for Qt to read: it goes with the preview.
  self.files_preview=None;shutil.rmtree(self.core.STATE/'files-preview',ignore_errors=True);self.sounds.play('back');self.show_files()
 def do_files_stop(self,_):self.files_session.stop_copy()
 def do_files_show(self,_):
  saved=self.files_saved
  if saved and Path(saved).exists():subprocess.Popen(['explorer','/select,',str(Path(saved))])
  else:QDesktopServices.openUrl(QUrl.fromLocalFile(str(ftp_files.downloads())))
 # The payload shelf and the developer loop.
 def payloads_view(self):
  """The shelf of payloads from the chosen repository, and the developer loop's state, for the Console section."""
  shelf=self.payload_shelf;watch=self.dev_watch
  items=[dict(name=item['name'],tag=item.get('tag',''),size=payload_sender.size_label(item['size']) if item.get('size') else '',have=item['have'],update=item['update'],
   label=item['name']+(f"  ·  {item['tag']}" if item.get('tag') else '')) for item in shelf.items()]
  return dict(payloadRepo=shelf.repo,payloadItems=items,payloadShelfStatus=shelf.status,
   devWatch=str(watch.path) if watch else '',devWatchName=watch.path.name if watch else '',devAuto=self.dev_auto,
   devLine=dict(text=self.dev_line[0],tone=self.dev_line[1]),devLogOn=bool(self.klog and self.klog.running),
   devLog='\n'.join(self.klog_lines[-200:]),devLogError=self.klog.error if self.klog else '')
 def refresh_from_thread(self):
  """A worker finished; the UI thread repaints Settings when it drains the queue."""
  self.payload_results.put(('','','refresh-only'))
 def do_payload_repo(self,text):
  self.payload_shelf.set_repo(str(text or ''));self.core.save_config(payload_repo=self.payload_shelf.repo)
  self.payload_shelf.fetch(self.refresh_from_thread);self.refresh_settings()
 def do_payload_refresh(self,_):self.payload_shelf.fetch(self.refresh_from_thread);self.refresh_settings()
 def do_payload_get(self,name):
  """Downloads a payload onto this PC (it is not sent; the owner sends it with Send)."""
  item=next((item for item in self.payload_shelf.items() if item['name']==str(name)),None)
  if item is None:return
  self.payload_status=(f"Downloading {item['name']}…",'plain');self.refresh_settings()
  def work():
   try:self.payload_store.store(item,payload_manager.download(item));self.payload_results.put((item['name'],'','got'))
   except (payload_manager.CatalogError,payload_sender.PayloadError) as problem:self.payload_results.put((item['name'],'',str(problem)))
  threading.Thread(target=work,name='PlayBridge payload get',daemon=True).start()
 def do_payload_send(self,name):
  """Sends a shelf payload. It downloads first when needed, then asks before sending, like the Send card."""
  if self.payload_store.have(str(name)):self.send_file(self.payload_store.path(str(name)))
  else:self.do_payload_get(str(name))
 # The developer loop.
 def set_watch(self,path):
  self.dev_watch=payload_manager.Watch(path) if path and Path(path).is_file() else None;self.dev_auto=False;self.dev_line=('','plain')
 def do_dev_watch_file(self,url):
  path=QUrl(str(url)).toLocalFile() if str(url).startswith('file:') else str(url)
  if not path:return
  self.set_watch(path);self.core.save_config(dev_watch=str(path))
  self.dev_line=(f'Watching {Path(path).name}. Resend it, or turn on resend when it changes.','news') if self.dev_watch else ('That file is not there.','error');self.refresh_settings()
 def do_dev_auto(self,on):
  if not self.dev_watch:self.dev_line=('Choose an ELF to watch first.','error');self.refresh_settings();return
  if not on:self.dev_auto=False;self.dev_line=('Resend when it changes is off.','plain');self.refresh_settings();return
  typed=(self.typed_host or self.app.args.host).strip()
  def arm():self.dev_auto=True;self.dev_line=(f'Will resend {self.dev_watch.path.name} to {typed} whenever it changes, until you turn this off.','news');self.refresh_settings()
  self.ask_first('Resend on every change?',f'{self.dev_watch.path.name}\nwill be sent to the PS5 at {typed} each time it changes on disk, with full access to the console, until you turn this off.\n\nOnly watch an ELF you are building yourself.','Turn on',arm)
 def do_dev_resend(self,_):
  if not self.dev_watch:self.dev_line=('Choose an ELF to watch first.','error');self.refresh_settings();return
  self.dev_watch.changed();self.send_file(self.dev_watch.path)
 def do_dev_log(self,on):
  if on:self.klog=payload_manager.KernelLog((self.typed_host or self.app.args.host).strip());self.klog_lines=[];self.klog.start()
  elif self.klog is not None:self.klog.stop()
  self.refresh_settings()
 def do_dev_log_clear(self,_):self.klog_lines=[];self.refresh_settings()
 def poll_developer(self):
  """A couple of times a second: a changed watch file is resent when armed, and the kernel log's new lines are taken in."""
  now=time.perf_counter()
  if self.klog is not None:
   lines=self.klog.take()
   if lines:self.klog_lines.extend(lines);del self.klog_lines[:-payload_manager.LINE_LIMIT]
  if now-self.dev_at<0.4:return
  self.dev_at=now;on_settings=self.values['page']=='settings' and self.section=='console'
  if self.dev_watch is not None and self.dev_watch.changed():
   if self.dev_auto:self.dev_line=(f'{self.dev_watch.path.name} changed — resending…','plain');self.send_file(self.dev_watch.path)
   else:self.dev_line=(f'{self.dev_watch.path.name} changed. Resend it when you are ready.','news')
   if on_settings:self.refresh_settings()
  if self.klog is not None and on_settings:
   key=(len(self.klog_lines),self.klog.running,self.klog.error)
   if key!=self.dev_seen:self.dev_seen=key;self.refresh_settings()
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
  if problem=='refresh-only':self.refresh_settings();return
  if problem=='got':self.payload_status=(f'{name} is on your shelf. Send it when you are ready.','news');self.refresh_settings();return
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
 def do_perf_overlay(self,on):
  self.perf_overlay=bool(on);self.core.save_config(perf_overlay=self.perf_overlay);self.refresh_settings()
  if on and not self.direct:self.app.notify('The performance overlay needs the GPU video output.')
 def do_smooth(self,on):
  if self.direct:self.smooth.turn(self.presenter,bool(on));self.core.save_config(smooth_motion=bool(on));self.refresh_settings()
 def smooth_note(self):
  """What smooth motion is doing now, under its switch."""
  if not self.direct:return ''
  state=self.smooth.state(self.presenter)
  if state=='on':return f'On now: {1/self.refresh.period:.0f} Hz screen.'
  if state.startswith('stopped'):return 'Stopped for this session: this PC could not make the pictures in time. Turn it off and on to try again.'
  return ''
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
 def do_save_backup(self,on):self.app.link.saves.auto=bool(on);self.core.save_config(save_backup=bool(on));self.refresh_settings()
 def do_saves_now(self,_):self.app.link.saves.ask(None);self.refresh_settings()
 def do_saves_folder(self,_):
  try:folder=self.app.link.saves.root();folder.mkdir(parents=True,exist_ok=True);os.startfile(str(folder))
  except OSError:self.app.notify('Unable to open the folder of saves.')
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
   if key or (kind in live_broadcast.WITH_SERVER and len(server)>=10):live_broadcast.destination(kind,key or 'k',server)
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
 # Stats.
 def show_stats(self):
  """The Stats page, put again when a session or trophy was added, a minute went by, or another year was chosen."""
  log=self.play_log;now=time.time();key=(len(log.sessions),len(log.trophies),log.open[0] if log.open else '',int(now//60),self.stats_year)
  if key!=self.stats_seen:self.stats_seen=key;self.put('stats',game_stats.page(log,self.app.link.games,self.stats_year,now))
 def do_stats_year(self,year):
  try:self.stats_year=int(year)
  except (TypeError,ValueError):return
  self.sounds.play('move');self.show_stats()
 # The clip editor.
 def clip_kinds(self):return [dict(key=key,label=clip_editor.KIND_NAMES[key]) for key in clip_editor.KINDS]
 def do_clip_edit(self,path):
  """Opens a recording in the editor: its length and a strip of stills come from a thread."""
  path=str(path or '')
  if not path.lower().endswith(('.mp4','.mov','.mkv')) or not os.path.isfile(path):return
  self.clip_job+=1;job=self.clip_job;folder=self.core.STATE/'clip-editor'/str(job)
  self.put('clip',dict(path=path,name=Path(path).name,loading=True,seconds=0,start=0,end=0,strip=[],kind='small',kinds=self.clip_kinds(),stills=['',''],status='',tone='plain',busy=False,share=0,made=''))
  def load():
   described=clip_editor.info(path)
   if described is None:self.clip_results.put((job,'failed','This recording cannot be read.'));return
   self.clip_results.put((job,'info',described));self.clip_results.put((job,'strip',clip_editor.strip(path,described['seconds'],folder)))
  threading.Thread(target=load,name='PlayBridge clip strip',daemon=True).start()
 def clip_stills(self,start,end):
  """The pictures where the stretch starts and ends, made on a thread."""
  job=self.clip_job;path=self.values['clip'].get('path');folder=self.core.STATE/'clip-editor'/str(job)
  def make():
   made=[]
   for name,moment in (('start',start),('end',max(0,end-.05))):
    image=clip_editor.still(path,moment,360);target=folder/f'{name}-{moment:.2f}.jpg'
    if image is None:made.append('');continue
    folder.mkdir(parents=True,exist_ok=True);image.convert('RGB').save(target,quality=85);made.append(str(target))
   self.clip_results.put((job,'stills',made))
  threading.Thread(target=make,name='PlayBridge clip stills',daemon=True).start()
 def finish_clip(self,job,kind,value):
  if job!=self.clip_job or not self.values['clip']:return
  clip=dict(self.values['clip'])
  if kind=='failed':clip.update(loading=False,status=value,tone='error')
  elif kind=='info':
   seconds=value['seconds'];clip.update(loading=False,seconds=round(seconds,2),start=0,end=round(min(seconds,30.0),2),width=value['width'],height=value['height'])
   self.put('clip',clip);self.clip_stills(0,clip['end']);return
  elif kind=='strip':clip.update(strip=[file_url(path) if path else '' for path in value])
  elif kind=='stills':clip.update(stills=[file_url(path) if path else '' for path in value])
  elif kind=='done':
   problem,target=value;self.clip_share=None
   if problem:clip.update(busy=False,status=problem,tone='error')
   else:
    clip.update(busy=False,share=1.0,made=str(target),status=f'Saved as {Path(target).name}, beside the recording.',tone='news');self.app.notify(f'Clip saved: {Path(target).name}')
    if self.values['page']=='media':self.open_media()
  self.put('clip',clip)
 def do_clip_range(self,value):
  clip=self.values['clip']
  try:start,end=(round(float(part),2) for part in value)
  except (TypeError,ValueError):return
  if not clip or clip.get('busy'):return
  start=max(0.0,min(start,clip['seconds']));end=max(start,min(end,clip['seconds']))
  if (start,end)!=(clip['start'],clip['end']):self.put('clip',dict(clip,start=start,end=end,status='',made=''));self.clip_stills(start,end)
 def do_clip_kind(self,kind):
  clip=self.values['clip']
  if clip and kind in clip_editor.KINDS and not clip.get('busy'):self.put('clip',dict(clip,kind=kind,status='',made=''));self.sounds.play('move')
 def do_clip_export(self,_):
  clip=self.values['clip']
  if not clip or clip.get('busy') or clip.get('loading'):return
  wrong=clip_editor.problem(clip['kind'],clip['start'],clip['end'],clip['seconds'])
  if wrong:self.put('clip',dict(clip,status=wrong,tone='error'));return
  job=self.clip_job;source=clip['path'];target=clip_editor.target_for(source,clip['kind']);self.clip_share=0.0
  self.put('clip',dict(clip,busy=True,share=0,status='Making the clip…',tone='plain',made=''));self.sounds.play('accept')
  def share(value):self.clip_share=value
  app=self.app
  def make():
   problem=clip_editor.export(source,target,clip['kind'],clip['start'],clip['end'],self.core.share_encoders(),share,busy=lambda:app.connection_state=='Connected',stopping=self.clip_stopping.is_set)
   self.clip_results.put((job,'done',(problem,target)))
  threading.Thread(target=make,name='PlayBridge clip export',daemon=True).start()
 def do_clip_show(self,_):
  made=self.values['clip'].get('made')
  if made and os.path.isfile(made):
   subprocess.Popen(['explorer','/select,'+os.path.normpath(made)])
 def do_clip_close(self,_):
  if self.values['clip'].get('busy'):return
  self.clip_job+=1;self.put('clip',{})
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
 ClassicFrame.view=ClassicArt.view=shell.classic_page;qmlRegisterType(ClassicFrame,'PlayBridge.Classic',1,0,'ClassicFrame');qmlRegisterType(ClassicArt,'PlayBridge.Classic',1,0,'ClassicArt')
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
