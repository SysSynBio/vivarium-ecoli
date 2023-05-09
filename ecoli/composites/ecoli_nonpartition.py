"""
========================
E. coli master composite
========================
"""
import copy
import os
import binascii
import numpy as np

import pytest

from vivarium.core.composer import Composer
from vivarium.library.topology import assoc_path
from vivarium.library.dict_utils import deep_merge
from vivarium.core.control import run_library_cli
from vivarium.core.engine import pf

from wholecell.utils import units

# sim data
from ecoli.library.sim_data import LoadSimData

# logging
from vivarium.library.wrappers import make_logging_process

# vivarium-ecoli processes
from ecoli.composites.ecoli_configs import (
    ECOLI_DEFAULT_PROCESSES, ECOLI_DEFAULT_TOPOLOGY)
from ecoli.processes.cell_division import Division

# state
from ecoli.states.wcecoli_state import get_state_from_file

# plotting
from vivarium.plots.topology import plot_topology
from ecoli.plots.topology import get_ecoli_nonpartition_topology_settings


RAND_MAX = 2**31
SIM_DATA_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__), '..', '..', 'reconstruction',
        'sim_data', 'kb', 'simData.cPickle',
    )
)

MINIMAL_MEDIA_ID = 'minimal'
AA_MEDIA_ID = 'minimal_plus_amino_acids'
ANAEROBIC_MEDIA_ID = 'minimal_minus_oxygen'


class Ecoli(Composer):

    defaults = {
        'time_step': 2.0,
        'parallel': False,
        'seed': 0,
        'sim_data_path': SIM_DATA_PATH,
        'daughter_path': tuple(),
        'agent_id': '0',
        'agents_path': ('..', '..', 'agents',),
        'division_threshold': 668,  # fg
        'division_variable': ('listeners', 'mass', 'dry_mass'),
        'divide': False,
        'log_updates': False
    }

    def __init__(self, config):
        super().__init__(config)

        self.load_sim_data = LoadSimData(
            sim_data_path=self.config['sim_data_path'],
            seed=self.config['seed'])

        if not self.config.get('processes'):
            self.config['processes'] = ECOLI_DEFAULT_PROCESSES.copy()
        if not self.config.get('process_configs'):
            self.config['process_configs'] = {process: "sim_data" for process in self.config['processes']}
        if not self.config.get('topology'):
            self.config['topology'] = ECOLI_DEFAULT_TOPOLOGY.copy()

        self.processes = self.config['processes']
        self.topology = self.config['topology']

    def initial_state(self, config=None, path=()):
        # Use initial state calculated with trna_charging and translationSupply disabled
        config = config or {}
        # Allow initial state to be directly supplied instead of a file name (useful when
        # loading individual cells in a colony save file)
        initial_state = config.get('initial_state', None)
        if not initial_state:
            initial_state_file = config.get('initial_state_file', 'wcecoli_t0')
            initial_state = get_state_from_file(path=f'data/{initial_state_file}.json')
        
        initial_state_overrides = config.get('initial_state_overrides', [])
        if initial_state_overrides:
            bulk_map = {bulk_id: row_id for row_id, bulk_id
                in enumerate(initial_state['bulk']['id'])}
        for override_file in initial_state_overrides:
            override = get_state_from_file(path=f"data/{override_file}.json")
            # Apply bulk overrides of the form {molecule: count} to Numpy array
            bulk_overrides = override.pop('bulk', {})
            initial_state['bulk'].flags.writeable = True
            for molecule, count in bulk_overrides.items():
                initial_state['bulk']['count'][bulk_map[molecule]] = count
            initial_state['bulk'].flags.writeable = False
            deep_merge(initial_state, override)

        embedded_state = {}
        assoc_path(embedded_state, path, initial_state)
        return embedded_state

    def generate_processes(self, config):
        time_step = config['time_step']
        parallel = config['parallel']

        # get process configs
        process_configs = config['process_configs']
        for process in process_configs.keys():
            if process_configs[process] == "sim_data":
                process_configs[process] = self.load_sim_data.get_config_by_name(process)
            elif process_configs[process] == "default":
                process_configs[process] = None
            else:
                # user passed a dict, deep-merge with config from LoadSimData
                # if it exists, else, deep-merge with default
                try:
                    default = self.load_sim_data.get_config_by_name(process)
                except KeyError:
                    default = self.processes[process].defaults

                process_configs[process] = deep_merge(copy.deepcopy(default), process_configs[process])

        # make the processes
        processes = {
            process_name: (process(process_configs[process_name])
                           if not config['log_updates']
                           else make_logging_process(process)(process_configs[process_name]))
            for (process_name, process) in self.processes.items()
        }

        # add division process
        if config['divide']:
            expectedDryMassIncreaseDict = self.load_sim_data.sim_data.expectedDryMassIncreaseDict
            division_name = 'division'
            division_config = {'threshold': config['division_threshold']}
            if config['division_threshold'] == 'massDistribution':
                division_random_seed = binascii.crc32(b'CellDivision', config['seed']) & 0xffffffff
                division_random_state = np.random.RandomState(seed=division_random_seed)
                division_mass_multiplier = division_random_state.normal(loc=1.0, scale=0.1)
                initial_state_file = config.get('initial_state_file', 'wcecoli_t0')
                initial_state_overrides = config.get('initial_state_overrides', [])
                initial_state = get_state_from_file(path=f'data/{initial_state_file}.json')
                for override_file in initial_state_overrides:
                    override = get_state_from_file(path=f"data/{override_file}.json")
                    deep_merge(initial_state, override)
                current_media_id = initial_state['environment']['media_id']
                division_config['threshold'] = (initial_state['listeners']['mass']['dry_mass'] + 
                    expectedDryMassIncreaseDict[current_media_id].asNumber(
                        units.fg) * division_mass_multiplier)
            division_config = dict(
                division_config,
                agent_id=config['agent_id'],
                composer=self,
                seed=self.load_sim_data.random_state.randint(RAND_MAX),
            )
            division_process = {division_name: Division(division_config)}
            processes.update(division_process)

        return processes

    def generate_topology(self, config):
        topology = {}

        # make the topology
        for process_id, ports in self.topology.items():
            topology[process_id] = ports
            if config['log_updates']:
                topology[process_id]['log_update'] = ('log_update', process_id,)

        # add division
        if self.config['divide']:
            topology['division'] = {
                'variable': config['division_variable'],
                'agents': config['agents_path']}

        return topology


