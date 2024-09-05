# Romain THOMAS 2024
# Stockholm Resilience Centre, Stockholm University

import os
from os.path import exists, join  # To check if a file exist
import psutil
import hashlib  # to generate file names
import logging
from collections import Counter

import pyalex.api
from tqdm import tqdm
import pandas as pd
import country_converter as coco
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

    * **email** (*string*) - Your Email for the OpenAlex API. Allows you to use the polite pool (see OpenAlex documentation). The default value is None (not using the polite pool).
    * **api_key** (*string*) - Your OpenAlex API key, if you have one. The default value is None.
    * **openalex_url** (*string*) - OpenAlex API URL or your self-hosted API URL. The default value is "https://api.openalex.org".
    * **http_retry_times** (*int*) - maximum number of retries when querying the OpenAlex API in HTTP. The default value is 3.
    * **disable_tqdm_loading_bar** (*bool*) - To disable the tqdm loading bar. The default is False.
    * **n_max_entities** (*int*) - Maximum number of entities to download (the default value is to download maximum 10 000 entities). If set to None, no limitation will be applied.
    * **project_datas_folder_path** (*string*) - Path to the folder containing the data downloaded from the OpenAlex API (these data are stored in compressed parquet files and used as a cache). The default path is "./data".
    * **parquet_compression** (*string*) - Type of compression for the parquet files used as cache (see the Pandas documentation). The default value is "brotli".
    * **max_storage_percent** (*int*) - When the disk capacity reaches this percentage, cached parquet files will be deleted. The default value is 95.
    * **log_level** (*string*) - The log detail level for openalex-analysis (library specific). The log_level must be 'DEBUG', 'INFO', 'WARNING', 'ERROR' or 'CRITICAL'. The default value 'WARNING'.
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


config = AnalysisConfig(email=None,
                        api_key=None,
                        openalex_url="https://api.openalex.org",
                        http_retry_times=3,
                        disable_tqdm_loading_bar=False,
                        n_max_entities=10000,
                        project_datas_folder_path="data",
                        parquet_compression="brotli",
                        max_storage_percent=95,
                        log_level='WARNING',
                        )


