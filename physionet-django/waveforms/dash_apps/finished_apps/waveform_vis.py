# Project path configuration
from django.conf import settings
# General package functionality
import re
import os
import wfdb
import math
import datetime
import numpy as np
import pandas as pd
from scipy import stats
import django.core.cache
# Data analysis and visualization
import dash
import plotly.graph_objs as go
import dash_core_components as dcc
import dash_html_components as html
from django_plotly_dash import DjangoDash
from plotly.subplots import make_subplots


# Specify the record file locations
# PRIVATE_DBPATH: path to activate database directory within PUBLIC_ROOT
PRIVATE_DBPATH = 'active-projects'
# PUBLIC_DBPATH: path to main database directory within PUBLIC_ROOT
PUBLIC_DBPATH = 'published-projects'
# PUBLIC_ROOT: chroot directory for public databases
if settings.STATIC_ROOT:
    PUBLIC_ROOT = settings.STATIC_ROOT
else:
    PUBLIC_ROOT = os.path.join(settings.DEMO_FILE_ROOT, 'static')
# All the project slug directories live here
PROJECT_PATH = os.path.join(PUBLIC_ROOT, PUBLIC_DBPATH)
# Formatting settings
dropdown_width = '500px'
event_fontsize = '24px'
# Maximum number of signals to display on the page
max_display_sigs = 8
# Set the error text font size and color
error_fontsize = 18
error_color = 'rgb(255, 0, 0)'
# The list of annotation file extensions the system will check for
# Maybe in the future look for any files which aren't .dat for .hea though
# this could cause problems with CSV and other random files
ann_classes = {'abp', 'al', 'alh', 'anI', 'all', 'alm', 'apn', 'ari', 'arou',
               'atr', 'atr_avf', 'atr_avl', 'atr_avr', 'atr_i', 'atr_ii',
               'atr_iii', 'atr_1', 'atr_2', 'atr_3', 'atr_4', 'atr_5', 'atr_6',
               'aux', 'blh', 'blm', 'bph', 'bpm', 'comp', 'cvp', 'ecg',
               'event', 'flash', 'hypn', 'in', 'log', 'man', 'marker', 'not',
               'oart', 'pap', 'ple', 'pwave', 'pu', 'pu0', 'pu1', 'qrs',
               'qrsc', 'qt1', 'qt2', 'q1c', 'q2c', 'resp', 'st', 'sta', 'stb',
               'stc', 'trigger', 'trg', 'wabp', 'wqrs', 'win', '16a'}
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
    ],
    'toImageButtonOptions': {
        'width': 1103,
        'height': 750
    }
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
                id = 'error_text_rec',
                children = html.Span(''),
                style = {
                    'fontSize': error_fontsize,
                    'color': error_color
                }
            ),
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


def get_base_fig(max_plot_height, fig_width, margin_left, margin_top,
                 margin_right, margin_bottom, drag_mode, grid_delta_major,
                 x_zoom_fixed, gridzero_color, y_zoom_fixed):
    # Create baseline figure with 1 subplot
    base_fig = get_subplot(1)
    # Update the layout to match the loaded state
    base_fig.update_layout(
        get_layout(max_plot_height/2, fig_width, margin_left, margin_top,
                   margin_right, margin_bottom, 1, drag_mode, 16)
    )
    # Update the Null signal and axes
    base_fig.add_trace(
        get_trace([None], [None], None, None, None, None, None),
        row = 1, col = 1)
    # Update axes based on signal type
    x_tick_vals = [round(n,1) for n in np.arange(0, 10.1, grid_delta_major).tolist()]
    x_tick_text = [str(round(n)) if n%1 == 0 else '' for n in x_tick_vals]
    y_tick_vals = [round(n,1) for n in np.arange(0, 2.25, grid_delta_major).tolist()]
    y_tick_text = [str(n) if n%1 == 0 else ' ' for n in y_tick_vals]
    # Create the empty chart
    base_fig.update_xaxes(
        get_xaxis('Time (s)', x_zoom_fixed, grid_delta_major, True, x_tick_vals,
                  x_tick_text, gridzero_color, 0, 10.1),
        row = 1, col = 1)
    base_fig.update_yaxes(
        get_yaxis(None, y_zoom_fixed, y_tick_vals, y_tick_text, gridzero_color,
                  0, 2.25),
        row = 1, col = 1)
    return (base_fig)

