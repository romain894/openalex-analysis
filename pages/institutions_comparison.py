from EntitiesConceptsPlot import InstitutionsConceptsPlot, WorksConceptsPlot
from EntitiesConceptsAnalysis import get_info_about_entitie_from_api
from OA_entities_names import OA_entities_names
# from jupyter_dash import JupyterDash
import dash_bootstrap_components as dbc # dash app theme
import plotly.io as pio # plotly theme
from dash import Dash, dcc, html, Input, Output, State, ALL, MATCH, Patch, DiskcacheManager, callback, dash_table, no_update
from dash.exceptions import PreventUpdate
import dash
#from dash.long_callback import DiskcacheLongCallbackManager
# import dash_auth
# import diskcache #for the long callback manager
import threading
# from flask import Flask
import time
import dash_loading_spinners
import os, sys
sys.path.append(os.path.abspath('../'))
from layout_parameters import *
import pandas as pd
import base64
import io


dash.register_page(__name__)

app = dash.get_app()

# concept names and BD file names:
OA_concepts = OA_entities_names()


works_infos = ["display_name", "author_citation_style", "publication_year"]

        
main_container = dbc.Container(className="container-app-references-analysis", id="container-app-references-analysis", fluid=True, children=[
    dbc.Row(justify="center", style={'margin': '1em 1em'}, children=
        [
            dbc.Col(
                [
                    html.H1(children="Comparison of institutions"),
                    html.P(children="Analysis of works (aka articles) of a concept (eg sustainability) from different institutions."),
                    html.P(children="""
                        First we select the concept where the works should come from. It allows us to focus the analysis on a specific field. 
                        Then we select a list of institutions. We will import the works of these institutions which fit the concept previously selected. 
                        With this set of works we can count the number of time each reference or concept was used and see the results in the tables below.
                        """),
                    #html.Br(),
                    html.H2(children="Analysis parameters"),
                    html.H3(children="Concept"),
                    html.P(children="The analysis will use only the works of this concept:"),
                    # dcc.Dropdown(OA_concepts.concepts_names_full, id='ref_i_concept_dropdown', clearable=True),
                    dcc.Dropdown(id='ref_i_concept_dropdown', clearable=True, placeholder='Type at least 3 characters (for example "Sustainability")',),
                    html.Br(),
                    html.H3(children="Institutions to compare"),
                    html.P("""
                        Enter the institutions you want to compare in the dropdown menu or upload a list from a file below (generate the file in the tab "Institutions plot").
                        Once added, the institutions will appear in the table below.
                    """),
                    dbc.Row(
                        [
                            dbc.Col(
                                dcc.Dropdown(id='ref_institutions_dropdown', clearable=True, placeholder='Type at least 5 characters (for example "Stockholm Resilience Centre")',),
                                sm = 10, md = 8
                            ),
                            dbc.Col(dbc.Button(id="ref_add_institution_button",
                                children="Add this institution",
                                disabled=True,
                            )),
                        ]
                    ),
                    html.P('You can also upload a file from "Institution plot" with the list of institutions you want to compare.'),
                    dcc.Upload(
                        id='upload_list_entities_to_compare',
                        children=html.Div([
                            'Drag and Drop or ',
                            html.A('Select a file'),
                            ' (max 150 rows)'
                        ]),
                        style={
                            'width': '100%',
                            'height': '60px',
                            'lineHeight': '60px',
                            'borderWidth': '1px',
                            'borderStyle': 'dashed',
                            'borderRadius': '5px',
                            'textAlign': 'center',
                            'margin': '10px'
                        },
                        # Allow multiple files to be uploaded
                        multiple=False
                    ),
                    dcc.Store(id='list_entities_to_compare'),
                    html.Br(),
                    # html.Div(id='div_table_list_entities_to_compare'),
                    dash_table.DataTable(
                        id = "table_entities_to_compare",
                        columns=[{'id': "id", 'name': "id"}, {'id': "display_name", 'name': "display_name"}],
                        style_cell = {'textAlign': 'left',},
                        style_data_conditional = dash_table_conditional_style,
                    ),
                    html.Br(),
                    dbc.Button(id='ref_a_button_remove_entitie_from_list_to_compare', children="Remove the selected institution(s)"),
                    html.Br(),
                    html.Br(),
                    html.P(children="The main entitie for the comparative analysis:"),
                    dcc.Dropdown([{'label': "Add at least one institution before", 'value': 0, 'disabled': True}], id='ref_a_main_entitie_dropdown'),
                    html.Br(),
                    # html.Br(),
                    # html.Br(),
                    html.H3(children="Element to count type"),
                    html.P(children="The element type we want to count in the analysis:"),
                    dcc.Dropdown([{'label': "Reference", 'value': 'reference'}, {'label': "Concept", 'value': 'concept'}], 'reference', id='ref_a_element_count_type_dropdown', clearable=False),
                    html.H3(children="Comparison mode"),
                    html.P(children="There is 2 comparison mode: "),
                    html.Ol(children=[
                        html.Li("Compare the main institution works with the works of the list of institutions added"),
                        html.Li("Compare the main institution works with the works of the concept"),
                    ]),
                    dcc.Dropdown([
                            {'label': "Main institution vs other institutions", 'value': 'other_institutions'},
                            {'label': "Main institution vs concept", 'value': 'concept'}
                        ],
                        'other_institutions',
                        id='ref_a_comparison_mode',
                        clearable=False
                    ),
                    html.H2(children="Analysis results"),
                    dbc.Row(justify="start", children=
                        [
                            dbc.Col(dbc.Checklist(
                                id='download_raw_ref_array_checklist',
                                options=['Download the raw references array'],
                                # value=['Download the raw references array'],
                                inline=True,
                                style={'margin-right': default_big_margin},
                                #switch=True,
                            ) ,md=4, xxl=3),
                            dbc.Col(html.Div("Maximum number of rows to download (optional):"), width='auto'),
                            dbc.Col(dbc.Input(
                                id='download_raw_ref_array_max_rows',
                                type='number',
                                # value=cited_by_average_default_threshold,
                                required=False,
                                # size='3',
                            ), md=4, xxl=3),
                        ],
                    ),
                    dbc.Row(justify="start", children=
                        [
                            dbc.Col(dbc.Checklist(
                                id='download_enriched_ref_array_checklist',
                                options=['Download the enriched references array'],
                                inline=True,
                                style={'margin-right': default_big_margin},
                                #switch=True,
                            ) ,md=4, xxl=3),
                            dbc.Col(html.Div("Maximum number of rows to download (optional):"), width='auto'),
                            dbc.Col(dbc.Input(
                                id='download_enriched_ref_array_max_rows',
                                type='number',
                                # value=cited_by_average_default_threshold,
                                required=False,
                                # size='3',
                            ), md=4, xxl=3),
                        ],
                    ),
                    dcc.Download(id="download_raw_ref_array"),
                    dcc.Download(id="download_enriched_ref_array"),
                    dbc.Button(id='button_start_references_analysis',
                        children="Start the references analysis",
                        disabled=True,),
                    " ",
                    dbc.Button(id='ref_a_button_cancel',
                        children="Cancel the references analysis",
                        disabled=True,),
                    html.Div(children=dbc.Progress(id='progress_references_analysis', animated=True, striped=True),
                        style={'visibility': 'hidden'}
                    ),
                    html.Div(children="",
                        id='text_progress_references_analysis'),
                ],
                **layout_dynamic_width
            ),
        ]
    ),
    dbc.Row(justify="center", style={'margin': '1em 1em'}, children=
        [
            dbc.Col(
                [
                    html.H3(children="Plots"),
                    dcc.Loading(
                        id="loading_plot_ref_concept_nb_cited",
                        children=[dcc.Graph(id='plot_ref_concept_nb_cited')],
                        type="default",
                        parent_style={'visibility': 'visible'}
                    ),
                    html.Br(),
                    html.H3(children="Tables"),
                    dcc.Store(id='element_type_counted'),
                    # html.H4(children="Most used by the main institution"),
                    # html.Div(id='div_table_most_used_ref_concept', children=dash_table.DataTable(id='table_most_used_ref_concept')),
                    # dbc.Alert(id='info_table_most_used_ref_concept'),
                    # html.H4(children="Most used by all"),
                    # html.Div(id='div_table_sum_all_entities', children=dash_table.DataTable(id='table_table_sum_all_entities')),
                    # dbc.Alert(id='info_table_sum_all_entities'),
                    # html.H4(children="Most used by all except by the main institution"),
                    # html.Div(id='div_table_h_used_all_l_use_main', children=dash_table.DataTable(id='table_h_used_all_l_use_main')),
                    # dbc.Alert(id='info_table_h_used_all_l_use_main'),
                    html.H4(children="Most used by the main institution"),
                    html.Div(id={'type': 'div_table', 'index': 'most_used_by_main'}, children=dash_table.DataTable(id={'type': 'table', 'index': 'most_used_by_main'})),
                    dbc.Alert(id={'type': 'info_table', 'index': 'most_used_by_main'}),
                    html.H4(children="Most used by all"),
                    html.Div(id={'type': 'div_table', 'index': 'most_used_by_all'}, children=dash_table.DataTable(id={'type': 'table', 'index': 'most_used_by_all'})),
                    dbc.Alert(id={'type': 'info_table', 'index': 'most_used_by_all'}),
                    html.H4(children="Most used by all except by the main institution"),
                    html.Div(id={'type': 'div_table', 'index': 'h_used_all_l_use_main'}, children=dash_table.DataTable(id={'type': 'table', 'index': 'h_used_all_l_use_main'})),
                    dbc.Alert(id={'type': 'info_table', 'index': 'h_used_all_l_use_main'}),
                ]
            )
        ]
    ), 
])


