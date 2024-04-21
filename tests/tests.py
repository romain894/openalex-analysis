import sys
import shutil
sys.path.append("..")

import numpy as np
from openalex_analysis.analysis import config, WorksAnalysis

config.n_max_entities = 200

institution_src_id = "I138595864"

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
