import io
B=chr(92)
p='report-sc3b.tex'
s=io.open(p,encoding='utf-8').read()
i0=s.index(B+'begin{equation}')
i1=s.index(B+'end{equation}')+len(B+'end{equation}')
# also swallow the trailing 式中... sentence up to the next newline
j=s.index('\n',i1)
k=s.index('\n',j+1) if s[j+1:j+2]!='\n' else j
seg=s[i0:k]
if seg.startswith(B+'begin{equation}') and ('式中' in seg or B+'end{equation}' in seg):
    pass
new=(B+'begin{equation}\n'+B+'mathrm{sel}=\argmin_{e}\, d_{'+B+'mathrm{entry}}(e),\n'+B+'end{equation}\n'
 '候选端头须同时满足（$\beta_e$ 为端头 $e$ 的入口相对本机的方位、$\psi$ 为航向、$\hat{d}_e$ 为着陆方向单位向量）：\n'
 B+'begin{itemize}\n'
 B+'item $|\beta_e-\psi|<90^\circ$——入口位于前方半球；\n'
 B+'item $(\mathbf{thr}_e-\mathbf{pos})\cdot\hat{d}_e>300$ m——跑道头尚未越过（接管后首拍不得触发复飞）；\n'
 B+'item $d_{'+B+'mathrm{entry}}(e)\le 15$ km——不跨未知走廊瞎飞；\n'
 B+'item $|\beta_e-\psi|<45^\circ$ 的指向候选优先——飞行员意愿高于就近。\n'
 B+'end{itemize}')
s=s[:i0]+new+s[k:]
io.open(p,'w',encoding='utf-8').write(s)
print('ok')
