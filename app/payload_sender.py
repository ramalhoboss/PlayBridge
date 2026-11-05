"""Sends an ELF the user picks to the loader their exploit opened on the PS5, the same way PlayBridge sends its own."""
import socket
from pathlib import Path

LOADER_PORT=9021
LIMIT=64*1024*1024
KEEP=5

class PayloadError(ValueError):
 """What went wrong, in words for the user."""

def read_payload(path):
 """The file's bytes, once it looks like a PS5 payload: a 64-bit, little-endian x86 ELF of a sane size."""
 path=Path(path)
 try:size=path.stat().st_size
 except OSError:raise PayloadError('That file cannot be read.') from None
 if size>LIMIT:raise PayloadError('That file is larger than 64 MB, too large for a payload.')
 try:data=path.read_bytes()
 except OSError:raise PayloadError('That file cannot be read.') from None
 if data[:4]!=b'\x7fELF':raise PayloadError('That file is not an ELF payload.')
 if len(data)<20 or data[4]!=2 or data[5]!=1 or int.from_bytes(data[18:20],'little')!=0x3E:raise PayloadError('That ELF is not built for the PS5, which needs 64-bit x86.')
 return data

def send_payload(host,data,port=LOADER_PORT,timeout=5):
 """Sends the whole file, then closes its half of the connection, which is how the loader knows it has all of it."""
 try:
  with socket.create_connection((host,port),timeout) as loader:
   loader.sendall(data);loader.shutdown(socket.SHUT_WR)
 except ConnectionRefusedError:raise PayloadError(f'Nothing answered on port {port}. Load the ELF loader with your exploit first.') from None
 except (socket.timeout,TimeoutError):raise PayloadError('The PS5 did not answer. Check its IP address and that it is on.') from None
 except OSError:raise PayloadError('The payload could not be sent. Check that the PS5 is on and on the network.') from None

def size_label(size):
 return f'{size/1024/1024:.1f} MB' if size>=1024*1024 else f'{max(1,round(size/1024))} KB'

def remember(recent,path):
 """The most recent first, each file once, at most KEEP."""
 path=str(path);return [path]+[item for item in recent if item!=path][:KEEP-1]
