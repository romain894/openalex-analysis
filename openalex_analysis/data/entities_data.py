# Romain THOMAS 2025
# Licence GPLv3

import os
from copy import deepcopy
from os.path import exists, join, isdir
import psutil
from pathlib import Path
import hashlib  # to generate file names
from time import time
import warnings
import re

import pyalex.api
from tqdm import tqdm
import pandas as pd
import requests

from pyalex import Works, Authors, Sources, Institutions, Topics, Concepts, Publishers

from ..config import (
    AnalysisConfig, config, load_config_from_file, log_oa, set_default_config, _validate_filters,
)
from .query_cache import QueryCache

OPENALEX_ID_PATTERN = r'^(?:https?://openalex\.org/)?[A-Za-z]\d+$'
DOI_PATTERN = r'^(?:https?://doi\.org/)?10\.\d{4,9}/[-._;()/:A-Za-z0-9]+$'


class EntitiesData:
    """
    This class contains methods to download data from the OpenAlex API and manage + cache those datasets locally
    """

    def __init__(self,
                 entity_from_id: str | None = None,
                 extra_filters: dict | None = None,
                 entities_from_id_list: list[str] | None = None,
                 database_file_path: str | None = None,
                 create_dataframe: bool = False,
                 load_only_columns: list[str] | None = None,
                 ):
        """

        :param entity_from_id: The entity identifier (e.g. an institution id) from which to take the entities (e.g. the
            works of this institution) to analyze.
            If not provided, the default value is None and the entities will be downloaded based on the extra_filters
            value.
        :type entity_from_id: str | None
        :param extra_filters: Optional filters, refer to the documentation of openalex and pyalex for the format.
            The default value is None.
        :type extra_filters: dict | None
        :param entities_from_id_list: Similar to entity_from_id but to explicitly specify the ids of the entities to
            query. When specified, entity_from_id and extra_filters must be None.
            For now, only DOIs are supported.
        :type entities_from_id_list: list[str] | None
        :param database_file_path: The database file (parquet or csv) path to force the analysis over datas in a
            specific file. The default value is None to use the data from the OpenAlex API or the cached data.
        :type database_file_path: str | None
        :param create_dataframe: Load the dataframe at initialization, downloading entities if needed.
            Defaults to False; call load_entities_dataframe() when the entity dataset is needed.
        :type create_dataframe: bool
        :param load_only_columns: Load only the specified columns from the parquet file. Everything will be downloaded
            anyway. The default value is None.
        :type load_only_columns: str | None
        """
        self.per_page = 100  # supported maximum for regular OpenAlex lists

        if entities_from_id_list is not None and (entity_from_id is not None or extra_filters is not None):
            raise ValueError("The entity_from_id and extra_filters values cannot be specified with "
                             "entities_from_id_list.")

        self.entity_from_id = entity_from_id
        self.entity_from_type = None
        self.extra_filters = extra_filters
        self.entities_from_id_list = entities_from_id_list
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

        # initialize the values only if entity_from_type is known
        if self.entity_from_id is not None or self.extra_filters is not None or self.entities_from_id_list is not None:
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
        _validate_filters(query_filters)
        return self.EntityOpenAlex(params={'filter': deepcopy(query_filters)}).count()

    def get_count(self, *, mode: str | None = None,
                  stale_if_error: bool | None = None) -> int:
        """
        Count all matching entities without downloading the collection or applying config.n_max_entities.
        Uses the instance's filters or ID list.

        :param mode: "auto" uses fresh cache entries, "refresh" fetches again, and "offline" uses cached data only.
            None uses config.query_cache_mode. Offline cache misses raise CacheMiss.
        :param stale_if_error: Use cached data with a warning on request errors. None uses the configuration setting.
        :return: The total number of matching entities.
        """
        parameters = {'filter': self.get_api_query()}

        def fetch_count():
            """Count the instance query, avoiding an API request for an empty ID list."""
            if self.entities_from_id_list == []:
                return 0
            return self.EntityOpenAlex(params=deepcopy(parameters)).count()

        return QueryCache().get_or_fetch(
            self.get_entity_type_string_name(), 'count', parameters,
            fetch_count,
            mode=mode, stale_if_error=stale_if_error)

    def get_group_by(self, field: str, *,
                     mode: str | None = None, stale_if_error: bool | None = None) -> pd.DataFrame:
        """
        Count matching entities by a grouping field, fetching all groups regardless of config.n_max_entities.
        Uses the instance's filters or ID list. Only complete results are cached; entities_df is unchanged.

        :param field: An OpenAlex grouping field, such as "publication_year". Append ``:include_unknown`` to include
            groups with missing values.
        :param mode: "auto", "refresh" or "offline"; see get_count(). None uses config.query_cache_mode.
        :param stale_if_error: Use cached data with a warning on request errors. None uses the configuration setting.
        :return: Groups in API order with key, key_display_name and count columns, including when empty.
        """
        if not isinstance(field, str) or not field.strip():
            raise ValueError('A non-empty OpenAlex grouping field is required.')
        parameters = {'filter': self.get_api_query(), 'group-by': field}

        def fetch_pages():
            """Yield PyAlex grouped pages without changing the filters between requests."""
            if self.entities_from_id_list == []:
                return
            query = self.EntityOpenAlex(params=deepcopy(parameters))
            for page in query.paginate(per_page=200, n_max=None):
                # PyAlex quotes logical expressions in place on each request.
                query.params['filter'] = deepcopy(parameters['filter'])
                yield page

        pages = QueryCache().get_or_fetch_pages(
            self.get_entity_type_string_name(), parameters, fetch_pages,
            mode=mode, stale_if_error=stale_if_error)
        groups = [group for page in pages for group in page['group_by']]
        return pd.DataFrame.from_records(
            groups, columns=['key', 'key_display_name', 'count']).astype({'count': 'int64'})

    def get_api_query(self) -> dict:
        """
        Get the API query from the instance filters or ID list.
        ID lists use OR filters and remain subject to OpenAlex query-size limits.

        :return: The api query
        :rtype: dict
        """
        if self.entities_from_id_list is not None:
            ids = self.entities_from_id_list
            if not ids or re.match(OPENALEX_ID_PATTERN, ids[0]):
                ids = [ident.removeprefix('https://openalex.org/').removeprefix('http://openalex.org/')
                       for ident in ids]
                query_filters = {'ids': {'openalex': '|'.join(ids)}}
            elif self.EntityOpenAlex == Works and re.match(DOI_PATTERN, ids[0]):
                dois = [doi.removeprefix('https://doi.org/').removeprefix('http://doi.org/').lower()
                        for doi in ids]
                query_filters = {'doi': '|'.join(dois)}
            else:
                raise ValueError('The first ID in the list did not match any supported ID pattern.')
        elif self.entity_from_id is not None:
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
            query_filters = type(self.extra_filters)(query_filters | self.extra_filters)
        _validate_filters(query_filters)
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
        entities_list_df = pd.DataFrame.from_records([entity for entity in entities_list if entity is not None])
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
        _validate_filters(self.extra_filters)
        if self.database_file_path is None:
            self.database_file_path = join(config.project_data_folder_path, self.get_database_file_name())
        log_oa.info(f"Downloading list of {self.get_entity_type_string_name()}")
        if self.entity_from_id is not None:
            log_oa.info(f"of the {self.get_entity_type_string_name(self.entity_from_type)[0:-1]} {self.entity_from_id}")
        if self.extra_filters is not None:
            log_oa.info(f"with extra filters: {self.extra_filters}")
        if self.entities_from_id_list is not None:
            log_oa.info(f"with {len(self.entities_from_id_list)} entities")

        if self.entities_from_id_list is None:
            # download entities from entity_from_id and extra_filters parameters
            query = self.get_api_query()
            log_oa.info(f"Query to download from the API: {query}")

            # A cached statistic must not limit a new entity download.
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
            # PyAlex checks n_max between pages, not within a page. Enforce the
            # existing configured cap locally as well, and never page for zero.
            entity_query = self.EntityOpenAlex(params={'filter': deepcopy(query)})
            pager = (entity_query.paginate(
                per_page=min(self.per_page, 100), n_max=n_entities_to_download)
                if n_entities_to_download > 0 else ())

            log_oa.info("Downloading the list of entities thought the OpenAlex API...")
            with tqdm(total=n_entities_to_download, disable=config.disable_tqdm_loading_bar) as pbar:
                i = 0
                self.entity_downloading_progress_percentage = 0
                for page in pager:
                    entity_query.params['filter'] = deepcopy(query)
                    # add the downloaded entities in the main list
                    page_start = i
                    for entity in page:
                        if config.n_max_entities is not None and i >= config.n_max_entities:
                            break
                        self.filter_and_format_entity_data_from_api_response(entity)
                        if i < n_entities_to_download:
                            entities_list[i] = entity
                        else:
                            # A page may contain more entities than the preflight count predicted.
                            entities_list.append(entity)
                            warnings.warn("entities_list was too short, appending the entity")
                        i += 1
                    # update the progress bar
                    pbar.update(i - page_start)
                    # update the progress percentage variable
                    self.entity_downloading_progress_percentage = min(i / n_entities_to_download * 100, 100) if i else 0
            self.entity_downloading_progress_percentage = 100

            log_oa.info("Converting the entities list downloaded to a DataFrame...")
            entities_list_df = self.convert_entities_list_to_df(entities_list)
        else:
            # download entities from the list self.entities_from_id_list
            # identify the type of id based on the first ID, this is experimental
            if re.match(OPENALEX_ID_PATTERN, self.entities_from_id_list[0]):
                log_oa.info("Downloading the entities from OpenAlex ID...")
                entities_list_df = self.get_multiple_entities_from_id(self.entities_from_id_list)
            elif self.EntityOpenAlex == Works and re.match(DOI_PATTERN, self.entities_from_id_list[0]):
                log_oa.info("Downloading the entities from DOI...")
                entities_list_df = self.get_multiple_works_from_doi(self.entities_from_id_list)
            # elif self.EntityOpenAlex == Institutions and re.match(ror_pattern, self.entities_from_id_list[0]):
            #     # TODO
            else:
                raise ValueError("The first ID in the list did not match any ID pattern, unknown ID type")

        if not isdir(config.project_data_folder_path):
            log_oa.info("Creating the directory to store the data from OpenAlex")
            os.makedirs(config.project_data_folder_path)
        log_oa.info("Checking space left on disk...")
        self.auto_remove_databases_saved()
        # fix dataframe: parquet doesn't allow empty structures
        for col in entities_list_df.columns:
            # Replace empty dicts
            if entities_list_df[col].apply(lambda x: isinstance(x, dict) and x == {}).any():
                entities_list_df[col] = entities_list_df[col].apply(
                    lambda x: None if isinstance(x, dict) and x == {} else x
                )
            # Replace empty lists
            if entities_list_df[col].apply(lambda x: isinstance(x, list) and x == []).any():
                entities_list_df[col] = entities_list_df[col].apply(
                    lambda x: None if isinstance(x, list) and x == [] else x
                )
        # save as compressed parquet file
        log_oa.info("Saving the list of entities as a parquet file...")
        entities_list_df.to_parquet(self.database_file_path, compression=config.parquet_compression)

    def load_entities_dataframe(self):
        """
        Load entities into entities_df from the Parquet cache, downloading them if missing or expired.
        Uses the instance query and config.n_max_entities for filtered downloads.
        """
        _validate_filters(self.extra_filters)
        # Load from a list of entities
        if self.entities_from_id_list is not None:
            log_oa.info(f"Loading a dataframe of {len(self.entities_from_id_list)} entities...")
            # return empty dataframe for empty list
            if not self.entities_from_id_list:
                log_oa.info("entities_from_id_list is empty, returning an empty dataframe...")
                self.entities_df = pd.DataFrame()
                return
        # load from a single entity
        else:
            log_oa.info(f"Loading dataframe of {self.get_entity_type_string_name()}")
            if self.entity_from_id is not None:
                log_oa.info(f"of the {self.get_entity_type_string_name(self.entity_from_type)[0:-1]} {self.entity_from_id}")
            if self.extra_filters is not None:
                log_oa.info(f"with extra filters: {self.extra_filters}")

        if self.database_file_path is None:
            self.database_file_path = join(config.project_data_folder_path, self.get_database_file_name())
        # check if the database file exists
        if not exists(self.database_file_path):
            # if the database cache was not found, download the data
            self.download_list_entities()
        # check the age of the cache (aka last date of modification)
        else:
            age_in_days = (time() - os.stat(self.database_file_path).st_mtime) / 86400
            if age_in_days > config.cache_max_age:
                os.remove(self.database_file_path)
                log_oa.info(f"Removed file {self.database_file_path} (age (days): {int(age_in_days)})")
                # download the data to renew the database cache
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
                warnings.warn("No more file to delete.")
                warnings.warn(f"Space used on disk: {psutil.disk_usage(config.project_data_folder_path).percent} %")
                break
            os.remove(join(config.project_data_folder_path, first_accessed_file))
            log_oa.info(f"Removed file {join(config.project_data_folder_path, first_accessed_file)} "
                        f"(last used: {first_accessed_file_time})")


    def get_database_file_name(self, db_format: str = "parquet") -> str:
        """
        Gets the database file name according to the parameters of the instance.

        :param db_format: The database file format. The default is "parquet".
        :type db_format: str
        :return: The database file name
        :rtype: str
        """
        _validate_filters(self.extra_filters)
        entity_from_id = self.entity_from_id
        entity_type = self.EntityOpenAlex
        file_name = self.get_entity_type_string_name(entity_type)
        # for list of entities, we directly hash the list:
        if self.entities_from_id_list is not None:
            file_name += "_from_list_" + hashlib.sha224("_".join(self.entities_from_id_list).encode()).hexdigest()
        # else, more elaborated naming method:
        else:
            if entity_from_id is not None:
                file_name += "_from_" + entity_from_id
            if self.extra_filters is not None:
                query = pyalex.api.BaseOpenAlex(params={'filter': deepcopy(self.extra_filters)}).url
                file_name += "_" + hashlib.sha224(query.encode()).hexdigest()
            # Change the version when cache identity or the stored data format changes.
            file_name += "_v3"
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
        Get information about the entity (eg. name, publication_date...). If no entity is provided, the entity_from_id
        will be used.

        :param entity: The entity id, if not provided, use the one from the instance. Default is None.
        :type entity: str | None
        :param infos: The information fields to get. Default is None, which will get ["display_name"].
        :type infos: list[str] | None
        :param return_as_pd_series: True to return the results as a Pandas Series. Otherwise, a dictionary is returned.
            Default is True.
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
        :param return_dataframe: Return a Dataframe. If True, the DataFrame returned will also be stored in
            self.entities_df and the cache system will be used. If False, a list will be returned. Default is True.
        :type return_dataframe: bool
        :return: the list of entities as pyalex objects (dictionaries) or DataFrame.
        :rtype: pd.DataFrame | list
        """
        res = []
        with tqdm(total=len(ids), disable=config.disable_tqdm_loading_bar) as pbar:
            for i in range(0, len(ids), 100):
                batch = ids[i:i+100]
                res.extend(self.EntityOpenAlex().filter(
                    ids={'openalex': '|'.join(batch)}).get(per_page=100))
                pbar.update(len(batch))

        if ordered:
            # sort the res list with the order provided in the list ids
            # create a dictionary with each id as key and the index in the res list as value
            res_ids_index = {entity['id'][21:]: i for i, entity in enumerate(res) if entity is not None}
            # sort based on the index
            normalized_ids = [entity_id.removeprefix('https://openalex.org/').removeprefix('http://openalex.org/')
                              for entity_id in ids]
            res = [res[res_ids_index[entity_id]] if res_ids_index.get(entity_id) is not None else None
                   for entity_id in normalized_ids]

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
    :param infos: The information to get (see OpenAlex API documentation). You can also request "author_citation_style"
        to get a citation string for the authors. The default is None, which will get ["display_name"].
    :type infos: list[str] | None
    :param return_as_pd_series: True to return the results as a Pandas Series. Otherwise, a dictionary is returned.
        Default is True.
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
    Check if the entity exists. Return False for HTTP 404; propagate other errors
    rather than treating an authentication or service failure as existence.

    :param entity: The entity id.
    :type entity: str
    :return: True if the entity exists.
    :rtype: bool
    """
    try:
        get_entity_type_from_id(entity)()[entity]
    except requests.HTTPError as error:
        if error.response is not None and error.response.status_code == 404:
            return False
        raise
    return True


