# Romain THOMAS 2023
# Stockholm Resilience Centre, Stockholm University

import os, sys
from os.path import exists, join # To check if a file exist
import psutil
import json

from tqdm import tqdm
import pandas as pd
import numpy as np
import country_converter as coco
from redis import StrictRedis
from redis_cache import RedisCache
import requests

# sys.path.append(os.path.abspath('pyalex'))
from pyalex import Works, Authors, Sources, Institutions, Concepts, Publishers, config

from openalex_analysis.names import EntitieNames


class AnalysisConfig(dict):
    """!
        @brief      TODO

        @param      email                     Email
        @param      api_key                   API key
        @param      openalex_url              OpenAlex URL
        @param      http_retry_times          HTTP retry times
        @param      allow_automatic_download  The allow automatic download
                                              (True/False)
        @param      disable_tqdm_loading_bar  The disable tqdm loading bar
                                              (True/False)
        @param      n_max_entities            TODO
        @param      project_datas_folder_path TODO
        @param      parquet_compression       TODO
        @param      max_storage_percent       TODO
        @param      redis_parameters          TODO TO UPDATE DOC
    """
    def __getattr__(self, key):
        return super().__getitem__(key)

    def __setattr__(self, key, value):
        # if key == 'redis_parameters':
        #     print("coucou1")
        #     if value != None:
        #         print("coucou2")
        #         super().__setitem__('redis_client', StrictRedis(value))
        #         super().__setitem__('cache', RedisCache(redis_client=self.redis_client))
        #         # redis_client = StrictRedis(**config.redis_parameters)
        #         # cache = RedisCache(redis_client=redis_client)
        return super().__setitem__(key, value)


config = AnalysisConfig(email=None,
                        api_key=None,
                        openalex_url="https://api.openalex.org",
                        allow_automatic_download = True,
                        disable_tqdm_loading_bar = False,
                        n_max_entities = 10000,
                        project_datas_folder_path = "data",
                        parquet_compression = "brotli",
                        max_storage_percent = 95,
                        redis_enabled = False,
                        redis_client = None,
                        redis_cache = None,
                        )


