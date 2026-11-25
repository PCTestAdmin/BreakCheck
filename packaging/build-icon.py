"""Generate the multi-resolution Windows icon used by EXEs and setup."""
from pathlib import Path
import io
import sys
from PIL import Image
root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root))
from breakcheck.brand import icon_png

sizes=(16,24,32,48,64,128,256)
image=Image.open(io.BytesIO(icon_png(256)))
image.save(root/'packaging'/'BreakCheck.ico',format='ICO',sizes=[(n,n) for n in sizes],bitmap_format='bmp')
with Image.open(root/'packaging'/'BreakCheck.ico') as result:
    if not {(16,16),(32,32),(48,48),(256,256)} <= result.ico.sizes():
        raise RuntimeError('Windows icon is missing required sizes.')
