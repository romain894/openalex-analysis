# Romain THOMAS 2023
# Stockholm Resilience Centre, Stockholm University

import pkgutil
from io import BytesIO

import pandas as pd

class EntitieNames():
    """Class to manage the concept and institution names"""

    ##### CONCEPTS #####
    concepts_parquet_file_path = "list_all_concepts.parquet"

    # Import the list of concepts
    concepts_df = pd.read_parquet(BytesIO(pkgutil.get_data(__name__, concepts_parquet_file_path)))

    # convert the concept id from link to just id
    concepts_df['openalex_id'] = concepts_df['openalex_id'].str.strip("https://openalex.org/").str.upper()

    # create the dictionaries with all the concepts
    concepts_names = concepts_df[['openalex_id', 'display_name']].set_index('openalex_id')['display_name'].to_dict()
    concepts_levels = concepts_df[['openalex_id', 'level']].set_index('openalex_id')['level'].to_dict()
    concepts_normalized_names = concepts_df[['openalex_id', 'normalized_name']].set_index('openalex_id')['normalized_name'].to_dict()


    ##### INSTITUTIONS #####
    institutions_parquet_file_path = "list_all_institutions.parquet"

    # Import the list of institutions
    institutions_df = pd.read_parquet(BytesIO(pkgutil.get_data(__name__, institutions_parquet_file_path)))

    # convert the institution id from link to just id
    institutions_df['id'] = institutions_df['id'].str.strip("https://openalex.org/").str.upper()

    # create the dictionary with all the institutions
    institutions_names = institutions_df[['id', 'display_name']].set_index('id')['display_name'].to_dict()

