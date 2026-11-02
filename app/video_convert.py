"""Display conversion with deterministic rounding across FFmpeg scaling slices."""
from av.video.reformatter import Interpolation

# Without FULL_CHR_H_INT two neighbouring pixels share one colour, and BITEXACT
# alone leaves the picture about 2 levels too dark at every level.
FLAGS=Interpolation.BITEXACT | Interpolation.FULL_CHR_H_INT | Interpolation.ACCURATE_RND

def reformat_for_display(frame,width,height,pixel_format):
 # Automatic slice threading with default rounding produced bright first-column
 # pixels at slice boundaries for sizes such as 1468x826 in the bundled FFmpeg.
 # BITEXACT avoids that path while retaining parallel scaling and the full image.
 # Measured on a real 4K recording: from half size down, area costs about 0.4 ms
 # more than bilinear with far more detail; nearer full size bicubic beats it.
 scaler=Interpolation.AREA if frame.width>=width*2 else Interpolation.BICUBIC
 return frame.reformat(width=width,height=height,format=pixel_format,interpolation=scaler | FLAGS)