layout = html.Div(children=
    [
        html.Div(
            id="div-loading-references-analysis",
            children=
                [
                    dash_loading_spinners.ClimbingBox(#Pacman(
                        fullscreen=True, 
                        id="loading-app-references-analysis"
                    )
                ]
        ),
        main_container
    ]
)

@app.callback(
    Output("div-loading-references-analysis", "children"),
    Input("container-app-references-analysis", "loading_state"),
    State("div-loading-references-analysis", "children"),
)
def hide_loading_after_startup(loading_state, children):
    if children:
        return None
    raise PreventUpdate


@app.callback(
    Output("ref_i_concept_dropdown", "options"),
    Input("ref_i_concept_dropdown", "search_value")
)
def update_options_ref_i_concept_dropdown(search_value):
    if not search_value or len(search_value) < 3:
        # return {}
        raise PreventUpdate
    search_value = search_value.lower()
    # return [o for o in OA_concepts.concepts_names_full if search_value in OA_concepts.concepts_names_full[o]]
    return {key: value for key, value in OA_concepts.concepts_names_full.items() if search_value in value.lower()}


@app.callback(
    Output("ref_institutions_dropdown", "options"),
    Input("ref_institutions_dropdown", "search_value")
)
def update_options_ref_institutions_dropdown(search_value):
    if not search_value or len(search_value) < 5:
        # return {}
        raise PreventUpdate
    search_value = search_value.lower()
    # return [o for o in OA_concepts.concepts_names_full if search_value in OA_concepts.concepts_names_full[o]]
    return {key: value for key, value in OA_concepts.institutions_names.items() if search_value in value.lower()}


