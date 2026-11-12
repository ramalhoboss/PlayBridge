import os,sys,tempfile,time,unittest,wave
from pathlib import Path
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import numpy as np
import sound_board as board

def silent_board(**options):
 """A board that never opens a device."""
 made=board.SoundBoard(**options);made.broken=True;return made
class SoundTests(unittest.TestCase):
 def test_cues_are_stereo_short_and_never_clip(self):
  for name,cue in board.cue_sounds().items():
   self.assertEqual(cue.shape[1],2,name);self.assertLess(len(cue),board.RATE*1.2,name);self.assertLess(np.abs(cue).max(),.5,name);self.assertLess(abs(float(cue[0,0])),.01,name);self.assertLess(abs(float(cue[-1,0])),.01,name)
 def test_moving_between_covers_is_the_shortest_cue(self):
  cues=board.cue_sounds();self.assertEqual(min(cues,key=lambda name:len(cues[name])),'move')
 def test_the_music_is_quiet_and_joins_up_when_it_repeats(self):
  music=board.ambient_loop(8);self.assertEqual(music.shape,(8*board.RATE,2));self.assertAlmostEqual(float(np.sqrt(np.mean(music**2))),.075,places=2);self.assertLess(np.abs(music).max(),.6)
  # The step across the join is no bigger than the steps inside the music.
  self.assertLess(np.abs(music[0]-music[-1]).max(),np.abs(np.diff(music,axis=0)).max()*1.5)
 def test_a_cue_plays_only_while_the_library_shows_and_only_if_switched_on(self):
  sounds=silent_board();self.addCleanup(sounds.close);sounds.play('move');self.assertEqual(sounds.voices,[])
  sounds.shown=True;sounds.effects_on=False;sounds.play('move');self.assertEqual(sounds.voices,[]);sounds.effects_on=True;sounds.play('nothing');self.assertEqual(sounds.voices,[])
  sounds.play('move');self.assertEqual(len(sounds.voices),1)
  self.assertGreater(np.abs(sounds.mix(1024)).max(),0)
  for _ in range(10):sounds.mix(1024)
  self.assertEqual(sounds.voices,[])
 def test_many_quick_moves_keep_a_small_number_of_voices(self):
  sounds=silent_board();self.addCleanup(sounds.close);sounds.shown=True
  for _ in range(40):sounds.play('accept')
  self.assertEqual(len(sounds.voices),board.VOICES);self.assertLessEqual(np.abs(sounds.mix(1024)).max(),1)
 def test_the_music_fades_in_only_when_wanted_and_fades_out_when_it_is_not(self):
  sounds=silent_board();self.addCleanup(sounds.close);sounds.track=np.full((board.RATE,2),.1,dtype=np.float32);self.assertEqual(np.abs(sounds.mix(1024)).max(),0)
  sounds.shown=True;sounds.music_wanted=True;first=sounds.mix(1024);self.assertLess(abs(float(first[0,0])),.001);self.assertGreater(float(first[-1,0]),0)
  for _ in range(100):sounds.mix(1024)
  self.assertEqual(sounds.gain,1)
  sounds.music_on=False
  for _ in range(100):sounds.mix(1024)
  self.assertEqual(sounds.gain,0);self.assertEqual(np.abs(sounds.mix(1024)).max(),0);self.assertTrue(sounds.quiet())
 def test_a_new_track_comes_in_as_the_old_one_goes(self):
  sounds=silent_board();self.addCleanup(sounds.close);sounds.shown=True;sounds.music_wanted=True;sounds.track=np.full((board.RATE,2),.1,dtype=np.float32);sounds.gain=1.0;sounds.volume=1.0
  sounds.swap=np.full((board.RATE,2),.1,dtype=np.float32);first=sounds.mix(1024);self.assertIsNone(sounds.swap);self.assertAlmostEqual(float(first[0,0]),.1,places=3);self.assertIsNotNone(sounds.leaving);self.assertFalse(sounds.quiet())
  levels=[float(np.abs(sounds.mix(1024)).max()) for _ in range(120)];self.assertIsNone(sounds.leaving);self.assertLess(max(levels),.21);self.assertAlmostEqual(levels[-1],.1,places=2)
 def test_a_track_with_nothing_playing_just_starts(self):
  sounds=silent_board();self.addCleanup(sounds.close);sounds.shown=True;sounds.music_wanted=True;sounds.swap=np.full((board.RATE,2),.1,dtype=np.float32);sounds.mix(1024);self.assertIsNone(sounds.leaving);self.assertGreater(sounds.gain,0)
 def test_a_games_music_is_turned_down_faded_at_its_ends_and_a_bad_file_leaves_the_apps_own(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'snd0.wav'
   with wave.open(str(path),'wb') as out:out.setnchannels(2);out.setsampwidth(2);out.setframerate(board.RATE);out.writeframes((np.sin(np.arange(board.RATE*4)*.05)*30000).astype('<i2').repeat(2).tobytes())
   track=board.game_track(path);self.assertAlmostEqual(float(np.sqrt(np.mean(track**2))),board.GAME_LEVEL,delta=.01);self.assertEqual(float(track[0,0]),0);self.assertLess(abs(float(track[-1,0])),.01)
   # A track in any other order makes every block of sound copy all of it, and the output runs dry.
   self.assertTrue(track.flags.c_contiguous);self.assertTrue(board.read_audio(path).flags.c_contiguous)
   # Quiet music comes up to the same level, and a sharp peak holds it back before it clips.
   quiet=Path(tmp)/'quiet.wav'
   with wave.open(str(quiet),'wb') as out:out.setnchannels(2);out.setsampwidth(2);out.setframerate(board.RATE);out.writeframes((np.sin(np.arange(board.RATE*4)*.05)*1500).astype('<i2').repeat(2).tobytes())
   self.assertAlmostEqual(float(np.sqrt(np.mean(board.game_track(quiet)**2))),board.GAME_LEVEL,delta=.01)
   sharp=Path(tmp)/'sharp.wav';samples=(np.sin(np.arange(board.RATE*4)*.05)*300);samples[board.RATE*2]=30000
   with wave.open(str(sharp),'wb') as out:out.setnchannels(2);out.setsampwidth(2);out.setframerate(board.RATE);out.writeframes(samples.astype('<i2').repeat(2).tobytes())
   self.assertLessEqual(float(np.abs(board.game_track(sharp)).max()),board.GAME_PEAK+.001)
   sounds=silent_board();self.addCleanup(sounds.close);own=np.full((64,2),.1,dtype=np.float32);sounds.own_track=own
   sounds.want_track(path);sounds.load_track();self.assertEqual(len(sounds.swap),len(track));sounds.track=sounds.swap;sounds.swap=None
   bad=Path(tmp)/'bad.at9';bad.write_bytes(b'not audio');sounds.want_track(bad);sounds.load_track();self.assertIs(sounds.swap,own)
   sounds.track=own;sounds.swap=None;sounds.want_track(None);sounds.load_track();self.assertIsNone(sounds.swap)
   # Back to a track already decoded takes no decoding.
   sounds.want_track(path);before=dict(sounds.kept);sounds.load_track();self.assertIs(sounds.swap,before[board.file_key(path)])
   # A track the console replaced under the same name is decoded again.
   old=sounds.track=sounds.swap;sounds.swap=None;moved=path.stat().st_mtime_ns+10**9;os.utime(path,ns=(moved,moved));sounds.load_track()
   self.assertIsNotNone(sounds.swap);self.assertIsNot(sounds.swap,old);self.assertIn(board.file_key(path),sounds.kept)
 def test_the_volume_scales_everything(self):
  sounds=silent_board(volume=.5);self.addCleanup(sounds.close);sounds.track=np.full((board.RATE,2),.2,dtype=np.float32);sounds.gain=1.0;sounds.shown=True;sounds.music_wanted=True
  self.assertAlmostEqual(float(sounds.mix(64)[32,0]),.1,places=4)
 def test_the_loop_wraps_around_the_end_of_the_track(self):
  sounds=silent_board();self.addCleanup(sounds.close);track=np.zeros((100,2),dtype=np.float32);track[:,0]=np.arange(100)/100;sounds.track=track;sounds.gain=1.0;sounds.shown=True;sounds.music_wanted=True;sounds.at=95
  self.assertAlmostEqual(float(sounds.mix(10)[5,0])/sounds.volume,0,places=5);self.assertEqual(sounds.at,5)
 def test_an_output_that_cannot_open_leaves_the_app_silent_and_running(self):
  sounds=board.SoundBoard(device=lambda:'no such device');self.addCleanup(sounds.close);sounds.show(True)
  deadline=time.monotonic()+5
  while not sounds.broken and time.monotonic()<deadline:time.sleep(.02)
  self.assertTrue(sounds.broken);self.assertIsNone(sounds.stream)
if __name__=='__main__':unittest.main()
