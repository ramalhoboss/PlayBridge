"""PlayBridge desktop shell: rounded focus cards and a quiet, content-first layout."""
import sys,time,socket,threading,ipaddress,queue
import tkinter as tk
from pathlib import Path
import customtkinter as ctk
from luxury_theme import AmbientScene, Bezel, LuxButton, apply_theme, dot, fade_in, gold_field, gold_label, gold_menu, gold_title_bar, local_image, thin_scrollbar, tint, BG, CARD, GOLD, GOLD_HOVER, GOLD_SOFT, INK, MUTED, PANEL, RAISED, STAGE, TEXT
from gaming_hub import PerformanceDock, CaptureLibrary
from desktop_features import CursorHider, saved_consoles, remember_console
from PIL import Image,ImageTk
import sounddevice as sd

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
 def icon(name,colour=GOLD):return tint(Image.open(core.HERE/'assets'/(name+'.png')),colour)
 icons={name:icon(name) for name in ('fullscreen','speaker','muted','settings','connect','disconnect','camera','folder','controller')}
 icons['record']=Image.open(core.HERE/'assets/record.png').convert('RGBA')
 on_gold={name:icon(name,INK) for name in ('connect','disconnect')}
 dots={True:dot(GOLD),False:dot(MUTED)}
 menu_art=local_image('menu.png')
 if menu_art is not None:icons['settings']=tint(menu_art,GOLD)
 symbols=ctk.CTkImage(tint(Image.open(core.HERE/'assets/symbols.png'),GOLD),size=(120,24))
 apply_theme()
 win=ctk.CTk();win.title('PlayBridge');win.configure(fg_color=BG);gold_title_bar(win)
 animations=ctk.BooleanVar(master=win,value=core.config().get('animations',True))
 sw,sh=win.winfo_screenwidth(),win.winfo_screenheight();w=min(1540,sw-80);h=min(920,sh-110)
 win.geometry(f'{w}x{h}+{(sw-w)//2}+{max(20,(sh-h)//2)}');win.minsize(900,620)
 try:win.iconbitmap(str(core.HERE/'assets/playbridge.ico'))
 except tk.TclError:pass
 win.grid_columnconfigure(1,weight=1);win.grid_rowconfigure(1,weight=1)
 rail=Bezel(win,width=84,glow=3);rail.grid(row=0,column=0,rowspan=4,sticky='ns',padx=(8,0),pady=12);rail.pack_propagate(False)
 workspace=ctk.CTkFrame(win,fg_color='transparent');workspace.grid(row=1,column=1,sticky='nsew',padx=(14,18));workspace.grid_columnconfigure(0,weight=1);workspace.grid_rowconfigure(0,weight=1)
 head=ctk.CTkFrame(win,fg_color='transparent');head.grid(row=0,column=1,sticky='ew',padx=24,pady=(18,10));head.grid_columnconfigure(1,weight=1)
 logo=ctk.CTkImage(Image.open(core.HERE/'assets/playbridge.png'),size=(42,42))
 ctk.CTkLabel(head,text='',image=logo).grid(row=0,column=0,rowspan=2,padx=(0,14))
 gold_label(head,'P L A Y B R I D G E',21).grid(row=0,column=1,sticky='w')
 ctk.CTkLabel(head,text='C O N S O L E   S T R E A M I N G',font=('Segoe UI',9),text_color=MUTED,height=18).grid(row=1,column=1,sticky='w',pady=(1,0))
 symbol_label=ctk.CTkLabel(head,text='',image=symbols);symbol_label.grid(row=0,column=2,padx=(0,22))
 pill=LuxButton(head,'Connecting',icon=dots[False],width=122,height=28,radius=14,text_size=11,icon_size=7,behind=BG,text_colour=MUTED,clickable=False);pill.grid(row=0,column=3,rowspan=2,padx=18)
 full_button=LuxButton(head,icon=icons['fullscreen'],behind=BG);full_button.grid(row=0,column=7,rowspan=2,padx=(0,8))
 screenshot_button=LuxButton(head,command=app.take_screenshot,icon=icons['camera'],behind=BG);screenshot_button.grid(row=0,column=4,rowspan=2,padx=(0,8))
 record_button=LuxButton(head,command=app.toggle_recording,icon=icons['record'],behind=BG);record_button.grid(row=0,column=5,rowspan=2,padx=(0,8))
 captures_button=LuxButton(head,command=app.open_captures,icon=icons['folder'],behind=BG);captures_button.grid(row=0,column=6,rowspan=2,padx=(0,8))
 stage=Bezel(workspace,fill=STAGE,glow=3);stage.grid(row=0,column=0,sticky='nsew');stage.body.grid_columnconfigure(0,weight=1);stage.body.grid_rowconfigure(0,weight=1)
 canvas=tk.Canvas(stage.body,bg=STAGE,borderwidth=0,highlightthickness=0);canvas.grid(row=0,column=0,sticky='nsew')
 item_id=canvas.create_image(0,0,anchor='center');placeholder=canvas.create_text(0,0,text='',state='hidden')
 ambient=AmbientScene(canvas,animations.get())
 has_video=False
 footer=Bezel(win,glow=3);footer.grid(row=2,column=1,sticky='ew',padx=(14,18),pady=(6,2));footer.body.grid_columnconfigure(3,weight=1)
 def device_label(name):
  return name.replace('Altifalantes','Speakers').replace('Auscultadores','Headphones').replace('Saída digital','Digital output')
 apis=sd.query_hostapis();devs=sd.query_devices();outputs=[(i,device_label(d['name'])) for i,d in enumerate(devs) if d['max_output_channels']>=2 and apis[d['hostapi']]['name']=='Windows WASAPI']
 choice=ctk.StringVar(value=device_label(app.output_name))
 def change_audio(value):
  try:
   index=next(i for i,n in outputs if n==value);app.open_audio(index);core.save_config(output=devs[index]['name']+' ['+apis[devs[index]['hostapi']]['name']+']')
  except Exception as e:app.error='Audio output: '+str(e)
 mute=ctk.BooleanVar(value=app.muted)
 def mute_audio():
  app.muted=not app.muted;mute_button.restyle(icon=icons['speaker'] if not app.muted else icons['muted'])
 mute_button=LuxButton(footer.body,command=mute_audio,icon=icons['speaker'],width=34,height=34,radius=17,icon_size=18);mute_button.grid(row=0,column=0,padx=(4,8),pady=2)
 volume=ctk.CTkSlider(footer.body,from_=0,to=1,command=lambda v:setattr(app,'volume',v),progress_color=GOLD,button_color=GOLD,button_hover_color=GOLD_HOVER,width=90,height=16);volume.set(app.volume);volume.grid(row=0,column=1,padx=(0,18))
 output_rim,output=gold_menu(footer.body,variable=choice,values=[n for _,n in outputs] or ['No audio device'],command=change_audio,fg_color=CARD,button_color=CARD,button_hover_color=RAISED,text_color=MUTED,height=30,width=230,font=('Segoe UI',11));output_rim.grid(row=0,column=2,padx=(0,12))
 host_label=ctk.CTkLabel(footer.body,text=app.args.host,text_color=MUTED,font=('Segoe UI',11));host_label.grid(row=0,column=3,sticky='e',padx=16)
 def disconnect():
  app.intentional_disconnect=True
  if app.sock:
   try:app.sock.shutdown(socket.SHUT_RDWR)
   except OSError:pass
 def connect_toggle():
  if app.worker.is_alive():disconnect()
  else:app.restart()
 connect_button=LuxButton(footer.body,'Connect',connect_toggle,icon=on_gold['connect'],width=130,height=38,icon_size=16,tone='gold');connect_button.grid(row=0,column=4,padx=(0,4))
 settings_window=None
 def settings():
  nonlocal settings_window
  if settings_window is not None and settings_window.winfo_exists():settings_window.focus();return
  dialog=ctk.CTkToplevel(win);settings_window=dialog;dialog.title('PlayBridge · Settings');gold_title_bar(dialog)
  dh=min(820,sh-120);dx=max(0,min(sw-520,win.winfo_rootx()+(win.winfo_width()-500)//2));dy=max(30,min(sh-dh-65,win.winfo_rooty()+(win.winfo_height()-dh)//2))
  dialog.geometry(f'500x{dh}+{dx}+{dy}');dialog.resizable(False,False);dialog.configure(fg_color=BG);dialog.transient(win)
  body=ctk.CTkScrollableFrame(dialog,fg_color=BG);body.pack(fill='both',expand=True);thin_scrollbar(body)
  fade_in(dialog,animations.get())
  gold_label(body,'Make it yours.',28).pack(anchor='w',padx=28,pady=(26,6))
  ctk.CTkLabel(body,text='Your connection. Your picture. Your space.',font=('Segoe UI',13),text_color=MUTED).pack(anchor='w',padx=28,pady=(0,22))
  favourites=saved_consoles(core.config(),core.PROFILES)
  favourite_map={item['name']+' · '+item['host']:item for item in favourites}
  def choose_favourite(label):
   if label not in favourite_map:return
   item=favourite_map[label];host.delete(0,'end');host.insert(0,item['host']);console_name.delete(0,'end');console_name.insert(0,item['name']);profile.set(core.PROFILES[item['profile']]['name'])
  if favourite_map:
   ctk.CTkLabel(body,text='Favourite consoles',font=('Segoe UI',13,'bold')).pack(anchor='w',padx=28)
   gold_menu(body,behind=BG,values=list(favourite_map),command=choose_favourite,height=30,fg_color=CARD,button_color=CARD,variable=ctk.StringVar(value='Choose a saved console'))[0].pack(fill='x',padx=28,pady=(8,18))
  ctk.CTkLabel(body,text='Console IP address',font=('Segoe UI',13,'bold')).pack(anchor='w',padx=28)
  host_rim,host=gold_field(body,height=32);host.insert(0,app.args.host);host_rim.pack(fill='x',padx=28,pady=(8,16))
  scan_results=queue.Queue();discovered={}
  scan_choice=ctk.StringVar(value='Select a console')
  def select_console(label):
   if label in discovered:host.delete(0,'end');host.insert(0,discovered[label])
  found_rim,found_menu=gold_menu(body,behind=BG,variable=scan_choice,values=['Select a console'],command=select_console,height=30,fg_color=CARD,button_color=CARD);found_rim.pack(fill='x',padx=28,pady=(0,6))
  scan_status=ctk.CTkLabel(body,text='Find your PS5 or enter its IP address above.',text_color=MUTED,font=('Segoe UI',11));scan_status.pack(anchor='w',padx=28)
  def finish_scan():
   if not dialog.winfo_exists():return
   try:items,problem=scan_results.get_nowait()
   except queue.Empty:dialog.after(100,finish_scan);return
   scan_button.restyle(enabled=True,text='Find console')
   discovered.clear();discovered.update({item['name']+' · '+item['ip']:item['ip'] for item in items})
   found_menu.configure(values=list(discovered) or ['No console found'])
   if discovered:
    label=next(iter(discovered));scan_choice.set(label);select_console(label);scan_status.configure(text='Select your console, then save to connect.')
   else:scan_choice.set('No console found');scan_status.configure(text=problem or 'No console found. Enter the IP manually; check Payload Manager.')
  def scan():
   scan_button.restyle(enabled=False,text='Scanning…');scan_status.configure(text='Searching the local network…');preferred=host.get().strip()
   def work():
    from console_discovery import discover
    try:scan_results.put((discover(preferred),None))
    except Exception:scan_results.put(([],'Network scan failed. You can still enter the IP manually.'))
   threading.Thread(target=work,name='Console discovery',daemon=True).start();dialog.after(100,finish_scan)
  scan_button=LuxButton(body,'Find console',scan,height=32,radius=8,behind=BG);scan_button.pack(fill='x',padx=28,pady=(0,12))
  ctk.CTkLabel(body,text='Quality profile',font=('Segoe UI',13,'bold')).pack(anchor='w',padx=28)
  profiles={v['name']:k for k,v in core.PROFILES.items()};profile=ctk.StringVar(value=core.PROFILES[app.args.profile]['name'])
  gold_menu(body,behind=BG,variable=profile,values=list(profiles),height=30,fg_color=CARD,button_color=CARD)[0].pack(fill='x',padx=28,pady=(8,8))
  ctk.CTkLabel(body,text='Profiles apply on reconnect. 30 fps limits PC playback only.\n1440p and 4K need the PS5 video output set to that resolution.',font=('Segoe UI',11),text_color=MUTED,justify='left').pack(anchor='w',padx=28,pady=(0,12))
  ctk.CTkLabel(body,text='Console name',font=('Segoe UI',13,'bold')).pack(anchor='w',padx=28)
  name_rim,console_name=gold_field(body,height=30,placeholder_text='My PS5');name_rim.pack(fill='x',padx=28,pady=(8,8))
  match=next((c for c in favourites if c['host']==app.args.host),None)
  if match:console_name.insert(0,match['name'])
  favourite_status=ctk.CTkLabel(body,text='Save this IP and quality profile for next time.',text_color=MUTED,font=('Segoe UI',11));favourite_status.pack(anchor='w',padx=28,pady=(0,6))
  def save_favourite():
   try:items=remember_console(core.config(),console_name.get(),host.get(),profiles[profile.get()],core.PROFILES)
   except ValueError:favourite_status.configure(text='Enter a valid console IP address.',text_color='#FF9C9C');return
   core.save_config(consoles=items);favourite_status.configure(text='Favourite saved with this quality profile.',text_color=GOLD_SOFT)
  heart=local_image('heart.png');heart_icon=tint(heart,GOLD) if heart is not None else None
  LuxButton(body,'Save to favourites',save_favourite,icon=heart_icon,height=34,radius=8,icon_size=16,behind=BG).pack(fill='x',padx=28,pady=(0,18))
  reconnect=ctk.BooleanVar(value=app.args.auto_reconnect)
  ctk.CTkSwitch(body,text='Reconnect automatically',variable=reconnect,progress_color=GOLD,font=('Segoe UI',12)).pack(anchor='w',padx=28,pady=(0,14))
  manual=ctk.BooleanVar(value=app.args.connect_only)
  ctk.CTkSwitch(body,text='ELF already loaded in Payload Manager',variable=manual,progress_color=GOLD,font=('Segoe UI',12)).pack(anchor='w',padx=28)
  ctk.CTkLabel(body,text='Off: PlayBridge uploads the ELF automatically.\nOn: load PlayBridge.elf, then connect within 60 seconds.',font=('Segoe UI',12),text_color=MUTED,justify='left').pack(anchor='w',padx=28,pady=(12,10))
  ctk.CTkSwitch(body,text='Show performance stats',variable=diagnostic,progress_color=GOLD,font=('Segoe UI',12),command=lambda:core.save_config(diagnostic=diagnostic.get())).pack(anchor='w',padx=28,pady=(0,10))
  def choose_capture_folder():
   from tkinter import filedialog
   folder=filedialog.askdirectory(parent=dialog,title='Choose capture folder',initialdir=str(app.capture_folder()))
   if folder:core.save_config(capture_folder=folder);app.notify('Capture folder updated.')
  LuxButton(body,'Choose capture folder',choose_capture_folder,height=34,radius=8,behind=BG).pack(fill='x',padx=28,pady=(0,8))
  def save_diagnostics():
   from tkinter import filedialog
   path=filedialog.asksaveasfilename(parent=dialog,title='Export diagnostics',defaultextension='.zip',initialfile='PlayBridge-diagnostics.zip',filetypes=[('ZIP archive','*.zip')])
   if path:app.export_diagnostics(path)
  LuxButton(body,'Export diagnostics',save_diagnostics,height=34,radius=8,behind=BG).pack(fill='x',padx=28,pady=(0,8))
  ctk.CTkLabel(body,text='Appearance',font=('Segoe UI',17,'bold'),text_color=TEXT).pack(anchor='w',padx=28,pady=(18,10))
  def change_motion():
   ambient.animations=animations.get();core.save_config(animations=animations.get())
  ctk.CTkSwitch(body,text='Ambient animations',variable=animations,command=change_motion,progress_color=GOLD,font=('Segoe UI',12)).pack(anchor='w',padx=28,pady=(0,8))
  ctk.CTkLabel(body,text='Motion pauses during video playback.',
  font=('Segoe UI',11),text_color=MUTED).pack(anchor='w',padx=28,pady=(0,12))
  if menu_art is not None:
   ctk.CTkLabel(body,text='Local artwork · Menu icon',font=('Segoe UI',11),text_color=MUTED).pack(anchor='w',padx=28,pady=(0,12))
  error=ctk.CTkLabel(dialog,text='',text_color='#FF9C9C',font=('Segoe UI',12));error.pack(anchor='w',padx=28)
  def save():
   try:ipaddress.IPv4Address(host.get().strip())
   except ValueError:error.configure(text='Enter a valid IPv4 address.');return
   app.args.host=host.get().strip();app.args.connect_only=manual.get();app.args.profile=profiles[profile.get()];app.args.auto_reconnect=reconnect.get();core.save_config(host=app.args.host,connect_only=app.args.connect_only,profile=app.args.profile,auto_reconnect=app.args.auto_reconnect);host_label.configure(text=app.args.host);dialog.destroy();disconnect()
   def connect_when_ready():
    if app.stop.is_set():return
    if app.worker.is_alive():win.after(100,connect_when_ready)
    else:app.restart()
   win.after(100,connect_when_ready)
  LuxButton(dialog,'Save changes',save,height=42,radius=21,text_size=13,tone='gold',behind=BG).pack(fill='x',padx=28,pady=(0,22))
 settings_button=LuxButton(head,command=settings,icon=icons['settings'],behind=BG);settings_button.grid(row=0,column=8,rowspan=2)
 library=CaptureLibrary(win,app,animations.get())
 captures_button.command=library.open
 def export_session():
  from tkinter import filedialog
  path=filedialog.asksaveasfilename(parent=win,title='Export diagnostics',defaultextension='.zip',initialfile='PlayBridge-diagnostics.zip',filetypes=[('ZIP archive','*.zip')])
  if path:app.export_diagnostics(path)
 dock_rim=Bezel(workspace,glow=3);dock=PerformanceDock(dock_rim.body,export_session);dock.pack(fill='both',expand=True)
 dock_visible=bool(core.config().get('performance_dock',w>=1250));dock_wanted=dock_visible
 def set_dock(visible):
  nonlocal dock_visible
  dock_visible=visible
  if visible:dock_rim.grid(row=0,column=1,sticky='nsew',padx=(10,0))
  else:dock_rim.grid_remove()
 def toggle_dock():
  nonlocal dock_wanted
  dock_wanted=not dock_visible;set_dock(dock_wanted);core.save_config(performance_dock=dock_wanted)
 def show_stream():
  nonlocal dock_wanted
  dock_wanted=False;set_dock(False);core.save_config(performance_dock=False)
 set_dock(dock_visible)
 gold_label(rail.body,'PB',19).pack(pady=(12,22))
 nav_buttons={}
 for label,name,command in (('LIVE','controller',show_stream),('MEDIA','folder',library.open),('STATS','connect',toggle_dock),('SETUP','settings',settings)):
  button=LuxButton(rail.body,label,command,icon=icons[name],width=58,height=66,text_size=10,icon_size=20,tone='ghost',compound='top',selected=label=='LIVE')
  button.pack(padx=3,pady=5);nav_buttons[label]=button
 ctk.CTkLabel(rail.body,text='DIRECT\nPLAY',font=('Segoe UI',8,'bold'),text_color=MUTED).pack(side='bottom',pady=12)
 Tooltip(nav_buttons['STATS'],'Session performance · Ctrl+I');Tooltip(nav_buttons['MEDIA'],'Capture library · Ctrl+L')
 Tooltip(screenshot_button,'Screenshot · F8');Tooltip(record_button,'Start / stop recording · F9');Tooltip(captures_button,'Capture library · Ctrl+L')
 Tooltip(settings_button,'Connection settings');Tooltip(full_button,'Fullscreen · F11');Tooltip(mute_button,'Mute / unmute');Tooltip(output,'Audio output');Tooltip(volume,'Volume')
 bottom=ctk.CTkFrame(win,fg_color='transparent');bottom.grid(row=3,column=1,sticky='ew',padx=26,pady=(0,9));bottom.grid_columnconfigure(0,weight=1)
 message=ctk.CTkLabel(bottom,text='',text_color=MUTED,font=('Segoe UI',10),anchor='w',height=16);message.grid(row=0,column=0,sticky='ew')
 diagnostic=ctk.BooleanVar(value=core.config().get('diagnostic',False))
 presenter=None
 if app.renderer=='gdi':
  from gdi_presenter import GdiPresenter
  presenter=GdiPresenter(canvas)
 from frame_pacing import RefreshClock
 refresh=RefreshClock(app.stop)
 fullscreen=False;photo=None;photo_size=None;rate_at=time.perf_counter();rate_frames=0;fps=0;last_info=0;recording_at=None;cursor=CursorHider(win)
 def full():
  nonlocal fullscreen
  fullscreen=not fullscreen
  if fullscreen:
   for widget in (head,footer,bottom,rail):widget.grid_remove()
   workspace.grid_configure(column=0,columnspan=2,padx=0);dock_rim.grid_remove()
   stage.edge_to_edge(True)
  else:
   for widget in (head,footer,bottom,rail):widget.grid()
   workspace.grid_configure(column=1,columnspan=1,padx=(14,18));set_dock(dock_wanted and win.winfo_width()>=1180)
   stage.edge_to_edge(False)
  win.attributes('-fullscreen',fullscreen)
  cursor.active=fullscreen;cursor.moved()
 canvas.bind('<Motion>',cursor.moved,add='+')
 full_button.command=full
 def close():app.stop.set();win.destroy()
 def escape(_):
  if fullscreen:full()
 win.protocol('WM_DELETE_WINDOW',close);win.bind('<Escape>',escape);win.bind('<F11>',lambda _:full());win.bind('<Control-i>',lambda _:toggle_dock());win.bind('<Control-l>',lambda _:library.open());win.bind('<Control-comma>',lambda _:settings());win.bind('<F8>',lambda _:app.take_screenshot());win.bind('<F9>',lambda _:app.toggle_recording());canvas.bind('<Double-Button-1>',lambda _:full())
 def tick():
  nonlocal photo,photo_size,rate_at,rate_frames,fps,last_info,has_video,recording_at
  if app.stop.is_set():close();return
  now=time.perf_counter()
  if app.args.seconds and now-app.started>=app.args.seconds:close();return
  win.update_idletasks();vw=max(1,canvas.winfo_width());vh=max(1,canvas.winfo_height());app.render_size=(vw,vh);canvas.coords(item_id,vw//2,vh//2);canvas.coords(placeholder,vw//2,vh//2)
  seconds=refresh.elapsed(now)
  with app.lock:item=app.pacer.advance(seconds,now) if seconds else None;queue_ms=len(app.pcm)/192
  if item and (item[0].width>vw or item[0].height>vh):item=None
  if not app.worker.is_alive() and has_video:
   has_video=False;canvas.itemconfigure(item_id,image='');photo=None;photo_size=None
   if presenter:presenter.frame=None
  if item:
   has_video=True;ambient.show(False,'',now)
   canvas.itemconfigure(placeholder,state='hidden');image,arrived,prepared=item;paint_at=time.perf_counter();app.timings.add('prepared_slot_wait_ms',(paint_at-prepared)*1000)
   if presenter:presenter.draw(image)
   elif photo is None or photo_size!=image.size:
    photo=ImageTk.PhotoImage(image);photo_size=image.size;canvas.itemconfigure(item_id,image=photo);canvas.image=photo
   else:photo.paste(image)
   app.timings.add('presenter_upload_ms',(time.perf_counter()-paint_at)*1000);app.timings.add('receive_to_present_ms',(time.perf_counter()-arrived)*1000);app.stats['video_presented']+=1;app.stats['last_frame_to_ui_ms']=round((time.perf_counter()-arrived)*1000,1);rate_frames+=1
  elif presenter:presenter.refresh()
  if not has_video:
   waiting='Connecting to your console…' if app.worker.is_alive() else 'Open Payload Manager on your PS5, then connect.'
   ambient.show(True,app.error or waiting,now)
  if now-rate_at>=1:
   fps=rate_frames/(now-rate_at);app.stats['presented_fps']=round(fps,1);rate_frames=0;rate_at=now;app.snapshot()
  if now-last_info>.25:
   last_info=now;app.poll_capture_events();record_button.restyle(icon=icons['disconnect'] if app.recorder.active else icons['record'],tone='danger' if app.recorder.active else 'plain');active=app.worker.is_alive();linked=app.connection_state=='Connected' and active
   connect_button.restyle(text='Disconnect' if active else 'Connect',icon=on_gold['disconnect'] if active else on_gold['connect'])
   pill.restyle(text='LIVE' if linked else 'Reconnecting' if active and app.connection_state.startswith('Reconnecting') else 'Connecting' if active else 'Offline',icon=dots[bool(linked)],text_colour=GOLD if linked else MUTED)
   with app.metrics_lock:health=app.metrics.summary()
   if app.recorder.active and app.recorder.state=='recording':
    if recording_at is None:recording_at=now
   elif not app.recorder.active:recording_at=None
   if not fullscreen:
    if win.winfo_width()<1180 and dock_visible:set_dock(False)
    elif win.winfo_width()>=1180 and dock_wanted and not dock_visible:set_dock(True)
    if win.winfo_width()<1250:symbol_label.grid_remove()
    else:symbol_label.grid()
   nav_buttons['STATS'].restyle(selected=dock_visible)
   nav_buttons['LIVE'].restyle(selected=not dock_visible)
   if dock_visible and not fullscreen:dock.update_session(app,health,fps,queue_ms,linked,now,now-recording_at if recording_at is not None else None)
   dimensions=f"{health['decoded_width']} × {health['decoded_height']}" if health['decoded_width'] else 'Waiting for video'
   info=app.error or (dimensions+'  ·  Stereo' if linked else 'Ready to connect')
   if linked:
    confirmed=app.capture_info and app.capture_info.get('confirmed');info+='  ·  '+(str(app.capture_info.get('fps_target'))+' fps target / '+str(app.capture_info.get('bitrate_target',0)//1000000)+' Mbps' if confirmed else 'Legacy payload: quality profile not confirmed')
   notice=core.resolution_notice(app.capture_info)
   if linked and notice:info+='  ·  '+notice
   if linked and health['received_mbps'] is not None:info+=f"  ·  {health['received_mbps']:.1f} Mbps received"
   if core.PROFILES[app.args.profile].get('playback_fps'):info+='  ·  30 fps PC playback'
   if app.recorder.active:info+='  ·  '+(('REC '+str(int(now-recording_at))+' s') if recording_at is not None else 'Recording: '+app.recorder.state)
   if now<app.notice_until:info=app.notice
   if diagnostic.get():info+=f'   |   {fps:.0f} fps · PC {app.stats["last_frame_to_ui_ms"]:.1f} ms · audio queue {queue_ms:.0f} ms'
   message.configure(text=info,text_color='#FFAAA5' if app.error else MUTED)
  win.after(1,tick)
 win.after(5,tick);win.mainloop()
