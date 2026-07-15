import csv
import io
import unicodedata
from datetime import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from GO.models import Cliente, OrdemServico, Unidade


FIELD_ALIASES = {
    "numero_os": {"numero_os", "os", "ordem_servico", "ordem_de_servico", "numero"},
    "especificacao": {"especificacao", "especificação", "descricao", "descricao"},
    "data_inicio_frente": {"data_inicio_frente", "inicio_frente"},
    "data_fim_frente": {"data_fim_frente", "fim_frente"},
    "dias_de_operacao_frente": {"dias_de_operacao_frente", "dias_frente"},
    "data_inicio": {"data_inicio", "inicio", "data_abertura"},
    "data_fim": {"data_fim", "fim", "data_encerramento"},
    "dias_de_operacao": {"dias_de_operacao", "dias_operacao"},
    "servico": {"servico", "serviço", "tipo_servico", "tipo_serviço"},
    "servicos": {"servicos", "serviços"},
    "tanque": {"tanque", "tanque_principal"},
    "tanques": {"tanques"},
    "tanques_inativos": {"tanques_inativos", "tanques_desativados", "tanques_inativos_csv"},
    "turno": {"turno"},
    "metodo": {"metodo", "método"},
    "metodo_secundario": {"metodo_secundario", "método_secundario", "metodo_2", "metodo2"},
    "observacao": {"observacao", "observação", "obs"},
    "pob": {"pob", "headcount"},
    "volume_tanque": {"volume_tanque", "volume", "capacidade_tanque"},
    "cliente": {"cliente"},
    "unidade": {"unidade", "base"},
    "tipo_operacao": {"tipo_operacao", "tipo_op", "operacao", "operação"},
    "solicitante": {"solicitante", "requisitante"},
    "coordenador": {"coordenador"},
    "supervisor": {"supervisor", "encarregado"},
    "status_operacao": {"status_operacao", "status_op"},
    "status_geral": {"status_geral"},
    "status_comercial": {"status_comercial"},
    "po": {"po", "pedido", "purchase_order"},
    "material": {"material"},
    "frente": {"frente"},
    "status_planejamento": {"status_planejamento"},
    "status_databook": {"status_databook", "databook"},
    "numero_certificado": {"numero_certificado", "certificado"},
}


def _normalize_token(value):
    text = str(value or "").strip()
    if not text:
        return ""
    text = "".join(
        ch for ch in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(ch)
    )
    chars = []
    prev_sep = False
    for ch in text.lower():
        if ch.isalnum():
            chars.append(ch)
            prev_sep = False
        else:
            if not prev_sep:
                chars.append("_")
            prev_sep = True
    return "".join(chars).strip("_")


def _build_choice_map(choices):
    out = {}
    for value, label in choices:
        out[_normalize_token(value)] = value
        out[_normalize_token(label)] = value
    return out


def _first_csv_item(value):
    if value is None:
        return ""
    parts = [item.strip() for item in str(value).split(",") if item.strip()]
    return parts[0] if parts else ""


