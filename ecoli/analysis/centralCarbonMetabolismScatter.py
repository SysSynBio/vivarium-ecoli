from __future__ import absolute_import, division, print_function

import argparse
from six.moves import cPickle
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
from unum import Unum

from wholecell.utils import units, toya
from ecoli.library.sim_data import SIM_DATA_PATH
from ecoli.processes.metabolism import (
    COUNTS_UNITS,
    VOLUME_UNITS,
    TIME_UNITS,
)

FLUX_UNITS = COUNTS_UNITS / VOLUME_UNITS / TIME_UNITS

class Plot():
    """Plot fluxome data"""

    @staticmethod
    def load_toya_data(validation_data_file, sim_data_file, sim_df):
        # type: (str, str, str) -> Tuple[List[str], Unum, Unum]
        """Load fluxome data from 2010 validation data

        Arguments:
            validation_data_file: Path to cPickle with validation data.
            sim_data_file: Path to cPickle with simulation data.
            sim_df: Dataframe from ecoli.analysis.antibiotics_colony.load_data,
                must contain 'Dry mass' and 'Cell mass' columns 

        Returns:
            Tuple of reaction IDs, fluxes, standard deviations, and simulation
            reaction IDs. Fluxes and standard deviations appear in the same
            order as their associated reactions do in the reaction ID list.
            Fluxes and standard deviations are numpy arrays with units
            FLUX_UNITS. Simulation reaction IDs are ordered in the same
            order used to retrieve data in ecoli.analysis.db.get_fluxome_data
        """
        validation_data = cPickle.load(open(validation_data_file, "rb"))
        sim_data = cPickle.load(open(sim_data_file, "rb"))
        cell_density = sim_data.constants.cell_density

        cell_masses = sim_df.loc[:, "Cell mass"] * units.fg
        dry_masses = sim_df.loc[:, "Dry mass"] * units.fg

        toya_reactions = validation_data.reactionFlux.toya2010fluxes["reactionID"]
        toya_fluxes = toya.adjust_toya_data(
            validation_data.reactionFlux.toya2010fluxes["reactionFlux"],
            cell_masses,
            dry_masses,
            cell_density,
        )
        # Treat all Toya fluxes as positive (moving forward under physiological
        # conditions)
        toya_fluxes = np.abs(toya_fluxes)
        toya_stdevs = toya.adjust_toya_data(
            validation_data.reactionFlux.toya2010fluxes["reactionFluxStdev"],
            cell_masses,
            dry_masses,
            cell_density,
        )
        sim_reaction_ids = np.array(sorted(sim_data.process.metabolism.reaction_stoich))
        return toya_reactions, toya_fluxes, toya_stdevs, sim_reaction_ids

    def do_plot(self, raw_data, sim_df, simDataFile,
            validationDataFile, outFile):
        # Tool to find all reaction pathways that start with a certain set of reactants
        # and end with a certain set of products
        # type: (str, str, str, str, str, Optional[dict]) -> None
        toya_reactions, toya_fluxes, toya_stdevs, reaction_ids = Plot.load_toya_data(
            validationDataFile, simDataFile, sim_df)
        common_ids = sorted(toya_reactions.copy())
        root_to_id_indices_map = get_toya_flux_rxns(simDataFile)

        fluxes = {common_id: [] for common_id in common_ids}
        empty = ()
        for time_data in raw_data.values():       
            for agent_data in time_data['agents'].values():
                if next(iter(agent_data['fluxome'].values())) is None:
                    continue
                for common_id in common_ids:
                    # Handle cases of (potentially reversible) reactions
                    flux = 0
                    for i_rxn_id in root_to_id_indices_map.get(common_id, empty):
                        flux += agent_data['fluxome'][str(i_rxn_id)]
                    for i_rxn_id in root_to_id_indices_map.get(
                        f'{common_id} (reverse)', empty):
                        flux -= agent_data['fluxome'][str(i_rxn_id)]
                    if flux != 0:
                        fluxes[common_id].append(flux)
                        continue
                    
                    # Handle cases where two reactions are combined into a
                    # single flux (use smaller flux at each time step)
                    flux_1 = 0
                    for i_rxn_id in root_to_id_indices_map.get(
                        f'{common_id}_1', empty):
                        flux_1 += agent_data['fluxome'][str(i_rxn_id)]
                    for i_rxn_id in root_to_id_indices_map.get(
                        f'{common_id}_1 (reverse)', empty):
                        flux_1 -= agent_data['fluxome'][str(i_rxn_id)]
                    flux_2 = 0
                    for i_rxn_id in root_to_id_indices_map.get(
                        f'{common_id}_2', empty):
                        flux_2 += agent_data['fluxome'][str(i_rxn_id)]
                    for i_rxn_id in root_to_id_indices_map.get(
                        f'{common_id}_2 (reverse)', empty):
                        flux_2 -= agent_data['fluxome'][str(i_rxn_id)]
                    fluxes[common_id].append(min(flux_1, flux_2))

        all_fluxes = np.array(list(fluxes.values()))
        sim_flux_means = np.mean(all_fluxes, axis=1)
        sim_flux_stdevs = np.std(all_fluxes, axis=1)
        
        toya_flux_means = toya.process_toya_data(
            common_ids, toya_reactions, toya_fluxes)
        toya_flux_stdevs = toya.process_toya_data(
            common_ids, toya_reactions, toya_stdevs)
        
        # Include PTS system flux in pyruvate kinase flux as done in
        # parentheses next in Fig 4 of Toya 2010
        common_ids = np.array(common_ids)
        toya_flux_means[common_ids=='PEPDEPHOS-RXN'] += toya_flux_means[
            common_ids=='TRANS-RXN-157']

        correlation_coefficient = np.corrcoef(
            sim_flux_means,
            toya_flux_means.asNumber(FLUX_UNITS),
        )[0, 1]
        plt.figure()

        plt.title("Central Carbon Metabolism Flux, Pearson R = {:.2}".format(
            correlation_coefficient))
        plt.errorbar(
            toya_flux_means.asNumber(FLUX_UNITS),
            sim_flux_means,
            xerr=toya_flux_stdevs.asNumber(FLUX_UNITS),
            yerr=sim_flux_stdevs,
            fmt="o", ecolor="k"
        )
        plt.ylabel("Mean WCM Reaction Flux {}".format(FLUX_UNITS.strUnit()))
        plt.xlabel("Toya 2010 Reaction Flux {}".format(FLUX_UNITS.strUnit()))

        plt.plot(np.linspace(0, 2), np.linspace(0,2))

        plt.savefig(outFile, bbox_inches='tight')
        plt.close("all")


