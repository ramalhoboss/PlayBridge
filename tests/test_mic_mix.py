"""Your voice mixed into the console's sound for recordings, replays and Go live."""
import io,os,sys,unittest
from fractions import Fraction
from pathlib import Path
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import av
import numpy as np
import mic_mix as m
from media_capture import strip_adts

def console_packets(count,tone=440.0,level=.3):
 """AAC packets as the console sends them: 48 kHz stereo AAC-LC in ADTS, one per 1024 samples, with 90 kHz timestamps."""
 encoder=av.CodecContext.create('aac','w');encoder.sample_rate=48000;encoder.layout='stereo';encoder.format='fltp';encoder.bit_rate=128000;encoder.time_base=Fraction(1,48000);encoder.open()
 out=[];at=0
 for n in range(count+4):
  t=(np.arange(1024)+at)/48000;wave=(level*np.sin(2*np.pi*tone*t)).astype(np.float32);at+=1024
  frame=av.AudioFrame.from_ndarray(np.stack([wave,wave]),format='fltp',layout='stereo');frame.sample_rate=48000;frame.pts=n*1024;frame.time_base=Fraction(1,48000)
  for packet in encoder.encode(frame):out.append(m.adts(bytes(packet)))
 return [(data,i*1920) for i,data in enumerate(out[:count])]
def decode(packets):
 decoder=av.CodecContext.create('aac','r');parts=[]
 for data in packets:
  for p in decoder.parse(data):
   for f in decoder.decode(p):parts.append(f.to_ndarray()[0])
 return np.concatenate(parts)
def strength(signal,tone):
 t=np.arange(len(signal))/48000;return abs(np.dot(signal,np.exp(-2j*np.pi*tone*t)))/len(signal)
def voice(seconds,tone=1000.0,level=.3):
 t=np.arange(int(48000*seconds))/48000;return (level*np.sin(2*np.pi*tone*t)).astype(np.float32)
def mixed_with_voice(mix,packets,spoken):
 """As in a session: the microphone delivers a frame of voice for each console frame, a little ahead."""
 out=[];mix.voice.add(spoken[:1024]);at=1024
 for data,pts in packets:mix.voice.add(spoken[at:at+1024]);at+=1024;out+=[data for data,_ in mix.mix(data,pts)]
 return out

class BufferTests(unittest.TestCase):
 def test_missing_voice_is_silence_and_counted(self):
  b=m.VoiceBuffer();b.add(np.ones(300,np.float32))
  out=b.take(1024)
  self.assertEqual(len(out),1024);self.assertTrue((out[:300]==1).all());self.assertTrue((out[300:]==0).all());self.assertEqual(b.short,724)
 def test_parts_are_taken_in_order_across_blocks(self):
  b=m.VoiceBuffer();b.add(np.arange(500,dtype=np.float32));b.add(np.arange(500,1000,dtype=np.float32))
  self.assertTrue((b.take(700)==np.arange(700)).all());self.assertTrue((b.take(300)==np.arange(700,1000)).all());self.assertEqual(b.held,0)
 def test_a_microphone_running_ahead_is_brought_back(self):
  # Its clock runs a little fast against the console's: the buffer would grow for ever.
  b=m.VoiceBuffer()
  for _ in range(40):b.add(np.zeros(480,np.float32))
  self.assertLessEqual(b.held,m.HIGH);self.assertGreater(b.dropped,0)
  # The newest sound is kept, the oldest dropped.
  b.add(np.full(480,7,np.float32));self.assertEqual(b.take(b.held)[-1],7)

