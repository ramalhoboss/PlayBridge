"""PlayBridge performance dock and local capture library."""
import os, queue, threading, time
from collections import deque
from datetime import datetime
import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageDraw
from desktop_features import capture_items, format_bytes, clock_text, video_thumbnail
from luxury_theme import Bezel, LuxButton, gold_label, gold_title_bar, local_image, fade_in, thin_scrollbar, tint, BG, CARD, GOLD as ACCENT, GOLD_SOFT, LINE, MUTED, PANEL, RAISED, TEXT

def with_play_mark(image):
    """A small gold play mark, so a recording's still does not read as a photo."""
    mark=Image.new('RGBA',(160,160));draw=ImageDraw.Draw(mark)
    draw.ellipse((0,0,159,159),fill=(0,0,0,170),outline=ACCENT,width=5);draw.polygon(((62,44),(62,116),(118,80)),fill=ACCENT)
    mark=mark.reduce(4);image=image.copy();image.paste(mark,((image.width-40)//2,(image.height-40)//2),mark)
    return image

class PerformanceDock(ctk.CTkScrollableFrame):
    def __init__(self, parent, export):
        super().__init__(parent, width=242, fg_color=PANEL, corner_radius=0);thin_scrollbar(self)
        self.history=deque(maxlen=60); self.last_sample=0
        ctk.CTkLabel(self,text='SESSION CONTROL',text_color=ACCENT,font=('Segoe UI',10,'bold')).pack(anchor='w',padx=16,pady=(20,6))
        gold_label(self,'In the moment.',22).pack(anchor='w',padx=16,pady=(0,18))
        self.values={}
        for key,title,hint in (('resolution','SOURCE','Decoded video dimensions'),('fps','PLAYBACK','Frames presented per second'),('latency','PC PIPELINE','Receive to presentation · PC only')):
            card=Bezel(self,fill=CARD,outer=PANEL,radius=12);card.pack(fill='x',padx=12,pady=(0,9))
            ctk.CTkLabel(card.body,text=title,text_color=MUTED,font=('Segoe UI',9,'bold')).pack(anchor='w',padx=14,pady=(10,0))
            value=ctk.CTkLabel(card.body,text='—',text_color=TEXT,font=('Segoe UI',22,'bold'));value.pack(anchor='w',padx=14)
            ctk.CTkLabel(card.body,text=hint,text_color=MUTED,font=('Segoe UI',9)).pack(anchor='w',padx=14,pady=(0,10));self.values[key]=value
        self.rate=ctk.CTkLabel(self,text='RECEIVED BITRATE  ·  —',text_color=ACCENT,font=('Segoe UI',10,'bold'));self.rate.pack(anchor='w',padx=16,pady=(8,0))
        self.graph=tk.Canvas(self,height=65,bg=PANEL,highlightthickness=0);self.graph.pack(fill='x',padx=16,pady=(6,0))
        ctk.CTkLabel(self,text='Last 60 seconds · media payload',text_color=MUTED,font=('Segoe UI',9)).pack(anchor='w',padx=16)
        self.details=ctk.CTkLabel(self,text='',text_color=MUTED,font=('Segoe UI',11),justify='left',anchor='w');self.details.pack(fill='x',padx=16,pady=(16,10))
        LuxButton(self,'Export diagnostics',export,height=34,radius=10).pack(fill='x',padx=12,pady=(4,16))
    def update_session(self, app, health, fps, queue_ms, linked, now, recording_elapsed=None):
        self.values['resolution'].configure(text=f"{health['decoded_width']} × {health['decoded_height']}" if linked and health['decoded_width'] else 'Awaiting video')
        self.values['fps'].configure(text=f'{fps:.0f} fps' if linked else '—')
        self.values['latency'].configure(text=f"{app.stats['last_frame_to_ui_ms']:.1f} ms" if linked and app.stats.get('video_presented') else '—')
        rate=health.get('received_mbps') if linked else None
        self.rate.configure(text=f'RECEIVED BITRATE  ·  {rate:.1f} Mbps' if rate is not None else 'RECEIVED BITRATE  ·  —')
        if now-self.last_sample>=1:
            if self.last_sample:
                for _ in range(min(59,max(0,int(now-self.last_sample)-1))):self.history.append(None)
            self.last_sample=now;self.history.append(rate);self.draw_graph()
        recording=('Recording  '+clock_text(recording_elapsed)) if recording_elapsed is not None else 'Recorder  '+app.recorder.state.capitalize()
        self.details.configure(text='App session  '+clock_text(now-app.started)+'\nAudio buffer  '+(f'{queue_ms:.0f} ms' if linked else '—')+'\nReceived  '+format_bytes(app.stats.get('received_bytes',0))+'\n'+recording)
    def draw_graph(self):
        c=self.graph;c.delete('all');w=max(1,c.winfo_width());h=60
        for y in (8,30,54):c.create_line(0,y,w,y,fill=LINE)
        values=list(self.history);ceiling=max(1,max((v for v in values if v is not None),default=1)*1.15)
        segment=[]
        for i,value in enumerate(values):
            if value is None:
                if len(segment)>=4:c.create_line(*segment,fill=ACCENT,width=2)
                segment=[];continue
            x=w*(60-len(values)+i)/59;y=54-value/ceiling*46;segment.extend((x,y))
        if len(segment)>=4:c.create_line(*segment,fill=ACCENT,width=2)
        elif segment:c.create_oval(segment[0]-2,segment[1]-2,segment[0]+2,segment[1]+2,fill=ACCENT,outline='')

class CaptureLibrary:
    def __init__(self, parent, app, animations=True):
        self.parent=parent;self.app=app;self.window=None;self.generation=0;self.page=0;self.items=[];self.images=[];self.animations=animations;self.thumbnails={}
    def open(self):
        if self.window is not None and self.window.winfo_exists():self.window.lift();self.window.focus();return
        win=ctk.CTkToplevel(self.parent);self.window=win;win.title('PlayBridge · Capture library');win.configure(fg_color=BG);win.transient(self.parent);gold_title_bar(win)
        w=min(1040,win.winfo_screenwidth()-80);h=min(800,win.winfo_screenheight()-120)
        win.geometry(f'{w}x{h}+{max(20,(win.winfo_screenwidth()-w)//2)}+40');win.minsize(760,540);win.grid_columnconfigure(0,weight=1);win.grid_rowconfigure(2,weight=1)
        fade_in(win,self.animations)
        head=ctk.CTkFrame(win,fg_color='transparent');head.grid(row=0,column=0,sticky='ew',padx=28,pady=(24,16));head.grid_columnconfigure(0,weight=1)
        gold_label(head,'Your best moments.',27).grid(row=0,column=0,sticky='w')
        ctk.CTkLabel(head,text='Native screenshots. Original stream recordings.',font=('Segoe UI',12),text_color=MUTED).grid(row=1,column=0,sticky='w',pady=(3,0))
        LuxButton(head,'Open folder',self.app.open_captures,width=110,height=32,radius=9,behind=BG).grid(row=0,column=1,rowspan=2)
        bar=ctk.CTkFrame(win,fg_color='transparent');bar.grid(row=1,column=0,sticky='ew',padx=28,pady=(0,12));bar.grid_columnconfigure(1,weight=1)
        self.filter=ctk.StringVar(value='All')
        filters=ctk.CTkFrame(bar,fg_color='transparent');filters.grid(row=0,column=0);self.filter_buttons={}
        for column,label in enumerate(('All','Photos','Videos')):
            self.filter_buttons[label]=LuxButton(filters,label,lambda value=label:self.choose_filter(value),width=72,height=32,radius=9,behind=BG,tone='ghost',selected=label=='All');self.filter_buttons[label].grid(row=0,column=column,padx=(0,6))
        LuxButton(bar,'Refresh',self.refresh,width=85,height=32,radius=9,behind=BG).grid(row=0,column=2)
        self.grid=ctk.CTkScrollableFrame(win,fg_color=BG);thin_scrollbar(self.grid);self.grid.grid(row=2,column=0,sticky='nsew',padx=22);self.grid.grid_columnconfigure((0,1,2),weight=1,uniform='cards')
        foot=ctk.CTkFrame(win,fg_color='transparent');foot.grid(row=3,column=0,sticky='ew',padx=28,pady=16);foot.grid_columnconfigure(0,weight=1)
        self.status=ctk.CTkLabel(foot,text='Reading your captures…',text_color=MUTED,font=('Segoe UI',11));self.status.grid(row=0,column=0,sticky='w')
        self.back=LuxButton(foot,'Previous',lambda:self.move(-1),width=85,height=32,radius=9,behind=BG);self.back.grid(row=0,column=1,padx=6)
        self.next=LuxButton(foot,'Next',lambda:self.move(1),width=85,height=32,radius=9,behind=BG);self.next.grid(row=0,column=2)
        def close():self.generation+=1;win.destroy();self.window=None
        win.protocol('WM_DELETE_WINDOW',close);self.refresh()
    def choose_filter(self,value):
        self.filter.set(value)
        for label,button in self.filter_buttons.items():button.restyle(selected=label==value)
        self.refresh()
    def refresh(self):
        self.page=0;self.load(True)
    def move(self,delta):
        self.page=max(0,self.page+delta);self.load(False)
    def load(self,refresh):
        if not self.window or not self.window.winfo_exists():return
        self.generation+=1;generation=self.generation;result=queue.Queue();kind=self.filter.get();page=self.page
        try:folder=self.app.capture_folder()
        except OSError:self.status.configure(text='Unable to read the capture folder.');return
        self.status.configure(text='Loading captures…');self.back.restyle(enabled=False);self.next.restyle(enabled=False)
        previous=list(self.items)
        def work():
            try:
                items=capture_items(folder,kind) if refresh else previous
                thumbs=[]
                for item in items[page*12:(page+1)*12]:
                    key=(item.path,item.modified)
                    image=self.thumbnails.get(key)
                    if image is None:
                        image=self.thumbnail(item)
                        if len(self.thumbnails)>=240:self.thumbnails.clear()
                        self.thumbnails[key]=image
                    thumbs.append(image)
                result.put((items,thumbs,None))
            except Exception:result.put(([],[], 'Unable to read the capture folder.'))
        threading.Thread(target=work,name='Capture library',daemon=True).start()
        def finish():
            if not self.window or not self.window.winfo_exists() or generation!=self.generation:return
            try:items,thumbs,error=result.get_nowait()
            except queue.Empty:self.window.after(60,finish);return
            self.items=items;self.render(thumbs,error)
        self.window.after(60,finish)
    def thumbnail(self,item):
        if item.kind=='Videos':
            still=video_thumbnail(item.path)
            return with_play_mark(still) if still is not None else None
        try:
            with Image.open(item.path) as source:
                source.thumbnail((300,170));return source.convert('RGB').copy()
        except (OSError,ValueError,Image.DecompressionBombError):return None
    def render(self,thumbs,error):
        for widget in self.grid.winfo_children():widget.destroy()
        self.images=[];page_items=self.items[self.page*12:(self.page+1)*12]
        if not page_items:
            empty=Bezel(self.grid,fill=CARD,outer=BG);empty.grid(row=0,column=0,columnspan=3,sticky='ew',padx=6,pady=24)
            trophy=local_image('trophy.png')
            if trophy is not None:
                art=ctk.CTkImage(tint(trophy,ACCENT),size=(72,72));self.images.append(art);ctk.CTkLabel(empty.body,text='',image=art).pack(pady=(30,10))
            gold_label(empty.body,'Make a moment worth keeping.',20).pack(pady=(24,8))
            ctk.CTkLabel(empty.body,text='F8 takes a screenshot. F9 starts or stops a recording.\nYour captures will appear here.',text_color=MUTED,font=('Segoe UI',12)).pack(pady=(0,35))
        for i,(item,image) in enumerate(zip(page_items,thumbs)):
            card=Bezel(self.grid,fill=CARD,outer=BG,radius=12);card.grid(row=i//3,column=i%3,sticky='nsew',padx=6,pady=7)
            if image is None:
                image=Image.new('RGB',(300,170),RAISED);d=ImageDraw.Draw(image);d.rounded_rectangle((116,50,184,120),12,outline=ACCENT,width=2);d.polygon(((143,70),(143,102),(166,86)),fill=GOLD_SOFT)
            art=ctk.CTkImage(image,size=(210,119));self.images.append(art)
            ctk.CTkButton(card.body,text='',image=art,command=lambda p=item.path:self.launch(p),height=125,fg_color='transparent',hover_color=RAISED,corner_radius=8).pack(fill='x',padx=2,pady=(2,0))
            when=datetime.fromtimestamp(item.modified).strftime('%d %b %Y · %H:%M')
            ctk.CTkLabel(card.body,text=when,text_color=TEXT,font=('Segoe UI',11,'bold')).pack(anchor='w',padx=14,pady=(8,0))
            ctk.CTkLabel(card.body,text=('PNG' if item.kind=='Photos' else 'MP4')+'  ·  '+format_bytes(item.size),text_color=MUTED,font=('Segoe UI',10)).pack(anchor='w',padx=14,pady=(0,4))
            LuxButton(card.body,'Open photo' if item.kind=='Photos' else 'Play recording',lambda p=item.path:self.launch(p),height=29,radius=9,behind=CARD).pack(fill='x',padx=6,pady=(4,6))
        pages=max(1,(len(self.items)+11)//12)
        self.status.configure(text=error or f'{len(self.items)} recent captures · Page {self.page+1} of {pages}')
        self.back.restyle(enabled=bool(self.page));self.next.restyle(enabled=self.page+1<pages)
    def launch(self,path):
        try:os.startfile(str(path))
        except OSError:self.status.configure(text='Unable to open this capture. Check its default app.')

