import dash
from dash import html, dcc
import dash_bootstrap_components as dbc # dash app theme
import os, sys
sys.path.append(os.path.abspath('../'))
from layout_parameters import *

dash.register_page(__name__, path='/')

layout = dbc.Container(fluid=True, children=
    [
        html.Div(children=
            [
                dbc.Row(justify="center", style={'margin': '1em 1em'}, children=
                    [
                        dbc.Col(
                            [
                                html.H1(children='Home page'),

                                html.Br(),

                                html.H2(children='Institutions plot'),

                                html.Div(children='''
                                    On this page, you can plot institutions related to one or multiple concepts. It's useful to get a list
                                    of institutions working within a field. You can filter these institutions and then download this list
                                    (button "Download list of institutions selected as CSV") to use it in the other page.
                                '''),

                                html.Br(),
                                html.Br(),

                                # html.H2(children='References analysis'),

                                html.H2(children='Institutions Comparison'),

                                html.Div(children='''
                                    Compare the usage of references or concepts between different institutions or between an institution and a concept.
                                '''),

                                html.Br(),
                                html.Br(),


                                html.Div(children='''
                                    For more explanation about the datas structure (eg Concepts, Works, Institutions...), you can check the documentation of OpenAlex:
                                '''),
                                html.A("https://docs.openalex.org/", href="https://docs.openalex.org/", target="_blank"),

                                html.Br(),
                                html.Br(),

                                html.Div(children='''
                                    In this web app, the number of entities (eg institutions or works) are limited to 10 000 per dataset. For example, when working on the works of x institutions,
                                    you will have x datasets of works, which can each contains 10 000 works.
                                '''),
                                # html.H3(children='Concept and institution references'),

                                # html.Div(children='''
                                #     Get the most cited works by the works of a selected concept and an institution.
                                # '''),
                            ],
                            **layout_dynamic_width
                        )
                    ]
                )
            ]
        )
    ]
)