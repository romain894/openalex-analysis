# OpenAlex Analysis

A python library to extract or analyse articles, institutions, and others entities from the OpenAlex API

This repo provides classes and methods to extract the data and create statistics, plots and graphs, as well as examples in Jupyter Notebooks.

Install with:
```
pip install openalex-analysis
```

A web app based on the library is available [here](https://github.com/romain894/webapp-openalex-analysis).

Documentation : [https://romain894.github.io/openalex-analysis](https://romain894.github.io/openalex-analysis)

[OpenAlex documentation](https://docs.openalex.org/) [Explore OpenAlex in a GUI](https://explore.openalex.org/)

Licence: GPL V3

## Examples

More examples can be found in the notebooks [Works_examples.ipynb](https://github.com/romain894/openalex-analysis/blob/main/Works_examples.ipynb) and [Concepts_Works_analysis.ipynb](https://github.com/romain894/openalex-analysis/blob/main/Concepts_works_analysis.ipynb)

### Get a dataset

You can use the library simply to get and manage dataset of OpenAlex. The library can download these dataset and cache them on the computer automatically.

These datasets can then be used in python outside the library as they are just simple dataframe objects.

Bellow, a few examples:

#### Get works from a concept

Get the works about regime shift:

```bash
from openalex_analysis.analysis import WorksAnalysis

concept_regime_shift_id = 'C2780893879'

wplt = WorksAnalysis(concept_regime_shift_id)

my_dataset = wplt.entities_df
```

#### Get the works about sustainability from the Stockholm Resilience Centre published in 2020

```bash
from openalex_analysis.analysis import WorksAnalysis

concept_sustainability = 'C66204764'
institution_src_id = "I138595864"
extra_filters = {
    'publication_year':2020,
    'authorships':{'institutions':{'id':institution_src_id}},
}

wplt = WorksAnalysis(concept_sustainability,
                     extra_filters = extra_filters)

my_dataset = wplt.entities_df
```

### Basic analysis

In the example, we create a dataset with the works about sustainability.

This dataset can be used as it, it is stored in a parquet file (more optimized than CSV) on the computer and can be simply imported as a dataframe with Pandas.

After getting this dataset, we continue by extracting the most cited articles by the dataset. For that, we extract all the references of the articles present in the dataset and rank these references.

```python
from openalex_analysis.plot import WorksPlot

concept_sustainability_id = 'C66204764'

# get the works about sustainability
wplt = WorksPlot(concept_sustainability_id)

print("\nFirst entities in the dataset:")
print(wplt.entities_df[['id', 'title']].head(3))

# compute the most cited works by the dataset previously downloaded
wplt.create_element_used_count_array('reference')

print("\nMost cited work within the dataset:")
print(wplt.element_count_df.head(3))
```

```
Loading dataframe of works of the concept C66204764
Loading the list of entities from a parquet file...

First entities in the dataset:
                                 id                                              title
0  https://openalex.org/W2101946146  Asset Stock Accumulation and Sustainability of...
1  https://openalex.org/W1999167944  Planetary boundaries: Guiding human developmen...
2  https://openalex.org/W2122266551  Agricultural sustainability and intensive prod... 

Getting name of C66204764 from the OpenAlex API (cache disabled)...
Creating the works references count of works C66204764...

Most cited work within the dataset:
                                  C66204764 Sustainability
element                                                   
https://openalex.org/W2026816730                       262
https://openalex.org/W2096885696                       249
https://openalex.org/W2103847341                       203
```

### Concepts yearly count

In this example, we will create two datasets: one with the articles about sustainability of the SRC (Stockholm Resilience Centre) and one with the articles about sustainability of the UTT (University of Technology of Troyes).

We will then plot the yearly usage of the concept sustainability by these institutions (in this case it's equal to the number of articles in the dataset, as the dataset contains only the articles about sustainability).

We could also plot the yearly usage of other concepts or of the references by changing the parameters of the functions `create_element_used_count_array()` and `get_figure_time_series_element_used_by_entities()`.

```python
from openalex_analysis.plot import InstitutionsPlot, WorksPlot

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
    entities_ref_to_count[i] = {'entitie_from_id': institution_ids_list[i],
                                'extra_filters': sustainability_concept_filter,
                                'entitie_name': institution_names_list[i]}


wplt = WorksPlot()
wplt.create_element_used_count_array('concept', entities_ref_to_count, count_years = count_years)

wplt.add_statistics_to_element_count_array(sort_by = 'sum_all_entities', min_concept_level = 2)

wplt.get_figure_time_series_element_used_by_entities().write_image("Plot_yearly_usage_sustainability_SRC_UTT.svg", width=1200)

wplt.get_figure_time_series_element_used_by_entities()
```

![Plot of the yearly usage of sustainability by SRC and UTT](https://raw.githubusercontent.com/romain894/openalex-analysis/main/Plot_yearly_usage_sustainability_SRC_UTT.svg)

## Configure the library

By default, the library will run out of the box. Nevertheless, some optional configurations can be done to improve the performance and to fit best the use case.

Setting up the email address allows you to use the polite pool from OpenAlex which is faster than the default one.


```python
from openalex_analysis.plot import config, InstitutionsPlot

config.email = "email@example.com"

InstitutionsPlot()
```

The notebook [Setup_example.ipynb](https://github.com/romain894/openalex-analysis/blob/main/Setup_example.ipynb) contains more setup examples.

### Default settings

```python
config.email = None
config.api_key = None
config.openalex_url = "https://api.openalex.org"
config.allow_automatic_download = True
config.disable_tqdm_loading_bar = False
config.n_max_entities = 10000
config.project_datas_folder_path = "data"·
config.parquet_compression = "brotli"
config.max_storage_percent = 95
config.redis_enabled = False
# Uncomment the following lines if you want to use Redis cache
# config.redis_client = StrictRedis(host=os.environ.get('DOCKER_REDIS_URL', "localhost"),
#                                  decode_responses=True,
#                                  port=6379,
#                                  db=2,)
# config.redis_cache = RedisCache(redis_client=config_redis_client)
# Don't forget to add the following two lines with all the imports
# from redis import StrictRedis
# from redis_cache import RedisCache
```

- `email` The email address is need to access the polite pool from OpenAlex which is faster than the default one.

- `api_key` Optional, if you have one from OpenAlex

- `openalex_url` OpenAlex URL

- `allow_automatic_download` Allow the library to download dataset from OpenAlex if not already present on the disk

- `disable_tqdm_loading_bar` If set to True, it will disable the loading bar in the terminal output when downloading data from the OpenAlex API.

- `n_max_entities` When downloading a list of entities from the API (eg a list of works), the maximum number of entities to download. Set to None to have no limitation. This number must be a multiple of 200 (the is the number of element per page used by the library)

- `project_datas_folder_path` Path to store the data downloaded from the API. The data will be stored as parquet files, with each file corresponding to one request.

- `parquet_compression` By default, the parquet files are compressed. The compression can be disabled by setting with parquet_compression = None. For other parquet compression algorithms, see the pandas documentation. Compressing reduces by 2 to 10 the file size while needing a negligeable time to compress or decompress. Disabling the compression is usefull if you want to read the parquet files with an external software.

- `max_storage_percent` Maximum storage usage percentage on the disk before starting to delete data stored in project_datas_folder_path. The parquet file with the oldest last read data will be deleted first.

- `redis_enabled` Whenever Redis cache is enabled or not

- `redis_client` The Redis client configuration. Don't forget to add `from redis import StrictRedis` where the configuration is defined.

- `redis_cache` The Redis cache configuration. Don't forget to add `from redis_cache import RedisCache` where the configuration is defined.



Romain Thomas 2023