# Romain THOMAS 2024

import os
from os.path import exists, join, isdir, isfile, expanduser
import psutil
from pathlib import Path
import hashlib  # to generate file names
from time import time
import logging
import tomllib

import pyalex.api
from tqdm import tqdm
import pandas as pd
import requests

from pyalex import Works, Authors, Sources, Institutions, Topics, Concepts, Publishers, config

# define a custom logging
log_oa = logging.getLogger(__name__)
log_oa.addHandler(logging.StreamHandler())
# log_oa.addHandler(logging.FileHandler(__name__ + ".log"))


class AnalysisConfig(dict):
    """
    OpenAlex Analysis configuration class. This class contains the settings used by openalex-analysis (some settings
    are passed to pyalex).

    Tu use it, import the class and set the parameters as follows:
    
    .. code-block:: python

        from openalex_analysis.plot import config

        config.n_max_entities = 10000

    * **email** (*str*) - Your Email for the OpenAlex API. Allows you to use the polite pool (see OpenAlex documentation). The default value is None (not using the polite pool).
    * **api_key** (*str*) - Your OpenAlex API key, if you have one. The default value is None.
    * **openalex_url** (*str*) - OpenAlex API URL or your self-hosted API URL. The default value is "https://api.openalex.org".
    * **http_retry_times** (*int*) - maximum number of retries when querying the OpenAlex API in HTTP. The default value is 3.
    * **disable_tqdm_loading_bar** (*bool*) - To disable the tqdm loading bar. The default is False.
    * **n_max_entities** (*int*) - Maximum number of entities to download (the default value is to download maximum 10 000 entities). If set to None, no limitation will be applied.
    * **project_data_folder_path** (*str*) - Path to the folder containing the data downloaded from the OpenAlex API (these data are stored in compressed parquet files and used as a cache). The default path is "~/openalex-analysis/data".
    * **parquet_compression** (*str*) - Type of compression for the parquet files used as cache (see the Pandas documentation). The default value is "brotli".
    * **max_storage_percent** (*int*) - When the disk capacity reaches this percentage, cached parquet files will be deleted. The default value is 95.
    * **max_storage_files** (*int*) - When the cache folder reaches this number of files, cached parquet files will be deleted. The default value is 10000.
    * **max_storage_size** (*int*) - When the cache folder reached this size (in bytes), cached parquet files will be deleted. The default value is 5e9 (5 GB).
    * **min_storage_files** (*int*) - Before deleting files, we check if we exceed the minimum number of files and folder size. If one of those minimum if exceeded, we allow the program to delete cached parquet files. This is to avoid the setting max_storage_percent to delete every cached file when the disk is almost full. The default value is 1000.
    * **min_storage_size** (*int*) - Before deleting files, we check if we exceed the minimum number of files and folder size. If one of those minimum if exceeded, we allow the program to delete cached parquet files. This is to avoid the setting max_storage_percent to delete every cached file when the disk is almost full. The default value is 5e8 (500 MB).
    * **cache_max_age** (*int*) - Maximum age of the cache in days. The default value is 365.
    * **log_level** (*str*) - The log detail level for openalex-analysis (library specific). The log_level must be 'DEBUG', 'INFO', 'WARNING', 'ERROR' or 'CRITICAL'. The default value 'WARNING'.
    """
    def __getattr__(self, key):
        return super().__getitem__(key)


    def __setattr__(self, key, value):
        if key == "log_level":
            match value:
                case 'DEBUG':
                    log_oa.setLevel(logging.DEBUG)
                case 'INFO':
                    log_oa.setLevel(logging.INFO)
                case 'WARNING':
                    log_oa.setLevel(logging.WARNING)
                case 'ERROR':
                    log_oa.setLevel(logging.ERROR)
                case 'CRITICAL':
                    log_oa.setLevel(logging.CRITICAL)
                case _:
                    raise ValueError("The log_level must be 'DEBUG', 'INFO', 'WARNING', 'ERROR' or 'CRITICAL'")

        return super().__setitem__(key, value)


