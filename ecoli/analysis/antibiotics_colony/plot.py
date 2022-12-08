import argparse
from concurrent.futures import ProcessPoolExecutor
from functools import partial
import matplotlib
import matplotlib.pyplot as plt

from ecoli.analysis.antibiotics_colony.plot_utils import prettify_axis
plt.rcParams['svg.fonttype'] = 'none'
plt.rcParams['font.family'] = 'Arial'
import numpy as np
import os
import pandas as pd
import pickle
import seaborn as sns
from tqdm import tqdm

from vivarium.library.dict_utils import get_value_from_path

from ecoli.analysis.db import access_counts, deserialize_and_remove_units
from ecoli.analysis.antibiotics_colony.timeseries import (
    plot_field_snapshots,
    plot_tag_snapshots,
    plot_timeseries)
from ecoli.analysis.antibiotics_colony.distributions import (
    plot_final_distributions,
    plot_death_distributions)
from ecoli.analysis.antibiotics_colony.validation import (
    plot_colony_growth_rates,
    plot_vs_distance_from_center,
    plot_synth_prob_fc,
    plot_mrna_fc,
    plot_protein_synth_inhib,
    plot_mass_fraction
)
from ecoli.analysis.antibiotics_colony import (
    DE_GENES, MAX_TIME, SPLIT_TIME, restrict_data,
    COUNTS_PER_FL_TO_NANOMOLAR)

# Mapping: Condition -> Seed -> Experiment ID
EXPERIMENT_ID_MAPPING = {
    'Glucose': {
        0: '',
        100: '',
        10000: '',
    },
    'Tetracycline (1.5 mg/L)': {
        0: '2022-12-06_18-03-41_270533+0000',
        100: '2022-12-06_18-04-09_769516+0000',
        10000: '2022-12-06_18-04-37_780937+0000'
    },
    'Tetracycline (4 mg/L)': {
        0: '2022-12-06_18-25-13_806449+0000',
    },
    'Tetracycline (2 mg/L)': {
        0: '2022-12-06_18-24-49_284601+0000',
    },
    'Tetracycline (1 mg/L)': {
        0: '2022-12-06_19-15-28_403400+0000',
    },
    'Tetracycline (0.5 mg/L)': {
        0: '2022-12-06_19-15-55_553165+0000',
    },
    'Ampicillin (2 mg/L)': {
        0: '',
        100: '',
        10000: ''
    },
    'Ampicillin (4 mg/L)': {
        0: '',
    },
    'Ampicillin (1.5 mg/L)': {
        0: '',
    },
    'Ampicillin (1 mg/L)': {
        0: '',
    },
    'Ampicillin (0.5 mg/L)': {
        0: '',
    },
}


