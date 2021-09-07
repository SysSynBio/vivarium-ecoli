"""
=============
Cell Division
=============
"""
import random
from typing import Any, Dict
import numpy as np

from vivarium.core.process import Deriver

NAME = 'ecoli-cell-division'


def divide_active_RNAPs_by_domain(state, **args):
    """
    divide a dictionary into two daughters based on their domain_index
    """
    daughter1 = {}
    daughter2 = {}
    for state_id, value in state.items():
        domain_index = value['domain_index']
        if domain_index == 1:
            daughter1[state_id] = value
        elif domain_index == 2:
            daughter2[state_id] = value
            daughter2[state_id]['domain_index'] = 1
    return [daughter1, daughter2]


def divide_RNAs_by_domain(state, view):
    """
    divide a dictionary of unique RNAs into two daughters,
    with partial RNAs divided along with their domain index
    """
    daughter1 = {}
    daughter2 = {}
    full_transcripts = []

    # divide partial transcripts by domain_index
    for unique_id, specs in state.items():
        if not specs['is_full_transcript']:
            if unique_id not in view['active_RNAP']:
                print(f"unique_id {unique_id} not in active_RNAP")
                continue
            domain_index = view['active_RNAP'][unique_id]['domain_index']
            if domain_index == 1:
                daughter1[unique_id] = specs
            elif domain_index == 2:
                daughter2[unique_id] = specs
        else:
            # save full transcripts
            full_transcripts.append(unique_id)

    # divide full transcripts binomially
    n_full_transcripts = len(full_transcripts)
    daughter1_counts = np.random.binomial(n_full_transcripts, 0.5)
    daughter1_ids = random.sample(full_transcripts, daughter1_counts)
    for unique_id in full_transcripts:
        specs = state[unique_id]
        if unique_id in daughter1_ids:
            daughter1[unique_id] = specs
        else:
            daughter2[unique_id] = specs

    return [daughter1, daughter2]


def daughter_phylogeny_id(mother_id):
    return [
        str(mother_id) + '0',
        str(mother_id) + '1']


class Division(Deriver):
    """ Division Process """
    name = NAME
    defaults: Dict[str, Any] = {
        'daughter_ids_function': daughter_phylogeny_id,
        'threshold': None,
    }

    def __init__(self, parameters=None):
        super().__init__(parameters)

        # must provide a composer to generate new daughters
        self.agent_id = self.parameters['agent_id']
        self.composer = self.parameters['composer']

    def ports_schema(self):
        return {
            'variable': {},
            'agents': {
                '*': {}}}

    def next_update(self, timestep, states):
        variable = states['variable']

        print(f'division variable = {variable}')

        if variable >= self.parameters['threshold']:

            daughter_ids = self.parameters['daughter_ids_function'](self.agent_id)
            daughter_updates = []
            for daughter_id in daughter_ids:
                composer = self.composer.generate({'agent_id': daughter_id})
                daughter_updates.append({
                    'key': daughter_id,
                    'processes': composer['processes'],
                    'topology': composer['topology'],
                    'initial_state': {}})

            return {
                'agents': {
                    '_divide': {
                        'mother': self.agent_id,
                        'daughters': daughter_updates}}}
        return {}
