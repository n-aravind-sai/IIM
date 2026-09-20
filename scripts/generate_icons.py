"""Build simple geometric application icons from vector coordinates."""
from pathlib import Path
from PIL import Image, ImageDraw
out=Path(__file__).resolve().parent.parent/'src-tauri'/'icons';out.mkdir(exist_ok=True)
image=Image.new('RGBA',(1024,1024),(13,22,29,255));draw=ImageDraw.Draw(image)
draw.rounded_rectangle((26,26,998,998),radius=200,fill=(18,40,43,255),outline=(44,82,78,255),width=15)
draw.polygon([(512,175),(791,294),(754,611),(661,752),(512,858),(363,752),(270,611),(233,294)],fill=(103,219,193,255))
draw.polygon([(512,253),(715,340),(684,585),(606,703),(512,775),(418,703),(340,585),(309,340)],fill=(18,40,43,255))
draw.rounded_rectangle((478,359,546,635),radius=24,fill=(103,219,193,255))
image.save(out/'icon.png')
image.save(out/'icon.ico',sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
image.save(out/'icon.icns')
print('Generated app icons.')