def get_toya_flux_rxns(simDataFile):
    sim_data = cPickle.load(open(simDataFile, "rb"))
    reaction_stoich = sim_data.process.metabolism.reaction_stoich
    reaction_stoich = {k: reaction_stoich[k] for k in sorted(reaction_stoich)}
    stoich_matrix = pd.DataFrame(list(reaction_stoich.values()))
    normal_reaction_mapping = {
        '1TRANSKETO-RXN': {
            'RIBOSE-5P[c]': -1,
            'XYLULOSE-5-PHOSPHATE[c]': -1,
            'GAP[c]': 1,
            'D-SEDOHEPTULOSE-7-P[c]': 1},
        '2OXOGLUTARATEDEH-RXN': {
            '2-KETOGLUTARATE[c]': -1,
            'SUC-COA[c]': 1,
            'CARBON-DIOXIDE[c]': 1},
        '2TRANSKETO-RXN': {
            'ERYTHROSE-4P[c]': -1,
            'XYLULOSE-5-PHOSPHATE[c]': -1,
            'FRUCTOSE-6P[c]': 1,
            'GAP[c]': 1},
        '6PFRUCTPHOS-RXN': {
            'FRUCTOSE-6P[c]': -1,
            'FRUCTOSE-16-DIPHOSPHATE[c]': 1},
        'F16ALDOLASE-RXN': {
            'FRUCTOSE-16-DIPHOSPHATE[c]': -1,
            'DIHYDROXY-ACETONE-PHOSPHATE[c]': 1,
            'GAP[c]': 1},
        'FUMHYDR-RXN': {
            'FUM[c]': -1,
            'MAL[c]': 1},
        'ISOCITDEH-RXN': {
            'THREO-DS-ISO-CITRATE[c]': -1,
            '2-KETOGLUTARATE[c]': 1,
            'CARBON-DIOXIDE[c]': 1},
        'MALATE-DEH-RXN': {
            'MAL[c]': -1,
            'OXALACETIC_ACID[c]': 1},
        'PEPCARBOX-RXN': {
            'PHOSPHO-ENOL-PYRUVATE[c]': -1,
            'OXALACETIC_ACID[c]': 1},
        'PEPDEPHOS-RXN': {
            'PHOSPHO-ENOL-PYRUVATE[c]': -1,
            'PYRUVATE[c]': 1},
        'PGLUCISOM-RXN': {
            'D-glucopyranose-6-phosphate[c]': -1,
            'FRUCTOSE-6P[c]': 1},
        'PYRUVDEH-RXN': {
            'PYRUVATE[c]': -1,
            'ACETYL-COA[c]': 1,
            'CARBON-DIOXIDE[c]': 1},
        'RIB5PISOM-RXN': {
            'RIBULOSE-5P[c]': -1,
            'RIBOSE-5P[c]': 1},
        'RIBULP3EPIM-RXN': {
            'RIBULOSE-5P[c]': -1,
            'XYLULOSE-5-PHOSPHATE[c]': 1},
        'RXN-9952': {
            'CPD-2961[c]': -1,
            'RIBULOSE-5P[c]': 1,
            'CARBON-DIOXIDE[c]': 1},
        'SUCCINATE-DEHYDROGENASE-UBIQUINONE-RXN-SUC/UBIQUINONE-8//FUM/CPD-9956.31.': {
            'SUC[c]': -1,
            'FUM[c]': 1},
        'TRANSALDOL-RXN': {
            'D-SEDOHEPTULOSE-7-P[c]': -1,
            'GAP[c]': -1,
            'ERYTHROSE-4P[c]': 1,
            'FRUCTOSE-6P[c]': 1},
        'TRIOSEPISOMERIZATION-RXN': {
            'DIHYDROXY-ACETONE-PHOSPHATE[c]': -1,
            'GAP[c]': 1}
    }
    rxn_ids = {}
    for rxn, stoich in normal_reaction_mapping.items():
        # Boolean for forward reaction
        condition = None
        for mol, coeff in stoich.items():
            if condition is None:
                condition = (stoich_matrix[mol]==coeff)
            else:
                condition = condition & (stoich_matrix[mol]==coeff)
        rxn_ids[rxn] = np.where(condition)[0]

        # Boolean for reverse reaction
        condition = None
        for mol, coeff in stoich.items():
            if condition is None:
                condition = stoich_matrix[mol]==-coeff
            else:
                condition = condition & (stoich_matrix[mol]==-coeff)
        rxn_ids[f'{rxn} (reverse)'] = np.where(condition)[0]
    
    step_skip_rxn_mapping = {
        'GAPOXNPHOSPHN-RXN': {
            # Toya goes directly from G3P (GAP in model) to 3-PG (G3P)
            1: {'GAP[c]': -1, 'DPG[c]': 1,},
            2: {'DPG[c]': -1, 'G3P[c]': 1}},            
        'CITSYN-RXN': {
            # Toya goes from OAA directly to isocitrate
            1: {'OXALACETIC_ACID[c]': -1,
                'ACETYL-COA[c]': -1,
                'CIT[c]': 1},
            2: {'CIT[c]': -1,
                'THREO-DS-ISO-CITRATE[c]': 1}},
        '2PGADEHYDRAT-RXN': {
            # Toya goes directly from 3-PG (G3P in model) to PEP
            1: {'G3P[c]': -1,
                '2-PG[c]': 1},
            2: {'2-PG[c]': -1,
                'PHOSPHO-ENOL-PYRUVATE[c]': 1}}
    }
    for rxn, sub_rxns in step_skip_rxn_mapping.items():
        for i, sub_rxn in sub_rxns.items():
            # Boolean for forward reaction
            condition = None
            for mol, coeff in sub_rxn.items():
                if condition is None:
                    condition = (stoich_matrix[mol]==coeff)
                else:
                    condition = condition & (stoich_matrix[mol]==coeff)
            rxn_ids[f'{rxn}_{i}'] = np.where(condition)[0]

            # Boolean for reverse reaction
            condition = None
            for mol, coeff in sub_rxn.items():
                if condition is None:
                    condition = stoich_matrix[mol]==-coeff
                else:
                    condition = condition & (stoich_matrix[mol]==-coeff)
            rxn_ids[f'{rxn}_{i} (reverse)'] = np.where(condition)[0]

    mix_and_match_rxns = {
        # Mix and match 1 starting reactant and 1 product
        'GLU6PDEHYDROG-RXN': {
            'reactants': [
                'D-glucopyranose-6-phosphate[c]',
                'ALPHA-GLC-6-P[c]',
                'GLC-6-P[c]',
            ],
            'products': ['D-6-P-GLUCONO-DELTA-LACTONE[c]']
        },
        'TRANS-RXN-157': {
            'reactants': [
                'Glucopyranose[p]',
                'Glucopyranose[c]',
                'ALPHA-GLUCOSE[p]',
                'ALPHA-GLUCOSE[c]',
                'GLC[p]',
                'GLC[c]'
            ],
            'products': [
                'D-glucopyranose-6-phosphate[c]',
                'ALPHA-GLC-6-P[c]',
                'GLC-6-P[c]',
            ]
        }
    }
    for rxn, stoich in mix_and_match_rxns.items():
        rxn_ids[rxn] = []
        rxn_ids[f'{rxn} (reverse)'] = []
        for reactant in stoich['reactants']:
            for product in stoich['products']:
                # Boolean for forward reaction
                condition = ((stoich_matrix[reactant]==-1)
                    & (stoich_matrix[product]==1))
                rxn_ids[rxn].extend(np.where(condition)[0].tolist())

                # Boolean for reverse reaction
                condition = ((stoich_matrix[reactant]==1)
                    & (stoich_matrix[product]==-1))
                rxn_ids[f'{rxn} (reverse)'].extend(np.where(condition)[0].tolist())
    
    rxn_ids = {k: v for k, v in rxn_ids.items() if len(v) > 0}
    return rxn_ids

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--raw_data',
        '-r',
        help='Path to saved pickle from ecoli.analysis.db.get_fluxome_data',
        required=True
    )
    parser.add_argument(
        '--sim_df',
        '-d',
        help='Path to dataframe from ecoli.analysis.antibiotics_colony.load_data '
            'must contain "Dry mass" and "Cell mass" columns.',
        required=True
    )
    parser.add_argument(
        '--out_file',
        '-o',
        help='Path to output file.',
        default='out/analysis/centralCarbonMetabolismScatter.svg'
    )
    parser.add_argument(
        '--sim_data',
        '-s',
        help='Path to sim_data file.',
        default=SIM_DATA_PATH
    )
    parser.add_argument(
        '--validation_data',
        '-v',
        help='Path to validation_data file.',
        default='reconstruction/sim_data/kb/validationData.cPickle'
    )
    args = parser.parse_args()

    with open(args.raw_data, 'rb') as f:
        raw_data = cPickle.load(f)
    with open(args.sim_df, 'rb') as f:
        sim_df = cPickle.load(f)

    plot = Plot()
    plot.do_plot(raw_data, sim_df, args.sim_data,
        args.validation_data, args.out_file)
