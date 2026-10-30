"""Measured stream health and deliberately limited diagnostic exports."""
import json,time,zipfile
from collections import deque
from datetime import datetime,timezone
from pathlib import Path

class StreamMetrics:
 def __init__(self,clock=time.monotonic):
  self.clock=clock;self.reset()
 def reset(self):
  self.samples=deque();self.width=0;self.height=0;self.pixel_format=None
 def packet(self,size,video=False):
  now=self.clock();self.samples.append((now,size,int(video)));self._prune(now)
 def _prune(self,now):
  while self.samples and now-self.samples[0][0]>5:self.samples.popleft()
 def frame(self,frame):
  self.width=frame.width;self.height=frame.height;self.pixel_format=frame.format.name
 def summary(self):
  now=self.clock();self._prune(now);elapsed=now-self.samples[0][0] if self.samples else 0
  # Exclude the first packet at the interval boundary from rate numerators.
  tail=list(self.samples)[1:]
  return {'decoded_width':self.width,'decoded_height':self.height,'pixel_format':self.pixel_format,'received_mbps':round(sum(s[1] for s in tail)*8/elapsed/1e6,2) if elapsed>=1 else None,'video_packets_per_second':round(sum(s[2] for s in tail)/elapsed,1) if elapsed>=1 else None,'rate_window_seconds':round(elapsed,2)}

# Explicit allowlists: no host address, device names, paths, frame/audio data,
# exception messages, environment, credentials, or arbitrary acknowledgement keys.
SAFE_STATS=('audio_queue_ms','presented_fps','video_decoded','video_presented','video_replaced','video_packets_dropped','prepared_replaced','video_late_waits','audio_empty_callbacks','device_underflows','audio_trim_samples','reconnection_attempts','transport_delay_growth_ms','latency_scope','observed_seconds')
SAFE_STREAM=('decoded_width','decoded_height','pixel_format','received_mbps','video_packets_per_second','rate_window_seconds')
SAFE_CAPTURE=('protocol','confirmed','fps_target','bitrate_target','resource_profile','resolution','resolution_requested','output_mode','refused_by')
def diagnostic_report(snapshot):
 report={'schema':1,'created_utc':datetime.now(timezone.utc).isoformat(),'stats':{k:snapshot[k] for k in SAFE_STATS if k in snapshot},'stream':{k:snapshot.get('stream',{}).get(k) for k in SAFE_STREAM},'capture':{k:snapshot.get('capture_info',{}).get(k) for k in SAFE_CAPTURE} if isinstance(snapshot.get('capture_info'),dict) else {},'timings_ms':{}}
 for name,values in snapshot.get('timings_ms',{}).items():
  if name in ('packet_body_read_ms','video_decode_ms','decoded_slot_wait_ms','video_convert_ms','prepared_slot_wait_ms','presenter_upload_ms','receive_to_present_ms'):
   report['timings_ms'][name]={k:values[k] for k in ('samples','mean','p50','p95','max') if k in values}
 return report
def export_diagnostics(path,snapshot):
 path=Path(path)
 with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as z:
  z.writestr('diagnostics.json',json.dumps(diagnostic_report(snapshot),indent=2))
  z.writestr('README.txt','PlayBridge diagnostics\nRates are measured received media payload, not encoder targets.\nVideo packet rate is not decoded frame rate.\nTiming measurements cover PC stages, not total console-to-display latency.\nNo screenshots, audio, IP addresses, device names or logs are included.\n')
 return path
