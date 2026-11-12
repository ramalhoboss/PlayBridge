"""PlayBridge desktop shell: one window of pages under the library's top bar, built from the library's cards."""
import sys,time,socket,threading,ipaddress,queue
import tkinter as tk
from pathlib import Path
import customtkinter as ctk
from luxury_theme import AmbientScene, Bezel, LuxButton, apply_theme, dark_title_bar, heading, local_image, rim_field, rim_menu, thin_scrollbar, tint, BG, CARD, GOLD_SOFT, INK, MUTED, RAISED, STAGE, TEXT
from gaming_hub import PerformanceDock, CaptureLibrary
from game_mode import ConfirmDialog, GameShelf, PopMenu, TopStrip, power_items, status_text
from sound_board import SoundBoard
from console_control import CLOSE, GameFlow, POWER_OFF, REBOOT, REST, console_line, menu_in_front, running_title
from pad_input import CONSOLE_PAD_READY, PadBridge
from settings_look import GlassPage
from focus_ring import FocusWalker
import graphics_card,payload_sender,live_broadcast,mic_mix,video_encoders
from hang_watch import HangWatch
from keep_awake import BatteryHint,KeepAwake,on_battery
from screen_rate import ScreenRate
from desktop_features import CursorHider, saved_consoles, remember_console
from PIL import Image,ImageTk
import sounddevice as sd

TABS=('games','live','media')
ALERT='#FF9C9C'

class Tooltip:
 def __init__(self,widget,text):
  self.widget=widget;self.text=text;self.timer=None;self.popup=None
  widget.bind('<Enter>',self.schedule,add='+');widget.bind('<Leave>',self.hide,add='+');widget.bind('<ButtonPress>',self.hide,add='+');widget.bind('<Destroy>',self.hide,add='+')
 def schedule(self,_=None):self.timer=self.widget.after(500,self.show)
 def show(self):
  self.timer=None
  if not self.widget.winfo_exists():return
  self.popup=ctk.CTkToplevel(self.widget);self.popup.overrideredirect(True);self.popup.attributes('-topmost',True)
  self.popup.geometry(f'+{self.widget.winfo_rootx()}+{self.widget.winfo_rooty()+self.widget.winfo_height()+8}')
  box=Bezel(self.popup,fill=RAISED,outer=BG,radius=6);box.pack()
  ctk.CTkLabel(box.body,text=self.text,text_color=TEXT,font=('Segoe UI',11),padx=10,pady=2).pack()
 def hide(self,_=None):
  if self.timer is not None:self.widget.after_cancel(self.timer);self.timer=None
  if self.popup is not None:self.popup.destroy();self.popup=None

