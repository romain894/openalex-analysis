# Romain THOMAS 2023
# Stockholm Resilience Centre, Stockholm University

import pandas as pd
from os import listdir

default_n_max_entities_to_download = 10000 # temporary here, should be better integrated

# TODO: UPDATE WITH COMPRESSED DATA FILES

class OA_entities_names():
    """Class to manage the concept names and databases file names for the webapp"""

    ##### CONCEPTS #####

    concepts_csv_file = "entitie_name_files_update_tools/OpenAlex_concepts_in_use_(17_August_2022)_-_concepts.csv"
    concepts_institutions_database_files_directory = "data/"
    max_concept_level = 2 # only for institions
    databases_format = ".parquet"

    # Import the list of concepts and create the dictionaries
    df_concepts = pd.read_csv(concepts_csv_file)

    # convert the concept id from link to just id
    df_concepts['openalex_id'] = df_concepts['openalex_id'].str.strip("https://openalex.org/").str.upper()

    # create the dictionaries with all the concepts
    concepts_names_full = df_concepts[['openalex_id', 'display_name']].set_index('openalex_id')['display_name'].to_dict()
    concepts_levels_full = df_concepts[['openalex_id', 'level']].set_index('openalex_id')['level'].to_dict()

    # convert the normalized_name into the file name
    # df_concepts['normalized_name_works'] = "works_concept_" + df_concepts['openalex_id'] + "_" + df_concepts['normalized_name'].str.replace(' ', '_', regex=False) + databases_format

    df_concepts_normalized_names_full = df_concepts[['openalex_id', 'normalized_name']]
    # df_concepts_works_file_names = df_concepts[['openalex_id', 'normalized_name_works']]


    # We filter the concepts only for the institutions
    # Filter the concept to keep only the concepts levels bellow max_concept_level included :
    df_concepts = df_concepts.loc[(df_concepts['level'] <= max_concept_level)]

    # convert the normalized_name into the file name
    df_concepts['normalized_name_institutions'] = "institutions_concept_" + df_concepts['openalex_id'] + "_" + df_concepts['normalized_name'].str.replace(' ', '_', regex=False) + "_max_"+str(default_n_max_entities_to_download) + databases_format

    # create the dictionaries
    concepts_names = df_concepts[['openalex_id', 'display_name']].set_index('openalex_id')['display_name'].to_dict()

    df_concepts_normalized_names = df_concepts[['openalex_id', 'normalized_name']]
    df_concepts_institutions_file_names = df_concepts[['openalex_id', 'normalized_name_institutions']]

    concepts_normalized_names = df_concepts_normalized_names.set_index('openalex_id')['normalized_name'].to_dict()
    concepts_institutions_database_file_name = df_concepts_institutions_file_names.set_index('openalex_id')['normalized_name_institutions'].to_dict()
    #concepts_works_database_file_name = df_concepts_works_file_names.set_index('openalex_id')['normalized_name_works'].to_dict()


    ##### INSTITUTIONS #####

    list_of_institutions_file_path = "entitie_name_files_update_tools/list_all_institutions_full.parquet"
    institutions_df = pd.read_parquet(list_of_institutions_file_path, columns = ['id', 'display_name'])
    # convert the concept id from link to just id
    institutions_df['id'] = institutions_df['id'].str.strip("https://openalex.org/").str.upper()
    institutions_names = institutions_df[['id', 'display_name']].set_index('id')['display_name'].to_dict()


    # bypass the init function from the parent class EntitiesConceptsAnalysis
    def __init__(self):
        pass

    def get_concepts_institutions_id_downloaded(self):
        concepts_files_name_downloaded = listdir(self.concepts_institutions_database_files_directory)
        return list(self.df_concepts_institutions_file_names.loc[self.df_concepts_institutions_file_names['normalized_name_institutions'].isin(concepts_files_name_downloaded)]['openalex_id'])


    ### Institutions ###
    # create the list of all the concept id with the databases downloaded
    def get_concepts_institutions_names_downloaded(self):
        concepts_id_downloaded = self.get_concepts_institutions_id_downloaded()
        # create the dictionary with the concept names downloaded
        concepts_names_downloaded = {k:self.concepts_names[k] for k in concepts_id_downloaded}
        return concepts_names_downloaded

    def get_concepts_institutions_names_downloadable(self):
        concepts_id_downloaded = self.get_concepts_institutions_id_downloaded()
        return [{'label': self.concepts_names[c], 'value': c, 'disabled': True} if c in concepts_id_downloaded else {'label': self.concepts_names[c], 'value': c} for c in self.concepts_names]


    # ### Works ###
    # def get_concepts_id_of_works_lists_downloaded(self):
    #     concepts_files_name_downloaded = listdir(self.concepts_institutions_database_files_directory)
    #     return list(self.df_concepts_works_file_names.loc[self.df_concepts_works_file_names['normalized_name_works'].isin(concepts_files_name_downloaded)]['openalex_id'])

    # def get_concepts_names_of_works_lists_downloaded(self):
    #     concepts_id_downloaded = self.get_concepts_id_of_works_lists_downloaded()
    #     # create the dictionary with the concept names downloaded
    #     concepts_names_downloaded = {k:self.concepts_names_full[k] for k in concepts_id_downloaded}
    #     return concepts_names_downloaded

    # def get_concepts_names_of_works_lists_downloadable(self):
    #     concepts_id_downloaded = self.get_concepts_id_of_works_lists_downloaded()
    #     return [{'label': self.concepts_names_full[c], 'value': c, 'disabled': True} if c in concepts_id_downloaded else {'label': self.concepts_names_full[c], 'value': c} for c in self.concepts_names_full]