class WorksData(EntitiesData, Works):
    """
    This class contains specific methods for Works entity data.
    """
    EntityOpenAlex = Works

    def get_count_by_year(self, **kwargs) -> pd.DataFrame:
        """
        Count works per publication year across all matching works.

        :param kwargs: Cache options mode and stale_if_error; see get_group_by().
        :return: Year groups with key, key_display_name and count columns.
        """
        return self.get_group_by('publication_year', **kwargs)

    def get_count_by_type(self, **kwargs) -> pd.DataFrame:
        """
        Count works per publication type across all matching works.

        :param kwargs: Cache options mode and stale_if_error; see get_group_by().
        :return: Publication type groups with key, key_display_name and count columns.
        """
        return self.get_group_by('type', **kwargs)

    def get_count_by_institution(self, **kwargs) -> pd.DataFrame:
        """
        Count works per institution, including the source institution when filtering by one.
        Works affiliated with several institutions can appear in several groups.

        :param kwargs: Cache options mode and stale_if_error; see get_group_by().
        :return: Institution groups with key, key_display_name and count columns.
        """
        return self.get_group_by('authorships.institutions.id', **kwargs)

    def get_count_by_country(self, **kwargs) -> pd.DataFrame:
        """
        Count works per authorship country. International works can appear in several groups.

        :param kwargs: Cache options mode and stale_if_error; see get_group_by().
        :return: Country groups with key, key_display_name and count columns.
        """
        return self.get_group_by('authorships.countries', **kwargs)

    def get_count_by_topic(self, **kwargs) -> pd.DataFrame:
        """
        Count works per topic. Works assigned several topics can appear in several groups.

        :param kwargs: Cache options mode and stale_if_error; see get_group_by().
        :return: Topic groups with key, key_display_name and count columns.
        """
        return self.get_group_by('topics.id', **kwargs)

    def filter_and_format_entity_data_from_api_response(self, entity: dict):
        """
        Filter and format the works data downloaded from the API.
        :param entity: The works data from the API.
        :type entity: dict
        :return: The works datas.
        :rtype: dict
        """

        # Store the abstract as a string (here, we avoid the key "abstract" as PyAlex redefined __getitem__() for it)
        # check if the key abstract_inverted_index exists: it avoids errors when formatting an article that might be
        # duplicated in the list
        if "abstract_inverted_index" in entity.keys():
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
        :param return_dataframe: Return a Dataframe. If True, the DataFrame returned will also be stored in
            self.entities_df and the cache system will be used. If False, a list will be returned. Default is True.
        :type return_dataframe: bool
        :return: the list of works as pyalex objects (dictionaries) or DataFrame.
        :rtype: pd.DataFrame | list
        """
        res = []
        # remove https://doi.org/ to keep request length below 4094 (limit from OpenAlex)
        short_doi = [doi.replace("https://doi.org/", "").replace("http://doi.org/", "") for doi in dois]
        with tqdm(total=len(short_doi), disable=config.disable_tqdm_loading_bar) as pbar:
            # querying more than 60 DOIs causes the HTTP query size being larger than what OpenAlex allows
            for i in range(0, len(short_doi), 60):
                batch = short_doi[i:i+60]
                res.extend(Works().filter(doi='|'.join(batch)).get(per_page=60))
                pbar.update(len(batch))

        if ordered:
            # normalize DOIs to sort
            # TODO: add error messages when DOIs badly formatted: specify format in documentation?
            normalized_dois = [doi if doi.startswith("https://doi.org/") else "https://doi.org/"+doi for doi in dois]
            # sort the res list with the order provided in the list dois
            # create a dictionary with each doi as key and the index in the res list as value
            # we use lower as the doi can be valid with either lower or upper cases
            res_dois_index = {entity['doi'].lower(): i for i, entity in enumerate(res) if entity is not None}
            # sort based on the index
            res = [res[res_dois_index[entity_doi.lower()]] if res_dois_index.get(entity_doi.lower()) is not None
                   else None for entity_doi in normalized_dois]

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
