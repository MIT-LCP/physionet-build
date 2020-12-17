# Project path configuration
from physionet.settings import base
# General package functionality
import re
import os
import wfdb
import math
import datetime
import numpy as np
import pandas as pd
import django.core.cache
# Data analysis and visualization
import dash
import plotly.graph_objs as go
import dash_core_components as dcc
import dash_html_components as html
from django_plotly_dash import DjangoDash
from plotly.subplots import make_subplots


# TODO: Include exceptions - https://dash.plotly.com/advanced-callbacks
# Specify the record file locations
BASE_DIR = base.BASE_DIR
FILE_ROOT = os.path.abspath(os.path.join(BASE_DIR, os.pardir))
FILE_LOCAL = os.path.join('demo-files', 'static', 'published-projects')
PROJECT_PATH = os.path.join(FILE_ROOT, FILE_LOCAL)
# Formatting settings
dropdown_width = '500px'
event_fontsize = '24px'
# Maximum number of signals to display on the page
max_display_sigs = 8
# Set the error text font size and color
error_fontsize = 18
error_color = 'rgb(255, 0, 0)'
# The list of annotation file extensions the system will check for
ann_classes = {'alh', 'alm', 'atr', 'atr_avf', 'atr_avl', 'atr_avr', 'atr_i',
               'atr_ii', 'atr_iii', 'atr_1', 'atr_2', 'atr_3', 'atr_4',
               'atr_5', 'atr_6','aux', 'blh', 'blm', 'bph', 'bpm', 'ecg',
               'marker', 'pwave', 'qrs', 'qrsc', 'st'}
# Set the default configuration of the plot top buttons
plot_config = {
    'displayModeBar': True,
    'modeBarButtonsToRemove': [
        'hoverClosestCartesian',
        'hoverCompareCartesian',
        'toggleSpikelines'
    ],
    'modeBarButtonsToAdd': [
        'sendDataToCloud',
        'editInChartStudio',
        'resetViews'
    ]
}


# Initialize the Dash App
app = DjangoDash(name = 'waveform_graph',
                 id = 'target_id',
                 assets_folder = 'assets')
# Specify the app layout
app.layout = html.Div([
    # Area to submit annotations
    html.Div([
        # The record dropdown
        html.Div([
            # The error display
            html.Div(
                id = 'error_text_sig',
                children = html.Span(''),
                style = {
                    'fontSize': error_fontsize,
                    'color': error_color
                }
            ),
            html.Div(
                id = 'error_text_graph',
                children = html.Span(''),
                style = {
                    'fontSize': error_fontsize,
                    'color': error_color
                }
            ),
            html.Label(['Select project to plot']),
            dcc.Dropdown(
                id = 'dropdown_dat',
                multi = False,
                clearable = False,
                searchable = True,
                persistence = False,
                placeholder = 'Please Select...',
                style = {'width': dropdown_width},
            ),
            html.Label(['Select record to plot']),
            dcc.Dropdown(
                id = 'dropdown_rec',
                multi = False,
                clearable = False,
                searchable = True,
                persistence = False,
                placeholder = 'Please Select...',
                style = {'width': dropdown_width},
            ),
            html.Label(['Input signals ({} maximum)'.format(max_display_sigs)]),
            dcc.Checklist(
                id = 'sig_name',
                options = [],
                value = [],
                labelStyle = {'display': 'inline-block'}
            ),
            html.Label(['Go to time (HH:MM:SS)']),
            dcc.Input(
                id = 'start_time',
                placeholder = '00:00:00',
                pattern = r'^((?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d$)',
                value = '00:00:00',
                debounce = True
            ),
            html.Br(),
            html.Label(['Display annotations']),
            dcc.RadioItems(
                id = 'annotation_status',
                options = [
                    {'label': 'On', 'value': 'On'},
                    {'label': 'Off', 'value': 'Off'}
                ],
                value = 'On'
            ),
            # Select previous or next annotation
            html.Button('Previous Record', id = 'previous_annotation'),
            html.Button('Next Record', id = 'next_annotation'),
        ], style = {'display': 'inline-block'}),
    ], style = {'display': 'inline-block', 'vertical-align': '0px'}),
    # The plot itself
    dcc.Loading(id = 'loading-1', children = [
        html.Div([
            dcc.Graph(
                id = 'the_graph',
                config = plot_config
            ),
        ], style = {'display': 'inline-block'})
    ], type = 'default'),
    # Hidden div inside the app that stores the project slug, version, and record
    dcc.Input(id = 'set_slug', type = 'hidden', value = ''),
    dcc.Input(id = 'set_version', type = 'hidden', value = ''),
    dcc.Input(id = 'set_record', type = 'hidden', value = ''),
])