def get_subplot(rows):
    return make_subplots(
        rows = rows,
        cols = 1,
        shared_xaxes = True,
        vertical_spacing = 0
    )

def get_layout(fig_height, fig_width, margin_left, margin_top, margin_right,
               margin_bottom, rows, drag_mode, font_size):
    return {
        'height': fig_height,
        'width': fig_width,
        'margin': {'l': margin_left,
                   't': margin_top,
                   'r': margin_right,
                   'b': margin_bottom},
        'grid': {
            'rows': rows,
            'columns': 1,
            'pattern': 'independent'
        },
        'showlegend': False,
        'hovermode': 'x',
        'dragmode': drag_mode,
        'spikedistance':  -1,
        'plot_bgcolor': '#ffffff',
        'paper_bgcolor': '#ffffff',
        'font_color': '#000000',
        'font': {
            'size': font_size
        }
    }

def get_trace(x_vals, y_vals, x_string, y_string, sig_color, sig_thickness, name):
    return go.Scatter({
        'x': x_vals,
        'y': y_vals,
        'xaxis': x_string,
        'yaxis': y_string,
        'type': 'scatter',
        'line': {
            'color': sig_color,
            'width': sig_thickness
        },
        'name': name
    })

def get_annotation(x_vals, y_vals, text, color):
    return {
        'x': x_vals,
        'y': y_vals,
        'text': text,
        'showarrow': False,
        'font': {
            'size': 18,
            'color': color
        }
    }

def get_xaxis(title, x_zoom_fixed, grid_delta_major, tick_labels, tick_vals,
              tick_text, gridzero_color, start_time, range_stop):
    return {
        'title': title,
        'fixedrange': x_zoom_fixed,
        'dtick': grid_delta_major,
        'showticklabels': tick_labels,
        'tickvals': tick_vals,
        'ticktext': tick_text,
        'tickfont': {
            'size': 16
        },
        'tickangle': 0,
        'gridcolor': gridzero_color,
        'gridwidth': 1,
        'zeroline': False,
        'range': [start_time, range_stop],
        'showspikes': True,
        'spikemode': 'across',
        'spikesnap': 'cursor',
        'showline': True
    }

def get_yaxis(y_title, y_zoom_fixed, y_tick_vals, y_tick_text, gridzero_color,
              min_y_vals, max_y_vals):
    return {
        'title': y_title,
        'fixedrange': y_zoom_fixed,
        'showgrid': True,
        'showticklabels': True,
        'tickvals': y_tick_vals,
        'ticktext': y_tick_text,
        'gridcolor': gridzero_color,
        'zeroline': False,
        'zerolinewidth': 1,
        'zerolinecolor': gridzero_color,
        'gridwidth': 1,
        'range': [min_y_vals, max_y_vals],
    }

def window_signal(y_vals):
    """
    This uses the Coefficient of Variation (CV) approach to determine
    significant changes in the signal then return the adjusted minimum
    and maximum range. If a significant variation is signal is found
    then filter out extrema using normal distribution. This method uses
    the Median Absolute Deviation in place of the typical Standard Deviation.
    """
    # Get parameters of the signal
    temp_std = stats.median_absolute_deviation(y_vals, nan_policy='omit')
    temp_mean = np.mean(y_vals[np.isfinite(y_vals)])
    temp_nan = np.all(np.isnan(y_vals))
    temp_zero = np.all(y_vals==0)
    if not temp_nan and not temp_zero:
        if (abs(temp_std / temp_mean) > 0.1) and (temp_std > 0.1):
            # Standard deviation signal range to window
            std_range = 10
            y_vals = y_vals[abs(y_vals - temp_mean) < std_range * temp_std]
            min_y_vals = np.nanmin(y_vals)
            max_y_vals = np.nanmax(y_vals)
        else:
            min_y_vals = np.nanmin(y_vals) - 1
            max_y_vals = np.nanmax(y_vals) + 1
    else:
        min_y_vals = -1
        max_y_vals = 1
    return min_y_vals, max_y_vals

def extract_signal(record_sigs, sig_name, rec_sig, time_start, time_stop, down_sample):
    sig_name_index = record_sigs.index(sig_name)
    y_vals = rec_sig[:,sig_name_index][time_start:time_stop:down_sample]
    y_vals = np.nan_to_num(y_vals).astype('float64')
    return y_vals

