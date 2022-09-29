'''Composite for simulations with EngineProcess cells in an environment.

.. note::

    This composite requires a config with the spatial environment
    enabled.
'''

from datetime import datetime, timezone
import os
import re
import gc
import binascii

import numpy as np
from vivarium.core.composer import Composer
from vivarium.core.emitter import SharedRamEmitter
from vivarium.core.engine import Engine
from vivarium.core.serialize import serialize_value
from vivarium.core.store import Store
from vivarium.library.dict_utils import deep_merge
from vivarium.library.topology import get_in

from wholecell.utils import units
from ecoli.experiments.ecoli_master_sim import (
    EcoliSim,
    SimConfig,
    get_git_revision_hash,
    get_git_status,
    report_profiling,
)
from ecoli.library.logging import write_json
from ecoli.library.sim_data import RAND_MAX
from ecoli.states.wcecoli_state import get_state_from_file
from ecoli.processes.engine_process import EngineProcess
from ecoli.processes.environment.field_timeline import FieldTimeline
from ecoli.composites.environment.lattice import Lattice
from ecoli.composites.ecoli_configs import CONFIG_DIR_PATH


class EcoliInnerSim(Composer):
    defaults = {
        'agent_id': '0',
        'seed': 0,
        'division_threshold': None,
        'division_variable': None,
        'initial_inner_state': None,
    }
    
    def generate(self, config=None):
        if config is None:
            config = self.config
        config['initial_state'] = config.pop('initial_inner_state')
        ecoli_sim = EcoliSim({
            **self.config,
            **config,
            'divide': False,  # Division is handled by EngineProcess.
            'spatial_environment': False,
        })
        ecoli_sim.build_ecoli()
        initial_state = ecoli_sim.initial_state
        if config['division_threshold'] == 'massDistribution':
            expectedDryMassIncreaseDict = ecoli_sim.ecoli.steps[
                'ecoli-mass-listener'].parameters['expectedDryMassIncreaseDict']
            division_random_seed = (binascii.crc32(b'CellDivision', config['seed']) 
                                    & 0xffffffff)
            division_random_state = np.random.RandomState(seed=division_random_seed)
            division_mass_multiplier = division_random_state.normal(loc=1.0, scale=0.1)
            current_media_id = initial_state['environment']['media_id']
            config['division_threshold'] = (
                get_in(initial_state, config['division_variable']) + 
                expectedDryMassIncreaseDict[current_media_id].asNumber(units.fg)
                * division_mass_multiplier)
        ecoli_sim.ecoli['division_threshold'] = config['division_threshold']
        ecoli_sim.ecoli['division_variable'] = config['division_variable']
        ecoli_sim.ecoli['initial_inner_state'] = initial_state
        return ecoli_sim.ecoli
    
    # Not used
    def generate_processes(self, config):
        pass
    def generate_topology(self, config):
        pass

class EcoliEngineProcess(Composer):

    defaults = {
        'agent_id': '0',
        'seed': 0,
        'tunnel_out_schemas': {},
        'stub_schemas': {},
        'parallel': False,
        'divide': False,
        'division_threshold': None,
        'division_variable': None,
        'tunnels_in': tuple(),
        'emit_paths': tuple(),
        'start_time': 0,
        'experiment_id': '',
        'inner_emitter': 'null',
        'inner_composer_config': {}
    }

    def generate_processes(self, config):
        inner_composer_config = config.pop('inner_composer_config')
        cell_process_config = {
            'agent_id': config['agent_id'],
            'outer_composer': EcoliEngineProcess,
            'outer_composer_config': config,
            'inner_composer': EcoliInnerSim,
            'inner_composer_config': inner_composer_config,
            'tunnels_in': dict({
                f'{"-".join(path)}_tunnel': path
                for path in config['tunnels_in']
            }),
            'emit_paths': config['emit_paths'],
            'tunnel_out_schemas': config['tunnel_out_schemas'],
            'stub_schemas': config['stub_schemas'],
            'seed': (config['seed'] + 1) % RAND_MAX,
            'inner_emitter': config['inner_emitter'],
            'divide': config['divide'],
            'division_threshold': config['division_threshold'],
            'division_variable': config['division_variable'],
            '_parallel': config['parallel'],
            'start_time': config['start_time'],
            'experiment_id': config['experiment_id'],
        }
        cell_process = EngineProcess(cell_process_config)
        return {
            'cell_process': cell_process,
        }

    def generate_topology(self, config):
        topology = {
            'cell_process': {
                'agents': ('..',),
                'fields_tunnel': ('..', '..', 'fields'),
                'dimensions_tunnel': ('..', '..', 'dimensions'),
            },
        }
        for path in config['tunnels_in']:
            topology['cell_process'][f'{"-".join(path)}_tunnel'] = path
        return topology


