import dash_bootstrap_components as dbc # dash app theme
from dash import Dash, dcc, html, Input, Output, State, ALL, Patch, CeleryManager
from dash.long_callback import CeleryLongCallbackManager
import dash
import dash_auth
from celery import Celery # for redis cache and long callback manager
from flask import Flask
import dash_loading_spinners
import os
from layout_parameters import *  

# Access passwords

if os.path.exists("dash_app_passwords.py"):
    from dash_app_passwords import *
    VALID_USERNAME_PASSWORD_PAIRS = dash_app_passwords
    print('OK: Loadeded the password from "dash_app_passwords.py"')
else:
    from dash_app_passwords_template import *
    VALID_USERNAME_PASSWORD_PAIRS = dash_app_passwords
    print("WARNING: Loaded the default user (admin) and password (admin), from the template file")
    print('Please copy the template file ("dash_app_passwords_template.py"), rename it and set the password in it')


version = os.environ.get('DASH_APP_VERSION', "V dev")
celery_broker_url = os.environ.get('DOCKER_CELERY_BROKER_URL', "redis://localhost:6379/0")
celery_backend_url = os.environ.get('DOCKER_CELERY_BACKEND_URL', "redis://localhost:6379/1")

celery_app = Celery(
    __name__, broker=celery_broker_url, backend=celery_backend_url
)

#redis_instance = redis.StrictRedis.from_url(get_redis_url())
#background_callback_manager = CeleryManager(celery_app, expire=60)
long_callback_manager = CeleryLongCallbackManager(celery_app)

dash_theme = dbc.themes.JOURNAL #PULSE

server = Flask(__name__)
# app = Dash(__name__, use_pages=True)
app = Dash(__name__, server=server, external_stylesheets=[dash_theme], long_callback_manager=long_callback_manager, use_pages=True)
app.title = 'OpenAlex Analysis'


auth = dash_auth.BasicAuth(
    app,
    VALID_USERNAME_PASSWORD_PAIRS
)


navbar = dbc.NavbarSimple(
    children=[
        # html.Div(
        #     dcc.Link(
        #         f"{page['name']} - {page['path']}", href=page["relative_path"]

        #     )
        # )

        dbc.NavItem(dbc.NavLink(page['name'], href=page["relative_path"]))
        for page in dash.page_registry.values()
        # dbc.DropdownMenu(
        #     children=[
        #         dbc.DropdownMenuItem("More pages", header=True),
        #         dbc.DropdownMenuItem("Page 2", href="#"),
        #         dbc.DropdownMenuItem("Page 3", href="#"),
        #     ],
        #     nav=True,
        #     in_navbar=True,
        #     label="More",
        # ),
    ],
    brand="OpenAlex Analysis",
    brand_href="https://litserver.stockholmresilience.su.se/",
    color="primary",
    dark=True,
)


app.layout = dbc.Container(id="root", fluid=True, class_name="g-0", children=
    [
        html.Div(
            [
                # html.H1('Multi-page app with Dash Pages'),

                # html.Div(
                #     [
                #         html.Div(
                #             dcc.Link(
                #                 f"{page['name']} - {page['path']}", href=page["relative_path"]
                #             )
                #         )
                #         for page in dash.page_registry.values()
                #     ]
                # ),

                navbar,

                dash.page_container,

                html.Footer(
                    [
                        dbc.Row(justify="center", style={'margin': '1em 1em'}, children=
                            [
                                dbc.Col(
                                    [
                                        dbc.Row(
                                            [
                                                html.Hr(),
                                            ]
                                        ),
                                        dbc.Row(
                                            [
                                                dbc.Col(html.Div(html.A("Romain THOMAS 2023", href="https://github.com/romain894", target="blank"), style={'text-align':'left'})),
                                                dbc.Col(html.Div(html.A("Stockholm Resilience Centre", href="https://www.stockholmresilience.org/", target="blank"), style={'text-align':'center'})),
                                                dbc.Col(html.Div(version, style={'text-align':'right'})),
                                            ]
                                        ),
                                        dbc.Row(
                                            [
                                                dbc.Col(html.Div(html.A("romain.thomas@su.se", href="mailto:romain.thomas@su.se"), style={'text-align':'left'})),
                                                dbc.Col(html.Div(html.A("Source code", href="https://github.com/romain894/openalex-analysis", target="blank"), style={'text-align':'right'})),
                                            ]
                                        ),
                                    ],
                                    **layout_dynamic_width
                                )
                            ]
                        )
                    ]
                )
            ]
        )
    ]
)

# # for auto reloading : 
# #per_pageapp.run_server(mode="jupyterlab", debug=True)
# app.run_server(mode='inline', debug=True)

if __name__ == '__main__':
    app.run_server(host="127.0.0.1", port=8050, debug=True)#, dev_tools_ui=True, debug=True)