"""v2.8 问题 3：在 δ=0 的唯一出发日向量上加强多起点路线搜索（启发式，用于在证书打包前确认/改进 z*）。"""
import sys, time; sys.path.insert(0, 'src')
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import pandas as pd

def run(seed):
    import f_blocks as fb, f_parse as fp, f_p3
    from f_run_p3 import load_assign
    cap, D = fp.load_cap(), fp.load_dist(); batches, blocks = fb.build(4)
    inst = f_p3.Instance(load_assign(Path('results/F/p2/assign_tie0.csv'), blocks), batches, blocks, cap, D)
    r = pd.read_csv('results/F/p3/ref.csv').iloc[0]
    ref = dict(l=(r.l_tau, r.l_L, r.l_delta), u=(r.u_tau, r.u_L, r.u_delta))
    m = pd.read_csv('results/F/p3/batches_main.csv')
    days = {int(x.batch): int(x.start) for x in m.itertuples()}
    init = {int(x.batch): (int(x.route), int(x.start)) for x in m.itertuples()}
    t0 = time.time()
    sol, k = f_p3.fixed_day_search(inst, ref, days, 100, seed=seed, sweeps=8, slack=5, init=init if seed == 0 else None)
    return seed, k, time.time() - t0

if __name__ == '__main__':
    with ProcessPoolExecutor(4) as ex:
        for seed, k, sec in ex.map(run, range(4)):
            print('seed', seed, 'best key', k, f'{sec:.0f}s', flush=True)