class EntitiesData:
    """
    This class contains methods to download data from the OpenAlex API and manage + cache those datasets locally
    """
    # to convert country code to country name
    cc = coco.CountryConverter()

    def __init__(self,
                 entity_from_id: str | None = None,
                 extra_filters: dict | None = None,
                 database_file_path: dict | None = None,
                 create_dataframe: bool = True,
                 load_only_columns: list[str] | None = None,
                 ):
        """

        :param entity_from_id: The entity identifier (eg an institution id) from which to take the entities (eg the works of this institution) to analyse. If not provided, the default value is None and the entities will be downloaded bases on the extra_filters value.
        :type entity_from_id: string | None
        :param extra_filters: Optional filters, refer to the documentation of openalex and pyalex for the format. The default value is None.
        :type extra_filters: dict | None
        :param database_file_path: The database file (parquet or csv) path to force the analysis over datas in a specific file. The default value is None to use the data from the OpenAlex API or the cached data.
        :type database_file_path: string | None
        :param create_dataframe: Create the dataframe at the initialisation (and download the data if allowed and entitie_from_id or extra_filters is provided). The default value is True.
        :type create_dataframe: bool
        :param load_only_columns: Load only the specified columns from the parquet file. Everything will be downloaded anyway. The default value is None.
        :type load_only_columns: string | None
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
                self.database_file_path = join(config.project_datas_folder_path, self.get_database_file_name())
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
            query_filters = {self.get_entity_type_as_string(self.entity_from_type): {"id": self.entity_from_id}}
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

    def filter_and_format_entity_data_from_api_response(self, entity: dict):
        """
        Filter and format the data downloaded from the API.
        This is a placeholder as not all entity types have this function defined.
        """


    def download_list_entities(self):
        """
        Downloads the entities which match the parameters of the instance, and store the dataset as a parquet file .
        """
        log_oa.info(f"Downloading list of {self.get_entity_type_as_string()}")
        if self.entity_from_id is not None:
            log_oa.info(f"of the {self.get_entity_type_as_string(self.entity_from_type)[0:-1]} {self.entity_from_id}")
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
                    # raise ValueError("toto stop")
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

        # normalize the json format (one column for each field)
        log_oa.info("Normalizing the json data downloaded...")
        entities_list_df = pd.json_normalize(entities_list)
        if not os.path.isdir(config.project_datas_folder_path):
            log_oa.info("Creating the directory to store the data from OpenAlex")
            os.makedirs(config.project_datas_folder_path)
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
        log_oa.info(f"Loading dataframe of {self.get_entity_type_as_string()}")
        if self.entity_from_id is not None:
            log_oa.info(f"of the {self.get_entity_type_as_string(self.entity_from_type)[0:-1]} {self.entity_from_id}")
        if self.extra_filters is not None:
            log_oa.info(f"with extra filters: {self.extra_filters}")

        # # check if the database file exists
        if not exists(self.database_file_path):
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
        Remove databases files (the data downloaded from OpenAlex) if the storage is full. It keeps the last accessed
        files.
        """
        while psutil.disk_usage(config.project_datas_folder_path).percent > config.max_storage_percent:
            first_accessed_file = None
            first_accessed_file_time = 0
            for file in os.listdir(config.project_datas_folder_path):
                if file.endswith(".parquet"):
                    if os.stat(join(config.project_datas_folder_path,
                                    file)).st_atime < first_accessed_file_time or first_accessed_file_time == 0:
                        first_accessed_file_time = os.stat(join(config.project_datas_folder_path, file)).st_atime
                        first_accessed_file = file
            if first_accessed_file is None:
                log_oa.warning("No more file to delete.")
                log_oa.warning(f"Space used on disk: {psutil.disk_usage(config.project_datas_folder_path).percent} %")
                break
            os.remove(join(config.project_datas_folder_path, first_accessed_file))
            log_oa.info(f"Removed file {join(config.project_datas_folder_path, first_accessed_file)} "
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
        file_name = self.get_entity_type_as_string(entity_type)
        if entity_from_id is not None:
            file_name += "_from_" + entity_from_id
        if self.extra_filters is not None:
            file_name += "_" + str(self.extra_filters).replace("'", '').replace(":", '').replace(' ', '_')
        # keep the file name below 120 characters and reserve 22 for the max size + parquet extension (csv extension
        # is shorter)
        if len(file_name) > 96:
            # sha224 length: 56
            file_name = file_name[:39] + "-" + hashlib.sha224(file_name.encode()).hexdigest()
        file_name += "_max_" + str(config.n_max_entities)
        # add warning for nb max entities to large (>999 999 999 999) because of file name
        return file_name + "." + db_format

    # TODO: rename function to get_entitie_type_string_name
    def get_entity_type_as_string(self, entity: pyalex.api.BaseOpenAlex | None = None) -> str:
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


    def get_multiple_entities_from_id(self, ids: list[str], ordered: bool = True) -> list:
        """
        Get multiple entities from their OpenAlex IDs by querying them to the OpenAlex API 100 by 100.

        :param ids: the list of OpenAlex IDs to query
        :type ids: list[str]
        :param ordered: keep the order of the input list in the output list. Default is True.
        :type ordered: bool
        :return: the list of entities as pyalex objects (dictionaries)
        :rtype: list[]
        """
        res = [None] * len(ids)
        i = 0
        with tqdm(total=len(ids), disable=config.disable_tqdm_loading_bar) as pbar:
            # reduce 100 if too big for OpenAlex
            while i + 100 < len(ids):
                res[i:i+100] = self.EntityOpenAlex().filter(ids={'openalex': '|'.join(ids[i:i+100])}).get(per_page=100)
                i += 100
                pbar.update(100)
            res[i:] = self.EntityOpenAlex().filter(ids={'openalex': '|'.join(ids[i:])}).get(per_page=100)
            pbar.update(len(ids) % 100)

        if not ordered:
            return res
        else:
            # sort the res list with the order provided in the list ids
            # create a dictionary with each id as key and the index in the res list as value
            res_ids_index = {entity['id'][21:]: i for i, entity in enumerate(res) if entity is not None}
            # sort based on the index
            res = [res[res_ids_index[entity_id]] if res_ids_index.get(entity_id) is not None else None for entity_id in ids]
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


def get_multiple_works_from_doi(dois: list[str], ordered: bool = True) -> list:
    """
    Get multiple works from their DOI by querying them to the OpenAlex API 60 by 60.

    :param dois: the list of DOIs to query
    :type dois: list[str]
    :param ordered: keep the order of the input list in the output list. Default is True.
    :type ordered: bool
    :return: the list of works as pyalex objects (dictionaries)
    :rtype: list[]
    """
    res = [None] * len(dois)
    i = 0
    with tqdm(total=len(dois), disable=config.disable_tqdm_loading_bar) as pbar:
        # querying more than 60 DOIs causes the HTTP query size being larger than what OpenAlex allows
        while i + 60 < len(dois):
            res[i:i+60] = Works().filter(doi='|'.join(dois[i:i+60])).get(per_page=60)
            i += 60
            pbar.update(60)
        res[i:] = Works().filter(doi='|'.join(dois[i:])).get(per_page=60)
        pbar.update(len(dois) % 60)

    if not ordered:
        return res
    else:
        # sort the res list with the order provided in the list dois
        # create a dictionary with each doi as key and the index in the res list as value
        # we use lower as the doi can be valid with either lower or upper cases
        res_dois_index = {entity['doi'].lower(): i for i, entity in enumerate(res) if entity is not None}
        # sort based on the index
        res = [res[res_dois_index[entity_doi.lower()]] if res_dois_index.get(entity_doi.lower()) is not None else None for entity_doi in dois]
        return res


class EntitiesAnalysis(EntitiesData):
    """
    This class contains generic methods to analyse entities.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # variables for the collaborations with institutions dataframe:
        self.collaborations_with_institutions_entities_from_metadata = pd.DataFrame() # ids and metadata of the entities
        # for which to look for their collaborations
        self.collaborations_with_institutions_df = pd.DataFrame() # list of the collaborations
        self.collaborations_with_institutions_year = None # years used to calculate the collaborations

    def get_collaborations_with_institutions(self,
                                             entities_from: list[str] | None = None,
                                             institutions_to_exclude: dict[str, list[str]] | None = None,
                                             year: int | str | None = None,
                                             extra_filters_for_entities_from: dict | None = None
                                             ) -> pd.DataFrame:
        """
        Create the collaborations_with_institutions_df DataFrame.

        :param entities_from: The list of entities to use to count the collaborations. If None, the entity_from_id is used.
        :type entities_from: list[str]
        :param institutions_to_exclude: For each entities_from (key), the list of institutions (value) to exclude when counting the collaborations. For example, it is usefull to exclude the parent institution.
        :type institutions_to_exclude: dict[str, list[str]]
        :param year: The years for which to look for the collaborations. Can be an integer or a string. You can provide a range of years as a string (e.g. "2020-2023")
        :type year: int | str | None
        :param extra_filters_for_entities_from: Filters to be used when downloading the datasets of works to extract the collaboration. If you want to use {'publication_year':2023}, you should use the year parameter and not provide extra_filters_for_entities_from. The extra filter won't be used to generate the links on the plot to check the collaboration works
        :type extra_filters_for_entities_from: dict | None
        :return: The collaborations_with_institutions_df DataFrame
        :rtype: pd.DataFrame
        """
        if entities_from is None:
            if self.entity_from_id is None:
                raise ValueError("You must either provide the entities_from or the entity_from_id when instantiating the object.")
            entities_from = [self.entity_from_id]
        if institutions_to_exclude is None:
            institutions_to_exclude = {}
        if extra_filters_for_entities_from is None:
            extra_filters_for_entities_from = {}
        if year is not None:
            extra_filters_for_entities_from['publication_year'] = year
        self.collaborations_with_institutions_year = year

        # get entities_from metadata
        self.collaborations_with_institutions_entities_from_metadata = [pd.DataFrame()] * len(entities_from)
        for i, entity_id in tqdm(enumerate(entities_from),
                                      total=len(self.collaborations_with_institutions_entities_from_metadata),
                                      desc="Getting entities_from metadata"):
            if get_entity_type_from_id(entity_id) == Institutions:
                inst_obj = Institutions()[entity_id]
                self.collaborations_with_institutions_entities_from_metadata[i] = {'id': inst_obj['id'][21:],
                                                'name': inst_obj['display_name'],
                                                'lat': inst_obj['geo']['latitude'],
                                                'lon': inst_obj['geo']['longitude'],
                                                'country': inst_obj['geo']['country'],
                                                }
            elif get_entity_type_from_id(entity_id) == Authors:
                inst_obj = Authors()[entity_id]
                self.collaborations_with_institutions_entities_from_metadata[i] = {'id': inst_obj['id'][21:],
                                                'name': inst_obj['display_name'],
                                                }
            else:
                raise ValueError("The entity type provided is not valid (only Institutions and Authors are supported).")
        self.collaborations_with_institutions_entities_from_metadata = pd.DataFrame(self.collaborations_with_institutions_entities_from_metadata).set_index('id')

        self.collaborations_with_institutions_df = [pd.DataFrame()] * len(entities_from)
        for i, institution_from in enumerate(entities_from):
            log_oa.info(f"Processing {institution_from}"
                        f"({self.collaborations_with_institutions_entities_from_metadata.at[institution_from, 'name']})"
                        f"...")
            # get the institutions to exclude for this institution
            institutions_to_exclude_i = institutions_to_exclude.get(institution_from)
            # if there is no institution to exclude, we only exclude the institution_from
            if institutions_to_exclude_i is None:
                institutions_to_exclude_i = [institution_from]
            else:
                institutions_to_exclude_i.append(institution_from)
            log_oa.info(f"Excluding {len(institutions_to_exclude_i)} institution: {institutions_to_exclude_i}")
            # add the https://openalex.org/ at the beggining of each id
            institutions_to_exclude_i = ["https://openalex.org/" + institution for institution in institutions_to_exclude_i]

            if extra_filters_for_entities_from != {}:
                works = WorksAnalysis(institution_from, extra_filters = extra_filters_for_entities_from)
            else:
                works = WorksAnalysis(institution_from)
            # get the list of institutions who collaborated per work:
            collaborations_per_work = [list(set([institution['id'] for author in work for institution in author['institutions']])) for work in works.entities_df['authorships'].to_list()]
            # list of the institutions we collaborated with
            institutions_collaborations = set(list([institution for institutions in collaborations_per_work for institution in institutions if institution not in institutions_to_exclude_i]))
            log_oa.info(f"{len(institutions_collaborations)} unique institutions with which "
                        f"{self.collaborations_with_institutions_entities_from_metadata.at[institution_from, 'name']} "
                        f"collaborated")
            # remove the https://openalex.org/ at the beginning
            institutions_collaborations = [institution_id[21:] for institution_id in institutions_collaborations]
            # count the number of collaboration per institutions:
            # collaborations_per_work contains the institutions we collaborated per work, so we
            # can count on how many works we collaborated with each institution
            institutions_count_dict = Counter(list([institution for institutions in collaborations_per_work for institution in institutions if institution not in institutions_to_exclude_i]))

            # create dictionaries with the institution id as key and lon, lat and name as item
            institutions_name = [None] * len(institutions_collaborations)
            institutions_id = [None] * len(institutions_collaborations)
            institutions_lat = [None] * len(institutions_collaborations)
            institutions_lon = [None] * len(institutions_collaborations)
            institutions_country = [None] * len(institutions_collaborations)
            institutions_count = [None] * len(institutions_collaborations)
            institutions = InstitutionsAnalysis().get_multiple_entities_from_id(institutions_collaborations)
            for j, institution in enumerate(institutions):
                institutions_name[j] = institution['display_name']
                institutions_id[j] = institution['id'][21:] # remove https://openalex.org/
                institutions_lat[j] = institution['geo']['latitude']
                institutions_lon[j] = institution['geo']['longitude']
                institutions_country[j] = institution['geo']['country']
                institutions_count[j] = institutions_count_dict[institution['id']]

            # store in a dataframe
            self.collaborations_with_institutions_df[i] = pd.DataFrame(list(zip(institutions_name,
                                                         institutions_id,
                                                         institutions_lat,
                                                         institutions_lon,
                                                         institutions_country,
                                                         [institution_from] * len(institutions_collaborations),
                                                         [self.collaborations_with_institutions_entities_from_metadata.at[institution_from, 'name']] * len(institutions_collaborations),
                                                         institutions_count
                                                        )), columns = ['name', 'id', 'lat', 'lon', 'country', 'id_from', 'name_from', 'count'])

            self.collaborations_with_institutions_df[i] = self.collaborations_with_institutions_df[i].sort_values('count', ascending=False)

        self.collaborations_with_institutions_df = pd.concat(self.collaborations_with_institutions_df, ignore_index=True)

        # add the link to consult the collaborations works
        if year is not None:
            self.collaborations_with_institutions_df['link_to_works'] = "https://explore.openalex.org/works?filter=authorships.institutions.lineage:"+self.collaborations_with_institutions_df.id+",authorships.institutions.lineage:"+self.collaborations_with_institutions_df.id_from+",publication_year:"+year
        else:
            self.collaborations_with_institutions_df['link_to_works'] = "https://explore.openalex.org/works?filter=authorships.institutions.lineage:"+self.collaborations_with_institutions_df.id+",authorships.institutions.lineage:"+self.collaborations_with_institutions_df.id_from

        return self.collaborations_with_institutions_df


class WorksAnalysis(EntitiesAnalysis, Works):
    """
    This class contains specific methods for Works entity analysis.
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

        # Store the abstract as a string
        entity['abstract'] = entity['abstract']
        # as we store the abstract as a string, we can delete its inverted index
        del entity['abstract_inverted_index']

        # # add computed datas:
        # # concept_score if the downloading list comes from a concept
        # if self.entity_from_type == Concepts:
        #     # self.entity_from_id is equal to the concept
        #     entity[self.entity_from_id] = float(next((item['score'] for item in entity['concepts'] if
        #                                               item['id'] == "https://openalex.org/" + self.entity_from_id),
        #                                              0))
        # # country_name
        # country_code = self.get_country_code(entity)
        # if country_code is not None:
        #     entity['country_name'] = self.cc.convert(names=[self.get_country_code(entity)], to='name_short')
        # else:
        #     entity['country_name'] = None
        # # institution_name
        # entity['institution_name'] = self.get_institution_name(entity)

    # def get_country_code(self, entity: dict) -> str | None:
    #     """
    #     Get the country code from an entity.
    #
    #     :param entity: The entity.
    #     :type entity: dict
    #     :return: The country code.
    #     :rtype: str
    #     """
    #     if entity['authorships'] != [] and entity['authorships'][0]['institutions'] != [] and 'country_code' in \
    #             entity['authorships'][0]['institutions'][0]:
    #         return entity['authorships'][0]['institutions'][0]['country_code']
    #     else:
    #         return None
    #
    # def get_institution_name(self, entity: dict) -> str | None:
    #     """
    #     Get the institution name from an entity.
    #
    #     :param entity: The entity.
    #     :type entity: dict
    #     :return: The institution name.
    #     :rtype: str
    #     """
    #     if entity['authorships'] != [] and entity['authorships'][0]['institutions'] != [] and 'display_name' in \
    #             entity['authorships'][0]['institutions'][0]:
    #         return entity['authorships'][0]['institutions'][0]['display_name']
    #     else:
    #         return None

    def get_works_references_count(self, count_years: list[int] | None = None) -> pd.Series:
        """
        Count the number of times each referenced work is used.

        :param count_years: List of years to count the references. The default value is None to not count by years.
        :type count_years: list[int]
        :return: The works references count.
        :rtype: pd.Series
        """
        log_oa.info(f"Creating the works references count of {self.get_entity_type_as_string()}...")
        if count_years is None:
            return self.entities_df['referenced_works'].explode().value_counts().convert_dtypes()
        else:
            counts_df_list = [None] * len(count_years)
            for i, year in enumerate(count_years):
                counts_df_list[i] = self.entities_df[self.entities_df.publication_year == year][
                    'referenced_works'].explode().value_counts().convert_dtypes()
            entities_count = pd.concat(counts_df_list, axis=1, keys=count_years).reset_index().fillna(0)
            entities_count = entities_count.set_index('referenced_works').stack()
            entities_count.name = 'count'
            return entities_count

    def get_works_concepts_count(self, count_years: list[int] | None = None) -> pd.Series:
        """
        Count the number of times each concept is used.

        :param count_years: List of years to count the concepts. The default value is None to not count by years.
        :type count_years: list[int]
        :return: The concept count.
        :rtype: pd.Series
        """
        log_oa.info(f"Creating the concept count of {self.get_entity_type_as_string()}...")
        if count_years is None:
            return self.entities_df['concepts'].explode().apply(
                lambda c: c['id'] if type(c) == dict else None).value_counts().convert_dtypes()
        else:
            counts_df_list = [None] * len(count_years)
            for i, year in enumerate(count_years):
                counts_df_list[i] = self.entities_df[self.entities_df.publication_year == year][
                    'concepts'].explode().apply(
                    lambda c: c['id'] if type(c) == dict else None).value_counts().convert_dtypes()
            entities_count = pd.concat(counts_df_list, axis=1, keys=count_years).reset_index().fillna(0)
            entities_count = entities_count.set_index('concepts').stack()
            entities_count.name = 'count'
            return entities_count

    def get_element_count(self, element_type: str, count_years: list[int] | None = None) -> pd.Series:
        """
        Count the number of times each element (for now references or concepts) is used by year (optional) by the
        entity.

        :param element_type: The element type ('reference' or 'concept').
        :type element_type: str
        :param count_years: List of years to count the concepts. The default value is None to not count by years.
        :type count_years: list[int]
        :return: The element count.
        :rtype: pd.Series
        """
        match element_type:
            case 'reference':
                return self.get_works_references_count(count_years=count_years)
            case 'concept':
                return self.get_works_concepts_count(count_years=count_years)
            case _:
                raise ValueError("Can only count for 'references' or 'concept'")

    def create_element_used_count_array(self,
                                        element_type: str,
                                        entities_from: list[dict] | None = None,
                                        out_file_name: str | None = None,
                                        # save_out_array: bool = False,
                                        count_years: list[int] | None = None
                                        ):
        """
        Creates the element used count array. Count the number of times each element (eg references, concepts...) are
        used and save the array as CSV (optional).

        :param element_type: The element type ('reference' or 'concept').
        :type element_type: str
        :param entities_from: The extra entities to which to count the concepts.
        :type entities_from: list[dict]
        :param out_file_name: The out CSV file name, if not provided, an appropriate name is generated. The default value is None.
        :type out_file_name: str
        :param save_out_array: True to save the out array. The default value is False
        :type save_out_array: bool
        :param count_years: If given, it will compute the count for each year separately
        :type count_years: list[int]
        """
        self.count_element_type = element_type
        self.count_element_years = count_years
        self.count_entities_cols = []
        match self.count_element_type:
            case 'reference':
                cols_to_load = ['id', 'referenced_works', 'publication_year']
            case 'concept':
                cols_to_load = ['id', 'concepts', 'publication_year']
            case _:
                raise ValueError("Can only count for 'references' or 'concept'")

        if self.entity_from_id is None and entities_from == []:
            raise ValueError(
                "You need either to instance the object with an entity_from_id or to provide entities_from to "
                "create_element_used_count_array()")
        # TODO: add parameter to drop references not in the entity to compare from : useless as we can not import it
        # if out_file_name is None:
        #     if self.entity_from_id is None:
        #         out_file_name = self.count_element_type + "s_" + self.get_entity_string_name() + "_of_diverse_entities"
        #     else:
        #         out_file_name = self.count_element_type + "s_" + self.get_entity_string_name() + "_of_" + self.get_entity_string_name(
        #             self.get_entity_type_from_id(self.entity_from_id))[0:-1] + "_" + self.entity_from_id
        #     out_file_name += ".csv"
        #     out_file_name = join(config.project_datas_folder_path, out_file_name)

        self.element_count_df = pd.DataFrame()
        self.element_count_df.index.name = self.count_element_type + "s"

        self.create_element_count_array_progress_percentage = 0
        self.create_element_count_array_progress_text = "Creating the " + self.count_element_type + "s array..."

        # Create the count array for the first/main entity if previously added to object
        if self.entity_from_id is not None:
            col_name = self.entity_from_id + " " + self.get_name_of_entity()
            self.count_entities_cols.append(col_name)
            if len(self.entities_df.index) == 0:
                self.element_count_df[col_name] = pd.Series().convert_dtypes()
            else:
                self.element_count_df = pd.concat(
                    [self.element_count_df, self.get_element_count(self.count_element_type, count_years=count_years)],
                    axis=1)
                self.element_count_df = self.element_count_df.rename(columns={'count': col_name})

        if count_years is not None:
            for i, entity in enumerate(entities_from):
                self.create_element_count_array_progress_percentage = int(i / len(entities_from) * 100)
                # initialise the WorksAnalysis instance
                works = WorksAnalysis(**entity, load_only_columns=cols_to_load)
                col_name = works.entity_from_id + " " + works.get_name_of_entity()
                self.count_entities_cols.append(col_name)
                # if there is no data in the dataframe, we add a blank column
                if len(works.entities_df.index) == 0:
                    self.element_count_df[col_name] = pd.Series().convert_dtypes()
                else:
                    self.element_count_df = pd.concat(
                        [self.element_count_df,
                         works.get_element_count(self.count_element_type, count_years=count_years)],
                        axis=1)
                    self.element_count_df = self.element_count_df.rename(columns={'count': col_name})
            self.element_count_df.index = self.element_count_df.index.set_names('element', level=0)
            self.element_count_df.index = self.element_count_df.index.set_names('year', level=1)
        else:
            self.element_count_df.index.name = 'element'

        self.create_element_count_array_progress_percentage = 100

        # if save_out_array:
        #     log_oa.info("Saving element_count_df to ", out_file_name)
        #     self.element_count_df.to_csv(out_file_name)

    def sort_count_array(self,
                         sort_by: str = 'h_used_all_l_use_main',
                         sort_by_ascending: bool = False
                         ):
        """
        Sort the dataframe with the count array (element_count_df).

        :param sort_by: The key to sort the dataframe. The default value is 'h_used_all_l_use_main'.
        :type sort_by: str
        :param sort_by_ascending: Whenever to sort the dataframe ascending. The default value is False.
        :type sort_by_ascending: bool
        """
        log_oa.info(f"Sorting by {sort_by}")
        if not self.count_element_years:
            # we didn't count per year so we can do a simple sort
            self.element_count_df = self.element_count_df.sort_values(by=sort_by, ascending=sort_by_ascending)
        else:
            sorted_sums = self.element_count_df[sort_by].groupby(level=0).sum().sort_values(ascending=sort_by_ascending)
            self.element_count_df = self.element_count_df.reindex(sorted_sums.index, level=0)

    def add_statistics_to_element_count_array(self,
                                              sort_by: str = 'h_used_all_l_use_main',
                                              sort_by_ascending: bool = False,
                                              ):
        """
        Adds a statistics to the element count array (statistics between the main entity to compare (second column in
        the dataframe) and the sum of the other entities).

        :param sort_by: The key to sort the dataframe. The default value is 'h_used_all_l_use_main'.
        :type sort_by: str
        :param sort_by_ascending: Whenever to sort the dataframe ascending. The default value is False.
        :type sort_by_ascending: bool
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
        main_entity_col_id = self.element_count_df.columns.values[0]
        log_oa.info(f"Main entity: {main_entity_col_id}")
        nb_entities = len(self.element_count_df.columns)
        self.element_count_df.fillna(value=0, inplace=True)
        log_oa.info("Computing sum_all_entities...")
        # self.element_count_df['sum_all_entities'] = self.element_count_df.iloc[:, 1:1+nb_entities].sum(axis=1)
        self.element_count_df['sum_all_entities'] = self.element_count_df.sum(axis=1)
        log_oa.info("Computing average_all_entities...")
        self.element_count_df['average_all_entities'] = self.element_count_df['sum_all_entities'] / nb_entities
        log_oa.info("Computing proportion_used_by_main_entity")
        # use sum all entities (include main entity in the sum)
        log_oa.info("fill with NaN values 0 of sum_all_entities to avoid them to be used when ranking (we want to"
                    "ignore these rows as these references aren't used)")
        self.element_count_df['sum_all_entities'] = self.element_count_df['sum_all_entities'].replace(0, None)
        self.element_count_df['proportion_used_by_main_entity'] = self.element_count_df[main_entity_col_id] / \
                                                                  self.element_count_df['sum_all_entities']
        # self.element_count_df['proportion_used_by_main_entitie'] = self.element_count_df[main_entity_col_id].div(self.element_count_df['sum_all_entities'])
        # # we put -1 inplace of NaN values (it's where the sum_all_entities is 0 so the division failed)
        # self.element_count_df.fillna(value=-1, inplace=True)
        log_oa.info("Computing sum_all_entities rank...")
        self.element_count_df['sum_all_entities_rank'] = self.element_count_df['sum_all_entities'].rank(ascending=True,
                                                                                                        pct=True)  # , method = 'dense') # before method = 'average' was used
        log_oa.info("Computing proportion_used_by_main_entity rank...")
        self.element_count_df['proportion_used_by_main_entity_rank'] = self.element_count_df[
            'proportion_used_by_main_entity'].rank(ascending=False,
                                                   pct=True)  # , method = 'dense') # before method = 'average' was used
        log_oa.info("Computing highly used by all entities and low use by main entity")
        self.element_count_df['h_used_all_l_use_main'] = self.element_count_df['sum_all_entities_rank'] * \
                                                         self.element_count_df['proportion_used_by_main_entity_rank']

        self.sort_count_array(sort_by=sort_by, sort_by_ascending=sort_by_ascending)


    def add_authorships_citation_style(self):
        """
        Add the author_citation_style column to the DataFrame entities_df
        """
        self.entities_df['author_citation_style'] = self.entities_df['authorships'].apply(
            extract_authorships_citation_style)

    def get_authors_count(self,
                          cols: list[str] | None
                          ) -> pd.DataFrame:
        """
        Count the number of times each author appears in entities_df and return the result as a pd.DataFrame.

        :param cols: Columns to return in the DataFrame. Must be existing columns names of authorships. The default value is None which correspond to ['author.id', 'count', 'raw_affiliation_string', 'author.display_name', 'author.orcid'].
        :type cols: list[str]
        :return: The authors count.
        :rtype: pd.DataFrame
        """
        if cols is None:
            cols = ['author.id', 'count', 'raw_affiliation_string', 'author.display_name', 'author.orcid']
        df_authors = pd.json_normalize(self.entities_df['authorships'].explode().to_list())
        authors_count = pd.DataFrame(df_authors.value_counts('author.id'))

        df_authors = df_authors.drop_duplicates('author.id')
        df_authors = df_authors.set_index('author.id')

        authors_count = pd.merge(authors_count, df_authors, how='left', left_index=True, right_index=True).reset_index()

        return authors_count[cols]

    def count_yearly_entity_usage(self, entity: str, count_years: list[int]) -> list[int]:
        """
        Counts the yearly number of time the entity is used.

        :param entity: The entity (id) to count.
        :type entity: str
        :param count_years: The years for which we need to count the entity.
        :type count_years: list[int]
        :return: The number of time the entity is used on a yearly basis.
        :rtype: list[int]
        """
        entity_link = "https://openalex.org/" + entity
        count_res = [0] * len(count_years)
        for i, year in enumerate(count_years):
            # get the list of works from the year
            df = self.entities_df.loc[self.entities_df['publication_year'] == year]
            if self.get_entity_type_from_id(entity) == Concepts:
                # get a dataframe with all the concepts used during the year in the column id
                df = pd.json_normalize(df['concepts'].explode().to_list())
            elif self.get_entity_type_from_id(entity) == Works:
                # get a dataframe with all the works used during the year in the column id
                df = pd.DataFrame({'id': df['referenced_works'].explode().dropna()})
            else:
                raise ValueError("Entity type not supported")
            if df.empty:
                count_res[i] = 0
            else:
                # count the concept usage
                count = pd.DataFrame(df.value_counts('id'))
                count_res[i] = count['count'].get(entity_link, 0)
                # count_res[i] = count.loc[concept]['count']
        return count_res

    def count_yearly_works(self, count_years: list[int]) -> list[int]:
        """
        Return the number of works present per year in entities_df.

        :param count_years: The years for which we need to count the works
        :type count_years: list[int]
        :return: Number of works per year.
        :rtype: list[int]
        """
        count_res = [0] * len(count_years)
        for i, year in enumerate(count_years):
            # get the list of works from the year
            df = self.entities_df.loc[self.entities_df['publication_year'] == year]
            if df.empty:
                count_res[i] = 0
            else:
                # get the number of rows
                count_res[i] = len(df.index)
        return count_res

    def get_df_yearly_usage_of_entities(self,
                                        count_years: list[int],
                                        entity_used_ids: str | list[str],
                                        entity_from_legend: str = "Custom dataset"
                                        ) -> pd.DataFrame:
        """
        Gets the dataframe with the yearly usage by works of entity_used_ids.

        :param count_years: The years for which we need to count the entity.
        :type count_years: list[int]
        :param entity_used_ids: The entity ids to count.
        :type entity_used_ids: str | list[str]
        :param entity_from_legend: The legend on the plot for the entity_from dataset. The default value is "Custom dataset". If the default value is unchanged and entitie_from_id was specified, entitie_from_id will be used.
        :type entity_from_legend: str
        :return: The df yearly usage by works.
        :rtype: pd.DataFrame
        """
        if not isinstance(entity_used_ids, list):
            entity_used_ids = [entity_used_ids]
        if entity_from_legend == "Custom dataset" and self.entity_from_id is not None:
            entity_from_legend = self.entity_from_id
        df = pd.DataFrame()
        for entity_used_id in entity_used_ids:
            # count
            usage_count = self.count_yearly_entity_usage(entity_used_id, count_years)
            works_count = self.count_yearly_works(count_years)
            entity_used_id_list = [entity_used_id] * len(count_years)
            entity_from_list = [entity_from_legend] * len(count_years)

            # create the dataframe
            zipped_data = list(zip(count_years,
                                   usage_count,
                                   works_count,
                                   entity_used_id_list,
                                   entity_from_list))

            df_i = pd.DataFrame(zipped_data, columns=['years',
                                                      'usage_count',
                                                      'works_count',
                                                      'entity_used',
                                                      'entity_from',
                                                      ])

            df = pd.concat([df, df_i])

        return df

    def get_df_yearly_usage_of_entities_by_multiples_entities(self,
                                                              count_years: list[int],
                                                              entity_used_ids: str | list[str],
                                                              entity_from_ids: str | list[str] | None = None,
                                                              ) -> pd.DataFrame:
        """
        Gets the dataframe with the yearly usage by works of entity_used_ids, works for multiple entities from.

        :param count_years: The years for which we need to count the entities.
        :type count_years: list[int]
        :param entity_used_ids: The entity ids to count.
        :type entity_used_ids: str | list[str]
        :param entity_from_ids: The entity from identifiers, aka the entities dataset in which we need to count the entity_used_ids. When the default value None is used, the entitie_from_id will be used.
        :type entity_from_ids: str | list[str] | None
        :return: The DataFrame of the yearly usage of entity_used_ids by entity_from_ids
        :rtype: pd.DataFrame
        """
        if entity_from_ids is None:
            entity_from_ids = self.entity_from_id
            if entity_from_ids is None:
                raise ValueError(
                    "entity_from_ids not provided and entities_from_id is None. You must provide either "
                    "entity_from_id to the class or entity_from_ids to the function")

        if not isinstance(entity_from_ids, list):
            entity_from_ids = [entity_from_ids]

        df = pd.DataFrame()

        for entity_from_id in entity_from_ids:
            work_analysis = WorksAnalysis(entity_from_id)
            df = pd.concat([
                df,
                work_analysis.get_df_yearly_usage_of_entities(count_years=count_years,
                                                              entity_used_ids=entity_used_ids,
                                                              )
            ])

        return df


class AuthorsAnalysis(EntitiesAnalysis, Authors):
    """
    This class contains specific methods for Authors entities analysis. Not used for now.
    """
    EntityOpenAlex = Authors


class SourcesAnalysis(EntitiesAnalysis, Sources):
    """
    This class contains specific methods for Sources entities analysis. Not used for now.
    """
    EntityOpenAlex = Sources


class InstitutionsAnalysis(EntitiesAnalysis, Institutions):
    """
    This class contains specific methods for Institutions entities analysis.
    """
    EntityOpenAlex = Institutions

    # def filter_and_format_entity_data_from_api_response(self, entity: dict):
    #     """
    #     Filter and format the institutions data downloaded from the OpenAlex API.
    #
    #     :param entity: The institutions data from the API.
    #     :type entity: dict
    #     :return: The institutions data filtered and formatted.
    #     :rtype: dict
    #     """
    #
    #     # # add computed datas:
    #     # # works_cited_by_count_average
    #     # entity['works_cited_by_count_average'] = round(entity['cited_by_count'] / entity['works_count'], 2)


class ConceptsAnalysis(EntitiesAnalysis, Concepts):
    """
    This class contains specific methods for Concepts entities analysis. Not used for now.
    """
    EntityOpenAlex = Concepts


class TopicsAnalysis(EntitiesAnalysis, Topics):
    """
    This class contains specific methods for Topics entities analysis. Not used for now.
    """
    EntityOpenAlex = Topics


class PublishersAnalysis(EntitiesAnalysis, Publishers):
    """
    This class contains specific methods for Publishers entities analysis. Not used for now.
    """
    EntityOpenAlex = Publishers
