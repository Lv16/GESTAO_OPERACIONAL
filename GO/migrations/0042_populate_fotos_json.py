from django.db import migrations
import json


def populate_fotos_json(apps, schema_editor):
    RDO = apps.get_model('GO', 'RDO')
    for r in RDO.objects.all():
        try:
            urls = []
            # legacy fotos_img
            try:
                fi = getattr(r, 'fotos_img', None)
                if fi:
                    try:
                        urls.append(fi.url)
                    except Exception:
                        urls.append(str(fi))
            except Exception:
                pass
            # slots
            for attr in ('fotos_1','fotos_2','fotos_3','fotos_4','fotos_5'):
                try:
                    ff = getattr(r, attr, None)
                    if ff:
                        try:
                            urls.append(ff.url)
                        except Exception:
                            urls.append(str(ff))
                except Exception:
                    continue
            if urls:
                r.fotos_json = json.dumps(urls)
                r.save()
        except Exception:
            # fail-safe: não abortar migração se algum registro problemático
            continue


class Migration(migrations.Migration):

    dependencies = [
        # apontar para a migração 0041 existente no repositório
        ('GO', '0041_rdo_fotos_1_rdo_fotos_2_rdo_fotos_3_rdo_fotos_4_and_more'),
    ]

    operations = [
        migrations.RunPython(populate_fotos_json, reverse_code=migrations.RunPython.noop),
    ]
