"""Read retained RGB PNGs and compare native and pilot yellow-stamina regions."""
import json,struct,sys,zlib
from collections import Counter
from pathlib import Path

def rgb_rows(path):
    data=Path(path).read_bytes()
    if data[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError('PNG required')
    pos=8;compressed=[];width=height=kind=None
    while pos<len(data):
        n=struct.unpack_from('>I',data,pos)[0];tag=data[pos+4:pos+8];payload=data[pos+8:pos+8+n];pos+=n+12
        if tag==b'IHDR':width,height,depth,kind,_,_,_=struct.unpack('>IIBBBBB',payload)
        if tag==b'IDAT':compressed.append(payload)
        if tag==b'IEND':break
    if depth!=8 or kind!=2 or (width,height)!=(1920,1080):raise ValueError('Expected full-scale 1920x1080 RGB capture')
    raw=zlib.decompress(b''.join(compressed));stride=width*3;index=0;previous=bytes(stride)
    for y in range(height):
        mode=raw[index];index+=1;row=bytearray(raw[index:index+stride]);index+=stride
        if mode not in range(5):raise ValueError('Unsupported PNG filter')
        for i in range(stride):
            left=row[i-3] if i>=3 else 0;up=previous[i];upper_left=previous[i-3] if i>=3 else 0
            if mode==1:predictor=left
            elif mode==2:predictor=up
            elif mode==3:predictor=(left+up)//2
            elif mode==4:
                p=left+up-upper_left;distance=(abs(p-left),abs(p-up),abs(p-upper_left));predictor=(left,up,upper_left)[distance.index(min(distance))]
            else:predictor=0
            row[i]=(row[i]+predictor)&255
        previous=row;yield y,row

def pilot_yellow(r,g,b):
    top=max(r,g,b);bottom=min(r,g,b);delta=top-bottom
    if top<150 or top==0 or delta*255<190*top or delta==0:return False
    if top==r:hue=((g-b)/delta)%6
    elif top==g:hue=(b-r)/delta+2
    else:hue=(r-g)/delta+4
    return 36<=hue*60<=56

def inspect(path):
    regions={'native':(1000,430,1100,630),'pilot':(1000,430,1220,630),'gaugeRight':(1030,430,1120,650),'avatar':(850,350,1250,900),'nearby':(350,320,1500,930),'questHudControl':(40,240,550,320),'full':(0,0,1920,1080)}
    totals={k:Counter() for k in regions};bounds={k:[9999,9999,-1,-1] for k in regions};tiles=Counter()
    for y,row in rgb_rows(path):
        for x in range(1920):
            r,g,b=row[x*3:x*3+3]
            exact=(r,g,b)==(255,199,0);yellow=pilot_yellow(r,g,b);bright=min(r,g,b)>=180
            if not exact and not yellow and not bright:continue
            if yellow:tiles[(x//120,y//120)]+=1
            for name,(left,top,right,bottom) in regions.items():
                if left<=x<right and top<=y<bottom:
                    totals[name]['nativeExact']+=exact;totals[name]['pilotHsv']+=yellow;totals[name]['brightNeutral']+=bright
                    if yellow:
                        box=bounds[name];box[0]=min(box[0],x);box[1]=min(box[1],y);box[2]=max(box[2],x);box[3]=max(box[3],y)
    return {'image':str(path),'regions':{k:{'nativeExact':totals[k]['nativeExact'],'pilotHsv':totals[k]['pilotHsv'],'brightNeutral':totals[k]['brightNeutral'],'yellowBounds':None if bounds[k][2]<0 else bounds[k]} for k in regions},'topYellowTiles':[{'x':x*120,'y':y*120,'pixels':count} for (x,y),count in tiles.most_common(12)]}

if __name__=='__main__':
    for filename in sys.argv[1:]:print(json.dumps(inspect(filename),separators=(',',':')))
