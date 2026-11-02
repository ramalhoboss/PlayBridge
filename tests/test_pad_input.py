import os,queue,socket,struct,sys,threading,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import pad_input as pad

class FakeSocket:
 def __init__(self):self.sent=[]
 def sendto(self,data,address):self.sent.append((data,address))
def drained(events):
 result=[]
 while not events.empty():result.append(events.get_nowait())
 return result

class MappingTests(unittest.TestCase):
 def test_xbox_buttons_land_on_the_console_positions(self):
  for mask,bit in ((0x1000,pad.CROSS),(0x2000,pad.CIRCLE),(0x4000,pad.SQUARE),(0x8000,pad.TRIANGLE),(0x100,pad.L1),(0x200,pad.R1),(0x10,pad.OPTIONS),(0x20,pad.CREATE),(0x40,pad.L3),(0x80,pad.R3),(0x1,pad.UP),(0x2,pad.DOWN),(0x4,pad.LEFT),(0x8,pad.RIGHT),(0x400,pad.PS)):
   self.assertEqual(pad.from_xinput(mask,0,0,0,0,0,0).buttons,bit,hex(mask))
 def test_xbox_sticks_turn_over_and_triggers_press(self):
  state=pad.from_xinput(0,255,29,-32768,32767,32767,-32768)
  self.assertEqual((state.lx,state.ly,state.rx,state.ry),(0,0,255,255));self.assertEqual((state.l2,state.r2),(255,29));self.assertEqual(state.buttons,pad.L2)
  self.assertEqual(pad.from_xinput(0,0,0,0,0,0,0)[1:5],(128,127,128,127))
 def test_dualsense_buttons_and_axes_as_windows_reports_them(self):
  for index,bit in enumerate((pad.SQUARE,pad.CROSS,pad.CIRCLE,pad.TRIANGLE,pad.L1,pad.R1,pad.L2,pad.R2,pad.CREATE,pad.OPTIONS,pad.L3,pad.R3,pad.PS,pad.TOUCHPAD)):
   self.assertEqual(pad.from_joystick(1<<index,65535,0,0,0,0,0,0).buttons,bit,index)
  self.assertEqual(pad.from_joystick(0,65535,0,65535,32768,4096,65535,256)[1:],(0,255,128,16,255,1))
 def test_the_hat_covers_the_diagonals_and_rests_at_65535(self):
  for pov,bits in ((0,pad.UP),(4500,pad.UP|pad.RIGHT),(9000,pad.RIGHT),(13500,pad.RIGHT|pad.DOWN),(18000,pad.DOWN),(22500,pad.DOWN|pad.LEFT),(27000,pad.LEFT),(31500,pad.LEFT|pad.UP),(65535,0)):self.assertEqual(pad.pov_bits(pov),bits,pov)
 def test_the_packet_has_the_size_the_payload_checks_and_only_console_buttons(self):
  data=pad.wire(5,pad.PadState(pad.CROSS|pad.CREATE|0x40000000,1,2,3,4,5,6))
  self.assertEqual(len(data),20);self.assertEqual(struct.unpack_from('<4sII',data),(b'PBP1',5,pad.CROSS));self.assertEqual(data[12:18],bytes((1,2,3,4,5,6)))
 def test_the_sequence_number_wraps(self):self.assertEqual(struct.unpack_from('<I',pad.wire(1<<32,pad.NEUTRAL),4)[0],0)

