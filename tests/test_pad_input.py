import os,queue,socket,struct,sys,threading,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import pad_input as pad

class FakeSocket:
 def __init__(self,answers=()):self.sent=[];self.answers=list(answers)
 def sendto(self,data,address):self.sent.append((data,address))
 def recvfrom(self,size):
  if not self.answers:raise BlockingIOError
  answer=self.answers.pop(0)
  if isinstance(answer,Exception):raise answer
  return answer,('192.0.2.1',pad.PAD_PORT)
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
  # Pressing it to leave adds no controller on the PS5.
  self.assertEqual(drained(bridge.events),['leave']);self.assertEqual(udp.sent,[])
  # While playing, it is kept from the console.
  bridge.step(pad.PadState(pad.CROSS),1,udp);bridge.step(pad.PadState(pad.PS),1.01,udp)
  self.assertEqual(struct.unpack_from('<I',udp.sent[-1][0],8)[0],0);self.assertEqual(drained(bridge.events),['leave'])
 def test_outside_gaming_mode_the_ps_button_goes_to_the_console(self):
  bridge,udp=self.bridge(sending=True);bridge.step(pad.PadState(pad.PS),0,udp);self.assertEqual(drained(bridge.events),[]);self.assertEqual(struct.unpack_from('<I',udp.sent[0][0],8)[0],pad.PS)
 def test_a_controller_nobody_touches_adds_nothing_on_the_ps5(self):
  bridge,udp=self.bridge(sending=True)
  # Drifting sticks, a trigger touched lightly, and the Create button the way back to the grid starts with.
  for k,state in enumerate((pad.NEUTRAL,pad.PadState(lx=150,ly=110,rx=100,ry=155),pad.PadState(l2=20,r2=29),pad.PadState(pad.CREATE),pad.PadState(pad.CREATE|pad.OPTIONS))):
   bridge.step(state,k,udp)
  self.assertEqual(udp.sent,[]);self.assertEqual(bridge.link(5),'off')
  # The first real press joins, and that press is played.
  bridge.step(pad.PadState(lx=200),6,udp);self.assertEqual(len(udp.sent),1);self.assertEqual(udp.sent[0][0][12],200)
 def test_two_minutes_with_nothing_pressed_takes_the_controller_off_the_ps5_until_the_next_press(self):
  bridge,udp=self.bridge(sending=True);bridge.step(pad.PadState(pad.CROSS),0,udp)
  # Still pressed nothing, but within the two minutes: it stays, kept alive.
  bridge.step(pad.NEUTRAL,60,udp);bridge.step(pad.NEUTRAL,119.9,udp)
  self.assertEqual([data[:4] for data,_ in udp.sent],[b'PBP1']*3)
  bridge.step(pad.NEUTRAL,120,udp);self.assertEqual([data[:4] for data,_ in udp.sent[3:]],[b'PBQ1',b'PBQ1'])
  bridge.step(pad.NEUTRAL,125,udp);self.assertEqual(len(udp.sent),5);self.assertEqual(bridge.link(125),'off')
  bridge.step(pad.PadState(pad.CIRCLE),130,udp);self.assertEqual(udp.sent[-1][0][:4],b'PBP1');self.assertEqual(struct.unpack_from('<I',udp.sent[-1][0],8)[0],pad.CIRCLE)
 def test_coming_back_to_the_live_view_waits_for_a_press_again(self):
  bridge,udp=self.bridge(sending=True);bridge.step(pad.PadState(pad.CROSS),0,udp);bridge.navigating=True;bridge.step(pad.NEUTRAL,1,udp)
  bridge.navigating=False;bridge.step(pad.NEUTRAL,2,udp);bridge.step(pad.NEUTRAL,3,udp)
  self.assertEqual([data[:4] for data,_ in udp.sent],[b'PBP1',b'PBQ1',b'PBQ1'])
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
 def test_the_controller_is_read_every_4_ms_on_a_timer_that_waits_no_longer(self):
  # Windows rounds an Event's wait up to its 15.6 ms timer, which read a controller half as often as meant; a sleep is not rounded.
  self.assertEqual(pad.PadBridge.INTERVAL,.004)
  reads=[]
  class Pads:
   def find(self):return 'Test pad'
   def read(self):
    reads.append(time.perf_counter())
    if len(reads)>=60:stop.set()
    return pad.NEUTRAL
  stop=threading.Event();bridge=pad.PadBridge(lambda:'127.0.0.1',stop,Pads());bridge.name='Test pad';bridge.run()
  steps=sorted(b-a for a,b in zip(reads,reads[1:]));self.assertLess(steps[len(steps)//2],.012,steps)
class LinkTests(unittest.TestCase):
 def bridge(self):
  bridge=pad.PadBridge(lambda:'192.0.2.1',threading.Event());bridge.sending=True;return bridge
 def test_the_answer_round_trips(self):
  self.assertEqual(pad.read_status(pad.status_wire(pad.FAILED,-2137784317,7,0)),(pad.FAILED,-2137784317,7,0))
  self.assertEqual(pad.read_status(pad.status_wire(pad.READY,0,8,3)),(pad.READY,0,8,3))
  # The first companion's 16-byte answer is not taken for this one's.
  self.assertIsNone(pad.read_status(b'PBS1'+bytes(12)));self.assertIsNone(pad.read_status(b'PBS2'+bytes(12)));self.assertIsNone(pad.read_status(b'XXXX'+bytes(16)))
 def test_off_while_the_controller_is_not_playing(self):
  bridge=self.bridge();bridge.sending=False;bridge.step(pad.NEUTRAL,0,FakeSocket());self.assertEqual(bridge.link(0),'off')
 def test_no_answer_is_waiting_at_first_then_unavailable(self):
  bridge=self.bridge();udp=FakeSocket();bridge.step(pad.PadState(pad.CROSS),10,udp)
  self.assertEqual(bridge.link(11),'waiting');self.assertEqual(bridge.link(12.5),'unavailable')
  # Sending carried on all the same: the console side is never waited for.
  bridge.step(pad.NEUTRAL,12.5,udp);self.assertEqual(len(udp.sent),2)
 def test_answers_give_the_state_and_go_stale(self):
  bridge=self.bridge();bridge.step(pad.PadState(pad.CROSS),0,FakeSocket())
  for state,name in ((pad.STARTING,'starting'),(pad.READY,'ready'),(pad.FAILED,'failed'),(9,'unavailable')):
   bridge.listen(FakeSocket([pad.status_wire(state,0,1)]),1);self.assertEqual(bridge.link(1.5),name)
  bridge.listen(FakeSocket([pad.status_wire(pad.READY,0,1)]),2);self.assertEqual(bridge.link(4.5),'unavailable')
  # Ready with an error: the console turned the states down. It counts again once it takes one.
  bridge.listen(FakeSocket([pad.status_wire(pad.READY,-2137784317,2)]),5);self.assertEqual(bridge.link(5),'refused')
  bridge.listen(FakeSocket([pad.status_wire(pad.READY,0,3)]),5.1);self.assertEqual(bridge.link(5.1),'ready')
 def test_a_console_with_four_controllers_in_use_says_so_and_each_pc_hears_its_own_number(self):
  bridge=self.bridge();bridge.step(pad.PadState(pad.CROSS),0,FakeSocket());self.assertEqual(bridge.player(),0)
  bridge.listen(FakeSocket([pad.status_wire(pad.FAILED,pad.PAD_FULL,1,0)]),1);self.assertEqual((bridge.link(1),bridge.player()),('full',0))
  bridge.listen(FakeSocket([pad.status_wire(pad.FAILED,-2137784317,2,0)]),2);self.assertEqual(bridge.link(2),'failed')
  bridge.listen(FakeSocket([pad.status_wire(pad.READY,0,3,2)]),3);self.assertEqual((bridge.link(3),bridge.player()),('ready',2))
 def test_reading_never_waits_and_skips_noise_and_errors(self):
  bridge=self.bridge();bridge.step(pad.PadState(pad.CROSS),0,FakeSocket())
  bridge.listen(FakeSocket([ConnectionResetError(10054,'port closed'),b'junk',pad.status_wire(pad.READY,0,4)]),1)
  self.assertEqual(bridge.link(1),'ready');self.assertEqual(bridge.answer[2],4)
  bridge.listen(FakeSocket(),2);self.assertEqual(bridge.answer[2],4)
 def test_stopping_sends_the_leave_message_and_no_state_that_would_make_a_new_controller(self):
  # The companion lets go of what was held itself; a neutral state arriving after the leave message would add a controller again.
  bridge=self.bridge();udp=FakeSocket();bridge.step(pad.PadState(pad.CROSS|pad.R2,r2=255),0,udp)
  bridge.sending=False;bridge.step(pad.PadState(pad.CROSS|pad.R2,r2=255),.01,udp);bridge.step(pad.NEUTRAL,1,udp)
  self.assertEqual(udp.sent[1:],[(pad.QUIT,('192.0.2.1',pad.PAD_PORT))]*pad.PadBridge.QUIT_COPIES)
  # Going back to the grid stops it too.
  bridge=self.bridge();udp=FakeSocket();bridge.step(pad.PadState(pad.CROSS),0,udp);bridge.navigating=True;bridge.step(pad.PadState(pad.CROSS),.01,udp)
  self.assertEqual([data[:4] for data,_ in udp.sent],[b'PBP1',b'PBQ1',b'PBQ1'])
 def test_a_bridge_that_played_tells_the_console_side_to_remove_its_controller_when_it_stops(self):
  class Udp(FakeSocket):
   def __enter__(self):return self
   def __exit__(self,*_):return False
   def setblocking(self,_):pass
  stop=threading.Event()
  class Pads:
   def read(self):stop.set();return pad.PadState(pad.CROSS)
   def find(self):return 'pad'
  udp=Udp();bridge=pad.PadBridge(lambda:'192.0.2.1',stop,Pads());bridge.sending=True
  original=pad.socket.socket;pad.socket.socket=lambda *args:udp
  try:bridge.run()
  finally:pad.socket.socket=original
  self.assertEqual(udp.sent[0][0][:4],b'PBP1');self.assertEqual(udp.sent[-1],(pad.QUIT,('192.0.2.1',pad.PAD_PORT)))
 def test_the_real_socket_does_not_block(self):
  with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as udp:
   udp.setblocking(False);bridge=self.bridge();import time;start=time.perf_counter();bridge.listen(udp,0);self.assertLess(time.perf_counter()-start,.05)

class KeyboardTests(unittest.TestCase):
 def test_keys_make_a_controller_state(self):
  k=pad.Keyboard()
  for name in ('w','d','enter','q','2'):self.assertTrue(k.press(name,0))
  state=k.state();self.assertEqual(state.buttons,pad.CROSS|pad.SQUARE|pad.L2);self.assertEqual((state.lx,state.ly,state.rx,state.ry,state.l2,state.r2),(255,0,128,128,255,0))
  # Opposite keys cancel out, a release lets go, and keys that are not the controller's are left to the window.
  k.press('a',0);self.assertEqual(k.state().lx,128);k.release('d',0);self.assertEqual(k.state().lx,0)
  self.assertFalse(k.press('escape',0));self.assertFalse(k.press('f11',0));self.assertFalse(k.press('m',0))
  k.clear();self.assertEqual(k.state(),pad.NEUTRAL)
 def test_every_console_button_has_a_key(self):
  covered=0
  for bit in pad.KEY_BUTTONS.values():covered|=bit
  self.assertEqual(covered,pad.CONSOLE_BUTTONS)
  for name in pad.KEY_NAMES:self.assertIn(name.upper() if len(name)==1 else name,pad.KEYBOARD_HELP.replace('Enter','enter').replace('Space','space').replace('Backspace','backspace').replace('Tab','tab').replace('Home','home').replace('arrows','up down left right'))
 def test_the_keyboard_counts_as_in_use_for_a_while_after_the_last_key(self):
  k=pad.Keyboard();self.assertFalse(k.in_use(0));k.press('w',1);self.assertTrue(k.in_use(100));k.release('w',100);self.assertTrue(k.in_use(109));self.assertFalse(k.in_use(111))
 def test_a_controller_and_the_keyboard_play_together(self):
  both=pad.merge(pad.PadState(pad.CROSS,lx=10,ly=128,rx=200,r2=90),pad.PadState(pad.CIRCLE,lx=128,ly=0,rx=128,r2=255))
  self.assertEqual(both,pad.PadState(pad.CROSS|pad.CIRCLE,10,0,200,128,0,255))

class AttachedTests(unittest.TestCase):
 def bridge(self,**flags):
  sent=[];bridge=pad.PadBridge(lambda:'192.0.2.1',threading.Event(),companion=lambda:b'\x7fELF companion',send_elf=lambda host,data:sent.append((host,data)))
  for name,value in flags.items():setattr(bridge,name,value)
  return bridge,FakeSocket(),sent
 def wait_for(self,sent,count):
  import time
  end=time.monotonic()+2
  while len(sent)<count and time.monotonic()<end:time.sleep(.01)
 def test_off_the_live_view_nothing_makes_a_controller_on_the_ps5(self):
  bridge,udp,_=self.bridge(attached=True,navigating=True)
  bridge.step(pad.PadState(pad.CROSS),10,udp);bridge.step(pad.PadState(pad.CROSS),10.5,udp);bridge.step(pad.PadState(pad.CROSS),11.0,udp)
  self.assertEqual(udp.sent,[])
  # The grid still gets its moves.
  self.assertEqual(drained(bridge.events),['accept'])
 def test_while_attached_and_not_playing_it_only_asks_whether_a_companion_runs(self):
  bridge,udp,_=self.bridge(attached=True,sending=True)
  for now in (0,.5,1.0,1.5,2.0):bridge.watch_companion(now,udp)
  self.assertEqual(udp.sent,[(pad.PROBE,('192.0.2.1',pad.PAD_PORT))]*3)
  # While playing, the states' answers say it, so no question goes.
  bridge.step(pad.PadState(pad.CROSS),2.1,udp);bridge.watch_companion(3.5,udp);self.assertEqual([data[:4] for data,_ in udp.sent[3:]],[b'PBP1'])
 def test_the_companion_is_sent_once_nothing_answers_and_never_twice_at_once(self):
  bridge,udp,sent=self.bridge(attached=True)
  # Just attached, so the first press plays at once.
  bridge.watch_companion(10,udp);bridge.watch_companion(11.9,udp);self.assertEqual(sent,[])
  bridge.watch_companion(12,udp);self.wait_for(sent,1);self.assertEqual(sent,[('192.0.2.1',b'\x7fELF companion')])
  # Then nothing needs it until something plays.
  bridge.watch_companion(13,udp);bridge.watch_companion(500,udp);self.assertEqual(len(sent),1)
  # A phone playing with nothing answering gets one more try, then no more while attached.
  bridge.wanted=lambda now:True;bridge.watch_companion(501,udp);bridge.watch_companion(502.9,udp);self.assertEqual(len(sent),1)
  bridge.watch_companion(503.1,udp);self.wait_for(sent,2);self.assertEqual(len(sent),2)
  bridge.watch_companion(600,udp);bridge.watch_companion(700,udp);self.assertEqual(len(sent),2)
  # Only questions went to the console port, never a controller state.
  self.assertTrue(udp.sent and all(data==pad.PROBE for data,_ in udp.sent))
 def test_a_companion_that_started_well_and_ended_is_sent_again_when_someone_plays(self):
  bridge,udp,sent=self.bridge(attached=True);bridge.watch_companion(0,udp);bridge.watch_companion(2,udp);self.wait_for(sent,1)
  bridge.listen(FakeSocket([pad.status_wire(pad.READY,0,0,0)]),3);bridge.watch_companion(3.5,udp)
  # Ten idle minutes later it has ended on the PS5; this PC plays and nothing answers.
  bridge.sending=True;bridge.step(pad.PadState(pad.CROSS),700,udp);bridge.watch_companion(700,udp);bridge.watch_companion(702,udp);self.wait_for(sent,2)
  self.assertEqual(len(sent),2)
  # And again each time it has started well, beyond the two tries in a row.
  bridge.listen(FakeSocket([pad.status_wire(pad.READY,0,1,1)]),703);bridge.watch_companion(703,udp)
  bridge.step(pad.PadState(pad.CROSS),1500,udp);bridge.watch_companion(1500,udp);bridge.watch_companion(1502,udp);self.wait_for(sent,3)
  self.assertEqual(len(sent),3)
 def test_a_companion_that_answers_is_not_sent_again(self):
  bridge,udp,sent=self.bridge(attached=True);bridge.watch_companion(0,udp)
  bridge.listen(FakeSocket([pad.status_wire(pad.READY,0,1,1)]),1.5);bridge.watch_companion(2.5,udp);self.assertEqual(sent,[])
  # Another PC's companion answering counts the same: only one runs on the PS5.
  bridge.listen(FakeSocket([pad.status_wire(pad.STARTING,0,2,0)]),3);bridge.watch_companion(4.9,udp);self.assertEqual(sent,[])
 def test_a_missing_companion_says_so_and_a_failed_send_says_why(self):
  bridge,udp,sent=self.bridge(attached=True);bridge.companion=lambda:None;bridge.watch_companion(0,udp);bridge.watch_companion(2,udp)
  self.assertEqual(sent,[]);self.assertIn('missing',bridge.companion_note)
  def refuse(host,data):raise OSError('connection refused')
  bridge,udp,_=self.bridge(attached=True);bridge.send_elf=refuse;bridge.watch_companion(0,udp);bridge.watch_companion(2,udp)
  import time
  end=time.monotonic()+2
  while 'refused' not in bridge.companion_note and time.monotonic()<end:time.sleep(.01)
  self.assertIn('connection refused',bridge.companion_note)
 def test_turning_it_off_removes_this_pcs_controller_at_once_without_making_another(self):
  bridge,udp,_=self.bridge(attached=True,sending=True);bridge.watch_companion(0,udp);bridge.step(pad.PadState(pad.CROSS),0,udp)
  bridge.attached=False;bridge.sending=False;bridge.watch_companion(.1,udp);bridge.step(pad.PadState(pad.CROSS),.1,udp)
  self.assertEqual([data[:4] for data,_ in udp.sent],[b'PBH1',b'PBP1',b'PBQ1',b'PBQ1'])
  # Detached again later, nothing more is said.
  bridge.watch_companion(5,udp);bridge.step(pad.NEUTRAL,5,udp);self.assertEqual(len(udp.sent),4)
 def test_with_only_the_keyboard_the_live_view_plays(self):
  class Udp(FakeSocket):
   def __enter__(self):return self
   def __exit__(self,*_):return False
   def setblocking(self,_):pass
  stop=threading.Event();reads=[]
  class Pads:
   def read(self):
    reads.append(1)
    if len(reads)>3:stop.set()
    return None
   def find(self):return ''
  udp=Udp();bridge=pad.PadBridge(lambda:'192.0.2.1',stop,Pads());bridge.sending=True;bridge.keys_on=True;bridge.INTERVAL=.001
  bridge.keyboard.press('enter',__import__('time').monotonic())
  original=pad.socket.socket;pad.socket.socket=lambda *args:udp
  try:bridge.run()
  finally:pad.socket.socket=original
  played=[data for data,_ in udp.sent if data[:4]==b'PBP1']
  self.assertTrue(played);self.assertEqual(struct.unpack_from('<I',played[0],8)[0],pad.CROSS)

if __name__=='__main__':unittest.main()
