import base64,http.client,io,json,os,queue,socket,struct,sys,tempfile,threading,time,unittest
from fractions import Fraction
from unittest import mock
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import av
import pad_input as pad
from media_capture import strip_adts
import phone_link as phone

def masked(opcode,data,mask=b'\x11\x22\x33\x44'):
 n=len(data);head=bytes([0x80|opcode])
 if n<126:head+=bytes([0x80|n])
 elif n<65536:head+=bytes([0x80|126])+struct.pack('>H',n)
 else:head+=bytes([0x80|127])+struct.pack('>Q',n)
 return head+mask+bytes(b^mask[i&3] for i,b in enumerate(data))
def h264_packets(count=12,gop=4,size=(256,144)):
 """Annex B H.264 as the PS5 sends it: headers before each picture that needs no other."""
 context=av.CodecContext.create('libx264','w');context.width,context.height=size;context.pix_fmt='yuv420p';context.time_base=Fraction(1,60)
 context.gop_size=gop;context.max_b_frames=0;context.options={'preset':'ultrafast','tune':'zerolatency'}
 frame=av.VideoFrame(size[0],size[1],'yuv420p');packets=[]
 for index in range(count):
  for plane in frame.planes:plane.update(bytes([index*9%255])*plane.buffer_size)
  frame.pts=index;packets+=[bytes(p) for p in context.encode(frame)]
 return packets+[bytes(p) for p in context.encode(None)]
def adts_frames(count=16):
 out=io.BytesIO();container=av.open(out,'w',format='adts');stream=container.add_stream('aac',rate=48000);stream.layout='stereo'
 frame=av.AudioFrame(format='fltp',layout='stereo',samples=1024);frame.sample_rate=48000
 for plane in frame.planes:plane.update(bytes(plane.buffer_size))
 for index in range(count):
  frame.pts=index*1024
  for packet in stream.encode(frame):container.mux(packet)
 for packet in stream.encode(None):container.mux(packet)
 container.close();data=out.getvalue();frames=[];at=0
 while at+7<=len(data):
  size=((data[at+3]&3)<<11)|(data[at+4]<<3)|(data[at+5]>>5);frames.append(data[at:at+size]);at+=size
 return frames
def stream_packets(video,audio):
 """The player's packets in arrival order: video at 60 fps and sound every 1024 samples, on the PS5's 90 kHz clock."""
 items=[(1,data,1000+index*1500) for index,data in enumerate(video)]+[(2,data,1000+index*1920) for index,data in enumerate(audio)]
 return sorted(items,key=lambda item:item[2])
def video_starts(fragment):
 """When each video sample in a fragment starts (its tfdt), on the 90 kHz clock."""
 out=[]
 for kind,start,end in phone.boxes(fragment,8):
  if kind!='traf':continue
  tfhd=phone.child(fragment,start,end,'tfhd');tfdt=phone.child(fragment,start,end,'tfdt')
  if struct.unpack_from('>I',fragment,tfhd[0]+12)[0]!=1:continue
  out.append(struct.unpack_from('>Q' if fragment[tfdt[0]+8] else '>I',fragment,tfdt[0]+12)[0])
 return out
def sample_lengths_in(fragment):
 """(track, length) of every sample in a fragment, from its trun or its tfhd's default."""
 out=[]
 for kind,start,end in phone.boxes(fragment,8):
  if kind!='traf':continue
  tfhd=phone.child(fragment,start,end,'tfhd');trun=phone.child(fragment,start,end,'trun')
  flags=struct.unpack_from('>I',fragment,tfhd[0]+8)[0]&0xffffff;track=struct.unpack_from('>I',fragment,tfhd[0]+12)[0];at=tfhd[0]+16;default=None
  for bit,size in ((0x1,8),(0x2,4)):
   if flags&bit:at+=size
  if flags&0x8:default=struct.unpack_from('>I',fragment,at)[0]
  flags=struct.unpack_from('>I',fragment,trun[0]+8)[0]&0xffffff;count=struct.unpack_from('>I',fragment,trun[0]+12)[0];at=trun[0]+16
  if flags&0x1:at+=4
  if flags&0x4:at+=4
  for _ in range(count):
   length=default
   if flags&0x100:length=struct.unpack_from('>I',fragment,at)[0]
   at+=4*sum(1 for bit in (0x100,0x200,0x400,0x800) if flags&bit)
   out.append((track,length))
 return out
def drain(viewer,seconds=8,until=None):
 items=[];end=time.monotonic()+seconds
 while time.monotonic()<end:
  item=viewer.take(.1)
  if item is not None:
   items.append(item)
   if until and until(items):break
 return items

