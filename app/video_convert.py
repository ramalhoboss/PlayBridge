"""Display conversion with deterministic rounding across FFmpeg scaling slices."""
from av.video.reformatter import Interpolation

def reformat_for_display(frame,width,height,pixel_format):
 # Automatic slice threading with default rounding produced bright first-column
 # pixels at slice boundaries for sizes such as 1468x826 in the bundled FFmpeg.
 # BITEXACT avoids that path while retaining parallel scaling and the full image.
 return frame.reformat(width=width,height=height,format=pixel_format,
                       interpolation=Interpolation.BILINEAR | Interpolation.BITEXACT)
