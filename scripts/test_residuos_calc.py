from collections import Counter
from datetime import datetime, timedelta

def _to_float_safe(x):
    try:
        return float(x or 0)
    except Exception:
        return 0.0

def _normalize_volume(v):
    f = _to_float_safe(v)
    if abs(f) > 100:
        try:
            return f / 1000.0
        except Exception:
            return f
    return f

sample_rdos = [
    {'data': '2025-12-12', 'total_liquido': 800, 'quantidade_bombeada': None, 'tanques': []},
    {'data': '2026-01-06', 'total_liquido': None, 'quantidade_bombeada': 1.2, 'tanques': []},
    {'data': '2026-01-06', 'total_liquido': None, 'quantidade_bombeada': None, 'tanques': [ {'total_liquido': 500} ]},
    {'data': '2026-01-05', 'total_liquido': 2.5, 'quantidade_bombeada': None, 'tanques': []},
    {'data': '2025-12-12', 'total_liquido': None, 'quantidade_bombeada': None, 'residuos_totais':1500, 'residuos_solidos':200, 'tanques': []},
]

start = datetime.strptime('2025-12-01', '%Y-%m-%d').date()
end = datetime.strptime('2026-01-10', '%Y-%m-%d').date()

counter = Counter()

for rdo in sample_rdos:
    d = rdo.get('data')
    if not d:
        continue
    ds = d
    val_total_liquido = rdo.get('total_liquido')
    val_quantidade_bombeada = rdo.get('quantidade_bombeada')

    t_total = _to_float_safe(val_total_liquido)
    t_quant = _to_float_safe(val_quantidade_bombeada)

    if t_total and t_total != 0:
        liquido = _normalize_volume(t_total)
    else:
        liquido = _normalize_volume(t_quant)

    if liquido == 0.0:
        r_tot = rdo.get('residuos_totais')
        r_sol = rdo.get('residuos_solidos')
        if r_tot is not None or r_sol is not None:
            liquido = _normalize_volume(_to_float_safe(r_tot) - _to_float_safe(r_sol))

    for rt in rdo.get('tanques', []):
        rt_total = rt.get('total_liquido')
        added = 0.0
        if rt_total is not None and float(rt_total or 0) != 0:
            added = _normalize_volume(rt_total)
        else:
            rt_tot = rt.get('residuos_totais')
            rt_sol = rt.get('residuos_solidos')
            if rt_tot is not None or rt_sol is not None:
                diff = _to_float_safe(rt_tot) - _to_float_safe(rt_sol)
                if diff > 0:
                    added = _normalize_volume(diff)
        liquido += added

    counter[ds] += liquido

cur = start
print('date,total_m3')
while cur <= end:
    ds = cur.strftime('%Y-%m-%d')
    print(f"{ds},{counter.get(ds,0)}")
    cur = cur + timedelta(days=1)

print('\nSamples:')
for k,v in counter.items():
    print(k, v)