from vivarium.core.composer import Composer
from vivarium.core.engine import Engine
from vivarium.core.emitter import timeseries_from_data
from vivarium.library.units import units
from vivarium.plots.simulation_output import plot_variables
from vivarium.processes.timeline import TimelineProcess

from ecoli.processes.antibiotics.exchange_aware_bioscrape import ExchangeAwareBioscrape
from ecoli.processes.antibiotics.permeability import (
    Permeability, CEPH_OMPC_CON_PERM, CEPH_OMPF_CON_PERM, OUTER_BILAYER_CEPH_PERM, TET_OMPF_CON_PERM, OUTER_BILAYER_TET_PERM,
    INNER_BILAYER_TET_PERM, SA_AVERAGE
)
from ecoli.processes.antibiotics.permeability import (
    Permeability, CEPH_OMPC_CON_PERM, CEPH_OMPF_CON_PERM, OUTER_BILAYER_CEPH_PERM, TET_OMPF_CON_PERM, OUTER_BILAYER_TET_PERM,
    INNER_BILAYER_TET_PERM, SA_AVERAGE
)
from ecoli.processes.antibiotics.nonspatial_environment import (
    NonSpatialEnvironment
)
from ecoli.processes.shape import Shape

INITIAL_ENVIRONMENT_CEPH = 0.1239 * units.mM
INITIAL_ENVIRONMENT_TET = 0.1239 * units.mM
BETA_LACTAM_KEY = 'cephaloridine'
TET_KEY = 'tetracycline'


class SimpleAntibioticsCell(Composer):
    '''
    This composite includes the minimum amount of steps/processes needed to
    simulate the diffusion of a beta-lactam and tetracycline into E. coli.
    '''

    default = {
        'ext_periplasm_bioscrape': {},
        'periplasm_cytoplasm_bioscrape': {},
        'timeline': {},
        'shape': {},
        'nonspatial_environment': {},
        'outer_permeability': {},
        'inner_permeability': {}
    }

    def generate_processes(self, config):
        ext_periplasm_bioscrape = ExchangeAwareBioscrape(config['ext_periplasm_bioscrape'])
        periplasm_cytoplasm_bioscrape = ExchangeAwareBioscrape(config['periplasm_cytoplasm_bioscrape'])
        timeline = TimelineProcess(config['timeline'])
        return {
            'ext_periplasm_bioscrape': ext_periplasm_bioscrape,
            'periplasm_cytoplasm_bioscrape': periplasm_cytoplasm_bioscrape,
            'timeline': timeline
        }

    def generate_steps(self, config):
        nonspatial_environment = NonSpatialEnvironment(config['nonspatial_environment'])
        shape = Shape(config['shape'])
        outer_permeability = Permeability(config['outer_permeability'])
        inner_permeability = Permeability(config['inner_permeability'])
        return {
            'nonspatial_environment': nonspatial_environment,
            'shape': shape,
            'outer_permeability': outer_permeability,
            'inner_permeability': inner_permeability
        }

    def generate_topology(self, config=None):
        boundary_path = config['boundary_path']
        topology = {
            'ext_periplasm_bioscrape': {
                'delta_species': ('delta_concs',),
                'exchanges': boundary_path + ('exchanges',),
                'external': boundary_path + ('external',),
                'globals': ('global',),
                'rates': ('kinetic_parameters',),
                'species': ('concs',),
            },
            'periplasm_cytoplasm_bioscrape': {
                'delta_species': ('delta_concs',),
                'exchanges': boundary_path + ('exchanges',),
                'external': boundary_path + ('external',),
                'globals': ('global',),
                'rates': ('kinetic_parameters',),
                'species': ('concs',),
            },
            'timeline': {
                'global': ('global',),  # The global time is read here
                'porins': ('bulk',),  # This port is based on the declared timeline
            },
            'shape': {
                'cell_global': boundary_path,
                'periplasm_global': ('periplasm',),
                'cytosol_global': ('cytosol',),
                'listener_cell_mass': ('mass_listener', 'dry_mass'),
            },
            'nonspatial_environment': {
                'external': boundary_path + ('external',),
                'exchanges': boundary_path + ('exchanges',),
                'fields': ('environment', 'fields',),
                'dimensions': ('environment', 'dimensions'),
                'global': ('global',),
            },
            'outer_permeability': {
                'porins': ('bulk',),
                'permeabilities': ('kinetic_parameters',),
                'surface_area': boundary_path + ('surface_area',)
            },
            'inner_permeability': {
                'porins': ('bulk',),
                'permeabilities': ('kinetic_parameters',),
                'surface_area': boundary_path + ('surface_area',)
            },
        }
        return topology


