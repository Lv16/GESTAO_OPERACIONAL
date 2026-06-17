from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from alertas_inteligentes.management.command_lock import (
    build_lock_message,
    command_execution_lock,
)


class Command(BaseCommand):
    help = "Executa a rotina automatica do Synchro AI."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limite-rdos",
            type=int,
            default=100,
            help="Quantidade maxima de RDOs para analisar.",
        )
        parser.add_argument(
            "--limite-operacoes",
            type=int,
            default=100,
            help="Quantidade maxima de OS/operacoes para analisar.",
        )

    def handle(self, *args, **options):
        limite_rdos = options["limite_rdos"]
        limite_operacoes = options["limite_operacoes"]

        with command_execution_lock("rodar_ia_synchro") as lock_info:
            if not lock_info["acquired"]:
                self.stdout.write(self.style.WARNING(build_lock_message(lock_info)))
                return

            inicio = timezone.now()

            self.stdout.write("")
            self.stdout.write("Iniciando rotina automatica do Synchro AI")
            self.stdout.write(f"Inicio: {inicio.strftime('%d/%m/%Y %H:%M:%S')}")
            self.stdout.write("=" * 60)

            try:
                self.stdout.write("")
                self.stdout.write("1/2 - Analisando RDOs pendentes...")
                call_command("analisar_rdos_pendentes", limite=limite_rdos)

                self.stdout.write("")
                self.stdout.write("2/2 - Analisando operacoes...")
                call_command("analisar_operacoes", limite=limite_operacoes)

                fim = timezone.now()
                duracao = fim - inicio

                self.stdout.write("")
                self.stdout.write("=" * 60)
                self.stdout.write(self.style.SUCCESS("Rotina automatica concluida com sucesso."))
                self.stdout.write(f"Fim: {fim.strftime('%d/%m/%Y %H:%M:%S')}")
                self.stdout.write(f"Duracao: {duracao}")
                self.stdout.write("=" * 60)

            except Exception as erro:
                fim = timezone.now()

                self.stdout.write("")
                self.stdout.write("=" * 60)
                self.stdout.write(self.style.ERROR("Ocorreu um erro durante a execucao da rotina automatica."))
                self.stdout.write(f"Fim: {fim.strftime('%d/%m/%Y %H:%M:%S')}")
                self.stdout.write(f"Erro: {erro}")
                self.stdout.write("=" * 60)

                raise
