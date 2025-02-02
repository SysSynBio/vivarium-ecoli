"""
==================================
Metabolism using user-friendly FBA
==================================
"""
import argparse

# vivarium-core imports
import pytest

# vivarium-ecoli imports
from ecoli.experiments.ecoli_master_sim import EcoliSim, CONFIG_DIR_PATH
from ecoli.states.wcecoli_state import get_state_from_file

from wholecell.utils import units

import numpy as np
import pathlib, datetime
import dill

def run_ecoli_with_metabolism_redux(
        filename='metabolism_redux',
        total_time=50,
        divide=True,
        initial_state_file='wcecoli_t0',
        progress_bar=True,
        log_updates=False,
        emitter='timeseries',
        name='metabolism-redux',
        raw_output=False,
        save=False,
        # save_times=4,
):
    # filename = 'default'
    sim = EcoliSim.from_file(CONFIG_DIR_PATH + filename + '.json')
    sim.total_time = total_time
    sim.divide = divide
    sim.progress_bar = progress_bar
    sim.log_updates = log_updates
    sim.emitter = emitter
    sim.initial_state = get_state_from_file(path=f'data/{initial_state_file}.json')
    sim.raw_output = raw_output
    sim.save = save


    sim.build_ecoli()
    sim.run()

    query = []
    folder = f'out/fbagd/{name}_{total_time}_{datetime.date.today()}/'
    # save_sim_output(folder, query, sim, save_model=True)


def run_ecoli_with_metabolism_redux_classic(
        filename='metabolism_redux_classic',
        total_time=4,
        divide=True,
        initial_state_file='wcecoli_t0',
        progress_bar=True,
        log_updates=False,
        emitter='timeseries',
        name='metabolism-redux-classic',
        raw_output=False,
        save=False,
        # save_times=4,
):
    # filename = 'default'
    sim = EcoliSim.from_file(CONFIG_DIR_PATH + filename + '.json')
    sim.total_time = total_time
    sim.divide = divide
    sim.progress_bar = progress_bar
    sim.log_updates = log_updates
    sim.emitter = emitter
    sim.initial_state = get_state_from_file(path=f'data/{initial_state_file}.json')
    sim.raw_output = raw_output
    sim.save = save
    # sim.save_times = [4]

    # # simplify working with uptake
    # sim.initial_state['environment']['exchange_data']['constrained'] = {}
    # sim.initial_state['environment']['exchange_data']['unconstrained'].add('GLC[p]')
    #
    # # in sim.initial_state['environment']['exchange_data']['unconstrained'], edit the set of molecules to be exchanged
    # sim.initial_state['environment']['exchange_data']['unconstrained'].remove('GLC[p]')
    # sim.initial_state['environment']['exchange_data']['unconstrained'].add('FRU[p]')


    sim.build_ecoli()
    sim.run()

    query = []
    folder = f'out/fbagd/{name}_{total_time}_{datetime.date.today()}/'
    # save_sim_output(folder, query, sim, save_model=True)