def colony_save_states(engine, config):
    """
    Runs the simulation while saving the states of the colony at specific timesteps to jsons.
    """
    for time in config["save_times"]:
        if time > config["total_time"]:
            raise ValueError(
                f'Config contains save_time ({time}) > total '
                f'time ({config["total_time"]})')

    for i in range(len(config["save_times"])):
        if i == 0:
            time_to_next_save = config["save_times"][i]
        else:
            time_to_next_save = config["save_times"][i] - config["save_times"][i - 1]
        # Run engine to next save point
        engine.update(time_to_next_save)
        time_elapsed = config["save_times"][i]

        # Save the full state of the super-simulation
        def not_a_process(value):
            return not (isinstance(value, Store) and value.topology)

        # Copy not needed because serialize_value no longer mutates with orjson
        state_to_save = engine.state.get_value(condition=not_a_process)

        # Get internal state from the EngineProcess sub-simulation
        for agent_id in state_to_save['agents']:
            engine.state.get_path(
                ('agents', agent_id, 'cell_process')
            ).value.send_command('get_inner_state')
        for agent_id in state_to_save['agents']:
            cell_state = engine.state.get_path(
                ('agents', agent_id, 'cell_process')
            ).value.get_command_result()
            cell_state['division_threshold'] = engine.state.get_path(
                ('agents', agent_id, 'cell_process')
            ).value.parameters['division_threshold']
            del cell_state['environment']['exchange_data']  # Can't save, but will be restored when loading state
            del cell_state['evolvers_ran']
            state_to_save['agents'][agent_id] = cell_state

        state_to_save = serialize_value(state_to_save)
        write_json('data/tet_seed_0_colony_t' + str(time_elapsed) + '.json', state_to_save)
        # Cleanup namespace (significant with high cell counts)
        del state_to_save, cell_state
        print('Finished saving the state at t = ' + str(time_elapsed))

    # Finish running the simulation
    time_remaining = config["total_time"] - config["save_times"][-1]
    if time_remaining:
        engine.update(time_remaining)


