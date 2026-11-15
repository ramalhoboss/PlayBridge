"""Repeated frames. The PS5 captures its screen at 60 fps, so a game that draws 30 frames a second reaches the PC with each of its
frames twice, and one that draws 20 with each three times. The copies show the same picture again.

While in-between pictures can be made, such copies are left out before they reach the pacer: the stream then runs at the game's own
rate, and smooth motion makes the pictures between two real frames of the game, so a 30 fps game moves at 60 on a 60 Hz screen, and at
120 on a 120 Hz one. Left in, the in-between picture of a frame and its copy is that same frame, and the game stays at 30.

Two real measurements decide it. The console counts the frames the game draws (console_control.GameRate), which says how many stream
frames each of the game's frames fills: two at 30, three at 20. And in each such run the game's own frame carries the most: it has the
change from the last one, while a copy only has the same picture again, which the encoder sends as little or nothing, or spends on
sharpening what it sent (a stand-in through x264 gave copies 70% of the size). Where each run starts is found from the sizes of the
recent frames, by their place in the run, which comes from their time stamps, so a frame lost on the way does not shift it. Only a place
whose frames are clearly the largest counts as the game's; with none, nothing is left out. Keyframes always stay: the frames after them
are built on them."""
import collections

# The game's own rate, frames a second, within which its frames fill two or three stream frames: 30 fps games, and 20 and 40 ones.
SLOWEST=18;FASTEST=42
# The stream's frame rate, and the time stamps' clock.
STREAM_FPS=60000/1001;TICKS=90000
# Recent frames whose sizes are compared, and how many are needed at each place in the run before any frame is left out.
RECENT=24;NEEDED=4
# The game's own frames are clearly the largest: the next largest place's middle size is at most this share of theirs.
CLEAR=.8

def middle(values):
 ordered=sorted(values);return ordered[len(ordered)//2]

class RepeatFrames:
 """Decides, frame by frame, whether a decoded frame repeats the one before it. wanted is set once a second by the window: True while
 in-between pictures can be made."""
 def __init__(self,stats):
  self.stats=stats;self.wanted=False;self.sizes=collections.deque(maxlen=RECENT);self.active=False;self.game_fps=None
  self.index=0;self.last_pts=None;self.start=None
 def run_length(self,game_fps):
  """How many stream frames each of the game's frames fills, or 0 when it is not slow enough for copies."""
  if game_fps is None or not SLOWEST<=game_fps<=FASTEST:return 0
  return max(2,round(STREAM_FPS/game_fps))
 def place(self,pts):
  """The frame's number in the stream, from its time stamp: a frame lost on the way still counts."""
  if self.last_pts is not None and pts is not None:self.index+=max(1,round((pts-self.last_pts)*STREAM_FPS/TICKS))
  else:self.index+=1
  if pts is not None:self.last_pts=pts
  return self.index
 def find_start(self,length):
  """The place in each run where the game's own frame sits, or None when no place stands out."""
  groups=[[] for _ in range(length)]
  for index,size,key in self.sizes:
   if not key:groups[index%length].append(size)
  if any(len(group)<NEEDED for group in groups):return None
  middles=[middle(group) for group in groups];best=max(range(length),key=middles.__getitem__)
  return best if all(value<=CLEAR*middles[best] for place,value in enumerate(middles) if place!=best) else None
 def skip(self,pts,size,key,game_fps):
  """True when this frame should not reach the pacer. pts: its time stamp at 90 kHz; size: the bytes of its packet; key: it is a
  keyframe; game_fps: the frames a second the console counted for the game, or None when it gave no count."""
  self.game_fps=game_fps;length=self.run_length(game_fps);self.active=bool(self.wanted and length)
  index=self.place(pts);self.sizes.append((index,size,key))
  if not self.active:self.start=None;return False
  self.start=self.find_start(length)
  if key or self.start is None or index%length==self.start:return False
  self.stats['repeats_skipped']=self.stats.get('repeats_skipped',0)+1;return True
 def state(self):
  """For the stats: whether copies are being left out now."""
  if not self.wanted:return 'off'
  if self.active:
   if self.start is None:return f'looking for the copies: the game draws {self.game_fps:.0f} a second'
   return f'leaving out copies: the game draws {self.game_fps:.0f} a second'
  if self.game_fps is None:return "waiting for the game's frame count"
  return f'not needed: the game draws {self.game_fps:.0f} a second'
