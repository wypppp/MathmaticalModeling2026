import numpy as np, math
rng=np.random.default_rng(0)
d=math.radians(1)
def clip(poly, p0, n):  # keep n·(x-p0) >= 0
    out=[]
    for i in range(len(poly)):
        a,b=poly[i],poly[(i+1)%len(poly)]
        fa,fb=np.dot(n,a-p0),np.dot(n,b-p0)
        if fa>=0: out.append(a)
        if fa*fb<0: out.append(a+(b-a)*fa/(fa-fb))
    return out
def region(S,th):
    B=1e5; poly=[np.array(v,float) for v in [(-B,-B),(B,-B),(B,B),(-B,B)]]
    for s,t in zip(S,th):
        for sgn in (+1,-1):
            a=t+sgn*d; u=np.array([math.cos(a),math.sin(a)])
            n=np.array([-u[1],u[0]])*(-sgn)  # inside toward bearing
            poly=clip(poly,s,n)
            if len(poly)<3: return None
        # also forward: n=dir
        u=np.array([math.cos(t),math.sin(t)]); poly=clip(poly,s,u)
        if len(poly)<3: return None
    return poly
worst=1e9; ex=None
for it in range(200000):
    G=np.zeros(2)
    S=[]; th=[]
    for k in range(2):
        r=rng.uniform(5,1500); a=rng.uniform(0,2*math.pi)
        s=G+r*np.array([math.cos(a),math.sin(a)]); S.append(s)
        th.append(math.atan2(*(G-s)[::-1])+rng.uniform(-d,d))
    P=region(S,th)
    if P is None: continue
    P=np.array(P)
    if np.abs(P).max()>9e4: continue
    D=0;AB=None
    for i in range(len(P)):
        for j in range(i+1,len(P)):
            dd=np.linalg.norm(P[i]-P[j])
            if dd>D: D=dd;AB=(P[i],P[j])
    A,Bp=AB
    m=min(np.dot(X-A,X-Bp)/D**2 for X in P)
    v=max(np.dot(X-A,X-Bp)/D**2 for X in P)
    if -v<worst: worst=-v; ex=(S,th,v)
print('max normalized (X-A)(X-B)/D^2 over samples (>0 => NOT covered):', -worst)
S,th,v=ex
G=np.zeros(2)
r=[np.linalg.norm(s) for s in S]
b=[math.degrees(math.atan2(*(G-s)[::-1])) for s in S]
print('r1,r2=',[round(x,1) for x in r],'crossing angle=',round(abs((b[0]-b[1]+180)%360-180),2),'deg')
print('errors (deg)=',[round(math.degrees(t)-bb,3) for t,bb in zip(th,b)])
P=np.array(region(S,th)); print('n vertices',len(P))
