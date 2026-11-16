"""Report a problem: the new-issue page carries the version, Windows, the graphics card, the stream and its timings, and never an
address, a console or player name, a path or the session's timeline; it fits in an address a browser takes."""
import sys,unittest
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import bug_report
from app_version import VERSION

SNAPSHOT=dict(renderer='d3d11',video_decoder='d3d11va',graphics_card='Radeon RX 7600',graphics_vendor='AMD',gpu_decodes_up_to='4K',presented_fps=59.9,
 stream=dict(decoded_width=1920,decoded_height=1080,pixel_format='nv12',received_mbps=19.8,video_packets_per_second=60.0,rate_window_seconds=5),
 capture_info=dict(fps_target=60,bitrate_target=20000,resolution='1080p',host='192.168.1.50',console_name='PS5-123'),observed_seconds=600,
 timings_ms=dict(video_decode_ms=dict(samples=1800,mean=3,p50=2.8,p95=5.1,max=9),receive_to_present_ms=dict(samples=1800,mean=10,p50=9,p95=14,max=30)),
 events=[(1.0,'Connected to 192.168.1.50 as PS5-123'),(2.0,r'Saved C:\Users\Someone\Videos\clip.mp4')],output='Speakers (Someone\'s headset)',error='Lost 192.168.1.50',
 host='192.168.1.50')

class BugReportTests(unittest.TestCase):
 def test_the_details_and_nothing_private(self):
  lines=bug_report.details(SNAPSHOT,'qt','Performance check: 1.7.1 is as fast as 1.7.0 on this PC, with the same settings.')
  text='\n'.join(lines)
  self.assertEqual(lines[0],f'PlayBridge {VERSION}, new look');self.assertIn('Graphics card: Radeon RX 7600 (AMD), decodes up to 4K',text)
  self.assertIn('Renderer: d3d11, video decoder: d3d11va',text);self.assertIn('Stream: 1920x1080 nv12, 19.8 Mbps received',text)
  self.assertIn('video_decode_ms: p50 2.8, p95 5.1, max 9 (1800 frames)',text);self.assertIn('Performance check',text);self.assertIn('fps_target 60',text)
  self.assertNotIn('Connection:',text);self.assertIn("Connection: secured (the payload holds this PC's key)",bug_report.details(dict(SNAPSHOT,secured=True),'qt'))
  self.assertIn('Connection: open (the payload holds no key)',bug_report.details(dict(SNAPSHOT,secured=False),'qt'))
  for private in ('192.168','PS5-123','Someone','Users','clip.mp4','Speakers'):self.assertNotIn(private,text)
 def test_the_issue_page(self):
  url=bug_report.issue_url('owner/PlayBridge',bug_report.details(SNAPSHOT,'tk'))
  parts=urlsplit(url);query=parse_qs(parts.query)
  self.assertEqual((parts.netloc,parts.path),('github.com','/owner/PlayBridge/issues/new'))
  self.assertIn('### What happened',query['body'][0]);self.assertIn('classic look',query['body'][0])
  long=bug_report.issue_url('owner/PlayBridge',['first line']+['x'*500]*40)
  self.assertLessEqual(len(long),bug_report.MOST);self.assertIn('first line',parse_qs(urlsplit(long).query)['body'][0])

if __name__=='__main__':unittest.main()
