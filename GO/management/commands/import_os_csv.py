import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from GO.models import Cliente, OrdemServico, Unidade


CSV_FIELDS = [
    "id",
    "numero_os",
    "cliente",
    "unidade",
    "data_inicio",
    "data_fim",
    "data_inicio_frente",
    "data_fim_frente",
    "servico",
    "servicos",
    "tanques",
    "turno",
    "metodo",
    "metodo_secundario",
    "tipo_operacao",
    "solicitante",
    "coordenador",
    "supervisor",
    "pob",
    "tanque",
    "volume_tanque",
    "especificacao",
    "observacao",
    "status_operacao",
    "status_geral",
    "status_comercial",
    "po",
    "material",
    "frente",
    "status_planejamento",
    "status_databook",
    "numero_certificado",
]

CHOICE_FIELDS = {
    "servico": "SERVICO_CHOICES",
    "turno": None,
    "metodo": "METODO_CHOICES",
    "metodo_secundario": "METODO_CHOICES",
    "tipo_operacao": "TIPO_OP_CHOICES",
    "status_operacao": "STATUS_CHOICES",
    "status_geral": "STATUS_CHOICES",
    "status_comercial": "STATUS_COMERCIAL_CHOICES",
    "material": "MATERIAL",
    "status_planejamento": "STATUS_PLANEJAMENTO",
    "status_databook": "STATUS_DATABOOK",
    "coordenador": "COORDENADORES",
}