PATHS_TO_LOAD = {
    'Dry mass': ('listeners', 'mass', 'dry_mass'),
    'Protein mass': ('listeners', 'mass', 'proteinMass'),
    'Dry mass fold change': ('listeners', 'mass', 'dryMassFoldChange'),
    'Protein mass fold change': ('listeners', 'mass', 'proteinMassFoldChange'),
    'RNA mass fold change': ('listeners', 'mass', 'rnaMassFoldChange'),
    'Small molecule fold change': ('listeners', 'mass', 'smallMoleculeFoldChange'),
    'Cell mass': ('listeners', 'mass', 'cell_mass'),
    'Water mass': ('listeners', 'mass', 'water_mass'),
    'RNA mass': ('listeners', 'mass', 'rnaMass'),
    'rRNA mass': ('listeners', 'mass', 'rRnaMass'),
    'tRNA mass': ('listeners', 'mass', 'tRnaMass'),
    'mRNA mass': ('listeners', 'mass', 'mRnaMass'),
    'DNA mass': ('listeners', 'mass', 'dnaMass'),
    'Small molecule mass': ('listeners', 'mass', 'smallMoleculeMass'),
    'Projection mass': ('listeners', 'mass', 'projection_mass'),
    'Cytosol mass': ('listeners', 'mass', 'cytosol_mass'),
    'Extracellular mass': ('listeners', 'mass', 'extracellular_mass'),
    'Flagellum mass': ('listeners', 'mass', 'flagellum_mass'),
    'Membrane mass': ('listeners', 'mass', 'membrane_mass'),
    'Outer membrane mass': ('listeners', 'mass', 'outer_membrane_mass'),
    'Periplasm mass': ('listeners', 'mass', 'periplasm_mass'),
    'Pilus mass': ('listeners', 'mass', 'pilus_mass'),
    'Inner membrane mass': ('listeners', 'mass', 'inner_membrane_mass'),
    'Growth rate': ('listeners', 'mass', 'growth'),
    'AcrAB-TolC': ('bulk', 'TRANS-CPLX-201[m]'),
    'Periplasmic tetracycline': ('periplasm', 'concentrations', 'tetracycline'),
    'Cytoplasmic tetracycline': ('cytoplasm', 'concentrations', 'tetracycline'),
    'Periplasmic ampicillin': ('periplasm', 'concentrations', 'ampicillin'),
    'Active MarR': ('bulk', 'CPLX0-7710[c]'),
    'Inactive MarR': ('bulk', 'marR-tet[c]'),
    'micF-ompF duplex': ('bulk', 'micF-ompF[c]'),
    'micF RNA': ('bulk', 'MICF-RNA[c]',),
    '30S subunit': ('bulk', 'CPLX0-3953[c]'),
    'Inactive 30S subunit': ('bulk', 'CPLX0-3953-tetracycline[c]'),
    'Active ribosomes': ('listeners', 'aggregated', 'active_ribosome_len'),
    'Active RNAP': ('listeners', 'aggregated', 'active_RNAP_len'),
    'Outer tet. permeability (cm/s)': ('kinetic_parameters', 'outer_tetracycline_permeability'),
    'Murein tetramer': ('bulk', 'CPD-12261[p]'),
    'PBP1a complex': ('bulk', 'CPLX0-7717[m]'),
    'PBP1a mRNA': ('mrna', 'EG10748_RNA'),
    'PBP1b alpha complex': ('bulk', 'CPLX0-3951[i]'),
    'PBP1b mRNA': ('mrna', 'EG10605_RNA'),
    'PBP1b gamma complex': ('bulk', 'CPLX0-8300[c]'),
    'Wall cracked': ('wall_state', 'cracked'),
    'AmpC monomer': ('monomer', 'EG10040-MONOMER'),
    'ampC mRNA': ('mrna', 'EG10040_RNA'),
    'Extension factor': ('wall_state', 'extension_factor'),
    'Wall columns': ('wall_state', 'lattice_cols'),
    'Unincorporated murein': ('murein_state', 'unincorporated_murein'),
    'Incorporated murein': ('murein_state', 'incorporated_murein'),
    'Shadow murein': ('murein_state', 'shadow_murein'),
    'Max hole size': ('listeners', 'hole_size_distribution'),
    'Porosity': ('listeners', 'porosity'),
    'Active fraction PBP1a': ('pbp_state', 'active_fraction_PBP1A'),
    'Active fraction PBP1b': ('pbp_state', 'active_fraction_PBP1B'),
    'Boundary': ('boundary',),
    'Volume': ('listeners', 'mass', 'volume'),
    'Total mRNA': ('total_mrna',)
}

for gene_data in DE_GENES[['Gene name', 'id', 'monomer_ids']].values:
    if gene_data[0] != 'MicF':
        PATHS_TO_LOAD[f'{gene_data[0]} mRNA'] = ('mrna', gene_data[1])
        PATHS_TO_LOAD[f'{gene_data[0]} synth prob'] = ('rna_synth_prob',
            gene_data[1])
    gene_data[2] = eval(gene_data[2])
    if len(gene_data[2]) > 0:
        monomer_name = gene_data[0][0].upper() + gene_data[0][1:]
        PATHS_TO_LOAD[f'{monomer_name} monomer'] = (
            'monomer', gene_data[2][0])
# Housekeeping gene GAPDH for normalization between samples
PATHS_TO_LOAD['GAPDH mRNA'] = ('mrna', 'EG10367_RNA')
PATHS_TO_LOAD['GAPDH synth prob'] = ('rna_synth_prob', 'EG10367_RNA')
PATHS_TO_LOAD['GAPDH monomer'] = ('monomer', 'GAPDH-A-MONOMER')
# RNAP monomers and mRNAs
PATHS_TO_LOAD['rpoA mRNA'] = ('mrna', 'EG10893_RNA')
PATHS_TO_LOAD['rpoB mRNA'] = ('mrna', 'EG10894_RNA')
PATHS_TO_LOAD['rpoC mRNA'] = ('mrna', 'EG10895_RNA')
PATHS_TO_LOAD['RpoA monomer'] = ('monomer', 'EG10893-MONOMER')
PATHS_TO_LOAD['RpoB monomer'] = ('monomer', 'RPOB-MONOMER')
PATHS_TO_LOAD['RpoC monomer'] = ('monomer', 'RPOC-MONOMER')


