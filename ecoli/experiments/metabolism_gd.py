"""
===========================================
Metabolism using Gradient Descent-based FBA
===========================================
"""
import argparse

# vivarium-core imports
import pytest
from vivarium.core.engine import Engine
from vivarium.core.composer import Composer
from vivarium.library.dict_utils import deep_merge

# vivarium-ecoli imports
from ecoli.experiments.ecoli_master_sim import EcoliSim, CONFIG_DIR_PATH
from ecoli.library.sim_data import LoadSimData
from ecoli.states.wcecoli_state import get_state_from_file
from ecoli.composites.ecoli_master import SIM_DATA_PATH
from ecoli.processes.metabolism_gd import MetabolismGD
from ecoli.processes.stubs.exchange_stub import Exchange
from ecoli.processes.registries import topology_registry

import numpy as np
import pathlib, datetime
import dill

# get topology from ecoli_master
metabolism_topology = topology_registry.access('ecoli-metabolism')


# make a composite with Exchange
class MetabolismExchange(Composer):
    defaults = {
        'metabolism': {
            'kinetic_rates': [],
        },
        'exchanger': {},
        'sim_data_path': SIM_DATA_PATH,
        'seed': 0,
    }

    def __init__(self, config=None):
        super().__init__(config)
        self.load_sim_data = LoadSimData(
            sim_data_path=self.config['sim_data_path'],
            seed=self.config['seed'])

    def generate_processes(self, config):
        # configure metabolism
        metabolism_config = self.load_sim_data.get_metabolism_gd_config()
        metabolism_config = deep_merge(metabolism_config, config['metabolism'])
        metabolism_process = MetabolismGD(metabolism_config)

        example_update = {'ATP[c]': 9064, 'DATP[c]': 2222, 'DCTP[c]': 1649, 'DGTP[c]': 1647, 'FAD[c]': 171,
                          'GTP[c]': 20122, 'LEU[c]': 325, 'METHYLENE-THF[c]': 223, 'NAD[c]': 769,
                          'PHENYL-PYRUVATE[c]': 996, 'REDUCED-MENAQUINONE[c]': 240, 'UTP[c]': 14648}

        # configure exchanger stub process
        # TODO -- this needs a dictionary with {mol_id: exchanged counts/sec}
        exchanger_config = {'exchanges': example_update, 'time_step': metabolism_config['time_step']}
        exchanger_process = Exchange(exchanger_config)

        return {
            'metabolism': metabolism_process,
            'exchanger': exchanger_process,
        }

    def generate_topology(self, config):
        return {
            'metabolism': metabolism_topology,
            'exchanger': {
                'molecules': ('bulk',),
            }
        }


def run_metabolism():
    # load the sim data
    load_sim_data = LoadSimData(
        sim_data_path=SIM_DATA_PATH,
        seed=0)

    # Create process, experiment, loading in initial state from file.
    config = load_sim_data.get_metabolism_gd_config()
    metabolism_process = MetabolismGD(config)

    initial_state = get_state_from_file(
        path=f'data/wcecoli_t1000.json')

    metabolism_composite = metabolism_process.generate()
    experiment = Engine(
        processes=metabolism_composite['processes'],
        topology=metabolism_composite['topology'],
        initial_state=initial_state
    )

    experiment.update(10)

    data = experiment.emitter.get_timeseries()


def run_metabolism_composite():
    composer = MetabolismExchange()
    metabolism_composite = composer.generate()

    initial_state = get_state_from_file(
        path=f'data/wcecoli_t1000.json')

    experiment = Engine(
        processes=metabolism_composite['processes'],
        topology=metabolism_composite['topology'],
        initial_state=initial_state
    )

    experiment.update(10)

    data = experiment.emitter.get_data()


def run_ecoli_with_metabolism_gd(
        filename='fba_gd_swap',
        total_time=10,
        divide=True,
        initial_state_file='vivecoli_t2000',
        progress_bar=False,
        log_updates=False,
        emitter='timeseries',
        name='kinetics',
        raw_output=False,
        save=False,
        save_times=None,
):
    # filename = 'default'
    sim = EcoliSim.from_file(CONFIG_DIR_PATH + filename + '.json')
    sim.total_time = total_time
    sim.divide = divide
    sim.progress_bar = progress_bar
    sim.log_updates = log_updates
    sim.emitter = emitter
    sim.initial_state = get_state_from_file(path=f'data/{initial_state_file}.json')
    sim.raw_output = False
    # sim.save = True
    # sim.save_times = [1000, 2000, 2500, 3000, 3500]


    sim.run()

    query = []
    agents = sim.query()['agents'].keys()
    for agent in agents:
        query.extend([('agents', agent, 'listeners', 'fba_results'),
                      ('agents', agent, 'listeners', 'mass'),
                      ('agents', agent, 'bulk')])
    output = sim.query(query)


    folder = f'out/fbagd/{name}_{total_time}_{datetime.date.today()}/'
    pathlib.Path(folder).mkdir(parents=True, exist_ok=True)
    np.save(folder + 'output.npy', output)

    f = open(folder + 'agent.pkl', 'wb')
    dill.dump(sim.ecoli['processes']['agents'][agent], f)
    f.close()