class WebSocketTests(unittest.TestCase):
 def test_the_handshake_key_is_the_rfc_example(self):self.assertEqual(phone.accept_key('dGhlIHNhbXBsZSBub25jZQ=='),'s3pPLMBiTxaQ9kYGzzhZRbK+xOo=')
 def test_frames_carry_their_length_in_the_three_sizes(self):
  for size,head in ((125,2),(126,4),(70000,10)):
   frame=phone.ws_frame(phone.BINARY,bytes(size));self.assertEqual(len(frame),size+head);self.assertEqual(frame[0],0x82)
 def test_a_masked_frame_from_the_phone_reads_back(self):
  self.assertEqual(phone.ws_read(io.BytesIO(masked(phone.TEXT,b'{"b":1}'))),(phone.TEXT,b'{"b":1}'))
  self.assertEqual(phone.ws_read(io.BytesIO(masked(phone.TEXT,bytes(300))))[1],bytes(300))
 def test_unmasked_large_and_cut_frames_are_refused(self):
  with self.assertRaises(ValueError):phone.ws_read(io.BytesIO(phone.ws_frame(phone.TEXT,b'x')))
  with self.assertRaises(ValueError):phone.ws_read(io.BytesIO(masked(phone.BINARY,bytes(5000))))
  with self.assertRaises(EOFError):phone.ws_read(io.BytesIO(masked(phone.TEXT,b'hello')[:5]))

class PairingTests(unittest.TestCase):
 def test_a_code_pairs_one_phone_once_and_only_its_hash_is_kept(self):
  saved=[];pairing=phone.Pairing(save=saved.append);code=pairing.new_code(0)
  self.assertRegex(code,r'^\d{6}$');self.assertEqual(pairing.showing(10),(code,290))
  result,token=pairing.pair(code,10);self.assertEqual(result,'ok');self.assertTrue(pairing.knows(token))
  self.assertEqual(saved[-1],[phone.digest(token)]);self.assertNotIn(token,json.dumps(saved))
  self.assertEqual(pairing.pair(code,11),('closed',None));self.assertIsNone(pairing.showing(11))
 def test_wrong_codes_count_down_and_the_fifth_closes_it(self):
  pairing=phone.Pairing();code=pairing.new_code(0);wrong='000000' if code!='000000' else '111111'
  self.assertEqual([pairing.pair(wrong,1) for _ in range(5)],[('wrong',4),('wrong',3),('wrong',2),('wrong',1),('wrong',0)])
  self.assertEqual(pairing.pair(code,2),('closed',None))
 def test_a_code_runs_out_after_five_minutes(self):
  pairing=phone.Pairing();code=pairing.new_code(0);self.assertEqual(pairing.pair(code,300),('closed',None))
 def test_tokens_are_checked_and_forgotten(self):
  pairing=phone.Pairing([phone.digest('a'*32)]);self.assertTrue(pairing.knows('a'*32))
  for token in ('b'*32,'a'*31,None,42,'é'*32):self.assertFalse(pairing.knows(token))
  pairing.forget();self.assertFalse(pairing.knows('a'*32));self.assertEqual(pairing.count(),0)

class PadMessageTests(unittest.TestCase):
 def test_a_phone_state_is_kept_to_the_consoles_ranges(self):
  self.assertEqual(phone.read_pad_message('{"b":16384,"s":[0,255,128,128,300,-5]}'),pad.PadState(pad.CROSS,0,255,128,128,255,0))
  self.assertEqual(phone.read_pad_message('{"b":1,"s":[128,128,128,128,0,0]}').buttons,0)
  for text in ('nope','[]','{"b":"1","s":[1,2,3,4,5,6]}','{"b":1,"s":[1,2]}','{"b":1,"s":[1,2,3,4,5,"6"]}'):
   self.assertIsNone(phone.read_pad_message(text),text);self.assertEqual(phone.read_pad_message(text,True),(None,None),text)
  # The phone's own clock comes with each state, for the controller's delay in the phone log; a state without it still plays.
  self.assertEqual(phone.read_pad_message('{"b":16384,"s":[0,255,128,128,300,-5],"t":81234}',True),(pad.PadState(pad.CROSS,0,255,128,128,255,0),81234))
  for text in ('{"b":0,"s":[128,128,128,128,0,0]}','{"b":0,"s":[128,128,128,128,0,0],"t":"5"}','{"b":0,"s":[128,128,128,128,0,0],"t":true}','{"b":0,"s":[128,128,128,128,0,0],"t":-1}'):
   self.assertEqual(phone.read_pad_message(text,True),(pad.NEUTRAL,None),text)
 def test_the_controller_delay_counts_from_the_quickest_state(self):
  # The phone's clock is 5 s behind this PC's; the states take 10 ms, one waits 60 ms more on the Wi-Fi.
  spread=phone.ArrivalSpread();self.assertIsNone(spread.take())
  for index in range(10):sent=1000+index*8;spread.note(sent,(sent+5000+10+(60 if index==4 else 0))/1000)
  self.assertEqual(spread.take(),(10,0,60));self.assertIsNone(spread.take())
  # The quickest of the last window still counts after a new window starts, so the first state after it is not taken as quickest.
  spread.note(40000,(40000+5000+25)/1000);self.assertEqual(spread.take(),(1,15,15))
  # A phone that sends without the line being read again keeps a bounded list.
  for index in range(spread.MOST+50):spread.note(index,(index+5010)/1000)
  self.assertEqual(spread.take()[0],spread.MOST)
 def test_only_devices_on_this_network_may_open_the_page(self):
  for address,allowed in (('192.168.1.40',True),('10.0.0.8',True),('172.16.3.1',True),('127.0.0.1',True),('169.254.2.2',True),('::ffff:192.168.1.9',True),('8.8.8.8',False),('2001:4860::8888',False),('x',False)):
   self.assertEqual(phone.nearby(address),allowed,address)
 def test_the_phone_is_never_told_to_open_this_pc_itself_when_another_route_exists(self):
  routes={'127.0.0.1':'127.0.0.1','192.168.1.1':'192.168.1.50'}
  class Probe:
   def __init__(self,*a):self.at=None
   def __enter__(self):return self
   def __exit__(self,*a):return False
   def connect(self,place):
    if place[0] not in routes:raise OSError('no route')
    self.at=routes[place[0]]
   def getsockname(self):return (self.at,5000)
  with mock.patch.object(phone.socket,'socket',Probe):
   self.assertEqual(phone.local_address('127.0.0.1'),'192.168.1.50')
   self.assertEqual(phone.local_address('192.168.1.1'),'192.168.1.50')
   self.assertEqual(phone.local_address(''),'192.168.1.50')
  routes.clear()
  with mock.patch.object(phone.socket,'socket',Probe),mock.patch.object(phone.socket,'getaddrinfo',lambda *a:[(2,2,17,'',('10.1.2.3',0))]):
   self.assertEqual(phone.local_address('127.0.0.1'),'10.1.2.3')

