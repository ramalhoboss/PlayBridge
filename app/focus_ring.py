"""Moving between a page's controls with the arrow keys or the controller, as on the console: the control in focus wears a gold ring,
and Enter or the controller's accept button uses it. The controls are found on the page each time, so the ones that come and go with a
choice need no list of their own. The ring only shows once the keys or the controller are used, and a click hides it again."""
import customtkinter as ctk
from luxury_theme import GOLD,GOLD_SOFT,TEXT,Bezel,LuxButton

def controls(root):
 """Every control on the page that can be used now, in the order they were made."""
 found=[]
 def walk(widget):
  for child in widget.winfo_children():
   try:
    if not child.winfo_ismapped():continue
   except Exception:continue
   if isinstance(child,LuxButton):
    if child.clickable and child.enabled and child.command is not None:found.append(child)
   elif isinstance(child,Bezel) and inner(child) is not None:found.append(child)
   elif isinstance(child,(ctk.CTkSwitch,ctk.CTkSlider,ctk.CTkCheckBox)):
    if str(child.cget('state'))!='disabled':found.append(child)
   else:walk(child)
 walk(root);return found

def inner(rim):
 """The entry or menu inside a rim, which is what a rim stands for."""
 for child in rim.body.winfo_children():
  if isinstance(child,(ctk.CTkEntry,ctk.CTkOptionMenu)):return child
 return None

def box(widget):
 x,y=widget.winfo_rootx(),widget.winfo_rooty();return x,y,x+widget.winfo_width(),y+widget.winfo_height()

def gap(low1,high1,low2,high2):
 """How far apart two spans are along one axis, 0 when they overlap."""
 return max(0,low2-high1,low1-high2)

def nearest(current,candidates,direction):
 """The control the arrow points at: the closest one on that side, with those in line with the current one first."""
 left,top,right,bottom=box(current);best=None;score=None
 for other in candidates:
  if other is current:continue
  l,t,r,b=box(other)
  if direction=='down' and t>=bottom-2:ahead,side=t-bottom,gap(left,right,l,r)
  elif direction=='up' and b<=top+2:ahead,side=top-b,gap(left,right,l,r)
  elif direction=='right' and l>=right-2:ahead,side=l-right,gap(top,bottom,t,b)
  elif direction=='left' and r<=left+2:ahead,side=left-r,gap(top,bottom,t,b)
  else:continue
  value=ahead+3*side
  if score is None or value<score:best,score=other,value
 return best

def mark(widget,on):
 """Puts the gold ring on a control, or takes it off."""
 try:
  if isinstance(widget,LuxButton):
   if widget.focused!=on:widget.focused=on;widget.draw()
  elif isinstance(widget,Bezel):widget.set_ring(on)
  elif isinstance(widget,ctk.CTkSwitch):widget.configure(text_color=GOLD_SOFT if on else TEXT,border_color=GOLD if on else 'transparent',border_width=2 if on else 0)
  elif isinstance(widget,ctk.CTkSlider):widget.configure(border_color=GOLD if on else 'transparent',border_width=3 if on else 0)
  elif isinstance(widget,ctk.CTkCheckBox):widget.configure(text_color=GOLD_SOFT if on else TEXT)
 except Exception:pass

class FocusWalker:
 """The ring on one page at a time. pop(items, right, top, choose) opens the app's own list for an option menu, so the controller
 can choose from it; reveal(widget) scrolls a page so the widget shows."""
 def __init__(self,pop=None,reveal=None):
  self.current=None;self.pop=pop;self.reveal=reveal
 def hide(self):
  if self.current is not None:mark(self.current,False)
  self.current=None
 def show(self,widget):
  if widget is not self.current:
   self.hide();self.current=widget;mark(widget,True)
  if self.reveal is not None:
   try:self.reveal(widget)
   except Exception:pass
 def valid(self,root):
  try:return self.current is not None and self.current.winfo_exists() and self.current.winfo_ismapped() and self.current in controls(root)
  except Exception:return False
 def move(self,root,direction):
  """True when the ring moved or appeared. False at the edge, so the page can take the key itself (the menu on the left)."""
  found=controls(root)
  if not found:self.hide();return False
  if not self.valid(root):
   self.show(found[0]);return True
  if isinstance(self.current,ctk.CTkSlider) and direction in ('left','right'):
   self.nudge(self.current,1 if direction=='right' else -1);return True
  target=nearest(self.current,found,direction)
  if target is None:return False
  self.show(target);return True
 def nudge(self,slider,steps):
  """Left and right move a slider in twentieths, and it keeps the value as the mouse would."""
  low,high=getattr(slider,'_from_',0),getattr(slider,'_to',1);value=min(high,max(low,slider.get()+steps*(high-low)/20))
  slider.set(value);command=getattr(slider,'_command',None)
  if command:command(value)
  canvas=getattr(slider,'_canvas',None)
  if canvas is not None:canvas.event_generate('<ButtonRelease-1>',x=0,y=0)
 def accept(self,root):
  """Uses the control in the ring. True when there was one."""
  if not self.valid(root):return False
  widget=self.current
  if isinstance(widget,LuxButton):
   widget.command()
  elif isinstance(widget,ctk.CTkSwitch) or isinstance(widget,ctk.CTkCheckBox):widget.toggle()
  elif isinstance(widget,Bezel):
   control=inner(widget)
   if isinstance(control,ctk.CTkEntry):control.focus_set();control.icursor('end')
   elif isinstance(control,ctk.CTkOptionMenu) and self.pop is not None:
    values=list(control.cget('values'))
    def choose(value):
     control.set(value);command=getattr(control,'_command',None)
     if command:command(value)
    left,top,right,bottom=box(widget);self.pop([(value,value) for value in values],right,bottom+4,choose)
  return True