class EntitiesAnalysis(EntitieNames):
    """!
    OpenAlexAnalysis class which contains generic methods to do analysis over OpenAlex entities
    """

    

    # to convert country code to country name
    cc = coco.CountryConverter()


    def __init__(self,
                 entitie_from_id = None,
                 extra_filters = None,
                 database_file_path = None,
                 create_dataframe = True,
                 entitie_name = None,
                 load_only_columns = None,
                ):
        """!
        @param      entitie_from_id           The entitie identifier (eg an
                                              institution id) from which to take
                                              the entities (eg the works) to
                                              analyse (str)
        @param      filters                   Optional additionnal filters,
                                              refer to the documentation of
                                              openalex and pyalex for the format
                                              (dict)
        @param      database_file_path        The database file path to force
                                              the analyse over datas in a
                                              specific file (str)
        @param      create_dataframe          Create the dataframe at the
                                              initialisation (and download the
                                              data if needed and allowed)
        @param      entitie_name              To specify the name of the entitie
                                              to avoid downloading it via the
                                              API if needed
        """
        self.per_page = 200 # maximum allowed by the API

        self.entitie_from_id = entitie_from_id
        self.entitie_from_type = None
        self.extra_filters = extra_filters
        self.database_file_path = database_file_path
        self.entitie_name = entitie_name
        self.load_only_columns = load_only_columns

        # dictionary containning for each concept a list of the entities linked to the concept
        # self.entities_concepts = {} # DEPRECATED
        # same than self.entities_concepts formated as a dataframe with extra informations
        # self.entities_concepts_df = {} # DEPRECATED
        # a dataframe containing entities related to the instance
        self.entities_df = None

        # Dataframe with the entities filtered with multi concepts
        self.entities_multi_filtered_df = None

        # Dataframe with all the references of the entitie(s) and their count + the count for other entities (optionnal)
        # self.references_works_count_df = pd.DataFrame() # DEPRECATED
        # Dataframe with all the element (count_element_type) of the entitie(s) and their count + the count for other entities (optionnal)
        self.element_count_df = pd.DataFrame()

        # to display a loading bar on the web interface
        self.entitie_downloading_progress_percentage = 0
        # self.create_references_works_count_array_progress_percentage = 0 # DEPRECATED
        # self.create_references_works_count_array_progress_text = "" # DEPRECATED
        self.create_element_count_array_progress_percentage = 0
        self.create_element_count_array_progress_text = ""
        self.count_element_type = None
        self.count_element_years = None
        self.count_entities_cols = []

        # maximum values for the storage usage (used to remove the databases)
        # self.max_storage_percent = max_storage_percent # it will delete databases if storage usage > max_storage_percent

        # initialize the values only if entitie_from_type is known
        if self.entitie_from_id != None:
            self.entitie_from_type = self.get_entitie_type_from_id(self.entitie_from_id)
            if self.database_file_path == None:
                self.database_file_path = join(config.project_datas_folder_path, self.get_database_file_name())

        if entitie_from_id != None and create_dataframe == True:
            self.load_entities_dataframe()

    def get_count_entities_matched(self, query_filters):
        """!
        @brief      Gets and return the number of entities which match the query
                    fitlers.
        
        @param      query_filters  The query filters (dict)
        
        @return     The count entities matched (int)
        """
        results, meta = self.EntitieOpenAlex().filter(**query_filters).get(per_page = 1, return_meta=True)
        # results, meta = type(self.EntitieOpenAlex).__new__().filter(**query_filters).get(per_page = 1, return_meta=True)
        return meta['count']


    def get_api_query(self):
        """!
        @brief      Gets the api query from the parameters of the instance

        @return     The api query (dict)
        """
        query_filters = {self.get_entitie_string_name(self.entitie_from_type): {"id": self.entitie_from_id}}
        # special cases:
        # concept of institution as the query key word is x_concepts instead of concepts
        if self.get_entitie_type_from_id() == Institutions and self.get_entitie_type_from_id(self.entitie_from_id) == Concepts:
            query_filters = {'x_concepts': {"id": self.entitie_from_id}}
        if self.get_entitie_type_from_id(self.entitie_from_id) == Authors:
            query_filters = {'author': {"id": self.entitie_from_id}}
        if self.extra_filters != None:
            query_filters = query_filters | self.extra_filters
            print("query:", query_filters)
        return query_filters


    def download_list_entities(self):
        """!
        @brief      Downloads the entities which match the parameters of the
                    instance, and store the dataset as a parquet file
                """

        print("Downloading list of "+self.get_entitie_string_name()+" of the "+self.get_entitie_string_name(self.entitie_from_type)[0:-1]+" "+str(self.entitie_from_id))

        query = self.get_api_query()
        print("Query to download from the API:", query)

        count_entities_matched = self.get_count_entities_matched(query)

        if config.n_max_entities == None or config.n_max_entities > count_entities_matched:
            n_entities_to_download = count_entities_matched
            print("All the", n_entities_to_download, "entities will be downloaded")
        else:
            n_entities_to_download = config.n_max_entities
            print("Only", n_entities_to_download, "entities will be downloaded ( out of", count_entities_matched, ")")

        # create a list to store the entities
        entities_list = [None] * n_entities_to_download

        # create the pager entitie to iterate over the pages of entities to download
        pager = self.EntitieOpenAlex().filter(**query).paginate(per_page = self.per_page, n_max = n_entities_to_download)

        print("Downloading the list of entities thought the OpenAlex API...")
        with tqdm(total=n_entities_to_download, disable=config.disable_tqdm_loading_bar) as pbar:
            i = 0
            self.entitie_downloading_progress_percentage = 0
            for page in pager:
                # add the downloaded entities in the main list
                for entitie in page:
                    # print(entitie)
                    self.filter_and_format_entitie_data_from_api_response(entitie)
                    # print(entitie)
                    # raise ValueError("toto stop")
                    if i < n_entities_to_download:
                        entities_list[i] = entitie
                    else:
                        entities_list.append(entitie)
                        print("entities_list was too short, appending the entitie")
                    i += 1
                # update the progress bar
                pbar.update(self.per_page)
                # update the progress percentage variable
                self.entitie_downloading_progress_percentage = i/n_entities_to_download*100
        self.entitie_downloading_progress_percentage = 100

        # sort the list by concept score
        # Not working + useless?: entities_list = sorted(entities_list, key=lambda d: self.get_concept_score(d, concept), reverse=True)
        
        # normalize the json format (one column for each field)
        print("Normalizing the json data downloaded...")
        entities_list_df = pd.json_normalize(entities_list)
        # We don't use multi index dataframe as plotly and dask doesn't support it and the use case is minor
        # # convert to multi index dataframe (we create an index for each 'subcolumn' (=when there is a '.'))
        # tuple_cols = entities_list_df.columns.str.split('.')
        # entities_list_df.columns = pd.MultiIndex.from_tuples(tuple(i) for i in tuple_cols)
        print("Checking space left on disk...")
        self.auto_remove_databases_saved()
        # save as compressed parquet file
        print("Saving the list of entities as a parquet file...")
        entities_list_df.to_parquet(self.database_file_path, compression=config.parquet_compression)


    def load_entities_dataframe(self):
        """!
        @brief      Loads an entities dataset from file (or download it if needed and
                    allowed by the instance) to the dataframe of the instance
        """
        print("Loading dataframe of "+self.get_entitie_string_name()+" of the "+self.get_entitie_string_name(self.entitie_from_type)[0:-1]+" "+self.entitie_from_id)
        #print("Creating dataframe for entities (concept: "+self.concepts_normalized_names[concept]+")")

        # # check if the database file exists
        if exists(self.database_file_path):
            # the database exists, we can load it
            pass
        elif config.allow_automatic_download == True:
            # the database doesn't exist and we can download the datas
            # we create the database and then load it
            self.download_list_entities()
        else:
            raise ValueError("Couldn't load the database of the entitie because doesn't exist locally and not allowed to download it")
        print("Loading the list of entities from a parquet file...")
        try:
            self.entities_df = pd.read_parquet(self.database_file_path, columns = self.load_only_columns)
        except:
            # couldn't load the parquet file (eg no row in parquet file so error because can't find columns to load)
            self.entities_df = pd.DataFrame()


    def auto_remove_databases_saved(self):
        """!
        @brief      Remove databases files (the data downloaded from OpenAlex) if the
                    storage is full. It keeps the last accessed files
        """
        while psutil.disk_usage(config.project_datas_folder_path).percent > config.max_storage_percent:
            first_accessed_file = None
            first_accessed_file_time = 0
            for file in os.listdir(config.project_datas_folder_path):
                if file.endswith(".parquet"):
                    if os.stat(join(config.project_datas_folder_path, file)).st_atime < first_accessed_file_time or first_accessed_file_time == 0:
                        first_accessed_file_time = os.stat(join(config.project_datas_folder_path, file)).st_atime
                        first_accessed_file = file
            if first_accessed_file == None:
                print("No more file to delete.")
                print("Space used on disk: "+str(psutil.disk_usage(config.project_datas_folder_path).percent)+"%")
                break
            os.remove(join(config.project_datas_folder_path, first_accessed_file))
            print("Removed file "+str(join(config.project_datas_folder_path, first_accessed_file))+"_(last_used:_"+str(first_accessed_file_time)+")")                


    def get_df_filtered_entities_selection_threshold(self, df_filters):
        """!
        @brief      Gets df_filtered which contains the entities of self.entities_df
                    fitting the filters in df_filters
        
        @param      df_filters  The filters in a dictionnary with for the key
                                for the data to filter and for the value the
                                minimum threshold (dict)
        
        @return     df_filtered, corresponding the the entities fitting the
                    thresholds (pandas DataFrame)
        """
        entities_df_filtered = self.entities_df
        for key_filter, value_filter in df_filters.items():
            entities_df_filtered = entities_df_filtered.loc[(entities_df_filtered[key_filter] >= value_filter)]
        # # fitler for cited_by_threshold
        # if cited_by_threshold != 0:
        #     entities_df_filtered = entities_df_filtered.loc[(entities_df_filtered['works_cited_by_count_average'] >= cited_by_threshold)]
        
        #     if len(display_only_selected_entities):
        #         entities_df_filtered = entities_df_filtered.loc[(entities_df_filtered[x_datas] >= x_threshold) & (entities_df_filtered[y_datas] >= y_threshold)]
        return entities_df_filtered


    def get_number_of_entities_selected(self, x_threshold, y_threshold, cited_by_threshold, x_datas, y_datas):
        """!
        @brief      Gets the number of entities selected on the plot
        
        @param      x_threshold         The x threshold (float or int)
        @param      y_threshold         The y threshold (float or int)
        @param      cited_by_threshold  The cited by threshold (float or int)
        @param      x_datas             The x datas key on the dataframe (str)
        @param      y_datas             The y datas key on the dataframe (str)
        
        @return     The number of entities selected (int)
        """
        n_selected_entities = 0
        if cited_by_threshold > 0:
            for index, row in self.entities_df.iterrows():
                if row[x_datas] >= x_threshold and row[y_datas] >= y_threshold and row['works_cited_by_count_average'] >= cited_by_threshold:
                    n_selected_entities += 1
        else:
            for index, row in self.entities_df.iterrows():
                if row[x_datas] >= x_threshold and row[y_datas] >= y_threshold:
                    n_selected_entities += 1
        return n_selected_entities

    def create_multi_concept_filters_entities_dataframe(self, concepts_from, concepts_filters, thresholds, x_datas, x_threshold, cited_by_threshold):
        """!
        @brief      Creates the multi concept filters entities dataframe. Combines
                    different datasets and filters them.
        
        @param      concepts_from       The concept datasets to import and on
                                        which the filters will be applied (list
                                        of str)
        @param      concepts_filters    The concepts which will be used to
                                        filter (list of str)
        @param      thresholds          The thresholds attached to each concepts
                                        to filter (list of float or int)
        @param      x_datas             The dataframe key of the global filter
                                        (eg the number of works) (str)
        @param      x_threshold         The threshold for the global filter
                                        (float or int)
        @param      cited_by_threshold  The cited by threshold (another global
                                        filter) (float or int)
        """
        self.entities_multi_filtered_df = pd.DataFrame()
        # We add the concepts from where to select the entities to the dataframe
        for concept in concepts_from:
            # import the dataframe (create a new instance of the same class which will load the dataframe)
            entitie_instance = type(self)(entitie_from_id = concept)
            entities_df_filtered = entitie_instance.entities_df
            # filter the entities/dataframe with the global filters
            entities_df_filtered = entities_df_filtered.loc[((entities_df_filtered[x_datas] >= x_threshold) & (entities_df_filtered['works_cited_by_count_average'] >= cited_by_threshold))]
            # merge with the main dataframe
            if len(self.entities_multi_filtered_df.index) == 0:
                self.entities_multi_filtered_df = entities_df_filtered.copy(deep=False)
            else:
                self.entities_multi_filtered_df = pd.concat([self.entities_multi_filtered_df, entities_df_filtered], ignore_index=True)
                self.entities_multi_filtered_df = self.entities_multi_filtered_df.drop_duplicates(subset=['id'])
            # remove the column with the concept score previously computed when loading the database from file
            self.entities_multi_filtered_df.drop(concept, axis=1, inplace=True)
            print("number of entities loaded:", len(self.entities_multi_filtered_df.index))
        # filter the entities/dataframe with the concept filters:
        for concept, threshold in zip(concepts_filters, thresholds):
            # load the dataframe of the concept to filter:
            entitie_instance = type(self)(entitie_from_id = concept)
            entitie_instance.entities_df = entitie_instance.entities_df.set_index('id')
            # add a column to add the concept score in it
            self.entities_multi_filtered_df['concept_score'] = 0
            # for each entitie in self.entities_multi_filtered_df, add the concept score if entitie found in entitie_instance (otherwise let 0)
            for entitie in self.entities_multi_filtered_df.itertuples():
                if entitie.id in entitie_instance.entities_df.index:
                    self.entities_multi_filtered_df.at[entitie.Index, 'concept_score'] = entitie_instance.entities_df.at[entitie.id, concept]
            # remove row with concept score bellow threshold:
            self.entities_multi_filtered_df = self.entities_multi_filtered_df[self.entities_multi_filtered_df['concept_score'] >= threshold]
            print("number of entities remaining after filter:", len(self.entities_multi_filtered_df.index))


    def add_average_combined_concept_score_to_multi_concept_entitie_df(self, concepts_from):
        """!
        @brief      Adds a column with the average combined concept score to the multi
                    concept entities dataframe.
        
        @param      concepts_from  The concepts to use to calculate the combined
                                   concept score (list of str)
        """
        concept_links = ["https://openalex.org/"+item for item in concepts_from]
        self.entities_multi_filtered_df['average_combined_concepts_score'] = [self.get_sum_concept_scores(entitie, concept_links)/len(concepts_from) for index, entitie in self.entities_multi_filtered_df.iterrows()]
    
    def get_database_file_name(self, entitie_from_id = None, entities_type = None, db_format = "parquet", extra_text = None):
        """!
        @brief      Gets the database file name according to the parameters of the
                    ojbect or the arguments given.
        
        @param      entitie_from_id  The identifier of the entitie (eg a concept
                                     id) which was used to filter the entities
                                     (eg works) in the database (str)
        @param      entities_type    The entities type in the database (eg
                                     works) (EntitieOpenAlex)
        @param      db_format        The database file format (str)
        @param      extra_text       Extra text to add to the file name (str)
        
        @return     The database file name (str)
        """
        if entitie_from_id == None:
            entitie_from_id = self.entitie_from_id
        if entities_type == None:
            entities_type = self.EntitieOpenAlex
        file_name = self.get_entitie_string_name(entities_type)+"_"+self.get_entitie_string_name(self.get_entitie_type_from_id(entitie_from_id))[0:-1]+"_"+entitie_from_id
        # if it's a concept, we add it's name to the file name (we can't do that for the other entitie type as
        # the names can change. For the concept, all the names are known and saved locally in a csv file)
        if self.get_entitie_type_from_id(entitie_from_id) == Concepts:
            file_name += "_"+self.concepts_normalized_names[entitie_from_id].replace(' ', '_')
        # temporary solution (can be problematic as database number can grow fast)
        # add the hash value of filters if used
        if self.extra_filters != None:
            # hash not working accross class instances
            #file_name += "_"+str(abs(hash(json.dumps(self.extra_filters, sort_keys=True))))
            # Can be a problem in case of many filters as file names are limited to 255 char
            file_name += "_" + str(self.extra_filters).replace("'", '').replace(":", '').replace(' ', '_')
        file_name += "_max_"+str(config.n_max_entities)
        if extra_text != None:
            file_name += "_" + extra_text
        return file_name+"."+db_format

    def get_entitie_string_name(self, entitie = None):
        """!
        @brief      Gets the entitie type string name.
        
        @param      entitie  The entitie, if not provided, the instance entitie
                             id will be used (BaseOpenAlex)
        
        @return     The entitie type name (str)
        """
        if entitie == None:
            entitie = self.EntitieOpenAlex
        return str(entitie).removeprefix("<class 'pyalex.api.").removesuffix("'>").lower()

    def get_entitie_type_from_id(self, entitie = None):
        """!
        @brief      Gets the entitie type from the entitie id

        @param      entitie  The entitie id (str)

        @return     The entitie type (BaseOpenAlex)
        """
        if entitie == None:
            entitie = self.entitie_from_id
        return get_entitie_type_from_id(entitie)

    def get_name_of_entitie(self, entitie = None, allow_download_from_API = True):
        """!
        @brief      Gets the name of entitie
        
        @param      entitie                  The entitie id, if not provided,
                                             use the one from the instance (str)
        @param      allow_download_from_API  Allow to download the entitie name
                                             from the OpenAlex API (bool)
        
        @return     The name of entitie (str)
        """
        if entitie == None:
            entitie = self.entitie_from_id
        # if the entitie name asked is the one of the current instance and it was provided in the initialisation
        if entitie == self.entitie_from_id and self.entitie_name != None:
            return self.entitie_name
        elif allow_download_from_API:
            return get_name_of_entitie_from_api(entitie)
        else:
            raise ValueError("Can't get the entitie name because not allowed to download from API and not provided at the initialisation")


    def get_info_about_entitie(self, entitie, infos = ["display_name"], return_as_pd_serie = True, allow_download_from_API = True):
        if entitie == None:
            entitie = self.entitie_from_id
        if allow_download_from_API:
            return get_info_about_entitie_from_api(entitie, infos = infos, return_as_pd_serie = return_as_pd_serie)
        else:
            raise ValueError("Can't get the entitie info because not allowed to download from API")




