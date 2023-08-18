from openalex_analysis.plot import config, InstitutionsPlot
from OA_entities_names import OA_entities_names
# from jupyter_dash import JupyterDash
import dash_bootstrap_components as dbc # dash app theme
import plotly.io as pio # plotly theme
from dash import Dash, dcc, html, Input, Output, State, ALL, Patch, callback
from dash.exceptions import PreventUpdate
import dash
import threading
# from flask import Flask
import time
import dash_loading_spinners
import os, sys
sys.path.append(os.path.abspath('../'))
import layout_parameters

dash.register_page(__name__)

app = dash.get_app()

# concept names and BD file names:
OA_concepts = OA_entities_names()

# openalex_analysis configuartion:
if os.path.exists("dash_app_configuration.py"):
    import dash_app_configuration as dash_app_config
    print('OK: Loadeded the configuration from "dash_app_configuration.py"')
else:
    import dash_app_configuration_template as dash_app_config
    print('WARNING: Loaded the default configuration, from the template file ("dash_app_configuration_template.py")')
    print('Please copy the template file, rename it "dash_app_configuration.py" and set the configuration in it')
config.email = dash_app_config.config_email
config.api_key = dash_app_config.config_api_key
config.openalex_url = dash_app_config.config_openalex_url
config.allow_automatic_download = dash_app_config.config_allow_automatic_download
config.disable_tqdm_loading_bar = dash_app_config.config_disable_tqdm_loading_bar
config.n_max_entities = dash_app_config.config_n_max_entities
config.project_datas_folder_path = dash_app_config.config_project_datas_folder_path
config.parquet_compression = dash_app_config.config_parquet_compression
config.max_storage_percent = dash_app_config.config_max_storage_percent
config.redis_enabled = dash_app_config.config_redis_enabled
config.redis_client = dash_app_config.config_redis_client
config.redis_cache = dash_app_config.config_redis_cache
print('OK: Configuration set')


plot_parameters_template = {
    #'plot_title': "Plot of the institutions related to ecology studies",
    'x_datas': 'works_count',
    'x_legend': "Number of works",
    #'y_datas': 'C18903297',
    #'y_legend': "Concept score (ecology)",
    'color_data': 'works_cited_by_count_average',
    'color_legend': "Cited by average"
}

plot_multi_concepts_parameters_template = {
    'plot_title': "Plot of the institutions related to the set of concepts",
    'x_datas': 'works_count',
    'x_legend': "Number of works",
    'y_datas': 'average_combined_concepts_score',
    'y_legend': "Average combined concept score",
    'color_data': 'geo.country',
    'color_legend': "Country name"
}

institution_to_highlight = 'https://openalex.org/I138595864'

default_concept_plot = 'C107826830' # 'C66204764' # take sustainability as default concept
x_default_threshold = 500
y_default_threshold = 40
cited_by_average_default_threshold = 0

# list of templates: https://plotly.com/python/templates/
pio.templates.default = "plotly"
# list of themes: https://bootswatch.com/
# dash_theme = dbc.themes.JOURNAL #PULSE
        
# app = JupyterDash(__name__, external_stylesheets=[dash_theme])
#app = Dash(__name__, external_stylesheets=[dash_theme], long_callback_manager=long_callback_manager)
# server = Flask(__name__)
# app = Dash(server=server, external_stylesheets=[dash_theme], long_callback_manager=long_callback_manager)
# app.title = 'Institutions analysis'

# auth = dash_auth.BasicAuth(
#     app,
#     VALID_USERNAME_PASSWORD_PAIRS
# )