class Command(BaseCommand):
    help = (
        "Importa um CSV de OS do Synchro para a tabela OrdemServico. "
        "Aceita cabeçalhos flexíveis e pode atualizar OS já existentes."
    )

    def add_arguments(self, parser):
        parser.add_argument("csv_path", help="Caminho do arquivo CSV.")
        parser.add_argument(
            "--delimiter",
            default="auto",
            help="Delimitador do CSV. Use 'auto' para detecção automática.",
        )
        parser.add_argument(
            "--encoding",
            default="utf-8-sig",
            help="Encoding do CSV. Padrão: utf-8-sig.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Valida e mostra o que seria importado sem gravar no banco.",
        )
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help="Atualiza todas as linhas já existentes com o mesmo numero_os.",
        )
        parser.add_argument(
            "--strict-related",
            action="store_true",
            help="Falha se Cliente, Unidade ou Supervisor não existirem.",
        )

    def handle(self, *args, **options):
        csv_path = options["csv_path"]
        delimiter = options["delimiter"]
        encoding = options["encoding"]
        dry_run = bool(options["dry_run"])
        update_existing = bool(options["update_existing"])
        strict_related = bool(options["strict_related"])

        try:
            with open(csv_path, "r", encoding=encoding, newline="") as handler:
                raw_content = handler.read()
        except FileNotFoundError as exc:
            raise CommandError(f"Arquivo não encontrado: {csv_path}") from exc

        if not raw_content.strip():
            raise CommandError("O arquivo CSV está vazio.")

        sniff_sample = raw_content[:4096]
        if delimiter == "auto":
            try:
                delimiter = csv.Sniffer().sniff(sniff_sample, delimiters=";,|\t").delimiter
            except csv.Error:
                delimiter = ","

        reader = csv.DictReader(io.StringIO(raw_content), delimiter=delimiter)
        if not reader.fieldnames:
            raise CommandError("Não foi possível identificar o cabeçalho do CSV.")

        header_map = self._build_header_map(reader.fieldnames)
        if "numero_os" not in header_map:
            raise CommandError("O CSV precisa ter uma coluna de número da OS.")

        summary = {
            "linhas_lidas": 0,
            "linhas_criadas": 0,
            "linhas_atualizadas": 0,
            "linhas_puladas": 0,
            "erros": 0,
            "registros_db_atualizados": 0,
        }

        for line_number, row in enumerate(reader, start=2):
            if not any(str(value or "").strip() for value in row.values()):
                continue

            summary["linhas_lidas"] += 1
            try:
                payload = self._build_payload(
                    row=row,
                    header_map=header_map,
                    strict_related=strict_related,
                )
                created, updated_count = self._persist_payload(
                    payload=payload,
                    dry_run=dry_run,
                    update_existing=update_existing,
                )
            except Exception as exc:
                summary["erros"] += 1
                self.stderr.write(f"Linha {line_number}: {exc}")
                continue

            if created:
                summary["linhas_criadas"] += 1
            elif updated_count:
                summary["linhas_atualizadas"] += 1
                summary["registros_db_atualizados"] += updated_count
            else:
                summary["linhas_puladas"] += 1

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run concluído. Nenhuma alteração foi gravada."))

        self.stdout.write(
            "Resumo: "
            f"lidas={summary['linhas_lidas']} "
            f"criadas={summary['linhas_criadas']} "
            f"atualizadas={summary['linhas_atualizadas']} "
            f"puladas={summary['linhas_puladas']} "
            f"erros={summary['erros']} "
            f"registros_db_atualizados={summary['registros_db_atualizados']}"
        )

        if summary["erros"]:
            raise CommandError("Importação finalizada com erros.")

    def _build_header_map(self, fieldnames):
        normalized_headers = {_normalize_token(name): name for name in fieldnames}
        header_map = {}
        for field_name, aliases in FIELD_ALIASES.items():
            for alias in aliases:
                original_header = normalized_headers.get(_normalize_token(alias))
                if original_header:
                    header_map[field_name] = original_header
                    break
        return header_map

    def _raw_value(self, row, header_map, field_name):
        header = header_map.get(field_name)
        if not header:
            return None
        return row.get(header)

    def _parse_int(self, raw_value, field_name, default=None):
        if raw_value in (None, ""):
            return default
        text = str(raw_value).strip()
        if not text:
            return default
        try:
            return int(float(text.replace(",", ".")))
        except ValueError as exc:
            raise CommandError(f"Campo '{field_name}' inválido: {raw_value}") from exc

    def _parse_decimal(self, raw_value, field_name, default=Decimal("0.00")):
        if raw_value in (None, ""):
            return default
        text = str(raw_value).strip()
        if not text:
            return default
        text = text.replace(".", "").replace(",", ".") if "," in text and "." in text else text.replace(",", ".")
        try:
            return Decimal(text)
        except Exception as exc:
            raise CommandError(f"Campo '{field_name}' inválido: {raw_value}") from exc

    def _parse_date(self, raw_value, field_name, required=False):
        if raw_value in (None, ""):
            if required:
                raise CommandError(f"Campo obrigatório ausente: {field_name}")
            return None

        text = str(raw_value).strip()
        if not text:
            if required:
                raise CommandError(f"Campo obrigatório ausente: {field_name}")
            return None

        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        raise CommandError(f"Campo '{field_name}' com data inválida: {raw_value}")

    def _parse_choice(self, raw_value, field_name, choice_map, default=None, required=False):
        if raw_value in (None, ""):
            if required and default is None:
                raise CommandError(f"Campo obrigatório ausente: {field_name}")
            return default
        token = _normalize_token(raw_value)
        resolved = choice_map.get(token)
        if resolved is None:
            raise CommandError(f"Valor inválido para '{field_name}': {raw_value}")
        return resolved

    def _resolve_cliente(self, raw_value, strict_related):
        value = str(raw_value or "").strip()
        if not value:
            raise CommandError("Campo obrigatório ausente: cliente")
        cliente = Cliente.objects.filter(nome__iexact=value).first()
        if cliente:
            return cliente
        if strict_related:
            raise CommandError(f"Cliente não encontrado: {value}")
        return Cliente.objects.create(nome=value)

    def _resolve_unidade(self, raw_value, strict_related):
        value = str(raw_value or "").strip()
        if not value:
            raise CommandError("Campo obrigatório ausente: unidade")
        unidade = Unidade.objects.filter(nome__iexact=value).first()
        if unidade:
            return unidade
        if strict_related:
            raise CommandError(f"Unidade não encontrada: {value}")
        return Unidade.objects.create(nome=value)

    def _resolve_supervisor(self, raw_value, strict_related):
        value = str(raw_value or "").strip()
        if not value:
            return None

        UserModel = get_user_model()
        qs = UserModel.objects.all()
        if value.isdigit():
            supervisor = qs.filter(pk=int(value)).first()
            if supervisor:
                return supervisor

        supervisor = qs.filter(username__iexact=value).first()
        if supervisor:
            return supervisor

        supervisor = qs.filter(email__iexact=value).first()
        if supervisor:
            return supervisor

        for user in qs:
            full_name = ""
            try:
                full_name = user.get_full_name() or ""
            except Exception:
                full_name = ""
            if full_name.strip().casefold() == value.casefold():
                return user

        if strict_related:
            raise CommandError(f"Supervisor não encontrado: {value}")
        return None

    def _build_payload(self, row, header_map, strict_related):
        service_choices = _build_choice_map(OrdemServico.SERVICO_CHOICES)
        metodo_choices = _build_choice_map(OrdemServico.METODO_CHOICES)
        tipo_operacao_choices = _build_choice_map(OrdemServico.TIPO_OP_CHOICES)
        status_choices = _build_choice_map(OrdemServico.STATUS_CHOICES)
        status_comercial_choices = _build_choice_map(OrdemServico.STATUS_COMERCIAL_CHOICES)
        material_choices = _build_choice_map(OrdemServico.MATERIAL)
        status_planejamento_choices = _build_choice_map(OrdemServico.STATUS_PLANEJAMENTO)
        status_databook_choices = _build_choice_map(OrdemServico.STATUS_DATABOOK)
        coordenador_choices = _build_choice_map(OrdemServico.COORDENADORES)
        turno_choices = _build_choice_map([("Diurno", "Diurno"), ("Noturno", "Noturno")])

        numero_os = self._parse_int(self._raw_value(row, header_map, "numero_os"), "numero_os")
        if numero_os is None:
            raise CommandError("Campo obrigatório ausente: numero_os")

        servicos_csv = self._raw_value(row, header_map, "servicos")
        tanques_csv = self._raw_value(row, header_map, "tanques")

        servico_raw = self._raw_value(row, header_map, "servico") or _first_csv_item(servicos_csv)
        tanque_raw = self._raw_value(row, header_map, "tanque") or _first_csv_item(tanques_csv)

        payload = {
            "numero_os": numero_os,
            "especificacao": self._clean_text(self._raw_value(row, header_map, "especificacao")),
            "data_inicio_frente": self._parse_date(self._raw_value(row, header_map, "data_inicio_frente"), "data_inicio_frente"),
            "data_fim_frente": self._parse_date(self._raw_value(row, header_map, "data_fim_frente"), "data_fim_frente"),
            "data_inicio": self._parse_date(self._raw_value(row, header_map, "data_inicio"), "data_inicio", required=True),
            "data_fim": self._parse_date(self._raw_value(row, header_map, "data_fim"), "data_fim"),
            "dias_de_operacao_frente": self._parse_int(self._raw_value(row, header_map, "dias_de_operacao_frente"), "dias_de_operacao_frente", default=0),
            "dias_de_operacao": self._parse_int(self._raw_value(row, header_map, "dias_de_operacao"), "dias_de_operacao", default=0),
            "servico": self._parse_choice(servico_raw, "servico", service_choices, required=True),
            "servicos": self._clean_text(servicos_csv) or self._clean_text(servico_raw),
            "tanque": self._clean_text(tanque_raw) or "",
            "tanques": self._clean_text(tanques_csv),
            "tanques_inativos": self._clean_text(self._raw_value(row, header_map, "tanques_inativos")),
            "turno": self._parse_choice(self._raw_value(row, header_map, "turno"), "turno", turno_choices, default=None),
            "metodo": self._parse_choice(self._raw_value(row, header_map, "metodo"), "metodo", metodo_choices, required=True),
            "metodo_secundario": self._parse_choice(self._raw_value(row, header_map, "metodo_secundario"), "metodo_secundario", metodo_choices, default=None),
            "observacao": self._clean_text(self._raw_value(row, header_map, "observacao")) or "",
            "pob": self._parse_int(self._raw_value(row, header_map, "pob"), "pob", default=0),
            "volume_tanque": self._parse_decimal(self._raw_value(row, header_map, "volume_tanque"), "volume_tanque"),
            "Cliente": self._resolve_cliente(self._raw_value(row, header_map, "cliente"), strict_related),
            "Unidade": self._resolve_unidade(self._raw_value(row, header_map, "unidade"), strict_related),
            "tipo_operacao": self._parse_choice(self._raw_value(row, header_map, "tipo_operacao"), "tipo_operacao", tipo_operacao_choices, required=True),
            "solicitante": self._clean_text(self._raw_value(row, header_map, "solicitante")) or "",
            "coordenador": self._parse_choice(self._raw_value(row, header_map, "coordenador"), "coordenador", coordenador_choices, default=None),
            "supervisor": self._resolve_supervisor(self._raw_value(row, header_map, "supervisor"), strict_related),
            "status_operacao": self._parse_choice(self._raw_value(row, header_map, "status_operacao"), "status_operacao", status_choices, default="Programada"),
            "status_geral": self._parse_choice(self._raw_value(row, header_map, "status_geral"), "status_geral", status_choices, default=None),
            "status_comercial": self._parse_choice(self._raw_value(row, header_map, "status_comercial"), "status_comercial", status_comercial_choices, default="Em aberto"),
            "po": self._clean_text(self._raw_value(row, header_map, "po")),
            "material": self._parse_choice(self._raw_value(row, header_map, "material"), "material", material_choices, default=None),
            "frente": self._clean_text(self._raw_value(row, header_map, "frente")),
            "status_planejamento": self._parse_choice(self._raw_value(row, header_map, "status_planejamento"), "status_planejamento", status_planejamento_choices, default="Pendente"),
            "status_databook": self._parse_choice(self._raw_value(row, header_map, "status_databook"), "status_databook", status_databook_choices, default=None),
            "numero_certificado": self._clean_text(self._raw_value(row, header_map, "numero_certificado")),
        }

        if not payload["solicitante"]:
            raise CommandError("Campo obrigatório ausente: solicitante")

        if not payload["status_geral"]:
            payload["status_geral"] = payload["status_operacao"]

        return payload

    def _clean_text(self, raw_value):
        if raw_value is None:
            return None
        text = str(raw_value).strip()
        return text or None

    def _persist_payload(self, payload, dry_run, update_existing):
        matches = OrdemServico.objects.filter(numero_os=payload["numero_os"]).order_by("id")
        if matches.exists():
            if not update_existing:
                return False, 0
            if dry_run:
                return False, matches.count()
            with transaction.atomic():
                updated_count = 0
                for os_obj in matches:
                    for field_name, field_value in payload.items():
                        setattr(os_obj, field_name, field_value)
                    os_obj.save()
                    updated_count += 1
            return False, updated_count

        if dry_run:
            return True, 0

        with transaction.atomic():
            OrdemServico.objects.create(**payload)
        return True, 0
