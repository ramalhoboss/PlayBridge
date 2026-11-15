"""How the Games page lays out its games: in a row as on the console, in a grid, or in a list with each game's details. The choice, where
everything stands in the grid and the list, and how the arrows, the wheel and the controller move in each, worked out without Qt or PIL so
that the tests can check them. scene.py and classic_games.py draw what this says."""
import math
from types import SimpleNamespace

VIEWS=(('row','Row'),('grid','Grid'),('list','List'))
SIZES=(('small','Small'),('medium','Medium'),('large','Large'))
VIEW_NAMES=dict(VIEWS);SIZE_NAMES=dict(SIZES)
# How large the tiles are next to the console's own row, the grid's tiles and the list's rows, in the page's units.
ROW_SCALE={'small':.86,'medium':1.0,'large':1.16}
GRID_SIDE={'small':132,'medium':164,'large':204}
LIST_ROW={'small':52,'medium':64,'large':80}
# How much larger the focused tile stands in the grid.
LIFT=1.1
# The list's columns after the name, from the left: key, caption, width in units, and whether the words end at the right. When the page is
# too narrow for all of them, the first ones in DROP_ORDER go first.
LIST_COLUMNS=(('kind','Type',120,False),('played','Last played',160,False),('time','Play time',120,True),('trophies','Trophies',200,False),('size','Size',100,True))
DROP_ORDER=('kind','played','size','trophies','time')
NAME_ROOM=240

class ViewChoice:
 """What the Games page shows, as the settings keep it."""
 def __init__(self,view='row',size='medium',names=True,badges=True):
  self.view=view if view in VIEW_NAMES else 'row';self.size=size if size in SIZE_NAMES else 'medium';self.names=bool(names);self.badges=bool(badges)
 @classmethod
 def from_saved(cls,saved):
  return cls(saved.get('games_view','row'),saved.get('tile_size','medium'),saved.get('tile_names',True),saved.get('tile_badges',True))
 def saved(self):return dict(games_view=self.view,tile_size=self.size,tile_names=self.names,tile_badges=self.badges)
 def key(self):return (self.view,self.size,self.names,self.badges)
 def next_size(self):
  keys=[key for key,_ in SIZES];self.size=keys[(keys.index(self.size)+1)%len(keys)]

def menu_items(choice,shelf_name):
 """The View menu: the three views with a mark on the one showing, then the choices that go with it, each with how it stands."""
 items=[(f'view:{key}',label,choice.view==key) for key,label in VIEWS]+[('shelf','Shelf',shelf_name),('size','Tile size' if choice.view!='list' else 'Row size',SIZE_NAMES[choice.size])]
 if choice.view=='grid':items.append(('names','Names under tiles','On' if choice.names else 'Off'))
 if choice.view!='list':items.append(('badges','Badges on tiles','On' if choice.badges else 'Off'))
 return items

def arranged(layout,choice):
 """The page's layout for this choice. The row keeps the console's own; the grid and the list put the focused game's name, its line and
 its buttons at the top and the games on one sheet of glass under them. band_y and band_height are then the sheet, the part drawn again
 while the focus moves."""
 page=SimpleNamespace(**vars(layout));page.view=choice.view
 if choice.view=='row':return page
 unit=layout.unit;margin=layout.margin;width=layout.width
 top=layout.bar_y+layout.bar+round(26*unit);page.head_size=max(18,round(46*unit));head_bottom=top+page.head_size+round(12*unit)+layout.meta
 page.head_y=top;page.meta_y=top+page.head_size+round(12*unit)+layout.meta//2
 page.option_x=width-margin-layout.pill;page.pill_x=page.option_x-round(14*unit)-layout.pill_width;page.pill_y=top+(head_bottom-top-layout.pill)//2
 page.head_width=max(80,page.pill_x-margin-round(30*unit))
 edge=round(22*unit);sheet=(margin-edge,head_bottom+round(22*unit),width-margin+edge,layout.hints_y-round(14*unit))
 page.sheet=sheet;page.sheet_radius=round(18*unit);pad=round(24*unit);page.inner=(sheet[0]+pad,sheet[1]+pad,sheet[2]-pad,sheet[3]-pad)
 page.band_y=sheet[1];page.band_height=sheet[3]-sheet[1];page.panel_top=sheet[1]
 # The fade at the sheet's top and bottom edges, where a row scrolls out of sight.
 page.fade=round(26*unit)
 if choice.view=='grid':grid(page,choice)
 else:rows(page,choice)
 return page