class MixTests(unittest.TestCase):
 def test_packets_look_like_the_consoles_own(self):
  mix=m.MicMix(av);out=[]
  for data,pts in console_packets(20):out+=mix.mix(data,pts)
  self.assertGreaterEqual(len(out),18)
  for data,pts in out:
   body,config=strip_adts(data);self.assertTrue(body)
   self.assertEqual(config,strip_adts(console_packets(1)[0][0])[1])
  # The recorder and the live output open their audio track from the first packet like this.
  with av.open(io.BytesIO(out[0][0]),format='aac') as probe:self.assertEqual(probe.streams.audio[0].sample_rate,48000)
 def test_timestamps_follow_the_console_packets(self):
  mix=m.MicMix(av);packets=console_packets(12);stamps=[]
  for data,pts in packets:stamps+=[stamp for _,stamp in mix.mix(data,pts)]
  self.assertEqual(stamps,[pts for _,pts in packets][:len(stamps)])
 def test_the_voice_is_heard_over_the_game(self):
  mix=m.MicMix(av);out=mixed_with_voice(mix,console_packets(50),voice(1.2))
  sound=decode(out)[4096:]
  self.assertGreater(strength(sound,1000),.05);self.assertGreater(strength(sound,440),.05)
 def test_volume_zero_leaves_only_the_game(self):
  mix=m.MicMix(av);mix.level=0;out=mixed_with_voice(mix,console_packets(50),voice(1.2))
  sound=decode(out)[4096:]
  self.assertLess(strength(sound,1000),.01);self.assertGreater(strength(sound,440),.05)
 def test_loud_voice_does_not_wrap_around(self):
  mix=m.MicMix(av);mix.level=m.LEVEL_MAX;out=mixed_with_voice(mix,console_packets(50,level=.9),voice(1.2,level=.9))
  self.assertLessEqual(np.abs(decode(out)).max(),1.2)
 def test_a_new_session_starts_clean(self):
  mix=m.MicMix(av);mix.voice.add(voice(.5))
  for data,pts in console_packets(5):mix.mix(data,pts)
  mix.reset();self.assertIsNone(mix.encoder);self.assertEqual(mix.voice.held,0);self.assertEqual(len(mix.waiting),0)

class FakeStream:
 def __init__(self,fail,**options):
  if fail:raise RuntimeError('Error opening InputStream: Invalid device [PaErrorCode -9996]')
  self.options=options;self.started=self.closed=False
 def start(self):self.started=True
 def stop(self):pass
 def close(self):self.closed=True
class FakeDevices:
 def __init__(self,fail_all=False):
  self.fail_all=fail_all;self.opened=[];self.default=type('D',(),{'device':[3,5]})()
 def query_hostapis(self,index=None):
  apis=[{'name':'MME'},{'name':'Windows WASAPI'}];return apis if index is None else apis[index]
 def query_devices(self,device=None,kind=None):
  devices=[{'name':'Speakers','hostapi':1,'max_input_channels':0},{'name':'Headset mic','hostapi':1,'max_input_channels':1},{'name':'Old mic','hostapi':0,'max_input_channels':2},{'name':'Laptop mic','hostapi':1,'max_input_channels':2}]
  return devices if device is None else devices[device]
 def WasapiSettings(self,auto_convert=False):return ('wasapi',auto_convert)
 def InputStream(self,**options):
  self.opened.append(options.get('device'));return FakeStream(self.fail_all,**options)

class MicrophoneTests(unittest.TestCase):
 def test_only_wasapi_microphones_are_offered(self):
  self.assertEqual(m.inputs(FakeDevices()),[(1,'Headset mic'),(3,'Laptop mic')])
 def test_the_chosen_microphone_opens(self):
  sd=FakeDevices();mic=m.Microphone(m.MicMix(av),sd)
  self.assertTrue(mic.open('Headset mic'));self.assertTrue(mic.on);self.assertEqual(sd.opened,[1]);self.assertEqual(mic.name,'Headset mic')
  self.assertEqual(mic.stream.options['samplerate'],48000);self.assertEqual(mic.stream.options['extra_settings'],('wasapi',True))
  mic.close();self.assertFalse(mic.on)
 def test_a_missing_choice_takes_the_default(self):
  sd=FakeDevices();mic=m.Microphone(m.MicMix(av),sd)
  self.assertTrue(mic.open('Gone mic'));self.assertEqual(sd.opened,[None]);self.assertEqual(mic.name,'Laptop mic')
 def test_no_microphone_says_why(self):
  mic=m.Microphone(m.MicMix(av),FakeDevices(fail_all=True))
  self.assertFalse(mic.open(''));self.assertFalse(mic.on);self.assertEqual(mic.error,'Error opening InputStream: Invalid device')
 def test_the_callback_feeds_the_mix(self):
  mix=m.MicMix(av);mic=m.Microphone(mix,FakeDevices())
  mic.callback(np.ones((480,1),np.float32),480,None,None);self.assertEqual(mix.voice.held,480)

if __name__=='__main__':unittest.main()
