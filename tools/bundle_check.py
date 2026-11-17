"""The third-party packages a PyInstaller build takes in, and the ones among them that third-party-licenses/components.json does not
list. PlayBridge.spec stops the build on any such package, so the EXE never carries code whose notice is missing."""
import json,re
from pathlib import Path,PureWindowsPath

# Folder and file names inside site-packages that belong to a listed component under another name.
ALIASES={'pil':'pillow','_cffi_backend':'cffi','_sounddevice':'sounddevice','_sounddevice_data':'sounddevice','shiboken6':'pyside6',
 'pyside6_essentials':'pyside6','pyside6_addons':'pyside6','pyinstaller':'pyinstaller'}

def package_of(path):
 """The top-level package name a bundled file comes from, or None when it is not from a site-packages folder."""
 parts=[part.lower() for part in PureWindowsPath(str(path)).parts]
 if 'site-packages' not in parts:return None
 rest=parts[len(parts)-1-parts[::-1].index('site-packages')+1:]
 if not rest:return None
 top=rest[0]
 top=re.sub(r'(-[^-]+)?\.(dist-info|egg-info)$','',top);top=re.sub(r'\.libs$','',top)
 top=re.sub(r'\.(cp\d+[^.]*\.)?(pyd|py|pth|so)$','',top)
 top=top.replace('-','_')
 return ALIASES.get(top,top)

def listed(components_file):
 return {item['component'].lower().replace('-','_') for item in json.loads(Path(components_file).read_text(encoding='utf8'))}

def unlisted(entries,components_file):
 """entries: (name, source path, kind) as PyInstaller's Analysis gives them. The packages from site-packages not in components.json."""
 known=listed(components_file);found=set()
 for entry in entries:
  package=package_of(entry[1]) if len(entry)>1 and entry[1] else None
  if package and package not in known:found.add(package)
 return sorted(found)
