import sys
from os.path import isdir
import shutil
sys.path.append("..")

import numpy as np
from openalex_analysis.analysis import config, WorksAnalysis, InstitutionsAnalysis
from openalex_analysis.plot import WorksPlot
from openalex_analysis.analysis import get_multiple_works_from_doi

config.n_max_entities = 200

institution_src_id = "I138595864"

data_path = "./data"

# remove data that may have been downloaded in the previous test
if isdir(data_path):
    shutil.rmtree(data_path)


def test_download_dataset_1():
    wa = WorksAnalysis(institution_src_id)
    first_author = wa.entities_df.at[0, "authorships"][0]

    assert isinstance(first_author['author']['display_name'], str)
    assert isinstance(first_author['institutions'][0]['display_name'], str)


def test_download_dataset_2():
    extra_filters = {
        'publication_year':2020,
        'authorships':{'institutions':{'id':institution_src_id}},
    }

    wa = WorksAnalysis(extra_filters = extra_filters)
    first_author = wa.entities_df.at[0, "authorships"][0]

    assert isinstance(first_author['author']['display_name'], str)
    assert isinstance(first_author['institutions'][0]['display_name'], str)


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
    res = WorksAnalysis().get_multiple_entities_from_id(entities_ids)
    for i in range(len(entities_names)):
        assert entities_names[i] == res[i]["display_name"]
    # TODO: add a test with more than 100 works


def test_get_multiple_entities_from_id_institutions():
    # test with a list of 3 articles
    entities_ids = [
        "I138595864",
        "I140494188",
        "I000000000"
    ]
    entities_names = [
        "Stockholm Resilience Centre",
        "University of Technology of Troyes",
        None
    ]
    res = InstitutionsAnalysis().get_multiple_entities_from_id(entities_ids)
    for i in range(len(entities_names)):
        if entities_ids[i] == "I000000000":
            assert res[i] is None
        else:
            assert entities_names[i] == res[i]["display_name"]
    # TODO: add a test with more than 100 institutions


def test_get_multiple_works_from_doi():
    # test with a list of 3 articles
    article_dois = [
        "https://doi.org/10.1038/461472a",
        "https://doi.org/10.1126/science.1259855",
        "https://doi.org/10.1038/nature10452",
    ]
    article_names = [
        "A safe operating space for humanity",
        "Planetary boundaries: Guiding human development on a changing planet",
        "Solutions for a cultivated planet",
    ]
    res = get_multiple_works_from_doi(article_dois)
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
    institution_names_list = ["Stockholm Resilience Centre", "University of Technology of Troyes"]

    # create a list of dictionaries with each dictionary containing the ID, name and filter for each institution
    entities_ref_to_count = [None] * len(institution_ids_list)
    for i in range(len(institution_ids_list)):
        entities_ref_to_count[i] = {'entity_from_id': institution_ids_list[i],
                                    'extra_filters': sustainability_concept_filter}

    wplt = WorksPlot()
    wplt.create_element_used_count_array('concept', entities_ref_to_count, count_years = count_years)

    wplt.add_statistics_to_element_count_array(sort_by = 'sum_all_entities')

    wplt.get_figure_time_series_element_used_by_entities().write_image("Plot_yearly_usage_sustainability_SRC_UTT.svg", width=900, height=350)
