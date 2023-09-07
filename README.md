# OpenAlex Analysis

Scientific literature analysis using the OpenAlex API.

This repo provides classes and methods to extract statistics, plots and graphs, as well as examples in Jupyter Notebooks.

A web app based on the library is available [here](https://github.com/romain894/webapp-openalex-analysis).

Documentation : [https://romain894.github.io/openalex-analysis](https://romain894.github.io/openalex-analysis)

[OpenAlex documentation](https://docs.openalex.org/) [Explore OpenAlex in a GUI](https://explore.openalex.org/)

Licence: GPL V3

## Examples

### Basic

More examples can be found in the notebooks [Works_examples.ipynb](https://github.com/romain894/openalex-analysis/blob/main/Works_examples.ipynb) and [Concepts_Works_analysis.ipynb](https://github.com/romain894/openalex-analysis/blob/main/Concepts_works_analysis.ipynb)

```python
from openalex_analysis.plot import WorksPlot

concept_sustainability_id = 'C66204764'

# get the works about sustainability
wplt = WorksPlot(concept_sustainability_id)

# compute the most cited works by the dataset previously downloaded
wplt.create_element_used_count_array('reference')
```

### Concepts yearly count




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