config = AnalysisConfig()


def set_default_config():
    """
    Set the default configuration of the library. This function is called is no configuration file is found.
    """
    log_oa.info(f"Setting the default configuration")
    config.email = None
    config.api_key = None
    config.openalex_url = "https://api.openalex.org"
    config.http_retry_times = 3
    config.disable_tqdm_loading_bar = False
    config.n_max_entities = 10000
    config.project_data_folder_path = join(expanduser("~"), "openalex-analysis", "data")
    config.parquet_compression = "brotli"
    config.max_storage_percent = 95
    config.max_storage_files = 10000
    config.max_storage_size = 5e9
    config.min_storage_files = 1000
    config.min_storage_size = 5e8
    config.cache_max_age = 365
    config.log_level = 'WARNING'


def load_config_from_file(config_path: str):
    """
    Load and set the configration of the library from a .toml file. When the library is imported, if a configuration
    file exists at "~/openalex-analysis/openalex-analysis-conf.toml", it is automatically loaded.

    :param config_path: The path of the configuration file.
    :type config_path: str
    """
    log_oa.info(f"Loading the configuration from the file {config_path}")
    with open(config_path, "rb") as f:
        config_data = tomllib.load(f)
    if "email" in config_data.keys():
        config.email = config_data['email']
    if "api_key" in config_data.keys():
        config.api_key = config_data['api_key']
    if "openalex_url" in config_data.keys():
        config.openalex_url = config_data['openalex_url']
    if "http_retry_times" in config_data.keys():
        config.http_retry_times = config_data['http_retry_times']
    if "disable_tqdm_loading_bar" in config_data.keys():
        config.disable_tqdm_loading_bar = config_data['disable_tqdm_loading_bar']
    if "n_max_entities" in config_data.keys():
        config.n_max_entities = config_data['n_max_entities']
    if "project_data_folder_path" in config_data.keys():
        config.project_data_folder_path = config_data['project_data_folder_path']
    if "parquet_compression" in config_data.keys():
        config.parquet_compression = config_data['parquet_compression']
    if "max_storage_percent" in config_data.keys():
        config.max_storage_percent = config_data['max_storage_percent']
    if "max_storage_files" in config_data.keys():
        config.max_storage_files = config_data['max_storage_files']
    if "max_storage_size" in config_data.keys():
        config.max_storage_size = config_data['max_storage_size']
    if "min_storage_files" in config_data.keys():
        config.min_storage_files = config_data['min_storage_files']
    if "min_storage_size" in config_data.keys():
        config.min_storage_size = config_data['min_storage_size']
    if "cache_max_age" in config_data.keys():
        config.cache_max_age = config_data['cache_max_age']
    if "log_level" in config_data.keys():
        config.log_level = config_data['log_level']


# if the config file exist, load the configuration from it otherwise load the default configuration
if isfile(join(expanduser("~"), "openalex-analysis","openalex-analysis-conf.toml")):
    load_config_from_file(join(expanduser("~"), "openalex-analysis", "openalex-analysis-conf.toml"))
else:
    set_default_config()