def make_figure_1(data, metadata):
    # Generational (ompF) vs sub-generational (marR) expression (Fig 1a)
    columns_to_plot = {
        'ompF mRNA': '0.4',
        'marR mRNA': (0, 0.4, 1),
        'OmpF monomer': '0.4',
        'MarR monomer': (0, 0.4, 1)}
    agent_ids = data.loc[data.loc[:, 'Time']==MAX_TIME, 'Agent ID']
    # Arbitrarily pick a surviving agent to plot trace of
    fig, axes = plt.subplots(2, 2, sharex='col', figsize=(6, 6))
    axes = np.ravel(axes)
    highlight_agent = '011001001'
    print(f'Highlighted agent: {highlight_agent}')
    plot_timeseries(
        data=data, axes=axes, columns_to_plot=columns_to_plot,
        highlight_lineage=highlight_agent, background_lineages=False)
    axes[0].set_xlabel(None)
    axes[1].set_xlabel(None)
    # Put gene name on top and remove superfluous axes labels
    gene_1 = axes[0].get_ylabel().split(' ')[0]
    gene_2 = axes[1].get_ylabel().split(' ')[0]
    axes[0].set_ylabel('mRNA\n(counts)')
    axes[2].set_ylabel('Monomer\n(counts)')
    axes[0].set_title(f'Exponential: {gene_1}', fontsize=10)
    axes[1].set_title(f'Sub-generational: {gene_2}', fontsize=10)
    axes[0].yaxis.set_label_coords(-0.3, 0.5)
    axes[2].yaxis.set_label_coords(-0.3, 0.5)
    axes[1].yaxis.label.set_visible(False)
    axes[3].yaxis.label.set_visible(False)
    axes[0].xaxis.set_visible(False)
    axes[0].spines.bottom.set_visible(False)
    axes[1].xaxis.set_visible(False)
    axes[1].spines.bottom.set_visible(False)
    for ax in axes:
        [item.set_fontsize(8) for item in ax.get_xticklabels()]
        [item.set_fontsize(8) for item in ax.get_yticklabels()]
        ax.xaxis.label.set_fontsize(9)
        ax.yaxis.label.set_fontsize(9)
        ax.xaxis.set_label_coords(0.5, -0.2)
    ax.tick_params(axis='both', which='major')
    fig.set_size_inches(4, 3)
    plt.draw()
    plt.tight_layout()
    plt.subplots_adjust(wspace=0.2, hspace=0.3)
    os.makedirs('out/analysis/paper_figures/1a/', exist_ok=True)
    plt.savefig(f'out/analysis/paper_figures/1a/fig_1a_{highlight_agent}.svg',
        bbox_inches='tight')
    plt.close()
    print('Done with Figure 1A.')