def get_entitie_type_from_id(entitie):
    """!
    @brief      Gets the entitie type from the entitie id

    @param      entitie  The entitie id (str)

    @return     The entitie type (BaseOpenAlex)
    """
    match entitie[0]:
        case 'W':
            return Works
        case 'A':
            return Authors
        case 'S':
            return Sources
        case 'I':
            return Institutions
        case 'C':
            return Concepts
        case 'P':
            return Publishers
        case _:
            raise ValueError("Entitie id "+entitie+" not valid")


def get_name_of_entitie_from_api_core(entitie):
    """!
    @brief      Gets the name of entitie from api

    @param      entitie  The entitie id

    @return     The name of entitie (str)
    """
    # call the API
    e = get_entitie_type_from_id(entitie)()[entitie]
    return e['display_name']

# @config.cache.cache()
# def get_name_of_entitie_from_api_cache(entitie):
#     print("Getting name of "+entitie+" from the OpenAlex API (not found in cache)...")
#     return get_info_about_entitie_from_api_core(entitie)

# def get_name_of_entitie_from_api_no_cache(entitie):
    # print("Getting name of "+entitie+" from the OpenAlex API (cache disabled)...")
    # return get_info_about_entitie_from_api_core(entitie)

def get_name_of_entitie_from_api(entitie):
    # if config.redis_parameters != None:
    #     return get_name_of_entitie_from_api_cache(entitie)
    # else:
    #     return get_name_of_entitie_from_api_no_cache(entitie)
    if config.redis_enabled == True:
        print("Getting name of "+entitie+" from the OpenAlex API (cache enabled)...")
        get_name_of_entitie_from_api_core_cached = config.redis_cache.cache()(get_name_of_entitie_from_api_core)
        return get_name_of_entitie_from_api_core_cached(entitie)
    else:
        print("Getting name of "+entitie+" from the OpenAlex API (cache disabled)...")
        return get_name_of_entitie_from_api_core(entitie)

