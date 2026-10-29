"""PlayBridge desktop shell: rounded focus cards and a quiet, content-first layout."""
import sys,time,socket,threading,ipaddress
import tkinter as tk
from pathlib import Path
import customtkinter as ctk
from PIL import Image,ImageTk
import sounddevice as sd

BG='#070E20';CARD='#101E37';TEXT='#F4F8FF';MUTED='#8399BB';BLUE='#0070F3';HOVER='#2489FF'

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
  ctk.CTkLabel(self.popup,text=self.text,fg_color='#172E50',text_color=TEXT,font=('Segoe UI',11),padx=12,pady=5).pack()
 def hide(self,_=None):
  if self.timer is not None:self.widget.after_cancel(self.timer);self.timer=None
  if self.popup is not None:self.popup.destroy();self.popup=None

def run_ui(app):
 core=sys.modules[app.__class__.__module__]
 def icon(name,size=20):return ctk.CTkImage(Image.open(core.HERE/'assets'/(name+'.png')),size=(size,size))
 icons={name:icon(name) for name in ('fullscreen','speaker','muted','settings','connect','disconnect','camera','record','folder')}
 symbols=ctk.CTkImage(Image.open(core.HERE/'assets/symbols.png'),size=(120,24))
 ctk.set_appearance_mode('dark');ctk.set_default_color_theme('blue')
 win=ctk.CTk();win.title('PlayBridge');win.configure(fg_color=BG)
 sw,sh=win.winfo_screenwidth(),win.winfo_screenheight();w=min(1360,sw-80);h=min(880,sh-110)
 win.geometry(f'{w}x{h}+{(sw-w)//2}+{max(20,(sh-h)//2)}');win.minsize(900,620)
 try:win.iconbitmap(str(core.HERE/'assets/playbridge.ico'))
 except tk.TclError:pass
 win.grid_columnconfigure(0,weight=1);win.grid_rowconfigure(1,weight=1)
 head=ctk.CTkFrame(win,fg_color='transparent');head.grid(row=0,column=0,sticky='ew',padx=24,pady=(18,14));head.grid_columnconfigure(1,weight=1)
 logo=ctk.CTkImage(Image.open(core.HERE/'assets/playbridge.png'),size=(34,34))
 ctk.CTkLabel(head,text='',image=logo).grid(row=0,column=0,padx=(0,10))
 ctk.CTkLabel(head,text='PLAYBRIDGE',font=('Segoe UI',20,'bold'),text_color=TEXT).grid(row=0,column=1,sticky='w')
 ctk.CTkLabel(head,text='',image=symbols).grid(row=0,column=2,padx=(0,22))
 pill=ctk.CTkLabel(head,text='●  Connecting',text_color=BLUE,width=95,height=30,font=('Segoe UI',11));pill.grid(row=0,column=3,padx=12)
 full_button=ctk.CTkButton(head,text='',image=icons['fullscreen'],width=36,height=36,corner_radius=18,fg_color=CARD,hover_color='#1D3D66',text_color=TEXT,font=('Segoe UI',19));full_button.grid(row=0,column=7,padx=(0,8))
 screenshot_button=ctk.CTkButton(head,text='',image=icons['camera'],command=app.take_screenshot,width=36,height=36,corner_radius=18,fg_color=CARD,hover_color='#1D3D66');screenshot_button.grid(row=0,column=4,padx=(0,8))
 record_button=ctk.CTkButton(head,text='',image=icons['record'],command=app.toggle_recording,width=36,height=36,corner_radius=18,fg_color=CARD,hover_color='#1D3D66');record_button.grid(row=0,column=5,padx=(0,8))
 captures_button=ctk.CTkButton(head,text='',image=icons['folder'],command=app.open_captures,width=36,height=36,corner_radius=18,fg_color=CARD,hover_color='#1D3D66');captures_button.grid(row=0,column=6,padx=(0,8))
 stage=ctk.CTkFrame(win,fg_color='#040913',corner_radius=10,border_width=1,border_color='#25466F');stage.grid(row=1,column=0,sticky='nsew',padx=18);stage.grid_columnconfigure(0,weight=1);stage.grid_rowconfigure(0,weight=1)
 canvas=tk.Canvas(stage,bg='#040913',borderwidth=0,highlightthickness=0);canvas.grid(row=0,column=0,sticky='nsew',padx=5,pady=5)
 item_id=canvas.create_image(0,0,anchor='center');placeholder=canvas.create_text(0,0,text='Your console. Your screen.',fill=MUTED,font=('Segoe UI',20),justify='center')
 footer=ctk.CTkFrame(win,fg_color=CARD,corner_radius=12,height=58);footer.grid(row=2,column=0,sticky='ew',padx=18,pady=(12,10));footer.grid_columnconfigure(3,weight=1)
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
  app.muted=not app.muted;mute_button.configure(image=icons['speaker'] if not app.muted else icons['muted'])
 mute_button=ctk.CTkButton(footer,text='',image=icons['speaker'],command=mute_audio,width=34,height=34,corner_radius=17,fg_color='#162C4C',hover_color='#224471',text_color=BLUE,font=('Segoe UI',19));mute_button.grid(row=0,column=0,padx=(14,8),pady=12)
 volume=ctk.CTkSlider(footer,from_=0,to=1,command=lambda v:setattr(app,'volume',v),progress_color=BLUE,button_color=BLUE,button_hover_color=HOVER,width=90,height=16);volume.set(app.volume);volume.grid(row=0,column=1,padx=(0,18))
 output=ctk.CTkOptionMenu(footer,variable=choice,values=[n for _,n in outputs] or ['No audio device'],command=change_audio,fg_color=CARD,button_color=CARD,button_hover_color='#1D3D66',text_color=MUTED,height=32,width=230,corner_radius=12,font=('Segoe UI',11));output.grid(row=0,column=2,padx=(0,12))
 host_label=ctk.CTkLabel(footer,text=app.args.host,text_color=MUTED,font=('Segoe UI',11));host_label.grid(row=0,column=3,sticky='e',padx=16)
 def disconnect():
  app.intentional_disconnect=True
  if app.sock:
   try:app.sock.shutdown(socket.SHUT_RDWR)
   except OSError:pass
 def connect_toggle():
  if app.worker.is_alive():disconnect()
  else:app.restart()
 connect_button=ctk.CTkButton(footer,text='Connect',image=icons['connect'],compound='left',command=connect_toggle,corner_radius=18,height=36,width=130,fg_color=BLUE,hover_color=HOVER,text_color='white',font=('Segoe UI',12,'bold'));connect_button.grid(row=0,column=4,padx=(0,14))
 settings_window=None
 def settings():
  nonlocal settings_window
  if settings_window is not None and settings_window.winfo_exists():settings_window.focus();return
  dialog=ctk.CTkToplevel(win);settings_window=dialog;dialog.title('PlayBridge · Settings');dialog.geometry(f'500x650+{max(0,win.winfo_rootx()+(win.winfo_width()-500)//2)}+{max(0,win.winfo_rooty()+(win.winfo_height()-650)//2)}');dialog.resizable(False,False);dialog.configure(fg_color=BG);dialog.transient(win)
  ctk.CTkLabel(dialog,text='Stream settings',font=('Segoe UI',25,'bold'),text_color=TEXT).pack(anchor='w',padx=28,pady=(26,6))
  ctk.CTkLabel(dialog,text='Keep your console and PC on the same network.',font=('Segoe UI',13),text_color=MUTED).pack(anchor='w',padx=28,pady=(0,22))
  ctk.CTkLabel(dialog,text='Console IP address',font=('Segoe UI',13,'bold')).pack(anchor='w',padx=28)
  host=ctk.CTkEntry(dialog,height=42,corner_radius=14,fg_color=CARD,border_width=0);host.insert(0,app.args.host);host.pack(fill='x',padx=28,pady=(8,16))
  ctk.CTkLabel(dialog,text='Quality profile',font=('Segoe UI',13,'bold')).pack(anchor='w',padx=28)
  profiles={v['name']:k for k,v in core.PROFILES.items()};profile=ctk.StringVar(value=core.PROFILES[app.args.profile]['name'])
  ctk.CTkOptionMenu(dialog,variable=profile,values=list(profiles),height=36,fg_color=CARD,button_color='#1D3D66').pack(fill='x',padx=28,pady=(8,8))
  ctk.CTkLabel(dialog,text='Bitrate applies on reconnect. 30 fps limits PC playback only.',font=('Segoe UI',11),text_color=MUTED).pack(anchor='w',padx=28,pady=(0,12))
  reconnect=ctk.BooleanVar(value=app.args.auto_reconnect)
  ctk.CTkSwitch(dialog,text='Reconnect automatically',variable=reconnect,progress_color=BLUE,font=('Segoe UI',12)).pack(anchor='w',padx=28,pady=(0,14))
  manual=ctk.BooleanVar(value=app.args.connect_only)
  ctk.CTkSwitch(dialog,text='ELF already loaded in Payload Manager',variable=manual,progress_color=BLUE,font=('Segoe UI',12)).pack(anchor='w',padx=28)
  ctk.CTkLabel(dialog,text='Off: PlayBridge uploads the ELF automatically.\nOn: load PlayBridge.elf, then connect within 60 seconds.',font=('Segoe UI',12),text_color=MUTED,justify='left').pack(anchor='w',padx=28,pady=(12,10))
  ctk.CTkSwitch(dialog,text='Show performance stats',variable=diagnostic,progress_color=BLUE,font=('Segoe UI',12),command=lambda:core.save_config(diagnostic=diagnostic.get())).pack(anchor='w',padx=28,pady=(0,10))
  def choose_capture_folder():
   from tkinter import filedialog
   folder=filedialog.askdirectory(parent=dialog,title='Choose capture folder',initialdir=str(app.capture_folder()))
   if folder:core.save_config(capture_folder=folder);app.notify('Capture folder updated.')
  ctk.CTkButton(dialog,text='Choose capture folder',command=choose_capture_folder,fg_color=CARD,hover_color='#1D3D66',height=34).pack(fill='x',padx=28,pady=(0,8))
  error=ctk.CTkLabel(dialog,text='',text_color='#FF9C9C',font=('Segoe UI',12));error.pack(anchor='w',padx=28)
  def save():
   try:ipaddress.IPv4Address(host.get().strip())
   except ValueError:error.configure(text='Enter a valid IPv4 address.');return
   app.args.host=host.get().strip();app.args.connect_only=manual.get();app.args.profile=profiles[profile.get()];app.args.auto_reconnect=reconnect.get();core.save_config(host=app.args.host,connect_only=app.args.connect_only,profile=app.args.profile,auto_reconnect=app.args.auto_reconnect);host_label.configure(text=app.args.host);dialog.destroy()
  ctk.CTkButton(dialog,text='Save changes',command=save,height=42,corner_radius=21,fg_color=BLUE,hover_color=HOVER,text_color='white',font=('Segoe UI',13,'bold')).pack(fill='x',padx=28,pady=(0,22))
 settings_button=ctk.CTkButton(head,text='',image=icons['settings'],command=settings,width=36,height=36,corner_radius=18,fg_color=CARD,hover_color='#2B2F3D',font=('Segoe UI',18,'bold'));settings_button.grid(row=0,column=8)
 Tooltip(screenshot_button,'Screenshot · F8');Tooltip(record_button,'Start / stop recording · F9');Tooltip(captures_button,'Open capture folder')
 Tooltip(settings_button,'Connection settings');Tooltip(full_button,'Fullscreen · F11');Tooltip(mute_button,'Mute / unmute');Tooltip(output,'Audio output');Tooltip(volume,'Volume')
 bottom=ctk.CTkFrame(win,fg_color='transparent');bottom.grid(row=3,column=0,sticky='ew',padx=26,pady=(0,9));bottom.grid_columnconfigure(0,weight=1)
 message=ctk.CTkLabel(bottom,text='',text_color=MUTED,font=('Segoe UI',10),anchor='w',height=16);message.grid(row=0,column=0,sticky='ew')
 diagnostic=ctk.BooleanVar(value=core.config().get('diagnostic',False))
 presenter=None
 if app.renderer=='gdi':
  from gdi_presenter import GdiPresenter
  presenter=GdiPresenter(canvas)
 fullscreen=False;photo=None;photo_size=None;rate_at=time.perf_counter();rate_frames=0;fps=0;last_info=0
 def full():
  nonlocal fullscreen
  fullscreen=not fullscreen
  if fullscreen:
   for widget in (head,footer,bottom):widget.grid_remove()
   stage.grid_configure(padx=0,pady=0);canvas.grid_configure(padx=0,pady=0);stage.configure(corner_radius=0)
  else:
   for widget in (head,footer,bottom):widget.grid()
   stage.grid_configure(padx=18);canvas.grid_configure(padx=5,pady=5);stage.configure(corner_radius=10)
  win.attributes('-fullscreen',fullscreen)
 full_button.configure(command=full)
 def close():app.stop.set();win.destroy()
 def escape(_):
  if fullscreen:full()
 win.protocol('WM_DELETE_WINDOW',close);win.bind('<Escape>',escape);win.bind('<F11>',lambda _:full());win.bind('<F8>',lambda _:app.take_screenshot());win.bind('<F9>',lambda _:app.toggle_recording());canvas.bind('<Double-Button-1>',lambda _:full())
 def tick():
  nonlocal photo,photo_size,rate_at,rate_frames,fps,last_info
  if app.stop.is_set():close();return
  now=time.perf_counter()
  if app.args.seconds and now-app.started>=app.args.seconds:close();return
  win.update_idletasks();vw=max(1,canvas.winfo_width());vh=max(1,canvas.winfo_height());app.render_size=(vw,vh);canvas.coords(item_id,vw//2,vh//2);canvas.coords(placeholder,vw//2,vh//2)
  with app.lock:item=app.ready_image;app.ready_image=None;queue_ms=len(app.pcm)/192
  if item and (item[0].width>vw or item[0].height>vh):item=None
  if item:
   canvas.itemconfigure(placeholder,state='hidden');image,arrived,prepared=item;paint_at=time.perf_counter();app.timings.add('prepared_slot_wait_ms',(paint_at-prepared)*1000)
   if presenter:presenter.draw(image)
   elif photo is None or photo_size!=image.size:
    photo=ImageTk.PhotoImage(image);photo_size=image.size;canvas.itemconfigure(item_id,image=photo);canvas.image=photo
   else:photo.paste(image)
   app.timings.add('presenter_upload_ms',(time.perf_counter()-paint_at)*1000);app.timings.add('receive_to_present_ms',(time.perf_counter()-arrived)*1000);app.stats['video_presented']+=1;app.stats['last_frame_to_ui_ms']=round((time.perf_counter()-arrived)*1000,1);rate_frames+=1
  elif presenter:presenter.refresh()
  if now-rate_at>=1:
   fps=rate_frames/(now-rate_at);app.stats['presented_fps']=round(fps,1);rate_frames=0;rate_at=now;app.snapshot()
  if now-last_info>.25:
   last_info=now;app.poll_capture_events();record_button.configure(image=icons['disconnect'] if app.recorder.active else icons['record'],fg_color='#722637' if app.recorder.active else CARD);active=app.worker.is_alive();linked=app.connection_state=='Connected' and active
   connect_button.configure(text='Disconnect' if active else 'Connect',image=icons['disconnect'] if active else icons['connect'])
   pill.configure(text='●  LIVE' if linked else '●  Reconnecting' if active and app.connection_state.startswith('Reconnecting') else '●  Connecting' if active else '●  Offline',text_color='#8AD8FF' if linked else BLUE,fg_color='transparent')
   info=app.error or ('1080p  ·  Stereo' if linked else 'Ready to connect')
   if linked:
    confirmed=app.capture_info and app.capture_info.get('confirmed');info+='  ·  '+(str(app.capture_info.get('fps_target'))+' fps target / '+str(app.capture_info.get('bitrate_target',0)//1000000)+' Mbps' if confirmed else 'Legacy payload: quality profile not confirmed')
   if core.PROFILES[app.args.profile].get('playback_fps'):info+='  ·  30 fps PC playback'
   if app.recorder.active:info+='  ·  '+('REC' if app.recorder.state=='recording' else 'Recording: '+app.recorder.state)
   if now<app.notice_until:info=app.notice
   if diagnostic.get():info+=f'   |   {fps:.0f} fps · PC {app.stats["last_frame_to_ui_ms"]:.1f} ms · audio queue {queue_ms:.0f} ms'
   message.configure(text=info,text_color='#FFAAA5' if app.error else MUTED)
  win.after(1,tick)
 win.after(5,tick);win.mainloop()
