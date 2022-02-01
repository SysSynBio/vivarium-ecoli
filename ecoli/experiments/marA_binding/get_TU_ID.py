import pandas as pd
import json
import numpy as np
from concurrent.futures import ProcessPoolExecutor
import multiprocessing

upreg = pd.read_table("ecoli/experiments/marA_binding/marA_up.tsv")
downreg = pd.read_table("ecoli/experiments/marA_binding/marA_down.tsv")

# Average fold change obtained from two independent marA constitutive expression experiments
for degenes in [upreg, downreg]:
    degenes['Fold change'] = degenes['Fold change'].str.split('/')
    degenes['Fold change'] = [np.mean([float(val) for val in reps]) for reps in degenes['Fold change']]

# Make downregulated genes have negative fold change
downreg['Fold change'] = -downreg['Fold change']
rnas = pd.read_table("reconstruction/ecoli/flat/rnas.tsv", comment='#')
degenes = pd.concat([upreg, downreg], ignore_index=True)
degenes = degenes.sort_values(by="Fold change", ascending=False, ignore_index=True)
model_degenes = []

for i, gene in enumerate(degenes["Gene name"]):
    # Cycle through gene synonyms in rnas.tsv to find EcoCyc name for DE genes
    for j, synonyms in enumerate(rnas["synonyms"]):
        if gene in synonyms:
            model_degenes.append(degenes.iloc[i,].append(rnas.iloc[j,]).to_frame().T)
        # Special case because "-" character is hard to deal with
        elif gene=="srlA2":
            if "srlA-2" in synonyms:
                model_degenes.append(degenes.iloc[i,].append(rnas.iloc[j,]).to_frame().T)

# Concatenating at end is supposed to be more efficient than row-wise append
model_degenes = pd.concat(model_degenes, ignore_index=True)
with open("ecoli/experiments/marA_binding/TU_id_to_index.json") as f:
    TU_id_to_index = json.load(f)

# Get model RNAs names by appending the "[c]" suffix, then get TU index for RNA
TU_idx = [TU_id_to_index[rna_id + "[c]"] for rna_id in model_degenes["id"]]
model_degenes["TU_idx"] = TU_idx
TU_idx_to_FC = {}

# TU index to fold change mapping saved as json (dictionary)
for i in range(len(TU_idx)):
    TU_idx_to_FC[int(model_degenes.loc[i, "TU_idx"])] = model_degenes.loc[i, "Fold change"]
with open("ecoli/experiments/marA_binding/TU_idx_to_FC.json", "w") as f:
    json.dump(TU_idx_to_FC, f)
with open("data/wcecoli_t0.json") as f:
    initial_state = json.load(f)
bulk_names = list(initial_state["bulk"].keys())

# Include complexes
comp_rxns = pd.read_table("reconstruction/ecoli/flat/complexation_reactions.tsv", comment = "#")

def get_IDs(monomer_id):
    monomer_id = json.loads(monomer_id)
    # In case monomer has more than 1 ID
    if len(monomer_id) != 1:
        print(monomer_id)
        raise Exception(f"Monomer has more than 1 ID: {monomer_id}")
    else:
        monomer_id = monomer_id[0]
    degene_bulk_names = []
    for bulk_name in bulk_names:
        if monomer_id in bulk_name:
            degene_bulk_names.append(bulk_name)

    monomers_used = []
    complex_ids = []
    for i in range(comp_rxns.shape[0]):
        stoich = json.loads(comp_rxns.iloc[i, 1])
        if monomer_id in stoich:
            monomers_used.append(stoich[monomer_id])
            complex_ids.append(list(stoich.keys())[0])
    
    return [degene_bulk_names, monomers_used, complex_ids]

# Protein IDs have varied suffixes: brute force search
with ProcessPoolExecutor(multiprocessing.cpu_count()) as executor:
    all_ids = executor.map(get_IDs, model_degenes["monomer_ids"])

model_degenes["bulk_ids"], model_degenes["monomers_used"], model_degenes["complex_ids"] = zip(*[ids for ids in all_ids])
    
model_degenes.to_csv("ecoli/experiments/marA_binding/model_degenes.csv", index=False)
