"""PlayBridge's session panel and the Media page."""
import os, queue, threading, time
from collections import deque
from datetime import datetime
import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk
from desktop_features import capture_items, format_bytes, clock_text, video_thumbnail
from luxury_theme import Bezel, LuxButton, heading, local_image, thin_scrollbar, tint, BG, CARD, GOLD as ACCENT, GOLD_SOFT, LINE, MUTED, RAISED, TEXT
from scene import ring_gauge

def with_play_mark(image):
    """A small white play mark, so a recording's still does not read as a photo."""
    mark=Image.new('RGBA',(160,160));draw=ImageDraw.Draw(mark)
    draw.ellipse((0,0,159,159),fill=(0,0,0,170),outline=TEXT,width=5);draw.polygon(((62,44),(62,116),(118,80)),fill=TEXT)
    mark=mark.reduce(4);image=image.copy();image.paste(mark,((image.width-40)//2,(image.height-40)//2),mark)
    return image

class PerformanceDock(ctk.CTkScrollableFrame):
    def __init__(self, parent, export, console=()):
        super().__init__(parent, width=242, fg_color=BG, corner_radius=0);thin_scrollbar(self)
        self.history=deque(maxlen=60); self.last_sample=0; self.rings={}; self.ring_side=round(112*ctk.ScalingTracker.get_widget_scaling(parent))
        heading(self,'Session',22).pack(anchor='w',padx=14,pady=(10,8))
        self.values={}
        card=Bezel(self,fill=CARD,outer=BG,radius=14);card.pack(fill='x',padx=8,pady=(0,9))
        self.ring=tk.Label(card.body,bg=CARD,bd=0);self.ring.pack(pady=(12,6));self.show_ring(None)
        for key,title in (('resolution','Source'),('latency','PC pipeline')):
            row=tk.Frame(card.body,bg=CARD);row.pack(fill='x',padx=14,pady=(0,4))
            ctk.CTkLabel(row,text=title,text_color=MUTED,font=('Segoe UI',11),height=20).pack(side='left')
            value=ctk.CTkLabel(row,text='—',text_color=TEXT,font=('Segoe UI',11,'bold'),height=20);value.pack(side='right');self.values[key]=value
        tk.Frame(card.body,bg=CARD,height=6).pack()
        card=Bezel(self,fill=CARD,outer=BG,radius=14);card.pack(fill='x',padx=8,pady=(0,9))
        ctk.CTkLabel(card.body,text='Console',text_color=MUTED,font=('Segoe UI',11)).pack(anchor='w',padx=14,pady=(10,0))
        self.console_game=ctk.CTkLabel(card.body,text='Not connected',text_color=TEXT,font=('Segoe UI Semilight',16),wraplength=200,justify='left');self.console_game.pack(anchor='w',padx=14)
        self.console_line=ctk.CTkLabel(card.body,text='',text_color=MUTED,font=('Segoe UI',10),wraplength=200,justify='left');self.console_line.pack(anchor='w',padx=14,pady=(0,6))
        actions=tk.Frame(card.body,bg=CARD);actions.pack(fill='x',padx=8,pady=(0,8));actions.grid_columnconfigure((0,1),weight=1,uniform='actions')
        for index,(label,command) in enumerate(console):
            LuxButton(actions,label,command,height=28,radius=14,text_size=10,behind=CARD).grid(row=index//2,column=index%2,sticky='ew',padx=2,pady=2)
        self.rate=ctk.CTkLabel(self,text='Received  ·  —',text_color=TEXT,font=('Segoe UI',11));self.rate.pack(anchor='w',padx=14,pady=(8,0))
        self.graph=tk.Canvas(self,height=65,bg=BG,highlightthickness=0);self.graph.pack(fill='x',padx=14,pady=(6,0))
        ctk.CTkLabel(self,text='Last 60 seconds · media payload',text_color=MUTED,font=('Segoe UI',9)).pack(anchor='w',padx=14)
        self.details=ctk.CTkLabel(self,text='',text_color=MUTED,font=('Segoe UI',11),justify='left',anchor='w');self.details.pack(fill='x',padx=14,pady=(16,10))
        LuxButton(self,'Export diagnostics',export,height=34,radius=17,behind=BG).pack(fill='x',padx=8,pady=(4,16))
    def show_ring(self, fps):
        """Each reading is drawn once and kept, so the gauge costs the video nothing."""
        key=None if fps is None else min(240,round(fps))
        if key not in self.rings:
            self.rings[key]=ImageTk.PhotoImage(ring_gauge(self.ring_side,0 if key is None else key/60,'—' if key is None else str(key),'FPS'),master=self)
        self.ring.configure(image=self.rings[key])
    def update_session(self, app, health, fps, queue_ms, linked, now, recording_elapsed=None):
        self.values['resolution'].configure(text=f"{health['decoded_width']} × {health['decoded_height']}" if linked and health['decoded_width'] else 'Awaiting video')
        self.show_ring(fps if linked else None)
        self.values['latency'].configure(text=f"{app.stats['last_frame_to_ui_ms']:.1f} ms" if linked and app.stats.get('video_presented') else '—')
        rate=health.get('received_mbps') if linked else None
        self.rate.configure(text=f'Received  ·  {rate:.1f} Mbps' if rate is not None else 'Received  ·  —')
        if now-self.last_sample>=1:
            if self.last_sample:
                for _ in range(min(59,max(0,int(now-self.last_sample)-1))):self.history.append(None)
            self.last_sample=now;self.history.append(rate);self.draw_graph()
        recording=('Recording  '+clock_text(recording_elapsed)) if recording_elapsed is not None else 'Recorder  '+app.recorder.state.capitalize()
        self.details.configure(text='App session  '+clock_text(now-app.started)+'\nAudio buffer  '+(f'{queue_ms:.0f} ms' if linked else '—')+'\nReceived  '+format_bytes(app.stats.get('received_bytes',0))+'\n'+recording)
    def update_console(self, game, line):
        if self.console_game.cget('text')!=game:self.console_game.configure(text=game)
        if self.console_line.cget('text')!=line:self.console_line.configure(text=line)
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
            if (len(values)-1-i)%10==0:c.create_oval(x-3,y-3,x+3,y+3,fill=GOLD_SOFT,outline='')
        if len(segment)>=4:c.create_line(*segment,fill=ACCENT,width=2)
        elif segment:c.create_oval(segment[0]-2,segment[1]-2,segment[0]+2,segment[1]+2,fill=ACCENT,outline='')

class CaptureLibrary:
    """The Media page: this PC's screenshots and recordings, in the same cards as the rest of the app."""
    MARGIN=52
    def __init__(self, parent, app):
        self.parent=parent;self.app=app;self.page=None;self.generation=0;self.number=0;self.items=[];self.images=[];self.thumbnails={}
    def build(self):
        page=tk.Frame(self.parent,bg=BG);self.page=page;page.grid_columnconfigure(0,weight=1);page.grid_rowconfigure(2,weight=1)
        head=tk.Frame(page,bg=BG);head.grid(row=0,column=0,sticky='ew',padx=self.MARGIN,pady=(8,10));head.grid_columnconfigure(0,weight=1)
        heading(head,'Your captures',34).grid(row=0,column=0,sticky='w')
        ctk.CTkLabel(head,text='Screenshots and recordings on this PC. F8 takes a screenshot, F9 starts or stops a recording.',font=('Segoe UI',12),text_color=MUTED).grid(row=1,column=0,sticky='w')
        LuxButton(head,'Open folder',self.app.open_captures,width=120,height=36,radius=18,behind=BG).grid(row=0,column=1,rowspan=2)
        bar=tk.Frame(page,bg=BG);bar.grid(row=1,column=0,sticky='ew',padx=self.MARGIN,pady=(0,10));bar.grid_columnconfigure(1,weight=1)
        self.filter=ctk.StringVar(value='All')
        filters=tk.Frame(bar,bg=BG);filters.grid(row=0,column=0);self.filter_buttons={}
        for column,label in enumerate(('All','Photos','Videos')):
            self.filter_buttons[label]=LuxButton(filters,label,lambda value=label:self.choose_filter(value),width=84,height=34,radius=17,text_size=13,behind=BG,tone='ghost',selected=label=='All');self.filter_buttons[label].grid(row=0,column=column,padx=(0,6))
        LuxButton(bar,'Refresh',self.refresh,width=96,height=34,radius=17,behind=BG).grid(row=0,column=2)
        self.grid=ctk.CTkScrollableFrame(page,fg_color=BG);thin_scrollbar(self.grid);self.grid.grid(row=2,column=0,sticky='nsew',padx=self.MARGIN-8)
        foot=tk.Frame(page,bg=BG);foot.grid(row=3,column=0,sticky='ew',padx=self.MARGIN,pady=10);foot.grid_columnconfigure(0,weight=1)
        self.status=ctk.CTkLabel(foot,text='Reading your captures…',text_color=MUTED,font=('Segoe UI',11));self.status.grid(row=0,column=0,sticky='w')
        self.back=LuxButton(foot,'Previous',lambda:self.move(-1),width=92,height=34,radius=17,behind=BG);self.back.grid(row=0,column=1,padx=6)
        self.next=LuxButton(foot,'Next',lambda:self.move(1),width=92,height=34,radius=17,behind=BG);self.next.grid(row=0,column=2)
    def open(self):
        """Called as the page comes up. Reading the folder happens on its own thread."""
        if self.page is None:self.build()
        self.refresh()
    def hide(self):
        self.generation+=1
    def choose_filter(self,value):
        self.filter.set(value)
        for label,button in self.filter_buttons.items():button.restyle(selected=label==value)
        self.refresh()
    def refresh(self):
        self.number=0;self.load(True)
    def move(self,delta):
        self.number=max(0,self.number+delta);self.load(False)
    def load(self,refresh):
        self.generation+=1;generation=self.generation;result=queue.Queue();kind=self.filter.get();page=self.number
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
            if generation!=self.generation:return
            try:items,thumbs,error=result.get_nowait()
            except queue.Empty:self.page.after(60,finish);return
            self.items=items;self.render(thumbs,error)
        self.page.after(60,finish)
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
        self.images=[];page_items=self.items[self.number*12:(self.number+1)*12]
        factor=ctk.ScalingTracker.get_widget_scaling(self.page);room=max(600,self.page.winfo_width()/factor-2*self.MARGIN);columns=4 if room>=1100 else 3;art_width=min(340,int(room/columns)-34)
        for column in range(4):self.grid.grid_columnconfigure(column,weight=1 if column<columns else 0,uniform='cards' if column<columns else '')
        if not page_items:
            empty=Bezel(self.grid,fill=CARD,outer=BG,radius=14);empty.grid(row=0,column=0,columnspan=columns,sticky='ew',padx=6,pady=24)
            trophy=local_image('trophy.png')
            if trophy is not None:
                art=ctk.CTkImage(tint(trophy,TEXT),size=(72,72));self.images.append(art);ctk.CTkLabel(empty.body,text='',image=art).pack(pady=(30,10))
            heading(empty.body,'Make a moment worth keeping',24).pack(pady=(24,8))
            ctk.CTkLabel(empty.body,text='F8 takes a screenshot. F9 starts or stops a recording.\nYour captures will appear here.',text_color=MUTED,font=('Segoe UI',12)).pack(pady=(0,35))
        for i,(item,image) in enumerate(zip(page_items,thumbs)):
            card=Bezel(self.grid,fill=CARD,outer=BG,radius=14);card.grid(row=i//columns,column=i%columns,sticky='nsew',padx=6,pady=7)
            if image is None:
                image=Image.new('RGB',(300,170),RAISED);d=ImageDraw.Draw(image);d.rounded_rectangle((116,50,184,120),12,outline=MUTED,width=2);d.polygon(((143,70),(143,102),(166,86)),fill=TEXT)
            art=ctk.CTkImage(image,size=(art_width,round(art_width*9/16)));self.images.append(art)
            ctk.CTkButton(card.body,text='',image=art,command=lambda p=item.path:self.launch(p),height=round(art_width*9/16)+6,fg_color='transparent',hover_color=RAISED,corner_radius=8).pack(fill='x',padx=2,pady=(2,0))
            when=datetime.fromtimestamp(item.modified).strftime('%d %b %Y · %H:%M')
            ctk.CTkLabel(card.body,text=when,text_color=TEXT,font=('Segoe UI',12),height=20).pack(anchor='w',padx=14,pady=(8,0))
            ctk.CTkLabel(card.body,text=('PNG' if item.kind=='Photos' else 'MP4')+'  ·  '+format_bytes(item.size),text_color=MUTED,font=('Segoe UI',10),height=18).pack(anchor='w',padx=14,pady=(0,4))
            LuxButton(card.body,'Open photo' if item.kind=='Photos' else 'Play recording',lambda p=item.path:self.launch(p),height=30,radius=15,behind=CARD).pack(fill='x',padx=8,pady=(4,8))
        pages=max(1,(len(self.items)+11)//12)
        self.status.configure(text=error or f'{len(self.items)} recent captures · Page {self.number+1} of {pages}')
        self.back.restyle(enabled=bool(self.number));self.next.restyle(enabled=self.number+1<pages)
    def launch(self,path):
        try:os.startfile(str(path))
        except OSError:self.status.configure(text='Unable to open this capture. Check its default app.')
