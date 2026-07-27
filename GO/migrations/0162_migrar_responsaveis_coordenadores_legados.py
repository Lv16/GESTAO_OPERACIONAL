from django.db import migrations


def normalize(value):
    return ' '.join(str(value or '').split()).strip()


def migrate_legacy_names(apps, schema_editor):
    Person = apps.get_model('GO', 'ResponsavelCoordenador')
    Audit = apps.get_model('GO', 'ResponsavelCoordenadorAuditoria')
    Financeiro = apps.get_model('GO', 'Financeiro')
    OrdemServico = apps.get_model('GO', 'OrdemServico')
    by_name = {}
    report = {'responsaveis_importados': 0, 'coordenadores_importados': 0, 'nomes_unificados': 0, 'propostas_migradas': 0, 'os_migradas': 0, 'sem_correspondencia': []}

    def get_person(raw_name, role):
        name = normalize(raw_name)
        if not name:
            return None
        key = name.casefold()
        person = by_name.get(key)
        if person is None:
            person = Person.objects.filter(nome__iexact=name).first()
        if person is None:
            person = Person.objects.create(
                nome=name,
                responsavel_comercial=role == 'responsavel',
                coordenador=role == 'coordenador',
            )
            report['responsaveis_importados' if role == 'responsavel' else 'coordenadores_importados'] += 1
        else:
            changed = False
            if role == 'responsavel' and not person.responsavel_comercial:
                person.responsavel_comercial = True; changed = True
            if role == 'coordenador' and not person.coordenador:
                person.coordenador = True; changed = True
            if changed:
                person.save(update_fields=['responsavel_comercial', 'coordenador'])
                report['nomes_unificados'] += 1
        by_name[key] = person
        return person

    for os in OrdemServico.objects.all().iterator():
        person = get_person(getattr(os, 'coordenador', ''), 'coordenador')
        if person:
            os.coordenador_cadastro_id = person.pk
            os.save(update_fields=['coordenador_cadastro'])
            report['os_migradas'] += 1

    for proposal in Financeiro.objects.select_related('cordenador').all().iterator():
        changed = []
        person = get_person(getattr(proposal, 'responsavel', ''), 'responsavel')
        if person:
            proposal.responsavel_cadastro_id = person.pk; changed.append('responsavel_cadastro')
        legacy_coordinator = getattr(getattr(proposal, 'cordenador', None), 'coordenador', '')
        coordinator = get_person(legacy_coordinator, 'coordenador')
        if coordinator:
            proposal.coordenador_cadastro_id = coordinator.pk; changed.append('coordenador_cadastro')
        if changed:
            proposal.save(update_fields=changed)
            report['propostas_migradas'] += 1
        elif getattr(proposal, 'responsavel', '') or legacy_coordinator:
            report['sem_correspondencia'].append(str(getattr(proposal, 'pk', '')))

    Audit.objects.create(acao='migracao_legado', detalhes=report)


class Migration(migrations.Migration):
    dependencies = [('GO', '0161_responsavelcoordenador_and_more')]
    operations = [migrations.RunPython(migrate_legacy_names, migrations.RunPython.noop)]