class FragmentTests(unittest.TestCase):
 def test_the_muxer_output_is_cut_into_an_init_and_marked_fragments(self):
  got=[];writer=phone.Fragments(lambda kind,data,info:got.append((kind,data,info)))
  out=av.open(writer,'w',format='mp4',container_options={'movflags':'frag_every_frame+empty_moov+default_base_moof','flush_packets':'1'})
  source=av.open(io.BytesIO(b''.join(h264_packets(8,4)[:1])),format='h264');stream=out.add_stream_from_template(source.streams.video[0])
  for index,data in enumerate(h264_packets(8,4)):
   packet=av.Packet(data);packet.pts=packet.dts=index*1500;packet.time_base=Fraction(1,90000);packet.stream=stream;packet.is_keyframe=index%4==0;out.mux(packet)
  out.close();source.close()
  # The MP4 has the picture only (the sound goes beside it, see Sound).
  self.assertEqual(got[0][0],'init');self.assertRegex(got[0][2],r'^video/mp4; codecs="avc1\.[0-9A-F]{6}"$')
  self.assertRegex(phone.video_mime(got[0][1],2),r'^video/mp4; codecs="avc1\.[0-9A-F]{6}, mp4a\.40\.2"$')
  fragments=[info for kind,_,info in got if kind=='fragment'];self.assertEqual(len(fragments),8);self.assertEqual(fragments,[True,False,False,False,True,False,False,False])
 def test_a_sample_the_muxer_left_with_no_length_gets_its_tracks_usual_one(self):
  # A phone's browser takes a sample of no length for a break and drops the picture up to the next whole one.
  def traf(track,default,lengths=None):
   tfhd=struct.pack('>I4sII',24,b'tfhd',0x020038 if default is not None else 0x020020,track)+(struct.pack('>II',default,0) if default is not None else struct.pack('>I',0))
   tfhd=struct.pack('>I',len(tfhd))+tfhd[4:]
   if lengths is None:trun=struct.pack('>I4sIII',20,b'trun',0x1,1,0)
   else:trun=struct.pack('>I4sIII',20+4*len(lengths),b'trun',0x101,len(lengths),0)+b''.join(struct.pack('>I',n) for n in lengths)
   body=tfhd+trun;return struct.pack('>I4s',8+len(body),b'traf')+body
  def moof(*trafs):body=b''.join(trafs);return struct.pack('>I4s',8+len(body),b'moof')+body
  lengths={1:[1500,True],2:[1024,False]}
  fixed=phone.fill_lengths(moof(traf(1,1501),traf(2,0)),lengths)
  self.assertEqual(sample_lengths_in(fixed),[(1,1501),(2,1024)])
  # The video's own length is learned and used next; the sound's stays one AAC frame.
  fixed=phone.fill_lengths(moof(traf(1,0),traf(2,2048),traf(2,0,[0,512,0])),lengths)
  self.assertEqual(sample_lengths_in(fixed),[(1,1501),(2,2048),(2,1024),(2,512),(2,1024)])
  # A track the movie header did not describe is left as it is.
  self.assertEqual(sample_lengths_in(phone.fill_lengths(moof(traf(3,0)),lengths)),[(3,0)])
 def test_the_movie_header_gives_each_tracks_usual_length(self):
  got=[];writer=phone.Fragments(lambda kind,data,info:got.append((kind,data,info)))
  out=av.open(writer,'w',format='mp4',container_options={'movflags':'frag_every_frame+empty_moov+default_base_moof','flush_packets':'1'})
  video=av.open(io.BytesIO(h264_packets(2,2)[0]),format='h264');audio=av.open(io.BytesIO(adts_frames(2)[0]),format='aac')
  vs=out.add_stream_from_template(video.streams.video[0]);out.add_stream_from_template(audio.streams.audio[0]).codec_context.extradata=strip_adts(adts_frames(2)[0])[1]
  packet=av.Packet(h264_packets(2,2)[0]);packet.pts=packet.dts=0;packet.time_base=Fraction(1,90000);packet.stream=vs;packet.is_keyframe=True;out.mux(packet)
  out.close();video.close();audio.close()
  lengths=phone.sample_lengths(got[0][1][got[0][1].find(b'moov')-4:])
  self.assertEqual(lengths[2],[1024,False]);self.assertTrue(lengths[1][1]);self.assertGreater(lengths[1][0],0)
 def test_a_phone_that_falls_behind_starts_again_at_a_whole_picture(self):
  viewer=phone.Viewer();viewer.LIMIT=100
  viewer.offer('init',b'i'*10,'mime');viewer.offer('fragment',b'a'*20,None);viewer.offer('fragment',b'p'*20,False)
  self.assertEqual([item[0] for item in drain(viewer,.3)],['init'])
  viewer.offer('fragment',b'k'*20,True);viewer.offer('fragment',b'a'*20,None);viewer.offer('fragment',b'x'*90,False)
  # The phone already has the start, so it is not sent again (its page would start its player again): it waits for a whole picture.
  self.assertEqual(viewer.dropped,1);self.assertEqual(drain(viewer,.3),[])
  viewer.offer('fragment',b'p'*20,False);viewer.offer('fragment',b'k'*20,True);self.assertEqual([item[1][:1] for item in drain(viewer,.3)],[b'k'])
 def test_a_start_not_yet_sent_stays_when_a_phone_falls_behind(self):
  viewer=phone.Viewer();viewer.LIMIT=100
  viewer.offer('init',b'i'*10,'mime');viewer.offer('fragment',b'k'*50,True);viewer.offer('fragment',b'x'*60,False)
  self.assertEqual(viewer.dropped,1);self.assertEqual([item[0] for item in drain(viewer,.3)],['init'])