class Command(BaseCommand):
    help = "Importa ordens de servico a partir de um CSV de contingencia."

    def add_arguments(self, parser):
        parser.add_argument("csv_path")
        parser.add_argument("--delimiter", default=None, help="Delimitador do CSV. Padrao: detectar automaticamente.")
        parser.add_argument("--dry-run", action="store_true", help="Valida e mostra o resumo sem salvar.")
        parser.add_argument("--update-existing", action="store_true", help="Atualiza quando a coluna id estiver preenchida.")
        parser.add_argument(
            "--update-by-numero-os",
            action="store_true",
            help="Atualiza a OS mais recente com o mesmo numero_os quando id estiver vazio.",
        )
        parser.add_argument(
            "--create-lookups",
            action="store_true",
            help="Cria Cliente/Unidade se nao existirem. Sem isso, nomes ausentes geram erro.",
        )

    def handle(self, *args, **options):
        csv_path = options["csv_path"]
        rows = self._read_rows(csv_path, options.get("delimiter"))
        if not rows:
            raise CommandError("CSV sem linhas de dados.")

        missing = [field for field in CSV_FIELDS if field not in rows[0]]
        if missing:
            raise CommandError(f"Cabecalho incompleto. Faltando: {', '.join(missing)}")

        created = updated = 0
        errors = []

        with transaction.atomic():
            for index, row in enumerate(rows, start=2):
                try:
                    obj, was_created = self._upsert_row(row, options)
                    created += int(was_created)
                    updated += int(not was_created)
                    action = "criaria" if was_created else "atualizaria"
                    if not options["dry_run"]:
                        action = "criou" if was_created else "atualizou"
                    self.stdout.write(f"Linha {index}: {action} OS {obj.numero_os}")
                except Exception as exc:
                    errors.append(f"Linha {index}: {exc}")

            if errors:
                raise CommandError("\n".join(errors))

            if options["dry_run"]:
                transaction.set_rollback(True)

        prefix = "Simulacao concluida" if options["dry_run"] else "Importacao concluida"
        self.stdout.write(self.style.SUCCESS(f"{prefix}: {created} criadas, {updated} atualizadas."))

    def _read_rows(self, path, delimiter):
        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as handle:
                sample = handle.read(4096)
                handle.seek(0)
                if delimiter is None:
                    try:
                        dialect = csv.Sniffer().sniff(sample, delimiters=";,")
                    except csv.Error:
                        dialect = csv.excel
                        dialect.delimiter = ";"
                else:
                    dialect = csv.excel
                    dialect.delimiter = delimiter
                return list(csv.DictReader(handle, dialect=dialect))
        except FileNotFoundError as exc:
            raise CommandError(f"Arquivo nao encontrado: {path}") from exc

    def _upsert_row(self, row, options):
        row = {key: self._clean(value) for key, value in row.items()}
        obj = self._resolve_target(row, options)
        was_created = obj is None
        if was_created:
            obj = OrdemServico()

        obj.numero_os = self._required_int(row, "numero_os")
        obj.Cliente = self._resolve_lookup(Cliente, row.get("cliente"), "cliente", options["create_lookups"])
        obj.Unidade = self._resolve_lookup(Unidade, row.get("unidade"), "unidade", options["create_lookups"])
        obj.data_inicio = self._required_date(row, "data_inicio")
        obj.data_fim = self._optional_date(row.get("data_fim"))
        obj.data_inicio_frente = self._optional_date(row.get("data_inicio_frente"))
        obj.data_fim_frente = self._optional_date(row.get("data_fim_frente"))
        obj.servico = self._choice_value("servico", row.get("servico"), required=True)
        obj.servicos = row.get("servicos") or None
        obj.tanques = row.get("tanques") or None
        obj.turno = self._choice_value("turno", row.get("turno"), required=False)
        obj.metodo = self._choice_value("metodo", row.get("metodo"), required=True)
        obj.metodo_secundario = self._choice_value("metodo_secundario", row.get("metodo_secundario"), required=False)
        obj.tipo_operacao = self._choice_value("tipo_operacao", row.get("tipo_operacao"), required=True)
        obj.solicitante = self._required(row, "solicitante")
        obj.coordenador = self._choice_value("coordenador", row.get("coordenador"), required=False)
        obj.supervisor = self._resolve_user(row.get("supervisor"))
        obj.pob = self._required_int(row, "pob")
        obj.tanque = row.get("tanque") or ""
        obj.volume_tanque = self._decimal(row.get("volume_tanque"), default=Decimal("0.00"))
        obj.especificacao = row.get("especificacao") or None
        obj.observacao = row.get("observacao") or ""
        obj.status_operacao = self._choice_value("status_operacao", row.get("status_operacao"), required=False) or "Programada"
        obj.status_geral = self._choice_value("status_geral", row.get("status_geral"), required=False) or "Programada"
        obj.status_comercial = self._choice_value("status_comercial", row.get("status_comercial"), required=False) or "Em aberto"
        obj.po = row.get("po") or None
        obj.material = self._choice_value("material", row.get("material"), required=False)
        obj.frente = row.get("frente") or None
        obj.status_planejamento = self._choice_value("status_planejamento", row.get("status_planejamento"), required=False) or "Pendente"
        obj.status_databook = self._choice_value("status_databook", row.get("status_databook"), required=False)
        obj.numero_certificado = row.get("numero_certificado") or None
        obj.full_clean(exclude=["dias_de_operacao", "dias_de_operacao_frente"])
        obj.save()
        return obj, was_created

    def _resolve_target(self, row, options):
        raw_id = row.get("id")
        if raw_id:
            try:
                obj = OrdemServico.objects.get(pk=int(raw_id))
            except OrdemServico.DoesNotExist as exc:
                raise ValueError(f"id {raw_id} nao existe") from exc
            if not options["update_existing"]:
                raise ValueError("coluna id preenchida exige --update-existing")
            return obj

        if options["update_by_numero_os"] and row.get("numero_os"):
            return OrdemServico.objects.filter(numero_os=int(row["numero_os"])).order_by("-id").first()
        return None

    def _resolve_lookup(self, model, value, field_label, create):
        value = self._required({field_label: value}, field_label)
        obj = model.objects.filter(nome__iexact=value).first()
        if obj:
            return obj
        if create:
            return model.objects.create(nome=value)
        raise ValueError(f"{field_label} nao encontrado: {value}")

    def _resolve_user(self, value):
        if not value:
            return None
        User = get_user_model()
        query = (
            Q(username__iexact=value)
            | Q(email__iexact=value)
            | Q(first_name__iexact=value)
            | Q(last_name__iexact=value)
        )
        parts = value.split()
        if len(parts) >= 2:
            query |= Q(first_name__iexact=parts[0], last_name__iexact=" ".join(parts[1:]))
        user = User.objects.filter(query).first()
        if not user:
            raise ValueError(f"supervisor nao encontrado: {value}")
        return user

    def _choice_value(self, field, value, required):
        value = self._clean(value)
        if not value:
            if required:
                raise ValueError(f"{field} e obrigatorio")
            return None
        if field == "turno":
            choices = [("Diurno", "Diurno"), ("Noturno", "Noturno")]
        else:
            choices_name = CHOICE_FIELDS[field]
            choices = getattr(OrdemServico, choices_name)
        normalized = self._normalize(value)
        for key, label in choices:
            if normalized in {self._normalize(key), self._normalize(label)}:
                return key
        allowed = ", ".join(str(key) for key, _label in choices if key)
        raise ValueError(f"{field} invalido: {value}. Valores aceitos: {allowed}")

    def _required(self, row, field):
        value = self._clean(row.get(field))
        if value == "":
            raise ValueError(f"{field} e obrigatorio")
        return value

    def _required_int(self, row, field):
        value = self._required(row, field)
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(f"{field} deve ser inteiro: {value}") from exc

    def _required_date(self, row, field):
        value = self._required(row, field)
        parsed = self._optional_date(value)
        if parsed is None:
            raise ValueError(f"{field} e obrigatorio")
        return parsed

    def _optional_date(self, value):
        value = self._clean(value)
        if not value:
            return None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                pass
        raise ValueError(f"data invalida: {value}")

    def _decimal(self, value, default=None):
        value = self._clean(value)
        if not value:
            return default
        try:
            return Decimal(value.replace(".", "").replace(",", ".") if "," in value else value)
        except InvalidOperation as exc:
            raise ValueError(f"decimal invalido: {value}") from exc

    def _clean(self, value):
        if value is None:
            return ""
        return str(value).strip()

    def _normalize(self, value):
        replacements = str.maketrans(
            "áàãâäéèêëíìîïóòõôöúùûüçÁÀÃÂÄÉÈÊËÍÌÎÏÓÒÕÔÖÚÙÛÜÇ",
            "aaaaaeeeeiiiiooooouuuucAAAAAEEEEIIIIOOOOOUUUUC",
        )
        return self._clean(value).translate(replacements).casefold()