class EntitiesData:
    """
    This class contains methods to download data from the OpenAlex API and manage + cache those datasets locally
    """

    def __init__(self,
                 entity_from_id: str | None = None,
                 extra_filters: dict | None = None,
                 database_file_path: dict | None = None,
                 create_dataframe: bool = True,
                 load_only_columns: list[str] | None = None,
                 ):
        """

        :param entity_from_id: The entity identifier (eg an institution id) from which to take the entities (eg the works of this institution) to analyse. If not provided, the default value is None and the entities will be downloaded bases on the extra_filters value.
        :type entity_from_id: str | None
        :param extra_filters: Optional filters, refer to the documentation of openalex and pyalex for the format. The default value is None.
        :type extra_filters: dict | None
        :param database_file_path: The database file (parquet or csv) path to force the analysis over datas in a specific file. The default value is None to use the data from the OpenAlex API or the cached data.
        :type database_file_path: str | None
        :param create_dataframe: Create the dataframe at the initialisation (and download the data if allowed and entitie_from_id or extra_filters is provided). The default value is True.
        :type create_dataframe: bool
        :param load_only_columns: Load only the specified columns from the parquet file. Everything will be downloaded anyway. The default value is None.
        :type load_only_columns: str | None
        """
        self.per_page = 200  # maximum allowed by the API

        self.entity_from_id = entity_from_id
        self.entity_from_type = None
        self.extra_filters = extra_filters
        self.database_file_path = database_file_path
        self.load_only_columns = load_only_columns

        # a dataframe containing entities related to the instance
        self.entities_df = None

        # # Dataframe with the entities filtered with multi concepts
        # self.entities_multi_filtered_df = None

        # Dataframe with all the element (count_element_type) of the entity(ies) and their count + the count for other
        # entities (optional). The creation needs to be manually started.
        self.element_count_df = pd.DataFrame()

        # to display a loading bar on the web interface
        self.entity_downloading_progress_percentage = 0
        self.create_element_count_array_progress_percentage = 0
        self.create_element_count_array_progress_text = ""
        self.count_element_type = None
        self.count_element_years = None
        self.count_entities_cols = []

        # initialize the values only if entity_from_type is known
        if self.entity_from_id is not None or self.extra_filters is not None:
            if self.entity_from_id is not None:
                self.entity_from_type = self.get_entity_type_from_id(self.entity_from_id)
            if self.database_file_path is None:
                self.database_file_path = join(config.project_data_folder_path, self.get_database_file_name())
            if create_dataframe:
                self.load_entities_dataframe()

    def get_count_entities_matched(self, query_filters: dict) -> int:
        """
        Gets and return the number of entities which match the query filters.

        :param query_filters: The query filters.
        :type query_filters: dict
        :return: The entities count matched.
        :rtype: int
        """
        results, meta = self.EntityOpenAlex().filter(**query_filters).get(per_page=1, return_meta=True)
        return meta['count']

    def get_api_query(self) -> dict:
        """
        Gets the api query from the parameters of the instance.

        :return: The api query
        :rtype: dict
        """
        if self.entity_from_id is not None:
            query_filters = {self.get_entity_type_string_name(self.entity_from_type): {"id": self.entity_from_id}}
            # special cases:
            # concept of institution as the query key word is x_concepts instead of concepts
            if self.get_entity_type_from_id() == Institutions and self.get_entity_type_from_id(
                    self.entity_from_id) == Concepts:
                query_filters = {'x_concepts': {"id": self.entity_from_id}}
            if self.get_entity_type_from_id(self.entity_from_id) == Authors:
                query_filters = {'author': {"id": self.entity_from_id}}
            # when querying authors from an institution, we use the attribute affiliations.institution.id because at the
            # time of the implementation (05/09/2024), the API filter last_known_institutions.id was not working
            if self.EntityOpenAlex == Authors and self.get_entity_type_from_id() == Institutions:
                query_filters = {'affiliations': {'institution': {"id": self.entity_from_id}}}
        else:
            query_filters = {}
        if self.extra_filters is not None:
            query_filters = query_filters | self.extra_filters
        log_oa.info(f"query: {query_filters}")
        return query_filters


    def convert_entities_list_to_df(self, entities_list: list) -> pd.DataFrame:
        """
        Converts a list of entities (a list of PyAlex objects) downloaded from the OpenAlex API into a dataframe.
        :param entities_list: The list of entities (PyAlex objects).
        :param entities_list: list
        :return: The entities in a DataFrame.
        :rtype: pd.DataFrame
        """
        entities_list_df = pd.DataFrame.from_records(entities_list)
        if self.EntityOpenAlex == Works:
            entities_list_df = entities_list_df.rename(columns={'extracted_abstract': 'abstract'})
        return entities_list_df


    def filter_and_format_entity_data_from_api_response(self, entity: dict):
        """
        Filter and format the data downloaded from the API.
        This is a placeholder as not all entity types have this function defined.
        """
        pass


    def download_list_entities(self):
        """
        Downloads the entities which match the parameters of the instance, and store the dataset as a parquet file .
        """
        log_oa.info(f"Downloading list of {self.get_entity_type_string_name()}")
        if self.entity_from_id is not None:
            log_oa.info(f"of the {self.get_entity_type_string_name(self.entity_from_type)[0:-1]} {self.entity_from_id}")
        if self.extra_filters is not None:
            log_oa.info(f"with extra filters: {self.extra_filters}")

        query = self.get_api_query()
        log_oa.info(f"Query to download from the API: {query}")

        count_entities_matched = self.get_count_entities_matched(query)

        if config.n_max_entities is None or config.n_max_entities > count_entities_matched:
            n_entities_to_download = count_entities_matched
            print(f"All the {n_entities_to_download} entities will be downloaded")
            log_oa.info(f"All the {n_entities_to_download} entities will be downloaded")
        else:
            n_entities_to_download = config.n_max_entities
            print(f"Only {n_entities_to_download} entities will be downloaded (out of {count_entities_matched})")
            log_oa.info(f"Only {n_entities_to_download} entities will be downloaded (out of {count_entities_matched})")

        # create a list to store the entities
        entities_list = [None] * n_entities_to_download

        # create the pager entity to iterate over the pages of entities to download
        pager = self.EntityOpenAlex().filter(**query).paginate(per_page=self.per_page, n_max=n_entities_to_download)

        log_oa.info("Downloading the list of entities thought the OpenAlex API...")
        with tqdm(total=n_entities_to_download, disable=config.disable_tqdm_loading_bar) as pbar:
            i = 0
            self.entity_downloading_progress_percentage = 0
            for page in pager:
                # add the downloaded entities in the main list
                for entity in page:
                    self.filter_and_format_entity_data_from_api_response(entity)
                    if i < n_entities_to_download:
                        entities_list[i] = entity
                    else:
                        # useless ?
                        entities_list.append(entity)
                        log_oa.warning("entities_list was too short, appending the entity")
                    i += 1
                # update the progress bar
                pbar.update(self.per_page)
                # update the progress percentage variable
                self.entity_downloading_progress_percentage = i / n_entities_to_download * 100 if i else 0
        self.entity_downloading_progress_percentage = 100

        log_oa.info("Converting the entities list downloaded to a DataFrame...")
        entities_list_df = self.convert_entities_list_to_df(entities_list)

        if not isdir(config.project_data_folder_path):
            log_oa.info("Creating the directory to store the data from OpenAlex")
            os.makedirs(config.project_data_folder_path)
        log_oa.info("Checking space left on disk...")
        self.auto_remove_databases_saved()
        # save as compressed parquet file
        log_oa.info("Saving the list of entities as a parquet file...")
        entities_list_df.to_parquet(self.database_file_path, compression=config.parquet_compression)

    def load_entities_dataframe(self):
        """
        Loads an entities dataset from file (or download it if needed and allowed by the instance) to the dataframe of
        the instance.
        """
        log_oa.info(f"Loading dataframe of {self.get_entity_type_string_name()}")
        if self.entity_from_id is not None:
            log_oa.info(f"of the {self.get_entity_type_string_name(self.entity_from_type)[0:-1]} {self.entity_from_id}")
        if self.extra_filters is not None:
            log_oa.info(f"with extra filters: {self.extra_filters}")

        # # check if the database file exists
        if not exists(self.database_file_path):
            self.download_list_entities()
        # check the age of the cache (aka last date of modification)
        else:
            age_in_days = (time() - os.stat(self.database_file_path).st_mtime) / 86400
            if age_in_days > config.cache_max_age:
                os.remove(self.database_file_path)
                log_oa.info(f"Removed file {self.database_file_path} (age (days): {int(age_in_days)})")
                self.download_list_entities()
        log_oa.info("Loading the list of entities from a parquet file...")
        try:
            self.entities_df = pd.read_parquet(self.database_file_path, columns=self.load_only_columns)
        except:
            # TODO: better manage the exception
            # couldn't load the parquet file (eg no row in parquet file so error because can't find columns to load)
            self.entities_df = pd.DataFrame()

    def auto_remove_databases_saved(self):
        """
        Remove databases files (the cached data downloaded from OpenAlex) if the storage is full, if there are too many
        files or if the cache uses too much space. It keeps the last accessed files with a minimum of files number, and
        folder size.
        """
        def max_cache_storage_usage_reached():
            nb_files = len(os.listdir(config.project_data_folder_path))
            size = sum(f.stat().st_size for f in Path(config.project_data_folder_path).glob('**/*') if f.is_file())
            # if we are reaching the threshold to delete the cache (this is useful if the program is running on a system
            # with a nearly full disk to avoid the limit from config.max_storage_percent to delete every cached file),
            # we check that one of the minimum of files number of folder size is exceeded:
            if nb_files > config.min_storage_files or size > config.min_storage_size:
                if psutil.disk_usage(config.project_data_folder_path).percent > config.max_storage_percent:
                    return True
                if nb_files > config.max_storage_files:
                    return True
                if size > config.max_storage_size:
                    return True
            return False


        while max_cache_storage_usage_reached():
            first_accessed_file = None
            first_accessed_file_time = 0
            for file in os.listdir(config.project_data_folder_path):
                if file.endswith(".parquet"):
                    if os.stat(join(config.project_data_folder_path,
                                    file)).st_atime < first_accessed_file_time or first_accessed_file_time == 0:
                        first_accessed_file_time = os.stat(join(config.project_data_folder_path, file)).st_atime
                        first_accessed_file = file
            if first_accessed_file is None:
                log_oa.warning("No more file to delete.")
                log_oa.warning(f"Space used on disk: {psutil.disk_usage(config.project_data_folder_path).percent} %")
                break
            os.remove(join(config.project_data_folder_path, first_accessed_file))
            log_oa.info(f"Removed file {join(config.project_data_folder_path, first_accessed_file)} "
                        f"(last used: {first_accessed_file_time})")


    def get_database_file_name(self,
                               entity_from_id: str | None = None,
                               entity_type: pyalex.api.BaseOpenAlex | None = None,
                               db_format: str = "parquet"
                               ) -> str:
        """
        Gets the database file name according to the parameters of the object or the arguments given.

        :param entity_from_id: The instance entity identifier (eg a concept id) which was used to filter the entities (eg works) in the database. If nothing is provided, the instance entity id will be used. Default is None.
        :type entity_from_id: str | None
        :param entity_type: The entity type in the database (eg works). If nothing is provided, the instance entity id will be used. Default is None.
        :type entity_type: pyalex.api.BaseOpenAlex | None
        :param db_format: The database file format. The default is "parquet".
        :type db_format: str
        :return: The database file name
        :rtype: str
        """
        if entity_from_id is None:
            entity_from_id = self.entity_from_id
        if entity_type is None:
            entity_type = self.EntityOpenAlex
        file_name = self.get_entity_type_string_name(entity_type)
        if entity_from_id is not None:
            file_name += "_from_" + entity_from_id
        if self.extra_filters is not None:
            file_name += "_" + str(self.extra_filters).replace("'", '').replace(":", '').replace(' ', '_')
        # add the data format version, we increment this number if the format (e.g. columns) change in the parquet file:
        file_name += "_v2"
        # keep the file name below 120 characters and reserve 22 for the max size + parquet extension
        if len(file_name) > 96:
            # sha224 length: 56
            file_name = file_name[:39] + "-" + hashlib.sha224(file_name.encode()).hexdigest()
        file_name += "_max_" + str(config.n_max_entities)
        # add warning for nb max entities to large (>999 999 999 999) because of file name
        return file_name + "." + db_format

    def get_entity_type_string_name(self, entity: pyalex.api.BaseOpenAlex | None = None) -> str:
        """
        Gets the entity type in the format of a string.

        :param entity: The entity type. If nothing is provided, the instance entity type will be used. Default is None.
        :type entity: pyalex.api.BaseOpenAlex | None
        :return: The entity type name in a string
        :rtype: str
        """
        if entity is None:
            entity = self.EntityOpenAlex
        return str(entity).removeprefix("<class 'pyalex.api.").removesuffix("'>").lower()

    def get_entity_type_from_id(self, entity: str | None = None) -> pyalex.api.BaseOpenAlex:
        """
        Gets the entity type from the entity id string.

        :param entity: The entity id. If nothing is provided, the instance entity id will be used. Default is None.
        :type entity: str | None
        :return: The entity type
        :rtype: pyalex.api.BaseOpenAlex
        """
        if entity is None:
            entity = self.entity_from_id
        return get_entity_type_from_id(entity)

    def get_name_of_entity(self, entity: str | None = None) -> str:
        """
        Gets the name of entity from its id.

        :param entity: The entity id, if not provided, use the one from the instance. Default is None.
        :type entity: str
        :return: The name of the entity.
        :rtype: str
        """
        if entity is None:
            entity = self.entity_from_id
            if entity is None:
                raise ValueError("No entity id provided, can't get the name of the entity")
        return get_name_of_entity(entity)

    def get_info_about_entity(self,
                              entity: str | None = None,
                              infos: list[str] | None = None,
                              return_as_pd_series: bool = True,
                              ) -> dict | pd.Series:
        """
        Get information about the entity (eg. name, publication_date...). If no entity is provided, the entity_from_id will be used.

        :param entity: The entity id, if not provided, use the one from the instance. Default is None.
        :type entity: str | None
        :param infos: The information fields to get. Default is None, which will get ["display_name"].
        :type infos: list[str] | None
        :param return_as_pd_series: True to return the results as a Pandas Series. Otherwise, a dictionary is returned. Default is True.
        :type return_as_pd_series: bool
        :return:
        :rtype:
        """
        if entity is None:
            entity = self.entity_from_id
            if entity is None:
                raise ValueError("Can't get the entity info of None")
        return get_info_about_entity(entity, infos=infos, return_as_pd_series=return_as_pd_series)


    def get_multiple_entities_from_id(self, ids: list[str],
                                      ordered: bool = True,
                                      return_dataframe: bool = True) -> pd.DataFrame | list:
        """
        Get multiple entities from their OpenAlex IDs by querying them to the OpenAlex API 100 by 100.

        :param ids: the list of OpenAlex IDs to query
        :type ids: list[str]
        :param ordered: keep the order of the input list in the output list. Default is True.
        :type ordered: bool
        :param return_dataframe: Return a Dataframe. If True, the DataFrame returned will also be stored in self.entities_df and the cache system will be used. If False, a list will be returned. Default is True.
        :type return_dataframe: bool
        :return: the list of entities as pyalex objects (dictionaries) or DataFrame.
        :rtype: pd.DataFrame | list
        """
        res = [] * len(ids)
        i = 0
        with tqdm(total=len(ids), disable=config.disable_tqdm_loading_bar) as pbar:
            # reduce 100 if too big for OpenAlex
            while i + 100 < len(ids):
                res[i:i+100] = self.EntityOpenAlex().filter(ids={'openalex': '|'.join(ids[i:i+100])}).get(per_page=100)
                i += 100
                pbar.update(100)
            res[i:] = self.EntityOpenAlex().filter(ids={'openalex': '|'.join(ids[i:])}).get(per_page=100)
            pbar.update(len(ids) % 100)

        if ordered:
            # sort the res list with the order provided in the list ids
            # create a dictionary with each id as key and the index in the res list as value
            res_ids_index = {entity['id'][21:]: i for i, entity in enumerate(res) if entity is not None}
            # sort based on the index
            res = [res[res_ids_index[entity_id]] if res_ids_index.get(entity_id) is not None else None
                   for entity_id in ids]

        if return_dataframe:
            # similar to the download function, apply the needed formatting (e.g. extracting the abstract for works)
            for i in range(len(res)):
                if res[i] is not None:
                    self.filter_and_format_entity_data_from_api_response(res[i])
            res = self.convert_entities_list_to_df(res)
        return res

