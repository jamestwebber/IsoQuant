from collections import namedtuple, Counter

import pytest

from src.long_read_assigner import LongReadAssigner, MatchEventSubtype, AmbiguityResolvingMethod, IsoformDiff

class Params:
    def __init__(self, delta):
        self.delta = delta
        self.minor_exon_extension = 10
        self.major_exon_extension = 100
        self.min_abs_exon_overlap = 10
        self.min_rel_exon_overlap = 0.2
        self.max_suspicious_intron_abs_len = 0
        self.max_suspicious_intron_rel_len = 0
        self.max_fake_terminal_exon_len = 0
        self.apa_delta = 50
        self.minimal_exon_overlap = 5
        self.minimal_intron_absence_overlap = 5
        self.max_intron_shift = 10
        self.max_missed_exon_len = 10
        self.resolve_ambiguous = AmbiguityResolvingMethod.monoexon_only
        self.correct_minor_errors = True

IntronProfiles = namedtuple("IntronProfiles", ("features", ))
GeneInfo = namedtuple("GeneInfo", ("intron_profiles", "start", "end"))


class TestMatchProfileAndFindMatchingIsoforms:
    gene_info = GeneInfo(IntronProfiles([(50, 60), (80, 100), (80, 110), 200, 210]), 0, 300)
    assigner = LongReadAssigner(gene_info, Params(0))  # we need no params here

    @pytest.mark.parametrize("read_gene_profile, isoform_profiles, hint, expected",
                             [([], dict(id1=[1], id2=[-1]), None, [IsoformDiff("id2", 0), IsoformDiff("id1", 0)])])
    def test_empty(self, read_gene_profile, isoform_profiles, hint, expected):
        with pytest.raises(AssertionError):
            self.check(read_gene_profile, isoform_profiles, hint, expected)

    @pytest.mark.parametrize("read_gene_profile, isoform_profiles, hint, expected",
                             [([-1, 1, -1, 0], dict(id1=[-1, 1, 1, -1], id2=[-1, 1 ,-2], id3=[-1, 1, 1, 1]),
                               {"id2", "id3"}, [IsoformDiff("id2", -1), IsoformDiff("id3", 1)])])
    def test_different_length(self, read_gene_profile, isoform_profiles, hint, expected):
        with pytest.raises(AssertionError):
            self.check(read_gene_profile, isoform_profiles, hint, expected)

    def check(self, read_gene_profile, isoform_profiles, hint, expected):
        assert expected == self.assigner.match_profile(read_gene_profile, isoform_profiles, hint)
        expected = sorted([x[0] for x in expected if x[1] == 0])
        assert expected == self.assigner.find_matching_isoforms(read_gene_profile, isoform_profiles, hint)

    @pytest.mark.parametrize("read_gene_profile, isoform_profiles, hint, expected",
                             [([-1, 1, -1, 0], dict(id1=[-1, 1, -1, -1], id2=[-1, 1, -1, -2]),
                               None, [IsoformDiff("id1", 0), IsoformDiff("id2", 0)]),
                              ([0, 1, -1, 1], dict(id1=[-1, 1, -1, 1], id2=[-2, 1, -1, 1]),
                               None, [IsoformDiff("id1", 0), IsoformDiff("id2", 0)])])
    def test_all_equals(self, read_gene_profile, isoform_profiles, hint, expected):
        self.check(read_gene_profile, isoform_profiles, hint, expected)

    @pytest.mark.parametrize("read_gene_profile, isoform_profiles, hint, expected",
                             [([-1, 1, -1, 0], dict(id1=[-1, 1, -1, -1], id2=[1, 1, 1, -1]),
                               None, [IsoformDiff("id1", 0), IsoformDiff("id2", 2)]),
                              ([0, 1, 1, -1, 0], dict(id1=[-1, 1, 1,  1, -2], id2=[-2, 1, 1, -1, -2],
                                                       id3=[ 1, -1, 1, -2, -2]),
                               None, [IsoformDiff("id2", 0), IsoformDiff("id1", 1), IsoformDiff("id3", 2)])])
    def test_some_equals(self, read_gene_profile, isoform_profiles, hint, expected):
        self.check(read_gene_profile, isoform_profiles, hint, expected)

    @pytest.mark.parametrize("read_gene_profile, isoform_profiles, hint, expected",
                             [([-1, 1, -1, 0], dict(id1=[-2, 1, -1, -1], id2=[1, 1, 1, 1]),
                               None, [IsoformDiff("id1", 1), IsoformDiff("id2", 2)]),
                              ([-1, 1, 1, -1, 0], dict(id1=[-1, 1, 1, 1, 1], id2=[1, 1, -1, -1, -1],
                                                       id3=[-2, -1, -1, 1, -2]),
                               None, [IsoformDiff("id1", 1), IsoformDiff("id2", 2), IsoformDiff("id3", 4)])])
    def test_no_equals(self, read_gene_profile, isoform_profiles, hint, expected):
        self.check(read_gene_profile, isoform_profiles, hint, expected)

    @pytest.mark.parametrize("read_gene_profile, isoform_profiles, hint, expected",
                             [([-1, 1, 1, 0], dict(id1=[-1, 1, 1, -1], id2=[1, 1, 1, -1], id3=[-1, -1, -1, 1]),
                               {"id2", "id3"}, [IsoformDiff("id2", 1), IsoformDiff("id3", 2)]),  # skip matched return another one
                              ([-1, 1, -1, 0], dict(id1=[-1, 1, 1, -2], id2=[-1, -1, 1, -2], id3=[-1, 1, -1, -2]),
                               {"id3"}, [IsoformDiff("id3", 0)])])  # matched
    def test_hint(self, read_gene_profile, isoform_profiles, hint, expected):
        self.check(read_gene_profile, isoform_profiles, hint, expected)