#html.Div(className="div-app", id="div-app", children=[
main_container = dbc.Container(className="div-app", id="div-app", fluid=True, children=[
    #html.Div(id='single_concept_div', style={'width': default_div_width, 'margin': '1em auto'}, children=#[
    #dbc.Col(html.Div(id='single_concept_div', style={'margin': '1em 1em'}, children=#[
    dbc.Row(justify="center", style={'margin': '1em 1em'}, children=
        [
            dbc.Col(
                [
                    html.H2(id='title_single_concept_plot', children="Single concept plot"),
                    dbc.Stack(
                        [
                            dbc.Row(html.Div("This graph allows you to plot the institutions related to one concept")),
                            #html.Br(),
                            dbc.Row(
                                [
                                    dbc.Col(
                                        [
                                            dbc.Row(
                                                [
                                                    dbc.Col(dbc.Input(
                                                        id='input_x_threshold',
                                                        type='number',
                                                        value=x_default_threshold,
                                                        required=True,
                                                        # size='3',
                                                    ), md=4, xxl=3),
                                                    dbc.Col(html.Div("Works threshold")),
                                                ],
                                            ),
                                            dbc.Row(
                                                [
                                                    dbc.Col(dbc.Input(
                                                        id='input_y_threshold',
                                                        type='number',
                                                        value=y_default_threshold,
                                                        required=True,
                                                        # size='3',
                                                    ), md=4, xxl=3),
                                                    dbc.Col(html.Div("Concept score threshold")),
                                                ],
                                            ),
                                            dbc.Row(
                                                [
                                                    dbc.Col(dbc.Input(
                                                        id='input_cited_by_average_threshold',
                                                        type='number',
                                                        value=cited_by_average_default_threshold,
                                                        required=True,
                                                        # size='3',
                                                    ), md=4, xxl=3),
                                                    dbc.Col(html.Div("Cited by average threshold")),
                                                ],
                                            ),
                                        ],
                                        sm = 6
                                    ),
                                    dbc.Col(
                                        [
                                            dbc.Checklist(
                                                id='display_threshold_lines',
                                                options=[' Display threshold lines'],
                                                value=[' Display threshold lines'],
                                                inline=True,
                                                style={'margin-right': layout_parameters.default_big_margin},
                                                #switch=True,
                                            ),
                                            dbc.Checklist(
                                                id='display_only_selected_institutions',
                                                options=[' Display only selected institutions'],
                                                inline=True,
                                                style={'margin-right': layout_parameters.default_huge_margin},
                                                #switch=True,
                                            ),
                                            html.Br(),
                                            html.Div(id='n_selected_institutions_output',
                                                    style={'margin-right': layout_parameters.default_big_margin}),
                                        ]
                                    ),
                                ]
                            ),
                            #html.Br(),
                            dbc.Row(justify="start", children=
                                "Plot the institutions related to the concept (if you are looking for another concept, you can download its data bellow):"),
                            dcc.Dropdown(OA_concepts.get_concepts_institutions_names_downloaded(), default_concept_plot, id='concept_dropdown', clearable=False),
                        ],
                        gap=2,
                    ),
                ],
                **layout_parameters.layout_dynamic_width
            ),
            html.Div(id='div_single_concept_plot', style={'width': layout_parameters.default_graph_width, 'margin': layout_parameters.default_graph_margin}, children=[
                dcc.Loading(
                    id="loading-1",
                    children=[
                        dcc.Graph(
                        id='main_institutions_plot',
                        ),
                    ],
                    type="default",
                    parent_style={'visibility': 'visible'}
                ),
                html.Div(id='div_download_data_single_concept',
                    style={'display': 'inline-block', 'margin-right': layout_parameters.default_big_margin},
                    children=[
                        dbc.Button(id='button_download_data_single_concept',
                            children="Download dataset as CSV",),
                        dcc.Download(id="download_data_single_concept")
                    ]
                ),
                html.Div(id='div_download_list_institutions_selected_single_concept',
                    style={'display': 'inline-block', 'margin-right': layout_parameters.default_big_margin},
                    children=[
                        dbc.Button(id='button_download_list_institutions_selected_single_concept',
                            children="Download list of institutions selected as CSV",),
                        dcc.Download(id="download_list_institutions_selected_single_concept")
                    ]
                ),

            ])
        ]
    ), #width={"size": 12, "offset": 0}, xl={"size": 8, "offset": 2}),
    # html.Div(id='add_institutions_concept_div', style={'width': default_div_width, 'margin': '1em auto'}, children=[
    #html.Div(id='add_institutions_concept_div', style={'margin': '1em 1em'}, children=[
    dbc.Row(justify="center", style={'margin': '1em 1em'}, children=
        [
            dbc.Col(
                [
                    html.H2(id='title_add_institutions_concept',
                    #style={'displprogress_concept_dropdownay': 'inline-block', 'margin-right': '25px'},
                    children="Add dataset from OpenAlex"),
                    "Only a limited number of dataset are stored on the server and available to plot but you can download more here (it will be stored on the server and available to plot on this webapp).",
                    # html.Div(id='concepts_download_div', children=[
                    dbc.Row(
                        [
                            dbc.Col(html.Div(children="Add another concept:",
                                # style={'display': 'inline-block'}
                            )),
                            dbc.Col(
                                dcc.Dropdown(OA_concepts.get_concepts_institutions_names_downloadable(), id='concept_download_dropdown'),
                                sm = 9, md = 7
                            ),
                            dbc.Col(dbc.Button(id="button_start_concept_download_dropdown",
                                children="Add this concept",
                                disabled=True,
                                # style={'display': 'inline-block', 'margin-left': default_big_margin}
                            )),
                            dbc.Col(dbc.Button(id="button_cancel_concept_download_dropdown",
                                children="Cancel",
                                disabled=True,
                                # style={'display': 'inline-block', 'margin-left': default_big_margin}
                            )),
                            # dcc.Interval(id="progress_concept_dropdown_interval", n_intervals=0, interval=500),
                            #html.Progress
                        ]
                    ),
                    html.Div(children=dbc.Progress(id='progress_concept_download_dropdown', animated=True, striped=True),
                        style={'visibility': 'hidden'}
                    ),
                    html.Div(children="Downloading progress: 0%",
                        id='percentage_concept_download_dropdown',
                        # style={'visibility': 'hidden'}
                    ),
                ],
                **layout_parameters.layout_dynamic_width
            ),
        ]
    ),
    # html.Div(id='multi_concepts_div', style={'width': default_div_width, 'margin': '1em auto'}, children=[
    #html.Div(id='multi_concepts_div', style={'margin': '1em 1em'}, children=[
    dbc.Row(justify="center", style={'margin': '1em 1em'}, children=
        [
            dbc.Col(
                [
                    html.H2(id='title_multi_concepts_plot',
                    #style={'displprogress_concept_dropdownay': 'inline-block', 'margin-right': '25px'},
                    children="Multi concepts plot"),
                    "This graph allows you to plot the institutions related to different concepts. Plot the institutions from the following datasets:",
                    #"Plot institutions from the following concepts on the same graph:",
                    dcc.Dropdown(OA_concepts.get_concepts_institutions_names_downloaded(), id='multi_concept_institution_from_dropdown', multi=True),
                    'Remember that the "Works threshold" and "Cited by average threshold" defined above will hide the institutions not fitting them.',
                    html.Br(),
                    "Then, you can optionally apply filters based on specific concept scores:",
                    dbc.Button("Add filter", id="add_filter_btn", style={'display': 'inline-block', 'margin-left': layout_parameters.default_margin},),
                    dbc.Button("Remove filter", id="remove_filter_btn", style={'display': 'inline-block', 'margin-left': layout_parameters.default_margin},),
                    html.Div(id="concepts_filters_container", children=[]),
                    'The "Average combined concepts score" is the average of the score of the concepts selected to plot the institutions from (aka the average of the score of the concepts selected in the menu right after Multi concepts plot)',
                    dbc.Button("Plot multi concept graph", id="plot_multi_concept_graph_button", style={'display': 'inline-block', 'margin-left': layout_parameters.default_margin},),
                    html.Div(id='plot_multi_concept_graph_button_infos',
                                style={'display': 'inline-block', 'margin-left': layout_parameters.default_big_margin, 'color': 'red'},
                                children=""),
                    html.Div(id='multi_concept_institutions_plot_number',
                                style={'display': 'inline-block', 'margin-left': layout_parameters.default_big_margin},
                                children="0 institutions plotted."),                    
                ],
                **layout_parameters.layout_dynamic_width
            ),
            #html.Div(id='div_multi_concept_plot', style={'width': default_graph_width, 'margin': default_graph_margin}, children=[
            dbc.Row(
                [
                    dcc.Loading(
                        id="loading_graph_multi_concepts",
                        children=[
                            dcc.Graph(id='multi_concept_institutions_plot'),
                        ],
                        type="default",
                        parent_style={'visibility': 'visible'}
                    ),
                    #html.Div(id='div_download_list_institutions_mult_concept',
                    html.Div(
                        [
                            dbc.Button(id='button_download_list_institutions_mult_concept',
                                children="Download list of institutions as CSV"
                            ),
                            dcc.Download(id="download_list_institutions_mult_concept"),
                            html.Br(),
                            html.Br(),
                            html.Br(),
                            html.Br(),
                        ]
                    ),

                ]
            )
        ]
    )
])


