# Romain THOMAS 2023
# Stockholm Resilience Centre, Stockholm University
# 
# Generate the parquet files for the library containing
# the list of all institutions and concepts from the raw
# files from OpenAlex.


import pandas as pd

parquet_compression = "brotli"

path_data_lib = "openalex_analysis/data/"

file_list_all_institutions_in = "list_all_institutions_full.parquet"
file_list_all_institutions_out = path_data_lib+"list_all_institutions.parquet"
col_list_all_institutions = ['id', 'display_name']

file_list_all_concepts_in = "OpenAlex_concepts_in_use_(17_August_2022)_-_concepts.csv"
file_list_all_concepts_out = path_data_lib+"list_all_concepts.parquet"
col_list_all_concepts = ['openalex_id', 'display_name', 'normalized_name', 'level']

print("Generating parquet file for the list of institutions...")
list_all_institutions_df = pd.read_parquet(file_list_all_institutions_in, columns = col_list_all_institutions)

list_all_institutions_df.to_parquet(file_list_all_institutions_out, compression=parquet_compression)

print("Generating parquet file for the list of concepts...")
list_all_concepts_df = pd.read_csv(file_list_all_concepts_in, usecols = col_list_all_concepts)

list_all_concepts_df.to_parquet(file_list_all_concepts_out, compression=parquet_compression)

print("Done.")
