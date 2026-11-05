"""Opening a Windows sound output for the PS5's 48 kHz audio, whatever rate the output mixes at."""
import sounddevice as sd

WASAPI='Windows WASAPI';OLDER=('Windows DirectSound','MME')

def output_settings(device):
 """Lets Windows convert the sample rate on a WASAPI output. Without it, an output that mixes at 44.1, 96 or 192 kHz refuses a 48 kHz stream
 with "Invalid sample rate" (PortAudio -9997), and PlayBridge 1.5.0 did not open on such a PC. Other host APIs get no settings."""
 try:
  info=sd.query_devices(device,'output') if device is not None else sd.query_devices(kind='output')
  if sd.query_hostapis(info['hostapi'])['name']==WASAPI:return sd.WasapiSettings(auto_convert=True)
 except Exception:pass
 return None

def candidates(chosen):
 """The outputs to try, in order: the chosen one, then the default output of WASAPI, DirectSound and MME. The older two convert the rate in
 Windows itself, so they still play where WASAPI will not open, at a longer delay."""
 order=[chosen]
 try:
  apis=sd.query_hostapis()
  order+=[api['default_output_device'] for name in (WASAPI,)+OLDER for api in apis if api['name']==name]
 except Exception:pass
 return [d for d in dict.fromkeys(order) if d is not None and d>=0] or [None]

def device_line(device):
 """One output as the audio check shows it: name, host API, channels and the rate Windows mixes at."""
 try:
  info=sd.query_devices(device,'output') if device is not None else sd.query_devices(kind='output')
  return f"{info['name']} [{sd.query_hostapis(info['hostapi'])['name']}], {info['max_output_channels']} channels, {info['default_samplerate']:g} Hz"
 except Exception as error:return f'output {device} ({describe(error)})'

def check_report(attempts,opened,latency,when):
 """The audio check file: every output that refused and why, then the one that opened. Written only when one refused, to find out why on a PC we cannot see."""
 lines=[f'PlayBridge audio check, {when}','The stream is 48000 Hz, 2 channels, 16-bit.','']
 lines+=[f'Refused: {device_line(device)}: {describe(error)}' for device,error in attempts]
 lines.append(f'Opened: {device_line(opened)}, delay {latency*1000:.0f} ms' if latency is not None else 'No output opened: PlayBridge runs without sound.')
 return '\n'.join(lines)+'\n'

def default_output():
 """The WASAPI default output, or None when this PC has no sound output at all."""
 for api in sd.query_hostapis():
  if api['name']==WASAPI and api['default_output_device']>=0:return api['default_output_device']
 return None

def output_name(device):
 """The output's name as Windows shows it; None means the default output."""
 return (sd.query_devices(device,'output') if device is not None else sd.query_devices(kind='output'))['name']

def describe(error):
 """A short reason for the status line; PortAudio's own text is clear enough once its error code is left out."""
 text=str(error).split(' [PaErrorCode')[0].strip()
 return text or type(error).__name__