layout = html.Div(children=
    [
        html.Div(
            id="div-loading",
            children=
                [
                    dash_loading_spinners.ClimbingBox(#Pacman(
                        fullscreen=True, 
                        id="loading-whole-app"
                    )
                ]
        ),
        main_container
    ]
)
    
    #style={'width': '98%', 'margin': 'auto'})


@app.callback(
    Output("div-loading", "children"),
    Input("div-app", "loading_state"),
    State("div-loading", "children"),
)
def hide_loading_after_startup(loading_state, children):
    if children:
        # print("remove loading spinner!")
        return None
    # print("spinner already gone!")
    raise PreventUpdate


@app.callback(
    [Output('main_institutions_plot', 'figure'), Output(component_id='n_selected_institutions_output', component_property='children')],
    Input('input_x_threshold', 'value'),
    Input('input_y_threshold', 'value'),
    Input('input_cited_by_average_threshold', 'value'),
    Input('display_only_selected_institutions', 'value'),
    Input('display_threshold_lines', 'value'),
    Input('concept_dropdown', 'value'),
    prevent_initial_call=True,
)
def update_plot_and_text_infos(x_threshold, y_threshold, cited_by_threshold, display_only_selected_institutions, display_threshold_lines, concept_dropdown):
    if x_threshold == None or y_threshold == None or cited_by_threshold == None:
        raise PreventUpdate

    print("concept_dropdown:", concept_dropdown)
    
    iplt = InstitutionsPlot(concept_dropdown)
    plot_parameters = plot_parameters_template.copy()
    plot_parameters['plot_title'] = "Plot of the institutions related to "+OA_concepts.concepts_names[concept_dropdown]+" studies"
    plot_parameters['y_datas'] = concept_dropdown
    plot_parameters['y_legend'] = "Concept score ("+OA_concepts.concepts_names[concept_dropdown]+")"
    fig_out = iplt.get_figure_entities_selection_threshold(concept_dropdown, plot_parameters, x_threshold, y_threshold, cited_by_threshold, display_only_selected_institutions, display_threshold_lines, institution_to_highlight)
    html_text_out = f"Number of institutions selected: {iplt.get_number_of_entities_selected(x_threshold, y_threshold, cited_by_threshold, plot_parameters['x_datas'], plot_parameters['y_datas'])} (out of {len(iplt.entities_df)})"
    print("plotting...")
    return fig_out, html_text_out