# Dynamically update the record dropdown settings using the project 
# record and event
@app.callback(
    [dash.dependencies.Output('dropdown_dat', 'options'),
     dash.dependencies.Output('dropdown_dat', 'value')],
    [dash.dependencies.Input('previous_annotation', 'n_clicks_timestamp'),
     dash.dependencies.Input('next_annotation', 'n_clicks_timestamp'),
     dash.dependencies.Input('set_record', 'value')])
def get_dat_options(click_previous, click_next, dat_value):
    all_dirs = os.listdir(PROJECT_PATH)
    options_dat = [{'label': dir, 'value': dir} for dir in all_dirs]
    if dat_value == '':
        # Keep blank if loading main page (no presets)
        return_dat = None
    else:
        return_dat = dat_value
    return options_dat, return_dat


# Dynamically update the record dropdown settings using the project 
# record and event
@app.callback(
    [dash.dependencies.Output('dropdown_rec', 'options'),
     dash.dependencies.Output('dropdown_rec', 'value')],
    [dash.dependencies.Input('previous_annotation', 'n_clicks_timestamp'),
     dash.dependencies.Input('next_annotation', 'n_clicks_timestamp'),
     dash.dependencies.Input('dropdown_dat', 'value')],
    [dash.dependencies.State('set_record', 'value'),
     dash.dependencies.State('set_version', 'value')])
def get_records_options(click_previous, click_next, slug_value, record_value, version_value):
    # Return default values if called without all the information
    options_rec = []
    return_record = None
    if not slug_value or not version_value:
        return options_rec, return_record

    # Get the record file
    records_path = os.path.join(PROJECT_PATH, slug_value, version_value, 'RECORDS')
    with open(records_path, 'r') as f:
        all_records = f.read().splitlines()

    # Set the record options based on the current project
    options_rec = [{'label': rec, 'value': rec} for rec in all_records]

    # Set the value if provided
    if click_previous or click_next:
        # Determine which button was clicked
        ctx = dash.callback_context
        if ctx.triggered[0]['prop_id'].split('.')[0] == 'previous_annotation':
            click_time = click_previous
        else:
            click_time = click_next

        time_now = datetime.datetime.now()
        # Convert ms from epoch to datetime object
        click_time = datetime.datetime.fromtimestamp(click_time / 1000.0)
        # Consider next annotation desired if button was pressed in the
        # last 1 second... change this?
        # TODO: make this better
        if (time_now - click_time).total_seconds() < 1:
            if ctx.triggered[0]['prop_id'].split('.')[0] == 'previous_annotation':
                idx = all_records.index(record_value)
                if idx == 0:
                    # At the beginning of the list, go to the end
                    return_record = all_records[-1]
                else:
                    # Decrement the record if not the beginning of the list
                    # TODO: Decrement to the next non-annotated waveform instead?
                    return_record = all_records[idx-1]
            else:
                idx = all_records.index(record_value)
                if idx == (len(all_records) - 1):
                    # Reached the end of the list, go back to the beginning
                    return_record = all_records[0]
                else:
                    # Increment the record if not the end of the list
                    # TODO: Increment to the next non-annotated waveform instead?
                    return_record = all_records[idx+1]
        else:
            # Should theoretically never happen but here just in case
            return_record = record_value
    else:
        if record_value == '':
            # Keep blank if loading main page (no presets)
            return_record = None
        else:
            return_record = record_value

    return options_rec, return_record


# Update the sig_name value
@app.callback(
    [dash.dependencies.Output('sig_name', 'options'),
     dash.dependencies.Output('sig_name', 'value'),
     dash.dependencies.Output('error_text_sig', 'children')],
    [dash.dependencies.Input('dropdown_rec', 'value')],
    [dash.dependencies.State('dropdown_dat', 'value'),
     dash.dependencies.State('set_version', 'value')])
