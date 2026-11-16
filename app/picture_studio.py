"""Picture Studio: the settings the GPU video output draws the picture with (the graphics card's super resolution, RTX Video HDR, FSR 1,
sharpening and debanding), kept for every game, or for one game of its own, which come back each time that game runs. The before and
after comparison is for the session only."""

DEFAULTS={'super_resolution':True,'video_hdr':False,'fsr':False,'sharpen':False,'deband':False}
NAMES={'super_resolution':'Graphics card super resolution','video_hdr':'RTX Video HDR','fsr':'FSR 1 upscaling','sharpen':'Sharpen picture','deband':'Deband'}

def chosen(saved):
 """The five settings from saved values, each a bool, with the defaults for any not there."""
 saved=saved or {};return {key:bool(saved.get(key,default)) for key,default in DEFAULTS.items()}

class PictureStudio:
 """Which values the picture uses now: the game's own while a game with its own runs, the usual ones otherwise. The presenter is told
 each time they change, from the window's thread."""
 def __init__(self,core):
  self.core=core;self.title='';self.name=''
 def presets(self):
  presets=self.core.config().get('picture_presets')
  return dict(presets) if isinstance(presets,dict) else {}
 def usual(self):return chosen(self.core.config())
 def own(self):return bool(self.title) and isinstance(self.presets().get(self.title),dict)
 def current(self):return chosen(self.presets()[self.title]) if self.own() else self.usual()
 def apply(self,presenter):
  """Gives the presenter the values in use now. A video engine setting that changes gets a fresh try, as when it is switched by hand."""
  if presenter is None:return
  values=self.current()
  if getattr(presenter,'super_resolution',None)!=values['super_resolution']:presenter.turn_engine(super_resolution=values['super_resolution'])
  if getattr(presenter,'video_hdr',None)!=values['video_hdr']:presenter.turn_engine(video_hdr=values['video_hdr'])
  presenter.fsr=values['fsr'];presenter.sharpen=values['sharpen'];presenter.deband=values['deband']
 def see(self,title,name,presenter):
  """Once a second, the game running now ('' for none). True when the values in use changed with it."""
  title=title or ''
  if title==self.title:
   if name:self.name=name
   return False
  before=self.current();self.title=title;self.name=name or '';self.apply(presenter);return self.current()!=before
 def change(self,key,value,presenter):
  """A switch moved: it changes the game's own values while it has them, the usual ones otherwise."""
  if key not in DEFAULTS:return
  if self.own():
   presets=self.presets();presets[self.title]={**chosen(presets[self.title]),key:bool(value),'name':self.name or presets[self.title].get('name','')}
   self.core.save_config(picture_presets=presets)
  else:self.core.save_config(**{key:bool(value)})
  self.apply(presenter)
 def keep_for_game(self,presenter):
  """The values in use now become the running game's own. False when no game runs."""
  if not self.title:return False
  presets=self.presets();presets[self.title]={**self.current(),'name':self.name};self.core.save_config(picture_presets=presets);self.apply(presenter);return True
 def forget_game(self,presenter):
  """The running game goes back to the usual values."""
  presets=self.presets()
  if self.title in presets:del presets[self.title];self.core.save_config(picture_presets=presets)
  self.apply(presenter)
 def view(self):
  """For Settings: the values in use, and which game they are for when it has its own."""
  values=self.current()
  return dict(superResolution=values['super_resolution'],videoHdr=values['video_hdr'],fsr=values['fsr'],sharpen=values['sharpen'],deband=values['deband'],
   studioGame=self.name if self.title else '',studioOwn=self.own(),studioGames=sorted((preset.get('name') or key) for key,preset in self.presets().items() if isinstance(preset,dict)))
