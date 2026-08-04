from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from GO.models import AnaliseCriticaOportunidade
from GO.views_comercial import _parse_critical_analysis_payload


class AnaliseCriticaOportunidadeTests(SimpleTestCase):
    def _analysis_with(self, value=None):
        values = {
            field_name: value
            for field_name in AnaliseCriticaOportunidade.RESPONSE_FIELDS
        }
        return AnaliseCriticaOportunidade(**values)

    def test_empty_analysis_is_pending(self):
        analysis = self._analysis_with()

        self.assertEqual(analysis.quantidade_respondida, 0)
        self.assertFalse(analysis.realizada)

    def test_all_answers_complete_analysis_even_with_no_or_na(self):
        analysis = self._analysis_with("NA")
        analysis.riscos_comerciais_relevantes = "NAO"

        self.assertEqual(analysis.quantidade_respondida, 14)
        self.assertTrue(analysis.realizada)

    def test_removing_one_answer_returns_analysis_to_pending(self):
        analysis = self._analysis_with("SIM")
        analysis.escopo_claramente_definido = None

        self.assertEqual(analysis.quantidade_respondida, 13)
        self.assertFalse(analysis.realizada)

    def test_invalid_payload_response_is_rejected(self):
        answers, errors, _comment = _parse_critical_analysis_payload(
            {"analise_critica_oportunidade": {"respostas": {"escopo_claramente_definido": "talvez"}}}
        )

        self.assertIsNotNone(answers)
        self.assertIn("analise_critica_oportunidade.escopo_claramente_definido", errors)

    def test_only_supported_responses_are_accepted(self):
        analysis = self._analysis_with("SIM")
        analysis.escopo_claramente_definido = "INVALIDA"

        with self.assertRaises(ValidationError):
            analysis.clean()