def get_ann_info(ann_path, ext, time_start, time_stop):
    current_ann = wfdb.rdann(ann_path, ext)
    current_ann_idx = list(filter(
        lambda x: (current_ann.sample[x] > time_start) and (current_ann.sample[x] < time_stop),
                   range(len(current_ann.sample))
    ))
    return current_ann, current_ann_idx

# Dynamically update the record dropdown settings using the project 
# record and event
@app.callback(
    [dash.dependencies.Output('dropdown_rec', 'options'),
     dash.dependencies.Output('dropdown_rec', 'value'),
     dash.dependencies.Output('error_text_rec', 'children')],
    [dash.dependencies.Input('previous_annotation', 'n_clicks_timestamp'),
     dash.dependencies.Input('next_annotation', 'n_clicks_timestamp'),
     dash.dependencies.Input('set_slug', 'value')],
    [dash.dependencies.State('set_record', 'value'),
     dash.dependencies.State('set_version', 'value')])
def get_records_options(click_previous, click_next, slug_value, record_value, version_value):
    # Set the default error text
    error_text = ['']
    # Return default values if called without all the information
    options_rec = []
    return_record = None
    if not slug_value and not version_value:
        return options_rec, return_record, error_text

    # Get the record file(s)
    # TODO: Maybe make this more concrete
    if slug_value.startswith('active_'):
        temp_path = os.path.join(settings.MEDIA_ROOT, PRIVATE_DBPATH)
        slug_value = '_'.join(slug_value.split('_')[1:])
        records_path = os.path.join(temp_path, slug_value, version_value)
    else:
        records_path = os.path.join(PROJECT_PATH, slug_value, version_value)
    records_file = os.path.join(records_path, 'RECORDS')

    try:
        with open(records_file, 'r') as f:
            all_records = f.read().splitlines()
    except FileNotFoundError:
        error_text.extend(['ERROR_REC: Record file not provided... {}'.format(records_file), html.Br()])
        return options_rec, return_record, error_text
    except Exception as e:
        error_text.extend(['ERROR_REC: Record file incorrectly formatted... {}'.format(e), html.Br()])
        return options_rec, return_record, error_text
    # TODO: Probably should refactor this
    temp_all_records = []
    for i,rec in enumerate(all_records):
        temp_path = os.path.join(records_path, rec)
        try:
            if 'RECORDS' in set(os.listdir(temp_path)):
                temp_file = os.path.join(temp_path, 'RECORDS')
                with open(temp_file, 'r') as f:
                    # Directory RECORDS values should always have a `/` at the end
                    temp_records = [rec + line.rstrip('\n') for line in f]
            temp_all_records.extend(temp_records)
        except FileNotFoundError:
            # No nested RECORDS files
            pass
        except NotADirectoryError:
            # No nested RECORDS files
            pass
        except Exception as e:
            error_text.extend(['ERROR_REC: Unable to read RECORDS file.. {}'.format(e), html.Br()])
            return options_rec, return_record, error_text
    if temp_all_records != []:
        all_records = temp_all_records

    # Set the record options based on the current project
    options_rec = [{'label': rec, 'value': rec} for rec in all_records]

    # Set the value if provided
    if click_previous or click_next:
        # Determine which button was clicked
        ctx = dash.callback_context
        click_id = ctx.triggered[0]['prop_id'].split('.')[0]
        if click_id == 'previous_annotation':
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
            if click_id == 'previous_annotation':
                idx = all_records.index(record_value)
                if idx == 0:
                    # At the beginning of the list, go to the end
                    return_record = all_records[-1]
                else:
                    # Decrement the record if not the beginning of the list
                    return_record = all_records[idx-1]
            else:
                idx = all_records.index(record_value)
                if idx == (len(all_records) - 1):
                    # Reached the end of the list, go back to the beginning
                    return_record = all_records[0]
                else:
                    # Increment the record if not the end of the list
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

    return options_rec, return_record, error_text

# Update the sig_name value
@app.callback(
    [dash.dependencies.Output('sig_name', 'options'),
     dash.dependencies.Output('sig_name', 'value'),
     dash.dependencies.Output('error_text_sig', 'children')],
    [dash.dependencies.Input('dropdown_rec', 'value')],
    [dash.dependencies.State('set_slug', 'value'),
     dash.dependencies.State('set_version', 'value')])
