"""独立抽查不提前出发、禁用代领③两项。需要 openpyxl、ortools。"""
from collections import defaultdict
from fractions import Fraction
from itertools import permutations
from math import ceil, floor
from ortools.sat.python import cp_model

from check import audit


def no_early():
    groups, _, _, origin, _ = audit.allocation(audit.RESULTS/'问题2_results.xlsx')
    producer,receiver = [next(b for b,k in origin.items() if k==i) for i in (13,25)]
    assert any(g['b']==receiver and g.get('recovery') and
               any(x['b']==producer and x['key']==g['key'] for x in groups) for g in groups)
    moves = defaultdict(lambda: defaultdict(Fraction))
    for g in groups:
        if g['b']==producer:
            assert g['side'] in ('收','发')
            s=sum(Fraction(q,audit.cap[d,'U6']) for d,q in g['items'])
            moves[g['w']][g['side']]+=s
            moves['WP']['收' if g['side']=='发' else '发']+=s
    mandatory={'U6',*moves}
    shortest={(a,b):audit.dist[a,b] for a in mandatory for b in mandatory}
    for k in mandatory:
        for a in mandatory:
            for b in mandatory:
                shortest[a,b]=min(shortest[a,b],shortest[a,k]+shortest[k,b])
    # Relax WP visit ordering completely; even omitting WP as required stop suffices.
    km=min(sum(shortest[a,b] for a,b in zip(('U6',*order),(*order,'U6')))
           for order in permutations(mandatory-{'U6','WP'}))
    cars=sum(ceil(s) for sides in moves.values() for s in sides.values())
    hours=Fraction(2*km,125)+Fraction(2*cars,5)
    earliest=audit.requests[13][1]+ceil(hours/8)
    deadline=audit.requests[25][2]
    print('不提前',km,cars,float(hours),ceil(hours/8),'领回最早/最晚日序',earliest+1,deadline+1)
    assert earliest>deadline


def no_r3():
    # Relaxation: candidates may use all original targets, but every supporting
    # warehouse must retain an own block. Ignore route mileage for a lower bound.
    m=cp_model.CpModel()
    own={k:m.new_bool_var(f'own{i}') for i,k in enumerate(audit.keys)}
    units={b:u for b,(u,a,e) in audit.requests.items()}
    active={}
    for b in units:
        active[b]=m.new_bool_var(f'active{b}')
        m.add_max_equality(active[b],[v for k,v in own.items() if k[0]==b])
    def support(b,w):
        return [v for k,v in own.items() if k[0]==b and k[1]==w and w not in audit.H[units[b]]]
    side_load=defaultdict(list)
    original_load=defaultdict(Fraction)
    transfers=[]
    u9=[]
    scale=10**7
    for k,keep in own.items():
        src,w,side,h=k
        y=units[src]
        def size(x):
            return sum(Fraction(q,audit.cap[d,x]) for d,q in audit.blocks[k])
        original_load[src,side]+=size(y)
        side_load[src,side].append(floor(size(y)*scale)*keep)
        choices=[keep]
        for b,x in units.items():
            if x==y or (y=='U9' and x!='U6'):
                continue
            orientations=[(w,side,h)]
            if side=='发' and w in set.union(*audit.H.values())-audit.H[y]:
                orientations.append((h,'收',w))
            for target,direction,home in orientations:
                supporters=support(b,target)
                if not supporters:
                    continue
                via=support(b,home)
                shared=home in audit.H[x]
                possible=shared or bool(via) or audit.dist[x,home]<=150
                if direction=='发' and not possible:
                    # Allow R4 whenever a candidate return batch exists under
                    # static date and warehouse conditions (deliberate relaxation).
                    possible=any(units[r]==y and audit.requests[b][1]-6<=audit.requests[r][2]
                                 and any(support(r,hx) for hx in audit.H[x]) for r in units)
                if not possible:
                    continue
                v=m.new_bool_var(f'x{len(transfers)}')
                transfers.append(v)
                m.add(v<=sum(supporters))
                # R2/R8 require actual retained support when they are the sole case.
                if direction=='收' and not shared and audit.dist[x,home]>150:
                    m.add(v<=sum(via))
                if direction=='发' and not shared:
                    # R2, R4 or R5. For R5 a matching source delivery must exist.
                    r5=(audit.dist[x,home]<=150 and any(kk[3]==home and kk[2]=='收'
                        and units[kk[0]]==y and support(b,kk[1]) for kk in own))
                    # Also allow an internally reversed pickup as the paired delivery.
                    r5 |= (audit.dist[x,home]<=150 and any(units[kk[0]]==y and kk[2]=='发'
                              and kk[1]==home and support(b,kk[3]) for kk in own))
                    r4=any(units[r]==y and audit.requests[b][1]-6<=audit.requests[r][2]
                           and any(support(r,hx) for hx in audit.H[x]) for r in units)
                    if not (r4 or r5):
                        m.add(v<=sum(via))
                side_load[b,direction].append(floor(scale*size(x))*v)
                if y=='U9':
                    u9.append(v)
                choices.append(v)
        m.add_exactly_one(choices)
    for (b,direction),terms in side_load.items():
        t0=ceil(max(original_load[b,'发'],original_load[b,'收']))
        m.add(sum(terms)<=min(30,t0+3)*scale)
    solver=cp_model.CpSolver()
    solver.parameters.num_workers=1
    m.maximize(sum(u9))
    assert solver.solve(m)==cp_model.OPTIMAL and solver.value(sum(u9))==5
    m.add(sum(u9)==5)
    m.minimize(sum(active.values()))
    status=solver.solve(m)
    print('禁用③的放松下界',solver.status_name(status),solver.best_objective_bound)
    assert status==cp_model.OPTIMAL and solver.value(sum(active.values()))==33
    # Upper bound: restore the sole R3 block to its original cancelled batch.
    # Both changed batches now consist solely of own pickup at WE.
    _,assigned,units,origin,_=audit.allocation(audit.RESULTS/'问题2_results.xlsx')
    old_b=assigned[audit.keys[11]]['b']
    assert len(origin)==32 and 6 not in origin.values() and origin[old_b]==17
    assert sorted(k[0] for k,g in assigned.items() if g['b']==old_b)==[6,17]
    for b in (6,17):
        k,=[k for k in audit.keys if k[0]==b]
        _,w,side,h=k
        unit=audit.requests[b][0]
        assert w=='WE' and side=='发' and h in audit.H[unit]
        mass=sum(Fraction(q,audit.cap[d,unit]) for d,q in audit.blocks[k])
        km=audit.dist[unit,w]+audit.dist[w,h]+audit.dist[h,unit]
        assert ceil(mass)<=30 and km<=2000
        print('33批见证的变动原批',b,unit,'运力',ceil(mass),'公里',km)


if __name__=='__main__':
    no_early()
    no_r3()
