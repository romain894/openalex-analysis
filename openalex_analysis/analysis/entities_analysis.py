# Romain THOMAS 2024

import logging
from collections import Counter

from tqdm import tqdm
import pandas as pd

from pyalex import Works, Authors, Institutions, Concepts

# config must NOT be imported from pyalex here as it is already imported via entities_analysis

from openalex_analysis.data import *


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
        self.collaborations_with_institutions_entities_from_metadata = pd.DataFrame(
            self.collaborations_with_institutions_entities_from_metadata).set_index('id')

        self.collaborations_with_institutions_df = [pd.DataFrame()] * len(entities_from)
        for i, institution_from in enumerate(entities_from):
            log_oa.info(f"Processing {institution_from} "
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
            collaborations_per_work = [
                list(set([institution['id'] for author in work for institution in author['institutions']]))
                for work in works.entities_df['authorships'].to_list()
            ]
            # list of the institutions we collaborated with
            institutions_collaborations = set(list(
                [institution for institutions in collaborations_per_work
                 for institution in institutions if institution not in institutions_to_exclude_i]
            ))
            log_oa.info(f"{len(institutions_collaborations)} unique institutions with which "
                        f"{self.collaborations_with_institutions_entities_from_metadata.at[institution_from, 'name']} "
                        f"collaborated")
            # remove the https://openalex.org/ at the beginning
            institutions_collaborations = [institution_id[21:] for institution_id in institutions_collaborations]
            # count the number of collaboration per institutions:
            # collaborations_per_work contains the institutions we collaborated per work, so we
            # can count on how many works we collaborated with each institution
            institutions_count_dict = Counter(list(
                [institution for institutions in collaborations_per_work for institution in institutions
                 if institution not in institutions_to_exclude_i]
            ))

            # create dictionaries with the institution id as key and lon, lat and name as item
            institutions_name = [None] * len(institutions_collaborations)
            institutions_id = [None] * len(institutions_collaborations)
            institutions_lat = [None] * len(institutions_collaborations)
            institutions_lon = [None] * len(institutions_collaborations)
            institutions_country = [None] * len(institutions_collaborations)
            institutions_count = [None] * len(institutions_collaborations)
            institutions = InstitutionsAnalysis().get_multiple_entities_from_id(institutions_collaborations,
                                                                                return_dataframe=False)
            for j, institution in enumerate(institutions):
                institutions_name[j] = institution['display_name']
                institutions_id[j] = institution['id'][21:] # remove https://openalex.org/
                institutions_lat[j] = institution['geo']['latitude']
                institutions_lon[j] = institution['geo']['longitude']
                institutions_country[j] = institution['geo']['country']
                institutions_count[j] = institutions_count_dict[institution['id']]

            # store in a dataframe
            self.collaborations_with_institutions_df[i] = pd.DataFrame(
                list(zip(
                    institutions_name,
                    institutions_id,
                    institutions_lat,
                    institutions_lon,
                    institutions_country,
                    [institution_from] * len(institutions_collaborations),
                    [self.collaborations_with_institutions_entities_from_metadata.at[institution_from, 'name']] *
                         len(institutions_collaborations),
                    institutions_count
                )),
                columns = ['name', 'id', 'lat', 'lon', 'country', 'id_from', 'name_from', 'count']
            )

            self.collaborations_with_institutions_df[i] = self.collaborations_with_institutions_df[i].sort_values(
                'count', ascending=False
            )

        self.collaborations_with_institutions_df = pd.concat(
            self.collaborations_with_institutions_df, ignore_index=True
        )

        # add the link to consult the collaborations works
        if year is not None:
            self.collaborations_with_institutions_df['link_to_works'] = (
                f"https://explore.openalex.org/works?filter=authorships.institutions.lineage:"
                f"{self.collaborations_with_institutions_df.id},"
                f"authorships.institutions.lineage:{self.collaborations_with_institutions_df.id_from},"
                f"publication_year:{year}"
            )
        else:
            self.collaborations_with_institutions_df['link_to_works'] = (
                f"https://explore.openalex.org/works?filter=authorships.institutions.lineage:"
                f"{self.collaborations_with_institutions_df.id},"
                f"authorships.institutions.lineage:{self.collaborations_with_institutions_df.id_from}"
            )

        return self.collaborations_with_institutions_df


class WorksAnalysis(EntitiesAnalysis, WorksData):
    """
    This class contains specific methods for Works entity analysis.
    """
    def get_element_count(self, element_type: str, count_years: list[int] | None = None) -> pd.Series:
        """
        Count the number of times each element (for now references or concepts) is used by the works in self.entities_df
        in total or by year (optional).

        :param element_type: The element type ('reference' or 'concept').
        :type element_type: str
        :param count_years: List of years to count the concepts. The default value is None to not count by years.
        :type count_years: list[int]
        :return: The element count.
        :rtype: pd.Series
        """
        def get_works_references_count() -> pd.Series:
            """
            Count the number of times each referenced work is used by the works in self.entities_df.

            :return: The works references count.
            :rtype: pd.Series
            """
            log_oa.info(f"Creating the works references count of {self.get_entity_type_string_name()}...")
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

        def get_works_concepts_count() -> pd.Series:
            """
            Count the number of times each concept is used by the works in self.entities_df.

            :return: The concept count.
            :rtype: pd.Series
            """
            log_oa.info(f"Creating the concept count of {self.get_entity_type_string_name()}...")
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

        match element_type:
            case 'reference':
                return get_works_references_count()
            case 'concept':
                return get_works_concepts_count()
            case _:
                raise ValueError("Can only count for 'references' or 'concept'")


    def create_element_used_count_array(self,
                                        element_type: str,
                                        entities_from: list[dict] | None = None,
                                        count_years: list[int] | None = None
                                        ):
        """
        Creates the element used count array. Count the number of times each element (e.g. references, concepts...) are
        used. You must provide at least 'element_type' ('reference' or 'concept').
        If you only provide 'element_type' the default behavior is to count the number of time the element_type are used
        (e.g. the number of times each reference is used) in the dataset loaded ('entities_df').
        If you provide 'entities_from', the count will be done for the dataset 'entities_df' if it exists and each
        entity in the list 'entities_from'.
        By default, one count is made by entity, but if you provide 'count_years' the count will be done for each given
        year.
        The result is saved in 'element_count_df'.

        :param element_type: The element type ('reference' or 'concept').
        :type element_type: str
        :param entities_from: The extra entities to which to count the concepts.
        :type entities_from: list[dict]
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
                "create_element_used_count_array()"
            )

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
        Note: This function is still experimental and might change in future versions.

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
        # we need at least 2 entities in the dataframe so 2 columns (self.entity_id and entity or 2 entities)
        # (the ref id are the index)
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
        Counts the yearly number of time the entity is used in entities_df.

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


class AuthorsAnalysis(EntitiesAnalysis, AuthorsData):
    """
    This class contains specific methods for Authors entity analysis. Not used for now.
    """
    pass


class SourcesAnalysis(EntitiesAnalysis, SourcesData):
    """
    This class contains specific methods for Sources entity analysis. Not used for now.
    """
    pass


class InstitutionsAnalysis(EntitiesAnalysis, InstitutionsData):
    """
    This class contains specific methods for Institutions entity analysis. Not used for now.
    """
    pass


class ConceptsAnalysis(EntitiesAnalysis, ConceptsData):
    """
    This class contains specific methods for Concepts entity analysis. Not used for now.
    """
    pass


class TopicsAnalysis(EntitiesAnalysis, TopicsData):
    """
    This class contains specific methods for Topics entity analysis. Not used for now.
    """
    pass


class PublishersAnalysis(EntitiesAnalysis, PublishersData):
    """
    This class contains specific methods for Publishers entity analysis. Not used for now.
    """
    pass