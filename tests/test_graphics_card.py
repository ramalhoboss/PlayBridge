import argparse,json,os,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import graphics_card as g
import playbridge as core
from stream_metrics import export_diagnostics

def card(*sizes,name='Test Card 3000'):return {'name':name,'vendor':'AMD','decodes':{r:r in sizes for r in (4,5,6)}}
def player():
 with patch.object(core,'config',return_value={}):
  return core.Player(argparse.Namespace(renderer='auto',profile='uhd_balanced',auto_reconnect=False,device=None,connect_only=True,host='127.0.0.1',record=False,preview=False,headless=True,seconds=0))

class WordingTests(unittest.TestCase):
 def test_the_largest_size_counts_only_unbroken_from_1080p(self):
  self.assertEqual(g.largest(card(4,5,6)),6);self.assertEqual(g.largest(card(4,5)),5);self.assertEqual(g.largest(card(4)),4)
  self.assertEqual(g.largest(card()),0);self.assertEqual(g.largest(None),0);self.assertEqual(g.largest(card(4,6)),4)
 def test_settings_names_the_card_and_what_it_leaves_to_the_processor(self):
  self.assertEqual(g.summary(card(4,5,6)),'Graphics card: Test Card 3000. It decodes every profile, up to 4K.')
  self.assertIn('It decodes up to 1080p. Higher profiles are decoded by the processor',g.summary(card(4)))
  self.assertIn('cannot decode this video',g.summary(card()));self.assertIn('No graphics card answered',g.summary(None))
 def test_the_processor_notice_is_only_for_1440p_and_4k(self):
  self.assertEqual(g.processor_notice(4,card()),'');self.assertEqual(g.processor_notice(4,None),'')
 def test_the_notice_suggests_the_largest_size_the_card_decodes(self):
  self.assertIn('cannot decode 4K',g.processor_notice(6,card(4,5)));self.assertIn('choose a 1440p profile',g.processor_notice(6,card(4,5)))
  self.assertIn('choose a 1080p profile',g.processor_notice(5,None))
 def test_a_card_that_can_decode_is_told_apart_from_one_that_cannot(self):
  self.assertIn('stopped decoding 4K',g.processor_notice(6,card(4,5,6)))
 def test_the_report_holds_the_model_and_nothing_else(self):
  self.assertEqual(g.report(card(4,5)),{'graphics_card':'Test Card 3000','graphics_vendor':'AMD','gpu_decodes_up_to':'1440p'})
  self.assertEqual(g.report(None),{'graphics_card':None,'graphics_vendor':None,'gpu_decodes_up_to':None})

class CardTests(unittest.TestCase):
 def setUp(self):g.probe.cache_clear()
 def tearDown(self):g.probe.cache_clear()
 def test_this_pc_names_its_card_and_decodes_1080p(self):
  found=g.probe()
  if found is None:self.skipTest('no Direct3D 11 here')
  self.assertTrue(found['name']);self.assertTrue(found['decodes'][4]);self.assertEqual(set(found['decodes']),{4,5,6})
 def test_the_check_says_no_above_the_cards_limit(self):
  # No card decodes H.264 at 16384 by 16384, so a check that always said yes would fail here.
  from ctypes import byref,c_void_p
  from d3d11_presenter import QueryInterface,Release,new_device
  try:device=new_device()
  except OSError:self.skipTest('no Direct3D 11 here')
  video=c_void_p()
  try:
   try:QueryInterface(device,g.IID_VIDEO_DEVICE,byref(video))
   except OSError:self.skipTest('no video decoder here')
   self.assertTrue(g.decodes(video.value,1920,1088));self.assertFalse(g.decodes(video.value,16384,16384))
  finally:
   if video.value:Release(video.value)
   Release(device)
 def test_no_direct3d_gives_no_card_rather_than_an_error(self):
  with patch.object(g,'new_device',side_effect=OSError('no device')):self.assertIsNone(g.probe())

class PlayerTests(unittest.TestCase):
 def test_4k_on_the_processor_says_so_and_names_a_size_that_works(self):
  p=player();p.capture_info={'resolution':6}
  with patch.object(core,'gpu_decoder',return_value=None),patch.object(g,'probe',return_value=card(4)):p.video_decoder()
  self.assertEqual(p.decoder_name,'software');self.assertIn('cannot decode 4K',p.notice);self.assertIn('1080p profile',p.notice)
 def test_1080p_on_the_processor_says_nothing(self):
  p=player();p.capture_info={'resolution':4}
  with patch.object(core,'gpu_decoder',return_value=None),patch.object(g,'probe',return_value=card()):p.video_decoder()
  self.assertEqual(p.notice,'')
 def test_a_failing_card_check_never_stops_the_stream(self):
  p=player()
  with patch.object(g,'probe',side_effect=RuntimeError('driver')):self.assertIsNone(p.graphics())
 def test_exported_diagnostics_carry_the_card(self):
  snapshot={'presented_fps':60,**g.report(card(4,5,6)),'video_decoder':'gpu'}
  with tempfile.TemporaryDirectory() as folder:
   with zipfile.ZipFile(export_diagnostics(Path(folder)/'report.zip',snapshot)) as z:stats=json.loads(z.read('diagnostics.json'))['stats']
  self.assertEqual((stats['graphics_card'],stats['graphics_vendor'],stats['gpu_decodes_up_to'],stats['video_decoder']),('Test Card 3000','AMD','4K','gpu'))

if __name__=='__main__':unittest.main()
