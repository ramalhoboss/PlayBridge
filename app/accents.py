"""Settings › Appearance › Colour: the colour PlayBridge draws its highlights in, and how dark the picture behind the pages is.

The colours are PlayBridge's own. Each one keeps dark text readable on it and stays readable itself on the black pages, and none is the
green PlayBridge uses for a friend who is online."""
ACCENTS={
 'Gold':('#D4AF37','#EBD48E','#E2C25A'),
 'Sky':('#5FA8FF','#B4D5FF','#86BEFF'),
 'Teal':('#22C9C9','#9DEBEB','#4DD6D6'),
 'Coral':('#FF7B6B','#FFBDB4','#FF9C90'),
 'Violet':('#A98BFF','#D3C5FF','#BFA8FF'),
 'Silver':('#C8CDD6','#E8EBF0','#DADEE5'),
}
DEFAULT='Gold'
# How much black lies over the picture behind the pages and the Games page's art.
SHADES={'Bright':0.0,'Dim':0.3,'Dimmer':0.5,'Darkest':0.7}

def accent(name):
 """The main colour, a softer one for news and small text, and one for a pointer over a control."""
 return ACCENTS.get(name) or ACCENTS[DEFAULT]
def shade(name):return SHADES.get(name,0.0)

def apply_classic(name):
 """The Games page's tiles are drawn in Python, from luxury_theme's and scene's colours: they take the accent when PlayBridge opens.
 Gold leaves them exactly as they were."""
 if name not in ACCENTS or name==DEFAULT:return
 main,soft,hover=ACCENTS[name]
 import luxury_theme,scene
 luxury_theme.GOLD=scene.GOLD=main;luxury_theme.GOLD_SOFT=soft;luxury_theme.GOLD_HOVER=scene.GOLD_HOVER=hover

def contrast(first,second):
 """WCAG contrast ratio of two '#RRGGBB' colours."""
 def light(code):
  parts=[int(code[i:i+2],16)/255 for i in (1,3,5)]
  parts=[part/12.92 if part<=0.03928 else ((part+0.055)/1.055)**2.4 for part in parts]
  return 0.2126*parts[0]+0.7152*parts[1]+0.0722*parts[2]
 high,low=sorted((light(first),light(second)),reverse=True)
 return (high+0.05)/(low+0.05)