def run_simulation(config):

    tunnel_out_schemas = {}
    stub_schemas = {}
    if config['spatial_environment']:
        # Generate environment composite.
        environment_composer = Lattice(
            config['spatial_environment_config'])
        environment_composite = environment_composer.generate()
        del environment_composer
        # Must declare actual timeline under spatial_process_config > field_timeline
        # for stores to properly initialize
        field_timeline = FieldTimeline(
            config['spatial_environment_config']['field_timeline'])
        environment_composite.merge(
            processes={'field_timeline': field_timeline},
            topology={
                'field_timeline': {
                    port: tuple(path)
                    for port, path in config[
                        'spatial_environment_config'
                    ]['field_timeline_topology'].items()
                },
            },
        )
        del field_timeline
        diffusion_schema = environment_composite.processes[
            'reaction_diffusion'].get_schema()
        multibody_schema = environment_composite.processes[
            'multibody'].get_schema()
        tunnel_out_schemas['fields_tunnel'] = diffusion_schema['fields']
        tunnel_out_schemas['dimensions_tunnel'] = diffusion_schema[
            'dimensions']
        stub_schemas['diffusion'] = {
            ('boundary',): diffusion_schema['agents']['*']['boundary'],
            ('environment',): diffusion_schema[
                'agents']['*']['environment'],
        }
        stub_schemas['multibody'] = {
            ('boundary',): multibody_schema['agents']['*']['boundary'],
        }
        del multibody_schema, diffusion_schema

    experiment_id = datetime.now(timezone.utc).strftime(
        '%Y-%m-%d_%H-%M-%S_%f%z')
    emitter_config = {'type': config['emitter']}
    for key, value in config['emitter_arg']:
        emitter_config[key] = value
    
    if 'division_threshold' not in config._config:
        config['division_threshold'] = 668
    if 'division_variable' not in config._config:
        config['division_variable'] = ('listeners', 'mass', 'dry_mass')

    base_config = {
        'agent_id': config['agent_id'],
        'tunnel_out_schemas': tunnel_out_schemas,
        'stub_schemas': stub_schemas,
        'parallel': config['parallel'],
        'divide': config['divide'],
        'tunnels_in': (
            ('environment',),
            ('boundary',),
        ),
        'emit_paths': tuple(
            tuple(path) for path in config['engine_process_reports']
        ),
        'seed': config['seed'],
        'experiment_id': experiment_id,
        'start_time': config.get('start_time', 0),
        'inner_composer_config': config.to_dict()
    }

    composite = {}
    if 'initial_colony_file' in config.keys():
        initial_state = get_state_from_file(path=f'data/{config["initial_colony_file"]}.json')  # TODO(Matt): initial_state_file is wc_ecoli?
        agent_states = initial_state['agents']
        for agent_id, agent_state in agent_states.items():
            time_str = re.fullmatch(r'.*_t([0-9]+)$', config['initial_colony_file']).group(1)
            seed = (
                base_config['seed']
                + int(float(time_str))
                + int(agent_id, base=2)
            ) % RAND_MAX
            agent_path = ('agents', agent_id)
            division_threshold = agent_state.pop('division_threshold', None)
            agent_config = {
                'inner_composer_config': {
                    'agent_id': agent_id,
                    'seed': seed,
                    'initial_inner_state': agent_state
                },
                'agent_id': agent_id,
                'seed': seed,
                'inner_emitter': {
                    **emitter_config,
                    'embed_path': agent_path,
                },
                'division_threshold': division_threshold
            }
            agent_composer = EcoliEngineProcess(base_config)
            agent_composite = agent_composer.generate(agent_config, path=agent_path)
            if not composite:
                composite = agent_composite
            composite.processes['agents'][agent_id] = agent_composite.processes['agents'][agent_id]
            composite.topology['agents'][agent_id] = agent_composite.topology['agents'][agent_id]
        initial_state = composite.initial_state()
        # Clean up namespace for garbage collector
        del (agent_id, agent_state, agent_states, agent_path, agent_composer, 
             agent_composite, base_config, agent_config)
    else:
        agent_config = {}
        if 'initial_state_file' in config.keys():
            agent_path = ('agents', config['agent_id'])
            agent_config = {
                'inner_emitter': {
                    **emitter_config,
                    'embed_path': agent_path,
                },
            }
        composer = EcoliEngineProcess(base_config)
        composite = composer.generate(agent_config, path=agent_path)
        initial_state = composite.initial_state()
        del agent_path, composer, agent_config, base_config

    if config['spatial_environment']:
        # Merge a lattice composite for the spatial environment.
        initial_environment = environment_composite.initial_state()
        composite.merge(environment_composite)
        initial_state = deep_merge(initial_state, initial_environment)
        del environment_composite, initial_environment

    metadata = config.to_dict()
    metadata['division_threshold'] = [
        agent['cell_process'].parameters['division_threshold'] for agent in composite.processes['agents'].values()]
    metadata.pop('initial_state', None)
    metadata['git_hash'] = get_git_revision_hash()
    metadata['git_status'] = get_git_status()

    engine = Engine(
        processes=composite.processes,
        topology=composite.topology,
        initial_state=initial_state,
        experiment_id=experiment_id,
        emitter=emitter_config,
        progress_bar=config['progress_bar'],
        metadata=metadata,
        profile=config['profile'],
        initial_global_time=config.get('start_time', 0)
    )
    # Unnecessary reference to initial_state
    engine.initial_state = None
    # Tidy up namespace and free memory
    del composite, initial_state, experiment_id, emitter_config
    gc.collect()

    # Save states while running if needed
    if config["save"]:
        colony_save_states(engine, config)
    else:
        engine.update(config['total_time'])
    engine.end()

    if config['profile']:
        report_profiling(engine.stats)
    return engine


def test_run_simulation():
    # Clear the emitter's data in case it has been filled by another
    # test.
    SharedRamEmitter.saved_data.clear()
    config = SimConfig()
    spatial_config_path = os.path.join(CONFIG_DIR_PATH, 'spatial.json')
    config.update_from_json(spatial_config_path)
    config.update_from_dict({
        'total_time': 5,
        'divide': True,
        'emitter' : 'shared_ram',
        'parallel': False,
        'engine_process_reports': [
            ('listeners', 'mass'),
        ],
        'progress_bar': False,
    })
    engine = run_simulation(config)
    data = engine.emitter.get_data()

    assert min(data.keys()) == 0
    assert max(data.keys()) == 5

    assert np.all(np.array(data[0]['fields']['GLC[p]']) == 1)
    assert np.any(np.array(data[4]['fields']['GLC[p]']) != 1)
    mass_path = ('agents', '0', 'listeners', 'mass', 'cell_mass')
    assert get_in(data[4], mass_path) > get_in(data[0], mass_path)


if __name__ == '__main__':
    # config = SimConfig()
    # config.update_from_cli()
    # run_simulation(config)
    test_run_simulation()