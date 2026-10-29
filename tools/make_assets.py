from PIL import Image,ImageDraw
from pathlib import Path
import numpy as np
p=Path(__file__).resolve().parents[1]/'app'/'assets';p.mkdir(exist_ok=True)
n=1024
y,x=np.mgrid[0:n,0:n];t=(x+y)/(2*n)
a=np.zeros((n,n,4),dtype=np.uint8)
for k,(lo,hi) in enumerate([(31,80),(76,130),(205,249)]):a[:,:,k]=(lo+(hi-lo)*t).astype(np.uint8)
a[:,:,3]=255
im=Image.fromarray(a);mask=Image.new('L',(n,n));ImageDraw.Draw(mask).rounded_rectangle((6,6,n-6,n-6),radius=236,fill=255);im.putalpha(mask)
d=ImageDraw.Draw(im)
d.rounded_rectangle((176,226,848,684),radius=88,outline='white',width=40)
d.line((512,686,512,785),fill='white',width=40);d.rounded_rectangle((367,768,657,808),radius=20,fill='white')
# Two interlocking rounded links, a visual bridge inside the display.
links=Image.new('RGBA',(1024,1024));q=ImageDraw.Draw(links)
q.rounded_rectangle((305,398,565,534),radius=68,outline='white',width=35)
q.rounded_rectangle((465,398,725,534),radius=68,outline='#96F2EE',width=35)
links=links.rotate(32,resample=Image.Resampling.BICUBIC,center=(512,466));im.alpha_composite(links)
im.save(p/'playbridge.png');im.save(p/'playbridge.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])

# Consistent line icons for the console-style shell.
def icon(name,draw):
 s=4;im=Image.new('RGBA',(256,256));d=ImageDraw.Draw(im);draw(d);im.resize((64,64),Image.Resampling.LANCZOS).save(p/(name+'.png'))
white='#F2F7FF';cyan='#76C7FF'
icon('fullscreen',lambda d:[d.line(v,fill=white,width=14,joint='curve') for v in [[(52,98),(52,52),(98,52)],[(158,52),(204,52),(204,98)],[(204,158),(204,204),(158,204)],[(98,204),(52,204),(52,158)]]])
icon('speaker',lambda d:(d.polygon([(44,104),(88,104),(140,60),(140,196),(88,152),(44,152)],fill=white),d.arc((130,72,210,184),-65,65,fill=white,width=12)))
icon('muted',lambda d:(d.polygon([(36,104),(80,104),(128,64),(128,192),(80,152),(36,152)],fill=white),d.line((165,103,211,149),fill=white,width=12),d.line((165,149,211,103),fill=white,width=12)))
icon('settings',lambda d:(d.line((48,68,208,68),fill=white,width=12),d.line((48,128,208,128),fill=white,width=12),d.line((48,188,208,188),fill=white,width=12),d.rounded_rectangle((83,44,113,92),radius=10,fill=white),d.rounded_rectangle((149,104,179,152),radius=10,fill=white),d.rounded_rectangle((79,164,109,212),radius=10,fill=white)))
icon('connect',lambda d:d.polygon([(84,48),(208,128),(84,208)],fill=white))
icon('disconnect',lambda d:d.rounded_rectangle((64,64,192,192),radius=18,fill=white))
icon('controller',lambda d:(d.rounded_rectangle((30,70,226,190),radius=46,outline=white,width=12),d.line((65,130,113,130),fill=white,width=12),d.line((89,106,89,154),fill=white,width=12),d.ellipse((166,104,184,122),fill=white),d.ellipse((187,130,205,148),fill=white)))
# Quiet geometric controller motif; no manufacturer logo.
shapes=Image.new('RGBA',(560,112));d=ImageDraw.Draw(shapes);col='#6A8DB9'
d.polygon([(55,17),(19,82),(91,82)],outline=col,width=5);d.ellipse((153,17,219,83),outline=col,width=5);d.line((291,20,355,84),fill=col,width=5);d.line((355,20,291,84),fill=col,width=5);d.rectangle((429,19,493,83),outline=col,width=5)
shapes.save(p/'symbols.png')

icon('camera',lambda d:(d.rounded_rectangle((30,80,226,198),radius=22,outline=white,width=12),d.line((72,80,88,55,165,55,183,80),fill=white,width=12),d.ellipse((93,107,163,177),outline=white,width=12)))
icon('record',lambda d:d.ellipse((58,58,198,198),fill='#FF626D'))
icon('folder',lambda d:(d.rounded_rectangle((30,75,226,200),radius=16,outline=white,width=12),d.line((30,106,30,58,98,58,123,83),fill=white,width=12)))