def grid(page,choice):
 unit=page.unit;x0,y0,x1,y1=page.inner;side=max(48,round(GRID_SIDE[choice.size]*unit));page.side=side;page.lift_side=round(side*LIFT)
 page.name_size=max(10,round(16*unit));page.name_room=round(page.name_size*2.1) if choice.names else 0
 gap=max(8,round(26*unit));room=x1-x0;columns=max(1,(room+gap)//(side+gap))
 spread=min((room-columns*side)/(columns-1),gap*2.2) if columns>1 else 0;used=columns*side+(columns-1)*spread
 page.columns=columns;page.step_x=side+spread;page.left=x0+(room-used)/2
 # Room above the first row and below the last for the focused tile, which stands larger than its cell.
 grow=(page.lift_side-side)/2+round(4*unit);page.content_top=y0+grow;page.step_y=side+page.name_room+gap
 page.rows_shown=max(1,int((y1-grow-page.content_top-side-page.name_room)//page.step_y)+1)

def rows(page,choice):
 unit=page.unit;x0,y0,x1,y1=page.inner;row=max(36,round(LIST_ROW[choice.size]*unit));page.row=row;page.icon=row-round(14*unit)
 page.captions_y=y0+round(12*unit);page.rows_top=y0+round(34*unit);page.rows_shown=max(1,(y1-page.rows_top)//row)
 page.name_x=x0+round(10*unit)+page.icon+round(18*unit);page.columns=1
 shown=[key for key,_,_,_ in LIST_COLUMNS]
 def need():return sum(round(width*unit)+round(20*unit) for key,_,width,_ in LIST_COLUMNS if key in shown)
 for key in DROP_ORDER:
  if x1-round(10*unit)-need()-page.name_x>=round(NAME_ROOM*unit):break
  shown.remove(key)
 right=x1-round(10*unit);places=[]
 for key,caption,width,at_right in reversed(LIST_COLUMNS):
  if key not in shown:continue
  w=round(width*unit);places.append((key,caption,right-w,right,at_right));right-=w+round(20*unit)
 page.list_columns=tuple(reversed(places));page.name_end=right

def rows_total(page,count):
 return max(1,math.ceil(count/page.columns)) if count else 0

def first_row(page,focus_row,first,count):
 """The first row in sight once the focus is in sight, moving the sheet as little as it can."""
 shown=page.rows_shown;total=rows_total(page,count)
 if focus_row<first:first=focus_row
 elif focus_row>first+shown-1:first=focus_row-shown+1
 return max(0,min(first,max(0,total-shown)))

def cell(page,index,scroll):
 """The middle of a game's tile in the grid, or its row's middle in the list, with the sheet scrolled by scroll rows."""
 if page.view=='grid':
  column,row=index%page.columns,index//page.columns
  return page.left+column*page.step_x+page.side/2,page.content_top+(row-scroll)*page.step_y+page.side/2
 return (page.inner[0]+page.inner[2])/2,page.rows_top+(index-scroll)*page.row+page.row/2

def in_sight(page,count,scroll):
 """The games the sheet can show at this scroll, part of a row included."""
 if not count:return range(0)
 low=max(0,math.floor(scroll)-1);high=min(rows_total(page,count),math.ceil(scroll+page.rows_shown)+1)
 return range(low*page.columns,min(count,high*page.columns))

def hit(page,x,y,count,scroll):
 """The game under a point on the sheet, or None."""
 x0,y0,x1,y1=page.inner
 if not (page.sheet[0]<=x<page.sheet[2] and y0<=y<y1) or not count:return None
 if page.view=='grid':
  for index in in_sight(page,count,scroll):
   cx,cy=cell(page,index,scroll)
   if abs(x-cx)<=page.side/2 and abs(y-cy)<=page.side/2:return index
  return None
 if y<page.rows_top:return None
 index=math.floor((y-page.rows_top)/page.row+scroll)
 return index if 0<=index<count else None

def move_for(view,event,target,count,columns=1,page_rows=1):
 """What a move from the keys or the controller does in this view: ('to', index), ('edge',) at an end, ('shelf', ±1), or None when
 it is not a move. The row moves along, the grid in two directions and the list up and down; the shelf changes with the arrows the view
 does not use."""
 if view=='row' and event in ('up','down'):return ('shelf',-1 if event=='up' else 1)
 if view=='list' and event in ('left','right'):return ('shelf',-1 if event=='left' else 1)
 if event not in ('left','right','up','down','previous','next'):return None
 if not count:return ('edge',)
 columns=max(1,columns);page_rows=max(1,page_rows)
 if view=='grid':
  changes={'left':-1,'right':1,'up':-columns,'down':columns,'previous':-columns*page_rows,'next':columns*page_rows}
  change=changes[event];at=target+change
  # Down from a row with a shorter row under it lands on that row's last game.
  if change>0 and at>=count:at=count-1 if target//columns<(count-1)//columns else target
  elif change<0 and at<0:at=0 if event=='previous' else target
  return ('edge',) if at==target else ('to',at)
 changes={'up':-1,'down':1,'previous':-page_rows,'next':page_rows} if view=='list' else {'left':-1,'right':1,'previous':-5,'next':5}
 if event not in changes:return None
 at=max(0,min(count-1,target+changes[event]));return ('edge',) if at==target else ('to',at)

def wheel_for(view,change,target,count,columns=1):
 """A turn of the wheel: a row of the grid at a time, one game in the row or the list."""
 if not count:return ('edge',)
 step=change*(max(1,columns) if view=='grid' else 1);at=target+step
 if view=='grid' and step>0 and at>=count:at=count-1 if target//columns<(count-1)//columns else target
 at=max(0,min(count-1,at));return ('edge',) if at==target else ('to',at)

def hints(view,keys):
 """The key hints for the bar along the bottom, with the arrows this view uses."""
 arrows={'grid':'←↑↓→','list':'↑  ↓'}.get(view)
 return tuple((arrows,label) if arrows and label=='Move' else (mark,label) for mark,label in keys)
