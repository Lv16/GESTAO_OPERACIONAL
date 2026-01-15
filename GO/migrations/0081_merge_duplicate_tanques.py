from django.db import migrations, transaction


def merge_duplicate_tanques(apps, schema_editor):
    import json
    from django.db.models import Count
    RdoTanque = apps.get_model('GO', 'RdoTanque')

    # Campos numéricos que vamos agregar somando valores (conservador)
    numeric_fields = [
        'bombeio', 'total_liquido', 'total_liquido_cumulativo',
        'residuos_solidos', 'residuos_solidos_cumulativo', 'residuos_totais',
        'tambores_dia', 'tambores_cumulativo',
        'ensacamento_dia', 'ensacamento_cumulativo',
        'icamento_dia', 'icamento_cumulativo',
        'cambagem_dia', 'cambagem_cumulativo'
    ]

    with transaction.atomic():
        # Tentar identificar grupos por ORM (rdo__ordem_servico_id + nome_tanque)
        dup_groups = (
            RdoTanque.objects
            .values('rdo__ordem_servico_id', 'nome_tanque')
            .annotate(count_id=Count('id'))
            .filter(count_id__gt=1)
        )

        if not dup_groups:
            # fallback: agrupar no Python caso o banco/ORM não suporte a annotate acima
            all_tanks = list(RdoTanque.objects.select_related('rdo').all())
            groups = {}
            for t in all_tanks:
                os_id = getattr(t.rdo, 'ordem_servico_id', None)
                nome = (t.nome_tanque or '').strip().lower()
                key = (os_id, nome)
                groups.setdefault(key, []).append(t)
            for key, items in groups.items():
                if len(items) <= 1:
                    continue
                canonical = sorted(items, key=lambda x: x.id)[0]
                duplicates = [x for x in items if x.id != canonical.id]
                _merge_and_delete(canonical, duplicates, numeric_fields, json)
            return

        # Processar cada grupo identificado
        for g in dup_groups:
            os_id = g.get('rdo__ordem_servico_id')
            nome_raw = g.get('nome_tanque') or ''
            nome = nome_raw.strip()
            tanks_qs = (
                RdoTanque.objects
                .filter(rdo__ordem_servico_id=os_id, nome_tanque__iexact=nome)
                .order_by('id')
            )
            tanks = list(tanks_qs)
            if len(tanks) <= 1:
                continue
            canonical = tanks[0]
            duplicates = tanks[1:]
            _merge_and_delete(canonical, duplicates, numeric_fields, json)


def _merge_and_delete(canonical, duplicates, numeric_fields, json_mod):
    """Mescla valores de `duplicates` em `canonical` e deleta duplicados."""
    for dup in duplicates:
        for f in numeric_fields:
            try:
                base = getattr(canonical, f, None) or 0
                add = getattr(dup, f, None) or 0
                try:
                    setattr(canonical, f, base + add)
                except Exception:
                    try:
                        setattr(canonical, f, (float(base) if base is not None else 0.0) + (float(add) if add is not None else 0.0))
                    except Exception:
                        pass
            except Exception:
                pass

        try:
            a_raw = getattr(canonical, 'compartimentos_avanco_json', None) or '{}'
            b_raw = getattr(dup, 'compartimentos_avanco_json', None) or '{}'
            a = json_mod.loads(a_raw) if isinstance(a_raw, str) and a_raw.strip() else (a_raw if isinstance(a_raw, dict) else {})
            b = json_mod.loads(b_raw) if isinstance(b_raw, str) and b_raw.strip() else (b_raw if isinstance(b_raw, dict) else {})
            if not isinstance(a, dict):
                a = {}
            if not isinstance(b, dict):
                b = {}
            for k, v in b.items():
                if k not in a:
                    a[k] = v
                    continue
                try:
                    ak = a.get(k) or {}
                    bk = v or {}
                    if not isinstance(ak, dict) or not isinstance(bk, dict):
                        a[k] = bk
                        continue
                    for sub in ('mecanizada', 'fina'):
                        av = ak.get(sub, 0) or 0
                        bv = bk.get(sub, 0) or 0
                        try:
                            a[k][sub] = float(av) + float(bv)
                        except Exception:
                            a[k][sub] = av or bv
                except Exception:
                    a[k] = v
            canonical.compartimentos_avanco_json = json_mod.dumps(a)
        except Exception:
            pass

        try:
            text_fields = ['tipo_tanque', 'servico_exec', 'metodo_exec', 'espaco_confinado', 'avanco_limpeza', 'avanco_limpeza_fina']
            for tf in text_fields:
                try:
                    if not getattr(canonical, tf, None) and getattr(dup, tf, None):
                        setattr(canonical, tf, getattr(dup, tf))
                except Exception:
                    pass
        except Exception:
            pass

        try:
            canonical.save()
        except Exception:
            try:
                canonical.save()
            except Exception:
                pass

        try:
            dup.delete()
        except Exception:
            pass


class Migration(migrations.Migration):

    dependencies = [
        ('GO', '0080_rdotanque_limpeza_fina_cumulativa_tanque_and_more'),
    ]

    operations = [
        migrations.RunPython(merge_duplicate_tanques, reverse_code=migrations.RunPython.noop),
    ]
