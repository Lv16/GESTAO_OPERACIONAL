import traceback

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Case, F, IntegerField, Value, When
from django.utils import timezone

from GO.models import RDO
from alertas_inteligentes.management.command_lock import (
    build_lock_message,
    command_execution_lock,
)
from alertas_inteligentes.models import AlertaInteligente
from alertas_inteligentes.services.rdo_validator import identificar_rdo, validar_rdo


class Command(BaseCommand):
    help = "Analisa RDOs pendentes e cria alertas inteligentes."

    def _detalhar_rdo_erro(self, rdo, erro):
        numero_rdo = getattr(rdo, "rdo", None) or getattr(rdo, "numero_rdo", None) or rdo.id
        os_obj = getattr(rdo, "ordem_servico", None)
        numero_os = None
        if os_obj is not None:
            numero_os = getattr(os_obj, "numero_os", None) or getattr(os_obj, "numero", None) or getattr(os_obj, "id", None)

        return (
            f"Erro ao analisar RDO ID {rdo.id} | RDO {numero_rdo} | OS {numero_os or 'N/D'}: {erro}\n"
            f"{traceback.format_exc()}"
        )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limite",
            type=int,
            default=None,
            help="Quantidade maxima de RDOs analisados por execucao. Se omitido, analisa todos os pendentes."
        )

    def handle(self, *args, **options):
        limite = options["limite"]

        with command_execution_lock("analisar_rdos_pendentes") as lock_info:
            if not lock_info["acquired"]:
                self.stdout.write(self.style.WARNING(build_lock_message(lock_info)))
                return

            rdos = RDO.objects.filter(
                status_analise_ia="pendente"
            ).annotate(
                prioridade_status_os=Case(
                    When(ordem_servico__status_operacao__iexact="Em Andamento", then=Value(0)),
                    When(ordem_servico__status_operacao__iexact="Programada", then=Value(1)),
                    When(ordem_servico__status_operacao__iexact="Paralizada", then=Value(1)),
                    When(ordem_servico__status_operacao__iexact="Finalizada", then=Value(2)),
                    When(ordem_servico__status_operacao__iexact="Cancelada", then=Value(3)),
                    default=Value(4),
                    output_field=IntegerField(),
                )
            ).order_by(
                "prioridade_status_os",
                F("data").desc(nulls_last=True),
                F("data_pendente_analise_ia").desc(nulls_last=True),
                "-id",
            )

            if limite is not None:
                rdos = rdos[:limite]

            total = rdos.count()

            if total == 0:
                self.stdout.write(
                    self.style.SUCCESS("Nenhum RDO pendente de analise.")
                )
                return

            self.stdout.write(f"Analisando {total} RDO(s)...")

            for rdo in rdos:
                try:
                    with transaction.atomic():
                        RDO.objects.filter(pk=rdo.pk).update(
                            status_analise_ia="em_analise",
                            erro_analise_ia=None,
                        )

                        AlertaInteligente.objects.filter(
                            rdo=rdo,
                            status__in=["pendente", "em_analise"]
                        ).update(
                            status="resolvido",
                            resolvido_em=timezone.now(),
                            justificativa="Resolvido automaticamente apos nova analise do RDO."
                        )
                        alertas = validar_rdo(rdo)

                        RDO.objects.filter(pk=rdo.pk).update(
                            status_analise_ia="analisado",
                            data_analise_ia=timezone.now(),
                        )

                        identificacao = identificar_rdo(rdo)
                        tipos_alertas = ", ".join([alerta.tipo for alerta in alertas]) or "nenhum"

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"{identificacao} - analisado. Alertas: {len(alertas)} | {tipos_alertas}"
                        )
                    )

                except Exception as erro:
                    RDO.objects.filter(pk=rdo.pk).update(
                        status_analise_ia="erro",
                        erro_analise_ia=str(erro),
                    )

                    self.stdout.write(
                        self.style.ERROR(
                            self._detalhar_rdo_erro(rdo, erro)
                        )
                    )
