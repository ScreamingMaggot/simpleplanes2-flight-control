# -*- coding: utf-8 -*-
"""|LT| 门限的离线选型：扫描门限，看能否 100% 分离三趟的"真/假锁定段"。"""
import io, glob
segs=[]
for cid, truth in [("56590",0),("87124",1),("2389",1)]:
    p=[x for x in glob.glob("analysis/data/telemetry.0927-1309.appr*.csv") if cid in x][0]
    rows=io.open(p,encoding="utf-8").read().strip().split("\n")
    h=rows[0].split(","); d=[r.split(",") for r in rows[1:]]
    def col(n):
        i=h.index(n); out=[]
        for r in d:
            try: f=float(r[i])
            except: f=float("nan")
            if f==f and abs(f)>=1e6: f=float("nan")
            out.append(f)
        return out
    t=col("t"); rwyOk=col("rwyOk"); LT=col("LT")
    s=None; ss=[]
    for i,v in enumerate(rwyOk):
        if v==v and v>0.5 and s is None: s=i
        elif (v!=v or v<=0.5) and s is not None: ss.append((s,i-1)); s=None
    if s is not None: ss.append((s,len(rwyOk)-1))
    for a,b in ss:
        lt=[abs(LT[i]) for i in range(a,b+1) if LT[i]==LT[i]]
        if lt: segs.append((cid,truth,t[a],t[b],max(lt),len(lt)))
print("全部锁定段（%d 段）：" % len(segs))
print("%-8s %-6s %-20s %-12s %-8s %s" % ("cid","真值","时间窗","|LT|max","帧数","判读"))
for cid,truth,t0,t1,mx,n in sorted(segs, key=lambda x:x[4]):
    print("%-8s %-6s t=%6.1f..%6.1f %-12.1f %-8d %s" % (cid, "真" if truth else "假", t0,t1,mx,n,""))
print()
# 扫描门限
best=None
for thr in [1,2,3,5,10,20,50,100,300]:
    ok=True; detail=[]
    for cid,truth,t0,t1,mx,n in segs:
        pred = 1 if mx<=thr else 0
        if pred!=truth: ok=False; detail.append("%s(t=%.0f,mx=%.0f)"%(cid,t0,mx))
    print("门限 |LT|max <= %-4d : %s %s" % (thr, "干净分离" if ok else "有误判", ("  错:"+",".join(detail)) if detail else ""))
    if ok and best is None: best=thr
print()
print("=> 可用门限区间:", "1 ~ 20 m" if best else "无")