def extract_authorships_citation_style(authorships):
    if len(authorships) == 0:
        res = "Unknown author"
    if len(authorships) >= 1:
        res = authorships[0]['author']['display_name']
    if len(authorships) >= 2:
        res += ", "+authorships[1]['author']['display_name']
    if len(authorships) > 1:
        res += " et al."
    return res


def get_info_about_entitie_from_api_core(entitie, infos = ["display_name"]):
    """!
    @brief      Gets information about entitie from api
    
    @param      entitie  The entitie id (str)
    @param      infos    The infos (str)
    
    @return     The name of entitie (str)
    """
    # call the API
    e = get_entitie_type_from_id(entitie)()[entitie]
    if "author_citation_style" in infos:
        e["author_citation_style"] = extract_authorships_citation_style(e["authorships"])
    e = {key: val for key, val in e.items() if key in infos}
    return e


# @config.cache.cache()
# def get_info_about_entitie_from_api_cache(entitie, infos = ["display_name"]):
#     print("Getting information about "+entitie+" from the OpenAlex API (not found in cache)...")
#     return get_info_about_entitie_from_api_core(entitie, infos = infos)

# def get_info_about_entitie_from_api_no_cache(entitie, infos = ["display_name"]):
#     print("Getting information about "+entitie+" from the OpenAlex API (cahe disabled)...")
#     return get_info_about_entitie_from_api_core(entitie, infos = infos)