@app.callback(
    Output('ref_add_institution_button', 'disabled'),
    Input('ref_institutions_dropdown', 'value'),
)
def update_button_ref_add_institution_button_disabled_status(institution_dropdown):
    disabled_download_btn = True
    if institution_dropdown != None:
        disabled_download_btn = False
    return disabled_download_btn


@app.callback(
    [
        Output('list_entities_to_compare', 'data', allow_duplicate=True),
        Output('ref_institutions_dropdown', 'value'),
    ],
    Input('ref_add_institution_button', 'n_clicks'),
    State('ref_institutions_dropdown', 'value'),
    State('list_entities_to_compare', 'data'),
    prevent_initial_call=True,
)
def add_institution_to_list_to_compare(n_click, institution_id, list_entities_to_compare):
    if list_entities_to_compare == None:
        list_entities_to_compare = {}
    list_entities_to_compare[institution_id] = OA_concepts.institutions_names[institution_id]
    return list_entities_to_compare, None


def extract_entities_from_uploaded_file_content(contents, filename):
    content_type, content_string = contents.split(',')

    decoded = base64.b64decode(content_string)
    cols_to_load = ['id', 'display_name']
    try:
        institutions_list_df = pd.read_csv(
            io.StringIO(decoded.decode('utf-8')),
            usecols = cols_to_load,
            index_col=False,
            nrows=150
        )
        # print(institutions_list_df)
        # extract the institution id from the openalex id link
        entities_to_compare = {} #[None] * len(institutions_list_df.index)
        institutions_list_df['id'] = institutions_list_df['id'].str.replace('https://openalex.org/', '')
        for i, institution in institutions_list_df.iterrows():
            entities_to_compare[institution['id']] = institution['display_name']
            #entities_to_compare[i] = {'entitie_from_id': institution['id'], 'entitie_name': institution['display_name']}
        # print(entities_to_compare)
        # table = dash_table.DataTable(
        #     institutions_list_df.to_dict('records'),
        #     [{"name": i, "id": i} for i in institutions_list_df.columns],
        #     style_cell = {'textAlign': 'left',},
        #     style_data_conditional = dash_table_conditional_style,
        # )
        return entities_to_compare#, table
    except Exception as e:
        print(e)
        # return html.Div([
        #     'There was an error processing this file.'
        # ])