def make_figure_2(data, metadata):
    # Overview of glucose data for seed 0 (can put other seeds in supp.)
    final_timestep = data.loc[data.loc[:, 'Time']==MAX_TIME, :]
    agent_ids = final_timestep.loc[:, 'Agent ID']
    highlight_agent = agent_ids[100]
    print(f'Highlighted agent: {highlight_agent}')
    # 5 equidistant snapshot plots in a row (Fig. 2b)
    plot_field_snapshots(
        data=data, metadata=metadata, highlight_lineage=highlight_agent,
        highlight_color=(0, 0.4, 1), min_pct=0.8, colorbar_decimals=2)

    # Set up subplot layout for timeseries plots
    fig = plt.figure()
    gs = fig.add_gridspec(3, 4)
    axes = [fig.add_subplot(gs[0, :])]
    for i in range(4):
        axes.append(fig.add_subplot(gs[2, i]))
    for i in range(4):
        axes.append(fig.add_subplot(gs[1, i], sharex=axes[i+1]))

    columns_to_plot = {
        'Dry mass': (0, 0.4, 1),
    }
    plot_timeseries(
        data=data, axes=axes, columns_to_plot=columns_to_plot,
        highlight_lineage=highlight_agent)
    columns_to_plot = {
        'OmpF monomer': (0, 0.4, 1),
        'MarR monomer': (0, 0.4, 1),
        'AmpC monomer': (0, 0.4, 1),
        'TolC monomer': (0, 0.4, 1),
        'ompF mRNA': (0, 0.4, 1),
        'marR mRNA': (0, 0.4, 1),
        'ampC mRNA': (0, 0.4, 1),
        'tolC mRNA': (0, 0.4, 1),
    }
    plot_timeseries(
        data=data, axes=axes[1:], columns_to_plot=columns_to_plot,
        highlight_lineage=highlight_agent, conc=True)
    # Add more regularly spaced tick marks to top row
    time_ticks = axes[0].get_xticks()
    new_ticks = np.arange(1, np.ceil(time_ticks[1]), 1).astype(int)
    # No need for tick at 7 since final tick is 7.2
    new_ticks = new_ticks[new_ticks != 7].tolist()
    time_ticks = [0] + new_ticks + [time_ticks[1]]
    axes[0].set_xticks(ticks=time_ticks, labels=time_ticks)
    # Put gene name on top and remove superfluous axes labels
    gene = axes[1].get_ylabel().split(' ')[0]
    axes[0].set_ylabel('Dry mass (fg)')
    axes[5].set_title(gene, fontsize=12, fontweight='bold')
    axes[5].set_ylabel('mRNA (nM)')
    axes[1].set_ylabel('Protein (nM)')
    for i in range(2, 5):
        gene = axes[i].get_ylabel().split(' ')[0]
        axes[i].yaxis.label.set_visible(False)
        axes[4+i].set_title(gene, fontsize=12, fontweight='bold')
        axes[4+i].yaxis.label.set_visible(False)
    for ax in axes[5:]:
        ax.xaxis.set_visible(False)
        ax.spines.bottom.set_visible(False)
    for ax in axes:
        [item.set_fontsize(8) for item in ax.get_xticklabels()]
        [item.set_fontsize(8) for item in ax.get_yticklabels()]
        ax.xaxis.label.set_fontsize(10)
        ax.yaxis.label.set_fontsize(10)
        ax.tick_params(axis='both', which='major')
    fig.set_size_inches(7, 4)
    plt.tight_layout()
    plt.subplots_adjust(hspace=0.35, wspace=0.45)
    for ax in axes[1:]:
        ax.xaxis.set_label_coords(0.5, -0.3)
        left, bottom, width, height = ax.get_position().bounds
        ax.set_position((left, bottom-0.15, width, height))
    left, bottom, width, height = axes[0].get_position().bounds
    axes[0].set_position((left, bottom+0.03, width, height))
    axes[0].xaxis.set_label_coords(0.5, -0.3)
    axes[0].yaxis.set_label_coords(-0.09, 0.5)
    axes[5].yaxis.set_label_coords(-0.5, 0.5)

    # Prettify axes (moving axis titles in to save space)
    for ax in axes[1:5]:
        xmin, xmax = ax.get_xlim()
        ax.set_xticks([(xmin + xmax) / 2], labels=[ax.get_xlabel()], minor=True)
        ax.set_xlabel(None)
        ax.tick_params(
            which="minor",
            width=0,
            length=ax.xaxis.get_major_ticks()[0].get_tick_padding(),
            labelsize=10
        )
    # for ax in (axes[0], axes[1], axes[5]):
    #     ymin, ymax = ax.get_ylim()
    #     ax.set_yticks([(ymin + ymax) / 2], labels=[ax.get_ylabel()], minor=True)
    #     ax.yaxis.get_minor_ticks()[0].label.set(rotation=90, va="center")
    #     ax.set_ylabel(None)
    #     ax.tick_params(
    #         which="minor",
    #         width=0,
    #         length=ax.xaxis.get_major_ticks()[0].get_tick_padding(),
    #         labelsize=10
    #     )

    plt.savefig('out/analysis/paper_figures/fig_2c_timeseries.svg',
        bbox_inches='tight')
    plt.close()
    print('Done with Figure 2.')


