from django.test import SimpleTestCase

from GO.models import _canonical_tank_alias_for_os


class TankAliasNormalizationTest(SimpleTestCase):
    def test_os_6044_maps_aliases_to_7p_cot(self):
        self.assertEqual(_canonical_tank_alias_for_os(6044, "7P"), "7P COT")
        self.assertEqual(_canonical_tank_alias_for_os(6044, "7P Tank"), "7P COT")
        self.assertEqual(_canonical_tank_alias_for_os(6044, " 7P   COT "), "7P COT")

    def test_os_5292_maps_aliases_to_cot_5s(self):
        self.assertEqual(_canonical_tank_alias_for_os(5292, "5S"), "COT-5s")
        self.assertEqual(_canonical_tank_alias_for_os(5292, "cot 5s"), "COT-5s")
        self.assertEqual(_canonical_tank_alias_for_os(5292, "COT-5s"), "COT-5s")

    def test_other_os_keeps_values_unmapped(self):
        self.assertIsNone(_canonical_tank_alias_for_os(6045, "7P"))
        self.assertIsNone(_canonical_tank_alias_for_os(None, "7P Tank"))
        self.assertIsNone(_canonical_tank_alias_for_os(5293, "5S"))