@app.callback(# [
        Output('list_entities_to_compare', 'data', allow_duplicate=True),
        # Output('div_table_list_entities_to_compare', 'children'),
        # Output("ref_a_main_entitie_dropdown", "options")
    # ],
    Input('upload_list_entities_to_compare', 'contents'),
    State('upload_list_entities_to_compare', 'filename'),
    State('upload_list_entities_to_compare', 'last_modified'),
    prevent_initial_call=True,
)
def update_list_entities_to_compare_from_file(content, filename, date):
    # entities_to_compare, table = extract_entities_from_uploaded_file_content(content, filename)
    if content == None:
        # we prevent the update as the content is None and the callback is called two times (bug?)
        print("PreventUpdate")
        raise PreventUpdate
    entities_to_compare = extract_entities_from_uploaded_file_content(content, filename)
    return entities_to_compare#, table, entities_to_compare


@app.callback(
    [
        # Output('div_table_list_entities_to_compare', 'children'),
        Output('table_entities_to_compare', 'data'),
        Output("ref_a_main_entitie_dropdown", "options")
    ],
    Input('list_entities_to_compare', 'data'),
    prevent_initial_call=True
)
def update_table_entities_to_compare(list_entities_to_compare):
    # table = dash_table.DataTable(
    #         [{'id': key, 'display_name': value} for key, value in list_entities_to_compare.items()],
    #         id = "table_entities_to_compare",
    #         #institutions_list_df.to_dict('records'),
    #         #[{"name": i, "id": i} for i in institutions_list_df.columns],
    #         style_cell = {'textAlign': 'left',},
    #         style_data_conditional = dash_table_conditional_style,
    #     )
    table_data = [{'id': key, 'display_name': value} for key, value in list_entities_to_compare.items()]
    return table_data, list_entities_to_compare


@app.callback(
    [
        Output('list_entities_to_compare', 'data'),
        Output("table_entities_to_compare", "selected_cells"),
        Output("table_entities_to_compare", "active_cell"),
        Output('ref_a_main_entitie_dropdown', 'value'),
    ],
    Input('ref_a_button_remove_entitie_from_list_to_compare', 'n_clicks'),
    State('table_entities_to_compare', 'selected_cells'),
    State('list_entities_to_compare', 'data'),
    State('ref_a_main_entitie_dropdown', 'value'),
    prevent_initial_call=True,
)
def delete_institution_to_list_to_compare(n_click, selected_cells, list_entities_to_compare, main_entitie):
    for cell in selected_cells:
        institution_id = cell['row_id']
        list_entities_to_compare.pop(institution_id, None)
        if institution_id == main_entitie:
            # if the institution removed is the one selected in the dropdown menu
            # we need to internaly reset its value
            main_entitie = None
    return list_entities_to_compare, [], None, main_entitie


@app.callback(
    Output('button_start_references_analysis', 'disabled'),
    [
        Input('ref_i_concept_dropdown', 'value'),
        Input('list_entities_to_compare', 'data'),
        Input('ref_a_main_entitie_dropdown', 'value'),
    ],
    prevent_initial_call=True,
)
def update_button_start_references_analysis_disabled_status(concept_dropdown, list_entities_to_compare, main_entitie):
    disabled_download_btn = True
    if concept_dropdown != None and list_entities_to_compare != None and main_entitie != None:
        disabled_download_btn = False
    return disabled_download_btn