def get_info_about_entitie_from_api(entitie, infos = ["display_name"], return_as_pd_serie = True):
    # if config.redis_parameters != None:
    #     res = get_info_about_entitie_from_api_cache(entitie, infos = infos)
    # else:
    #     res = get_info_about_entitie_from_api_no_cache(entitie, infos = infos)
    if config.redis_enabled == True:
        print("Getting information about "+entitie+" from the OpenAlex API (cache enabled)...")
        get_info_about_entitie_from_api_core_cached = config.redis_cache.cache()(get_info_about_entitie_from_api_core)
        res = get_info_about_entitie_from_api_core_cached(entitie, infos = infos)
    else:
        print("Getting information about "+entitie+" from the OpenAlex API (cahe disabled)...")
        res = get_info_about_entitie_from_api_core(entitie, infos = infos)
    if return_as_pd_serie:
        data = [val for val in res.values()]
        index = [key for key in res]
        res = pd.Series(data=data, index=index)
    return res


def check_if_entity_exists_core(entitie):
    """!
    @brief      Check if the entity exists

    @param      entitie  The entitie id

    @return     The name of entitie (str)
    """
    # get the name of the entity
    api_path = str(entitie).removeprefix("<class 'pyalex.api.").removesuffix("'>").lower()+"s"
    # call the API
    response = requests.get("https://api.openalex.org/"+api_path+"/"+entitie)
    if response.status_code == 404:
        return False
    else:
        return True 


def check_if_entity_exists_from_api(entitie):
    if config.redis_enabled == True:
        print("Checking if "+entitie+" exists (cache enabled)...")
        check_if_entity_exists_core_cached = config.redis_cache.cache()(check_if_entity_exists_core)
        return check_if_entity_exists_core_cached(entitie)
    else:
        print("Checking if "+entitie+" exists (cache disabled)...")
        return check_if_entity_exists_core(entitie)
        