def get_entity_type_from_id(entity: str) -> pyalex.api.BaseOpenAlex:
    """
     Gets the entity type from the entity id string.

    :param entity: The entity id, if not provided, use the one from the instance. Default is None.
    :type entity: str | None
    :return: The entity type
    :rtype: pyalex.api.BaseOpenAlex
    """
    match entity[0]:
        case 'W':
            return Works
        case 'A':
            return Authors
        case 'S':
            return Sources
        case 'I':
            return Institutions
        case 'T':
            return Topics
        case 'C':
            return Concepts
        case 'P':
            return Publishers
        case _:
            raise ValueError("Entity id " + entity + " not valid")


def get_name_of_entity(entity: str) -> str:
    """
    Gets the name of the entity from the api.

    :param entity: The entity id.
    :type entity: str
    :return: The name of the entity.
    :rtype: str
    """
    # call the API
    e = get_entity_type_from_id(entity)()[entity]
    return e['display_name']


def extract_authorships_citation_style(authorships: dict) -> str:
    """
    Create a string to cite the authors from an authorships dictionary.

    :param authorships: The authorships dictionary.
    :type authorships: dict
    :return: The citation string.
    :rtype: str
    """
    if len(authorships) == 0:
        res = "Unknown author"
    else:
        res = authorships[0]['author']['display_name']
    if len(authorships) >= 2:
        res += ", " + authorships[1]['author']['display_name']
    if len(authorships) > 2:
        res += " et al."
    return res