def demo():
    sim_time = 100
    timeline = []
    for i in range(10):
        timeline.append(
            (i, {
                ('porins', 'CPLX0-7533[o]'):  5000 + ((i + 2) * 500),
                ('porins', 'CPLX0-7534[o]'):  5000 + ((i + 2) * 500),
            },
             )
        )

    config = {
        'boundary_path': ('boundary',),
        'ext_periplasm_bioscrape': {
            'sbml_file': 'data/ext_periplasm_sbml.xml',
        },
        'periplasm_cytoplasm_bioscrape': {
            'sbml_file': 'data/periplasm_cytoplasm_sbml.xml',
        },
        'timeline': {
            'time_step': 1.0,
            'timeline': timeline,
        },
        'shape': {},
        'nonspatial_environment': {
            'concentrations': {
                BETA_LACTAM_KEY: INITIAL_ENVIRONMENT_CEPH,
                TET_KEY: INITIAL_ENVIRONMENT_TET
            },
            'internal_volume': 1.2,  # * units.fL,
            'env_volume': 1 * units.mL,
        },
        'outer_permeability': {
            'porin_ids': ['CPLX0-7533[o]', 'CPLX0-7534[o]'],
            'diffusing_molecules': {
                'cephaloridine': {
                    'concentration_perm': {
                        'CPLX0-7533[o]': CEPH_OMPC_CON_PERM,
                        'CPLX0-7534[o]': CEPH_OMPF_CON_PERM
                    },
                    'bilayer_perm': OUTER_BILAYER_CEPH_PERM
                },
                'tetracycline': {
                    'concentration_perm': {
                        'CPLX0-7534[o]': TET_OMPF_CON_PERM,
                    },
                    'bilayer_perm': OUTER_BILAYER_TET_PERM
                },
            },
        },
        'inner_permeability': {
            'porin_ids': [],
            'diffusing_molecules': {
                'tetracycline': {
                    'concentration_perm': {},
                    'bilayer_perm': INNER_BILAYER_TET_PERM
                }
            },
        },
    }

    composite = SimpleAntibioticsCell(config).generate()
    initial_state = composite.initial_state()
    initial_state['boundary']['surface_area'] = SA_AVERAGE
    initial_state['bulk'] = {}
    initial_state['bulk']['CPLX0-7533[o]'] = 6000
    initial_state['bulk']['CPLX0-7534[o]'] = 6000
    import ipdb; ipdb.set_trace()

    sim = Engine(composite=composite, initial_state=initial_state)
    sim.update(sim_time)
    timeseries_data = timeseries_from_data(sim.emitter.get_data())
    plot_variables(
        timeseries_data,
        variables=[
            ('concs', 'cephaloridine_environment'),
            ('concs', 'cephaloridine_periplasm'),
            ('concs', 'cephaloridine_hydrolyzed'),
            ('concs', 'tetracycline_environment'),
            ('concs', 'tetracycline_periplasm'),
            ('concs', 'tetracycline_cytoplasm'),
        ],
        out_dir='out',
        filename='antibiotics_simple'
    )


if __name__ == '__main__':
    demo()
