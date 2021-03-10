import datetime
import math
import os
import re

import dash
import dash_core_components as dcc
import dash_html_components as html
from django_plotly_dash import DjangoDash
import numpy as np
import pandas as pd
import plotly.graph_objs as go
from plotly.subplots import make_subplots
from scipy import stats
import wfdb

from django.conf import settings
import django.core.cache


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
max_display_sigs = 8
error_fontsize = 18
error_color = 'rgb(255, 0, 0)'

app = DjangoDash(name = 'waveform_graph',
                 id = 'target_id',
                 assets_folder = 'assets')

app.layout = html.Div([
    html.Div([
        html.Div([
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
                style = {'width': '500px'},
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
            html.Button('Previous Record', id = 'previous_annotation'),
            html.Button('Next Record', id = 'next_annotation'),
        ], style = {'display': 'inline-block'}),
    ], style = {'display': 'inline-block', 'vertical-align': '0px'}),
    dcc.Loading(id = 'loading-1', children = [
        html.Div([
            dcc.Graph(
                id = 'the_graph',
                config = {
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
            ),
        ], style = {'display': 'inline-block'})
    ], type = 'default'),
    dcc.Input(id = 'set_slug', type = 'hidden', value = ''),
    dcc.Input(id = 'set_version', type = 'hidden', value = ''),
    dcc.Input(id = 'set_record', type = 'hidden', value = ''),
])


def return_error(error, inputs=[]):
    """
    Return a formatted error based on a desired exception message and optional
    variable inputs which can be formatted in the string.

    Parameters
    ----------
    error : str
        A description of the error encountered.
    inputs : list[str], optional
        A list of inputs which will be insterted into the `error` string based
        on the desired formatting method.
        Ex. error='{}:{}', inputs=[1,2], returns=['1:2']

    Returns
    -------
    N/A : list
        Represents the elements inside of the final generated `div` container.
        For example, `html.Br()` can be added at the end the list to specify
        a line break after the error text.

    """
    return [error.format(*inputs), html.Br()]

def get_base_fig():
    """
    Generate the default figure to be used upon initial load, or when an error
    occurs. This should be nearly identical to the figure which is displayed
    when requesting a record except without a signal.

    Parameters
    ----------
    N/A

    Returns
    -------
    base_fig : plotly.graph_objects
        Represents the data used to define appearance of the figure (subplot
        layout, tick labels, etc.).

    """
    base_fig = get_subplot(1)
    base_fig.update_layout(
        get_layout(1)
    )
    # Get a trace object with no signal
    base_fig.add_trace(
        get_trace([None], [None], None, None, None),
        row = 1, col = 1)
    base_fig.update_xaxes(
        get_xaxis('Time (s)', True, 0, 10.1, 10.1),
        row = 1, col = 1)
    base_fig.update_yaxes(
        get_yaxis(None, 0, 2.25),
        row = 1, col = 1)
    return (base_fig)

def get_subplot(rows):
    """
    Create a graph layout based on the number of input signals (rows).

    Parameters
    ----------
    rows : int
        The number of signals or desired graph figures.

    Returns
    -------
    N/A : plotly.graph_objects
        Represents the data used to define appearance of the figure (subplot
        layout, tick labels, etc.).

    """
    return make_subplots(
        rows = rows,
        cols = 1,
        shared_xaxes = True,
        vertical_spacing = 0
    )

def get_layout(rows, max_plot_height=750, fig_width=1103, margin_left=0,
               margin_top=25, margin_right=0, margin_bottom=0,
               drag_mode='pan', font_size=16):
    """
    Generate a dictionary that is used to generate and format the layout of
    the figure.

    Parameters
    ----------
    rows : int
        The number of signals or desired graph figures.
    max_plot_height : float, int, optional
        The maximum height of the figure's SVG div. Notice, it is not called
        `fig_height` since this only applies to the wrapping container and the
        figure height is determined by dividing `max_plot_height` by the number
        of signals.
    fig_width : float, int, optional
        The width of the figure's SVG div.
    margin_left : float, int, optional
        How much margin should be to the left of the figure.
    margin_top : float, int, optional
        How much margin should be at the top of the figure.
    margin_right : float, int, optional
        How much margin should be to the right of the figure.
    margin_bottom : float, int, optional
        How much margin should be at the bottom of the figure.
    drag_mode : str, optional
        Set the initial dragmode (zoom, pan, etc.). See more here:
        https://plotly.com/javascript/reference/#layout-dragmode.
    font_size : int, optional
        The size of the font to be used for the ticks and labels.

    Returns
    -------
    N/A : dict
        Represents the layout of the figure.

    """
    return {
        'height': max_plot_height/2 if rows == 1 else max_plot_height,
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

def get_trace(x_vals, y_vals, x_string, y_string, name,
              sig_color='rgb(0, 0, 0)', sig_thickness=1.5):
    """
    Generate a dictionary that is used to generate and format the signal trace
    of the figure.

    Parameters
    ----------
    x_vals : list[float,int]
        The x-values to place the annotation.
    y_vals : list[float,int]
        The y-values to place the annotation.
    x_string : str
        Indicates which x-axis the signal belongs with.
    y_string : str
        Indicates which y-axis the signal belongs with.
    name : str
        The name of the signal.
    sig_color : str, optional
        A string of the RGB representation of the desired signal color.
        Ex: 'rgb(20,40,100)'
    sig_thickness : float, int, optional
        Specifies the thickness of the signal.

    Returns
    -------
    N/A : dict
        Represents the layout of the signal.

    """
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

def get_record_path(slug, version, rec):
    """
    Get the correct file path of the record based on whether it's and active
    project or not.

    Parameters
    ----------
    slug : str
        The slug of the project.
    version : str
        The version of the project.
    rec : str
        The desired record from the project.

    Returns
    -------
    rec_path : str
        The file path of the record.
    project_path : str
        The file path of the location where all projects (either active or
        published) are stored.

    """
    if slug.startswith('active_'):
        project_path = os.path.join(settings.MEDIA_ROOT, PRIVATE_DBPATH)
        slug = '_'.join(slug.split('_')[1:])
    else:
        project_path = PROJECT_PATH
    rec_path = os.path.join(project_path, slug, version, rec)
    return rec_path, project_path

def get_annotation(folder_path, dropdown_rec, os_path, ann_path, time_start,
                   time_stop):
    """
    Attempts to retrieve an annotation and returns any errors along the way.

    Parameters
    ----------
    folder_path : str
        The file path of the annotation.
    dropdown_rec : str
        The record selected by the user.
    os_path : str
        The file path of the directory where the proposed annotation lives.
    ann_path : str
        The file path of the annotation.
    time_start : int
        The start index to window the signal.
    time_stop : int
        The stop index to window the signal.

    Returns
    -------
    anns : wfdb.annotation object
        The annotation in WFDB format which can be read later to extract the
        timestamps, annotation symbol, and other attributes.
    anns_idx : list[int]
        All of the valid annotation indices for the desired time range.
    temp_error : list[str]
        Represents the elements inside of the final generated `div` container.
        For example, `html.Br()` can be added at the end the list to specify
        a line break after the error text.

    """
    # The list of annotation file extensions the system will check for
    # Maybe in the future look for any files which aren't .dat for .hea though
    # this could cause problems with CSV and other random files
    ann_classes = {'abp', 'al', 'alh', 'anI', 'all', 'alm', 'apn', 'ari',
                   'arou', 'atr', 'atr_avf', 'atr_avl', 'atr_avr', 'atr_i',
                   'atr_ii', 'atr_iii', 'atr_1', 'atr_2', 'atr_3', 'atr_4',
                   'atr_5', 'atr_6', 'aux', 'blh', 'blm', 'bph', 'bpm',
                   'comp', 'cvp', 'ecg', 'event', 'flash', 'hypn', 'in',
                   'log', 'man', 'marker', 'not', 'oart', 'pap', 'ple',
                   'pwave', 'pu', 'pu0', 'pu1', 'qrs', 'qrsc', 'qt1', 'qt2',
                   'q1c', 'q2c', 'resp', 'st', 'sta', 'stb', 'stc', 'trigger',
                   'trg', 'wabp', 'wqrs', 'win', '16a'}

    anns = []
    anns_idx = []
    temp_error = []
    try:
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
                    temp_error.extend(
                        return_error('ERROR_GRAPH: Annotation file ({}.{}) ' \
                                     'can not be read... {}', [ann_path,ext,e]))
    except IOError:
        # Can't find ANNOTATORS file, guess what annotation files are and
        # show warning in case annotation was expected (known extension
        # found in directory)
        possible_files = [d for d in os.listdir(os_path) if len(d.split('.')) > 1]
        if any(x.split('.')[-1] in ann_classes for x in set(possible_files)):
            # Annotation file found, try to use it
            temp_error.extend(
                return_error('WARNING_GRAPH: Annotation files found, but ' \
                             'ANNOTATORS file not found'))
            for i,f in enumerate(possible_files):
                ext = f.split('.')[-1]
                if ext in ann_classes:
                    try:
                        current_ann, ann_idx = get_ann_info(ann_path, ext,
                                                            time_start, time_stop)
                        anns.append(current_ann)
                        anns_idx.append(ann_idx)
                        temp_error.extend(
                            return_error('WARNING_GRAPH: Annotation file ' \
                                         'worked: {}', [f]))
                    except Exception as e:
                        temp_error.extend(
                            return_error('ERROR_GRAPH: Annotation file ({}) ' \
                                         'can not be read... {}', [f,e]))
    except Exception as e:
        temp_error.extend(return_error('ERROR_GRAPH: {}', [e]))
    return anns, anns_idx, temp_error

def plot_annotation(x_vals, y_vals, text, color='rgb(0, 0, 200)'):
    """
    Generate a dictionary that is used to generate and format the annotations
    to be placed on the figure if the specified record has some, and the user
    decides to display them.

    Parameters
    ----------
    x_vals : list[float,int]
        The x-values to place the annotation.
    y_vals : list[float,int]
        The y-values to place the annotation.
    text : str
        The annotation text.
    color : str, optional
        A string of the RGB representation of the desired annotation color.
        Ex: 'rgb(20,40,100)'

    Returns
    -------
    N/A : dict
        Formatted information about the annotation.

    """
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

def get_xaxis(title, tick_labels, start_time, range_stop, tick_stop,
              zoom_fixed=False, grid_delta_major=0.1,
              grid_color='rgb(200, 100, 100)', text_fontsize=16):
    """
    Generate a dictionary that is used to generate and format the x-axis for
    the figure.

    Parameters
    ----------
    title : str
        The title to be placed on the x-axis.
    tick_labels : bool
        If True, display both the ticks and their respective label.
    start_time : float, int
        The start x-value of the signal.
    range_stop : float, int
        The end x-value of the signal at initial display.
    tick_stop : int
        The end x-value of the signal in total.
    zoom_fixed : bool, optional
        If True, prevent the user from scaling the x-axis. This applies to
        both the horizontal drag animation on the x-axis and "Zoom" button
        when selecting the bounding box.
    grid_delta_major : float, int, optional
        The spacing of the gridlines.
    grid_color : str, optional
        A string of the RGB representation of the desired color.
        Ex: `rgb(20,40,100)`

    Returns
    -------
    N/A : dict
        Formatted information about the x-axis.

    """
    tick_vals = [round(n,1) for n in np.arange(start_time, tick_stop,
                                               grid_delta_major).tolist()]
    tick_text = [str(round(n)) if n%1 == 0 else '' for n in tick_vals]
    return {
        'title': title,
        'fixedrange': zoom_fixed,
        'dtick': grid_delta_major,
        'showticklabels': tick_labels,
        'tickvals': tick_vals,
        'ticktext': tick_text,
        'tickfont': {
            'size': text_fontsize
        },
        'tickangle': 0,
        'gridcolor': grid_color,
        'gridwidth': 1,
        'zeroline': False,
        'range': [start_time, range_stop],
        'showspikes': True,
        'spikemode': 'across',
        'spikesnap': 'cursor',
        'showline': True
    }

def get_yaxis(title, min_val, max_val, zoom_fixed=True,
              grid_color='rgb(200, 100, 100)', max_labels=8):
    """
    Generate a dictionary that is used to generate and format the y-axis for
    the figure.

    Parameters
    ----------
    title : str
        The title to be placed on the y-axis.
    min_val : float, int
        The minimum value of the signal.
    max_val : float, int
        The maximum value of the signal.
    zoom_fixed : bool, optional
        If True, prevent the user from scaling the y-axis. This applies to
        both the vertical drag animation on the y-axis and "Zoom" button when
        selecting the bounding box.
    grid_color : str, optional
        A string of the RGB representation of the desired color.
        Ex: `rgb(20,40,100)`
    max_labels : int, optional
        The maximum number of labels permitted on the y-axis at once.

    Returns
    -------
    N/A : dict
        Formatted information about the y-axis.

    """
    tick_vals = [round(n,1) for n in np.linspace(min_val, max_val,
                                                 max_labels).tolist()][1:-1]
    tick_text = [str(n) for n in tick_vals]
    return {
        'title': title,
        'fixedrange': zoom_fixed,
        'showgrid': True,
        'showticklabels': True,
        'tickvals': tick_vals,
        'ticktext': tick_text,
        'gridcolor': grid_color,
        'zeroline': False,
        'zerolinewidth': 1,
        'zerolinecolor': grid_color,
        'gridwidth': 1,
        'range': [min_val, max_val],
    }

def window_signal(y_vals):
    """
    This uses the Coefficient of Variation (CV) approach to determine
    significant changes in the signal then return the adjusted minimum
    and maximum range. If a significant variation is signal is found
    then filter out extrema using normal distribution. This method uses
    the Median Absolute Deviation in place of the typical Standard Deviation.

    Parameters
    ----------
    y_vals : numpy array
        The y-values of the signal.

    Returns
    -------
    min_y_vals : float, int
        The minimum y-value of the windowed signal.
    max_y_vals : float, int
        The maximum y-value of the windowed signal.

    """
    temp_std = stats.median_absolute_deviation(y_vals, nan_policy='omit')
    temp_mean = np.mean(y_vals[np.isfinite(y_vals)])
    temp_nan = np.all(np.isnan(y_vals))
    temp_zero = np.all(y_vals==0)
    if not temp_nan and not temp_zero:
        if (abs(temp_std / temp_mean) > 0.1) and (temp_std > 0.1):
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
    """
    Get the desired signal which is windowed from a specified start to stop
    time, downsampled to a desired degree, all NaN values replaced with 0, and
    converted to float-64 format.

    Parameters
    ----------
    record_sigs : list[str]
        All of the signal names from the desired record.
    sig_name : str
        The desired signal name to be extracted.
    rec_sig : numpy array
        All of the signals from the desired record. This will be in a format
        with separate signals as new columns.
    time_start : int
        The start index to window the signal.
    time_stop : int
        The stop index to window the signal.
    down_sample : int
        To what degree the signal should be downsampled. A value of 1
        indicates no downsampling. A value of n>1 indicates that every n-th
        value will be extracted from the signal.

    Returns
    -------
    y_vals : numpy array
        The y-values of the desired signal.

    """
    sig_name_index = record_sigs.index(sig_name)
    y_vals = rec_sig[:,sig_name_index][time_start:time_stop:down_sample]
    y_vals = np.nan_to_num(y_vals).astype('float64')
    return y_vals

def get_ann_info(ann_path, ext, time_start, time_stop):
    """
    Read the desired annotation from an input file path into WFDB format and
    then filter out the desired ones based on a start index and end index
    determined beforehand from multiplying the sample rate by the desired time.

    Parameters
    ----------
    ann_path : str
        The file path of the annotation file.
    ext : str
        The extension of the annotation file.
    time_start : int
        The start index to window the signal.
    time_stop : int
        The stop index to window the signal.

    Returns
    -------
    ann : wfdb.annotation object
        The annotation in WFDB format which can be read later to extract the
        timestamps, annotation symbol, and other attributes.
    ann_idx : list[int]
        All of the valid annotation indices for the desired time range.

    """
    ann = wfdb.rdann(ann_path, ext)
    ann_idx = list(filter(
        lambda x: (ann.sample[x] > time_start) and (ann.sample[x] < time_stop),
                  range(len(ann.sample))
    ))
    return ann, ann_idx

def get_y_title(sig_name, units, max_title_length):
    """
    Create and format long titles based on a given signal name, its units, and
    the desired maximum title length. Currently it splits based solely on the
    index of the letters which may cut off some words at awkward locations.

    Parameters
    ----------
    sig_name : str
        The name of the signal.
    units : str
        The units of the signal.
    max_title_length : int
        The maximum length of each line of the title. Long titles will be
        wrapped to the next line.

    Returns
    -------
    title : str
        The formatted and wrapped title.

    """
    title = '{} ({})'.format(sig_name, units)
    if len(title) > max_title_length:
        temp_title = ''.join(title.split('(')[:-1]).strip()
        temp_title = [temp_title[z:z+max_title_length] for z in range(0,
                                                                      len(temp_title),
                                                                      max_title_length)]
        temp_units = '(' + title.split('(')[-1]
        title = '<br>'.join(temp_title) + '<br>' + temp_units
    return title

@app.callback(
    [dash.dependencies.Output('dropdown_rec', 'options'),
     dash.dependencies.Output('dropdown_rec', 'value'),
     dash.dependencies.Output('error_text_rec', 'children')],
    [dash.dependencies.Input('previous_annotation', 'n_clicks_timestamp'),
     dash.dependencies.Input('next_annotation', 'n_clicks_timestamp'),
     dash.dependencies.Input('set_slug', 'value')],
    [dash.dependencies.State('set_record', 'value'),
     dash.dependencies.State('set_version', 'value')])
def get_record_options(click_previous, click_next, slug_value, record_value,
                        version_value):
    """
    Get all of the record options and update the current record.

    Parameters
    ----------
    click_previous : int
        The timestamp if the previous button was clicked in ms from epoch.
    click_next : int
        The if the next button was clicked in ms from epoch.
    slug_value : str
        The slug of the project.
    record_value : str
        The current record.
    version_value : str
        The version of the project.

    Returns
    -------
    options_rec : list[str]
        All of the possible records.
    return_record : str
        The next record.
    error_text : list[str]
        Represents the elements inside of the final generated `div` container.
        For example, `html.Br()` can be added at the end the list to specify
        a line break after the error text.

    """
    error_text = ['']
    options_rec = []
    return_record = None
    if not slug_value and not version_value:
        return options_rec, return_record, error_text

    records_path,_ = get_record_path(slug_value, version_value, '')
    records_file = os.path.join(records_path, 'RECORDS')

    try:
        with open(records_file, 'r') as f:
            all_records = f.read().splitlines()
    except FileNotFoundError:
        error_text.extend(
            return_error('ERROR_REC: Record file not provided... {}',
                         [records_file]))
        return options_rec, return_record, error_text
    except Exception as e:
        error_text.extend(
            return_error('ERROR_REC: Record file incorrectly formatted... {}',
                         [e]))
        return options_rec, return_record, error_text
    # TODO: Probably should refactor this
    temp_all_records = []
    for i,rec in enumerate(all_records):
        temp_path = os.path.join(records_path, rec)
        try:
            if 'RECORDS' in set(os.listdir(temp_path)):
                temp_file = os.path.join(temp_path, 'RECORDS')
                with open(temp_file, 'r') as f:
                    # Directory RECORDS values should always have a `/` at
                    # the end
                    temp_records = [rec + line.rstrip('\n') for line in f]
            temp_all_records.extend(temp_records)
        except FileNotFoundError:
            # No nested RECORDS files
            pass
        except NotADirectoryError:
            # No nested RECORDS files
            pass
        except Exception as e:
            error_text.extend(
                return_error('ERROR_REC: Unable to read RECORDS file.. {}',
                             [e]))
            return options_rec, return_record, error_text
    if temp_all_records != []:
        all_records = temp_all_records

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
        click_time = datetime.datetime.fromtimestamp(click_time / 1000.0)
        # Consider next annotation desired if button was pressed in the
        # last second
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

    options_rec = [{'label': rec, 'value': rec} for rec in all_records]
    return options_rec, return_record, error_text

@app.callback(
    [dash.dependencies.Output('sig_name', 'options'),
     dash.dependencies.Output('sig_name', 'value'),
     dash.dependencies.Output('error_text_sig', 'children')],
    [dash.dependencies.Input('dropdown_rec', 'value')],
    [dash.dependencies.State('set_slug', 'value'),
     dash.dependencies.State('set_version', 'value')])
def update_sig(dropdown_rec, slug_value, version_value):
    """
    Get all of the signal options and update the selected signals.

    Parameters
    ----------
    dropdown_rec : str
        The current record.
    slug_value : str
        The slug of the project.
    version_value : str
        The version of the project.

    Returns
    -------
    options_sig : list[str]
        All of the possible signals.
    return_sigs : str
        The selected signals.
    return_error : list[str]
        Represents the elements inside of the final generated `div` container.
        For example, `html.Br()` can be added at the end the list to specify
        a line break after the error text.

    """
    error_text = ['']
    options_sig = []
    return_sigs = []
    if dropdown_rec and slug_value:
        header_path,_ = get_record_path(slug_value, version_value, dropdown_rec)
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
        #       be updated? Might have to leave it like this. The best way may
        #       be to just add a submit button instead of dynamically updating.
        # Set the options and values (only the first `max_display_sigs` signals)
        try:
            if header_path.endswith('.edf'):
                sig_name = wfdb.edf2mit(header_path).sig_name
            else:
                sig_name = wfdb.rdsamp(header_path)[1]['sig_name']
            options_sig = [{'label': sig, 'value': sig} for sig in sig_name]
            return_sigs = sig_name[:max_display_sigs]
        except FileNotFoundError:
            error_text.extend(return_error('ERROR_SIG: Record file not provided... {}', [header_path]))
        except Exception as e:
            error_text.extend(return_error('ERROR_SIG: Record/Header file incorrectly formatted... {}', [e]))
    except Exception as e:
        error_text.extend(return_error('ERROR_SIG: Header file (.hea) incorrectly formatted... {}', [e]))

    return_error = html.Span(error_text)
    return options_sig, return_sigs, return_error

@app.callback(
    dash.dependencies.Output('set_record', 'value'),
    [dash.dependencies.Input('the_graph', 'figure')],
    [dash.dependencies.State('dropdown_rec', 'value')])
def update_rec(fig, dropdown_rec):
    """
    Update the set record so it can be used when choosing the previous or next
    record.

    Parameters
    ----------
    fig : plotly.subplots
        This variable isn't used, it is just what causes this function to
        trigger every time it changes.
    dropdown_rec : str
        The current record.

    Returns
    -------
    return_dropdown : str
        The updated record.

    """
    if dropdown_rec:
        return_dropdown = dropdown_rec
    else:
        return_dropdown = ''
    return return_dropdown

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
    """
    Take all of the selected information and generate the figure.

    Parameters
    ----------
    sig_name : list[str]
        The desired signals to plot.
    start_time : str
        The desired start time for the signal on the figure.
    annotation_status : str
        If 'On', add annotations to the figure. The other option is 'Off'.
    dropdown_rec : str
        The current record.
    start_time_pattern : str
        The regex pattern expected for the `start_time`.
    slug_value : str
        The slug of the project.
    version_value : str
        The version of the project.

    Returns
    -------
    N/A : plotly.subplots
        The final figure.
    N/A : dash.dash_html_components
        The formatted errors.

    """
    # Preset the error text
    error_text = ['']
    # Check if valid number of input signals or input start time
    if (dropdown_rec and ((len(sig_name) == 0) or (len(sig_name) > max_display_sigs) or
            (re.compile(start_time_pattern).match(start_time) == None))):
        # If not, plot the default graph
        dropdown_rec = None
        if (len(sig_name) == 0):
            error_text.extend(
                return_error('ERROR_GRAPH: No input signals provided'))
        elif (len(sig_name) > max_display_sigs):
            error_text.extend(
                return_error('ERROR_GRAPH: Exceeded maximum input signals ({} maximum)',
                             [max_display_sigs]))
        elif (re.compile(start_time_pattern).match(start_time) == None):
            error_text.extend(
                return_error('ERROR_GRAPH: Invalid start time provided'))

    # Set a blank plot if none is loaded
    if not dropdown_rec:
        base_fig = get_base_fig()
        return base_fig, html.Span(error_text)

    # Read the requested record and extract relevent properties
    record_path, project_path = get_record_path(slug_value, version_value,
                                                dropdown_rec)
    if record_path.endswith('.edf'):
        try:
            record = wfdb.edf2mit(record_path)
        except FileNotFoundError:
            base_fig = get_base_fig()
            error_text.extend(
                return_error('ERROR_SIG: EDF file not provided... {}',
                             [record_path]))
            return base_fig, html.Span(error_text)
        except Exception as e:
            base_fig = get_base_fig()
            error_text.extend(
                return_error('ERROR_SIG: EDF file incorrectly formatted... {}',
                             [e]))
            return base_fig, html.Span(error_text)
    else:
        try:
            record = wfdb.rdsamp(record_path)
        except FileNotFoundError:
            base_fig = get_base_fig()
            error_text.extend(
                return_error('ERROR_SIG: Record file not provided... {}',
                             [record_path]))
            return base_fig, html.Span(error_text)
        except Exception as e:
            base_fig = get_base_fig()
            error_text.extend(
                return_error('ERROR_SIG: Record/Header file incorrectly ' \
                             'formatted... {}', [e]))
            return base_fig, html.Span(error_text)

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

    if len(record_sigs) != len(set(record_sigs)):
        error_text.extend(
            return_error('ERROR_GRAPH: Multiple signals are named the same; ' \
                         'not all will be plotted'))

    # Select only the desired signal units
    n_sig = len(sig_name)
    units = [None] * n_sig
    for i,s in enumerate(record_sigs):
        if s in set(sig_name):
            units[sig_name.index(s)] = rec_units[i]

    # Determine the start time of the record to plot (seconds)
    # Should always start at the beginning (default input is 00:00:00)
    start_time = sum(int(x)*60**i for i,x in enumerate(reversed(start_time.split(':'))))
    time_start = int(fs * start_time)
    if time_start >= rec_len:
        max_time = str(datetime.timedelta(seconds = rec_len/fs))
        error_text.extend(
            return_error('ERROR_GRAPH: Start time exceeds signal length ({:0>8})',
                         [max_time]))

    # How much signal should be displayed after start time (seconds)
    time_range = 60
    # Determine how much signal to display initially after start time (seconds)
    window_size = 10

    if start_time+time_range > rec_len/fs:
        time_stop = rec_len
        if (rec_len/fs - start_time) < window_size:
            range_stop = rec_len/fs
        else:
            range_stop = start_time  + window_size
    else:
        time_stop = int(fs * (start_time + time_range))
        range_stop = start_time + window_size
    sig_len = time_stop - time_start

    # Adjust the font size based on the number of signals (should never
    # get too small due to the maximum allowed to be displayed)
    text_fontsize = 16
    font_size = text_fontsize - n_sig

    # Set the initial layout of the figure
    fig = get_subplot(n_sig)
    fig.update_layout(
        get_layout(n_sig, font_size=font_size)
    )

    # Attempt to load in annotations if available
    folder_path = os.path.join(project_path, slug_value, version_value)
    ann_path = os.path.join(folder_path, dropdown_rec)
    os_path = os.sep.join(ann_path.split(os.sep)[:-1])
    if annotation_status == 'On':
        anns, anns_idx, temp_error = get_annotation(folder_path, dropdown_rec,
                                                    os_path, ann_path,
                                                    time_start, time_stop)
        error_text.extend(temp_error)

    # Down-sample signal to increase performance
    max_fs = 100
    down_sample = 1 if int(fs/max_fs) == 0 else int(fs/max_fs)
    x_vals = [start_time + (i / fs) for i in range(sig_len)][::down_sample]

    for s in range(n_sig):
        try:
            y_vals = extract_signal(record_sigs, sig_name[s], rec_sig,
                                    time_start, time_stop, down_sample)
        except Exception as e:
            error_text.extend(
                return_error('ERROR_GRAPH: Record file (.dat) can not be ' \
                             'read... {}', [e]))

        x_string = 'x' + str(s+1)
        y_string = 'y' + str(s+1)
        fig.add_trace(
            get_trace(x_vals, y_vals, x_string, y_string, sig_name[s]),
            row = s+1, col = 1)

        # Remove outliers to prevent weird axes scaling if possible
        min_y_vals, max_y_vals = window_signal(y_vals)

        if anns != [] and s == 0:
            for i,ann in enumerate(anns):
                for a in anns_idx[i]:
                    # TODO: Use ann.symbol for now, but use ann.aux_note if
                    # it's possible (some are long and take up the whole
                    # screen and get really crowded, also some are empty, so
                    # maybe don't use it? Find some kind of balance?)
                    fig.add_annotation(
                        plot_annotation(float(ann.sample[a]/fs), max_y_vals,
                                        ann.symbol[a])
                    )

        if s != (n_sig - 1):
            fig.update_xaxes(
                get_xaxis(None, False, start_time, range_stop,
                          start_time+time_range),
                row = s+1, col = 1)
        else:
            fig.update_xaxes(
                get_xaxis('Time (s)', True, start_time, range_stop,
                          start_time+time_range),
                row = s+1, col = 1)

        # Add line breaks for long titles
        max_title_length = 20 - n_sig
        y_title = get_y_title(sig_name[s], units[s], max_title_length)
        fig.update_yaxes(
            get_yaxis(y_title, min_y_vals, max_y_vals),
            row = s+1, col = 1)

        fig.update_traces(xaxis = x_string)

    return (fig), html.Span(error_text)
