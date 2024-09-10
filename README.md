# OpenAlex Analysis

A python library to download, analyse or plot articles, institutions, and other entities from the OpenAlex API

Install with:
```
pip install openalex-analysis
```

Documentation: [https://romain894.github.io/openalex-analysis](https://romain894.github.io/openalex-analysis)

Licence: GPL V3

If you want to export the plots, you need to install `kaleido`:
```bash
pip install kaleido
```

## Examples

Examples in the documentation: [https://romain894.github.io/openalex-analysis/html/example_works_concepts.html](https://romain894.github.io/openalex-analysis/html/example_works_concepts.html)

### Get a dataset

You can use the library simply to download and work with datasets from OpenAlex. The library can download these datasets and cache them on the computer automatically.

These datasets can then be used in python outside the library, as they are pandas DataFrame objects.

It is possible to save the datasets as a CSV file with the pandas function `df.to_csv("my_dataset.csv")`.

Bellow, a few examples:

#### Get works from a concept

Get the works about regime shift and save them in a CSV file:

```python
from openalex_analysis.analysis import WorksAnalysis

concept_regime_shift_id = 'C2780893879'

wplt = WorksAnalysis(concept_regime_shift_id)

my_dataset = wplt.entities_df

my_dataset.to_csv("dataset_regime_shift_works.csv")
```

#### Get the works about sustainability from the Stockholm Resilience Centre published in 2020

```python
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

### Institutions collaborations plot

```python
from openalex_analysis.plot import InstitutionsPlot

year = "2023"

entities_from = [
                     "I163151358",  # Cyprus University of Technology
                     "I107257983",  # Darmstadt University of Applied Sciences
                     "I201787326",  # Riga Technical University
                     "I4210144925", # Technological University Dublin
                     "I31151848",   # Technical University of Sofia
                     "I3123212020", # Universidad Politécnica de Cartagena
                     "I140494188",  # University of Technology of Troyes
                     "I158333966",  # Technical University of Cluj-Napoca
                     "I186995768",  # University of Cassino and Southern Lazio
                     ]

iplt = InstitutionsPlot()

# generate the DataFrame
iplt.get_collaborations_with_institutions(entities_from = entities_from,
                                          year = year,
                                         )

# generate the plot
fig = iplt.get_figure_collaborations_with_institutions()

fig.write_image("plot_collaborations_eut+_2023.svg")
fig.write_image("plot_collaborations_eut+_2023.png", scale=2)
fig.write_html("plot_collaborations_eut+_2023.html")
 
fig.show()
```

[![Plot of the collaborations of the EUt+ universities in 2023](https://raw.githubusercontent.com/romain894/openalex-analysis/main/plot_collaborations_eut%2B_2023.svg)](https://romain894.github.io/openalex-analysis/html/notebooks/eut%2B_universities_collaborations.html)
Click on the plot to go to notebook with the interactive view.

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
from openalex_analysis.plot import WorksPlot

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

The documentation or this notebook [setup_and_settings.ipynb](https://github.com/romain894/openalex-analysis/blob/main/sphinx-doc/notebooks/setup_and_settings.ipynb) contains more setup examples.

### Available settings

  - `email` (*string*) - Your Email for the OpenAlex API. Allows you to use the polite pool (see OpenAlex documentation). The default value is None (not using the polite pool).
  - `api_key` (*string*) - Your OpenAlex API key, if you have one. The default value is None.
  - `openalex_url` (*string*) - OpenAlex API URL or your self-hosted API URL. The default value is "https://api.openalex.org".
  - `http_retry_times` (*int*) - maximum number of retries when querying the OpenAlex API in HTTP. The default value is 3.
  - `disable_tqdm_loading_bar` (*bool*) - To disable the tqdm loading bar. The default is False.
  - `n_max_entities` (*int*) - Maximum number of entities to download (the default value is to download maximum 10 000 entities). If set to None, no limitation will be applied.
  - `project_data_folder_path` (*string*) - Path to the folder containing the data downloaded from the OpenAlex API (these data are stored in compressed parquet files and used as a cache). The default path is "~/openalex-analysis/data".
  - `parquet_compression` (*string*) - Type of compression for the parquet files used as cache (see the Pandas documentation). The default value is "brotli".
  - `max_storage_percent` (*int*) - When the disk capacity reaches this percentage, cached parquet files will be deleted. The default value is 95.
  - `max_storage_files` (*int*) - When the cache folder reaches this number of files, cached parquet files will be deleted. The default value is 10000.
  - `max_storage_size` (*int*) - When the cache folder reached this size (in bytes), cached parquet files will be deleted. The default value is 5e9 (5 GB).
  - `min_storage_files` (*int*) - Before deleting files, we check if we exceed the minimum number of files and folder size. If one of those minimum if exceeded, we allow the program to delete cached parquet files. This is to avoid the setting max_storage_percent to delete every cached file when the disk is almost full. The default value is 1000.
  - `min_storage_size` (*int*) - Before deleting files, we check if we exceed the minimum number of files and folder size. If one of those minimum if exceeded, we allow the program to delete cached parquet files. This is to avoid the setting max_storage_percent to delete every cached file when the disk is almost full. The default value is 5e8 (500 MB).
  - `cache_max_age` (*int*) - Maximum age of the cache in days. The default value is 365.
  - `log_level` (*string*) - The log detail level for openalex-analysis (library specific). The log_level must be 'DEBUG', 'INFO', 'WARNING', 'ERROR' or 'CRITICAL'. The default value 'WARNING'.

## Use a configuration file

You can use a configuration file to load your settings. If you save it in
`~/openalex-analysis/openalex-analysis-conf.toml`, it will be automatically loaded each time you import the library.

If you want to use another path for you configuration file, you can load it after importing the library as follows:
```python
from openalex_analysis.analysis import load_config_from_file, WorksAnalysis

load_config_from_file("my-openalex-analysis-conf.toml")
```

In the configuration file, you can define the available settings with the following format:
```python
log_level = "DEBUG"
n_max_entities = 200
```

## Tests

In the directory `tests/` run:
```bash
pytest tests.py
```


## Build the documentation

In the directory `sphinx-doc/` run:
```bash
make html
```

## Other resources

  - Web app based on the library is available [here](https://github.com/romain894/webapp-openalex-analysis) (this project is not currently maintained but an update is planned in the coming months).
  - [OpenAlex documentation](https://docs.openalex.org/)
  - [Explore OpenAlex online](https://explore.openalex.org/)
  - [PyAlex](https://github.com/J535D165/pyalex) (Python library for OpenAlex)

Romain Thomas 2024