"""Extract per-cell, per-row ink runs from a mono sample image."""
from PIL import Image; import numpy as np, collections, sys, json
def runs(b):
    r=[];s=None
    for i,v in enumerate(b):
        if v and s is None:s=i
        if not v and s is not None:r.append((s,i));s=None
    if s is not None:r.append((s,len(b)))
    return r
def bands(im):
    """group row-runs into text lines (gap > 10px splits lines)"""
    rr=runs(im.any(1)); lines=[]; cur=[rr[0]]
    for a in rr[1:]:
        if a[0]-cur[-1][1]>10: lines.append(cur); cur=[a]
        else: cur.append(a)
    lines.append(cur); return lines

def cell_grid(im, rowbands, x_left, cols, colw):
    """coverage grid: rows x cols, each value 0..1"""
    out=[]
    for (a,b) in rowbands:
        strip=im[a:b].mean(0)  # per-pixel column coverage
        row=[]
        for c in range(cols):
            l=x_left+c*colw; r=l+colw
            xs=np.arange(int(np.floor(l)),int(np.ceil(r)))
            w=np.clip(np.minimum(xs+1,r)-np.maximum(xs,l),0,1)
            v=(strip[np.clip(xs,0,len(strip)-1)]*w).sum()/w.sum()
            row.append(v)
        out.append(row)
    return out
def ascii(g):
    return [''.join('#' if v>0.65 else ('+' if v>0.3 else '.') for v in r) for r in g]