def get_dash_table_references_works_count(wcp, id_table):
    df = wcp.element_count_df.iloc[:50].copy().round(2).reset_index()
    # add a column at the last position with the works links and transform the works link at the first column to names
    df = df.rename(columns={'element': 'Element names'})
    df['Element link'] = df['Element names'].copy()
    if wcp.count_element_type == 'concept':
        # The column concept_name already contains the name so we drop Element names and rename concept_name
        df = df.drop('Element names', axis=1)
        df = df.rename(columns={'concept_name': 'Element names'})
    else:
        extra_info_df = df['Element names'].str.replace("https://openalex.org/", "").apply(get_info_about_entitie_from_api, infos = works_infos)
        df = df.join(extra_info_df)
        df['Element names'] = df['display_name']
        df = df.drop('display_name', axis=1)
        df = df.rename(columns={'publication_year': 'year', 'author_citation_style': 'authors'})
        # df['Element names'] = df['Element names'].str.replace("https://openalex.org/", "").apply(get_name_of_entitie_from_api)
    # replace _ by spaces in columns names to allow line break:
    df.columns = df.columns.str.replace("_", " ")
    table = dash_table.DataTable(
        df.to_dict('records', index = True),
        [{"name": i, "id": i} for i in df.columns],
        id = id_table,
        style_cell = dash_table_style_cell,
        # style_data_conditional = dash_table_ref_conditional_style,
        style_data_conditional = [
            {
                'if': {'column_id': c},
                'width': '170px'
            } for c in df.columns
        ] + [
            {
                'if': {'column_id': 'Element names'},
                 'width': '350px'
            },
            {
                'if': {'row_index': 'odd'},
                'backgroundColor': 'rgb(240, 240, 240)',
            },
        ],
        style_header = dash_table_style_header,
        # fixed_columns={'headers': True, 'data': 1},
        style_table={'minWidth': '100%', 'overflowX': 'auto'},
        page_size=10,
    )
    return table