@app.callback(
    Output("download_data_single_concept", "data"),
    Input("button_download_data_single_concept", "n_clicks"),
    State('concept_dropdown', 'value'),
    prevent_initial_call=True,
)
def downlad_data_plot_single_concept(n_clicks, concept_dropdown):
    ica = InstitutionsPlot(concept_dropdown)
    return dcc.send_data_frame(ica.entities_df.to_csv, ica.get_database_file_name(db_format = "csv"))
    

@app.callback(
    Output("download_list_institutions_selected_single_concept", "data"),
    Input("button_download_list_institutions_selected_single_concept", "n_clicks"),
    State('input_x_threshold', 'value'),
    State('input_y_threshold', 'value'),
    State('input_cited_by_average_threshold', 'value'),
    State('concept_dropdown', 'value'),
    prevent_initial_call=True,
)
def download_list_institutions_selected_single_concept(n_clicks, input_x_threshold, input_y_threshold, input_cited_by_average_threshold, concept_dropdown):
    ica = InstitutionsPlot(concept_dropdown)
    df_filters = {}
    if input_cited_by_average_threshold > 0:
        df_filters['works_cited_by_count_average'] = input_cited_by_average_threshold
    df_filters[plot_parameters_template['x_datas']] = input_x_threshold
    df_filters[concept_dropdown] = input_y_threshold
    entities_df_filtered = ica.get_df_filtered_entities_selection_threshold(df_filters).reset_index(drop=True)
    return dcc.send_data_frame(entities_df_filtered.to_csv, ica.get_database_file_name(db_format = "csv", extra_text = "user_filtered"))


