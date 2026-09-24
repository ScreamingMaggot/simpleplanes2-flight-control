# SC-3b 跑道表核对工具：读日志里的 RWY CAPTURED / RWY SEL 行，对静态表打残差
# 用法: python calib_rwy.py [日志文件...]
import io, os, sys, re, json

_S = os.path.dirname(os.path.abspath(__file__))
TABLE = json.load(open(os.path.join(_S, '..', 'data', 'runway-locations.json'), encoding='utf-8'))
# 与 telemetry-addon.lua 同步的映射：lat=z、lon=x（CraftProxy.cs 恒等实锤；SP1 区才有 -400000 偏移，四机场均非 SP1 区）
ENTRIES = []
for e in TABLE:
    if 'Airport' not in e['id']:
        continue
    x, y, z = (float(v) for v in e['pos'].split(','))
    hdg = float(e['rot'].split(',')[1])
    ENTRIES.append(dict(id=e['id'], name=e['name'], lat=z, lon=x, hdg=hdg % 360, alt=y))

def wrapd(a):
    return (a + 180) % 360 - 180

caps = []
for path in sys.argv[1:] or [os.path.join(_S, '..', 'data', 'Player.landing-sc3-v417.log')]:
    with io.open(path, encoding='utf-8', errors='ignore') as f:
        for ln in f:
            m = re.match(r'RWY CAPTURED lat=(-?[\d.]+) lon=(-?[\d.]+) hdg=([\d.]+)', ln.strip())
            if m:
                caps.append((os.path.basename(path), float(m.group(1)), float(m.group(2)), float(m.group(3))))
if not caps:
    print("日志里没有 RWY CAPTURED 行（需出生帧 AUTOCAP）")
    sys.exit(0)
print("%-28s %14s %5s   %-16s %8s %7s %7s" % ("日志/捕获", "捕获(lat,lon)", "hdg", "最近表项", "dlat", "dlon", "水平"))
for src, lat, lon, hdg in caps:
    best = min(ENTRIES, key=lambda e: ((e['lat']-lat)**2 + (e['lon']-lon)**2))
    dl, dn = best['lat']-lat, best['lon']-lon
    dh = wrapd(best['hdg'] - hdg)
    flag = "" if abs(dh) < 30 and (dl*dl+dn*dn)**0.5 < 600 else "  <-- 不匹配?"
    print("%-28s (%9.0f,%9.0f) %5.0f   %-16s %+8.0f %+7.0f %7.0f  dh=%+.0f%s"
          % (src[:28], lat, lon, hdg, best['name'], dl, dn, (dl*dl+dn*dn)**0.5, dh, flag))
print("\n注：残差=出生点物理停在 threshold 后方沿跑道轴的量（正常 ±400m 内、方向应与 hdg 反向）。")