class TestCompareJunctions:
    gene_info = GeneInfo(IntronProfiles([(50, 60), (80, 100), (80, 110), (200, 210)]), 0, 300)

    @pytest.mark.parametrize("read_junctions, read_region, isoform_junctions, isoform_region, delta",
                             [([], (20, 200), [], (20, 290), 1)])
    def test_monoexon_match(self, read_junctions, read_region, isoform_junctions, isoform_region, delta):
        assigner = LongReadAssigner(self.gene_info, Params(delta))
        match_events = assigner.intron_comparator.compare_junctions(read_junctions, read_region,
                                                                    isoform_junctions, isoform_region)
        assert len(match_events) == 1
        assert match_events[0].event_type == MatchEventSubtype.mono_exon_match

    @pytest.mark.parametrize("read_junctions, read_region, isoform_junctions, isoform_region, delta",
                             [([], (20, 200), [(150, 170)], (20, 290), 1)])
    def test_unspliced_intron_retention(self, read_junctions, read_region, isoform_junctions, isoform_region, delta):
        assigner = LongReadAssigner(self.gene_info, Params(delta))
        match_events = assigner.intron_comparator.compare_junctions(read_junctions, read_region,
                                                                    isoform_junctions, isoform_region)
        assert len(match_events) == 1
        assert match_events[0].event_type == MatchEventSubtype.unspliced_intron_retention

    @pytest.mark.parametrize("read_junctions, read_region, isoform_junctions, isoform_region, delta",
                             [([], (20, 100), [(50, 170)], (20, 290), 1)])
    def test_incomplete_intron_retention_right(self, read_junctions, read_region, isoform_junctions, isoform_region, delta):
        assigner = LongReadAssigner(self.gene_info, Params(delta))
        match_events = assigner.intron_comparator.compare_junctions(read_junctions, read_region,
                                                                    isoform_junctions, isoform_region)
        assert len(match_events) == 1
        assert match_events[0].event_type == MatchEventSubtype.incomplete_intron_retention_right

    @pytest.mark.parametrize("read_junctions, read_region, isoform_junctions, isoform_region, delta",
                             [([], (150, 320), [(50, 170)], (20, 290), 1)])
    def test_incomplete_intron_retention_left(self, read_junctions, read_region, isoform_junctions, isoform_region, delta):
        assigner = LongReadAssigner(self.gene_info, Params(delta))
        match_events = assigner.intron_comparator.compare_junctions(read_junctions, read_region,
                                                                    isoform_junctions, isoform_region)
        assert len(match_events) == 1
        assert match_events[0].event_type == MatchEventSubtype.incomplete_intron_retention_left

    @pytest.mark.parametrize("read_junctions, read_region, isoform_junctions, isoform_region, delta",
                             [([], (100, 150), [(50, 170)], (20, 290), 1),
                              ([], (20, 55), [(50, 170)], (20, 290), 1)])
    def test_mono_exonic(self, read_junctions, read_region, isoform_junctions, isoform_region, delta):
        assigner = LongReadAssigner(self.gene_info, Params(delta))
        match_events = assigner.intron_comparator.compare_junctions(read_junctions, read_region,
                                                                    isoform_junctions, isoform_region)
        assert len(match_events) == 1
        assert match_events[0].event_type == MatchEventSubtype.mono_exonic

    @pytest.mark.parametrize("read_junctions, read_region, isoform_junctions, isoform_region, delta",
                             [([(1, 10), (15,  20)], (0, 30), [(2, 10), (15,  19)], (0, 40), 3),
                              ([(1, 10), (15, 20)], (0, 30), [(1, 10), (15, 20)], (0, 50), 0),
                              ([(1, 10), (15, 20)], (0, 30), [(1, 10), (15, 21)], (0, 30), 1),
                              ([(15, 20), (25, 35)], (10, 40), [(1, 10), (15, 21), (25, 34)], (0, 40), 2)])
    def test_no_contradiction(self, read_junctions, read_region, isoform_junctions, isoform_region, delta):
        assigner = LongReadAssigner(self.gene_info, Params(delta))
        match_events = assigner.intron_comparator.compare_junctions(read_junctions, read_region,
                                                                    isoform_junctions, isoform_region)
        assert len(match_events) == 1
        assert match_events[0].event_type == MatchEventSubtype.none

    @pytest.mark.parametrize("read_junctions, read_region, isoform_junctions, isoform_region, delta, expected_len",
                             [([(1, 100), (150,  200)], (0, 300), [(2, 101)], (0, 120), 1, 1),
                              ([(1, 100), (150, 200), (250, 360), (380, 390)], (0, 400), [(3, 100), (150, 201)], (0, 249), 3, 2)])
    def test_extra_intron_out_right(self, read_junctions, read_region, isoform_junctions, isoform_region, delta, expected_len):
        assigner = LongReadAssigner(self.gene_info, Params(delta))
        match_events = assigner.intron_comparator.compare_junctions(read_junctions, read_region,
                                                                    isoform_junctions, isoform_region)
        assert len(match_events) == expected_len
        assert match_events[0].event_type == MatchEventSubtype.extra_intron_flanking_right

    @pytest.mark.parametrize("read_junctions, read_region, isoform_junctions, isoform_region, delta, expected_len",
                             [([(1, 100), (150, 200)], (0, 300), [(150, 201)], (110, 220), 1, 1),
                              ([(1, 100), (150, 200), (250, 360)], (0, 400), [(251, 361)], (201, 405), 3, 2)])
    def test_extra_intron_out_left(self, read_junctions, read_region, isoform_junctions, isoform_region, delta, expected_len):
        assigner = LongReadAssigner(self.gene_info, Params(delta))
        match_events = assigner.intron_comparator.compare_junctions(read_junctions, read_region,
                                                                    isoform_junctions, isoform_region)
        assert len(match_events) == expected_len
        assert match_events[0].event_type == MatchEventSubtype.extra_intron_flanking_left

    @pytest.mark.parametrize("read_junctions, read_region, isoform_junctions, isoform_region, delta",
                             [([(20, 50), (60, 100), (150,  200)], (0, 300), [(20, 51), (150, 201)], (0, 290), 1)])
    def test_extra_intron(self, read_junctions, read_region, isoform_junctions, isoform_region, delta):
        assigner = LongReadAssigner(self.gene_info, Params(delta))
        match_events = assigner.intron_comparator.compare_junctions(read_junctions, read_region,
                                                                    isoform_junctions, isoform_region)
        assert len(match_events) == 1
        assert match_events[0].event_type == MatchEventSubtype.extra_intron

    @pytest.mark.parametrize("read_junctions, read_region, isoform_junctions, isoform_region, delta",
                             [([(20, 40), (50, 60), (150,  200)], (0, 300), [(20, 41), (150, 201)], (0, 290), 1),
                              ([(20, 40), (78, 112), (150, 200)], (0, 300), [(20, 41), (150, 201)], (0, 290), 3)])
    def test_extra_intron_known(self, read_junctions, read_region, isoform_junctions, isoform_region, delta):
        assigner = LongReadAssigner(self.gene_info, Params(delta))
        match_events = assigner.intron_comparator.compare_junctions(read_junctions, read_region,
                                                                    isoform_junctions, isoform_region)
        assert len(match_events) == 1
        assert match_events[0].event_type == MatchEventSubtype.extra_intron_known

    @pytest.mark.parametrize("read_junctions, read_region, isoform_junctions, isoform_region, delta",
                             [([(10, 50), (150,  200)], (0, 300), [(10, 51), (80, 100), (150, 200), (225, 240)], (0, 310), 3)])
    def test_missed_intron_in(self, read_junctions, read_region, isoform_junctions, isoform_region, delta):
        assigner = LongReadAssigner(self.gene_info, Params(delta))
        match_events = assigner.intron_comparator.compare_junctions(read_junctions, read_region,
                                                                    isoform_junctions, isoform_region)
        event_types = [match_events[i].event_type for i in range(len(match_events))]
        assert len(match_events) == 2
        assert set(event_types) == {MatchEventSubtype.intron_retention}

    @pytest.mark.parametrize("read_junctions, read_region, isoform_junctions, isoform_region, delta",
                             [([(10, 50)], (0, 100), [(10, 25), (40, 49)], (0, 99), 3)])
    def test_exon_skipping_novel_intron(self, read_junctions, read_region, isoform_junctions, isoform_region, delta):
        assigner = LongReadAssigner(self.gene_info, Params(delta))
        match_events = assigner.intron_comparator.compare_junctions(read_junctions, read_region,
                                                                    isoform_junctions, isoform_region)
        assert len(match_events) == 1
        assert match_events[0].event_type == MatchEventSubtype.exon_skipping_novel_intron

    @pytest.mark.parametrize("read_junctions, read_region, isoform_junctions, isoform_region, delta",
                             [([(1, 10), (15, 50)], (15, 50), [(1, 49)], (1, 49), 1)])
    def test_exon_gain_novel(self, read_junctions, read_region, isoform_junctions, isoform_region, delta):
        assigner = LongReadAssigner(self.gene_info, Params(delta))
        match_events = assigner.intron_comparator.compare_junctions(read_junctions, read_region,
                                                                    isoform_junctions, isoform_region)
        assert len(match_events) == 1
        assert match_events[0].event_type == MatchEventSubtype.exon_gain_novel


class TestDetectContradictionType:
    gene_info = GeneInfo(IntronProfiles([(1, 1)]), 1, 100)

    def test(self):
        assigner = LongReadAssigner(self.gene_info, Params(3))
        match_events = assigner.intron_comparator.detect_contradiction_type((0, 200), [(50, 75)], (0, 200), [(45, 70)], [((0, 0), (0, 0))])
        assert len(match_events) == 1
        assert match_events[0].event_type == MatchEventSubtype.intron_shift
