# -*- coding: utf-8 -*-
"""离线选型：|BRG-HDG| 门限能否干净分离"误咬"与"真咬"？
   三趟真实数据 + 全帧扫描（不只看 rwyOk=1，因为误咬发生在 rwyOk=1 时）。
   输出：不同门限下的"保留真进近 / 剔除横侧误咬"矩阵。"""
import io, glob, os
cases = []
for cid in ["56590","87124","2389"]:
    p = [x for x in glob.glob("analysis/data/telemetry.0927-1309.appr*.csv") if cid in x][0]
    rows = io.open(p, encoding="utf-8").read().strip().split("\n")
    h = rows[0].split(","); d = [r.split(",") for r in rows[1:]]
    def col(n):
        i=h.index(n); out=[]
        for r in d:
            try: f=float(r[i])
            except: f=float("nan")
            if f==f and abs(f)>=1e6: f=float("nan")
            out.append(f)
        return out
    cases.append((cid, h, d, col))

print("%-8s %-26s %-26s" % ("cid","rwyOk=1 且 |BRG-HDG|<=门限","rwyOk=1 且 >门限(横侧误咬)"))
print("-"*80)
for thr in [10, 20, 30, 45, 60]:
    print("门限 %d deg:" % thr)
    for cid, h, d, col in cases:
        rwyOk=col("rwyOk"); HDG=col("HDG"); BRG=col("BRG")
        keep=miss=0
        for i in range(len(rwyOk)):
            if rwyOk[i]==rwyOk[i] and rwyOk[i]>0.5 and HDG[i]==HDG[i] and BRG[i]==BRG[i]:
                dif=abs((BRG[i]-HDG[i]+540)%360-180)
                if dif<=thr: keep+=1
                else: miss+=1
        print("   %-8s 保留 %4d 帧   剔除 %4d 帧" % (cid, keep, miss))
    print()
print("="*80)
print("判读：门限 30 deg 时 ——")
for cid, h, d, col in cases:
    rwyOk=col("rwyOk"); HDG=col("HDG"); BRG=col("BRG")
    keep=sum(1 for i in range(len(rwyOk)) if rwyOk[i]==rwyOk[i] and rwyOk[i]>0.5
             and HDG[i]==HDG[i] and BRG[i]==BRG[i] and abs((BRG[i]-HDG[i]+540)%360-180)<=30)
    tot=sum(1 for i in range(len(rwyOk)) if rwyOk[i]==rwyOk[i] and rwyOk[i]>0.5)
    print("   cid=%-7s 真进近帧保留 %3d/%3d (%.0f%%)" % (cid, keep, tot, 100.0*keep/max(1,tot)))