def plot_exp_growth_rate(data, metadata):
    grouped_agents = data.groupby(['Condition', 'Agent ID'])
    new_data = []
    active_ribo_concs = []
    growth_rates = []
    tet_concs = []
    for _, agent_data in grouped_agents:
        delta_t = np.diff(agent_data.loc[:, 'Time'], append=0)
        if len(delta_t) < 2:
            continue
        delta_t[-1] = delta_t[-2]
        dry_mass = agent_data.loc[:, 'Dry mass']
        mass_ratio = dry_mass[1:].to_numpy() / dry_mass[:-1].to_numpy()
        mass_ratio = np.append(mass_ratio, mass_ratio[-1])
        agent_data['Doubling rate'] = np.log2(mass_ratio) / delta_t * 3600
        new_data.append(agent_data)
        active_ribo_concs.append((agent_data.loc[:, 'Active ribosomes'] /
            agent_data.loc[:, 'Volume']).mean() *
            COUNTS_PER_FL_TO_NANOMOLAR / 1000)
        growth_rates.append(agent_data.loc[:, 'Doubling rate'].mean())
        tet_concs.append(agent_data.loc[:, 'Cytoplasmic tetracycline'].mean() * 1000)
    data = pd.concat(new_data)
    plt.scatter(active_ribo_concs, growth_rates, alpha=0.5, c=tet_concs)
    sns.despine(offset=0.1, trim=True)
    cbar = plt.colorbar()
    cbar.ax.set_label('Tetracycline (cytoplasm, uM)')
    plt.xlabel('Active ribosomes (mM)')
    plt.ylabel('Doubling rate (1/hr)')
    plt.tight_layout()
    plt.savefig('out/analysis/paper_figures/growth_rate_variation.svg')
    plt.close()
    
    # Get median glucose growth rate at each timestep
    glucose_data = data.loc[data.loc[:, 'Condition']=='Glucose', :]
    med_growth_rate = glucose_data.loc[:, ['Doubling rate', 'Time']].groupby(
        'Time').median()
    fc_col = 'Growth rate\n($\mathregular{log_2}$ fold change)'
    data[fc_col] = data.loc[:, 'Doubling rate']

    # Get log 2 fold change over median glucose growth rate at each timestep
    for time in med_growth_rate.index:
        data.loc[data.loc[:, 'Time']==time, fc_col] = data.loc[data.loc[
            :, 'Time']==time, fc_col] / med_growth_rate.loc[time, 'Doubling rate']
    data.loc[:, fc_col] = np.log2(data.loc[:, fc_col])
    # Set up custom divergent colormap
    cmp = matplotlib.colors.LinearSegmentedColormap.from_list(
        'divergent', [(0, 0.4, 1), (1, 1, 1), (0.678, 0, 0.125)])
    norm = matplotlib.colors.Normalize(vmin=-2.5, vmax=2.5)
    plot_tag_snapshots(
        data=data, metadata=metadata, tag_colors={fc_col: {
            'cmp': cmp, 'norm': norm}}, snapshot_times=np.array([
            1.9, 3.2, 4.5, 5.8, 7.1]) * 3600, show_membrane=True)


def plot_raw_growth_rate(data, metadata):
    # Fill in zeros in growth rate with growth at next timestep
    zero_not_max = (data.loc[:, 'Growth rate']==0) & (data.loc[:, 'Time']<MAX_TIME)
    next_timestep = np.append([False], zero_not_max[:-1])
    data.loc[zero_not_max, 'Growth rate'] = data.loc[
        next_timestep, 'Growth rate'].to_numpy()
    # Fill in zero growth at final timestep with growth at previous timestep
    zero_max = (data.loc[:, 'Growth rate']==0) & (data.loc[:, 'Time']==MAX_TIME)
    previous_timestep = np.append(zero_max[1:], [False])
    data.loc[zero_max, 'Growth rate'] = data.loc[
        previous_timestep, 'Growth rate'].to_numpy()

    # Get median glucose growth rate at each timestep
    glucose_data = data.loc[data.loc[:, 'Condition']=='Glucose', :]
    med_growth_rate = glucose_data.loc[:, ['Growth rate', 'Time']].groupby(
        'Time').median()
    fc_col = 'Growth rate\n($\mathregular{log_2}$ fold change)'
    data[fc_col] = data.loc[:, 'Growth rate']

    # Get log 2 fold change over median glucose growth rate at each timestep
    for time in med_growth_rate.index:
        data.loc[data.loc[:, 'Time']==time, fc_col] = data.loc[data.loc[
            :, 'Time']==time, fc_col] / med_growth_rate.loc[time, 'Growth rate']
    data.loc[:, fc_col] = np.log2(data.loc[:, fc_col])
    # Set up custom divergent colormap
    cmp = matplotlib.colors.LinearSegmentedColormap.from_list(
        'divergent', [(0, 0.4, 1), (1, 1, 1), (0.678, 0, 0.125)])
    norm = matplotlib.colors.Normalize(vmin=-2.5, vmax=2.5)
    plot_tag_snapshots(
        data=data, metadata=metadata, tag_colors={fc_col: {
            'cmp': cmp, 'norm': norm}}, snapshot_times=np.array([
            1.9, 3.2, 4.5, 5.8, 7.1]) * 3600, show_membrane=True)