@pytest.mark.slow
def test_ecoli_with_metabolism_redux(
        filename='metabolism_redux',
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
    sim.build_ecoli()

    # run simulation and add asserts to output
    sim.run()

    # assert 'ecoli-metabolism-gradient-descent' in sim.ecoli['processes']
    # assert 'ecoli-metabolism' not in sim.ecoli['processes']
    # assert 'ecoli-metabolism-gradient-descent' in sim.ecoli['topology']
    # assert 'ecoli-metabolism' not in sim.ecoli['topology']



@pytest.mark.slow
def test_ecoli_with_metabolism_redux_div(
        filename='metabolism_redux',
        total_time=4,
        divide=True,
        emitter='timeseries',
):
    # TODO (Cyrus) - Add test that affirms structure of output query.
    sim = EcoliSim.from_file(CONFIG_DIR_PATH + filename + '.json')
    sim.total_time = total_time
    sim.divide = divide
    sim.emitter = emitter
    sim.build_ecoli()

    sim.run()
    
    # # assert that the processes were swapped
    # assert 'ecoli-metabolism-gradient-descent' in sim.processes
    # assert 'ecoli-metabolism' not in sim.processes
    # assert 'ecoli-metabolism-gradient-descent' in sim.processes
    # assert 'ecoli-metabolism' not in sim.processes

    query = []
    agents = sim.query()['agents'].keys()
    for agent in agents:
        query.extend([('agents', agent, 'listeners', 'fba_results'),
                      ('agents', agent, 'listeners', 'mass'),
                      ('agents', agent, 'bulk')])
    output = sim.query(query)

    # test that water is being used (model is running)
    assert sum(output['agents'][agent]['listeners']['fba_results']['estimated_exchange_dmdt']['WATER']) != 0


@pytest.mark.slow
def test_ecoli_with_metabolism_classic(
        filename='metabolism_redux_classic',
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
    sim.build_ecoli()

    # run simulation and add asserts to output
    sim.run()

    # assert 'ecoli-metabolism-gradient-descent' in sim.ecoli['processes']
    # assert 'ecoli-metabolism' not in sim.ecoli['processes']
    # assert 'ecoli-metabolism-gradient-descent' in sim.ecoli['topology']
    # assert 'ecoli-metabolism' not in sim.ecoli['topology']


@pytest.mark.slow
def test_ecoli_with_metabolism_classic_div(
        filename='metabolism_redux_classic',
        total_time=4,
        divide=True,
        emitter='timeseries',
):
    # TODO (Cyrus) - Add test that affirms structure of output query.
    sim = EcoliSim.from_file(CONFIG_DIR_PATH + filename + '.json')
    sim.total_time = total_time
    sim.divide = divide
    sim.emitter = emitter
    sim.build_ecoli()

    sim.run()

    # # assert that the processes were swapped
    # assert 'ecoli-metabolism-gradient-descent' in sim.processes
    # assert 'ecoli-metabolism' not in sim.processes
    # assert 'ecoli-metabolism-gradient-descent' in sim.processes
    # assert 'ecoli-metabolism' not in sim.processes

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
    sim.build_ecoli()

    sim.run()
    # output = sim.query()
    output = sim.ecoli_experiment.emitter.get_timeseries()


    folder = f'out/fbagd/{total_time}/{datetime.datetime.now()}/'
    pathlib.Path(folder).mkdir(parents=True, exist_ok=True)
    np.save(folder + 'fba_results.npy', output['listeners']['fba_results'])
    np.save(folder + 'mass.npy', output['listeners']['mass'])
    np.save(folder + 'bulk.npy', output['bulk'])
    np.save(folder + 'stoichiometry.npy', sim.ecoli_experiment.steps['ecoli-metabolism'].model.stoichiometry)

experiment_library = {
    '2': run_ecoli_with_metabolism_redux,
    '2a': run_ecoli_with_metabolism_redux_classic,
    '3': test_ecoli_with_metabolism_redux,
    '3a': test_ecoli_with_metabolism_classic,
    '4': test_ecoli_with_metabolism_redux_div,
    '4a': test_ecoli_with_metabolism_classic_div,
    '5': run_ecoli_with_default_metabolism,
}


def save_sim_output(folder, query, sim, save_model=False):
    agents = sim.query()['agents'].keys()
    for agent in agents:
        query.extend([('agents', agent, 'listeners', 'fba_results'),
                      ('agents', agent, 'listeners', 'mass'),
                      ('agents', agent, 'bulk')])
    output = sim.query(query)
    pathlib.Path(folder).mkdir(parents=True, exist_ok=True)
    np.save(folder + 'output.npy', output)

    if save_model:
        f = open(folder + 'agent_processes.pkl', 'wb')
        dill.dump(sim.ecoli['processes']['agents'][agent], f)
        f.close()

        f = open(folder + 'agent_steps.pkl', 'wb')
        dill.dump(sim.ecoli['steps']['agents'][agent], f)
        f.close()

# run experiments with command line arguments: python ecoli/experiments/metabolism_redux_sim.py -n exp_id
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='user-friendly metabolism')
    parser.add_argument('--name', '-n', default=[], nargs='+', help='test ids to run')
    args = parser.parse_args()
    run_all = not args.name

    for name in args.name:
        experiment_library[name]()
    if run_all:
        for name, test in experiment_library.items():
            test()