def update_sig(dropdown_rec, slug_value, version_value):
    # Set the default error text
    error_text = ['']
    options_sig = []
    return_sigs = []
    # Read the header file to get the signal names
    # TODO: Doesn't work on non-WFDB files
    if dropdown_rec and slug_value:
        header_path = os.path.join(PROJECT_PATH, slug_value, version_value,
                                   dropdown_rec)
    else:
        return options_sig, return_sigs, html.Span(error_text)
    try:
        header = wfdb.rdheader(header_path)
        options_sig = [{'label': sig, 'value': sig} for sig in header.sig_name]
        return_sigs = header.sig_name[:max_display_sigs]
    except FileNotFoundError:
        # Load the entire record instead to get the signal names
        # TODO: Make this faster by preventing double record load; return
        #       nothing and move it to the main callback though this wouldn't
        #       be updated? Might have to leave it like this...
        # Set the options and values (only the first `max_display_sigs` signals)
        try:
            sig_name = wfdb.rdsamp(header_path)[1]['sig_name']
            options_sig = [{'label': sig, 'value': sig} for sig in sig_name]
            return_sigs = sig_name[:max_display_sigs]
        except FileNotFoundError:
            error_text.extend(['ERROR_SIG: Record file not provided', html.Br()])
        except Exception as e:
            error_text.extend(['ERROR_SIG: Record/Header file incorrectly formatted... {}'.format(e), html.Br()])
    except Exception as e:
        error_text.extend(['ERROR_SIG: Header file (.hea) incorrectly formatted... {}'.format(e), html.Br()])
    return_error = html.Span(error_text)

    return options_sig, return_sigs, return_error


# Update the set_record value
@app.callback(
    [dash.dependencies.Output('set_record', 'value'),
     dash.dependencies.Output('set_dat', 'value')],
    [dash.dependencies.Input('the_graph', 'figure')],
    [dash.dependencies.State('dropdown_rec', 'value'),
     dash.dependencies.State('dropdown_dat', 'value')])
def update_rec(fig, dropdown_rec, dropdown_dat):
    if dropdown_rec:
        return_dropdown = dropdown_rec
    else:
        return_dropdown = ''
    if dropdown_dat:
        return_dat = dropdown_dat
    else:
        return_dat = ''
    
    return return_dropdown, return_dat


# Run the app using the chosen initial conditions
@app.callback(
    [dash.dependencies.Output('the_graph', 'figure'),
     dash.dependencies.Output('error_text_graph', 'children')],
    [dash.dependencies.Input('sig_name', 'value'),
     dash.dependencies.Input('start_time', 'value'),
     dash.dependencies.Input('annotation_status', 'value')],
    [dash.dependencies.State('dropdown_rec', 'value'),
     dash.dependencies.State('start_time', 'pattern'),
     dash.dependencies.State('dropdown_dat', 'value'),
     dash.dependencies.State('set_version', 'value')])
