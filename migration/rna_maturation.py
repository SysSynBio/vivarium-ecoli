"""
tests that vivarium-ecoli RnaMaturation process update is the same as saved wcEcoli updates
"""
import pytest

from ecoli.processes.rna_maturation import RnaMaturation
from migration.migration_utils import run_and_compare

@pytest.mark.master
def test_rna_maturation_migration():
    times = [0, 1870]
    for initial_time in times:
        run_and_compare(initial_time, RnaMaturation, layer=4)

if __name__ == "__main__":
    test_rna_maturation_migration()