def get_info_about_entity(entity: str, infos: list[str] | None = None,
                          return_as_pd_series: bool = True) -> str | pd.Series:
    """

    :param entity: The entity id.
    :type entity: str
    :param infos: The information to get (see OpenAlex API documentation). You can also request "author_citation_style" to get a citation string for the authors. The default is None, which will get ["display_name"].
    :type infos: list[str] | None
    :param return_as_pd_series: True to return the results as a Pandas Series. Otherwise, a dictionary is returned. Default is True.
    :type return_as_pd_series: bool
    :return: The entity information.
    :rtype: str | pd.Series
    """
    if infos is None:
        infos = ["display_name"]
    e = get_entity_type_from_id(entity)()[entity]
    if "author_citation_style" in infos:
        e["author_citation_style"] = extract_authorships_citation_style(e["authorships"])
    res = {key: val for key, val in e.items() if key in infos}
    if return_as_pd_series:
        data = [val for val in res.values()]
        index = [key for key in res]
        res = pd.Series(data=data, index=index)
    return res


def check_if_entity_exists(entity: str) -> bool:
    """
    Check if the entity exists.
    TODO: check status code for existence of entity as other errors can occur.

    :param entity: The entity id.
    :type entity: str
    :return: True if the entity exists.
    :rtype: bool
    """
    # get the name of the entity
    api_path = str(entity).removeprefix("<class 'pyalex.api.").removesuffix("'>").lower() + "s"
    # call the API
    response = requests.get("https://api.openalex.org/" + api_path + "/" + entity)
    if response.status_code == 404:
        return False
    else:
        return True


