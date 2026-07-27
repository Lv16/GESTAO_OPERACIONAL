from django.db import migrations


RESPONSAVEIS_COMERCIAIS = [
    'Daniel Cunha',
    'Rafael Pariz',
    'Katlyn Brito',
    'Sabryna Montoro',
    'Marcos França',
    'Felipe Segundo',
    'Fernanda Braz',
    'Anderson Bueno',
    'André Santiago',
    'Gabriel Delaia',
    'Jorge Brasil',
]


def adicionar_responsaveis_comerciais(apps, schema_editor):
    Pessoa = apps.get_model('GO', 'ResponsavelCoordenador')
    Auditoria = apps.get_model('GO', 'ResponsavelCoordenadorAuditoria')
    adicionados = 0
    atualizados = 0

    for nome in RESPONSAVEIS_COMERCIAIS:
        pessoa = Pessoa.objects.filter(nome__iexact=nome).first()
        if pessoa is None:
            Pessoa.objects.create(
                nome=nome,
                responsavel_comercial=True,
                ativo=True,
            )
            adicionados += 1
            continue

        campos = []
        if not pessoa.responsavel_comercial:
            pessoa.responsavel_comercial = True
            campos.append('responsavel_comercial')
        if not pessoa.ativo:
            pessoa.ativo = True
            campos.append('ativo')
        if campos:
            pessoa.save(update_fields=campos)
            atualizados += 1

    Auditoria.objects.create(
        acao='carga_responsaveis_iniciais',
        detalhes={
            'adicionados': adicionados,
            'atualizados': atualizados,
            'nomes': RESPONSAVEIS_COMERCIAIS,
        },
    )


class Migration(migrations.Migration):
    dependencies = [('GO', '0163_alter_financeiro_responsavel_and_more')]

    operations = [
        migrations.RunPython(adicionar_responsaveis_comerciais, migrations.RunPython.noop)]