@pytest.mark.slow
def test_ecoli_with_metabolism_gd(
        filename='fba_gd_swap',
        total_time=4,
        divide=False,
        progress_bar=True,
        log_updates=False,
        emitter='timeseries',
):
    sim = EcoliSim.from_file(CONFIG_DIR_PATH + filename + '.json')
    sim.total_time = total_time
    sim.divide = divide
    sim.progress_bar = progress_bar
    sim.log_updates = log_updates
    sim.emitter = emitter

    # assert that the processes were swapped
    sim.build_ecoli()

    assert 'ecoli-metabolism-gradient-descent' in sim.ecoli['processes']
    assert 'ecoli-metabolism' not in sim.ecoli['processes']
    assert 'ecoli-metabolism-gradient-descent' in sim.ecoli['topology']
    assert 'ecoli-metabolism' not in sim.ecoli['topology']


    # run simulation and add asserts to output
    sim.run()



@pytest.mark.slow
def test_ecoli_with_metabolism_gd_div(
        filename='fba_gd_division',
        total_time=4,
        divide=True,
        emitter='timeseries',
):
    # TODO (Cyrus) - Add test that affirms structure of output query.
    sim = EcoliSim.from_file(CONFIG_DIR_PATH + filename + '.json')
    sim.total_time = total_time
    sim.divide = divide
    sim.emitter = emitter

    # assert that the processes were swapped
    sim.build_ecoli()

    assert 'ecoli-metabolism-gradient-descent' in sim.processes
    assert 'ecoli-metabolism' not in sim.processes
    assert 'ecoli-metabolism-gradient-descent' in sim.processes
    assert 'ecoli-metabolism' not in sim.processes

    sim.run()

    query = []
    agents = sim.query()['agents'].keys()
    for agent in agents:
        query.extend([('agents', agent, 'listeners', 'fba_results'),
                      ('agents', agent, 'listeners', 'mass'),
                      ('agents', agent, 'bulk')])
    output = sim.query(query)

    # test that water is being used (model is running)
    assert sum(output['agents'][agent]['listeners']['fba_results']['estimated_exchange_dmdt']['WATER[p]']) != 0

def run_ecoli_with_default_metabolism(
        filename='default',
        total_time=10,
        divide=False,
        progress_bar=True,
        log_updates=False,
        emitter='timeseries',
):
    sim = EcoliSim.from_file(CONFIG_DIR_PATH + filename + '.json')
    sim.total_time = total_time
    sim.divide = divide
    sim.progress_bar = progress_bar
    sim.log_updates = log_updates
    sim.emitter = emitter

    sim.run()
    output = sim.query()


    folder = f'out/fbagd/{total_time}/{datetime.datetime.now()}/'
    pathlib.Path(folder).mkdir(parents=True, exist_ok=True)
    np.save(folder + 'fba_results.npy', output['listeners']['fba_results'])
    np.save(folder + 'mass.npy', output['listeners']['mass'])
    np.save(folder + 'bulk.npy', output['bulk'])
    np.save(folder + 'stoichiometry.npy', sim.ecoli.processes['ecoli-metabolism-gradient-descent'].stoichiometry)

experiment_library = {
    '0': run_metabolism,
    '1': run_metabolism_composite,
    '2': run_ecoli_with_metabolism_gd,
    '3': test_ecoli_with_metabolism_gd,
    '4': test_ecoli_with_metabolism_gd_div,
    '5': run_ecoli_with_default_metabolism,
}

# run experiments with command line arguments: python ecoli/experiments/metabolism_gd.py -n exp_id
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='metabolism with gd')
    parser.add_argument('--name', '-n', default=[], nargs='+', help='test ids to run')
    args = parser.parse_args()
    run_all = not args.name

    for name in args.name:
        experiment_library[name]()
    if run_all:
        for name, test in experiment_library.items():
            test()