def update_sig(dropdown_rec, slug_value, version_value):
    # Set the default error text
    error_text = ['']
    options_sig = []
    return_sigs = []
    # Read the header file to get the signal names
    # TODO: Doesn't work on non-WFDB files
    if dropdown_rec and slug_value:
        # TODO: Maybe make this more concrete
        if slug_value.startswith('active_'):
            temp_path = os.path.join(settings.MEDIA_ROOT, PRIVATE_DBPATH)
            slug_value = '_'.join(slug_value.split('_')[1:])
            header_path = os.path.join(temp_path, slug_value, version_value,
                                       dropdown_rec)
        else:
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
        #       The best way may be to just add a submit button instead of
        #       dynamically updating.
        # Set the options and values (only the first `max_display_sigs` signals)
        try:
            if header_path.endswith('.edf'):
                sig_name = wfdb.edf2mit(header_path).sig_name
            else:
                sig_name = wfdb.rdsamp(header_path)[1]['sig_name']
            options_sig = [{'label': sig, 'value': sig} for sig in sig_name]
            return_sigs = sig_name[:max_display_sigs]
        except FileNotFoundError:
            error_text.extend(['ERROR_SIG: Record file not provided... {}'.format(header_path), html.Br()])
        except Exception as e:
            error_text.extend(['ERROR_SIG: Record/Header file incorrectly formatted... {}'.format(e), html.Br()])
    except Exception as e:
        error_text.extend(['ERROR_SIG: Header file (.hea) incorrectly formatted... {}'.format(e), html.Br()])
    return_error = html.Span(error_text)

    return options_sig, return_sigs, return_error

# Update the set_record value
@app.callback(
    dash.dependencies.Output('set_record', 'value'),
    [dash.dependencies.Input('the_graph', 'figure')],
    [dash.dependencies.State('dropdown_rec', 'value')])
def update_rec(fig, dropdown_rec):
    if dropdown_rec:
        return_dropdown = dropdown_rec
    else:
        return_dropdown = ''

    return return_dropdown

# Run the app using the chosen initial conditions
@app.callback(
    [dash.dependencies.Output('the_graph', 'figure'),
     dash.dependencies.Output('error_text_graph', 'children')],
    [dash.dependencies.Input('sig_name', 'value'),
     dash.dependencies.Input('start_time', 'value'),
     dash.dependencies.Input('annotation_status', 'value')],
    [dash.dependencies.State('dropdown_rec', 'value'),
     dash.dependencies.State('start_time', 'pattern'),
     dash.dependencies.State('set_slug', 'value'),
     dash.dependencies.State('set_version', 'value')])