def run_ecoli(
        total_time=10,
        divide=False,
        progress_bar=True,
        log_updates=False,
        time_series=True,
        print_config=False,
):
    """
    Simple way to run ecoli simulations. For full API, see ecoli.experiments.ecoli_master_sim.

    Arguments:
        * **total_time** (:py:class:`int`): the total runtime of the experiment
        * **divide** (:py:class:`bool`): whether to incorporate division
        * **progress_bar** (:py:class:`bool`): whether to show a progress bar
        * **log_updates**  (:py:class:`bool`): whether to save updates from each process
        * **time_series** (:py:class:`bool`): whether to return data in timeseries format
    Returns:
        * output data
    """

    from ecoli.experiments.ecoli_master_sim import EcoliSim, CONFIG_DIR_PATH

    sim = EcoliSim.from_file(CONFIG_DIR_PATH + "no_partition.json")
    sim.total_time = total_time
    sim.divide = divide
    sim.progress_bar = progress_bar
    sim.log_updates = log_updates
    sim.raw_output = not time_series

    sim.build_ecoli()
    if print_config:
        ecoli_store = sim.ecoli.generate_store()
        print(pf(ecoli_store['unique'].get_config()))

    sim.run()
    return sim.query()


def test_ecoli():
    output = run_ecoli()


@pytest.mark.slow
def run_division(
        total_time=30
):
    """
    Work in progress to get division working
    * TODO -- unique molecules need to be divided between daughter cells!!! This can get sophisticated
    """

    from ecoli.experiments.ecoli_master_sim import EcoliSim, CONFIG_DIR_PATH

    # get division mass
    initial_state = Ecoli({}).initial_state()
    initial_mass = initial_state['listeners']['mass']['cell_mass']
    division_mass = initial_mass+0.1
    # print(f"DIVIDE AT {division_mass} fg")

    # initialize simulation
    sim = EcoliSim.from_file(CONFIG_DIR_PATH + "no_partition.json")
    sim.division = {'threshold': division_mass}
    sim.total_time = total_time
    sim.divide = True
    sim.progress_bar = False
    sim.raw_output = True
    sim.build_ecoli()

    # run simulation
    sim.run()
    output = sim.query()

    # asserts
    initial_agents = output[0.0]['agents'].keys()
    final_agents = output[total_time]['agents'].keys()
    print(f"initial agent ids: {initial_agents}")
    print(f"final agent ids: {final_agents}")
    assert len(final_agents) == 2 * len(initial_agents)


def test_ecoli_generate():
    ecoli_composer = Ecoli({})
    ecoli_composite = ecoli_composer.generate()

    # asserts to ecoli_composite['processes'] and ecoli_composite['topology']
    assert all(isinstance(v, ECOLI_DEFAULT_PROCESSES[k])
               for k, v in ecoli_composite['processes'].items())
    assert all(ECOLI_DEFAULT_TOPOLOGY[k] == v
               for k, v in ecoli_composite['topology'].items())


def ecoli_topology_plot():
    """Make a topology plot of Ecoli"""
    agent_config = {
        'agent_id': '1',
        'processes': ECOLI_DEFAULT_PROCESSES,
        'topology': ECOLI_DEFAULT_TOPOLOGY,
        'process_configs': {
            process_id: "sim_data" for process_id in ECOLI_DEFAULT_PROCESSES.keys()}
        }
    ecoli = Ecoli(agent_config)
    settings = get_ecoli_nonpartition_topology_settings()

    topo_plot = plot_topology(
        ecoli,
        filename='ecoli_nonpartition_topology',
        out_dir='out/composites/ecoli_nonpartition/',
        settings=settings)
    return topo_plot


test_library = {
    '0': run_ecoli,
    '1': run_division,
    '2': test_ecoli_generate,
    '3': ecoli_topology_plot,
}

# run experiments in test_library from the command line with:
# python ecoli/composites/ecoli_nonpartition.py -n [experiment id]
if __name__ == '__main__':
    run_library_cli(test_library)