def make_figure_3(data, metadata):
    # plot_mass_fraction(data)
    fig, ax = plt.subplots(1, 1, figsize=(3, 3))
    plot_colony_growth_rates(data, ax)
    ax.legend(labels=['0', '0.5', '1', '1.5', '2', '4'], frameon=False,
        title='Tetracycline\n(mg/L)', fontsize=8, title_fontsize=8)
    plt.tight_layout()
    fig.savefig('out/analysis/paper_figures/tet_growth_rate.svg')
    plt.close()

    data = data.loc[data.loc[:, 'Time']<=MAX_TIME, :]
    data = data.sort_values(['Condition', 'Agent ID', 'Time'])

    data = plot_exp_growth_rate(data, metadata)
    # data = plot_raw_growth_rate(data, metadata)

    # Top row of plots show short-term changes to tet. exposure
    # Filter data to only include 150 seconds before and after
    glucose_mask = ((data.loc[:, 'Time'] >= 11400) &
        (data.loc[:, 'Time'] <= SPLIT_TIME) &
        (data.loc[:, 'Condition'] == 'Glucose'))
    tet_mask = ((data.loc[:, 'Time'] >= SPLIT_TIME) &
        (data.loc[:, 'Time'] <= 11700) &
        (data.loc[:, 'Condition'] == 'Tetracycline (1.5 mg/L)'))
    transition_data = data.loc[glucose_mask | tet_mask, :]
    # Convert tetracycline concentrations to uM
    transition_data.loc[:, 'Periplasmic tetracycline'] *= 1000
    transition_data.loc[:, 'Cytoplasmic tetracycline'] *= 1000
    fig, axes = plt.subplots(1, 3, figsize=(7, 3))
    short_term_columns = {
        'Periplasmic tetracycline': (False, 0),
        'Cytoplasmic tetracycline': (False, 1),
        'Active ribosomes': (True, 2),
    }
    for column, (conc, ax_idx) in short_term_columns.items():
        plot_timeseries(
            data=transition_data,
            axes=[axes.flat[ax_idx]],
            columns_to_plot={column: (0, 0.4, 1)},
            highlight_lineage='median',
            filter_time=False,
            background_alpha=0.5,
            background_linewidth=0.3,
            conc=conc)
    for ax in axes.flat:
        ylim = ax.get_ylim()
        ax.set_yticks(np.round(ylim, 0).astype(int))
        ax.set_xlabel(None)
        # Mark minutes since tetracycline addition
        ax.set_xticks(ticks=[11430/3600, 11490/3600, 11550/3600,
            11610/3600, 11670/3600], labels=[-2, -1, 0, 1, 2])
        ax.spines.bottom.set(bounds=(11400/3600, 11700/3600), linewidth=1,
            visible=True, color=(0, 0, 0), alpha=1)
        ylabel = ax.get_ylabel()
        ax.set_ylabel(None)
        ax.set_title(ylabel)
    fig.supxlabel('Minutes Since Tetracycline Addition')
    plt.tight_layout()
    fig.savefig('out/analysis/paper_figures/tet_short_term.svg')
    plt.close()

    # Second row of plots show long-term changes to tet. exposure
    # Filter data to include glucose for first 11550 seconds and
    # tetracycline data for remainder of simulation
    long_transition_data = restrict_data(data)
    long_term_columns = {
        'micF-ompF duplex': 0,
        'ompF mRNA': 1,
        'OmpF monomer': 2,
        'acrA mRNA': 3,
        'AcrA monomer': 4,
        'AcrAB-TolC': 5,
    }
    fig, axes = plt.subplots(2, 3, figsize=(7, 6))
    for column, ax_idx in long_term_columns.items():
        plot_timeseries(
            data=long_transition_data,
            axes=[axes.flat[ax_idx]],
            columns_to_plot={column: (0, 0.4, 1)},
            highlight_lineage='median',
            filter_time=False,
            background_alpha=0.5,
            background_linewidth=0.3,
            conc=True)
    for ax in axes.flat:
        ylim = ax.get_ylim()
        ax.set_yticks(np.round(ylim, 0).astype(int))
        # Mark hours since tetracycline addition
        xlim = np.array(ax.get_xlim())
        xticks = np.append(xlim, 11550/3600)
        xtick_labels = np.trunc(xticks-11550/3600).astype(int)
        ax.set_xticks(ticks=xticks, labels=xtick_labels)
        ax.set_xlabel(None)
        ax.spines.bottom.set(bounds=(0, MAX_TIME/3600), linewidth=1,
            visible=True, color=(0, 0, 0), alpha=1)
        ylabel = ax.get_ylabel()
        ax.set_ylabel(None)
        ax.set_title(ylabel)
    fig.supxlabel('Hours Since Tetracycline Addition')
    plt.tight_layout()
    fig.savefig('out/analysis/paper_figures/tet_long_term.svg')
    plt.close()

    # Convert ribosome counts to concentrations
    data.loc[:, 'Active ribosomes'] = (np.divide(data.loc[
        :, 'Active ribosomes'], data.loc[:, 'Volume']) *
        COUNTS_PER_FL_TO_NANOMOLAR)
    glc_data = data.loc[data.loc[:, 'Condition']=='Glucose', :]
    early_glc_mask = ((glc_data.loc[:, 'Time'] > 11550) &
        (glc_data.loc[:, 'Time'] < 12550))
    early_glc_mask = (glc_data.loc[:, 'Time'] == 11550)
    early_glc_data = glc_data.loc[early_glc_mask, :]
    late_glc_mask = ((glc_data.loc[:, 'Time'] > 25500) &
        (glc_data.loc[:, 'Time'] < 26000))
    late_glc_mask = (glc_data.loc[:, 'Time'] == 26000)
    late_glc_data = glc_data.loc[late_glc_mask, :]
    tet_data = data.loc[data.loc[
        :, 'Condition']=='Tetracycline (1.5 mg/L)', :]
    early_tet_mask = ((tet_data.loc[:, 'Time'] > 11550) &
        (tet_data.loc[:, 'Time'] < 12550))
    early_tet_mask = (tet_data.loc[:, 'Time'] == 11550)
    early_tet_data = tet_data.loc[early_tet_mask, :]
    late_tet_mask = ((tet_data.loc[:, 'Time'] > 25500) &
        (tet_data.loc[:, 'Time'] < 26000))
    late_tet_mask = (tet_data.loc[:, 'Time'] == 26000)
    late_tet_data = tet_data.loc[late_tet_mask, :]
    columns_to_plot = ['Growth rate', 'Active ribosomes',
        'Cytoplasmic tetracycline']
    bounds = metadata['Glucose'][0]['bounds']
    fig, axes = plt.subplots(4, 3, figsize=(7, 8))
    ax_idx = 0
    for condition_data in [early_glc_data, late_glc_data,
        early_tet_data, late_tet_data]:
        for column in columns_to_plot:
            plot_vs_distance_from_center(
                condition_data, bounds, axes.flat[ax_idx], column)
            ax_idx += 1
    plt.tight_layout()
    fig.savefig('out/analysis/paper_figures/dist_from_center.svg')
    plt.close()


