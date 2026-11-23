"""Controls dels diagnòstics de geometria i duplicats de la revisió d'identitat."""

import unittest

from benchmarks.calibration.tools.analyze_identity import compatible, geometry, minimum_changes, endpoint_continuity


class IdentityDiagnosticTests(unittest.TestCase):
    """Distingeix fragments, contenidors gegants i conjunts d'IDs simultanis."""

    def test_useful_fragment_can_fail_iou50(self):
        """Un fragment pur pot superar el diagnòstic permissiu sense arribar a IoU 0,5."""
        self.assertTrue(compatible([0,0,4,10],[0,0,10,10],'coverage25_purity50'))
        self.assertFalse(compatible([0,0,4,10],[0,0,10,10],'iou50'))

    def test_full_coverage_does_not_accept_giant_container(self):
        """La cobertura total no oculta que una caixa inclou gairebé tota l'escena."""
        self.assertEqual(geometry([0,0,100,100],[10,10,20,20])['coverage'],1)
        self.assertFalse(compatible([0,0,100,100],[10,10,20,20],'coverage25_purity50'))

    def test_duplicate_ids_do_not_force_arbitrary_switch(self):
        """El límit inferior considera camins entre conjunts, sense triar el primer ID."""
        self.assertEqual(minimum_changes([{'a'},{'a','b'},{'b'}]),1)
        self.assertEqual(minimum_changes([{'a','b'},{'b','c'},{'b'}]),0)

    def test_missing_matches_do_not_create_new_identity(self):
        """Un buit no prova cap canvi: el resultat només és un límit entre matches dispersos."""
        self.assertEqual(minimum_changes([{'a'},set(),{'a'}]),0)
        self.assertEqual(minimum_changes([{'a'},set(),{'b'}]),1)

    def test_endpoints_do_not_bridge_missing_annotation(self):
        """Un buit anotat genera dos parells incomplets, no una continuïtat inventada."""
        stats,pairs=endpoint_continuity([(0,{'a'}),(10,set()),(20,{'a'})])
        self.assertEqual(stats['same_id'],0)
        self.assertEqual(stats['missing_right'],1)
        self.assertEqual(stats['missing_left'],1)
        self.assertFalse(stats['single_id_covers_all_visible_annotations'])

    def test_pairwise_success_does_not_imply_one_global_id(self):
        """Dos parells compatibles poden usar IDs diferents al frame duplicat."""
        stats,pairs=endpoint_continuity([(0,{'a'}),(10,{'a','b'}),(20,{'b'})])
        self.assertEqual(stats['same_id'],2)
        self.assertFalse(stats['single_id_covers_all_matched_annotations'])

    def test_changed_id_is_separate_from_missing_observation(self):
        """Un canvi exigeix observació als dos extrems i cap ID compartit."""
        stats,pairs=endpoint_continuity([(0,{'a'}),(10,{'b'}),(20,{'b'})])
        self.assertEqual(stats['changed_id'],1)
        self.assertEqual(stats['same_id'],1)
        self.assertEqual(stats['same_id_fraction_all_visible_pairs'],.5)
