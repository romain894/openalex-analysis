layout_dynamic_width = {'lg': 11, 'xl': 10, 'xxl': 9}

default_margin = '0.5%'
default_big_margin = '1.5%'
default_huge_margin = '5%'
default_div_width = '100%'#'60%'
default_graph_width = '100%'#'166%' # 1/0.7 = 1,428571429
default_graph_margin = '0 0'#'0 -33.2%' # 20×1,66  top/bot left/right

dash_table_style_cell = {
    'textAlign': 'left',
    # 'minWidth': '120px', 'width': '120px', 'maxWidth': '120px',
    'overflow': 'hidden',
    'textOverflow': 'ellipsis',
}

dash_table_conditional_style = [
    {
        'if': {'row_index': 'odd'},
        'backgroundColor': 'rgb(240, 240, 240)',
    }
]

# dash_table_ref_conditional_style = [
#     {
#         'if': {'column_id': 'referenced_works'},
#          'width': '30%'
#     },
#     {
#         'if': {'row_index': 'odd'},
#         'backgroundColor': 'rgb(240, 240, 240)',
#     },
#     {
#         'if': {'column_id': c},
#         'width': '15%'
#     } for c in params
# ]

dash_table_style_header = {
    'whiteSpace': 'normal',
    'height': '150px',#'auto',
    #'lineHeight': '15px'
}