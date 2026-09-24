% sp_id.m — 短周期辨识：elev->pa 二阶模型
thisdir = fileparts(mfilename('fullpath')); cd(thisdir);
files = {'../id15.csv','../id8.csv'};
out = [];
for fi = 1:numel(files)
    d = readtable(files{fi});
    m = d.agl > 150 & d.ias > 40;
    t = d.t(m); u = d.elev(m); y = d.pa(m);
    if numel(t) < 500, continue; end
    u = u - mean(u); y = y - mean(y);
    fs = 1/median(diff(t));
    [Pxy,f] = tfestimate(u, y, hanning(256), 128, [], fs);
    [Pxx,~] = pwelch(u, hanning(256), 128, [], fs);
    [Cxy,fc] = mscohere(u, y, hanning(256), 128, [], fs);
    H = Pxy ./ Pxx;
    band = f > 0.05 & f < 3.0 & Cxy > 0.1;
    fb = f(band); Hb = H(band); Cb = Cxy(band);
    mdl = @(p,s) p(1)*p(2)^2 ./ (s.^2 + 2*p(3)*p(2)*s + p(2)^2);
    obj = @(p) sum(Cb .* (20*log10(abs(mdl(p, 1i*2*pi*fb)) + eps) ...
                        - 20*log10(abs(Hb) + eps)).^2);
    p0 = [12, 4, 0.3];
    lb = [0.1, 0.5, 0.02]; ub = [200, 20, 3];
    p = fminsearch(@(q) obj([exp(q(1)) exp(q(2)) 1/(1+exp(-q(3)))*1.5]), ...
                   [log(p0(1)) log(p0(2)) 0]);
    K = exp(p(1)); wn = exp(p(2)); z = 1.5/(1+exp(-p(3)));
    fprintf('== %s == fs=%.1fHz N=%d  wn=%.2f rad/s (%.2f Hz)  zeta=%.2f  K=%.1f deg/unit\n', ...
            files{fi}, fs, numel(t), wn, wn/(2*pi), z, K);
    out = [out; wn z K];
    % 绘图
    figure('Visible','off'); s = 1i*2*pi*f;
    Hm = mdl([K wn z], s);
    subplot(2,1,1); semilogx(f,20*log10(abs(H)+eps),'b', f,20*log10(abs(Hm)+eps),'r--');
    grid on; xlabel('Hz'); ylabel('|G| dB'); xlim([0.03 4]);
    legend('flight FRF','2nd-order fit'); title(files{fi});
    subplot(2,1,2); semilogx(f,(180/pi)*angle(H),'b', f,(180/pi)*angle(Hm),'r--');
    grid on; xlabel('Hz'); ylabel('phase deg'); xlim([0.03 4]);
    exportgraphics(gcf, fullfile(thisdir, sprintf('bode_fit_%d.png', fi)), 'Resolution', 130);
    close all;
end
writematrix(out, 'id_results.csv');
disp('DONE');