@app.long_callback(
    output=[
        Output('plot_ref_concept_nb_cited', 'figure'),
        Output({'type': 'div_table', 'index': 'most_used_by_main'}, 'children'),
        Output('download_raw_ref_array', 'data'),
        Output({'type': 'div_table', 'index': 'most_used_by_all'}, 'children'),
        Output({'type': 'div_table', 'index': 'h_used_all_l_use_main'}, 'children'),
        Output('download_enriched_ref_array', 'data'),
        Output('element_type_counted', 'data'),
    ],
    inputs=[
        Input('button_start_references_analysis', 'n_clicks'),
    ],
    state=[
        State('ref_i_concept_dropdown', 'value'),
        State('list_entities_to_compare', 'data'),
        State('ref_a_main_entitie_dropdown', 'value'),
        State('ref_a_comparison_mode', 'value'),
        State('download_raw_ref_array_checklist', 'value'),
        State('download_raw_ref_array_max_rows', 'value'),
        State('download_enriched_ref_array_checklist', 'value'),
        State('download_enriched_ref_array_max_rows', 'value'),
        State('ref_a_element_count_type_dropdown', 'value'),
    ],
    running=[
        (Output('button_start_references_analysis', 'disabled'), True, False),
        (Output('ref_a_button_cancel', 'disabled'), False, True),
        (
            Output('progress_references_analysis', 'style'),
            {'visibility': 'visible', 'height': '12px', 'width': 'auto'},
            {'visibility': 'hidden'},
        ),
        (
            Output('text_progress_references_analysis', 'style'),
            {'visibility': 'visible', 'display': 'inline-block', 'margin-right': default_big_margin},
            {'visibility': 'hidden'},
        ),
    ],
    progress=[
        Output('progress_references_analysis', 'value'),
        Output('text_progress_references_analysis', 'children')
    ],
    cancel=[Input('ref_a_button_cancel', 'n_clicks')],
    prevent_initial_call=True,
)
def update_results_reference_analysis(set_progress,
                                      n_click,
                                      concept_dropdown,
                                      list_entities_to_compare,
                                      main_entitie,
                                      comparison_mode,
                                      download_raw_array,
                                      download_raw_array_max_rows,
                                      download_enriched_array,
                                      download_enriched_array_max_rows,
                                      element_count_type
                                      ):
    print("\nUpdating results...")
    wcp = WorksConceptsPlot()
    # wcp = WorksConceptsPlot(concept_dropdown)
    # format the list of entities to load for the lib:
    # create the filter to download only the works from the entities of the concept to study
    concept_filter = {'concepts': {'id': concept_dropdown}}
    entities_ref_to_count = None
    if comparison_mode == 'other_institutions':
        entities_ref_to_count = [None] * len(list_entities_to_compare.keys())
        # place the main entitie to compare at the first position:
        entities_ref_to_count[0] = {'entitie_from_id': main_entitie,
                                    'extra_filters': concept_filter,
                                    'entitie_name': list_entities_to_compare[main_entitie]}
        del list_entities_to_compare[main_entitie]
        for i, entitie_id in enumerate(list_entities_to_compare):
            entities_ref_to_count[i+1] = {'entitie_from_id': entitie_id,
                                        'extra_filters': concept_filter,
                                        'entitie_name': list_entities_to_compare[entitie_id]}
    else: #concept
        entities_ref_to_count = [None] * 2
        entities_ref_to_count[0] = {'entitie_from_id': main_entitie,
                                    'extra_filters': concept_filter,
                                    'entitie_name': list_entities_to_compare[main_entitie]}
        entities_ref_to_count[1] = {'entitie_from_id': concept_dropdown,
                                    #'extra_filters': concept_filter,
                                    'entitie_name': OA_concepts.concepts_names_full[concept_dropdown]}

    create_ref_thread = threading.Thread(target=wcp.create_element_used_count_array, kwargs={'element_type': element_count_type, 'entities_from':entities_ref_to_count, 'save_out_array': False})
    create_ref_thread.start()
    while create_ref_thread.is_alive():
        time.sleep(0.2)
        loading_text_info = wcp.create_element_count_array_progress_text+" "+str(round(wcp.create_element_count_array_progress_percentage, 1))+"%"
        set_progress((str(wcp.create_element_count_array_progress_percentage), loading_text_info))

    # set_progress((str(wcp.create_element_count_array_progress_percentage), wcp.create_element_count_array_progress_text))
    set_progress((str(wcp.create_element_count_array_progress_percentage), "Adding statistics on the references array..."))

    # create the raw dataframe
    fig_nb_time_referenced = WorksConceptsPlot(**entities_ref_to_count[0]).get_figure_nb_time_referenced(element_type = element_count_type)

    raw_array = no_update
    if download_raw_array != None:
        if len(download_raw_array):
            if download_raw_array_max_rows == None:
                download_raw_array_max_rows = len(wcp.element_count_df.index)
            raw_array = dcc.send_data_frame(wcp.element_count_df.iloc[:download_raw_array_max_rows].to_csv, element_count_type+"s_works_analysis_user.csv")


    # add statistics on the dataframe and create the table and sort by the most used by the main entitie
    wcp.add_statistics_to_element_count_array(sort_by = wcp.count_entities_cols[0])
    table_most_cited_concept = get_dash_table_references_works_count(wcp, id_table = {'type': 'table', 'index': 'most_used_by_main'})

    wcp.sort_count_array(sort_by = 'sum_all_entities')
    table_sum_all_entities = get_dash_table_references_works_count(wcp, id_table = {'type': 'table', 'index': 'most_used_by_all'})

    wcp.sort_count_array(sort_by = 'h_used_all_l_use_main')
    table_h_used_all_l_use_main = get_dash_table_references_works_count(wcp, id_table = {'type': 'table', 'index': 'h_used_all_l_use_main'})

    enriched_array = no_update
    if download_enriched_array != None:
        if len(download_enriched_array):
            if download_enriched_array_max_rows == None:
                download_enriched_array_max_rows = len(wcp.element_count_df.index)
            raw_array = dcc.send_data_frame(wcp.element_count_df.iloc[:download_enriched_array_max_rows].to_csv, element_count_type+"s_works_analysis_user.csv")

    return fig_nb_time_referenced, table_most_cited_concept, raw_array, table_sum_all_entities, table_h_used_all_l_use_main, enriched_array, element_count_type


@app.callback(
    Output({'type': 'info_table', 'index': MATCH}, 'children'),
    Input({'type': 'table', 'index': MATCH}, 'active_cell'),
    State({'type': 'table', 'index': MATCH}, 'data'),
    State('element_type_counted', 'data'),
    prevent_initial_call=True,
    # suppress_callback_exceptions=True, # because using components generated by callback
)
def update_table(active_cell, data, element_type_counted):
    div_children = "Click the table"
    if active_cell:
        if element_type_counted == 'reference':
            div_children = [
                html.A(data[active_cell['row']]['Element names'], href=data[active_cell['row']]['Element link'], target="_blank"),
                html.Br(),
                data[active_cell['row']]['authors'],
                html.Br(),
                "Publication year: "+str(data[active_cell['row']]['year']),
            ]
        else:
            div_children = [
                html.A(data[active_cell['row']]['Element names'], href=data[active_cell['row']]['Element link'], target="_blank"),
            ]
    return div_children