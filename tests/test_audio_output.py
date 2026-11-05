"""Opening the sound output on a PC whose output mixes at a rate other than the stream's 48 kHz, or will not open at all."""
import collections,os,sys,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import sounddevice as sd
import audio_output
import playbridge as core

APIS=({'name':'MME','default_output_device':0},{'name':'Windows WASAPI','default_output_device':3},{'name':'Windows DirectSound','default_output_device':4},
      {'name':'Windows WDM-KS','default_output_device':-1})
DEVICES={0:{'name':'Speakers (MME)','hostapi':0},2:{'name':'Headphones','hostapi':1},3:{'name':'Speakers','hostapi':1},4:{'name':'Speakers (DirectSound)','hostapi':2}}
for info in DEVICES.values():info.update(max_output_channels=2,default_samplerate=44100.0)
def query_devices(device=None,kind=None):return DEVICES[0 if device is None else device]
def query_hostapis(index=None):return APIS if index is None else APIS[index]
REFUSAL='Error opening RawOutputStream: Invalid sample rate [PaErrorCode -9997]'

class FakeStream:
 """Refuses the outputs in refused like a 44.1 kHz WASAPI output refuses 48 kHz without conversion."""
 refused=set()
 def __init__(self,device=None,extra_settings=None,**_):
  if device in self.refused:raise sd.PortAudioError(REFUSAL)
  self.device=device;self.extra=extra_settings;self.latency=.01;self.closed=False
 def start(self):pass
 def stop(self):pass
 def close(self):self.closed=True

def fake_sound(test):
 for name,fake in (('query_devices',query_devices),('query_hostapis',query_hostapis)):
  p=patch.object(audio_output.sd,name,side_effect=fake);p.start();test.addCleanup(p.stop)

class OutputSettingsTests(unittest.TestCase):
 def setUp(self):fake_sound(self)
 def test_a_wasapi_output_lets_windows_convert_the_rate(self):
  settings=audio_output.output_settings(3)
  self.assertIsInstance(settings,sd.WasapiSettings)
  self.assertTrue(settings._streaminfo.flags&0x40)  # paWinWasapiAutoConvert
 def test_other_host_apis_get_no_settings(self):
  self.assertIsNone(audio_output.output_settings(0))
  self.assertIsNone(audio_output.output_settings(None))
 def test_the_chosen_output_comes_first_then_the_wasapi_directsound_and_mme_defaults(self):
  self.assertEqual(audio_output.candidates(2),[2,3,4,0])
  self.assertEqual(audio_output.candidates(None),[3,4,0])
  self.assertEqual(audio_output.candidates(4),[4,3,0])
 def test_the_reason_leaves_out_portaudio_s_code(self):
  self.assertEqual(audio_output.describe(sd.PortAudioError(REFUSAL)),'Error opening RawOutputStream: Invalid sample rate')
 def test_the_check_names_each_refusal_and_the_output_that_opened(self):
  report=audio_output.check_report([(2,sd.PortAudioError(REFUSAL))],4,.12,'2026-11-05 20:00:00')
  self.assertIn('Refused: Headphones [Windows WASAPI], 2 channels, 44100 Hz: Error opening RawOutputStream: Invalid sample rate',report)
  self.assertIn('Opened: Speakers (DirectSound) [Windows DirectSound], 2 channels, 44100 Hz, delay 120 ms',report)
  self.assertIn('No output opened',audio_output.check_report([],None,None,'now'))

class OpenAudioTests(unittest.TestCase):
 def setUp(self):
  fake_sound(self);FakeStream.refused=set();folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup);self.state=Path(folder.name)
  for target,name,value in ((core.sd,'RawOutputStream',FakeStream),(core,'STATE',self.state),(core,'output_settings',lambda d:('convert',d)),
                            (core,'candidates',lambda chosen:[d for d in dict.fromkeys((chosen,3,4,0)) if d is not None])):
   p=patch.object(target,name,value);p.start();self.addCleanup(p.stop)
 def player(self,device=2):
  notices=[]
  p=SimpleNamespace(audio=None,lock=threading.Lock(),pcm=bytearray(b'old'),stats=collections.Counter(),output_name='',notice_until=0,
                    audio_callback=lambda *a:None,device=lambda:device,notify=notices.append)
  p.audio_check=lambda *a:core.Player.audio_check(p,*a)
  return p,notices
 def check(self):
  path=self.state/'audio-check.txt';return path.read_text(encoding='utf8') if path.exists() else None
 def test_the_chosen_output_opens_with_conversion_and_writes_no_check(self):
  p,notices=self.player()
  self.assertTrue(core.Player.open_audio(p))
  self.assertEqual((p.audio.device,p.audio.extra,p.output_name,p.stats['output_device']),(2,('convert',2),'Headphones',2))
  self.assertEqual((notices,bytes(p.pcm),self.check()),([],b'',None))
 def test_a_refused_output_falls_back_to_the_windows_default(self):
  FakeStream.refused={2};p,notices=self.player()
  self.assertTrue(core.Player.open_audio(p))
  self.assertEqual((p.audio.device,p.output_name,notices),(3,'Speakers',[]))
  self.assertIn('Refused: Headphones',self.check())
 def test_when_wasapi_refuses_directsound_plays(self):
  FakeStream.refused={2,3};p,notices=self.player()
  self.assertTrue(core.Player.open_audio(p))
  self.assertEqual((p.audio.device,p.audio.extra,notices),(4,('convert',4),[]))
  check=self.check();self.assertIn('Refused: Headphones',check);self.assertIn('Refused: Speakers [Windows WASAPI]',check);self.assertIn('Opened: Speakers (DirectSound)',check)
 def test_with_every_output_refused_the_app_still_opens_without_sound(self):
  FakeStream.refused={0,2,3,4};p,notices=self.player()
  self.assertFalse(core.Player.open_audio(p))
  self.assertIsNone(p.audio);self.assertEqual(p.output_name,'');self.assertIsNone(p.stats['output_device'])
  self.assertEqual(notices,['No sound: Error opening RawOutputStream: Invalid sample rate. Choose another output in the audio menu.'])
  self.assertEqual(self.check().count('Refused:'),4);self.assertIn('No output opened',self.check())
 def test_a_new_output_replaces_the_one_playing(self):
  p,_=self.player();core.Player.open_audio(p);first=p.audio
  core.Player.open_audio(p,3)
  self.assertTrue(first.closed);self.assertEqual(p.audio.device,3)
 def test_a_pc_without_any_output_still_opens(self):
  p,notices=self.player(device=None)
  with patch.object(core,'candidates',lambda chosen:[None]),patch.object(core.sd,'RawOutputStream',side_effect=sd.PortAudioError('Error querying device -1')):
   self.assertFalse(core.Player.open_audio(p))
  self.assertEqual(len(notices),1)

if __name__=='__main__':unittest.main()