def update_graph(sig_name, start_time, annotation_status, dropdown_rec,
                 start_time_pattern, slug_value, version_value):
    # Preset the error text
    error_text = ['']
    # Check if valid number of input signals or input start time
    if dropdown_rec and ((len(sig_name) == 0) or (len(sig_name) > max_display_sigs) or (re.compile(start_time_pattern).match(start_time) == None)):
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
    # Gridlines tick differential
    grid_delta_major = 0.1
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
        base_fig = get_base_fig(max_plot_height, fig_width, margin_left,
                                margin_top, margin_right, margin_bottom,
                                drag_mode, grid_delta_major, x_zoom_fixed,
                                gridzero_color, y_zoom_fixed)
        return base_fig, html.Span(error_text)

    # Set some initial conditions
    # TODO: Maybe make this more concrete
    if slug_value.startswith('active_'):
        project_path = os.path.join(settings.MEDIA_ROOT, PRIVATE_DBPATH)
        slug_value = '_'.join(slug_value.split('_')[1:])
    else:
        project_path = PROJECT_PATH
    record_path = os.path.join(project_path, slug_value, version_value,
                               dropdown_rec)

    # Read the requested record and extract relevent properties
    if record_path.endswith('.edf'):
        try:
            record = wfdb.edf2mit(record_path)
        except FileNotFoundError:
            base_fig = get_base_fig(max_plot_height, fig_width, margin_left,
                                    margin_top, margin_right, margin_bottom,
                                    drag_mode, grid_delta_major, x_zoom_fixed,
                                    gridzero_color, y_zoom_fixed)
            error_text.extend(['ERROR_SIG: EDF file not provided... {}'.format(record_path), html.Br()])
            return base_fig, html.Span(error_text)
        except Exception as e:
            base_fig = get_base_fig(max_plot_height, fig_width, margin_left,
                                    margin_top, margin_right, margin_bottom,
                                    drag_mode, grid_delta_major, x_zoom_fixed,
                                    gridzero_color, y_zoom_fixed)
            error_text.extend(['ERROR_SIG: EDF file incorrectly formatted... {}'.format(e), html.Br()])
            return base_fig, html.Span(error_text)
    else:
        try:
            record = wfdb.rdsamp(record_path)
        except FileNotFoundError:
            base_fig = get_base_fig(max_plot_height, fig_width, margin_left,
                                    margin_top, margin_right, margin_bottom,
                                    drag_mode, grid_delta_major, x_zoom_fixed,
                                    gridzero_color, y_zoom_fixed)
            error_text.extend(['ERROR_SIG: Record file not provided... {}'.format(record_path), html.Br()])
            return base_fig, html.Span(error_text)
        except Exception as e:
            base_fig = get_base_fig(max_plot_height, fig_width, margin_left,
                                    margin_top, margin_right, margin_bottom,
                                    drag_mode, grid_delta_major, x_zoom_fixed,
                                    gridzero_color, y_zoom_fixed)
            error_text.extend(['ERROR_SIG: Record/Header file incorrectly formatted... {}'.format(e), html.Br()])
            return base_fig, html.Span(error_text)
    # Read in the record information depending on its format
    try:
        record_sigs = record[1]['sig_name']
        fs = record[1]['fs']
        rec_len = record[1]['sig_len']
        rec_units = record[1]['units']
        rec_sig = record[0]
    except TypeError:
        record_sigs = record.sig_name
        fs = record.fs
        rec_len = record.sig_len
        rec_units = record.units
        rec_sig = record.p_signal
    # Sometimes multiple signals are named the same; this causes problems later
    if len(record_sigs) != len(set(record_sigs)):
        error_text.extend(['ERROR_GRAPH: Multiple signals are named the same; not all will be plotted', html.Br()])
    # Re-order the units
    n_sig = len(sig_name)
    units = [None] * n_sig
    for i,s in enumerate(record_sigs):
        if s in set(sig_name):
            units[sig_name.index(s)] = rec_units[i]

    # Set the initial display range of y-values based on values in
    # initial range of x-values
    time_start = int(fs * start_time)
    if time_start >= rec_len:
        max_time = str(datetime.timedelta(seconds = rec_len/fs))
        error_text.extend(['ERROR_GRAPH: Start time exceeds signal length ({:0>8})'.format(max_time), html.Br()])
    if start_time + time_range > rec_len/fs:
        time_stop = rec_len
        if (rec_len/fs - start_time) < window_size:
            range_stop = rec_len/fs
        else:
            range_stop = start_time  + window_size
    else:
        time_stop = int(fs * (start_time + time_range))
        range_stop = start_time + window_size
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

    # Adjust the font size based on the number of signals (should never
    # get too small due to the maximum allowed to be displayed)
    font_size = 16 - n_sig

    # Set the initial layout of the figure
    fig = get_subplot(n_sig)

    fig.update_layout(
        get_layout(fig_height*n_sig, fig_width, margin_left, margin_top,
                   margin_right, margin_bottom, n_sig, drag_mode, font_size)
    )

    # Attempt to load in annotations if available
    anns = []
    anns_idx = []
    folder_path = os.path.join(project_path, slug_value, version_value)
    ann_path = os.path.join(folder_path, dropdown_rec)
    os_path = str(os.sep).join(ann_path.split(os.sep)[:-1])
    if annotation_status == 'On':
        try:
            # Read the annotation metadata (ANNOTATORS) if any
            with open(os.path.join(folder_path, 'ANNOTATORS'), 'r') as f:
                ann_ext = [l.split('\t')[0] for l in f.readlines()]
            for ext in ann_ext:
                # Check if file exists first (some extensions are only for a
                # subset of all the records)
                if '.'.join([dropdown_rec, ext]).split(os.sep)[-1] in set(os.listdir(os_path)):
                    try:
                        current_ann, ann_idx = get_ann_info(ann_path, ext,
                                                            time_start, time_stop)
                        anns.append(current_ann)
                        anns_idx.append(ann_idx)
                    except Exception as e:
                        error_text.extend(['ERROR_GRAPH: Annotation file ({}.{}) can not be read... {}'.format(ann_path,ext,e), html.Br()])
        except IOError:
            # Can't find ANNOTATORS file, guess what annotation files are and
            # show warning in case annotation was expected (known extension
            # found in directory)
            possible_files = [d for d in os.listdir(os_path) if len(d.split('.')) > 1]
            if any(x.split('.')[-1] in ann_classes for x in set(possible_files)):
                # Annotation file found
                error_text.extend(['WARNING_GRAPH: Annotation files found, but ANNOTATORS file not found', html.Br()])
                for i,f in enumerate(possible_files):
                    ext = f.split('.')[-1]
                    if ext in ann_classes:
                        try:
                            current_ann, ann_idx = get_ann_info(ann_path, ext,
                                                                time_start, time_stop)
                            anns.append(current_ann)
                            anns_idx.append(ann_idx)
                            error_text.extend(['WARNING_GRAPH: Annotation file worked: {}'.format(f), html.Br()])
                        except Exception as e:
                            error_text.extend(['ERROR_GRAPH: Annotation file ({}) can not be read... {}'.format(f,e), html.Br()])
        except Exception as e:
            error_text.extend(['ERROR_GRAPH: {}'.format(e), html.Br()])

    # Name the axes to create the subplots
    x_vals = [start_time + (i / fs) for i in range(sig_len)][::down_sample]
    for s in range(n_sig):
        # Create the tags for each plot
        x_string = 'x' + str(s+1)
        y_string = 'y' + str(s+1)
        # Generate the waveform y-values
        try:
            y_vals = extract_signal(record_sigs, sig_name[s], rec_sig,
                                    time_start, time_stop, down_sample)
        except Exception as e:
            error_text.extend(['ERROR_GRAPH: Record file (.dat) can not be read... {}'.format(e), html.Br()])
        # Remove outliers to prevent weird axes scaling if possible
        min_y_vals, max_y_vals = window_signal(y_vals)
        # Set the initial y-axis parameters
        y_tick_vals = [round(n,1) for n in np.linspace(min_y_vals, max_y_vals, 8).tolist()][1:-1]
        y_tick_text = [str(n) for n in y_tick_vals]

        # Add line breaks for long titles
        # TODO: Make this cleaner (break at whitespaces if available)
        # Maximum length of title before wrapping
        max_title_length = 20 - n_sig
        y_title = '{} ({})'.format(sig_name[s], units[s])
        if len(y_title) > max_title_length:
            temp_title = ''.join(y_title.split('(')[:-1]).strip()
            temp_units = '(' + y_title.split('(')[-1]
            y_title = '<br>'.join(temp_title[z:z+max_title_length] for z in range(0, len(temp_title), max_title_length)) + '<br>' + temp_units

        # Create the signal to plot
        fig.add_trace(
            get_trace(x_vals, y_vals, x_string, y_string, sig_color,
                      sig_thickness, sig_name[s]),
            row = s+1, col = 1)

        # Display where the events are if any
        if anns != [] and s == 0:
            for i,ann in enumerate(anns):
                for a in anns_idx[i]:
                    # TODO: Use ann.symbol for now, but use ann.aux_note if
                    # it's possible (some are long and take up the whole
                    # screen and get really crowded... also some are empty...
                    # so maybe don't use it?)
                    fig.add_annotation(
                        get_annotation(float(ann.sample[a]/fs), max_y_vals,
                                       ann.symbol[a], ann_color)
                    )

        # Set the initial x-axis parameters
        x_tick_vals = [round(n,1) for n in np.arange(start_time, start_time + time_range, grid_delta_major).tolist()]
        x_tick_text = [str(round(n)) if n%1 == 0 else '' for n in x_tick_vals]
        if s != (n_sig - 1):
            fig.update_xaxes(
                get_xaxis(None, x_zoom_fixed, grid_delta_major, False, None,
                          None, gridzero_color, start_time, range_stop),
                row = s+1, col = 1)
        else:
            fig.update_xaxes(
                get_xaxis('Time (s)', x_zoom_fixed, grid_delta_major, True,
                          x_tick_vals, x_tick_text, gridzero_color, start_time,
                          range_stop),
                row = s+1, col = 1)

        # Set the initial y-axis parameters
        fig.update_yaxes(
            get_yaxis(y_title, y_zoom_fixed, y_tick_vals, y_tick_text,
                      gridzero_color, min_y_vals, max_y_vals),
            row = s+1, col = 1)

        fig.update_traces(xaxis = x_string)

    return (fig), html.Span(error_text)