class WorksData(EntitiesData, Works):
    """
    This class contains specific methods for Works entity data.
    """
    EntityOpenAlex = Works

    def filter_and_format_entity_data_from_api_response(self, entity: dict):
        """
        Filter and format the works data downloaded from the API.
        :param entity: The works data from the API.
        :type entity: dict
        :return: The works datas.
        :rtype: dict
        """

        # Store the abstract as a string (here, we avoid the key "abstract" as PyAlex redefined __getitem__() for it)
        entity['extracted_abstract'] = entity['abstract']
        # as we store the abstract as a string, we can delete its inverted index
        del entity['abstract_inverted_index']

    def add_authorships_citation_style(self):
        """
        Add the author_citation_style column to the DataFrame entities_df
        """
        self.entities_df['author_citation_style'] = self.entities_df['authorships'].apply(
            extract_authorships_citation_style)


    def get_multiple_works_from_doi(self, dois: list[str],
                                    ordered: bool = True,
                                    return_dataframe: bool = True) -> pd.DataFrame | list:
        """
        Get multiple works from their DOI by querying them to the OpenAlex API 60 by 60.

        :param dois: the list of DOIs to query
        :type dois: list[str]
        :param ordered: keep the order of the input list in the output list. Default is True.
        :type ordered: bool
        :param return_dataframe: Return a Dataframe. If True, the DataFrame returned will also be stored in self.entities_df and the cache system will be used. If False, a list will be returned. Default is True.
        :type return_dataframe: bool
        :return: the list of works as pyalex objects (dictionaries) or DataFrame.
        :rtype: pd.DataFrame | list
        """
        res = [] * len(dois)
        i = 0
        with tqdm(total=len(dois), disable=config.disable_tqdm_loading_bar) as pbar:
            # querying more than 60 DOIs causes the HTTP query size being larger than what OpenAlex allows
            while i + 60 < len(dois):
                res[i:i+60] = Works().filter(doi='|'.join(dois[i:i+60])).get(per_page=60)
                i += 60
                pbar.update(60)
            res[i:] = Works().filter(doi='|'.join(dois[i:])).get(per_page=60)
            pbar.update(len(dois) % 60)

        if ordered:
            # sort the res list with the order provided in the list dois
            # create a dictionary with each doi as key and the index in the res list as value
            # we use lower as the doi can be valid with either lower or upper cases
            res_dois_index = {entity['doi'].lower(): i for i, entity in enumerate(res) if entity is not None}
            # sort based on the index
            res = [res[res_dois_index[entity_doi.lower()]] if res_dois_index.get(entity_doi.lower()) is not None else None
                   for entity_doi in dois]

        if return_dataframe:
            # similar to the download function, apply the needed formatting (e.g. extracting the abstract)
            for i in range(len(res)):
                if res[i] is not None:
                    self.filter_and_format_entity_data_from_api_response(res[i])
            res = self.convert_entities_list_to_df(res)
        return res


class AuthorsData(EntitiesData, Authors):
    """
    This class contains specific methods for Authors entity data. Not used for now.
    """
    EntityOpenAlex = Authors


class SourcesData(EntitiesData, Sources):
    """
    This class contains specific methods for Sources entity data. Not used for now.
    """
    EntityOpenAlex = Sources


class InstitutionsData(EntitiesData, Institutions):
    """
    This class contains specific methods for Institutions entity data. Not used for now.
    """
    EntityOpenAlex = Institutions


class ConceptsData(EntitiesData, Concepts):
    """
    This class contains specific methods for Concepts entity data. Not used for now.
    """
    EntityOpenAlex = Concepts


class TopicsData(EntitiesData, Topics):
    """
    This class contains specific methods for Topics entity data. Not used for now.
    """
    EntityOpenAlex = Topics


class PublishersData(EntitiesData, Publishers):
    """
    This class contains specific methods for Publishers entity data. Not used for now.
    """
    EntityOpenAlex = Publishers