class WorksAnalysis(EntitiesAnalysis, Works):
    """!
    @brief      This class contains specific methods for Works concepts analysis.
    """
    EntitieOpenAlex = Works
    def filter_and_format_entitie_data_from_api_response(self, entitie):
        """!
        @brief      Filter and format the works data downloaded from the API
        
        @param      entitie  The works data from the API (dict)
        
        @return     The works datas (dict)
        """
        # # transform datas
        # # abstract
        # disabled for now
        # entitie['extracted_abstract'] = entitie['abstract']

        # delete useless datas
        # for now storing the abstract_inverted_index isn't possible because if expand in the dataframe
        # and makes it too big --> storing full abstract
        del entitie['abstract_inverted_index']
        
        # add computed datas:
        # concept_score if the downloading list comes from a concept
        if self.entitie_from_type == Concepts:
            # self.entitie_from_id is equal to the concept
            entitie[self.entitie_from_id] = float(next((item['score'] for item in entitie['concepts'] if item['id'] == "https://openalex.org/"+self.entitie_from_id), 0))
            # entitie[concept] = next((item['score'] for key, item in entitie['x_concepts'].items() if item['id'] == "https://openalex.org/"+concept), 0)
        # country_name
        country_code = self.get_country_code(entitie)
        if country_code != None:
            entitie['country_name'] = self.cc.convert(names = [self.get_country_code(entitie)], to = 'name_short')
        else:
            entitie['country_name'] = None
        # institution_name
        entitie['institution_name'] = self.get_institution_name(entitie)


    def get_country_code(self, entitie):
        """!
        @brief      Gets the country code from an entitie

        @param      entitie  The entitie (dict)

        @return     The country code (str)
        """
        if entitie['authorships'] != [] and entitie['authorships'][0]['institutions'] != [] and 'country_code' in entitie['authorships'][0]['institutions'][0]:
            return entitie['authorships'][0]['institutions'][0]['country_code']
        else:
            return None


    def get_institution_name(self, entitie):
        """!
        @brief      Gets the institution name from an entitie

        @param      entitie  The entitie (dict)

        @return     The institution name (str)
        """
        if entitie['authorships'] != [] and entitie['authorships'][0]['institutions'] != [] and 'display_name' in entitie['authorships'][0]['institutions'][0]:
            return entitie['authorships'][0]['institutions'][0]['display_name'] 
        else:
            return None

    
    def get_works_references_count(self, count_years = []):
        """!
        @brief      Gets the works references count of the works list of the instance
        
        @return     The works references count (pandas Serie)
        """
        print("Creating the works references count of "+self.get_entitie_string_name()+" "+self.entitie_from_id+"...")
        if count_years == []:
            return self.entities_df['referenced_works'].explode().value_counts().convert_dtypes()
        else:
            counts_df_list = [None] * len(count_years)
            for i, year in enumerate(count_years):
                counts_df_list[i] = self.entities_df[self.entities_df.publication_year == year]['referenced_works'].explode().value_counts().convert_dtypes()
            entities_count = pd.concat(counts_df_list, axis=1, keys=count_years).reset_index().fillna(0)
            entities_count = entities_count.set_index('referenced_works').stack()
            entities_count.name = 'count'
            return entities_count


    def get_works_concepts_count(self, count_years = []):
        """!
        @brief      Gets the concepts count of the works list of the instance
        
        @param      count_only_year  If different than None, count only the
                                     concepts of the works of the given year
                                     (int)
        
        @return     The concept count (pandas Serie)
        """
        print("Creating the concept count of "+self.get_entitie_string_name()+" "+self.entitie_from_id+"...")
        if count_years == []:
            return self.entities_df['concepts'].explode().apply(lambda c: c['id'] if type(c) == dict else None).value_counts().convert_dtypes()
        else:
            counts_df_list = [None] * len(count_years)
            for i, year in enumerate(count_years):
                counts_df_list[i] = self.entities_df[self.entities_df.publication_year == year]['concepts'].explode().apply(lambda c: c['id'] if type(c) == dict else None).value_counts().convert_dtypes()
            entities_count = pd.concat(counts_df_list, axis=1, keys=count_years).reset_index().fillna(0)
            entities_count = entities_count.set_index('concepts').stack()
            entities_count.name = 'count'
            return entities_count


    def get_element_count(self, element_type, count_years = []):
        # entities_to_count_df = None
        # if count_only_year == None:
        #     entities_to_count_df = self.entities_df
        # else:
        #     entities_to_count_df = self.entities_df[self.entities_df.publication_year == count_only_year]
        match element_type:
            case 'reference':
                return self.get_works_references_count(count_years = count_years)
            case 'concept':
                return self.get_works_concepts_count(count_years = count_years)
            case _:
                raise ValueError("Can only count for 'references' or 'concept'")
    

    def create_element_used_count_array(self, element_type, entities_from = [], out_file_name = None, save_out_array = False, count_years = []):
        """!
        @brief      Creates the element used count array. Count the number of times each
                    element (eg reference, concept..) is used and save the array as CSV
                    (optional)
        
        @param      element_type    The element type
        @param      entities_from   The extra entities to which to count the
                                    concepts (list of str)
        @param      out_file_name   The out CSV file name, if not provided, an
                                    appropriate name is generated (str)
        @param      save_out_array  Save out array (bool)
        @param      count_years     If given, it will compute the count for each
                                    year (list[int])
        """
        self.count_element_type = element_type
        self.count_element_years = count_years
        self.count_entities_cols = []
        cols_to_load = None
        match self.count_element_type:
            case 'reference':
                cols_to_load = ['id', 'referenced_works', 'publication_year']
            case 'concept':
                cols_to_load = ['id', 'concepts', 'publication_year']
            case _:
                raise ValueError("Can only count for 'references' or 'concept'")

        if self.entitie_from_id == None and entities_from == []:
            raise ValueError("You need either to instancy the object with an entitie_from_id or to provide entities_from to create_element_used_count_array()")
        # TODO: add parameter to drop references not in the entitie to compare from : useless as we can not import it
        if out_file_name == None:
            if self.entitie_from_id == None:
                out_file_name = self.count_element_type+"s_"+self.get_entitie_string_name()+"_of_diverse_entities"
            else:
                out_file_name = self.count_element_type+"s_"+self.get_entitie_string_name()+"_of_"+self.get_entitie_string_name(self.get_entitie_type_from_id(self.entitie_from_id))[0:-1]+"_"+self.entitie_from_id
                if self.get_entitie_type_from_id(self.entitie_from_id) == Concepts:
                    out_file_name += "_("+self.concepts_normalized_names[self.entitie_from_id].replace(' ', '_')+")"
            out_file_name += ".csv"
            out_file_name = join(config.project_datas_folder_path, out_file_name)

        self.element_count_df = pd.DataFrame()
        self.element_count_df.index.name = self.count_element_type+"s"

        self.create_element_count_array_progress_percentage = 0
        self.create_element_count_array_progress_text = "Creating the "+self.count_element_type+"s array..."

        # Create the count array for the first/main entitie if previously added to object
        if self.entitie_from_id != None:
            col_name = self.entitie_from_id+" "+self.get_name_of_entitie()
            self.count_entities_cols.append(col_name)
            if len(self.entities_df.index) == 0:
                self.element_count_df[col_name] = pd.Series().convert_dtypes()
            else:
                self.element_count_df = pd.concat([self.element_count_df, self.get_element_count(self.count_element_type, count_years = count_years)], axis = 1)
                self.element_count_df = self.element_count_df.rename(columns = {'count':col_name})

        for i, entitie in enumerate(entities_from):
            self.create_element_count_array_progress_percentage = int(i/len(entities_from)*100)
            # initialise the WorksAnalysis instance
            works = WorksAnalysis(**entitie, load_only_columns=cols_to_load)
            col_name = works.entitie_from_id+" "+works.get_name_of_entitie()
            self.count_entities_cols.append(col_name)
            # if there is no data in the dataframe, we add a blank colomn
            if len(works.entities_df.index) == 0:
                self.element_count_df[col_name] = pd.Series().convert_dtypes()
            else:
                self.element_count_df = pd.concat([self.element_count_df, works.get_element_count(self.count_element_type, count_years = count_years)], axis = 1)
                self.element_count_df = self.element_count_df.rename(columns = {'count':col_name})

        if count_years != []:
            self.element_count_df.index = self.element_count_df.index.set_names('element', level=0)
            self.element_count_df.index = self.element_count_df.index.set_names('year', level=1)
        else:
            self.element_count_df.index.name = 'element'

        self.create_element_count_array_progress_percentage = 100

        if save_out_array:
            print("Saving element_count_df to ", out_file_name)
            self.element_count_df.to_csv(out_file_name)


    def sort_count_array(self, sort_by = 'h_used_all_l_use_main', sort_by_ascending = False):
        """!
        @brief      Sort the dataframe with the count array (element_count_df)
        
        @param      sort_by            The key to sort the dataframe (str)
        @param      sort_by_ascending  Whenever to sort the dataframe ascending
                                       (bool)
        """
        print("Sorting by "+sort_by)
        if self.count_element_years == []:
            # we didn't count per year so we can do a simple sort
            self.element_count_df = self.element_count_df.sort_values(by=sort_by, ascending = sort_by_ascending)
        else:
            sorted_sums = self.element_count_df[sort_by].groupby(level=0).sum().sort_values(ascending=sort_by_ascending)
            self.element_count_df = self.element_count_df.reindex(sorted_sums.index, level=0)


    def add_statistics_to_element_count_array(self, sort_by = 'h_used_all_l_use_main', sort_by_ascending = False, min_concept_level = None):
        """!
        @brief      Adds a statistics to the element count array (statistics between the
                    main entitie to compare (second column in the dataframe) and the sum
                    of the other entities)
        
        @param      sort_by            The key to sort the dataframe (str)
        @param      sort_by_ascending  Whenever to sort the dataframe ascending
                                       (bool)
        @param      min_concept_level  In case the element is a concept, this is
                                       the minimum level of the concepts we will
                                       keep (aka remove the lower (= more
                                       global) concepts)
        """
        if not self.count_element_type in ['reference', 'concept']:
            raise ValueError("Can only count for 'references' or 'concept'")
        # self.create_references_works_count_array_progress_text = "Adding statistics on the references array..."
        if self.element_count_df.empty:
            raise ValueError("Need to create element_count_df before adding statistics")
        # we need at least 2 entities in the dataframe so 2 columns (self.entitie_id and entitie or 2 entities) (the ref id are the index)
        nb_entities = len(self.element_count_df.columns)
        if nb_entities < 1:
            raise ValueError("Need at least 2 entities in the dataframe to compare entities")
        main_entitie_col_id = self.element_count_df.columns.values[0]
        print("Main entitie:", main_entitie_col_id)
        nb_entities = len(self.element_count_df.columns)
        self.element_count_df.fillna(value=0, inplace=True)
        print("Computing sum_all_entities...")
        # self.element_count_df['sum_all_entities'] = self.element_count_df.iloc[:, 1:1+nb_entities].sum(axis=1)
        self.element_count_df['sum_all_entities'] = self.element_count_df.sum(axis=1)
        print("Computing average_all_entities...")
        self.element_count_df['average_all_entities'] = self.element_count_df['sum_all_entities']/nb_entities
        # print("Computing nb_cited_sum_other_entities...")
        # self.element_count_df['nb_cited_sum_other_entities'] = self.element_count_df['sum_all_entities'] - self.element_count_df[main_entitie_col_id]
        print("Computing proportion_used_by_main_entitie")
        # use sum other entities (exclude main entitie from the sum)
        # self.element_count_df['proportion_used_by_main_entitie'] = self.element_count_df[main_entitie_col_id] / self.element_count_df['nb_cited_sum_other_entities']
        # use sum all entities (include main entitie in the sum)
        print("fill with NaN values 0 of sum_all_entities to avoid them to be used when ranking (we wan't to ignore these rows as these references aren't used)")
        self.element_count_df['sum_all_entities'] = self.element_count_df['sum_all_entities'].replace(0, None)
        self.element_count_df['proportion_used_by_main_entitie'] = self.element_count_df[main_entitie_col_id] / self.element_count_df['sum_all_entities']
        #self.element_count_df['proportion_used_by_main_entitie'] = self.element_count_df[main_entitie_col_id].div(self.element_count_df['sum_all_entities'])
        # # we put -1 inplace of NaN values (it's where the sum_all_entities is 0 so the division failed)
        # self.element_count_df.fillna(value=-1, inplace=True)
        print("Computing sum_all_entities rank...")
        self.element_count_df['sum_all_entities_rank'] = self.element_count_df['sum_all_entities'].rank(ascending = True, pct = True)#, method = 'dense') # before method = 'average' was used
        print("Computing proportion_used_by_main_entitie rank...")
        self.element_count_df['proportion_used_by_main_entitie_rank'] = self.element_count_df['proportion_used_by_main_entitie'].rank(ascending = False, pct = True)#, method = 'dense') # before method = 'average' was used
        print("Computing highly used by all entities and low use by main entitie")
        self.element_count_df['h_used_all_l_use_main'] = self.element_count_df['sum_all_entities_rank'] * self.element_count_df['proportion_used_by_main_entitie_rank']
        
        self.sort_count_array(sort_by = sort_by, sort_by_ascending = sort_by_ascending)

        match self.count_element_type:
            case 'reference':
                self.add_statistics_to_references_works_count_array()
            case 'concept':
                self.add_statistics_to_concept_count_array(min_concept_level = min_concept_level)


    def add_statistics_to_references_works_count_array(self):
        """!
        @brief      Adds a statistics to the references works count array (statistics
                    between the main entitie to compare (second column in the dataframe)
                    and the sum of the other entities)
        """
        pass


    def add_statistics_to_concept_count_array(self, min_concept_level = None):
        """!
        @brief      Adds a statistics to the concepts count array (statistics
                    between the main entitie to compare (second column in the dataframe)
                    and the sum of the other entities)
        """
        # add concept names and levels
        element_count_concepts_serie = self.element_count_df.index.to_series()
        if type(self.element_count_df.index) == pd.Index:
            # Classic pandas index
            element_count_concepts_serie = element_count_concepts_serie.str.strip("https://openalex.org/")
            concept_names_serie = element_count_concepts_serie.apply(lambda c:EntitieNames.concepts_names[c]).convert_dtypes()
            concept_levels_serie = element_count_concepts_serie.apply(lambda c:EntitieNames.concepts_levels[c]).convert_dtypes()
        else:
            # pandas multi index
            concept_names_serie = element_count_concepts_serie.apply(lambda c:EntitieNames.concepts_names[c[0].strip("https://openalex.org/")]).convert_dtypes()
            concept_levels_serie = element_count_concepts_serie.apply(lambda c:EntitieNames.concepts_levels[c[0].strip("https://openalex.org/")]).convert_dtypes()

        self.element_count_df.insert(loc=0, column='concept_name', value=concept_names_serie)
        self.element_count_df.insert(loc=1, column='concept_level', value=concept_levels_serie)

        if min_concept_level != None:
            print(type(min_concept_level))
            print((self.element_count_df.concept_level.iloc[0]))
            self.element_count_df = self.element_count_df.loc[self.element_count_df.concept_level>=min_concept_level]


    def add_authorships_citation_style(self):
        self.entities_df['author_citation_style'] = self.entities_df['authorships'].apply(extract_authorships_citation_style)


    def get_authors_count(self, cols = ['author.id', 'count', 'raw_affiliation_string', 'author.display_name', 'author.orcid']):
        df_authors = pd.json_normalize(self.entities_df['authorships'].explode().to_list())
        authors_count = pd.DataFrame(df_authors.value_counts('author.id'))

        df_authors = df_authors.drop_duplicates('author.id')
        df_authors = df_authors.set_index('author.id')

        authors_count = pd.merge(authors_count, df_authors, how='left', left_index=True, right_index=True).reset_index()

        return authors_count[cols]
        



