#!/usr/bin/env python3
"""TESTaircraft 离线气动模型：几何→升力线→中性点→配平。
CG 以设计器读数为输入（本机存的质量语义不完整，见 platform-facts §十五）。
用法: python craft_model.py [craft.xml] [CG距主翼前缘_m]"""
import xml.etree.ElementTree as ET
import math, sys

RHO, G = 1.225, 9.81

def naca4(code):
    """薄翼理论：α_L0(°)、Cm_ac、m、p、t。"""
    m, p, t = int(code[4])/100.0, int(code[5])/10.0, int(code[6:])/100.0
    n = 4000
    th = [1e-9 + (math.pi-2e-9)*i/(n-1) for i in range(n)]
    xi = [(1-math.cos(a))/2 for a in th]
    zc = [0.0 if m == 0 else (m/p/p*(2*p*x-x*x) if x < p else m/(1-p)**2*((1-2*p)+2*p*x-x*x)) for x in xi]
    d = [(zc[i+1]-zc[i-1])/(xi[i+1]-xi[i-1]) for i in range(1, n-1)]
    dd = [0.0]+d+[0.0]
    a0 = -(1/math.pi)*sum(dd[i]*(th[1]-th[0]) for i in range(n))   # α_L0 = -(1/π)∫ dz/dx dθ
    cm0 = (m/(p*p))*((1-p)*(2*p*p-2*p+1)/3 + 2*p*p*math.log(1-p)) if m > 0 and 0 < p < 1 else 0.0
    return math.degrees(a0), -cm0, m, p, t

def wing3d(S, b, cl0deg):
    AR = b*b/S
    a0 = 2*math.pi
    a = a0/(1 + a0/(math.pi*0.92*AR))
    return AR, a

def panel(w):
    cr, ct, span = w['cr'], w['ct'], w['span']
    S = (cr+ct)/2*span
    mac = 2/3*(cr+ct-cr*ct/(cr+ct))
    return S, mac

def main():
    path = sys.argv[2] if len(sys.argv) > 2 else r"C:/Users/Administrator/AppData/LocalLow/Jundroo/SimplePlanes 2/Crafts/TESTaircraft.xml"
    cg = float(sys.argv[1]) if len(sys.argv) > 1 else None
    root = ET.parse(path).getroot()
    spec = root.find('Specifications')
    W = float(spec.get('EmptyWeight'))
    groups = {'main': [], 'tail': [], 'fin': []}
    for p in root.iter('Part'):
        if p.get('partType') != 'JWing-1':
            continue
        st = p.find('JWing.State')
        pos = [float(x) for x in p.get('position').split(',')]
        rot = [float(x) for x in (p.get('rotation') or '0,0,0').split(',')]
        sl = st.findall('Slice')
        w = dict(pos=pos, span=float(sl[-1].get('position')),
                 cr=float(sl[0].get('scale')), ct=float(sl[-1].get('scale')),
                 aoa=float(sl[0].get('angleOfAttack', 0)))
        if abs(rot[2]) > 45 and abs(rot[2]) < 135:
            groups['fin'].append(w)
        elif pos[2] < -2:
            groups['tail'].append(w)
        else:
            groups['main'].append(w)
    mw = max(groups['main'], key=lambda w: w['span'])
    Sm, mac_m = panel(mw); Sm *= 2
    b = 2*(abs(mw['pos'][0]) + mw['span'])
    tw = max(groups['tail'], key=lambda w: w['span'])
    St, mac_t = panel(tw); St *= 2
    lt = (mw['pos'][2] - 0.25*mac_m) - (tw['pos'][2] - 0.25*mac_t)
    Vbar = St*lt/(Sm*mac_m)
    ARm, am = wing3d(Sm, b, 0)
    bt = 2*(abs(tw['pos'][0]) + tw['span'])
    ARt, at = wing3d(St, bt, 0)
    a0w, cm0w, *_ = naca4('NACA3412')
    a0t, cm0t, *_ = naca4('NACA0012')
    eps = (4.44/ARm)*(ARm+2.25)/(ARm+10*(lt/mac_m))     # Anderson 下洗系数 dε/dα
    h_np = 0.25 + (at/am)*Vbar*(1-eps)                   # 中性点（主翼 MAC 分数）
    V = 85
    CL = W*G/(0.5*RHO*V*V*Sm)
    print("=== TESTaircraft 离线模型（薄翼+升力线一阶近似）===")
    print(f"空重 {W:.0f} kg   翼载 {W/Sm:.1f} kg/m²")
    print(f"主翼  S={Sm:.2f} m²  b={b:.2f} m  MAC={mac_m:.2f} m  AR={ARm:.2f}  a={am/math.degrees(1):.3f}/°  (NACA3412 αL0={a0w:.1f}°, Cm_ac={cm0w:.3f})")
    print(f"平尾  S={St:.2f} m²  MAC={mac_t:.2f} m  尾臂 l_t={lt:.2f} m (={lt/mac_m:.2f}c̄)  V̄={Vbar:.3f}  a_t={at/math.degrees(1):.3f}/°")
    print(f"下洗 dε/dα={eps:.3f}   中性点 h_np = {100*h_np:.1f}% MAC = 主翼前缘后 {h_np*mac_m:.2f} m")
    print(f"配平@{V} m/s: CL={CL:.3f} → α_eff={math.degrees(CL/am):.1f}° → 几何迎角≈{math.degrees(CL/am)-a0w:.1f}°")
    if cg is not None:
        sm = (h_np*mac_m - cg)/mac_m*100
        print(f"CG(前缘后 {cg:.2f} m) → 静稳裕度 SM = {sm:.1f}% MAC")
        print(f"配平所需平尾升力系数增量 ≈ CL_t = -Cm_ac/(a_t·l_t/S_t)（含机身贡献，误差±50%，实飞辨识校准）")
    else:
        print(">> 传入 CG 读数：python craft_model.py <CG距前缘m> [xml]  得静稳裕度")

if __name__ == '__main__':
    main()