def run_ui(app):
 core=sys.modules[app.__class__.__module__]
 def icon(name,colour=TEXT):return tint(Image.open(core.HERE/'assets'/(name+'.png')),colour)
 icons={name:icon(name) for name in ('speaker','muted','connect','disconnect','camera','folder','replay','mini','live')}
 icons['on_air']=icon('live','#FF5A64')
 icons['record']=Image.open(core.HERE/'assets/record.png').convert('RGBA')
 on_white={name:icon(name,INK) for name in ('connect','disconnect')}
 apply_theme()
 win=ctk.CTk();win.title('PlayBridge');win.configure(fg_color=BG);dark_title_bar(win)
 animations=ctk.BooleanVar(master=win,value=core.config().get('animations',True))
 sw,sh=win.winfo_screenwidth(),win.winfo_screenheight();w=min(1540,sw-80);h=min(920,sh-110)
 win.geometry(f'{w}x{h}+{(sw-w)//2}+{max(20,(sh-h)//2)}');win.minsize(900,620)
 try:win.iconbitmap(str(core.HERE/'assets/playbridge.ico'))
 except tk.TclError:pass
 win.grid_columnconfigure(0,weight=1);win.grid_rowconfigure(1,weight=1)
 workspace=tk.Frame(win,bg=BG);workspace.grid(row=1,column=0,sticky='nsew');workspace.grid_columnconfigure(0,weight=1);workspace.grid_rowconfigure(0,weight=1)
 stage=tk.Frame(workspace,bg=STAGE);stage.grid(row=0,column=0,sticky='nsew');stage.grid_columnconfigure(0,weight=1);stage.grid_rowconfigure(0,weight=1)
 canvas=tk.Canvas(stage,bg=STAGE,borderwidth=0,highlightthickness=0);canvas.grid(row=0,column=0,sticky='nsew')
 # The video is drawn straight on the window, so a smaller frame leaves the last one showing around it until the canvas paints itself black.
 canvas.bind('<Configure>',lambda _:canvas.configure(bg=STAGE),add='+')
 item_id=canvas.create_image(0,0,anchor='center');placeholder=canvas.create_text(0,0,text='',state='hidden')
 ambient=AmbientScene(canvas,animations.get())
 has_video=False
 footer=tk.Frame(win,bg=BG);footer.grid(row=2,column=0,sticky='ew',padx=16,pady=(8,2));footer.grid_columnconfigure(1,weight=1)
 audio_zone=tk.Frame(footer,bg=BG);audio_zone.grid(row=0,column=0,sticky='w')
 tools=tk.Frame(footer,bg=BG);tools.grid(row=0,column=1)
 link_zone=tk.Frame(footer,bg=BG);link_zone.grid(row=0,column=2,sticky='e')
 def device_label(name):
  return name.replace('Altifalantes','Speakers').replace('Auscultadores','Headphones').replace('Saída digital','Digital output')
 apis=sd.query_hostapis();devs=sd.query_devices();outputs=[(i,device_label(d['name'])) for i,d in enumerate(devs) if d['max_output_channels']>=2 and apis[d['hostapi']]['name']=='Windows WASAPI']
 choice=ctk.StringVar(value=device_label(app.output_name) or 'No sound output')
 def change_audio(value):
  try:
   # An output that will not open is not saved, so the next start does not try it first.
   index=next(i for i,n in outputs if n==value)
   if app.open_audio(index):core.save_config(output=devs[index]['name']+' ['+apis[devs[index]['hostapi']]['name']+']')
   choice.set(device_label(app.output_name) or 'No sound output');sounds.reopen()
  except Exception as e:app.error='Audio output: '+str(e)
 def mute_audio():
  app.muted=not app.muted;mute_button.restyle(icon=icons['speaker'] if not app.muted else icons['muted'])
 def round_tool(parent,image,command):
  return LuxButton(parent,command=command,icon=image,width=40,height=40,radius=20,icon_size=19,behind=BG)
 mute_button=round_tool(audio_zone,icons['speaker'],mute_audio);mute_button.grid(row=0,column=0,padx=(0,8),pady=2)
 volume=ctk.CTkSlider(audio_zone,from_=0,to=1,command=lambda v:setattr(app,'volume',v),width=90,height=16);volume.set(app.volume);volume.grid(row=0,column=1,padx=(0,14))
 output_rim,output=rim_menu(audio_zone,behind=BG,variable=choice,values=[n for _,n in outputs] or ['No audio device'],command=change_audio,text_color=MUTED,height=30,width=180,font=('Segoe UI',11));output_rim.grid(row=0,column=2,padx=(0,12))
 screenshot_button=round_tool(tools,icons['camera'],app.take_screenshot);screenshot_button.grid(row=0,column=0,padx=4)
 record_button=round_tool(tools,icons['record'],app.toggle_recording);record_button.grid(row=0,column=1,padx=4)
 replay_button=round_tool(tools,icons['replay'],app.save_replay);replay_button.grid(row=0,column=2,padx=4)
 captures_button=round_tool(tools,icons['folder'],lambda:show_page('media'));captures_button.grid(row=0,column=3,padx=4)
 mini_button=round_tool(tools,icons['mini'],lambda:small_window());mini_button.grid(row=0,column=4,padx=4)
 live_button=round_tool(tools,icons['live'],lambda:toggle_live());live_button.grid(row=0,column=5,padx=4)
 session_button=LuxButton(tools,'Session',lambda:toggle_session(),width=92,height=40,radius=20,text_size=13,behind=BG);session_button.grid(row=0,column=6,padx=(12,0))
 host_label=ctk.CTkLabel(link_zone,text=app.args.host,text_color=MUTED,font=('Segoe UI',11));host_label.grid(row=0,column=0,sticky='e',padx=14)
 def disconnect():
  app.intentional_disconnect=True
  if app.sock:
   try:app.sock.shutdown(socket.SHUT_RDWR)
   except OSError:pass
 def connect_toggle():
  if app.worker.is_alive():disconnect()
  else:app.restart()
 connect_button=LuxButton(link_zone,'Connect',connect_toggle,icon=on_white['connect'],width=130,height=40,radius=20,icon_size=16,text_size=13,tone='main',behind=BG);connect_button.grid(row=0,column=1)
 settings_page=None
 def build_settings():
  nonlocal settings_page
  page=GlassPage(workspace);settings_page=page
  sections={}
  for key,label,icon_name,subtitle in (('console','Console','controller','Address, favourites, connection and power'),('picture','Picture','fullscreen','Quality, graphics card, video output and upscaling'),('captures','Captures','camera','Instant replay, files and diagnostics'),('sound','Sound','speaker','Music and sounds on the Games page'),('live','Streaming','live','Twitch, YouTube, any RTMP server, or OBS on this PC'),('look','Appearance','games','Gaming Mode, motion and the look of PlayBridge'),('updates','Updates','replay','New versions of PlayBridge from GitHub')):
   sections[key]=page.section(key,label,Image.open(core.HERE/'assets'/(icon_name+'.png')).convert('RGBA'),subtitle)
  foot=page.footer
  def open_section(key):
   page.open(key)
   # Every setting applies the moment it changes. The line under these two says what that did, or what is wrong with the address.
   page.show_footer(key in ('console','picture'))
  page.choose_hook=open_section;page.open_section=open_section
  def card(section,title=None):return page.card(section,title)
  # Settings reads from further away than the rest of the app, so its words and controls are a size up.
  BODY=('Segoe UI',16);SMALL=('Segoe UI',15);FIELD_HEIGHT=44
  def note(parent,text):
   label=ctk.CTkLabel(parent,text=text,font=SMALL,text_color=MUTED,wraplength=590,justify='left');label.pack(anchor='w',pady=(2,10));return page.wrap(label)
  def caption(parent,text):
   return ctk.CTkLabel(parent,text=text,font=BODY,text_color=MUTED)
  def switch(parent,text,variable,command=None):
   ctk.CTkSwitch(parent,text=text,variable=variable,command=command,font=BODY,switch_width=50,switch_height=26).pack(anchor='w',pady=(4,8))
  def wide_button(parent,text,command,**look):
   button=LuxButton(parent,text,command,height=48,radius=24,text_size=16,behind=CARD,**look);button.pack(fill='x',pady=(4,10));return button
  def drop(parent,**options):
   return rim_menu(parent,height=FIELD_HEIGHT,font=BODY,dropdown_font=BODY,**options)
  def entry(parent,**options):
   return rim_field(parent,height=FIELD_HEIGHT,font=BODY,**options)
  def menu(parent,**options):
   drop(parent,**options)[0].pack(fill='x',pady=(0,8))
  # Console.
  favourites=saved_consoles(core.config(),core.PROFILES)
  favourite_map={item['name']+' · '+item['host']:item for item in favourites}
  def choose_favourite(label):
   if label not in favourite_map:return
   item=favourite_map[label];host.delete(0,'end');host.insert(0,item['host']);console_name.delete(0,'end');console_name.insert(0,item['name']);profile.set(core.PROFILES[item['profile']]['name'])
   # Its profile applies at once, as the profile menu does; a different address waits for Save, and Save then uses both.
   if item['host']==app.args.host:save()
   else:waiting()
  place=card(sections['console'],'Your console')
  if favourite_map:menu(place,values=list(favourite_map),command=choose_favourite,variable=ctk.StringVar(value='Choose a saved console'))
  caption(place,'IP address').pack(anchor='w')
  # The address is the one setting that waits for Save (or Enter): a new one drops the stream and sends the ELF again, so it is
  # never used half typed. Everything else on this page applies the moment it changes.
  host_row=tk.Frame(place,bg=CARD);host_row.pack(fill='x',pady=(4,10))
  host_rim,host=entry(host_row);host.insert(0,app.args.host);host_rim.pack(side='left',fill='x',expand=True)
  LuxButton(host_row,'Save',lambda:save(True),width=110,height=FIELD_HEIGHT,radius=FIELD_HEIGHT//2,text_size=15,behind=CARD,tone='main').pack(side='left',padx=(8,0))
  def waiting():
   """Says that the address in the field is not the one in use yet."""
   typed=host.get().strip()
   if typed!=app.args.host:say(f'Press Save to connect to {typed}.',GOLD_SOFT,keep=True)
  def left_host(_):
   if not host.winfo_exists():return
   # Back to the address in use: nothing waits, and a complaint about what was typed before no longer applies.
   if host.get().strip()==app.args.host:say('')
   else:
    try:ipaddress.IPv4Address(host.get().strip());waiting()
    except ValueError:say('Enter a valid IPv4 address, such as 192.168.1.20.',ALERT)
  host.bind('<Return>',lambda _:save(True),add='+');host.bind('<FocusOut>',left_host,add='+')
  scan_results=queue.Queue();discovered={}
  scan_choice=ctk.StringVar(value='Select a console')
  def select_console(label):
   if label in discovered:host.delete(0,'end');host.insert(0,discovered[label]);waiting()
  found_rim,found_menu=drop(place,variable=scan_choice,values=['Select a console'],command=select_console);found_rim.pack(fill='x',pady=(0,6))
  scan_status=note(place,'Find your PS5 or enter its IP address above.')
  def finish_scan():
   try:items,problem=scan_results.get_nowait()
   except queue.Empty:win.after(100,finish_scan);return
   scan_button.restyle(enabled=True,text='Find console')
   discovered.clear();discovered.update({item['name']+' · '+item['ip']:item['ip'] for item in items})
   found_menu.configure(values=list(discovered) or ['No console found'])
   if discovered:
    label=next(iter(discovered));scan_choice.set(label);select_console(label);scan_status.configure(text='Choose your console above, then press Save to connect.' if len(discovered)>1 else 'Found it. Press Save to connect.')
   else:scan_choice.set('No console found');scan_status.configure(text=problem or 'No console found. Enter the IP manually; check Payload Manager.')
  def scan():
   scan_button.restyle(enabled=False,text='Scanning…');scan_status.configure(text='Searching the local network…');preferred=host.get().strip()
   def work():
    from console_discovery import discover
    try:scan_results.put((discover(preferred),None))
    except Exception:scan_results.put(([],'Network scan failed. You can still enter the IP manually.'))
   threading.Thread(target=work,name='Console discovery',daemon=True).start();win.after(100,finish_scan)
  scan_button=wide_button(place,'Find console',scan)
  place=card(sections['console'],'Favourite')
  name_rim,console_name=entry(place,placeholder_text='My PS5');name_rim.pack(fill='x',pady=(0,6))
  match=next((c for c in favourites if c['host']==app.args.host),None)
  if match:console_name.insert(0,match['name'])
  favourite_status=note(place,'Save this IP and quality profile for next time.')
  def save_favourite():
   try:items=remember_console(core.config(),console_name.get(),host.get(),profiles[profile.get()],core.PROFILES)
   except ValueError:favourite_status.configure(text='Enter a valid console IP address.',text_color=ALERT);return
   core.save_config(consoles=items);favourite_status.configure(text='Favourite saved with this quality profile.',text_color=GOLD_SOFT)
  heart=local_image('heart.png');heart_icon=tint(heart,TEXT) if heart is not None else None
  wide_button(place,'Save to favourites',save_favourite,icon=heart_icon,icon_size=20)
  place=card(sections['console'],'Connection')
  reconnect=ctk.BooleanVar(value=app.args.auto_reconnect);switch(place,'Reconnect automatically',reconnect,lambda:save())
  manual=ctk.BooleanVar(value=app.args.connect_only);switch(place,'ELF already loaded in Payload Manager',manual,lambda:save())
  note(place,'Off: PlayBridge uploads the ELF automatically.\nOn: load PlayBridge.elf, then connect within 60 seconds.')
  notices=ctk.BooleanVar(value=core.config().get('ps5_notices',False))
  def change_notices():
   core.save_config(ps5_notices=notices.get());say('Saved. Used the next time PlayBridge connects.')
  switch(place,'Notices on the PS5',notices,change_notices)
  note(place,'The PS5 shows a notice when PlayBridge starts streaming to this PC and when it stops. A PlayBridge.elf you load yourself has to be from this version, or it refuses the connection while this is on.')
  place=card(sections['console'],'Send a payload')
  recent_payloads=[item for item in core.config().get('recent_payloads',[]) if isinstance(item,str)]
  def payload_label(path):return Path(path).name+'  ·  '+(Path(path).parent.name or str(Path(path).parent))
  recent_choice=ctk.StringVar(value='Send a recent payload')
  def send_recent(label):
   path=next((item for item in recent_payloads if payload_label(item)==label),None);recent_choice.set('Send a recent payload')
   if path:send_file(path)
  recent_rim,recent_menu=drop(place,variable=recent_choice,values=[payload_label(item) for item in recent_payloads] or ['No payload sent yet'],command=send_recent);recent_rim.pack(fill='x',pady=(0,8))
  def choose_payload():
   from tkinter import filedialog
   path=filedialog.askopenfilename(parent=win,title='Choose a payload',filetypes=[('ELF payload','*.elf'),('All files','*.*')])
   if path:send_file(path)
  wide_button(place,'Choose ELF and send',choose_payload)
  payload_status=note(place,'Sends any ELF to the loader your exploit opened on port 9021. A payload runs with full access to the PS5, so send only files you trust.')
  def send_file(path):
   typed=host.get().strip()
   try:ipaddress.IPv4Address(typed)
   except ValueError:payload_status.configure(text='Enter a valid console IP address above first.',text_color=ALERT);return
   try:data=payload_sender.read_payload(path)
   except payload_sender.PayloadError as problem:payload_status.configure(text=str(problem),text_color=ALERT);return
   name=Path(path).name
   def send():
    recent_payloads[:]=payload_sender.remember(recent_payloads,path);core.save_config(recent_payloads=recent_payloads);recent_menu.configure(values=[payload_label(item) for item in recent_payloads])
    payload_status.configure(text=f'Sending {name}…',text_color=MUTED);results=queue.Queue()
    def work():
     try:payload_sender.send_payload(typed,data);results.put(None)
     except payload_sender.PayloadError as problem:results.put(str(problem))
    threading.Thread(target=work,name='PlayBridge payload',daemon=True).start()
    def finish():
     try:problem=results.get_nowait()
     except queue.Empty:win.after(100,finish);return
     if problem:payload_status.configure(text=problem,text_color=ALERT)
     else:payload_status.configure(text=f'{name} reached the loader on {typed}.',text_color=GOLD_SOFT);app.notify(f'{name} sent to the PS5.')
    win.after(100,finish)
   ask_first('Send this payload?',f'{name}  ·  {payload_sender.size_label(len(data))}\nto the PS5 at {typed}.\n\nIt runs with full access to the console. Send only files you trust.','Send',send,height=250)
  place=card(sections['console'],'Power')
  actions=tk.Frame(place,bg=CARD);actions.pack(fill='x',pady=(0,4));actions.grid_columnconfigure((0,1),weight=1,uniform='power')
  for index,(label,command) in enumerate(power_actions):
   LuxButton(actions,label,command,height=48,radius=24,text_size=16,behind=CARD).grid(row=index//2,column=index%2,sticky='ew',padx=4,pady=4)
  note(place,'These need the PS5 connected. After a reboot or a power off, load your exploit again.')
  # Picture.
  place=card(sections['picture'],'Quality profile')
  profiles={v['name']:k for k,v in core.PROFILES.items()};profile=ctk.StringVar(value=core.PROFILES[app.args.profile]['name'])
  menu(place,variable=profile,values=list(profiles),command=lambda _:save())
  note(place,'Choosing a profile reconnects to the PS5 with it at once. 30 fps limits PC playback only.\n1440p and 4K need the PS5 video output set to that resolution.')
  note(place,graphics_card.summary(app.graphics()))
  # Only where there is a choice, as on a laptop with the processor's graphics and an NVIDIA or AMD card.
  found=graphics_card.cards()
  if len(found)>1:
   place=card(sections['picture'],'Graphics card')
   automatic='Automatic: '+graphics_card.label(graphics_card.automatic(found),found)
   kept=core.config().get('graphics_card',graphics_card.AUTOMATIC);names=[item['name'] for item in found]
   gpu_card=ctk.StringVar(value=kept if kept in names else automatic)
   menu(place,variable=gpu_card,values=[automatic]+names,command=lambda value:(core.save_config(graphics_card=graphics_card.AUTOMATIC if value==automatic else value),reopen()))
   note(place,'The card that decodes and draws the video. Automatic takes the one with the most memory of its own, such as the NVIDIA or AMD card in a gaming laptop. Applies the next time PlayBridge opens.')
  place=card(sections['picture'],'On screen')
  switch(place,'Show performance stats',diagnostic,lambda:core.save_config(diagnostic=diagnostic.get()))
  place=card(sections['picture'],'Video output')
  gpu_on=ctk.BooleanVar(value=core.config().get('direct_video',True))
  switch(place,'GPU video output',gpu_on,lambda:(core.save_config(direct_video=gpu_on.get()),reopen()))
  note(place,'The graphics card decodes and draws the video, which uses far less of the processor and keeps playing while the window is busy. Applies the next time PlayBridge opens.')
  switch(place,'Match the screen to the stream',match_on,lambda:core.save_config(match_refresh=match_on.get()))
  note(place,'60 fps judders on a 144 or 165 Hz screen, because some frames stay up longer than others. While a game streams, PlayBridge switches the screen to 120 or 60 Hz, and back when the stream ends.')
  if direct:
   sharpen_on=ctk.BooleanVar(value=presenter.sharpen)
   def change_sharpen():
    presenter.sharpen=sharpen_on.get();core.save_config(sharpen=sharpen_on.get())
   switch(place,'Sharpen picture',sharpen_on,change_sharpen)
   fsr_on=ctk.BooleanVar(value=presenter.fsr)
   def change_fsr():
    presenter.fsr=fsr_on.get();core.save_config(fsr=fsr_on.get())
   switch(place,'FSR 1 upscaling',fsr_on,change_fsr)
   note(place,'When the screen is larger than the picture, such as 1080p on a 1440p or 4K monitor, AMD FidelityFX Super Resolution 1 enlarges it, and Sharpen picture uses its sharpening. Works on any graphics card.')
   from d3d11_presenter import screen_varies,tearing_supported
   # Only where the screen can follow it: a screen with a fixed rate would tear, so the switch would do nothing there.
   if tearing_supported() and screen_varies(presenter.hwnd) is not False:
    vrr_wanted=ctk.BooleanVar(value=core.config().get('vrr',False))
    switch(place,'Variable refresh rate',vrr_wanted,lambda:(core.save_config(vrr=vrr_wanted.get()),reopen()))
    note(place,'For screens with G-Sync, FreeSync or Adaptive-Sync: each frame shows the moment it is due, so 60 fps plays evenly on a 144 Hz screen without switching it to 60 Hz. Works best in full screen (F11), and other screens may show tearing. While it is on, PlayBridge leaves the screen rate alone. Applies the next time PlayBridge opens.')
  # Captures.
  place=card(sections['captures'],'Instant replay')
  replay_lengths={'Off':0,'Last 30 seconds':30,'Last 60 seconds':60,'Last 2 minutes':120}
  def change_replay(label):
   app.replay.resize(replay_lengths[label]);core.save_config(replay_seconds=replay_lengths[label])
  current=next((label for label,seconds in replay_lengths.items() if seconds==app.replay.seconds),'Last 60 seconds')
  menu(place,variable=ctk.StringVar(value=current),values=list(replay_lengths),command=change_replay)
  note(place,'F10 saves it to your recordings. It stays in this PC\'s memory, up to 1 GB, and nothing changes on the PS5.')
  place=card(sections['captures'],'Microphone')
  switch(place,'Add my voice',mic_on,lambda:set_microphone(mic_on.get()))
  mics=mic_mix.inputs(sd);default_mic='Windows default microphone'
  kept_mic=core.config().get('mic_device','')
  def change_mic(label):
   core.save_config(mic_device='' if label==default_mic else label)
   if mic_on.get():set_microphone(True)
  menu(place,variable=ctk.StringVar(value=kept_mic if kept_mic in [name for _,name in mics] else default_mic),values=[default_mic]+[name for _,name in mics],command=change_mic)
  caption(place,'Microphone volume').pack(anchor='w',pady=(6,0))
  def change_mic_level(value):app.mic_mix.level=float(value)
  mic_level=ctk.CTkSlider(place,from_=0,to=mic_mix.LEVEL_MAX,command=change_mic_level,height=20);mic_level.set(app.mic_mix.level);mic_level.pack(fill='x',pady=(6,8))
  mic_level.bind('<ButtonRelease-1>',lambda _:core.save_config(mic_level=round(app.mic_mix.level,2)),add='+')
  note(place,'Your voice goes into recordings, instant replays and Go live, mixed with the game\'s sound. You do not hear it in PlayBridge. F7 turns it on and off. The middle of the slider is your microphone as Windows gives it.')
  place=card(sections['captures'],'Files')
  def choose_capture_folder():
   from tkinter import filedialog
   folder=filedialog.askdirectory(parent=win,title='Choose capture folder',initialdir=str(app.capture_folder()))
   if folder:core.save_config(capture_folder=folder);app.notify('Capture folder updated.')
  wide_button(place,'Choose capture folder',choose_capture_folder)
  wide_button(place,'Export diagnostics',export_session)
  place=card(sections['captures'],'Smaller recordings')
  compact_on=ctk.BooleanVar(value=core.config().get('compact_recordings',False))
  def change_compact():
   core.save_config(compact_recordings=compact_on.get())
   if compact_on.get():app.compactor.resume(core.config().get('compact_waiting',[]))
  switch(place,'Make recordings smaller',compact_on,change_compact)
  compact_note=note(place,'Looking for this PC\'s video encoders…')
  compact_progress=note(place,'')
  def show_compact(encoder):
   if encoder is None:compact_note.configure(text='This PC has no encoder for this, so recordings stay as the PS5 made them.');return
   compact_note.configure(text=f'After each recording or replay is saved, PlayBridge makes its video again with {video_encoders.NAMES.get(encoder,encoder)}, at about a third of the size, and keeps the sound as it is. It works only while no stream plays, and the original goes to the Recycle Bin once the new file has been checked.')
  def follow_compact():
   if not compact_progress.winfo_exists():return
   compact_progress.configure(text=app.compactor.status());win.after(1000,follow_compact)
  follow_compact()
  # Finding the encoders tries each one, so it runs away from the window and fills in both notes when it is done.
  encoder_results=queue.Queue()
  threading.Thread(target=lambda:encoder_results.put((video_encoders.for_files(),video_encoders.for_live())),name='PlayBridge encoders',daemon=True).start()
  def encoders_found():
   try:files,live=encoder_results.get_nowait()
   except queue.Empty:win.after(200,encoders_found);return
   show_compact(files);show_live_encoder(live)
  win.after(200,encoders_found)
  # Streaming.
  place=card(sections['live'],'Go live')
  services={name:key for key,name in live_broadcast.SERVICES.items()}
  saved=core.config();service=ctk.StringVar(value=live_broadcast.SERVICES.get(saved.get('live_service'),'Twitch'))
  server_label=caption(place,'Server address')
  server_rim,server_field=entry(place,placeholder_text='rtmp://')
  if isinstance(saved.get('live_server'),str):server_field.insert(0,saved['live_server'])
  key_label=caption(place,'Stream key')
  key_row=tk.Frame(place,bg=CARD)
  key_rim,key_field=entry(key_row,show='•');key_rim.pack(side='left',fill='x',expand=True)
  key_field.insert(0,live_broadcast.unseal(saved.get('live_key','')))
  def show_key():
   hidden=key_field.cget('show')!='';key_field.configure(show='' if hidden else '•');key_shown.restyle(text='Hide' if hidden else 'Show')
  key_shown=LuxButton(key_row,'Show',show_key,width=96,height=FIELD_HEIGHT,radius=FIELD_HEIGHT//2,text_size=15,behind=CARD);key_shown.pack(side='left',padx=(8,0))
  def check_live(*_):
   """Says what is wrong with the key or the address while it is typed, before Go live is pressed. An empty field waits."""
   if app.broadcast.active:return
   kind=services.get(service.get(),'twitch');key=key_field.get().strip();server=server_field.get().strip()
   try:
    if key or (kind=='custom' and len(server)>=10):live_broadcast.destination(kind,key or 'k',server)
   except ValueError as problem:live_status.configure(text=str(problem),text_color=ALERT);return
   live_status.configure(text=hints[kind],text_color=MUTED)
  key_field.bind('<KeyRelease>',check_live,add='+');server_field.bind('<KeyRelease>',check_live,add='+')
  live_go=LuxButton(place,'Go live',lambda:start_live(),height=48,radius=24,text_size=16,behind=CARD,tone='main')
  live_status=note(place,'')
  smaller=tk.Frame(place,bg=CARD)
  compress_on=ctk.BooleanVar(value=core.config().get('live_compress',False))
  switch(smaller,'Smaller stream (HEVC or AV1)',compress_on,lambda:core.save_config(live_compress=compress_on.get()))
  compress_note=note(smaller,'Looking for this PC\'s video encoders…')
  def show_live_encoder(encoder):
   if encoder is None:compress_note.configure(text='This PC\'s graphics card makes neither HEVC nor AV1, so the stream always goes as the PS5 sent it.');return
   compress_note.configure(text=f'{video_encoders.NAMES.get(encoder,encoder)} makes the video again at about a quarter of the PS5\'s bitrate (4K at about {video_encoders.bitrate(encoder,2160,live=True)//1_000_000} Mbps), for a slower upload. It uses the graphics card\'s encoder, not the processor.')
  hints={'twitch':'Twitch recommends at most 6 Mbps, so the Data saver profile suits it best. Higher profiles work on many channels.','youtube':'YouTube takes every 1080p profile. The key travels over an encrypted connection.','custom':'Enter the server address and, if your service gives it separately, the stream key.','obs':f'In OBS, add a Media Source, untick Local File, and enter udp://127.0.0.1:{live_broadcast.OBS_PORT} as the input, with mpegts as its format. Then go live here.'}
  def arrange(*_):
   kind=services.get(service.get(),'twitch')
   for widget in (server_label,server_rim,key_label,key_row,smaller,live_go,live_status):widget.pack_forget()
   if kind=='custom':server_label.pack(anchor='w');server_rim.pack(fill='x',pady=(4,10))
   if kind!='obs':key_label.pack(anchor='w');key_row.pack(fill='x',pady=(4,10))
   if kind in live_broadcast.COMPRESSIBLE:smaller.pack(fill='x')
   live_go.pack(fill='x',pady=(4,10));live_status.pack(anchor='w',pady=(2,10));live_status.configure(text=hints[kind],text_color=MUTED)
   if kind!='obs':check_live()
  menu(place,variable=service,values=list(services),command=arrange)
  arrange()
  def start_live():
   if app.broadcast.active:app.end_live();return
   kind=services[service.get()];key=key_field.get().strip();server=server_field.get().strip()
   # The key is kept encrypted for this Windows user.
   core.save_config(live_service=kind,live_server=server,live_key=live_broadcast.seal(key))
   problem=app.go_live(kind,key,server)
   if problem:live_status.configure(text=problem,text_color=ALERT)
   else:live_status.configure(text='Waiting for the next keyframe…',text_color=MUTED)
  page.live_controls=(live_go,live_status)
  place=card(sections['live'],'How it works')
  note(place,'PlayBridge sends on the video and sound the PS5 already made, without encoding them again, so it costs this PC almost nothing. The stream uses your quality profile, as H.264 and AAC, so check that its bitrate suits your channel.')
  note(place,'For YouTube and other RTMP servers, Smaller stream makes the video again as AV1 or HEVC on the graphics card, so 4K fits a slower upload. Twitch takes those only in its Enhanced Broadcasting beta, so it always gets H.264.')
  note(place,'Ctrl+B or the button beside the small window starts and ends it with these settings. Recording and instant replay keep working while you are live.')
  # Sound.
  place=card(sections['sound'],'In the library')
  music_on=ctk.BooleanVar(value=sounds.music_on);cues_on=ctk.BooleanVar(value=sounds.effects_on)
  def change_music():
   sounds.set_music(music_on.get());core.save_config(sound_music=music_on.get())
  def change_cues():
   sounds.effects_on=cues_on.get();core.save_config(sound_cues=cues_on.get());sounds.play('move')
  switch(place,'Background music',music_on,change_music);switch(place,'Navigation sounds',cues_on,change_cues)
  caption(place,'Library volume').pack(anchor='w',pady=(6,0))
  level=ctk.CTkSlider(place,from_=0,to=1,command=lambda value:setattr(sounds,'volume',value),height=20);level.set(sounds.volume);level.pack(fill='x',pady=(6,8));level.bind('<ButtonRelease-1>',lambda _:core.save_config(sound_level=sounds.volume),add='+')
  note(place,'These sound only while your games are on screen, never over a game. A game with music of its own plays it; the others share the app\'s.')
  # Appearance.
  place=card(sections['look'],'Gaming Mode')
  start_gaming=ctk.BooleanVar(value=core.config().get('gaming_mode',False))
  switch(place,'Open in Gaming Mode',start_gaming,lambda:core.save_config(gaming_mode=start_gaming.get()))
  note(place,'Your games, fullscreen on this PC, with no console menu. The TV still shows the PS5 as usual.')
  place=card(sections['look'],'Motion')
  def change_motion():
   ambient.animations=animations.get();core.save_config(animations=animations.get())
  switch(place,'Animations',animations,change_motion)
  note(place,'The library\'s moving tiles and the waiting screen. Motion pauses during video playback.')
  place=card(sections['look'],'Look')
  glass=ctk.BooleanVar(value=core.config().get('ui','qt')=='qt')
  switch(place,'Glass look',glass,lambda:(core.save_config(ui='qt' if glass.get() else 'tk'),reopen()))
  note(place,'Glass panels and motion, drawn on the graphics card. Off keeps this classic window. Applies the next time PlayBridge opens.')
  # Updates.
  place=card(sections['updates'],f'PlayBridge {app.updates.status()["current"]}')
  update_line=note(place,app.updates.text())
  def install_update():
   if app.updates.status()['installable']:app.restart_after_update=True;close()
  check_button=wide_button(place,'Check now',app.updates.check_now)
  install_button=wide_button(place,'Restart and update',install_update,tone='main');install_button.pack_forget()
  automatic=ctk.BooleanVar(value=app.updates.automatic)
  switch(place,'Update automatically',automatic,lambda:(app.updates.set_automatic(automatic.get()),core.save_config(update_auto=automatic.get())))
  note(place,'PlayBridge looks for a new version on GitHub when it opens and every six hours. It downloads it slowly in the background, so a stream keeps its speed, checks it against the release\'s checksums, and puts it in when you close PlayBridge.')
  seen=[-1]
  def follow_updates():
   # Redrawn only when the update state moves on, looked at twice a second.
   if not update_line.winfo_exists():return
   state=app.updates.status()
   if state['revision']!=seen[0]:
    seen[0]=state['revision'];update_line.configure(text=app.updates.text(),text_color=ALERT if state['state']=='failed' else MUTED)
    busy=state['state'] in ('checking','downloading','ready')
    check_button.restyle(enabled=not busy,text='Looking…' if state['state']=='checking' else 'Downloading…' if state['state']=='downloading' else 'Check now')
    if state['installable'] and not install_button.winfo_ismapped():install_button.pack(fill='x',pady=(4,10),after=check_button)
   win.after(500,follow_updates)
  follow_updates()
  error=ctk.CTkLabel(foot,text='',text_color=ALERT,font=BODY)
  def say(text,color=MUTED,keep=False):
   """The line under Console and Picture. A confirmation fades after a few seconds; a problem, or an address waiting for Save, stays
   until it is dealt with."""
   if not error.winfo_exists():return
   error.configure(text=text,text_color=color)
   if color!=ALERT and not keep:win.after(6000,lambda:error.winfo_exists() and error.cget('text')==text and error.configure(text=''))
  def reopen():say('Saved. It takes effect the next time PlayBridge opens.',GOLD_SOFT)
  def save(reach=False):
   """Keeps what Console and Picture say the moment it changes. reach: the user asked for this console (Enter in the address, or
   picking one), so PlayBridge connects to it when it is not connected yet."""
   typed=host.get().strip()
   try:ipaddress.IPv4Address(typed)
   except ValueError:say('Enter a valid IPv4 address, such as 192.168.1.20.' if typed else 'Enter your PS5\'s IP address.',ALERT);return
   chosen=(typed,manual.get(),profiles[profile.get()]);before=(app.args.host,app.args.connect_only,app.args.profile,app.args.auto_reconnect)
   running=app.worker.is_alive();new_host=typed!=app.args.host;new_profile=chosen[2]!=app.args.profile
   # A new connection sends the ELF again, so only a new address, a new profile while connected, or an asked-for console starts one.
   # The ELF switch and reconnecting apply to the next connection, so flipping them never drops a game that is playing.
   connect=new_host or (new_profile and running) or (reach and not running)
   # A new address from the user is kept from now on, even when another PS5 answers.
   if new_host:app.follow=False
   app.args.host,app.args.connect_only,app.args.profile=chosen;app.args.auto_reconnect=reconnect.get();core.save_config(host=app.args.host,host_auto=app.follow,connect_only=app.args.connect_only,profile=app.args.profile,auto_reconnect=app.args.auto_reconnect);host_label.configure(text=app.args.host)
   if connect:say(f'Reconnecting with {profile.get()}…' if new_profile and not new_host else f'Connecting to the PS5 at {typed}…',GOLD_SOFT)
   elif new_profile:say(f'Saved. {profile.get()} is used the next time you connect.')
   elif before!=(*chosen,reconnect.get()):say('Saved. Used the next time PlayBridge connects.' if chosen[1]!=before[1] else 'Saved.')
   elif reach:say(f'Saved. Already connected to the PS5 at {typed}.' if app.connection_state=='Connected' else f'Saved. Still connecting to the PS5 at {typed}…')
   if not connect:return
   disconnect()
   def connect_when_ready():
    if app.stop.is_set():return
    if app.worker.is_alive():win.after(100,connect_when_ready)
    else:app.restart()
   win.after(100,connect_when_ready)
  error.pack(side='left',padx=(0,14))
  open_section('console')
 library=CaptureLibrary(workspace,app)
 def export_session():
  from tkinter import filedialog
  path=filedialog.asksaveasfilename(parent=win,title='Export diagnostics',defaultextension='.zip',initialfile='PlayBridge-diagnostics.zip',filetypes=[('ZIP archive','*.zip')])
  if path:app.export_diagnostics(path)
 flow=GameFlow();page='live';back_page='games';games_shown=False;gaming_mode=False;menu_was_in_front=False;seen_status=None;revealed_at=0;opened_title='';opened_at=0;first_status=True;top_info={}
 def say(text):
  app.notify(text);sounds.play('error')
 def ask_first(title,text,action,command,height=230):ConfirmDialog(win,title,text,action,command,height)
 def close_game():
  title=running_title(app.link.status)
  if not title:app.notify('No game is open.');return
  def close():
   # The console's menu comes back as the game goes, and in Gaming Mode it never reaches the screen.
   if gaming_mode:show_games(True)
   app.link.send(CLOSE)
  ask_first('Close this game?',app.link.game_name(title)+' closes on your PS5. Anything not saved in the game is lost.','Close game',close)
 def soft_reset():
  title=running_title(app.link.status)
  if not title:app.notify('No game is open.');return
  def again():
   if gaming_mode:show_games(True)
   flow.replace(title,time.perf_counter());app.link.send(CLOSE)
  ask_first('Restart this game?',app.link.game_name(title)+' closes and starts again. Anything not saved in the game is lost.','Restart game',again)
 def rest_console():
  ask_first('Put your PS5 to rest?','The game stops and this session ends. You may need to load your exploit again when the PS5 comes back.','Rest',lambda:app.console_power(REST))
 def reboot_console():
  ask_first('Reboot your PS5?','The game stops and this session ends. You will need to load your exploit again when the PS5 comes back.','Reboot',lambda:app.console_power(REBOOT))
 def power_off_console():
  ask_first('Turn off your PS5?','The game stops and this session ends. You will need to load your exploit again next time.','Turn off',lambda:app.console_power(POWER_OFF))
 def recovery_console():
  # The flag that asks for Safe Mode shares its values with the ones that format the console, so PlayBridge never writes it.
  ask_first('Recovery (Safe Mode)','Safe Mode starts from the console itself. Turn the PS5 off here, hold its power button until the second beep, about 7 seconds, and connect the controller with a USB cable.\n\nTo leave, choose Restart PS5. Never choose Update System Software or any reset: PlayBridge needs firmware 13.60. Load your exploit again afterwards.','Turn off',lambda:app.console_power(POWER_OFF),300)
 power_actions=(('Soft reset',soft_reset),('Rest mode',rest_console),('Reboot',reboot_console),('Turn off',power_off_console),('Recovery',recovery_console))
 dock=PerformanceDock(workspace,export_session,(('Close game',close_game),)+power_actions)
 session_wanted=bool(core.config().get('session_panel',False));dock_visible=False
 def place_session():
  # The session panel belongs to the live view, and only if the window has room for it.
  nonlocal dock_visible
  visible=session_wanted and page=='live' and not fullscreen and mini is None and win.winfo_width()>=1180
  if visible!=dock_visible:
   dock_visible=visible
   if visible:dock.grid(row=0,column=1,sticky='nsew',padx=(10,0))
   else:dock.grid_remove()
 def toggle_session():
  nonlocal session_wanted
  session_wanted=not dock_visible;core.save_config(session_panel=session_wanted)
  if session_wanted and page!='live':show_page('live')
  place_session()
 def show_stream():show_page('live')
 def start_game(title):
  # An open game comes back at once. Another game has to wait until this one has closed.
  running=running_title(app.link.status)
  if title==running:
   # Nothing on the PC can bring a game forward while the console shows its menu.
   if gaming_mode and menu_in_front(app.link.status):say('Your PS5 is showing its menu. Press the PS button on your controller to go back to the game.')
   else:show_games(False)
   return
  if title in (flow.waiting,flow.after_close):return
  if not app.link.online:say('Connect to your PS5 first.');return
  def launch():
   flow.launch(title,time.perf_counter())
   if not app.link.launch(title,launched):flow.waiting=None;say('The PS5 is not connected.')
  if not running:launch();return
  def replace():
   flow.replace(title,time.perf_counter());app.link.send(CLOSE)
  ask_first('Switch games?',app.link.game_name(running)+' closes first. Anything not saved in it is lost.','Switch',replace)
 def launched(result):
  if result:flow.waiting=None;say(f'The PS5 did not start the game ({result:#010x}).')
 sounds=SoundBoard(lambda:app.stats.get('output_device'),core.config().get('sound_music',True),core.config().get('sound_cues',True),core.config().get('sound_level',.6))
 page_actions={}
 games=GameShelf(workspace,app.link,page_actions,sounds,animations.get)
 def reveal_game():
  # In Gaming Mode the console's menu stays on the TV, whether no game is open or the menu covers one.
  if gaming_mode and (not running_title(app.link.status) or menu_in_front(app.link.status)):return
  show_games(False)
 def show_strip():
  strip.show(tab=page if page in TABS else '',selected='settings' if page=='settings' else '',status=status_text(top_info),online=top_info.get('state')=='online',clock=time.strftime('%H:%M'),pad=bool(top_info.get('pad')))
 def typing():
  """True while a text field has the keys, where the arrows and Escape belong to the field."""
  widget=win.focus_get()
  return widget is not None and widget.winfo_class() in ('Entry','Text')
 def reveal(widget):
  """Scrolls the page so the control in the ring shows, when it sits on the page's scrolling part."""
  holder=settings_page if page=='settings' else library.page
  view=getattr(holder,'view',None)
  if view is None or not str(widget).startswith(str(view)):return
  height=view.winfo_height();top=widget.winfo_rooty()-view.winfo_rooty();bottom=top+widget.winfo_height();margin=round(24*strip.layout.unit)
  if top>=margin and bottom<=height-margin:return
  total=max(holder.height,height);shift=top-margin if top<margin else bottom-height+margin
  view.yview_moveto(max(0,min(1,(view.canvasy(0)+shift)/total)));holder.pin()
 def pop(items,right,top,choose):PopMenu(win,items,right,top,strip.layout.unit,choose)
 # The gold ring of the keys and the controller on Settings and Media. A click puts the mouse back in charge and hides it.
 walker=FocusWalker(pop,reveal);rail=False
 win.bind_all('<Button-1>',lambda _:walker.hide(),add='+')
 def show_page(name):
  nonlocal page,back_page,games_shown,has_video,last_info,revealed_at,rail
  if name==page:return
  PopMenu.close();walker.hide()
  if settings_page is not None and rail:settings_page.hover(None)
  rail=False
  # The small window holds only the picture, so any other page brings the full window back.
  if mini is not None and name!='live':small_window()
  # Everything is laid out before anything leaves, or the first visit shows the empty window for as long as it takes to build.
  if name=='settings' and settings_page is None:build_settings()
  if name=='media':library.open()
  was=page;page=name;games_shown=name=='games'
  if name in ('media','settings') and was in ('games','live'):back_page=was
  # The game's sound carries on behind Media and Settings, where only the picture is out of sight.
  app.video_hidden=name!='live';app.sound_hidden=games_shown;pad.navigating=name!='live'
  if was=='games':games.show(False);games.grid_remove()
  elif was=='live':stage.grid_remove()
  elif was=='media':library.hide();library.page.grid_remove()
  else:settings_page.grid_remove()
  if name=='live':stage.grid();revealed_at=time.perf_counter()
  else:
   has_video=False;last_info=0
   if presenter:presenter.frame=None
   if name=='games':games.grid(row=0,column=0,sticky='nsew');games.show(True)
   else:(library.page if name=='media' else settings_page).grid(row=0,column=0,sticky='nsew')
   if name=='settings':settings_page.refresh()
  sounds.show(games_shown);show_strip();fit_shell();place_session()
 def show_games(on):show_page('games' if on else 'live')
 def next_tab(step):return TABS[(TABS.index(page)+step)%len(TABS)] if page in TABS else 'games'
 def set_gaming(on):
  nonlocal gaming_mode
  gaming_mode=on;pad.ps_leaves=on
  if on!=fullscreen:full()
  # Leaving Gaming Mode stays on whichever page was showing.
  if on:show_games(True)
  games.set_exit('Exit Gaming Mode' if on else '')
 def power_menu():
  items=power_items(app.link.online,running_title(app.link.status),'Exit Gaming Mode' if gaming_mode else '')
  if not items:say('Connect to your PS5 first.');return
  _,_,right,bottom_edge=strip.hits['power'];PopMenu(win,items,strip.winfo_rootx()+right,strip.winfo_rooty()+bottom_edge+round(10*strip.layout.unit),strip.layout.unit,lambda key:page_actions[key]())
 def top_pressed(key):
  sounds.play('accept')
  if key=='games':show_games(True)
  elif key=='power':power_menu()
  elif key=='search':show_games(True);games.start_search()
  # On the live view this is plain fullscreen. Elsewhere it is the library's button.
  elif key=='fullscreen' and page=='live':full()
  else:page_actions[key]()
 strip=TopStrip(win,top_pressed);strip.grid(row=0,column=0,sticky='ew')
 pad=PadBridge(lambda:app.args.host,app.stop)
 Tooltip(session_button,'Session performance · Ctrl+I');Tooltip(screenshot_button,'Screenshot · F8');Tooltip(record_button,'Start / stop recording · F9');Tooltip(replay_button,'Save the last moments · F10');Tooltip(captures_button,'Your captures · Ctrl+L');Tooltip(mini_button,'Small window on top · Ctrl+M');Tooltip(live_button,'Go live · Ctrl+B')
 Tooltip(mute_button,'Mute / unmute');Tooltip(output,'Audio output');Tooltip(volume,'Volume')
 bottom=tk.Frame(win,bg=BG);bottom.grid(row=3,column=0,sticky='ew',padx=20,pady=(0,6));bottom.grid_columnconfigure(0,weight=1)
 message=ctk.CTkLabel(bottom,text='',text_color=MUTED,font=('Segoe UI',12),anchor='w',height=20);message.grid(row=0,column=0,sticky='ew')
 diagnostic=ctk.BooleanVar(value=core.config().get('diagnostic',False))
 match_on=ctk.BooleanVar(value=core.config().get('match_refresh',True))
 mic_on=ctk.BooleanVar(value=False)
 def set_microphone(on):
  """Your voice in recordings, instant replays and Go live. The choice is kept, and a microphone that will not open says why."""
  if on and not app.microphone.open(core.config().get('mic_device','')):
   mic_on.set(False);core.save_config(mic_on=False);app.notify('Microphone could not open: '+app.microphone.error);app.notice_until=time.perf_counter()+15;return
  if not on:app.microphone.close()
  mic_on.set(on);core.save_config(mic_on=on)
  app.notify(f'Microphone on: {app.microphone.name}. Your voice goes into recordings, replays and Go live.' if on else 'Microphone off.')
 presenter=None;surface=None;direct=False
 if app.renderer=='d3d11':
  # A window of its own that Tk never paints, because a swap chain and anything drawn on the same window fight over it.
  surface=tk.Frame(stage,bg='',width=1,height=1)
  try:
   from d3d11_presenter import D3D11Presenter
   presenter=D3D11Presenter(surface,core.config().get('sharpen',False),core.config().get('fsr',False),app.adapter,core.config().get('vrr',False));direct=True
  except Exception:surface.destroy();surface=None;app.use_gdi()
 if app.renderer=='gdi':
  from gdi_presenter import GdiPresenter
  presenter=GdiPresenter(canvas)
 from frame_pacing import CAPTURE_FRAME,FrameTimer,HitchWatch,RefreshClock
 refresh=RefreshClock(app.stop)
 # Variable refresh, when it is on and the driver offers it: each frame goes to the screen at its own time, from a timer that follows
 # the stream, and the screen starts its refresh then. Otherwise the paint follows the screen's refreshes as before.
 vrr_on=direct and presenter.tearing
 vrr_state='on' if vrr_on else 'fixed screen' if getattr(presenter,'fixed_screen',False) else 'unsupported' if core.config().get('vrr',False) else 'off'
 def next_due():
  with app.lock:return app.pacer.due()
 # Never two frames closer than one refresh, and never so far apart that 60 fps could not keep up.
 clock=FrameTimer(app.stop,next_due,spacing=lambda:min(refresh.period,.75*CAPTURE_FRAME)) if vrr_on else refresh
 seen_presented=0;shown_at=[None];hitches=HitchWatch();paint_took=[0]
 def note_shown(done):
  # The time between two frames on screen: 16.7 ms each on a steady screen, and 13.9 then 20.8 on a 144 Hz one, which is the judder.
  last,shown_at[0]=shown_at[0],done
  if last is not None and done-last<.25:app.timings.add('shown_gap_ms',(done-last)*1000)
  hitches.shown(done,refresh.period,done-app.started)
 def paint(output=presenter):
  # On the refresh clock's thread, so nothing in the Tk loop can delay a frame.
  try:
   now=time.perf_counter();seconds=clock.elapsed(now)
   with app.lock:missing=app.pacer.missing;item=app.pacer.advance(seconds,now) if seconds else None;missing=app.pacer.missing!=missing
   hitches.refresh(round(seconds/clock.period),missing,paint_took[0]>clock.period)
   if item is None:output.refresh();return
   image,arrived,prepared=item;paint_at=time.perf_counter();app.timings.add('prepared_slot_wait_ms',(paint_at-prepared)*1000)
   if output.draw(image):
    done=time.perf_counter();note_shown(done);app.timings.add('presenter_upload_ms',(done-paint_at)*1000);app.timings.add('receive_to_present_ms',(done-arrived)*1000);app.stats['video_presented']+=1;app.stats['last_frame_to_ui_ms']=round((done-arrived)*1000,1)
    if vrr_on:clock.last=done
   else:hitches.unpresented()
  except Exception as error:output.failed=error
  finally:paint_took[0]=time.perf_counter()-now
 def leave_direct():
  # This PC cannot keep the GPU output going, so the picture carries on through memory.
  nonlocal presenter,direct,vrr_on,vrr_state
  from gdi_presenter import GdiPresenter
  clock.after=None;direct=False;surface.grid_remove();presenter=GdiPresenter(canvas);app.use_gdi()
  # The refresh clock was not read while the frame timer ran, so its count starts again here.
  if vrr_on:vrr_on=False;vrr_state='off';refresh.elapsed(time.perf_counter())
 if direct:clock.after=paint
 last_tick=time.perf_counter();watch=HangWatch(threading.get_ident(),app.stop);awake=KeepAwake();rate=ScreenRate();battery=BatteryHint();fullscreen=False;mini=None;photo=None;photo_size=None;rate_at=time.perf_counter();rate_frames=0;fps=0;last_info=0;recording_at=None;cursor=CursorHider(win)
 def fit_shell():
  # The library and fullscreen video have the whole window to themselves.
  live=page=='live';bare=games_shown or live and (fullscreen or mini is not None)
  # Configuring a widget grids it again, so this comes before anything is taken away.
  bottom.grid_configure(padx=20 if live else 52)
  for widget,shown in ((strip,not bare),(footer,live and not bare),(bottom,not bare)):
   if shown:widget.grid()
   else:widget.grid_remove()
 def full():
  nonlocal fullscreen
  if mini is not None:small_window()
  fullscreen=not fullscreen;fit_shell()
  place_session();win.attributes('-fullscreen',fullscreen)
  cursor.active=fullscreen;cursor.moved()
 def on_screen(place):
  """A saved place for the small window, if it is still on this screen."""
  import re
  found=re.fullmatch(r'(\d+)x(\d+)\+(-?\d+)\+(-?\d+)',place) if isinstance(place,str) else None
  if not found:return False
  width,height,x,y=map(int,found.groups())
  return 160<=width<=2000 and 90<=height<=1200 and 0<=x<win.winfo_screenwidth()-100 and 0<=y<win.winfo_screenheight()-100
 def show_live(on_air):
  controls=getattr(settings_page,'live_controls',None)
  if controls is None:return
  button,status=controls
  button.restyle(text='End live stream' if on_air else 'Go live',tone='danger' if on_air else 'main')
  if app.broadcast.state=='live':status.configure(text='Live on '+app.broadcast.name+' for '+live_broadcast.clock(app.broadcast.elapsed())+'.',text_color=GOLD_SOFT)
  elif not on_air and status.cget('text').startswith('Live on '):status.configure(text='The live stream ended.',text_color=MUTED)
 def toggle_live():
  if app.broadcast.active:app.end_live();return
  saved=core.config();kind=saved.get('live_service');key=live_broadcast.unseal(saved.get('live_key',''));server=saved.get('live_server','')
  ready=kind=='obs' or kind in ('twitch','youtube') and key or kind=='custom' and server
  if not ready:
   show_page('settings');settings_page.open_section('live');say('Choose where to go live, then select Go live.');return
  problem=app.go_live(kind,key,server)
  if problem:say(problem)
 def small_window():
  """Only the picture, in a small window above every other one: Ctrl+M or its button, and again to come back."""
  nonlocal mini
  if mini is None:
   if gaming_mode:set_gaming(False)
   if fullscreen:full()
   if page!='live':show_page('live')
   zoomed=win.state()=='zoomed';mini=(win.geometry(),zoomed)
   if zoomed:win.state('normal')
   fit_shell();place_session();win.minsize(320,180)
   # Where it was left last time, or the lower right corner of the screen.
   factor=ctk.ScalingTracker.get_window_scaling(win);width,height=480,270
   place=core.config().get('mini_geometry')
   if not on_screen(place):place=f'{width}x{height}+{win.winfo_screenwidth()-round((width+28)*factor)}+{win.winfo_screenheight()-round((height+110)*factor)}'
   # In this order: on Windows, -topmost set after a move puts the window back where it was.
   win.attributes('-topmost',True);win.geometry(place)
  else:
   geometry,zoomed=mini;core.save_config(mini_geometry=win.geometry());mini=None
   win.attributes('-topmost',False);win.minsize(900,620);win.geometry(geometry)
   if zoomed:win.state('zoomed')
   fit_shell();place_session()
 win.bind('<Motion>',cursor.moved,add='+')
 page_actions.update(open=start_game,close=close_game,connect=connect_toggle,live=show_stream,media=lambda:show_page('media'),settings=lambda:show_page('settings'),fullscreen=lambda:set_gaming(not gaming_mode),rest=rest_console,off=power_off_console,reboot=reboot_console,soft_reset=soft_reset,recovery=recovery_console,exit=lambda:set_gaming(False))
 def close():awake.want(False);rate.want(False,0);app.microphone.close();app.stop.set();sounds.close();win.destroy()
 def focus_root():
  return (settings_page.view if page=='settings' else library.page) if page in ('settings','media') else None
 def focus_key(event):
  """The arrows and the controller on Settings and Media. On Settings the menu on the left is reached by going left past the
  panels; there, up and down open the sections and right goes back into them."""
  nonlocal rail
  root=focus_root()
  if root is None:return
  if page=='settings' and rail:
   order=settings_page.order;at=order.index(settings_page.current) if settings_page.current in order else 0
   if event in ('up','down'):
    key=order[(at+(1 if event=='down' else -1))%len(order)];settings_page.open_section(key);settings_page.hover(key)
   elif event in ('right','accept'):rail=False;settings_page.hover(None);walker.hide();walker.move(root,'down')
   return
  if event=='accept':walker.accept(root);return
  if event not in ('up','down','left','right'):return
  if not walker.move(root,event) and page=='settings' and event=='left':
   rail=True;walker.hide();settings_page.hover(settings_page.current)
 def escape(_):
  if typing():win.focus_set();return 'break'
  if ConfirmDialog.current is not None:ConfirmDialog.close()
  elif PopMenu.current is not None:PopMenu.close()
  elif games_shown and games.dismiss():pass
  elif page in ('media','settings'):show_page(back_page)
  elif gaming_mode:set_gaming(False)
  elif mini is not None:small_window()
  elif fullscreen:full()
 def grid_key(event):
  if games_shown and games.navigate(event):return 'break'
  if page in ('settings','media') and PopMenu.current is None and ConfirmDialog.current is None:
   # In a text field, left and right move the cursor and Enter leaves it; up and down still leave for the next control.
   if typing():
    if event in ('left','right'):return
    win.focus_set()
    if event=='accept':return 'break'
   focus_key(event);return 'break'
 def pad_event(event):
  dialog=ConfirmDialog.current
  if dialog is not None:
   if event=='accept':dialog.accept()
   elif event in ('back','leave'):dialog.cancel()
   return
  if PopMenu.current is not None:PopMenu.current.answer(event);return
  if games_shown:
   if event in ('back','leave'):
    if games.dismiss():pass
    elif running_title(app.link.status):reveal_game()
   # The shoulder buttons go through the tabs, as they do on the console.
   elif event=='next' and not games.menu:show_page(next_tab(1))
   elif event=='previous' and not games.menu:show_page(next_tab(-1))
   else:games.navigate(event)
  elif page=='live':
   if event=='leave':show_games(True)
  elif event in ('back','leave'):show_page(back_page)
  elif event=='next':show_page(next_tab(1))
  elif event=='previous':show_page(next_tab(-1))
  elif event in ('up','down','left','right','accept'):focus_key(event)
 def save_replay_key(_):
  app.save_replay();return 'break'
 win.protocol('WM_DELETE_WINDOW',close);win.bind('<Escape>',escape);win.bind('<F11>',lambda _:full());win.bind('<Control-i>',lambda _:toggle_session());win.bind('<Control-l>',lambda _:show_page('media'));win.bind('<Control-comma>',lambda _:show_page('settings'));win.bind('<F8>',lambda _:app.take_screenshot());win.bind('<F9>',lambda _:app.toggle_recording());win.bind('<F10>',save_replay_key);win.bind('<F7>',lambda _:set_microphone(not app.microphone.on));win.bind('<F6>',lambda _:reveal_game() if games_shown else show_games(True));win.bind('<Control-g>',lambda _:set_gaming(not gaming_mode));win.bind('<Control-m>',lambda _:small_window());win.bind('<Control-b>',lambda _:toggle_live());win.bind('<Left>',lambda _:grid_key('left'));win.bind('<Right>',lambda _:grid_key('right'));win.bind('<Up>',lambda _:grid_key('up'));win.bind('<Down>',lambda _:grid_key('down'));win.bind('<Return>',lambda _:grid_key('accept'));win.bind('<Prior>',lambda _:grid_key('previous'));win.bind('<Next>',lambda _:grid_key('next'));canvas.bind('<Double-Button-1>',lambda _:small_window() if mini is not None else full())
 def follow_console(now):
  # Runs once for each status, so the console's menu leaves the screen as soon as the status shows it.
  nonlocal menu_was_in_front,opened_title,opened_at,first_status
  playing=running_title(app.link.status)
  if app.link.online:
   change=flow.update(playing,now)
   if change in ('started','closed'):app.event('Game '+change+' on the PS5')
   if change=='started':opened_title=playing;opened_at=now;show_games(False)
   elif change=='closed':
    # A game opened from the library comes back to it, and one that died at once says so instead of leaving the console's menu on screen.
    if opened_title and now-opened_at<5:say(app.link.game_name(opened_title)+' closed as soon as it started.')
    if gaming_mode or opened_title:show_games(True)
    opened_title=''
   elif change=='launch':
    if not app.link.launch(flow.waiting,launched):flow.waiting=None
   elif change=='failed':say('The PS5 did not start the game.')
   if first_status:
    # Connecting while a game is already open goes straight to it.
    first_status=False
    if playing:
     games.go_to_title(playing)
     if not menu_in_front(app.link.status):show_games(False)
  covered=menu_in_front(app.link.status)
  # Someone in Media or Settings stays there, whatever the console's menu does.
  if gaming_mode and covered!=menu_was_in_front and page in ('games','live'):
   if covered:show_games(True)
   # The console names the game again while its menu is still fading out.
   elif playing:win.after(300,reveal_game)
  menu_was_in_front=covered
 info_at=0;decoded_mark=0;decoded_rate=0
 def library_info(active,linked,health):
  """What the top bar and the library's live cards say."""
  shown=bool(health['decoded_width']) and linked;status=app.link.status
  def degrees(name):
   return status[name] if isinstance(status.get(name),int) and status[name]>0 else None
  return dict(name=(app.console or {}).get('name') or 'PS5',state='online' if app.link.online else 'connecting' if active else 'offline',pad=bool(pad.name),fps=decoded_rate if shown else None,picture=f"{health['decoded_width']}×{health['decoded_height']}" if shown else '',bitrate=f"{health['received_mbps']:.0f} Mbps" if linked and health['received_mbps'] is not None else '',cpu=degrees('cpu_c'),soc=degrees('soc_c'))
 def tick():
  nonlocal photo,photo_size,rate_at,rate_frames,fps,last_info,has_video,recording_at,seen_status,info_at,decoded_mark,decoded_rate,top_info,seen_presented
  nonlocal last_tick
  if app.stop.is_set():close();return
  now=time.perf_counter()
  # A window that stops answering shows in the timeline, so a frozen picture can be told apart from a stream that stopped.
  stuck=watch.beat()
  if now-last_tick>.3:app.event(f'Window busy for {round((now-last_tick)*1000)} ms on the {page} page'+(f', in {stuck}' if stuck else ''))
  last_tick=now
  if app.args.seconds and now-app.started>=app.args.seconds:close();return
  win.update_idletasks();vw=max(1,canvas.winfo_width());vh=max(1,canvas.winfo_height());app.render_size=(vw,vh);canvas.coords(item_id,vw//2,vh//2);canvas.coords(placeholder,vw//2,vh//2)
  if direct and presenter.failed:leave_direct()
  if direct:
   item=None;presenter.wanted=(vw,vh)
   with app.lock:queue_ms=len(app.pcm)/192
  else:
   seconds=refresh.elapsed(now)
   with app.lock:missing=app.pacer.missing;item=app.pacer.advance(seconds,now) if seconds else None;queue_ms=len(app.pcm)/192;missing=app.pacer.missing!=missing
   hitches.refresh(0,missing,False)
   if item and (item[0].width>vw or item[0].height>vh):item=None
  # While PlayBridge connects again on its own, as when a game closes, the last picture stays on screen until the new one arrives.
  if not app.worker.is_alive() and has_video:
   has_video=False;canvas.itemconfigure(item_id,image='');photo=None;photo_size=None
   if presenter:presenter.frame=None
   if direct:surface.grid_remove()
  if direct:
   presented=app.stats['video_presented']
   if presented!=seen_presented:rate_frames+=presented-seen_presented;seen_presented=presented
   # The video window shows as soon as a picture waits for it, because the presenter makes its swap chain only on a window that shows.
   if not has_video and presenter.frame is not None and app.connection_state=='Connected' and app.worker.is_alive():has_video=True;ambient.show(False,'',now);surface.grid(row=0,column=0,sticky='nsew')
  elif item:
   has_video=True;ambient.show(False,'',now)
   canvas.itemconfigure(placeholder,state='hidden');image,arrived,prepared=item;paint_at=time.perf_counter();app.timings.add('prepared_slot_wait_ms',(paint_at-prepared)*1000)
   if presenter:presenter.draw(image)
   elif photo is None or photo_size!=image.size:
    photo=ImageTk.PhotoImage(image);photo_size=image.size;canvas.itemconfigure(item_id,image=photo);canvas.image=photo
   else:photo.paste(image)
   note_shown(time.perf_counter());app.timings.add('presenter_upload_ms',(time.perf_counter()-paint_at)*1000);app.timings.add('receive_to_present_ms',(time.perf_counter()-arrived)*1000);app.stats['video_presented']+=1;app.stats['last_frame_to_ui_ms']=round((time.perf_counter()-arrived)*1000,1);rate_frames+=1
  elif presenter:presenter.refresh()
  if not pad.events.empty():pad_event(pad.events.get_nowait())
  if app.link.status is not seen_status:seen_status=app.link.status;follow_console(now)
  # The video keeps arriving behind the other pages, so coming back shows a waiting screen only if no frame turns up.
  if not has_video and page=='live' and now-revealed_at>1:
   waiting='Connecting to your console…' if app.worker.is_alive() else 'Open Payload Manager on your PS5, then connect.'
   if direct:surface.grid_remove()
   ambient.show(True,app.error or waiting,now)
  if now-rate_at>=1:
   decoded=app.stats.get('video_decoded',0);decoded_rate=(decoded-decoded_mark)/(now-rate_at);decoded_mark=decoded
   fps=rate_frames/(now-rate_at);app.stats['presented_fps']=round(fps,1);rate_frames=0;rate_at=now
   # What the screen side looked like, to tell a PC that stutters from one that does not.
   app.stats['refresh_hz']=round(1/refresh.period,1);app.stats['vrr']=vrr_state;app.stats['hitches']=dict(hitches.counts);app.stats['hitch_log']=list(hitches.log)
   if direct:app.stats['present_timeouts']=presenter.timeouts;app.stats['cross_card']=presenter.cross;app.stats['frames_in_flight']=presenter.flight
   app.stats['screen_rate']=rate.label();app.stats['screen_rate_check']=rate.note;app.stats['controller_link']=pad.link(time.monotonic())
   # What the app cannot fix itself, it says, once a session and only when frames are really being lost.
   wanted_fps=core.PROFILES[app.args.profile].get('playback_fps') or (app.capture_info or {}).get('fps_target') or 60
   streaming=app.connection_state=='Connected' and app.worker.is_alive()
   hint=battery.second(streaming,app.stats['presented_fps'],wanted_fps);app.stats['on_battery']=battery.on
   if hint:app.notify(hint);app.notice_until=now+15
   app.snapshot()
  if now-last_info>.25:
   last_info=now;app.poll_capture_events();record_button.restyle(icon=icons['disconnect'] if app.recorder.active else icons['record'],tone='danger' if app.recorder.active else 'plain');on_air=app.broadcast.active;live_button.restyle(icon=icons['on_air'] if on_air else icons['live']);show_live(on_air);active=app.worker.is_alive();linked=app.connection_state=='Connected' and active
   connect_button.restyle(text='Disconnect' if active else 'Connect',icon=on_white['disconnect'] if active else on_white['connect'])
   # While a session runs the display and the PC stay on, unless the window is minimized.
   awake.want(linked and win.state()!='iconic')
   # A screen whose rate does not fit 60 fps gets one that does, but only while the game fills it.
   # From the first time the picture shows until the stream ends, so moving between pages does not make the screen flash each time.
   switched=rate.want(match_on.get() and not vrr_on and linked and win.state()!='iconic' and (page=='live' or rate.changed is not None),win.winfo_id())
   if switched:app.notify(f'Screen set from {switched[0]} to {switched[1]} Hz while the game streams, so every frame shows for the same time.')
   with app.metrics_lock:health=app.metrics.summary()
   if app.recorder.active and app.recorder.state=='recording':
    if recording_at is None:recording_at=now
   elif not app.recorder.active:recording_at=None
   if not fullscreen:
    place_session();roomy=win.winfo_width()
    if roomy<1120:output_rim.grid_remove()
    else:output_rim.grid()
    if roomy<1300:host_label.grid_remove()
    else:host_label.grid()
   session_button.restyle(selected=dock_visible)
   sounds.want_music(games_shown and not (flow.waiting or flow.after_close))
   pad.sending=CONSOLE_PAD_READY and app.link.online and page=='live'
   host_text=app.console_label()
   if host_label.cget('text')!=host_text:host_label.configure(text=host_text)
   playing=running_title(app.link.status)
   readings=console_line(app.link.status)
   if games_shown:games.sync(playing,flow.waiting or flow.after_close,'  ·  '.join(part for part in ('Menu open on your PS5' if menu_was_in_front else '',pad.name) if part) if app.link.online else 'Waiting for your PS5…',app.notice if now<app.notice_until else app.error or '')
   if now-info_at>=1:
    info_at=now;top_info=library_info(active,linked,health)
    if games_shown:games.set_info(top_info)
   if not games_shown:show_strip()
   if dock_visible and not fullscreen:dock.update_console(app.link.game_name(playing) if playing else 'No game open' if app.link.online else 'Not connected',readings)
   if dock_visible and not fullscreen:dock.update_session(app,health,fps,queue_ms,linked,now,now-recording_at if recording_at is not None else None)
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
   # The controller on the console says where it stands, and the game's picture never waits for it.
   if pad.sending:
    link=pad.link(time.monotonic())
    if not pad.name:info+='  ·  No controller on this PC'
    elif link in ('waiting','starting'):info+='  ·  Controller starting…'
    elif link=='failed':info+=f'  ·  Controller could not start ({pad.answer[1]&0xffffffff:08x})'
    elif link=='refused':info+=f'  ·  Controller input refused ({pad.answer[1]&0xffffffff:08x})'
    elif link=='unavailable':info+='  ·  Controller unavailable'
   if app.recorder.active:info+='  ·  '+(('REC '+str(int(now-recording_at))+' s') if recording_at is not None else 'Recording: '+app.recorder.state)
   if app.broadcast.state=='live':info+='  ·  LIVE '+live_broadcast.clock(app.broadcast.elapsed())+' on '+app.broadcast.name
   elif app.broadcast.active:info+='  ·  Going live…'
   if now<app.notice_until:info=app.notice
   if diagnostic.get():info+=f'   |   {fps:.0f} fps · PC {app.stats["last_frame_to_ui_ms"]:.1f} ms · audio queue {queue_ms:.0f} ms'
   # Errors in red and fresh news in gold, so neither hides among the stream's own details.
   message.configure(text=info,text_color='#FFAAA5' if app.error else GOLD_SOFT if now<app.notice_until else MUTED)
  # A 1 ms timer makes Tk spin and uses a whole core even with nothing to do. With the frames on another thread, this loop has only the window to look after.
  win.after(8 if direct and page=='live' else 2,tick)
 pad.start()
 win.after(1,lambda:set_gaming(True) if core.config().get('gaming_mode',False) else show_games(True))
 # A microphone left on stays on, and says so when it opens.
 if core.config().get('mic_on',False):win.after(800,lambda:set_microphone(True))
 win.after(5,tick);win.mainloop()