def make_figure_3_validation(data):
    genes_to_plot = DE_GENES.loc[:, 'Gene name']
    fig, ax = plt.subplots(3, 1, figsize=(4, 7))
    plot_synth_prob_fc(data, ax[0], genes_to_plot)
    plot_mrna_fc(data, ax[1], genes_to_plot)
    plot_protein_synth_inhib(data, ax[2])
    plt.tight_layout()
    fig.savefig('out/analysis/paper_figures/tet_synth_prob.svg')
    plt.close()


def agent_data_table(raw_data, paths_dict, condition, seed):
    """Combine data from all agents into DataFrames for each timestep.

    Args:
        raw_data: Tuple of (time, dictionary at time for one replicate).
        paths_dict: Dictionary mapping paths within each agent to names
            that will be used the keys in the returned dictionary.
        condition: String identifier for experimental condition
        seed: Initial seed for this replicate

    Returns:
        Dataframe where each column is a path and each row is an agent."""
    time = raw_data[0]
    raw_data = raw_data[1]
    collected_data = {'Agent ID': []}
    agents_at_time = raw_data['agents']
    for agent_id, agent_at_time in agents_at_time.items():
        collected_data['Agent ID'].append(agent_id)
        for name, path in paths_dict.items():
            value_in_agent = get_value_from_path(agent_at_time, path)
            # Replace missing values with 0
            if value_in_agent == None:
                value_in_agent = 0
            path_data = collected_data.setdefault(name, [])
            path_data.append(value_in_agent)
    collected_data = pd.DataFrame(collected_data)
    collected_data['Time'] = [time] * len(collected_data)
    collected_data['Seed'] = [seed] * len(collected_data)
    collected_data['Condition'] = [condition] * len(collected_data)
    return collected_data