# Doc for pattern matching callbacks used to set dynamically the number of filter fields :
# https://dash.plotly.com/pattern-matching-callbacks

# Callback to disable download button if no concept selected
@app.callback(
    Output('button_start_concept_download_dropdown', 'disabled', allow_duplicate=True),
    Input('concept_download_dropdown', 'value'),
    prevent_initial_call=True,
)
def update_download_button_disabled_status(concept):
    disabled_download_btn = False
    if concept == None:
        disabled_download_btn = True
    return disabled_download_btn


@app.long_callback(
    prevent_initial_call=False, # the initial call will update the dropdown options
    output=[Output("concept_dropdown", "options"),
        Output("multi_concept_institution_from_dropdown", "options"),
        Output({'type': 'concept_filter_dropdown', 'index': ALL}, 'options'),
        Output("concept_download_dropdown", "options"),
        ],
    inputs=Input("button_start_concept_download_dropdown", "n_clicks"),
    state=[State("concept_download_dropdown", "value"), State({'type': 'concept_filter_dropdown', 'index': ALL}, 'value')],
    #inputs=Input("concept_download_dropdown", "value"),
    running=[
        (Output("button_start_concept_download_dropdown", "disabled"), True, True),
        (Output("button_cancel_concept_download_dropdown", "disabled"), False, True),
        (
            Output("progress_concept_download_dropdown", "style"),
            {"visibility": "visible", 'height': '12px', 'width': 'auto'},
            {"visibility": "hidden"},
        ),
        (
            Output("percentage_concept_download_dropdown", "style"),
            {"visibility": "visible", 'display': 'inline-block', 'margin-right': layout_parameters.default_big_margin},
            {"visibility": "hidden"},
        ),
    ],
    cancel=[Input("button_cancel_concept_download_dropdown", "n_clicks")],
    progress=[Output("progress_concept_download_dropdown", "value"), Output('percentage_concept_download_dropdown', 'children')]
)
def download_new_concept(set_progress, n_clicks, concept_dropdown, multi_concepts_dropdown):
    print(n_clicks)
    # if it's not the initial call
    if n_clicks != None:
        ica = InstitutionsPlot(concept_dropdown, allow_automatic_download = True, disable_tqdm_loading_bar = True, progress_fct_update = set_progress, create_dataframe = False)
        download_thread = threading.Thread(target=ica.download_list_entities)
        download_thread.start()
        while download_thread.is_alive():
            time.sleep(0.5)
            loading_text_info = f"Downloading progress: {round(ica.entitie_downloading_progress_percentage, 1)} %"
            if ica.entitie_downloading_progress_percentage >= 90:
                loading_text_info = "Please keep waiting, it may take a few more minutes..."
            set_progress((str(ica.entitie_downloading_progress_percentage), loading_text_info))
    updated_concepts_names_downloaded = OA_concepts.get_concepts_institutions_names_downloaded()
    # update the dropdown options and disable the download button
    return updated_concepts_names_downloaded, updated_concepts_names_downloaded, [updated_concepts_names_downloaded]*len(multi_concepts_dropdown), OA_concepts.get_concepts_institutions_names_downloadable()


