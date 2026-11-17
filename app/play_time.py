"""Play time: a daily limit on playing through PlayBridge, kept with a PIN. Time counts while the PS5's picture streams to this PC.
Ten minutes and one minute before the limit PlayBridge says so; at the limit it ends the stream and does not connect again that day,
until the PIN adds time. The PS5's own Family settings limit the console itself; this limits only PlayBridge.

The PIN is kept as a salted PBKDF2 hash. Five wrong PINs in a row wait a minute before the next try."""
import hashlib,hmac,os,time

LIMITS={'Off':0,'30 minutes':1800,'1 hour':3600,'1 hour 30 minutes':5400,'2 hours':7200,'3 hours':10800,'4 hours':14400}
WARNINGS=(600,60)
ROUNDS=200_000
TRIES=5;WAIT=60
UNLOCKED_FOR=300
WHOLE_DAY=24*3600

def hash_pin(pin,salt):return hashlib.pbkdf2_hmac('sha256',pin.encode(),salt,ROUNDS).hex()

def duration(seconds):
 """'1 h 05 min', '42 min' or 'under a minute'."""
 minutes=int(seconds)//60
 if minutes<1:return 'under a minute'
 return f'{minutes//60} h {minutes%60:02d} min' if minutes>=60 else f'{minutes} min'

class PlayTime:
 """saved: what the preferences kept (or None); keep(data): saves it. clock and today are for tests."""
 def __init__(self,saved,keep,clock=time.time,today=lambda:time.strftime('%Y-%m-%d')):
  saved=saved if isinstance(saved,dict) else {}
  self.keep=keep;self.clock=clock;self.today=today
  self.limit=saved.get('limit') if saved.get('limit') in LIMITS.values() else 0
  self.salt=bytes.fromhex(saved['salt']) if isinstance(saved.get('salt'),str) and saved.get('hash') else b''
  self.hash=saved.get('hash','') if self.salt else ''
  self.day=saved.get('day','');self.used=float(saved.get('used',0) or 0);self.extra=float(saved.get('extra',0) or 0)
  self.warned=set();self.wrong=0;self.wait_until=0;self.unlocked_until=0;self.dirty=0
  self.roll()
 def data(self):
  return dict(limit=self.limit,salt=self.salt.hex(),hash=self.hash,day=self.day,used=round(self.used),extra=round(self.extra))
 def save(self):self.dirty=0;self.keep(self.data())
 def roll(self):
  """A new day starts from nothing."""
  if self.day!=self.today():self.day=self.today();self.used=0;self.extra=0;self.warned=set()
 # The PIN.
 def has_pin(self):return bool(self.hash)
 def set_pin(self,pin):
  """A first PIN, or a new one while unlocked. Four to eight digits."""
  if self.has_pin() and not self.unlocked():return 'Unlock with the current PIN first.'
  if not (pin.isdigit() and 4<=len(pin)<=8):return 'The PIN is four to eight digits.'
  self.salt=os.urandom(16);self.hash=hash_pin(pin,self.salt);self.unlocked_until=self.clock()+UNLOCKED_FOR;self.save();return ''
 def unlock(self,pin):
  now=self.clock()
  if now<self.wait_until:return f'Too many wrong PINs. Try again in {int(self.wait_until-now)+1} seconds.'
  if not self.has_pin():return ''
  if hmac.compare_digest(hash_pin(str(pin),self.salt),self.hash):self.wrong=0;self.unlocked_until=now+UNLOCKED_FOR;return ''
  self.wrong+=1
  if self.wrong>=TRIES:self.wrong=0;self.wait_until=now+WAIT;return f'Too many wrong PINs. Try again in {WAIT} seconds.'
  return 'That PIN is not right.'
 def unlocked(self):return not self.has_pin() or self.clock()<self.unlocked_until
 def lock(self):self.unlocked_until=0
 # What a parent changes, only while unlocked.
 def set_limit(self,name):
  if name not in LIMITS:return ''
  if not self.has_pin():return 'Set a PIN first, so the limit cannot be changed without it.'
  if not self.unlocked():return 'Unlock with the PIN first.'
  self.limit=LIMITS[name];self.warned=set();self.save();return ''
 def add(self,seconds):
  if not self.unlocked():return 'Unlock with the PIN first.'
  self.roll();self.extra+=seconds;self.warned=set();self.save();return ''
 def forget_pin(self):
  if not self.unlocked():return 'Unlock with the PIN first.'
  self.salt=b'';self.hash='';self.limit=0;self.unlocked_until=0;self.save();return ''
 # The day's count.
 def left(self):
  """Seconds still allowed today, or None with no limit."""
  self.roll()
  return None if not self.limit else max(0.0,self.limit+self.extra-self.used)
 def blocked(self):
  """Why PlayBridge may not stream now, or ''."""
  left=self.left()
  return '' if left is None or left>0 else f'Today\'s play time is used up ({duration(self.limit+self.extra)}). It starts again tomorrow, or a parent can add time in Settings › Console › Play time.'
 def count(self,seconds):
  """seconds more of streaming. Returns what to say now: a warning, the end, or ''."""
  self.roll();self.used+=seconds;self.dirty+=seconds
  if self.dirty>=30:self.save()
  left=self.left()
  if left is None:return ''
  if left<=0:
   if 'end' in self.warned:return ''
   self.warned.add('end');self.save();return self.blocked()
  for mark in WARNINGS:
   if left<=mark and mark not in self.warned:
    self.warned.update(m for m in WARNINGS if m>=mark)
    return f'{duration(left) if left>=60 else "One minute"} of play time left today.' if mark==600 else 'One minute of play time left today.'
  return ''
 def view(self):
  left=self.left();name=next((n for n,s in LIMITS.items() if s==self.limit),'Off')
  if left is None:line=f'No limit. Played through PlayBridge today: {duration(self.used)}.'
  else:line=f'Played today: {duration(self.used)} of {duration(self.limit+self.extra)}. '+(f'{duration(left)} left.' if left>0 else 'Time is up for today.')
  return dict(limit=name,limits=list(LIMITS),hasPin=self.has_pin(),unlocked=self.unlocked() and self.has_pin(),line=line,up=left is not None and left<=0)
