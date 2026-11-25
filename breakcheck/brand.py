"""Dependency-free, deterministic BreakCheck shield artwork."""
import struct
import zlib
from functools import lru_cache

SHIELD=((32,2),(58,12),(56,37),(47,50),(32,62),(17,50),(8,37),(6,12))
CHECK=((15,30),(20,25),(28,34),(44,18),(50,23),(28,45))

def contains(x,y,polygon):
    inside=False
    a=polygon[-1]
    for b in polygon:
        if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:
            inside=not inside
        a=b
    return inside

def chunk(tag,data):
    return struct.pack('>I',len(data))+tag+data+struct.pack('>I',zlib.crc32(tag+data)&0xffffffff)

@lru_cache(maxsize=8)
def icon_png(size=64):
    if size not in (16,24,32,48,64,128,256):
        raise ValueError('Unsupported icon size')
    rows=[]
    for y in range(size):
        row=bytearray([0])
        for x in range(size):
            px,py=(x+.5)*64/size,(y+.5)*64/size
            if contains(px,py,CHECK):
                row.extend((255,255,255,255))
            elif contains(px,py,SHIELD):
                row.extend((37,99,235,255))
            else:
                row.extend((0,0,0,0))
        rows.append(bytes(row))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',size,size,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b'')
