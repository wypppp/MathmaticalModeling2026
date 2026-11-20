"""Y1 逐批回放，共用 §5.3 精确时钟。"""
import re
from collections import Counter, defaultdict
from fractions import Fraction

from check import audit, OUT, replay


def historical(n):
    data = audit.original(n, 11 if n == 2 else 10, True)
    plans, target, pre, post = {}, defaultdict(list), defaultdict(list), defaultdict(list)
    loading = defaultdict(Counter)
    unloading = defaultdict(Counter)
    for r in data[2:]:
        b, interval, u = r[:3]
        if n == 2:
            w, flow, item, qty = r[3:7]
        else:
            flow, item, qty = r[3:6]
            if not re.fullmatch(r'D\d+', str(item)):
                continue
            w = re.search(r'W[A-U]', flow)[0]
        if not re.fullmatch(r'D\d+', str(item)):
            continue
        note = r[-1] or ''
        plans[b] = u, *audit.window(interval)
        explicit = re.search(r'(?:存放至|从)(W[A-U])', note)
        home = explicit[1] if explicit else {'U7':'WU','U11':'WO'}.get(u, sorted(audit.H[u])[0])
        if n == 3 and '代' in note:
            home = {9:'WQ',23:'WO'}.get(b, home)
        amount = Fraction(qty, audit.cap[item,u])
        if w not in target[b]:
            target[b].append(w)
        pickup = flow.startswith(w) if n == 3 else '送交' not in note and not flow.startswith(u+'（发')
        if pickup:
            loading[b][w] += amount
            unloading[b][home] += amount
            if home not in post[b]:
                post[b].append(home)
        else:
            loading[b][home] += amount
            unloading[b][w] += amount
            if home not in pre[b]:
                pre[b].append(home)
    stops = {}
    for b,(u,start,end) in plans.items():
        returns = [w for w in post[b] if w not in target[b]]
        if n == 3 and b == 9:
            returns = ['WQ','WT']
        itinerary = [(w, {'发':loading[b][w]}) for w in pre[b]]
        itinerary += [(w, {'发':loading[b][w], '收':unloading[b][w]}) for w in target[b]]
        itinerary += [(w, {'收':unloading[b][w]}) for w in returns]
        stops[b] = [dict(w=w,loads=amounts) for w,amounts in itinerary+[(u,{})]]
    times,_ = replay(plans,stops,audit.dist)
    rows = []
    for b,(u,start,end) in plans.items():
        returned = times[b,len(stops[b])-1][0]//audit.DAY
        rows.append([n,b,u,start+1,end+1,returned+1,end-start+1,returned-start+1,
                     int(returned>end),' → '.join([u]+[s['w'] for s in stops[b]])])
    return rows


if __name__ == '__main__':
    audit.OUT = OUT
    records = historical(2)+historical(3)
    audit.save('Q1_batches.csv','附件,批号,单位,出发日序,表列末日,回放末日,表列天数,回放天数,表列短于回放,访问顺序',records)
    for n in (2,3):
        selected=[r for r in records if r[0]==n]
        print(n, len(selected), sum(r[6] for r in selected),sum(r[7] for r in selected),
              [r[1] for r in selected if r[8]])
