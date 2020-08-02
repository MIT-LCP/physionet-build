import os
import wfdb
from physionet.settings import base
import pandas as pd
import django.core.cache
import math
# Data analysis and visualization
import dash
from django_plotly_dash import DjangoDash
import dash_core_components as dcc
import dash_html_components as html
import plotly.graph_objs as go
from plotly.subplots import make_subplots


# Specify the record file locations
BASE_DIR = base.BASE_DIR
FILE_ROOT = os.path.abspath(os.path.join(BASE_DIR, os.pardir))
FILE_LOCAL = os.path.join('demo-files', 'static', 'published-projects')
# Formatting settings
dropdown_width = "300px"

# Initialize the Dash App
app = DjangoDash(name='waveform_graph', id='target_id', assets_folder="assets")
# Specify the app layout
app.layout = html.Div([
    # The record dropdown
    html.Div([
        html.Label(['Select Record to Plot']),
        dcc.Dropdown(
            id = 'dropdown_rec',
            multi = False,
            clearable = False,
            searchable = True,
            placeholder = 'Please Select...',
            style = {"width": dropdown_width},
            persistence = True,
            persistence_type = 'session',
        ),
    ]),
    # The signal dropdown
    html.Div([
        html.Label(['Select Signal to Plot']),
        dcc.Dropdown(
            id = 'dropdown_sig',
            multi = False,
            clearable = False,
            searchable = True,
            placeholder = 'Please Select...',
            style = {"width": dropdown_width},
            persistence = True,
            persistence_type = 'session',
        ),
    ]),
    # The plot itself
    html.Div([
        dcc.Graph(id = 'the_graph'),
    ]),
    # Hidden div inside the app that stores the project slug and version
    dcc.Input(id = 'target_id', type = 'hidden', value = ''),
])

# Dynamically update the record dropdown settings using the project 
# slug and version
@app.callback(
    dash.dependencies.Output('dropdown_rec', 'options'),
    [dash.dependencies.Input('target_id', 'value')])
def get_records_options(target_id):
    # Get the record file
    project_slug = target_id['project_slug']
    version = target_id['version']
    project_path = os.path.join(FILE_ROOT, FILE_LOCAL, project_slug, version)
    records_path = os.path.join(project_path, 'RECORDS')
    with open(records_path, 'r') as f:
        all_records = f.read().splitlines()

    # Set the record options based on the current project
    options_rec = [{'label': rec, 'value': rec} for rec in all_records]

    return options_rec


# Dynamically update the signal dropdown settings using the record name, project 
# slug, and version
@app.callback(
    dash.dependencies.Output('dropdown_sig', 'options'),
    [dash.dependencies.Input('dropdown_rec', 'value'),
     dash.dependencies.Input('target_id', 'value')])
def get_signal_options(dropdown_rec, target_id):
    # Get the record file
    project_slug = target_id['project_slug']
    version = target_id['version']
    record_path = os.path.join(FILE_ROOT, FILE_LOCAL, project_slug,
                               version, dropdown_rec)
    record = wfdb.rdrecord(record_path)

    # Set the options based on the signal names of the chosen record 
    options_sig = [{'label': sig, 'value': sig} for sig in record.sig_name]

    return options_sig


# Run the app using the chosen initial conditions
@app.callback(
    dash.dependencies.Output('the_graph', 'figure'),
    [dash.dependencies.Input('dropdown_rec', 'value'),
     dash.dependencies.Input('dropdown_sig', 'value'),
     dash.dependencies.Input('target_id', 'value')])
def update_graph(dropdown_rec, dropdown_sig, target_id):
    # Set some initial conditions
    project_slug = target_id['project_slug']
    version = target_id['version']
    record_path = os.path.join(FILE_ROOT, FILE_LOCAL, project_slug,
                               version, dropdown_rec)
    record = wfdb.rdrecord(record_path, channel_names=[dropdown_sig])

    # TODO: dynamically determine down_sample based on record.sig_len
    down_sample = 3
    # Grid and zero-line color
    gridzero_color = 'rgb(255, 60, 60)'
    # ECG gridlines parameters
    grid_delta_major = 0.2

    # Set the initial layout of the figure
    fig = make_subplots(rows=1, cols=1)
    fig.update_layout({
        'height': 600,
        'title': 'Waveform of Record {} and Signal {}'.format(dropdown_rec, dropdown_sig),
        'grid': {
            'rows': 1,
            'columns': 1,
            'pattern': 'independent'
        },
        'showlegend': False
    })

    # Name the axes to create the subplots
    x_string = 'x1'
    y_string = 'y1'
    # Generate the waveform x-values and y-values
    x_vals = [(i / record.fs) for i in range(record.sig_len)][::down_sample]
    y_vals = record.p_signal[:,0][::down_sample]

    # Create the signal to plot
    fig.add_trace(go.Scatter({
        'x': x_vals,
        'y': y_vals,
        'xaxis': x_string,
        'yaxis': y_string,
        'type': 'scatter',
        'line': {
            'color': 'black',
            'width': 3
        },
        'name': record.sig_name[0]
    }), row = 1, col = 1)

    # Set the initial x-axis parameters
    fig.update_xaxes({
        'title': 'Time (s)',
        'dtick': grid_delta_major,
        'showticklabels': False,
        'gridcolor': gridzero_color,
        'zeroline': True,
        'zerolinewidth': 1,
        'zerolinecolor': gridzero_color,
        'gridwidth': 1,
        'range': [0,60],
        'rangeslider': {
            'visible': True
        }
    })

    # Set the initial y-axis parameters
    fig.update_yaxes({
        'title': record.sig_name[0] + ' (' + record.units[0] + ')',
        'fixedrange': True,
        'dtick': grid_delta_major,
        'gridcolor': gridzero_color,
        'zeroline': True,
        'zerolinewidth': 1,
        'zerolinecolor': gridzero_color,
        'gridwidth': 1
    })

    return (fig)
