"""The DualSense's microphone through the PS5: a stand-in payload answers on its port as console-mic.h does, and its blocks reach the voice
buffer at 48 kHz, as loud as they were; the console's refusal and the silent flags are told; the port and layout match the payload's."""
import os,re,socket,struct,sys,threading,time,unittest
from pathlib import Path
import numpy as np
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import console_mic as cm
import mic_mix

RULES=(Path(__file__).resolve().parents[1]/'payload'/'mic-rules.h').read_text(encoding='utf8')

class StandIn:
 """The payload's microphone port: the answer, then blocks of a 1 kHz tone at rate, with silent flags from silent(block)."""
 def __init__(self,rate=16000,handle=1,way=0,blocks=60,silent=lambda n:0):
  self.rate=rate;self.handle=handle;self.way=way;self.blocks=blocks;self.silent=silent;self.served=0
  self.server=socket.create_server(('127.0.0.1',0));self.port=self.server.getsockname()[1]
  threading.Thread(target=self.serve,daemon=True).start()
 def serve(self):
  while True:
   try:connection,_=self.server.accept()
   except OSError:return
   self.served+=1
   with connection:
    try:
     connection.sendall(struct.pack('<4siiii',b'PBM1',self.handle,self.rate if self.handle>=0 else 0,256,self.way))
     if self.handle<0:continue
     at=0
     for n in range(self.blocks):
      t=(at+np.arange(256))/self.rate;at+=256
      tone=(np.sin(2*np.pi*1000*t)*16384).astype('<i2')
      connection.sendall(struct.pack('<HH',256,self.silent(n))+tone.tobytes())
     time.sleep(.3)
    except OSError:pass

class Collector:
 """Keeps every sample, unlike the voice buffer, which drops what the mixer has not taken."""
 def __init__(self):self.parts=[]
 def add(self,samples):self.parts.append(np.asarray(samples,np.float32))
 @property
 def held(self):return sum(len(part) for part in self.parts)
 def all(self):return np.concatenate(self.parts) if self.parts else np.zeros(0,np.float32)

def wait_for(test,seconds=4):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  if test():return True
  time.sleep(.02)
 return False

class MicTests(unittest.TestCase):
 def setUp(self):
  self.original=cm.PORT;self.addCleanup(setattr,cm,'PORT',self.original);self.notes=[]
 def listen(self,console):
  cm.PORT=console.port;voice=Collector();mic=cm.ConsoleMic(lambda:'127.0.0.1',voice,self.notes.append);self.addCleanup(mic.stop);return mic,voice
 def test_the_port_and_the_layout_match_the_payload(self):
  self.assertEqual(int(re.search(r'#define MIC_PORT (\d+)',RULES).group(1)),self.original)
  self.assertIn('#define MIC_MAGIC "PBM1"',RULES);self.assertEqual(int(re.search(r'#define MIC_HEAD (\d+)u',RULES).group(1)),cm.HEAD.size)
  self.assertEqual(int(re.search(r'#define MIC_BLOCK_HEAD (\d+)u',RULES).group(1)),cm.BLOCK.size)
 def test_16_khz_blocks_reach_the_voice_at_48_khz_as_loud(self):
  console=StandIn(blocks=60);mic,voice=self.listen(console)
  self.assertTrue(wait_for(lambda:mic.blocks==60));mic.stop()
  self.assertAlmostEqual(voice.held/(60*256*3),1,delta=.01)
  heard=voice.all()[48:];self.assertAlmostEqual(float(np.abs(heard).max()),.5,delta=.02)
  # Still a 1 kHz tone: 100 cycles, so 100 rises through zero, in a tenth of a second at 48 kHz.
  part=heard[:4800];rises=int(np.sum((part[:-1]<0)&(part[1:]>=0)));self.assertAlmostEqual(rises,100,delta=2)
  self.assertIn('DualSense microphone on, at 16 kHz.',self.notes)
 def test_48_khz_blocks_go_as_they_are(self):
  console=StandIn(rate=48000,blocks=10);mic,voice=self.listen(console)
  self.assertTrue(wait_for(lambda:mic.blocks==10));self.assertEqual(voice.held,2560)
 def test_a_refusal_is_told_and_not_asked_again_at_once(self):
  console=StandIn(handle=-2139029502);mic,voice=self.listen(console)
  self.assertTrue(wait_for(lambda:'did not open' in mic.state));self.assertIn('80810002',mic.state)
  time.sleep(.5);self.assertEqual(console.served,1)
 def test_the_silent_flags_are_told(self):
  console=StandIn(blocks=40,silent=lambda n:cm.PRIORITY_LOW if n>=10 else 0);mic,voice=self.listen(console)
  self.assertTrue(wait_for(lambda:'Another app' in mic.state));self.assertTrue(any('party chat' in note for note in self.notes))
 def test_it_waits_for_the_stream_and_comes_back(self):
  cm.PORT=1;voice=mic_mix.VoiceBuffer();mic=cm.ConsoleMic(lambda:'127.0.0.1',voice);self.addCleanup(mic.stop)
  time.sleep(.3);self.assertEqual(mic.state,'Waiting for the PS5…');self.assertEqual(voice.held,0)
 def test_the_microphone_choice_opens_and_closes_it(self):
  console=StandIn(blocks=20);cm.PORT=console.port;mix=mic_mix.MicMix()
  microphone=mic_mix.Microphone(mix,console=lambda:'127.0.0.1');self.assertTrue(microphone.open(cm.NAME));self.addCleanup(microphone.close)
  self.assertEqual(microphone.name,cm.NAME);self.assertTrue(microphone.on)
  self.assertTrue(wait_for(lambda:microphone.state().startswith('DualSense microphone on')))
  microphone.close();self.assertFalse(microphone.on);self.assertEqual(microphone.state(),'')
  self.assertFalse(mic_mix.Microphone(mix).open(cm.NAME))

class UpsampleTests(unittest.TestCase):
 def test_blocks_join_with_no_gap_or_repeat(self):
  up=cm.Upsampler(16000);ramp=np.arange(0,1600,dtype=np.float32)
  whole=np.concatenate([up(ramp[i:i+256]) for i in range(0,1536,256)])
  self.assertEqual(len(whole),1535*3+1);self.assertEqual(whole[0],0);self.assertTrue(np.allclose(np.diff(whole),1/3,atol=1e-4))
  self.assertEqual(len(up(np.zeros(0,np.float32))),0)

if __name__=='__main__':unittest.main()
