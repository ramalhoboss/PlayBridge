import argparse,json,os,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import graphics_card as g
import playbridge as core
from stream_metrics import export_diagnostics

def card(*sizes,name='Test Card 3000'):return {'name':name,'vendor':'AMD','decodes':{r:r in sizes for r in (4,5,6)}}
# A gaming laptop as Windows lists it: the processor's graphics first, because it drives the screen.
INTEL={'index':0,'name':'Intel(R) UHD Graphics','vendor':'Intel','memory':128}
NVIDIA={'index':1,'name':'NVIDIA GeForce RTX 3060 Laptop GPU','vendor':'NVIDIA','memory':5996}
def player(settings=None):
 with patch.object(core,'config',return_value=settings or {}):
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

class ChoiceTests(unittest.TestCase):
 def test_a_laptop_gets_its_nvidia_card_rather_than_the_one_windows_lists_first(self):
  self.assertEqual(g.automatic((INTEL,NVIDIA)),1);self.assertEqual(g.choose(g.AUTOMATIC,(INTEL,NVIDIA)),1)
 def test_a_card_chosen_in_settings_wins_and_a_missing_one_falls_back_to_automatic(self):
  self.assertEqual(g.choose('Intel(R) UHD Graphics',(INTEL,NVIDIA)),0)
  self.assertEqual(g.choose('A card taken out last week',(INTEL,NVIDIA)),1)
 def test_two_equal_cards_keep_windows_order_and_no_card_gives_the_default(self):
  self.assertEqual(g.automatic(({**NVIDIA,'index':0},NVIDIA)),0);self.assertIsNone(g.choose(g.AUTOMATIC,()))
 def test_settings_shows_the_card_by_name(self):
  self.assertEqual(g.label(1,(INTEL,NVIDIA)),'NVIDIA GeForce RTX 3060 Laptop GPU');self.assertEqual(g.label(None,(INTEL,NVIDIA)),'')
 def test_the_list_keeps_windows_order_and_leaves_out_its_software_renderer(self):
  listed={11:('Intel(R) UHD Graphics',0x8086,128),12:('NVIDIA GeForce RTX 3060 Laptop GPU',0x10de,5996),13:('Microsoft Basic Render Driver',0x1414,0)}
  def describe(adapter,desc):
   name,vendor,memory=listed[adapter];d=desc._obj;d.Description=name;d.VendorId=vendor;d.DedicatedVideoMemory=memory*2**20
  released=[];g.cards.cache_clear();self.addCleanup(g.cards.cache_clear)
  with patch.object(g,'adapters',return_value=[11,12,13]),patch.object(g,'GetAdapterDesc',describe),patch.object(g,'Release',released.append):found=g.cards()
  self.assertEqual(found,(INTEL,NVIDIA));self.assertEqual(released,[11,12,13])
 def test_a_pc_where_windows_lists_nothing_has_no_cards(self):
  g.cards.cache_clear();self.addCleanup(g.cards.cache_clear)
  with patch.object(g,'adapters',side_effect=OSError('no dxgi')):self.assertEqual(g.cards(),())
 def test_the_check_asks_the_chosen_card(self):
  g.probe.cache_clear();self.addCleanup(g.probe.cache_clear);asked=[]
  def refuse(adapter=None):asked.append(adapter);raise OSError('no device')
  with patch.object(g,'new_device',refuse):self.assertIsNone(g.probe(1))
  self.assertEqual(asked,[1])
 @unittest.skipUnless(sys.platform=='win32','Windows only')
 def test_this_pc_opens_a_device_on_the_automatic_card_and_on_a_place_it_does_not_have(self):
  from d3d11_presenter import Release,new_device
  if not g.cards():self.skipTest('no graphics card here')
  for place in (g.choose(g.AUTOMATIC),99):
   device=new_device(place);self.assertTrue(device);Release(device)
 def test_a_card_that_will_not_decode_leaves_the_default_one(self):
  tried=[]
  class Decoder:is_hwaccel=True;options=None
  def create(name,mode,hwaccel):
   tried.append(hwaccel['device'])
   if hwaccel['device']=='1':raise core.av.error.FFmpegError(22,'no device')
   return Decoder()
  with patch.object(core,'HWAccel',dict),patch.object(core.av.CodecContext,'create',create):self.assertIsInstance(core.gpu_decoder(0,True,1),Decoder)
  self.assertEqual(tried,['1',None])
 @unittest.skipUnless(sys.platform=='win32','Windows only')
 def test_a_card_direct3d_will_not_start_on_leaves_the_default_one(self):
  # Windows' software renderer has no video support, so it stands in for a card whose driver refuses.
  import ctypes
  from d3d11_presenter import Release,adapters,new_device
  listed=adapters();software=None
  for index,adapter in enumerate(listed):
   desc=g.AdapterDesc();g.GetAdapterDesc(adapter,ctypes.byref(desc));Release(adapter)
   if desc.VendorId==g.SOFTWARE and software is None:software=index
  if software is None or not g.cards():self.skipTest('no software renderer listed here')
  g.probe.cache_clear();self.addCleanup(g.probe.cache_clear)
  device=new_device(software);self.assertTrue(device);Release(device)
  self.assertEqual(g.probe(software)['name'],g.cards()[0]['name'])
 @unittest.skipUnless(sys.platform=='win32','Windows only')
 def test_the_decoder_opens_on_the_chosen_card(self):
  if not g.cards():self.skipTest('no graphics card here')
  if core.gpu_decoder(0,True) is None:self.skipTest('no hardware decoder here')
  self.assertIsNotNone(core.gpu_decoder(0,True,g.choose(g.AUTOMATIC)))

class PlayerTests(unittest.TestCase):
 def test_the_player_decodes_on_the_laptop_s_nvidia_card(self):
  asked=[]
  with patch.object(core.sys,'platform','win32'),patch.object(g,'cards',return_value=(INTEL,NVIDIA)):p=player()
  p.capture_info={'resolution':6}
  with patch.object(core,'gpu_decoder',lambda codec,on_gpu,adapter=None:asked.append(adapter)),patch.object(g,'probe',return_value=card(4,5,6)):p.video_decoder()
  self.assertEqual((p.adapter,asked),(1,[1]))
 def test_the_card_saved_in_settings_is_the_one_used(self):
  with patch.object(core.sys,'platform','win32'),patch.object(g,'cards',return_value=(INTEL,NVIDIA)):
   self.assertEqual(player({'graphics_card':'Intel(R) UHD Graphics'}).adapter,0)
 def test_a_failing_card_list_leaves_the_default_card(self):
  with patch.object(core.sys,'platform','win32'),patch.object(g,'choose',side_effect=RuntimeError('driver')):self.assertIsNone(player().adapter)
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
