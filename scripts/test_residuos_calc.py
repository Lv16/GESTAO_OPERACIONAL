from collections import Counter
from datetime import datetime, timedelta

# Replicar a heurística de normalização usada em dashboard_views.rdo_residuos_liquido_por_dia

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

# Exemplo de RDOs de teste
sample_rdos = [
    # total_liquido em litros -> 800 L => 0.8 m3
    {'data': '2025-12-12', 'total_liquido': 800, 'quantidade_bombeada': None, 'tanques': []},
    # quantidade_bombeada em m3
    {'data': '2026-01-06', 'total_liquido': None, 'quantidade_bombeada': 1.2, 'tanques': []},
    # tanque com total_liquido em litros -> 500 L => 0.5 m3
    {'data': '2026-01-06', 'total_liquido': None, 'quantidade_bombeada': None, 'tanques': [ {'total_liquido': 500} ]},
    # caso com total_liquido pequeno já em m3 -> 2.5 m3
    {'data': '2026-01-05', 'total_liquido': 2.5, 'quantidade_bombeada': None, 'tanques': []},
    # caso sem total nem quantidade, mas residuos_totais - residuos_solidos = 1500-200 => 1300 L -> 1.3 m3
    {'data': '2025-12-12', 'total_liquido': None, 'quantidade_bombeada': None, 'residuos_totais':1500, 'residuos_solidos':200, 'tanques': []},
]

start = datetime.strptime('2025-12-01', '%Y-%m-%d').date()
end = datetime.strptime('2026-01-10', '%Y-%m-%d').date()

counter = Counter()

for rdo in sample_rdos:
    d = rdo.get('data')
    if not d:
        continue
    # parse date like in code
    ds = d
    # compute liquido similar to updated function
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

    # tanques
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

# Print series
cur = start
print('date,total_m3')
while cur <= end:
    ds = cur.strftime('%Y-%m-%d')
    print(f"{ds},{counter.get(ds,0)}")
    cur = cur + timedelta(days=1)

# Print samples
print('\nSamples:')
for k,v in counter.items():
    print(k, v)