class AuthorsAnalysis(EntitiesAnalysis, Authors):
    EntitieOpenAlex = Authors
    

class SourcesAnalysis(EntitiesAnalysis, Sources):
    EntitieOpenAlex = Sources


class InstitutionsAnalysis(EntitiesAnalysis, Institutions):
    """!
    @brief      This class contains specific methods for Institutions concepts analysis.
    """
    EntitieOpenAlex = Institutions
 
    def filter_and_format_entitie_data_from_api_response(self, entitie):
        """!
        @brief      Filter and format the institutions data downloaded from the API
        
        @param      entitie  The institutions data from the API (dict)
        
        @return     The institutions datas (dict)
        """
        # delete useless datas
        del entitie['international']
        del entitie['repositories']
        del entitie['country_code'] # already in geo.country_code

        # keep only the first element in the list of theses data
        # display_name_acronym
        if entitie['display_name_acronyms']:
            entitie['display_name_acronym'] = entitie['display_name_acronyms'][0]
        else:
            entitie['display_name_acronym'] = None
        del entitie['display_name_acronyms']
        # display_name_alternative
        if entitie['display_name_alternatives']:
            entitie['display_name_alternative'] = entitie['display_name_alternatives'][0]
        else:
            entitie['display_name_alternative'] = None
        del entitie['display_name_alternatives']

        # # convert the list into dictionnary to allow panda to normalize the data
        # # counts_by_year
        # new_dict = {}
        # for item in entitie['counts_by_year']:
        #    key = item.pop('year')
        #    new_dict[key] = item
        # entitie['counts_by_year'] = new_dict
        # # x_concepts
        # new_dict = {}
        # for i, item in enumerate(entitie['x_concepts']):
        #    key = str(i)
        #    new_dict[key] = item
        # entitie['x_concepts'] = new_dict

        # add computed datas:
        # works_cited_by_count_average
        entitie['works_cited_by_count_average'] = round(entitie['cited_by_count']/entitie['works_count'], 2)
        # concept_score if the downloading list comes from a concept
        if self.entitie_from_type == Concepts:
            # self.entitie_from_id is equal to the concept
            entitie[self.entitie_from_id] = next((item['score'] for item in entitie['x_concepts'] if item['id'] == "https://openalex.org/"+self.entitie_from_id), 0)
            # entitie[concept] = next((item['score'] for key, item in entitie['x_concepts'].items() if item['id'] == "https://openalex.org/"+concept), 0)


    def get_sum_concept_scores(self, institutions, concept_links):
        """!
        @brief      Gets the sum of the concept scores of the concepts in the list
                    concepts
        
        @param      Institutions   The institution (list of dict)
        @param      concept_links  The concept links
        
        @return     The sum of the concept scores
        """
        return sum([item['score'] for item in institutions['x_concepts'] if item['id'] in concept_links])
        

class ConceptsAnalysis(EntitiesAnalysis, Concepts):
    EntitieOpenAlex = Concepts


class PublishersAnalysis(EntitiesAnalysis, Publishers):
    EntitieOpenAlex = Publishers