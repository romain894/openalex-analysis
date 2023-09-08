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