def update_graph(sig_name, start_time, annotation_status, dropdown_rec,
                 start_time_pattern, slug_value, version_value):
    print('HERE')
    # Preset the error text
    error_text = ['']
    # Check if valid number of input signals or input start time
    if dropdown_rec and (len(sig_name) == 0) or (len(sig_name) > max_display_sigs) or (re.compile(start_time_pattern).match(start_time) == None):
        # If not, plot the default graph
        dropdown_rec = None
        if (len(sig_name) == 0):
            error_text.extend(['ERROR_GRAPH: No input signals provided', html.Br()])
        elif (len(sig_name) > max_display_sigs):
            error_text.extend(['ERROR_GRAPH: Exceeded maximum input signals ({} maximum)'.format(max_display_sigs), html.Br()])
        elif (re.compile(start_time_pattern).match(start_time) == None):
            error_text.extend(['ERROR_GRAPH: Invalid start time provided', html.Br()])
    # The figure height and width
    max_plot_height = 750
    fig_width = 1103
    # The figure margins
    margin_left = 0
    margin_top = 25
    margin_right = 0
    margin_bottom = 0
    # Grid and zero-line color
    gridzero_color = 'rgb(200, 100, 100)'
    # The color and thickness of the signal
    sig_color = 'rgb(0, 0, 0)'
    sig_thickness = 1.5
    # The thickness of the annotation
    ann_color = 'rgb(0, 0, 200)'
    # ann_thickness = 0.67 * sig_thickness
    # ECG gridlines parameters
    grid_delta_major = 0.2
    # Set the maximum samples per second to increase speed
    max_fs = 100
    # Determine the start time of the record to plot (seconds)
    # Should always start at the beginning (default input is 00:00:00)
    start_time = sum(int(x) * 60 ** i for i, x in enumerate(reversed(start_time.split(':'))))
    # How much signal should be displayed after event (seconds)
    time_range = 60
    # Determine how much signal to display after event (seconds)
    window_size = 10
    # Standard deviation signal range
    std_range = 2
    # Set the initial dragmode (zoom, pan, etc.)
    drag_mode = 'pan'
    # Set the zoom restrictions
    x_zoom_fixed = False
    y_zoom_fixed = True

    # Set a blank plot if none is loaded
    if not dropdown_rec:
        # Create baseline figure with 1 subplot
        fig = make_subplots(
            rows = 1,
            cols = 1,
            shared_xaxes = True,
            vertical_spacing = 0
        )
        # Update the layout to match the loaded state
        fig.update_layout({
            'height': max_plot_height / 2,
            'width': fig_width,
            'margin': {
                'l': margin_left,
                't': margin_top,
                'r': margin_right,
                'b': margin_bottom
            },
            'grid': {
                'rows': 1,
                'columns': 1,
                'pattern': 'independent'
            },
            'showlegend': False,
            'hovermode': 'x',
            'dragmode': drag_mode
        })
        # Update the Null signal and axes
        fig.add_trace(go.Scatter({
            'x': [None],
            'y': [None]
        }), row = 1, col = 1)
        # Update axes based on signal type
        x_tick_vals = [round(n,1) for n in np.arange(0, 10.1, grid_delta_major).tolist()]
        x_tick_text = [str(round(n)) if n%1 == 0 else '' for n in x_tick_vals]
        y_tick_vals = [round(n,1) for n in np.arange(0, 2.25, grid_delta_major).tolist()]
        y_tick_text = [str(n) if n%1 == 0 else ' ' for n in y_tick_vals]
        # Create the empty chart
        fig.update_xaxes({
            'title': 'Time (s)',
            'fixedrange': x_zoom_fixed,
            'showgrid': True,
            'tickvals': x_tick_vals,
            'ticktext': x_tick_text,
            'showticklabels': True,
            'gridcolor': gridzero_color,
            'zeroline': False,
            'zerolinewidth': 1,
            'zerolinecolor': gridzero_color,
            'gridwidth': 1,
            'range': [0, 10],
            'rangeslider': {
                'visible': False
            }
        }, row = 1, col = 1)
        fig.update_yaxes({
            'fixedrange': y_zoom_fixed,
            'showgrid': True,
            'dtick': None,
            'showticklabels': True,
            'gridcolor': gridzero_color,
            'zeroline': False,
            'zerolinewidth': 1,
            'zerolinecolor': gridzero_color,
            'gridwidth': 1,
            'range': [0, 2.25],
        }, row = 1, col = 1)

        return (fig), html.Span(error_text)

    # Set some initial conditions
    record_path = os.path.join(PROJECT_PATH, slug_value, version_value,
                               dropdown_rec)

    # Read the requested record and extract relevent properties
    record = wfdb.rdsamp(record_path)
    fs = record[1]['fs']
    n_sig = len(sig_name)
    units = [None] * n_sig
    for i,s in enumerate(record[1]['sig_name']):
        if s in set(sig_name):
            units[sig_name.index(s)] = record[1]['units'][i]
    # Sort the list of signal names for better default grouping
    temp_zip = sorted(list(zip(sig_name, units)),
                      key = lambda x: x[0])
    sig_name = [t[0] for t in temp_zip]
    units = [t[1] for t in temp_zip]

    # Set the initial display range of y-values based on values in
    # initial range of x-values
    time_start = int(fs * start_time)
    if time_start > record[1]['sig_len']:
        max_time = str(datetime.timedelta(seconds=record[1]['sig_len'] / fs))
        error_text.extend(['ERROR_GRAPH: Start time exceeds signal length ({:0>8})'.format(max_time), html.Br()])
    time_stop = int(fs * (start_time + time_range))
    sig_len = time_stop - time_start

    # Down-sample signal to increase performance
    down_sample = int(fs / max_fs)
    if down_sample == 0:
        down_sample = 1

    # Determine the subplot graph height
    if n_sig == 1:
        fig_height = max_plot_height / 2
    else:
        fig_height = max_plot_height / n_sig
    if fig_height < 87.5:
        large_plot = True
    else:
        large_plot = False

    # Set the initial layout of the figure
    fig = make_subplots(
        rows = n_sig,
        cols = 1,
        shared_xaxes = True,
        vertical_spacing = 0
    )
    fig.update_layout({
        'height': fig_height * n_sig,
        'width': fig_width,
        'margin': {'l': margin_left,
                   't': margin_top,
                   'r': margin_right,
                   'b': margin_bottom},
        'grid': {
            'rows': n_sig,
            'columns': 1,
            'pattern': 'independent'
        },
        'showlegend': False,
        'hovermode': 'x',
        'dragmode': drag_mode,
        'spikedistance':  -1,
        'plot_bgcolor': '#ffffff',
        'paper_bgcolor': '#ffffff'
    })

    # Put all EKG signals before BP, then all others following
    sig_order = []
    ekg_sigs = {'II', 'V', 'ecg'}
    bp_sigs = {'ABP', 'abp'}
    if any(x not in ekg_sigs or 'ecg' not in x.lower() or 'ekg' not in x.lower() for x in sig_name):
        for i,s in enumerate(sig_name):
            if s in ekg_sigs or 'ecg' in s.lower() or 'ekg' in s.lower():
                sig_order.append(i)
        # TODO: Could maybe do this faster using sets
        for bps in bp_sigs:
            if bps in sig_name:
                sig_order.append(sig_name.index(bps))
        for s in [y for x,y in enumerate(sig_name) if x not in set(sig_order)]:
            sig_order.append(sig_name.index(s))
    else:
        sig_order = range(n_sig)

    if any(x in ekg_sigs for x in sig_name):
        # Collect all the signals
        all_y_vals = []
        ekg_y_vals = []
        for r in sig_order:
            sig_name_index = record[1]['sig_name'].index(sig_name[r])
            current_y_vals = record[0][:,sig_name_index][time_start:time_stop:down_sample]
            current_y_vals = np.nan_to_num(current_y_vals).astype('float64')
            all_y_vals.append(current_y_vals)
            # Find unified range for all EKG signals
            if sig_name[r] in ekg_sigs:
                ekg_y_vals.append(current_y_vals)

        # Flatten and change data type to prevent overflow
        ekg_y_vals = np.stack(ekg_y_vals).flatten()
        # Filter out extreme values from being shown on graph range
        # This uses the Coefficient of Variation (CV) approach to determine
        # significant changes in the signal... If a significant variation in
        # signal is found then filter out extrema using normal distribution
        # TODO: Prevent repeat code for non-EKG signals
        temp_std = np.nanstd(ekg_y_vals)
        temp_mean = np.mean(ekg_y_vals[np.isfinite(ekg_y_vals)])
        temp_nan = np.all(np.isnan(ekg_y_vals))
        small_var_criteria = abs(temp_std / temp_mean) > 0.1
        if small_var_criteria and not temp_nan:
            ekg_y_vals = ekg_y_vals[abs(ekg_y_vals - temp_mean) < std_range * temp_std]
        # Set default min and max values if all NaN
        if temp_nan:
            min_ekg_y_vals = -1
            max_ekg_y_vals = 1
        else:
            if small_var_criteria:
                min_ekg_y_vals = np.nanmin(ekg_y_vals)
                max_ekg_y_vals = np.nanmax(ekg_y_vals)
            else:
                min_ekg_y_vals = np.nanmin(ekg_y_vals) - 1
                max_ekg_y_vals = np.nanmax(ekg_y_vals) + 1
        min_ekg_tick = (round(min_ekg_y_vals / grid_delta_major) * grid_delta_major) - grid_delta_major
        max_ekg_tick = (round(max_ekg_y_vals / grid_delta_major) * grid_delta_major) + grid_delta_major
    else:
        # Collect all the signals
        all_y_vals = []
        for r in sig_order:
            try:
                sig_name_index = record[1]['sig_name'].index(sig_name[r])
                current_y_vals = record[0][:,sig_name_index][time_start:time_stop:down_sample]
                current_y_vals = np.nan_to_num(current_y_vals).astype('float64')
                all_y_vals.append(current_y_vals)
            except Exception as e:
                error_text.extend(['ERROR_GRAPH: Record file (.dat) can not be read... {}'.format(e), html.Br()])

    # Attempt to load in annotations if available
    anns = []
    anns_idx = []
    folder_path = os.path.join(PROJECT_PATH, slug_value, version_value)
    ann_path = os.path.join(folder_path, dropdown_rec)
    if annotation_status == 'On':
        try:
            # Read the annotation metadata (ANNOTATORS) if any
            with open(os.path.join(folder_path, 'ANNOTATORS'), 'r') as f:
                ann_ext = [l.split('\t')[0] for l in f.readlines()]
            for ext in ann_ext:
                try:
                    current_ann = wfdb.rdann(ann_path, ext)
                    anns.append(current_ann)
                    anns_idx.append(list(filter(lambda x: (current_ann.sample[x] > time_start) and (current_ann.sample[x] < time_stop), range(len(current_ann.sample)))))
                except Exception as e:
                    error_text.extend(['ERROR_GRAPH: Annotation file ({}.{}) can not be read... {}'.format(ann_path,ext,e), html.Br()])
        except IOError:
            # Can't find ANNOTATORS file, guess what annotation files are and
            # show warning in case annotation was expected (known extension
            # found in directory)
            os_path = str(os.sep).join(ann_path.split(os.sep)[:-1])
            possible_files = [d for d in os.listdir(os_path) if len(d.split('.')) > 1]
            if any(x.split('.')[-1] in ann_classes for x in set(possible_files)):
                # Annotation file found
                error_text.extend(['WARNING_GRAPH: Annotation files found, but ANNOTATORS file not found', html.Br()])
                for i,f in enumerate(possible_files):
                    ext = f.split('.')[-1]
                    if ext in ann_classes:
                        try:
                            current_ann = wfdb.rdann(ann_path, ext)
                            anns.append(current_ann)
                            anns_idx.append(list(filter(lambda x: (current_ann.sample[x] > time_start) and (current_ann.sample[x] < time_stop), range(len(current_ann.sample)))))
                        except Exception as e:
                            error_text.extend(['ERROR_GRAPH: Annotation file ({}) can not be read... {}'.format(f,e), html.Br()])
        except Exception as e:
            error_text.extend(['ERROR_GRAPH: {}'.format(e), html.Br()])

    # Name the axes to create the subplots
    x_vals = [start_time + (i / fs) for i in range(sig_len)][::down_sample]
    for idx,r in enumerate(sig_order):
        # Create the tags for each plot
        x_string = 'x' + str(idx+1)
        y_string = 'y' + str(idx+1)
        # Generate the waveform x-values and y-values
        y_vals = all_y_vals[idx]
        # Set the initial y-axis parameters
        if sig_name[r] in ekg_sigs:
            min_y_vals = min_ekg_y_vals
            max_y_vals = max_ekg_y_vals
            grid_state = True
            dtick_state = grid_delta_major
            zeroline_state = True
            if large_plot:
                y_tick_vals = [(min_ekg_tick + max_ekg_tick) / 2]
                y_tick_text = ['{} ({})'.format(sig_name[r], units[r])]
            else:
                y_tick_vals = [round(n,1) for n in np.arange(min_ekg_tick, max_ekg_tick, grid_delta_major).tolist()][1:-1]
                # Max text length to fit should be ~8
                # Multiply by (1/grid_delta_major) to account for fractions
                while len(y_tick_vals) > (1/grid_delta_major)*8:
                    y_tick_vals = y_tick_vals[::2]
                y_tick_text = [str(n) if n%1 == 0 else ' ' for n in y_tick_vals]
        else:
            # Remove outliers to prevent weird axes scaling if possible
            # TODO: Refactor this!
            temp_std = np.nanstd(y_vals)
            temp_mean = np.mean(y_vals[np.isfinite(y_vals)])
            temp_nan = np.all(np.isnan(y_vals))
            small_var_criteria = (temp_std / temp_mean) > 0.1
            if small_var_criteria and not temp_nan:
                extreme_y_vals = y_vals[abs(y_vals - temp_mean) < std_range * temp_std]
            else:
                extreme_y_vals = y_vals
            # Set default min and max values if all NaN
            if temp_nan:
                min_y_vals = -1
                max_y_vals = 1
            else:
                if small_var_criteria:
                    min_y_vals = np.nanmin(extreme_y_vals)
                    max_y_vals = np.nanmax(extreme_y_vals)
                else:
                    min_y_vals = np.nanmin(extreme_y_vals) - 1
                    max_y_vals = np.nanmax(extreme_y_vals) + 1
            grid_state = True
            dtick_state = None
            zeroline_state = False
            x_tick_vals = []
            x_tick_text = []
            if large_plot:
                y_tick_vals = [(min_y_vals + max_y_vals) / 2]
                y_tick_text = ['{} ({})'.format(sig_name[r], units[r])]
            else:
                y_tick_vals = [round(n,1) for n in np.linspace(min_y_vals, max_y_vals, 8).tolist()][1:-1]
                y_tick_text = [str(n) for n in y_tick_vals]

        if large_plot:
            y_title = None
        else:
            y_title = '{}({})'.format(sig_name[r], units[r])

        # Create the signal to plot
        fig.add_trace(go.Scatter({
            'x': x_vals,
            'y': y_vals,
            'xaxis': x_string,
            'yaxis': y_string,
            'type': 'scatter',
            'line': {
                'color': sig_color,
                'width': sig_thickness
            },
            'name': sig_name[r]
        }), row = idx+1, col = 1)

        # Display where the events are if any
        if anns != [] and idx == 0:
            for i,ann in enumerate(anns):
                for a in anns_idx[i]:
                    # Add only the label due to the hover feature... add
                    # the lines later though much slower? 
                    # fig.add_shape({
                    #     'type': 'line',
                    #     'x0': float(ann.sample[a] / fs),
                    #     'y0': min_y_vals - 0.5 * (max_y_vals - min_y_vals),
                    #     'x1': float(ann.sample[a] / fs),
                    #     'y1': max_y_vals + 0.5 * (max_y_vals - min_y_vals),
                    #     'xref': x_string,
                    #     'yref': y_string,
                    #     'line': {
                    #         'color': ann_color,
                    #         'width': ann_thickness
                    #     }
                    # })
                    fig.add_annotation({
                        'x': float(ann.sample[a] / fs),# + 0.1, <-- add if line
                        'y': max_y_vals,
                        'text': ann.symbol[a],
                        'showarrow': False,
                        'font': {
                            'size': 18,
                            'color': ann_color
                        }
                    })

        # Set the initial x-axis parameters
        x_tick_vals = [round(n,1) for n in np.arange(start_time, start_time + time_range, grid_delta_major).tolist()]
        x_tick_text = [str(round(n)) if n%1 == 0 else '' for n in x_tick_vals]
        if idx != (n_sig - 1):
            fig.update_xaxes({
                'title': None,
                'fixedrange': x_zoom_fixed,
                'dtick': 0.2,
                'showticklabels': False,
                'gridcolor': gridzero_color,
                'gridwidth': 1,
                'zeroline': zeroline_state,
                'zerolinewidth': 1,
                'zerolinecolor': gridzero_color,
                'range': [start_time, start_time + window_size],
                'showspikes': True,
                'spikemode': 'across',
                'spikesnap': 'cursor',
                'showline': True,
            }, row = idx+1, col = 1)
        else:
            # Add the x-axis title to the bottom figure
            fig.update_xaxes({
                'title': 'Time (s)',
                'fixedrange': x_zoom_fixed,
                'dtick': 0.2,
                'showticklabels': True,
                'tickvals': x_tick_vals,
                'ticktext': x_tick_text,
                'gridcolor': gridzero_color,
                'gridwidth': 1,
                'zeroline': zeroline_state,
                'zerolinewidth': 1,
                'zerolinecolor': gridzero_color,
                'range': [start_time, start_time + window_size],
                'showspikes': True,
                'spikemode': 'across',
                'spikesnap': 'cursor',
                'showline': True,
            }, row = idx+1, col = 1)

        # Set the initial y-axis parameters
        fig.update_yaxes({
            'title': y_title,
            'fixedrange': y_zoom_fixed,
            'showgrid': grid_state,
            'showticklabels': True,
            'tickvals': y_tick_vals,
            'ticktext': y_tick_text,
            'gridcolor': gridzero_color,
            'zeroline': zeroline_state,
            'zerolinewidth': 1,
            'zerolinecolor': gridzero_color,
            'gridwidth': 1,
            'range': [min_y_vals, max_y_vals],
        }, row = idx+1, col = 1)

        fig.update_traces(xaxis = x_string)

        # Adjust the font size based on the number
        # of signals
        if n_sig <= 8:
            font_size = 16 - n_sig
            fig.update_layout({
                'font': {
                    'size': font_size
                }
            })

    return (fig), html.Span(error_text)
