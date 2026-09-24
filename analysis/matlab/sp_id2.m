% sp_id2.m — 闭环辨识（已知控制器 C=0.05 反馈 pa + 0.5*pit+trim 前馈）
% 被控对象 G = K*wn^2/(s^2+2*z*wn*s+wn^2)，闭环 T = G/(1-0.05*G)
% 拟合：lsim(T, u_ext) 对 pa 最小二乘。u_ext = 0.5*pit + trim（去均值）
thisdir = fileparts(mfilename('fullpath')); cd(thisdir);
files = {'../id15.csv','../id8.csv'};
res = [];
for fi = 1:numel(files)
    d = readtable(files{fi});
    m = d.agl > 150 & d.ias > 40 & abs(d.pa) < 25;
    t = d.t(m); y = d.pa(m); u = 0.5*d.pit(m) + d.trim(m);
    t = t(:); y = y(:); u = u(:);
    if numel(t) < 500, continue; end
    fsr = 10;  % 重采样到 10Hz 均匀网格
    tg = (t(1):1/fsr:t(end))';
    y = interp1(t, y, tg); u = interp1(t, u, tg);
    y = y - mean(y); u = u - mean(u);
    t = tg;
    cost = @(q) sp_cost(q, t, u, y);
    q0 = [0, log(4), 0];   % [logK, log wn, logit z]
    q = fminsearch(cost, q0, optimset('MaxFunEvals',4000,'TolX',1e-3));
    K = exp(q(1)); wn = exp(q(2)); z = 2.5/(1+exp(-q(3)));
    J = cost(q);
    rmse = sqrt(J/numel(y));
    fprintf('== %s == N=%d  K=%.1f deg/unit  wn=%.2f rad/s (%.2f Hz)  zeta=%.2f  fitRMSE=%.2f deg\n', ...
            files{fi}, numel(t), K, wn, wn/(2*pi), z, rmse);
    res = [res; K wn z rmse];
    % 绘图：数据 vs 模型仿真
    T = tf(K*wn^2, [1, 2*z*wn + 0.05*K*wn^2, wn^2*(1+0.05*K)]);
    [ysim,tsim] = lsim(T, u, t);
    figure('Visible','off');
    plot(t, y, "b", tsim, ysim, "r--", "LineWidth", 1); grid on;
    xlabel('t (s)'); ylabel('pitch angle (deg)');
    legend('flight','closed-loop sim (K,wn,z fitted)'); title(files{fi});
    exportgraphics(gcf, fullfile(thisdir, sprintf('clfit_%d.png', fi)), 'Resolution', 130);
    close all;
end
writematrix(res, 'id_results2.csv');
disp('DONE');

function J = sp_cost(q, t, u, y)
K  = exp(q(1));
wn = exp(q(2));
z  = 2.5/(1+exp(-q(3)));
if ~isfinite(K) || ~isfinite(wn), J = 1e9; return; end
T = tf(K*wn^2, [1, 2*z*wn + 0.05*K*wn^2, wn^2*(1+0.05*K)]);
try
    [ys,~] = lsim(T, u, t);
catch
    J = 1e9; return;
end
e = y - ys;
J = sum(e.^2);
end