class NavigationTests(unittest.TestCase):
 def test_a_press_moves_once_and_a_held_direction_repeats(self):
  n=pad.Navigator();held=pad.PadState(pad.RIGHT)
  self.assertEqual(n.update(held,0),['right']);self.assertEqual(n.update(held,.2),[]);self.assertEqual(n.update(held,.41),['right']);self.assertEqual(n.update(held,.5),[]);self.assertEqual(n.update(held,.56),['right'])
  self.assertEqual(n.update(pad.NEUTRAL,.6),[]);self.assertEqual(n.update(held,.61),['right'])
 def test_buttons_fire_once_however_long_they_are_held(self):
  n=pad.Navigator();held=pad.PadState(pad.CROSS);self.assertEqual(n.update(held,0),['accept']);self.assertEqual(n.update(held,5),[])
 def test_the_left_stick_navigates_only_past_a_clear_push(self):
  n=pad.Navigator();self.assertEqual(n.update(pad.PadState(lx=100,ly=150),0),[]);self.assertEqual(n.update(pad.PadState(lx=128,ly=10),.1),['up'])
 def test_holding_options_and_create_leaves_once(self):
  c=pad.HomeCombo();both=pad.PadState(pad.OPTIONS|pad.CREATE)
  self.assertFalse(c.update(both,0));self.assertFalse(c.update(both,.9));self.assertTrue(c.update(both,1.0));self.assertFalse(c.update(both,3));self.assertFalse(c.update(pad.NEUTRAL,3.1));self.assertFalse(c.update(both,4));self.assertTrue(c.update(both,5))
  self.assertFalse(c.update(pad.PadState(pad.OPTIONS),9))

class BridgeTests(unittest.TestCase):
 def bridge(self,**flags):
  bridge=pad.PadBridge(lambda:'192.0.2.1',threading.Event())
  for name,value in flags.items():setattr(bridge,name,value)
  return bridge,FakeSocket()
 def test_nothing_is_sent_while_the_grid_or_no_link_owns_the_controller(self):
  for flags in ({'sending':False},{'sending':True,'navigating':True}):
   bridge,udp=self.bridge(**flags);bridge.step(pad.PadState(pad.CROSS),0,udp);self.assertEqual(udp.sent,[],flags)
 def test_a_change_goes_at_once_and_a_still_controller_only_stays_alive(self):
  bridge,udp=self.bridge(sending=True);state=pad.PadState(pad.CROSS)
  bridge.step(state,0,udp);bridge.step(state,.01,udp);self.assertEqual(len(udp.sent),1)
  bridge.step(state,.06,udp);self.assertEqual(len(udp.sent),2);bridge.step(pad.NEUTRAL,.061,udp);self.assertEqual(len(udp.sent),3)
  self.assertEqual(udp.sent[0][1],('192.0.2.1',pad.PAD_PORT));self.assertEqual([struct.unpack_from('<I',data,4)[0] for data,_ in udp.sent],[0,1,2])
 def test_the_grid_gets_moves_and_the_ps_button(self):
  bridge,udp=self.bridge(navigating=True);bridge.step(pad.PadState(pad.DOWN),0,udp);bridge.step(pad.PadState(pad.DOWN|pad.PS),.01,udp);bridge.step(pad.PadState(pad.DOWN|pad.PS),.02,udp)
  self.assertEqual(drained(bridge.events),['down','leave'])
 def test_in_gaming_mode_the_ps_button_comes_back_to_the_grid_instead_of_the_console_menu(self):
  bridge,udp=self.bridge(sending=True,ps_leaves=True);bridge.step(pad.PadState(pad.PS),0,udp)
  self.assertEqual(drained(bridge.events),['leave']);self.assertEqual(struct.unpack_from('<I',udp.sent[0][0],8)[0],0)
 def test_outside_gaming_mode_the_ps_button_goes_to_the_console(self):
  bridge,udp=self.bridge(sending=True);bridge.step(pad.PadState(pad.PS),0,udp);self.assertEqual(drained(bridge.events),[]);self.assertEqual(struct.unpack_from('<I',udp.sent[0][0],8)[0],pad.PS)
 def test_a_network_error_does_not_end_the_thread(self):
  class Broken:
   def sendto(self,data,address):raise OSError('no route')
  bridge,_=self.bridge(sending=True);bridge.step(pad.PadState(pad.CROSS),0,Broken());self.assertIsNone(bridge.sent)
 def test_a_controller_leaving_and_coming_back_is_followed(self):
  class Pads:
   def __init__(self):self.reads=[pad.NEUTRAL,None,None];self.finds=['Controller','']
   def read(self):return self.reads.pop(0) if self.reads else stop.set()
   def find(self):return self.finds.pop(0) if self.finds else ''
  stop=threading.Event();bridge=pad.PadBridge(lambda:'127.0.0.1',stop,Pads());bridge.LOOK_AGAIN=.01;bridge.INTERVAL=.001;bridge.run();self.assertEqual(bridge.name,'')
if __name__=='__main__':unittest.main()
