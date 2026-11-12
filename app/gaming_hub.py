"""PlayBridge's session panel and the Media page."""
import os, queue, threading, time
from collections import deque
from datetime import datetime
import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk
from desktop_features import capture_items, format_bytes, clock_text, video_thumbnail
from luxury_theme import Bezel, LuxButton, dark_title_bar, heading, local_image, thin_scrollbar, tint, BG, CARD, GOLD as ACCENT, GOLD_SOFT, LINE, MUTED, RAISED, TEXT
from scene import ring_gauge
from settings_look import GlassBoard

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
        self.console_line=ctk.CTkLabel(card.body,text='',text_color=MUTED,font=('Segoe UI',11),wraplength=200,justify='left');self.console_line.pack(anchor='w',padx=14,pady=(0,6))
        actions=tk.Frame(card.body,bg=CARD);actions.pack(fill='x',padx=8,pady=(0,8));actions.grid_columnconfigure((0,1),weight=1,uniform='actions')
        for index,(label,command) in enumerate(console):
            LuxButton(actions,label,command,height=28,radius=14,text_size=10,behind=CARD).grid(row=index//2,column=index%2,sticky='ew',padx=2,pady=2)
        self.rate=ctk.CTkLabel(self,text='Received  ·  —',text_color=TEXT,font=('Segoe UI',11));self.rate.pack(anchor='w',padx=14,pady=(8,0))
        self.graph=tk.Canvas(self,height=65,bg=BG,highlightthickness=0);self.graph.pack(fill='x',padx=14,pady=(6,0))
        ctk.CTkLabel(self,text='Last 60 seconds · media payload',text_color=MUTED,font=('Segoe UI',11)).pack(anchor='w',padx=14)
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
    """The Media page: this PC's screenshots and recordings, on panels over the art of the game played last."""
    def __init__(self, parent, app):
        self.parent=parent;self.app=app;self.page=None;self.board=None;self.generation=0;self.number=0;self.items=[];self.images=[];self.thumbnails={};self.last=None
    def build(self):
        board=GlassBoard(self.parent,'Your captures','Screenshots and recordings on this PC. F8 takes a screenshot, F9 starts or stops a recording.');self.page=self.board=board;scenery=board.scenery
        board.add(LuxButton(scenery,'From your PS5',self.open_console,width=170,height=44,radius=22,text_size=15,behind=BG,tone='main'),'top')
        board.add(LuxButton(scenery,'Open folder',self.app.open_captures,width=140,height=44,radius=22,text_size=15,behind=BG),'top')
        self.filter=ctk.StringVar(value='All');self.filter_buttons={}
        for label in ('All','Photos','Videos'):
            self.filter_buttons[label]=board.add(LuxButton(scenery,label,lambda value=label:self.choose_filter(value),width=100,height=40,radius=20,text_size=15,behind=BG,tone='ghost',selected=label=='All'),'left')
        board.add(LuxButton(scenery,'Refresh',self.refresh,width=116,height=40,radius=20,text_size=15,behind=BG),'right')
        self.back=board.add(LuxButton(scenery,'Previous',lambda:self.move(-1),width=116,height=40,radius=20,text_size=15,behind=BG),'foot')
        self.next=board.add(LuxButton(scenery,'Next',lambda:self.move(1),width=116,height=40,radius=20,text_size=15,behind=BG),'foot')
        board.status('Reading your captures…');board.resized=self.rerender
    def open(self):
        """Called as the page comes up. Reading the folder happens on its own thread."""
        if self.page is None:self.build()
        self.board.refresh();self.refresh()
    def hide(self):
        self.generation+=1
    def choose_filter(self,value):
        self.filter.set(value)
        for label,button in self.filter_buttons.items():button.restyle(selected=label==value)
        self.refresh()
    def refresh(self):
        self.number=0;self.load(True)
    def open_console(self):
        ConsoleCaptures(self.page.winfo_toplevel(),self.app,self.refresh)
    def move(self,delta):
        self.number=max(0,self.number+delta);self.load(False)
    def load(self,refresh):
        self.generation+=1;generation=self.generation;result=queue.Queue();kind=self.filter.get();page=self.number
        try:folder=self.app.capture_folder()
        except OSError:self.board.status('Unable to read the capture folder.');return
        self.board.status('Loading captures…');self.back.restyle(enabled=False);self.next.restyle(enabled=False)
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
    def rerender(self):
        """The window changed how many panels fit across: the same page again, at the new size."""
        if self.last is not None:self.render(*self.last)
        else:self.board.layout()
    def render(self,thumbs,error):
        board=self.board;self.last=(thumbs,error);board.clear();self.images=[];page_items=self.items[self.number*12:(self.number+1)*12]
        _,column=board.grid_size();art_width=max(160,int(column/board.factor)-24)
        if not page_items:
            empty=board.card(span=True)
            trophy=local_image('trophy.png')
            if trophy is not None:
                art=ctk.CTkImage(tint(trophy,TEXT),size=(80,80));self.images.append(art);ctk.CTkLabel(empty,text='',image=art).pack(pady=(34,10))
            heading(empty,'Make a moment worth keeping',30).pack(pady=(28,8))
            ctk.CTkLabel(empty,text='F8 takes a screenshot. F9 starts or stops a recording.\nYour captures will appear here.',text_color=MUTED,font=('Segoe UI',15)).pack(pady=(0,38))
        for item,image in zip(page_items,thumbs):
            card=board.card()
            if image is None:
                image=Image.new('RGB',(300,170),RAISED);d=ImageDraw.Draw(image);d.rounded_rectangle((116,50,184,120),12,outline=MUTED,width=2);d.polygon(((143,70),(143,102),(166,86)),fill=TEXT)
            art=ctk.CTkImage(image,size=(art_width,round(art_width*9/16)));self.images.append(art)
            ctk.CTkButton(card,text='',image=art,command=lambda p=item.path:self.launch(p),height=round(art_width*9/16)+6,fg_color='transparent',hover_color=RAISED,corner_radius=10).pack(fill='x',padx=4,pady=(6,0))
            when=datetime.fromtimestamp(item.modified).strftime('%d %b %Y · %H:%M')
            ctk.CTkLabel(card,text=when,text_color=TEXT,font=('Segoe UI',16),height=24).pack(anchor='w',padx=16,pady=(10,0))
            ctk.CTkLabel(card,text=(item.path.suffix[1:].upper().replace('JPEG','JPG') or ('PNG' if item.kind=='Photos' else 'MP4'))+'  ·  '+format_bytes(item.size),text_color=MUTED,font=('Segoe UI',14),height=22).pack(anchor='w',padx=16,pady=(0,4))
            LuxButton(card,'Open photo' if item.kind=='Photos' else 'Play recording',lambda p=item.path:self.launch(p),height=42,radius=21,text_size=15,behind=CARD).pack(fill='x',padx=12,pady=(6,14))
        board.layout()
        pages=max(1,(len(self.items)+11)//12)
        board.status(error or f'{len(self.items)} recent capture{"" if len(self.items)==1 else "s"} · Page {self.number+1} of {pages}')
        self.back.restyle(enabled=bool(self.number));self.next.restyle(enabled=self.number+1<pages)
    def launch(self,path):
        try:os.startfile(str(path))
        except OSError:self.board.status('Unable to open this capture. Check its default app.')


class ConsoleCaptures:
    """The PS5's own screenshots and clips, listed through the payload and copied on request into the capture folder."""
    current=None
    def __init__(self,parent,app,copied_some):
        if ConsoleCaptures.current is not None and ConsoleCaptures.current.window.winfo_exists():
            ConsoleCaptures.current.window.focus_force();return
        ConsoleCaptures.current=self
        import console_captures
        self.cc=console_captures;self.app=app;self.copied_some=copied_some;self.answers=queue.Queue();self.found=[];self.chosen={};self.busy=False
        self.window=window=ctk.CTkToplevel(parent);window.title('PlayBridge');window.configure(fg_color=BG);dark_title_bar(window);window.transient(parent)
        x=parent.winfo_rootx()+(parent.winfo_width()-760)//2;y=parent.winfo_rooty()+(parent.winfo_height()-600)//2;window.geometry(f'760x600+{max(0,x)}+{max(0,y)}');window.minsize(560,400)
        window.grid_columnconfigure(0,weight=1);window.grid_rowconfigure(1,weight=1)
        head=tk.Frame(window,bg=BG);head.grid(row=0,column=0,sticky='ew',padx=22,pady=(18,8));head.grid_columnconfigure(0,weight=1)
        heading(head,'On your PS5',28).grid(row=0,column=0,sticky='w')
        ctk.CTkLabel(head,text='Screenshots and clips the console saved. Copies go to your capture folder and show in Media.',font=('Segoe UI',12),text_color=MUTED).grid(row=1,column=0,sticky='w')
        self.list=ctk.CTkScrollableFrame(window,fg_color=BG);thin_scrollbar(self.list);self.list.grid(row=1,column=0,sticky='nsew',padx=16);self.list.grid_columnconfigure(1,weight=1)
        foot=tk.Frame(window,bg=BG);foot.grid(row=2,column=0,sticky='ew',padx=22,pady=14);foot.grid_columnconfigure(0,weight=1)
        self.status=ctk.CTkLabel(foot,text='Asking your PS5…',font=('Segoe UI',12),text_color=MUTED,anchor='w');self.status.grid(row=0,column=0,sticky='ew')
        self.copy_new=LuxButton(foot,'Copy new',lambda:self.copy([c for c in self.found if not self.cc.copied(c,self.folder())]),width=120,height=36,radius=18,behind=BG,enabled=False);self.copy_new.grid(row=0,column=1,padx=(0,8))
        self.copy_chosen=LuxButton(foot,'Copy selected',lambda:self.copy([c for c in self.found if self.chosen[c['path']].get()]),width=140,height=36,radius=18,behind=BG,tone='main',enabled=False);self.copy_chosen.grid(row=0,column=2)
        window.protocol('WM_DELETE_WINDOW',self.close);window.bind('<Escape>',lambda _:self.close());window.after(80,window.focus_force)
        if not app.link.work(lambda sock:self.cc.find_captures(sock,name_of=app.link.game_name),lambda result:self.answers.put(('found',result))):
            self.status.configure(text='Connect to your PS5 first. The list comes through PlayBridge\'s connection.')
        else:window.after(100,self.poll)
    def folder(self):return self.app.capture_folder()
    def close(self):
        ConsoleCaptures.current=None
        if self.window.winfo_exists():self.window.destroy()
    def poll(self):
        if not self.window.winfo_exists():return
        try:
            while True:
                kind,value=self.answers.get_nowait()
                if kind=='found':self.show(*value) if isinstance(value,tuple) else self.status.configure(text='The PS5 did not answer.')
                elif kind=='progress':self.status.configure(text=value)
                elif kind=='done':self.finish(*value)
        except queue.Empty:pass
        self.window.after(100,self.poll)
    def show(self,found,old):
        self.found=found
        if old:self.status.configure(text='Your PS5 runs an older PlayBridge payload. Reconnect so that PlayBridge sends the current one.');return
        if not found:self.status.configure(text='No screenshots or clips were found on your PS5.');return
        folder=self.folder()
        for row,capture in enumerate(found[:400]):
            variable=tk.BooleanVar(master=self.window,value=False);self.chosen[capture['path']]=variable
            ctk.CTkCheckBox(self.list,text='',variable=variable,width=24,command=self.update_buttons).grid(row=row,column=0,padx=(6,4),pady=3)
            when=datetime.fromtimestamp(capture['modified']).strftime('%d %b %Y  %H:%M')
            done='  ·  On this PC' if self.cc.copied(capture,folder) else ''
            ctk.CTkLabel(self.list,text=capture['name'],font=('Segoe UI',13),text_color=TEXT,anchor='w').grid(row=row,column=1,sticky='ew')
            ctk.CTkLabel(self.list,text=f"{capture['folder']}  ·  {'Photo' if capture['kind']=='Photos' else 'Clip'}  ·  {self.cc.size_label(capture['size'])}  ·  {when}{done}",font=('Segoe UI',11),text_color=MUTED,anchor='e').grid(row=row,column=2,sticky='e',padx=(10,6))
        photos=sum(c['kind']=='Photos' for c in found)
        self.status.configure(text=f'{photos} photos and {len(found)-photos} clips on your PS5.'+(' The 400 newest are listed.' if len(found)>400 else ''))
        self.update_buttons()
    def update_buttons(self):
        self.copy_new.restyle(enabled=bool(self.found) and not self.busy)
        self.copy_chosen.restyle(enabled=not self.busy and any(v.get() for v in self.chosen.values()))
    def copy(self,captures):
        if self.busy or not captures:
            if not captures:self.status.configure(text='Everything listed is already on this PC.')
            return
        self.busy=True;self.update_buttons();folder=self.folder();total=len(captures)
        def job(sock):
            done=failed=0
            for index,capture in enumerate(captures,1):
                def progress(got,size,index=index,name=capture['name']):
                    if got==size or got%(1<<22)<65536:self.answers.put(('progress',f'Copying {index} of {total}: {name}  ·  {got*100//max(size,1)}%'))
                if self.cc.copy_capture(sock,capture,folder,progress):done+=1
                else:failed+=1
            return done,failed
        # Clips can take minutes. The console's status waits for each file, so the video keeps its place first.
        if not self.app.link.work(job,lambda result:self.answers.put(('done',result if isinstance(result,tuple) else (0,total)))):
            self.busy=False;self.update_buttons();self.status.configure(text='Connect to your PS5 first.')
    def finish(self,done,failed):
        self.busy=False;self.update_buttons()
        self.status.configure(text=f'{done} copied to your capture folder.'+(f' {failed} could not be read.' if failed else ''))
        if done:self.copied_some()
