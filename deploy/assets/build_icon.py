"""Rebuild the original application icon with Pillow (already a dependency)."""
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
scale = 4
image = Image.new('RGBA', (256*scale,256*scale))
draw = ImageDraw.Draw(image)
def box(coords): return tuple(round(n*scale) for n in coords)
def rect(coords, radius, fill): draw.rounded_rectangle(box(coords), radius=radius*scale, fill=fill)
def polygon(points, fill): draw.polygon([(x*scale,y*scale) for x,y in points],fill=fill)
rect((8,8,248,248),48,'#F6D4B8')
rect((51,37,211,229),12,'#DFC1A8')
rect((43,29,203,221),12,'#977257')
rect((50,36,196,214),7,'#FFFAF3')
rect((68,54,178,196),1,'#F3D7B8')
draw.ellipse(box((139,70,163,94)),fill='#ED7C13')
polygon([(68,153),(113,112),(178,160),(178,196),(68,196)],'#CD9A75')
polygon([(68,177),(145,132),(178,151),(178,196),(68,196)],'#857660')
image.resize((256,256),Image.Resampling.LANCZOS).save(ROOT/'web/icon.png',optimize=True)
# Apple's touch icon is opaque; Safari applies the platform's own presentation.
touch = Image.new('RGBA', image.size, '#F6D4B8')
touch.alpha_composite(image)
touch.convert('RGB').resize((180,180),Image.Resampling.LANCZOS).save(ROOT/'web/apple-touch-icon.png',optimize=True)
image.resize((256,256),Image.Resampling.LANCZOS).save(ROOT/'web/favicon.ico',sizes=[(16,16),(32,32),(48,48)])
