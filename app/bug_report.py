"""Report a problem: a new issue on PlayBridge's GitHub page, opened in the browser with this PC's details filled in. PlayBridge
sends nothing itself: the player reads the issue, writes what happened and submits it on GitHub, or closes the page.

The details are the allowlist of exported diagnostics (stream_metrics.diagnostic_report): no addresses, names, paths, logs or
pictures, with the graphics card's model because decoding depends on it. To them come the version, the Windows version, the look,
the renderer and the performance check."""
import platform
from urllib.parse import urlencode
from app_version import VERSION
from stream_metrics import diagnostic_report

ISSUES='https://github.com/{repository}/issues/new'
NOTE=('Opens a new issue on PlayBridge\'s GitHub page with this PC\'s details filled in: the version, Windows, the graphics card, the stream '
 'settings and how long each frame takes. No addresses, names or files. Nothing is sent until you submit it there; the details are also '
 'copied, to paste anywhere.')
# Browsers and GitHub take addresses of about 8,000 characters; the details are cut to fit.
MOST=7600
STAGES=('video_decode_ms','video_convert_ms','presenter_upload_ms','receive_to_present_ms','shown_gap_ms')
STATS=('presented_fps','video_decoded','video_presented','video_packets_dropped','video_late_waits','audio_empty_callbacks','device_underflows','reconnection_attempts',
 'transport_delay_growth_ms','refresh_hz','vrr','screen_rate','hitches','stream_gaps','present_timeouts','frames_in_flight','network_link','smooth_motion','picture_engine','video_hdr','on_battery')

def details(snapshot,look='qt',check=''):
 """The details as plain lines."""
 report=diagnostic_report(snapshot);stats=report['stats'];stream=report['stream'];capture=report['capture']
 lines=[f'PlayBridge {VERSION}, {"new" if look=="qt" else "classic"} look',f'Windows {platform.release()} (build {platform.version()})',
  f"Graphics card: {stats.get('graphics_card') or 'unknown'}"+(f" ({stats['graphics_vendor']})" if stats.get('graphics_vendor') else '')+(f", decodes up to {stats['gpu_decodes_up_to']}" if stats.get('gpu_decodes_up_to') else ''),
  f"Renderer: {snapshot.get('renderer') or 'unknown'}, video decoder: {stats.get('video_decoder') or 'none yet'}"]
 if stream.get('decoded_width'):lines.append(f"Stream: {stream['decoded_width']}x{stream['decoded_height']} {stream.get('pixel_format') or ''}, {stream.get('received_mbps')} Mbps received, {stream.get('video_packets_per_second')} packets/s")
 if capture:lines.append('Capture: '+', '.join(f'{key} {value}' for key,value in capture.items() if value not in (None,'')))
 if 'secured' in snapshot:lines.append('Connection: '+("secured (the payload holds this PC's key)" if snapshot['secured'] else 'open (the payload holds no key)'))
 if snapshot.get('observed_seconds') is not None:lines.append(f"Open for {round(float(snapshot['observed_seconds'])/60,1)} min")
 shown=[f'{key} {stats[key]}' for key in STATS if key in stats and stats[key] not in (None,'',{},[])]
 if shown:lines.append('Stats: '+'; '.join(shown))
 for name in STAGES:
  values=report['timings_ms'].get(name)
  if values:lines.append(f"{name}: p50 {values.get('p50')}, p95 {values.get('p95')}, max {values.get('max')} ({values.get('samples')} frames)")
 if check:lines.append(check)
 return lines

def body(lines):
 return ('### What happened\n\n<!-- What you did, what went wrong, and whether it happens every time. -->\n\n\n### What you expected\n\n\n'
  '### Details from PlayBridge\n\n<!-- Filled in by PlayBridge: no addresses, names or files. -->\n```\n'+'\n'.join(lines)+'\n```\n')

def issue_url(repository,lines,title=''):
 """The new-issue page with the details in it, the details cut from the end until the address fits."""
 lines=list(lines)
 while True:
  url=ISSUES.format(repository=repository)+'?'+urlencode(dict(title=title,body=body(lines)))
  if len(url)<=MOST or len(lines)<=1:return url
  lines=lines[:-1] if len(lines)>2 else [lines[0][:200]]
