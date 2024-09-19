import sys
from os.path import isdir
import shutil
import numpy as np

sys.path.append("..")

from openalex_analysis.analysis import config, load_config_from_file
from openalex_analysis.data import WorksData
from openalex_analysis.analysis import WorksAnalysis, InstitutionsAnalysis, AuthorsAnalysis
from openalex_analysis.plot import WorksPlot

# set the default configuration (this avoids using the configuration defined in the file
# ~/openalex-analysis/openalex-analysis-conf.toml)
from openalex_analysis.data.entities_data import set_default_config

set_default_config()

load_config_from_file("openalex-analysis-conf.toml")

institution_src_id = "I138595864"

regime_shift_topic_id = "T13377"

# Use a specific folder for the tests to be able to clear the cache
config.project_data_folder_path = "./data"

# remove data (cache) that may have been downloaded in the previous test
if isdir(config.project_data_folder_path):
    shutil.rmtree(config.project_data_folder_path)


def test_download_dataset_1():
    # basic test with works
    wa = WorksAnalysis(institution_src_id)
    first_author = wa.entities_df.at[0, "authorships"][0]

    assert isinstance(first_author['author']['display_name'], str)


def test_download_dataset_2():
    # test with works and extra filter
    extra_filters = {
        'publication_year': 2020,
        'authorships': {'institutions': {'id': institution_src_id}},
    }

    wa = WorksAnalysis(extra_filters=extra_filters)
    first_author = wa.entities_df.at[0, "authorships"][0]

    assert isinstance(first_author['author']['display_name'], str)


def test_download_dataset_3():
    # test with a topic dataset
    wa = WorksPlot(regime_shift_topic_id)
    print(wa.entities_df.authorships[0])
    first_author = wa.entities_df.at[0, "authorships"][0]

    assert isinstance(first_author['author']['display_name'], str)


def test_download_dataset_4():
    # basic test with authors
    aa = AuthorsAnalysis(institution_src_id)
    print(aa.entities_df.columns)
    first_author_name = aa.entities_df.at[0, "display_name"]

    assert isinstance(first_author_name, str)


def test_analysis_1():
    wa = WorksAnalysis(institution_src_id)

    wa.create_element_used_count_array('reference')

    assert isinstance(wa.element_count_df.iloc[0, 0], np.int64)


def test_get_multiple_entities_from_id_works():
    # test with a list of 3 articles
    entities_ids = [
        "W1999167944",
        "W2096885696",
        "W2126902408",
    ]
    entities_names = [
        "Planetary boundaries: Guiding human development on a changing planet",
        "A safe operating space for humanity",
        "Solutions for a cultivated planet",
    ]
    res = WorksAnalysis().get_multiple_entities_from_id(entities_ids, return_dataframe=False)
    for i in range(len(entities_names)):
        assert entities_names[i] == res[i]["display_name"]
    # TODO: add a test with more than 100 works


def test_get_multiple_entities_from_id_institutions():
    # test with a list of 3 institutions
    entities_ids = [
        "I138595864",
        "I140494188",
        "I000000000"
    ]
    entities_names = [
        "Stockholm Resilience Centre",
        "Université de Technologie de Troyes",
        None
    ]
    res = InstitutionsAnalysis().get_multiple_entities_from_id(entities_ids, return_dataframe=False)
    for i in range(len(entities_names)):
        if entities_ids[i] == "I000000000":
            assert res[i] is None
        else:
            assert entities_names[i] == res[i]["display_name"]
    # TODO: add a test with more than 100 institutions


def test_get_multiple_entities_from_id_works_to_df():
    # test with a list of 3 articles
    entities_ids = [
        "W1999167944",
        "W2096885696",
        "W2126902408",
    ]
    entities_names = [
        "Planetary boundaries: Guiding human development on a changing planet",
        "A safe operating space for humanity",
        "Solutions for a cultivated planet",
    ]
    res = WorksAnalysis().get_multiple_entities_from_id(entities_ids)
    for i in range(len(entities_names)):
        assert entities_names[i] == res.at[i, "display_name"]
    assert "abstract" in res.columns


def test_get_multiple_works_from_doi():
    # test with a list of 3 articles
    article_dois = [
        "https://doi.org/10.1038/461472a",
        # added upper case to check that the ordering is working with uppercases:
        "https://doi.org/10.1126/SCIENCE.1259855",
        "https://doi.org/10.1038/nature10452",
    ]
    article_names = [
        "A safe operating space for humanity",
        "Planetary boundaries: Guiding human development on a changing planet",
        "Solutions for a cultivated planet",
    ]
    res = WorksData().get_multiple_works_from_doi(article_dois, return_dataframe=False)
    for i in range(len(article_dois)):
        assert article_names[i] == res[i]["display_name"]
    # TODO: add a test with more than 60 works


def test_concept_yearly_count():
    concept_sustainability_id = 'C66204764'
    # create the filter for the API to get only the articles about sustainability
    sustainability_concept_filter = {"concepts": {"id": concept_sustainability_id}}

    # set the years we want to count
    count_years = list(range(2004, 2024))

    institution_ids_list = ["I138595864", "I140494188"]
    # ["Stockholm Resilience Centre", "University of Technology of Troyes"]

    # create a list of dictionaries with each dictionary containing the ID, name and filter for each institution
    entities_ref_to_count = [{}] * len(institution_ids_list)
    for i in range(len(institution_ids_list)):
        entities_ref_to_count[i] = {'entity_from_id': institution_ids_list[i],
                                    'extra_filters': sustainability_concept_filter}

    wplt = WorksPlot()
    wplt.create_element_used_count_array('concept', entities_ref_to_count, count_years=count_years)

    wplt.add_statistics_to_element_count_array(sort_by='sum_all_entities')

    wplt.get_figure_time_series_element_used_by_entities().write_image("Plot_yearly_usage_sustainability_SRC_UTT.svg",
                                                                       width=900, height=350)


def test_generating_collaboration_map():
    wplt = WorksPlot("I138595864")

    wplt.get_collaborations_with_institutions()

    wplt.get_figure_collaborations_with_institutions()