class FeedTests(unittest.TestCase):
 def run_feed(self,video,audio,**settings):
  feed=phone.PhoneFeed()
  for name,value in settings.items():setattr(feed,name,value)
  viewer=feed.join()
  try:
   for kind,data,stamp in stream_packets(video,audio):feed.feed(kind,data,stamp,stamp)
   items=drain(viewer,20,until=lambda items:sum(kind=='fragment' for kind,_,_ in items)>=6)
  finally:feed.leave(viewer)
  return feed,items
 def test_h264_up_to_720p_reaches_the_phone_as_it_came(self):
  feed,items=self.run_feed(h264_packets(16,4),adts_frames(20))
  self.assertEqual(items[0][0],'init');self.assertNotIn('mp4a',items[0][2]);self.assertEqual(feed.mode,'as the PS5 sends it')
  fragments=[item for item in items if item[0]=='fragment'];self.assertGreaterEqual(len(fragments),6);self.assertTrue(fragments[0][2])
  self.assertEqual(feed.error,'')
 def test_the_sound_reaches_the_phone_as_plain_samples_beside_the_picture(self):
  # Given the sound inside the MP4, a phone's browser waited longer each time the stream came late before it played on, and the
  # picture stopped with it; the page now plays the sound itself.
  feed=phone.PhoneFeed();viewer=feed.join()
  try:
   for kind,data,stamp in stream_packets(h264_packets(40,4),adts_frames(30)):feed.feed(kind,data,stamp,stamp)
   items=drain(viewer,20,until=lambda items:sum(kind=='sound' for kind,_,_ in items)>=20)
  finally:feed.leave(viewer)
  sounds=[data for kind,data,info in items if kind=='sound'];self.assertEqual(feed.error,'');self.assertGreaterEqual(len(sounds),20)
  rows=[struct.unpack_from('<4sdIH',data) for data in sounds]
  self.assertEqual({(magic,rate,channels) for magic,_,rate,channels in rows},{(phone.SOUND,48000,2)})
  # One AAC frame each, 1024 samples a channel, 16 bits, on the picture's clock (from the first picture, 1000 on the PS5's clock).
  self.assertEqual({len(data)-18 for data in sounds},{1024*2*2})
  times=[seconds for _,seconds,_,_ in rows];self.assertTrue(0<=times[0]<0.05,times[0])
  self.assertEqual([round((b-a)*90000) for a,b in zip(times,times[1:])],[1920]*(len(times)-1))
 def test_larger_pictures_are_made_again_smaller(self):
  feed,items=self.run_feed(h264_packets(30,4,(640,360)),adts_frames(40),COPY_HEIGHT=300,HEIGHT=270)
  self.assertEqual(feed.error,'');self.assertEqual(items[0][0],'init');self.assertEqual(feed.mode,'made again as 270p H.264')
  self.assertTrue([item for item in items if item[0]=='fragment'])
 def test_a_stream_made_again_has_a_whole_picture_every_so_often(self):
  # The page jumps to the newest picture when it falls behind, and that jump needs one; with the AMD encoder there was only the first.
  feed=phone.PhoneFeed();feed.COPY_HEIGHT=300;feed.HEIGHT=270;feed.KEY_EVERY=5;viewer=feed.join()
  try:
   for kind,data,stamp in stream_packets(h264_packets(80,80,(640,360)),adts_frames(100)):feed.feed(kind,data,stamp,stamp)
   items=drain(viewer,30,until=lambda items:sum(kind=='fragment' and info is not None for kind,_,info in items)>=30)
  finally:feed.leave(viewer)
  self.assertEqual(feed.error,'');video=[info for kind,_,info in items if kind=='fragment' and info is not None]
  self.assertGreaterEqual(len(video),30);self.assertEqual([k for k,key in enumerate(video[:30]) if key],[0,5,10,15,20,25])
 def test_every_sample_reaching_the_phone_has_a_length(self):
  # With sound, the muxer wrote most sound samples with a length of 0, and the phone then showed one picture a second.
  for copy in (True,False):
   feed=phone.PhoneFeed();feed.COPY_HEIGHT=300 if copy else 100;feed.HEIGHT=270;viewer=feed.join()
   try:
    for kind,data,stamp in stream_packets(h264_packets(60,30,(640,360)),adts_frames(80)):feed.feed(kind,data,stamp,stamp)
    items=drain(viewer,30,until=lambda items:sum(kind=='fragment' for kind,_,_ in items)>=50)
   finally:feed.leave(viewer)
   samples=[sample for kind,data,_ in items if kind=='fragment' for sample in sample_lengths_in(data)]
   self.assertEqual(feed.error,'');self.assertGreaterEqual(len(samples),50,copy);self.assertEqual({track for track,_ in samples},{1},copy)
   self.assertEqual([sample for sample in samples if not sample[1]],[],copy)
 def test_the_decoder_wakes_the_phone_stream_when_a_picture_is_ready(self):
  # A picture made again used to wait in the decoder's queue for the next packet, a frame later.
  import live_broadcast
  class Decoder:
   def decode(self,packet):return [] if packet is None else ['frame']
  ready=threading.Event();remaker=live_broadcast.Remaker(Decoder(),None,on_frame=ready.set)
  remaker.inbox.put('packet');self.assertTrue(ready.wait(2));self.assertEqual(remaker.outbox.get(timeout=1),'frame')
  remaker.inbox.put(None);remaker.thread.join(2)
  # A full queue already wakes the stream, so a wake that does not fit is dropped rather than waited for.
  inbox=queue.Queue(1);phone.wake(inbox);phone.wake(inbox);self.assertIs(inbox.get_nowait(),phone.READY)
 def test_each_encoder_is_asked_to_make_a_requested_whole_picture_a_real_one(self):
  self.assertEqual(phone.encoder_options('h264_amf'),{'usage':'ultralowlatency','forced_idr':'1'})
  self.assertEqual(phone.encoder_options('h264_nvenc')['forced-idr'],'1');self.assertEqual(phone.encoder_options('h264_qsv'),{'forced_idr':'1'})
  self.assertEqual(phone.encoder_options('libx264'),{'preset':'ultrafast','tune':'zerolatency'})
 def test_no_picture_made_for_the_phone_is_larger_than_three_frames_of_its_bitrate(self):
  # Whole pictures were ten times the others and came late over the phone's Wi-Fi every second.
  for name in ('h264_amf','h264_nvenc','h264_qsv','libx264'):
   options=phone.encoder_options(name,6_000_000);self.assertEqual((options['maxrate'],options['bufsize']),('6000000','300000'),name)
  self.assertEqual(phone.encoder_options('h264_amf',6_000_000)['rc'],'cbr');self.assertEqual(phone.encoder_options('h264_amf',6_000_000)['enforce_hrd'],'1')
  # An encoder that cannot take the cap is still used, as it can.
  feed=phone.PhoneFeed();tried=[]
  def works(name,options,bitrate):tried.append((name,'bufsize' in options));return name=='h264_amf' and 'bufsize' not in options
  feed._works=works;self.assertEqual(feed._encoder(),('h264_amf',phone.encoder_options('h264_amf')))
  self.assertEqual(tried,[('h264_nvenc',True),('h264_nvenc',False),('h264_amf',True),('h264_amf',False)])
 def test_pictures_the_ps5_leaves_out_are_filled_in(self):
  # On a still screen the PS5 leaves pictures out; each gap broke the phone's buffer in two and its page stopped and jumped.
  feed=phone.PhoneFeed();feed.COPY_HEIGHT=300;feed.HEIGHT=270;viewer=feed.join()
  try:
   packets=stream_packets(h264_packets(90,30,(640,360)),adts_frames(120));began=time.perf_counter()
   for kind,data,stamp in packets:
    # Fed in real time, without the pictures 40 to 49 (a 183 ms gap), as the PS5 did.
    wait=began+stamp/90000-time.perf_counter()
    if wait>0:time.sleep(wait)
    if kind==1 and 40*1500<=stamp<50*1500:continue
    feed.feed(kind,data,stamp,stamp)
   items=drain(viewer,5,until=lambda items:sum(kind=='fragment' and info is not None for kind,_,info in items)>=85)
  finally:feed.leave(viewer)
  starts=[start for kind,data,info in items if kind=='fragment' and info is not None for start in video_starts(data)]
  self.assertEqual(feed.error,'');self.assertGreaterEqual(len(starts),85)
  steps=[b-a for a,b in zip(starts,starts[1:])];self.assertLessEqual(max(steps),1500,steps)
  # The ten left out, and the few after them the decoder cannot make without the pictures they build on.
  self.assertGreaterEqual(feed.report(30)['made_up'],10)
 def test_a_late_picture_from_the_ps5_is_kept_and_none_is_made_up(self):
  # Wi-Fi from the PS5 brings many pictures 35 to 60 ms late. Made up on a timer, the real ones that came after were thrown away and
  # the owner saw a much worse picture on the phone.
  feed=phone.PhoneFeed();feed.COPY_HEIGHT=300;feed.HEIGHT=270;viewer=feed.join()
  try:
   packets=stream_packets(h264_packets(90,30,(640,360)),adts_frames(120));began=time.perf_counter();late=0.0
   for kind,data,stamp in packets:
    # Every tenth picture comes 60 ms late, and the ones after it right behind.
    if kind==1 and stamp//1500%10==5:late+=.06
    wait=began+stamp/90000+late-time.perf_counter()
    if wait>0:time.sleep(wait)
    feed.feed(kind,data,stamp,stamp)
   items=drain(viewer,5,until=lambda items:sum(kind=='fragment' and info is not None for kind,_,info in items)>=85)
  finally:feed.leave(viewer)
  starts=[start for kind,data,info in items if kind=='fragment' and info is not None for start in video_starts(data)]
  self.assertEqual(feed.error,'');self.assertEqual(starts[:85],[index*1500 for index in range(85)])
  self.assertEqual(feed.report(30)['made_up'],0)
 def test_a_phone_report_becomes_one_line_of_the_phone_log(self):
  report=phone.read_stats_message('{"type":"stats","player":"split","waits":3,"stall_ms":420,"seeks":1,"ranges":2,"dropped":5,"frames":900,"sound_late":2,"sound_lost_ms":64,"sound_trims":3,"sound_resyncs":1,"sound_rate":48000,"sound_out_ms":42,"sound_underruns":5,"behind":0.123,"picture_aim":0.06,"aim":0.11}')
  self.assertEqual(report,{'waits':3,'stall_ms':420,'seeks':1,'ranges':2,'dropped':5,'frames':900,'sound_late':2,'sound_lost_ms':64,'sound_trims':3,'sound_resyncs':1,'sound_rate':48000,'sound_out_ms':42,'sound_underruns':5,'behind':0.123,'picture_aim':0.06,'aim':0.11,'player':'split'})
  # Only the two players the page has are written to the log.
  self.assertEqual(phone.read_stats_message('{"type":"stats","player":"<b>x</b>"}')['player'],'-')
  # A browser that does not count its sound running out sends -1: the log shows ? for it, and 0 stays 0.
  self.assertIsNone(phone.read_stats_message('{"type":"stats","sound_underruns":-1}')['sound_underruns'])
  self.assertEqual(phone.read_stats_message('{"type":"stats","sound_underruns":0}')['sound_underruns'],0)
  self.assertIn('ran out ?',phone.stats_line(2,phone.read_stats_message('{"type":"stats","sound_underruns":-1}'),phone.Viewer(),phone.PhoneFeed().report()))
  self.assertIsNone(phone.read_stats_message('{"b":0,"s":[128,128,128,128,0,0]}'));self.assertIsNone(phone.read_stats_message('nonsense'))
  self.assertEqual(phone.read_stats_message('{"type":"stats","waits":"x","behind":1e9}')['behind'],0.0)
  feed=phone.PhoneFeed();feed.note('gap',120);feed.note('pc',30);feed.note('pc',50);feed.note('made',1)
  line=phone.stats_line(1,report,phone.Viewer(),feed.report(),(120,4,37))
  self.assertIn('behind 0.12 s (aim 0.06), store 0.11 s',line);self.assertTrue(line.endswith('| controller: 120 states, 4 ms later than its quickest (latest 37)'),line)
  self.assertTrue(phone.stats_line(1,report,phone.Viewer(),feed.report()).endswith('| controller: no states'))
  self.assertIn('phone 1 (split): stalls 3 (420 ms in all)',line);self.assertIn('sound late 2 (64 ms left out), taken back 3, rejoined 1, output 48000 Hz 42 ms, ran out 5',line);self.assertIn('longest wait for the PS5 120 ms',line);self.assertIn('pictures made up 1',line)
  with tempfile.TemporaryDirectory() as folder:
   log=phone.PhoneLog(Path(folder)/'phone-log.txt');log.LIMIT=200
   for _ in range(4):log.write(line)
   self.assertTrue((Path(folder)/'phone-log.old.txt').exists());self.assertIn('phone 1 (split):',(Path(folder)/'phone-log.txt').read_text(encoding='utf8'))
 def test_the_phone_stream_is_720p_at_6_mbps(self):
  self.assertEqual((phone.PhoneFeed.HEIGHT,phone.PhoneFeed.COPY_HEIGHT,phone.PhoneFeed.BITRATE),(720,720,6_000_000))
 def test_a_late_phone_gets_the_start_and_waits_for_a_whole_picture(self):
  feed=phone.PhoneFeed();first=feed.join()
  try:
   packets=stream_packets(h264_packets(16,4),adts_frames(20))
   for kind,data,stamp in packets[:len(packets)//2]:feed.feed(kind,data,stamp,stamp)
   drain(first,10,until=lambda items:any(kind=='fragment' for kind,_,_ in items))
   second=feed.join()
   for kind,data,stamp in packets[len(packets)//2:]:feed.feed(kind,data,stamp,stamp)
   items=drain(second,10,until=lambda items:any(kind=='fragment' for kind,_,_ in items))
   self.assertEqual(items[0][0],'init');self.assertTrue(next(item for item in items if item[0]=='fragment')[2])
   feed.leave(second)
  finally:feed.leave(first)
  self.assertIsNone(feed.thread)

class ServerTests(unittest.TestCase):
 def setUp(self):
  self.companion=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.companion.bind(('127.0.0.1',0));self.companion.settimeout(3)
  self.port_before=phone.pad.PAD_PORT;phone.pad.PAD_PORT=self.companion.getsockname()[1]
  self.pairing=phone.Pairing();self.play=True
  self.server=phone.PhoneServer(phone.PhoneFeed(),self.pairing,lambda:'127.0.0.1',lambda:self.play,port=0);self.assertTrue(self.server.start())
  self.port=self.server.server.server_address[1]
 def tearDown(self):
  self.server.stop();phone.pad.PAD_PORT=self.port_before;self.companion.close()
 def request(self,method,path,body=None,headers=None):
  connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5);connection.request(method,path,body,headers or {})
  answer=connection.getresponse();data=answer.read();connection.close();return answer.status,data
 def websocket(self,token):
  sock=socket.create_connection(('127.0.0.1',self.port),5);key=base64.b64encode(os.urandom(16)).decode()
  sock.sendall(f'GET /ws HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n'.encode())
  stream=sock.makefile('rb');head=b''
  while not head.endswith(b'\r\n\r\n'):head+=stream.read(1)
  self.assertIn(b'101',head.split(b'\r\n')[0]);self.assertIn(phone.accept_key(key).encode(),head)
  sock.sendall(masked(phone.TEXT,json.dumps({'token':token}).encode()));return sock,stream
 def read_frame(self,stream):
  b0,b1=stream.read(2);n=b1&0x7f
  if n==126:n=struct.unpack('>H',stream.read(2))[0]
  elif n==127:n=struct.unpack('>Q',stream.read(8))[0]
  return b0&0x0f,stream.read(n)
 def test_the_page_and_pairing(self):
  status,page=self.request('GET','/');self.assertEqual(status,200);self.assertIn(b'<title>PlayBridge</title>',page)
  # The browser's own player can be picked in the address.
  self.assertEqual(self.request('GET','/?player=media'),(200,page))
  # A TV, a Steam Deck or another computer opens the same page at /tv, for a remote, a controller or a keyboard.
  self.assertEqual(self.request('GET','/tv'),(200,page));self.assertIn(b'location.pathname === "/tv"',page)
  self.assertEqual(self.request('POST','/api/pair',b'{"code":"123456"}')[0],410)
  code=self.pairing.new_code(time.monotonic());wrong='000000' if code!='000000' else '111111'
  status,body=self.request('POST','/api/pair',json.dumps({'code':wrong}).encode());self.assertEqual((status,json.loads(body)),(403,{'error':'code','left':4}))
  self.assertEqual(self.request('POST','/api/pair',b'x'*300)[0],400)
  status,body=self.request('POST','/api/pair',json.dumps({'code':code}).encode());token=json.loads(body)['token'];self.assertEqual(status,200)
  self.assertEqual(self.request('GET','/api/check',headers={'X-Token':token})[0],200);self.assertEqual(self.request('GET','/api/check',headers={'X-Token':'f'*32})[0],401)
  self.assertEqual(self.request('GET','/nothing')[0],404)
 def test_an_unpaired_phone_is_closed_with_its_own_code(self):
  sock,stream=self.websocket('f'*32)
  try:opcode,data=self.read_frame(stream);self.assertEqual((opcode,struct.unpack('>H',data)[0]),(phone.CLOSE,4401))
  finally:sock.close()
 def test_a_paired_phone_plays_as_a_controller_of_its_own_and_leaves_with_quit(self):
  _,token=self.pairing.pair(self.pairing.new_code(0),1)
  sock,stream=self.websocket(token)
  try:
   opcode,data=self.read_frame(stream);self.assertEqual((opcode,json.loads(data)),(phone.TEXT,{'type':'hello','play':True,'joined':False}))
   sock.sendall(masked(phone.TEXT,b'{"b":16384,"s":[0,128,128,128,0,0]}'))
   data,phone_address=self.companion.recvfrom(64);self.assertEqual(data[:4],b'PBP1');self.assertEqual(struct.unpack_from('<I',data,8)[0],pad.CROSS);self.assertEqual(data[12],0)
   # The companion's answer reaches the phone as its player number.
   self.companion.sendto(pad.status_wire(pad.READY,0,0,2),phone_address);sock.sendall(masked(phone.TEXT,b'{"b":0,"s":[128,128,128,128,0,0]}'))
   self.companion.recvfrom(64);deadline=time.monotonic()+3;shown=None
   while time.monotonic()<deadline and not (shown and shown.get('player')==2):
    sock.sendall(masked(phone.TEXT,b'{"b":0,"s":[128,128,128,128,0,0]}'))
    try:self.companion.recvfrom(64)
    except socket.timeout:pass
    opcode,data=self.read_frame(stream)
    if opcode==phone.TEXT:shown=json.loads(data)
   self.assertEqual((shown['type'],shown['joined'],shown['state'],shown['player']),('pad',True,pad.READY,2))
   self.assertTrue(self.server.in_use(time.monotonic()))
   sock.sendall(masked(phone.CLOSE,b''))
   while True:
    data,_=self.companion.recvfrom(64)
    if data[:4]==b'PBQ1':break
  finally:sock.close()
 def test_with_play_off_on_the_pc_a_phone_only_watches(self):
  self.play=False;_,token=self.pairing.pair(self.pairing.new_code(0),1);sock,stream=self.websocket(token)
  try:
   self.assertEqual(json.loads(self.read_frame(stream)[1]),{'type':'hello','play':False,'joined':False})
   sock.sendall(masked(phone.TEXT,b'{"b":16384,"s":[0,128,128,128,0,0]}'));self.companion.settimeout(.5)
   with self.assertRaises(socket.timeout):self.companion.recvfrom(64)
  finally:sock.close()

 def test_a_phone_nobody_touches_adds_nothing_on_the_ps5(self):
  _,token=self.pairing.pair(self.pairing.new_code(0),1);sock,stream=self.websocket(token)
  try:
   self.read_frame(stream)
   # The page sends its state ten times a second while open; at rest, or with a stick drifting a little, nothing reaches the PS5.
   for _ in range(5):sock.sendall(masked(phone.TEXT,b'{"b":0,"s":[140,120,128,128,10,0]}'))
   shown=json.loads(self.read_frame(stream)[1]);self.assertEqual((shown['type'],shown['play'],shown['joined']),('pad',True,False))
   self.companion.settimeout(.5)
   with self.assertRaises(socket.timeout):self.companion.recvfrom(64)
   self.assertFalse(self.server.in_use(time.monotonic()))
  finally:sock.close()
 def test_an_alert_reaches_each_phone_connected_now(self):
  self.assertEqual(self.server.alert('Trophy','None here'),0)
  _,token=self.pairing.pair(self.pairing.new_code(0),1);sock,stream=self.websocket(token)
  try:
   self.read_frame(stream);deadline=time.monotonic()+3
   while self.server.phones!=1 and time.monotonic()<deadline:time.sleep(.01)
   self.assertEqual(self.server.alert('Trophy unlocked','First Steps in Some Game'),1)
   while True:
    opcode,data=self.read_frame(stream)
    if opcode==phone.TEXT and json.loads(data)['type']=='alert':break
   self.assertEqual(json.loads(data),{'type':'alert','title':'Trophy unlocked','text':'First Steps in Some Game'})
  finally:sock.close()
 def test_disconnect_phones_closes_each_one_and_takes_its_controller_off_the_ps5(self):
  _,token=self.pairing.pair(self.pairing.new_code(0),1);sock,stream=self.websocket(token)
  try:
   self.read_frame(stream);sock.sendall(masked(phone.TEXT,b'{"b":16384,"s":[128,128,128,128,0,0]}'))
   self.assertEqual(self.companion.recvfrom(64)[0][:4],b'PBP1')
   deadline=time.monotonic()+3
   while self.server.phones!=1 and time.monotonic()<deadline:time.sleep(.01)
   self.assertEqual(self.server.disconnect(),1)
   while True:
    opcode,data=self.read_frame(stream)
    if opcode==phone.CLOSE:break
   self.assertEqual(struct.unpack('>H',data)[0],phone.CLOSED_ON_PC)
   quits=[self.companion.recvfrom(64)[0] for _ in range(2)];self.assertEqual(quits,[pad.QUIT]*2)
   while self.server.phones and time.monotonic()<deadline+3:time.sleep(.01)
   self.assertEqual((self.server.phones,self.server.disconnect()),(0,0))
  finally:sock.close()

class PhonePadTests(unittest.TestCase):
 def setUp(self):
  self.companion=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.companion.bind(('127.0.0.1',0));self.companion.settimeout(.3)
  self.port_before=phone.pad.PAD_PORT;phone.pad.PAD_PORT=self.companion.getsockname()[1];self.pad=phone.PhonePad(lambda:'127.0.0.1')
 def tearDown(self):
  self.pad.close();phone.pad.PAD_PORT=self.port_before;self.companion.close()
 def received(self):
  out=[]
  while True:
   try:out.append(self.companion.recvfrom(64)[0][:4])
   except socket.timeout:return out
 def test_two_minutes_with_nothing_pressed_takes_its_controller_off_until_the_next_press(self):
  self.pad.send(pad.PadState(pad.CROSS),0);self.pad.send(pad.NEUTRAL,60);self.pad.send(pad.NEUTRAL,119.9)
  self.assertEqual(self.received(),[b'PBP1']*3);self.assertTrue(self.pad.in_use(119.9))
  self.pad.send(pad.NEUTRAL,120);self.pad.send(pad.NEUTRAL,121);self.assertEqual(self.received(),[b'PBQ1',b'PBQ1']);self.assertFalse(self.pad.joined)
  self.pad.send(pad.PadState(pad.CIRCLE),130);self.assertEqual(self.received(),[b'PBP1'])
 def test_leaving_without_playing_says_nothing(self):
  self.pad.send(pad.NEUTRAL,0);self.pad.leave();self.assertEqual(self.received(),[])
 def test_its_answers_are_read_at_once_even_before_it_ever_sent(self):
  # Windows answers every read on a socket that never sent with an error; that must not keep the phone's connection waiting.
  start=time.perf_counter();self.assertIsNone(self.pad.heard());self.assertLess(time.perf_counter()-start,.1)
  self.pad.send(pad.PadState(pad.CROSS),0);data,address=self.companion.recvfrom(64)
  self.companion.sendto(pad.status_wire(pad.READY,0,0,3),address);deadline=time.monotonic()+2
  while self.pad.heard() is None and time.monotonic()<deadline:time.sleep(.01)
  self.assertEqual(self.pad.heard()[3],3)

if __name__=='__main__':unittest.main()
