"""Read a .map26 with the same schema tools/generate_maps.py writes."""
def _varint(d, o):
    r=s=0
    while True:
        b=d[o]; o+=1; r |= (b & 0x7F) << s; s+=7
        if not b & 0x80: return r,o
def read_map(path):
    d=open(path,"rb").read(); o=0; w=h=None; rows=[]
    while o < len(d):
        key,o=_varint(d,o); field,wire=key>>3, key&7
        if wire==0:
            v,o=_varint(d,o)
            if field==1: w=v
            elif field==2: h=v
        elif wire==2:
            ln,o=_varint(d,o); payload=d[o:o+ln]; o+=ln
            if field==3:
                p=0; k2,p=_varint(payload,p)
                if k2>>3==1 and k2&7==2:
                    n,p=_varint(payload,p); rows.append(payload[p:p+n])
        else:
            raise ValueError(f"wire {wire}")
    return w,h,rows
def stats(path):
    w,h,rows=read_map(path)
    ore=sum(r.count(2) for r in rows); wall=sum(r.count(1) for r in rows)
    return w,h,ore,wall
