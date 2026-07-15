from django.core.management.base import BaseCommand
from django.db import transaction

from GO.models import OrdemServico
from alertas_inteligentes.management.command_lock import (
    build_lock_message,
    command_execution_lock,
)
from alertas_inteligentes.services.operacional_validator import (
    identificar_os,
    resolver_alertas_operacionais_obsoletos,
    validar_os_operacional,
    validar_supervisores_em_os_simultaneas,
)


class Command(BaseCommand):
    help = "Analisa OS/Home Operacional e cria alertas operacionais inteligentes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limite",
            type=int,
            default=100,
            help="Quantidade maxima de OS analisadas por execucao."
        )

    def handle(self, *args, **options):
        limite = options["limite"]

        with command_execution_lock("analisar_operacoes") as lock_info:
            if not lock_info["acquired"]:
                self.stdout.write(self.style.WARNING(build_lock_message(lock_info)))
                return

            ordens = OrdemServico.objects.all().order_by("-id")[:limite]

            self.stdout.write(f"Analisando {ordens.count()} OS...")

            total_alertas = 0

            for os_obj in ordens:
                try:
                    with transaction.atomic():
                        alertas = validar_os_operacional(os_obj)
                        resolver_alertas_operacionais_obsoletos(
                            os_obj,
                            alertas,
                            justificativa="Resolvido automaticamente apos nova analise operacional.",
                        )
                        total_alertas += len(alertas)

                    if alertas:
                        self.stdout.write(
                            self.style.WARNING(
                                f"{identificar_os(os_obj)} analisada. Alertas gerados: {len(alertas)}"
                            )
                        )

                        for alerta in alertas:
                            self.stdout.write(
                                f"  - {alerta.get_tipo_display()} | Prioridade: {alerta.get_prioridade_display()}"
                            )
                            self.stdout.write(
                                f"    {alerta.mensagem}"
                            )
                    else:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"{identificar_os(os_obj)} analisada. Nenhum alerta gerado."
                            )
                        )

                except Exception as erro:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Erro ao analisar {identificar_os(os_obj)}: {erro}"
                        )
                    )

            try:
                alertas_supervisor = validar_supervisores_em_os_simultaneas()
                total_alertas += len(alertas_supervisor)

                if alertas_supervisor:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Validacao de supervisores concluida. Alertas gerados: {len(alertas_supervisor)}"
                        )
                    )

                    for alerta in alertas_supervisor:
                        self.stdout.write(
                            f"  - {alerta.identificacao_operacional}"
                        )
                        self.stdout.write(
                            f"    {alerta.get_tipo_display()} | Prioridade: {alerta.get_prioridade_display()}"
                        )
                        self.stdout.write(
                            f"    {alerta.mensagem}"
                        )
                else:
                    self.stdout.write(
                        self.style.SUCCESS(
                            "Validacao de supervisores concluida. Nenhum alerta gerado."
                        )
                    )

            except Exception as erro:
                self.stdout.write(
                    self.style.ERROR(
                        f"Erro na validacao de supervisores: {erro}"
                    )
                )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Analise operacional concluida. Total de alertas criados/atualizados: {total_alertas}"
                )
            )