def load_data(experiment_id=None, cpus=8, sampling_rate=2,
    host="10.138.0.75", port=27017
):
    # Get data for the specified experiment_id
    monomers = [path[-1] for path in PATHS_TO_LOAD.values() if path[0]=='monomer']
    mrnas = [path[-1] for path in PATHS_TO_LOAD.values() if path[0]=='mrna']
    inner_paths = [path for path in PATHS_TO_LOAD.values()
        if path[-1] not in mrnas and path[-1] not in monomers
        and path != ('total_mrna',)]
    outer_paths = [('data', 'dimensions'), ('data', 'fields')]
    for condition, seeds in EXPERIMENT_ID_MAPPING.items():
        for seed, curr_experiment_id in seeds.items():
            if curr_experiment_id != experiment_id:
                continue
            metadata = {condition: {seed: {}}}
            rep_data = access_counts(
                experiment_id=experiment_id,
                monomer_names=monomers,
                mrna_names=mrnas,
                rna_synth_prob=mrnas,
                inner_paths=inner_paths,
                outer_paths=outer_paths,
                host=host,
                port=port,
                sampling_rate=sampling_rate,
                cpus=cpus,
                start_time=0,
                end_time=26000)
            with ProcessPoolExecutor(cpus) as executor:
                print('Deserializing data and removing units...')
                deserialized_data = list(tqdm(executor.map(
                    deserialize_and_remove_units, rep_data.values()),
                    total=len(rep_data)))
            rep_data = dict(zip(rep_data.keys(), deserialized_data))
            # Get spatial environment data for snapshot plots
            print('Extracting spatial environment data...')
            metadata[condition][seed]['bounds'] = rep_data[
                min(rep_data)]['dimensions']['bounds']
            metadata[condition][seed]['fields'] = {
                time: data_at_time['fields']
                for time, data_at_time in rep_data.items()
            }
            agent_df_paths = partial(agent_data_table,
                paths_dict=PATHS_TO_LOAD, condition=condition, seed=seed)
            with ProcessPoolExecutor(cpus) as executor:
                print('Converting data to DataFrame...')
                rep_dfs = list(tqdm(executor.map(
                    agent_df_paths, rep_data.items()),
                    total=len(rep_data)))
            # Save data for each experiment as local pickle
            pd.concat(rep_dfs).to_pickle(f'data/{experiment_id}.pkl')
            with open(f'data/{experiment_id}_metadata.pkl', 'wb') as f:
                pickle.dump(metadata, f)


def main():
    # Uncomment to create DataFrame pickle for experiment ID
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--experiment_id",
        "-e",
        help="Experiment ID to load data for",
        required=True,
    )
    parser.add_argument(
        "--cpus",
        "-c",
        type=int,
        help="# of CPUs to use for deserializing",
        required=True,
    )
    args = parser.parse_args()
    load_data(args.experiment_id, cpus=args.cpus)

    # Uncomment to create Figures 1 and 2 (seed 10000 looks best)
    # os.makedirs('out/analysis/paper_figures/', exist_ok=True)
    # with open(f'data/sim_dfs/{EXPERIMENT_ID_MAPPING["Glucose"][10000]}.pkl', 'rb') as f:
    #     data = pickle.load(f)
    # with open(f'data/sim_dfs/{EXPERIMENT_ID_MAPPING["Glucose"][10000]}_metadata.pkl', 'rb') as f:
    #     metadata = pickle.load(f)
    # make_figure_1(data, metadata)
    # make_figure_2(data, metadata)

    # Uncomment to create Figure 3 (seed 0 required for multiple concentrations)
    # tet_ids = [
    #     EXPERIMENT_ID_MAPPING['Glucose'][0],
    #     EXPERIMENT_ID_MAPPING['Tetracycline (4 mg/L)'][0],
    #     EXPERIMENT_ID_MAPPING['Tetracycline (2 mg/L)'][0],
    #     EXPERIMENT_ID_MAPPING['Tetracycline (1.5 mg/L)'][0],
    #     EXPERIMENT_ID_MAPPING['Tetracycline (1 mg/L)'][0],
    #     EXPERIMENT_ID_MAPPING['Tetracycline (0.5 mg/L)'][0],
    # ]
    # tet_ids = [
    #     EXPERIMENT_ID_MAPPING['Glucose'][0],
    #     EXPERIMENT_ID_MAPPING['Glucose'][100],
    #     EXPERIMENT_ID_MAPPING['Glucose'][10000],
    #     EXPERIMENT_ID_MAPPING['Tetracycline (1.5 mg/L)'][0],
    #     EXPERIMENT_ID_MAPPING['Tetracycline (1.5 mg/L)'][100],
    #     EXPERIMENT_ID_MAPPING['Tetracycline (1.5 mg/L)'][10000],
    # ]
    # tet_data = []
    # tet_metadata = {}
    # for exp_id in tet_ids:
    #     with open(f'data/sim_dfs/{exp_id}.pkl', 'rb') as f:
    #         tet_data.append(pickle.load(f))
    #     with open(f'data/sim_dfs/{exp_id}_metadata.pkl', 'rb') as f:
    #         tet_metadata.update(pickle.load(f))
    # tet_data = pd.concat(tet_data)
    # make_figure_3(tet_data, tet_metadata)
    # make_figure_3_validation(tet_data)

    # Uncomment to create Figure 4 (seed 0 required for multiple concentrations)
    # with open('data/sim_dfs/2022-10-28_05-47-52_977686+0000.pkl', 'rb') as f:
    #     amp_data = pickle.load(f)
    # with open('data/sim_dfs/2022-10-28_05-47-52_977686+0000_metadata.pkl', 'rb') as f:
    #     amp_metadata = pickle.load(f)


if __name__ == '__main__':
    main()
