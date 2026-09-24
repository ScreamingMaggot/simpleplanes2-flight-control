% sp_id3.m — 闭环辨识 v3：G 增益为负（正杆=低头），多初值防局部极小
thisdir = fileparts(mfilename('fullpath')); cd(thisdir);
files = {'../data/id15.csv','../data/id8.csv'};
res = [];
for fi = 1:numel(files)
    d = readtable(files{fi});
    m = d.agl > 150 & d.ias > 40 & abs(d.pa) < 25;
    t = d.t(m); y = d.pa(m); u = 0.5*d.pit(m) + d.trim(m);
    t = t(:); y = y(:); u = u(:);
    if numel(t) < 500, continue; end
    tg = (t(1):0.1:t(end))';
    y = interp1(t, y, tg); u = interp1(t, u, tg);
    y = y - mean(y); u = u - mean(u);
    best = struct('J',inf);
    for wn0 = [2 4 6]
        for z0 = [0.2 0.5]
            q0 = [log(15), log(wn0), log(z0/(2.5-z0)*(1))];
            q = fminsearch(@(q) sp_cost(q, tg, u, y), q0, ...
                           optimset('MaxFunEvals',3000,'TolX',1e-3));
            J = sp_cost(q, tg, u, y);
            if J < best.J, best = struct('q',q,'J',J); end
        end
    end
    q = best.q;
    Kneg = exp(q(1)); wn = exp(q(2)); z = 2.5/(1+exp(-q(3)));
    rmse = sqrt(best.J/numel(y));
    fprintf('== %s == N=%d  K=-%.1f deg/unit  wn=%.2f rad/s (%.2f Hz)  zeta=%.2f  RMSE=%.2f deg\n', ...
            files{fi}, numel(t), Kneg, wn, wn/(2*pi), z, rmse);
    res = [res; -Kneg wn z rmse];
    T = tf(-Kneg*wn^2, [1, 2*z*wn, wn^2*(1+0.05*Kneg)]);
    [ysim,tsim] = lsim(T, u, tg);
    figure('Visible','off');
    plot(tg, y, 'b', tsim, ysim, 'r--', 'LineWidth', 1); grid on;
    xlabel('t (s)'); ylabel('pitch (deg)');
    legend('flight','closed-loop sim'); title(files{fi});
    exportgraphics(gcf, fullfile(thisdir, sprintf('clfit_%d.png', fi)), 'Resolution', 130);
    close all;
end
writematrix(res, 'id_results3.csv');
disp('DONE');

function J = sp_cost(q, t, u, y)
Kp = exp(q(1)); wn = exp(q(2)); z = 2.5/(1+exp(-q(3)));
if ~isfinite(Kp)||~isfinite(wn)||wn>15, J=1e9; return; end
% G = -Kp*wn^2/(s^2+2 z wn s + wn^2);  闭环 T=G/(1-0.05G)
T = tf(-Kp*wn^2, [1, 2*z*wn, wn^2*(1+0.05*Kp)]);
try
    [ys,~] = lsim(T, u, t);
catch
    J = 1e9; return;
end
J = sum((y - ys).^2);
end
