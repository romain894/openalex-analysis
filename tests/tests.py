import sys
import shutil
sys.path.append("..")

import numpy as np
from openalex_analysis.analysis import config, WorksAnalysis
from openalex_analysis.analysis import get_multiple_entities_from_doi, get_multiple_entities_from_id

config.n_max_entities = 200

institution_src_id = "I138595864"

# remove data that may have been downloaded in the previous test
shutil.rmtree("./data")


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


def test_get_multiple_entities_from_id():
    # test with a list of 3 articles
    article_ids = [
        "W2096885696",
        "W1999167944",
        "W2126902408",
    ]
    article_names = [
        "A safe operating space for humanity",
        "Planetary boundaries: Guiding human development on a changing planet",
        "Solutions for a cultivated planet",
    ]
    res = get_multiple_entities_from_id(article_ids)
    for i in range(len(article_ids)):
        assert article_names[i] == res[i]["display_name"]
    # TODO: add a test with more than 100 articles

def test_get_multiple_entities_from_doi():
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
    res = get_multiple_entities_from_doi(article_dois)
    for i in range(len(article_dois)):
        assert article_names[i] == res[i]["display_name"]
    # TODO: add a test with more than 60 articles