# Callback to add new item to list
@app.callback(
    Output('concepts_filters_container', 'children'),#, allow_duplicate=True),
    Input('add_filter_btn', 'n_clicks'),
    #prevent_initial_call=True,
)
def add_item(button_clicked):
    # for initial call and bug?
    # the call back is called twice for one click
    if button_clicked == None:
        # we skip the callback
        return Patch()
    patched_children = Patch()
    # create the dropdown menu
    new_dropdown = dbc.Col(dcc.Dropdown(
                OA_concepts.get_concepts_institutions_names_downloaded(),
                id={'type': 'concept_filter_dropdown', 'index': button_clicked},
                style={'display': 'inline-block', 'width': '100%'}
            ),
            #style={'display': 'inline-block', 'verticalAlign': 'middle', 'width': '70%','margin-right': default_margin}
        lg=6
    )
    # create the input zone threshold
    new_input = dbc.Col(dbc.Input(
            id={'type': 'concept_filter_input', 'index': button_clicked},
            type='number',
            value=y_default_threshold,
            required=True,
            #size='5',
            #style={'display': 'inline-block', 'margin-right': default_margin}
        ),
        md=2, xxl=1
    )
    # create the div element containing the dropdown menu and input zone
    new_row = dbc.Row(children=[new_dropdown, "Concept score threshold: ", new_input])
    patched_children.append(new_row)
    return patched_children

# Callback to remove item from list
@app.callback(
    Output('concepts_filters_container', 'children', allow_duplicate=True),
    Input('remove_filter_btn', 'n_clicks'),
    prevent_initial_call=True,
)
def delete_item(button_clicked):
    patched_children = Patch()
    del patched_children[-1]
    return patched_children


# Callback to disable plot multi concepts graph button if not all concept filters selected
@app.callback(
    [Output('plot_multi_concept_graph_button', 'disabled'), Output('plot_multi_concept_graph_button_infos', 'children')],
    Input({'type': 'concept_filter_dropdown', 'index': ALL}, 'value'),
    Input('multi_concept_institution_from_dropdown', 'value'),
)
def update_plot_multi_concept_graph_button_disabled_status(concepts_filters, concepts_from):
    disabled_download_btn = False
    children_updated = ""
    if concepts_from == None:
        disabled_download_btn = True
        children_updated += "Please select at least one concept from where to pick the institutions to plot. "
    if None in concepts_filters:
        disabled_download_btn = True
        children_updated += "Please select a concept for each filter. "
    return disabled_download_btn, children_updated


# Callback to create the list of instituions filtered
@app.callback(
    [Output('multi_concept_institutions_plot', 'figure'),
    Output('multi_concept_institutions_plot_number', 'children')],
    Input('plot_multi_concept_graph_button', 'n_clicks'),
    State('multi_concept_institution_from_dropdown', 'value'),
    State({'type': 'concept_filter_dropdown', 'index': ALL}, 'value'),
    State({'type': 'concept_filter_input', 'index': ALL}, 'value'),
    State('input_x_threshold', 'value'),
    State('input_cited_by_average_threshold', 'value'),
    prevent_initial_call=True,
)
def update_plot_multi_concept_graph_button(button_clicked, concepts_from, concepts_filters, thresholds, x_threshold, cited_by_threshold):
    iplt = InstitutionsPlot()
    fig_out = iplt.get_figure_institutions_multi_concepts_filtered(plot_multi_concepts_parameters_template, concepts_from, concepts_filters, thresholds, x_threshold, cited_by_threshold, institution_to_highlight)
    return fig_out, str(len(iplt.entities_multi_filtered_df.index))+" institutions plotted."

        

@app.callback(
    Output("download_list_institutions_mult_concept", "data"),
    Input("button_download_list_institutions_mult_concept", "n_clicks"),
    State('multi_concept_institution_from_dropdown', 'value'),
    State({'type': 'concept_filter_dropdown', 'index': ALL}, 'value'),
    State({'type': 'concept_filter_input', 'index': ALL}, 'value'),
    State('input_x_threshold', 'value'),
    State('input_cited_by_average_threshold', 'value'),
    prevent_initial_call=True,
)
def download_list_institutions_mult_concept(n_clicks, concepts_from, concepts_filters, thresholds, x_threshold, cited_by_threshold):
    ica = InstitutionsPlot()
    ica.create_multi_concept_filters_entities_dataframe(concepts_from, concepts_filters, thresholds, plot_multi_concepts_parameters_template['x_datas'], x_threshold, cited_by_threshold)
    ica.add_average_combined_concept_score_to_multi_concept_entitie_df(concepts_from)
    return dcc.send_data_frame(ica.entities_multi_filtered_df.reset_index(drop=True).to_csv, "institutions_multi_concepts_user_filtered.csv")        
