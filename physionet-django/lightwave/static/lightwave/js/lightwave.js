// file: lightwave.js	G. Moody	18 November 2012
//			Last revised:	  15 June 2022     version 0.71
// LightWAVE Javascript code
//
// Copyright (C) 2012-2013 George B. Moody
//
// This program is free software; you can redistribute it and/or
// modify it under the terms of the GNU General Public License as
// published by the Free Software Foundation; either version 2 of the
// License, or (at your option) any later version.
//
// This program is distributed in the hope that it will be useful, but
// WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
// General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program; if not, write to the Free Software
// Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA
// 02111-1307, USA.
//
// You may contact the author by e-mail (george@mit.edu) or postal
// mail (MIT Room E25-505A, Cambridge, MA 02139 USA).  For updates to
// this software, please visit PhysioNet (http://physionet.org/).
// ____________________________________________________________________________
//
// LightWAVE is a lightweight waveform and annotation viewer and editor.
//
// LightWAVE is modelled on WAVE, an X11/XView application I wrote and
// maintained between 1989 and 2012.  LightWAVE runs within any modern
// web browser and does not require installation on the user's computer.
//
// This file contains Javascript code that runs within the user's browser
// to respond to his or her input and retrieve data via AJAX, using jQuery
// 1.7 or later.  On the server end, the AJAX requests are handled by
// '/cgi-bin/lightwave', the LightWAVE CGI application.
// ____________________________________________________________________________

/*global $ */
/*jslint plusplus: true, white: true, passfail: false, browser: true,
   maxerr: 1000, devel: true */

(function(){
"use strict";

// 'server' and 'scribe' are the URLs of the LightWAVE server and its edit
// backup server.  Change them if you are not using the public server.
var server,
    scribe,

    server_flags, // extra query parameters sent to server
    url,	// request sent to server (server + request-specific string)
    db = '',	// name of the selected database
    sdb = '',	// shortened name of the selected database
    record = '',// name of the selected record
    recinfo,    // metadata for the selected record, initialized by slist()
    tickfreq,   // ticks per second (LCM of sampling frequencies of signals)
    adt_ticks,  // length of longest annotation set, in ticks
    sdt_ticks,  // length of signals, in ticks
    rdt_ticks,	// record length, in ticks (max of adt_ticks and sdt_ticks)
    ann_set = [], // annotators for the selected database, from alist()
    ann = [],   // annotations read and cached by read_annotations()
    nann = 0,	// number of annotators, set by read_annotations()
    annselected = '',// name of annotation set to be highlighted, if any
    selarr = null, // array of annotations selected for search/edit
    selann = -1,// index of selected annotation in selarr, if any
    asy0,	// baseline y for display of labels in selarr
    signals,    // signals for the selected record, from slist()
    nsig = 0,	// number of signals, set by read_signals()
    sigselected = '',// name of signal to be highlighted, if any
    current_tab,// name of the currently selected tab
    dt_sec = 10,// window width in seconds
    dt_ticks,   // window width in ticks
    t0_ticks = -1, // time of the first sample in the signal window, in ticks
    tf_ticks,	// time of the first sample after the signal window, in ticks
    tscl = 1000,// time scale, in SVG units per second
    tickint,    // interval (in ticks) between timestamps on plot
    griddt,	// interval (in ticks) between vertical grid-lines on plot
    griddx,	// interval (in SVG x-units) between vertical grid-lines on plot
    tpool = [], // cache of 'trace' objects (10-second signal segments)
    tid = 0,	// next trace id (all traces have id < tid)
    target = '*',// search target, set in Find... dialog
    g_visible = 1, // visibility flag for grid (1: on, 0: off)
    m_visible = 1, // visibility flag for annotation marker bars (1: on, 0: off)
    s_visible = [], // visibility flags for signals
    x_cursor = -1, // signal window cursor x-coordinate (see svgxyt())
    xx_cursor = -1,// raw cursor x-coordinate (= x_cursor if in signal window)
    y_cursor,	// unconstrained cursor y-coordinate (see svgxyt())
    t_cursor,	// time in ticks corresponding to x_cursor (see svgxyt())
    c_velocity = 10, // SVG cursor velocity (see nudge_left() and nudge_right())
    mag = [],   // magnification of signals in plots
    help_main = 'about.html', // initial and main help topic
    svc = '',   // SVG code to draw the cursor (see show_time())
    svg = '',   // SVG code to draw the signal window (see show_plot())
    svsa = '',   // SVG code to highlight the selected annotation (see jump_*)
    m = null,  // current transformation matrix for signal window
    requests = 0, // count of AJAX requests since last page load
    pending = 0,  // count of pending AJAX requests
    rqlog = '',	// AJAX request log (hidden by default)
    autoscroll = null, // autoplay_fwd/rev timer
    emode = 1, // edit mode (1: no edit, 2: edit with mouse, 3: edit with touch)
    editing = false,   // editing controls hidden if false
    mouse = false,     // true if user selected 'Edit using mouse'
    palette = null,    // annotation palette (see load_palette())
    seltype, // id of the current selection in the palette ('#palette_N')
    selkey,  // button text for the current palette selection
    insert_mode = true, // editing mode (true: insert, false: delete)
    changes = [],	// edit log
    undo_count = 0,	// number of undos that are possible from current state
    ilast = -1,		// index in selarr of annot most recently found

// SVG click targets
    $grid,	// grid click target
    $mrkr,	// marker bar click target
    $anames,	// annotator name click targets
    $snames,	// signal name click targets
    $svg,       // signal window

// View/edit panel geometry
    width,	// width of View/edit panel, in pixels
    height,	// height of View/edit panel, in pixels
    swl,        // width of left column, in pixels
    sww,	// signal window width, in pixels
    swr,	// width of right column, in pixels
    svgw,	// grid width, in SVG coords
    svgh,	// grid height, in SVG coords
    svgl,	// left column width, in SVG coords
    svgr,       // right column width, in SVG coords
    svgtw,	// total available width in SVG coords
    svgf,	// font-size for signal/annotation labels
    svgtf,	// small font-size for timestamps
    svgc,	// size for small elements (circles, etc.)
    lwl,	// light stroke-width
    lwn,	// normal stroke-width
    lwb,	// emphasized stroke-width
    adx1,	// arrow half-width
    adx2,	// arrow width / edit marker half-width
    adx4,	// edit marker width
    ady1;	// arrow height

// Minimal jQuery plugin for touch event support, based on Stephen von Takach's
// jquery.ui.touch.js; emulates mousedown, mousemove, mouseup only
(function($) {
    function sim_event(event, type) {
	var sim = document.createEvent("MouseEvent"),
            touch = event.changedTouches[0];

	sim.initMouseEvent(type, true, true, window, 1,
			   touch.screenX, touch.screenY,
			   touch.clientX, touch.clientY,
			   false, false, false, false, 0, null);
	touch.target.dispatchEvent(sim);
    }

    function touchstart_handler(event) {
	if (event.touches.length <= 1) {
	    sim_event(event, "mousedown");
	}
    }

    function touchmove_handler(event) {
	if (event.touches.length <= 1) {
	    event.preventDefault();
	    sim_event(event, "mousemove");
	}
    }

    function touchend_handler(event) {
	if (event.touches.length <= 1) {
	    sim_event(event, "mouseup");
	}
    }

    $.extend($.support, { touch: "ontouchend" in document });

    $.fn.addTouch = function() {
	if ($.support.touch) {
            this.each(function(i,el){
		el.addEventListener("touchstart", touchstart_handler, false);
		el.addEventListener("touchmove", touchmove_handler, false);
		el.addEventListener("touchend", touchend_handler, false);
            });
	}
    };
})(jQuery);

// Initialize or expand tpool
function init_tpool(ntrace) {
    var i;

    for (i = tpool.length; i < ntrace; i++) {
	tpool[i] = {};
	tpool[i].id = tid++;
    }
}

// Find a trace in the cache
function find_trace(db, record, signame, t) {
    var i;

    for (i = 0; i < tpool.length; i++) {
	if (tpool[i].name === signame &&
	    tpool[i].t0 <= t && t < tpool[i].tf &&
	    tpool[i].record === record && tpool[i].db === db) {
	    return tpool[i];
	}
    }
    return null;
}

// Find the earliest-starting trace that overlaps the given range
function find_trace_in_range(db, record, signame, t0, tf) {
    var i, trace = null;

    for (i = 0; i < tpool.length; i++) {
	if (tpool[i].name === signame &&
	    tpool[i].t0 < tf && t0 < tpool[i].tf &&
	    tpool[i].record === record && tpool[i].db === db) {
	    trace = tpool[i];
	    tf = trace.t0;
	}
    }
    return trace;
}

// Replace the least-recently-used trace with the contents of s
function set_trace(db, record, s) {
    var i, idmin, imin, j, len, ni, p, trace, v, vmean, vmid, vmax, vmin, w;

    idmin = tid;
    len = s.samp.length;

    // do nothing if the trace is already in the pool
    trace = find_trace(db, record, s.name, s.t0);
    if (trace && trace.tf >= s.t0 + len*s.tps) { return; }

    // set additional properties of s that were not supplied by the server
    s.id = tid++;
    s.db = db;
    s.record = record;
    s.tf = s.t0 + len*s.tps;

    // restore amplitudes from first differences sent by server
    v = s.samp;
    vmean = vmax = vmin = v[0];
    for (j = ni = p = 0; j < len; j++) {
	p = v[j] += p;
	// ignore invalid samples in baseline calculation
	if (p === -32768) { ni++; }
	else {
	    if (p > vmax) { vmax = p; }
	    else if (p < vmin) { vmin = p; }
	    vmean += +p;
	}
    }

    // calculate the local baseline (a weighted sum of mid-range and mean)
    vmean /= len - ni;
    vmid = (vmax + vmin)/2;
    if (vmid > vmean) { w = (vmid - vmean)/(vmax - vmean); }
    else if (vmid < vmean) { w = (vmean - vmid)/(vmean - vmin); }
    else { w = 1; }
    s.zbase = vmid + w*(vmean - vmin);

    // find the least-recently-used trace
    for (i = 0; i < tpool.length; i++) {
	if (tpool[i].id < idmin) {
	    imin = i;
	    idmin = tpool[i].id;
	}
    }
    tpool[imin] = s; // replace it
}

// Convert argument (in samples) to a string in HH:MM:SS format
function timstr(t) {
    var ss, mm, hh, tstring;

    ss = Math.round(t/tickfreq);
    mm  = Math.floor(ss/60);    ss %= 60;
    hh  = Math.floor(mm/60);    mm %= 60;
    if (ss < 10) { ss = '0' + ss; }
    if (mm < 10) { mm = '0' + mm; }
    if (hh < 10) { hh = '0' + hh; }
    tstring = hh + ':' +  mm + ':' + ss;
    return tstring;
}

// Convert argument (in samples) to a string in HH:MM:SS.mmm format
function mstimstr(t) {
    var mmm, ss, mm, hh, tstring;

    mmm = Math.round(1000*t/tickfreq);
    ss  = Math.floor(mmm/1000); mmm %= 1000;
    mm  = Math.floor(ss/60);    ss %= 60;
    hh  = Math.floor(mm/60);    mm %= 60;
    if (mmm < 100) {
	if (mmm < 10) { mmm = '.00' + mmm; }
	else { mmm = '.0' + mmm; }
    }
    else { mmm = '.' + mmm; }
    if (ss < 10) { ss = '0' + ss; }
    if (mm < 10) { mm = '0' + mm; }
    if (hh < 10) { hh = '0' + hh; }
    tstring = hh + ':' +  mm + ':' + ss + mmm;
    return tstring;
}

// Convert string argument to time in samples
function strtim(s) {
    var c, t;

    c = s.split(":");
    switch (c.length) {
      case 1:
	if (c[0] === "") { t = 0; }
	else { t = +c[0]; }
	break;
      case 2:
	t = 60*c[0] + Number(c[1]);
	break;
      case 3:
	t = 3600*c[0] + 60*c[1] + Number(c[2]);
	break;
      default: t = 0;
    }
    return Math.round(t*tickfreq);
}

// Replace HTML special characters in s with HTML escape sequences
function html_escape(s) {
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

// Request JSONP data (equivalent to '$.getJSON' minus the
// anti-caching and anti-cross-domain options)
function get_jsonp(url, callback) {
    $.ajax({ dataType: "json",
             url: url,
             success: callback,
             cache: true,
             crossDomain: true });
}

// Update the summary on the Tables tab
function show_summary() {
    var i, ia, ii, is, itext = '', rdurstr, s;

    if (!recinfo) { return; }
    if (recinfo.duration) { sdt_ticks = strtim(recinfo.duration); }
    else { sdt_ticks = 0; }
    rdt_ticks = (adt_ticks > sdt_ticks) ? adt_ticks : sdt_ticks;
    rdurstr = timstr(rdt_ticks);
    itext += '<h3>Summary</h3>\n<table>\n'
        + ' <tr><td>Record length</td><td>' + rdurstr + '</td></tr>\n';
    if (recinfo.start) {
	itext += ' <tr><td>Start</td><td>' + recinfo.start + '</td></tr>\n';
    }
    itext += ' <tr><td>Clock frequency&nbsp;</td><td>' + tickfreq
	+ ' ticks per second</td></tr>\n';

    if (nann > 0) {
	for (ia = 0; ia < nann; ia++) {
	    itext += '<tr><td style="vertical-align: top">Annotator: '
		+ ann[ia].name + '</td><td>' + '(' + ann[ia].annotation.length
		+ ' annotations)<br>\n<table style="padding: 0 0 1em 3em">';
	    s = ann[ia].summary;
	    for (i = 0; i < s.length; i++) {
		if (s[i][1] > 0) {
		    itext += '<tr><td>' + s[i][0] + '</td><td align=right>'
			+ s[i][1] + '</td</tr>\n';
		}
	    }
	    itext += '</table>\n</td></tr>\n';
	}
    }
    if (signals) {
	for (is = 0; is < nsig; is++) {
	    itext += '<tr><td>Signal: ' + signals[is].name + '</td><td>';
	    if (signals[is].tps === 1) {
		itext += signals[is].tps + ' tick per sample; ';
	    }
	    else {
		itext += signals[is].tps + ' ticks per sample; ';
	    }
	    itext += signals[is].gain + ' adu/';
	    if (signals[is].units) {
		itext += signals[is].units + '; ';
	    }
	    else {
		itext += 'mV; ';
	    }
	    itext +=  signals[is].adcres + '-bit ADC, zero at '
		+ signals[is].adczero + ';  baseline is '
		+ signals[is].baseline + '</td></tr>\n';
	}
    }
    if (recinfo.note) {
	itext += '<tr><td style="vertical-align: top;">Notes:</td><td><pre>';
	for (ii = 0; ii < recinfo.note.length; ii++) {
	    itext += html_escape(recinfo.note[ii]) + '\n';
	}
	itext += '</pre></td></tr>\n';
    }
    itext += '</table>';
    $('#info').html(itext);
}

// Return the index in annotation array a[] of the first annotation following t.
//  If a[] is empty, or if all of a[] follows t, return 0.
//  If all of a[] precedes t, return the next index (a.length).
function ann_after(a, t) {
    var i, imin = 0, imax = 0;

    if (a) {
	imax = a.length - 1;
	if (imax >= 0) {
	    if (a[0].t > t) { imax = 0; }
	    else if (a[imax].t > t) {
		while (imax - imin > 1) {
		    i = Math.floor((imin + imax)/2);
		    if (a[i].t < t) { imin = i; }
		    else if (a[i].t > t) { imax = i; }
		    else { imax = imin = i + 1; }
		}
	    }
	    else { imax++; }
	}
    }
    return imax;
}

// Return index in annotation array a[] of the last annotation at or before t.
//  If all of a[] precedes t, return a.length - 1.
//  If a[] is empty, or if all of a[] follows t, return -1.
function ann_before(a, t) {
    var i;

    i = ann_after(a, t) - 1;
    return i;
}

// Update annotations-as-text and signals-as-text if selected on Tables tab
function show_tables() {
    var a, atext = '', i, ia, is, j, sig = [], sname, stext = '', t, u, v, vi;

    if ($('#viewann').prop('checked')) {
        if (ann.length > 0) { atext += '<h3>Annotations</h3>\n'; }
	for (ia = 0; ia < nann; ia++) {
	    if (ann[ia].state === 0) {
		atext += '<p>Annotator: ' + ann[ia].name + ' [hidden]</br>\n';
	    }
	    else {
		atext += '<p><b>Annotator:</b> ' + ann[ia].name
		    + '\n<p><table class="dtable">\n<tr>'
		    + '<th>Time (elapsed)&nbsp;</th>'
		    + '<th>Sample #</th><th>Type</th>'
		    + '<th>Sub&nbsp;</th><th>Chan</th>'
		    + '<th>Num&nbsp;</th><th>Aux</th></tr>\n';
		a = ann[ia].annotation;
		for (i = ann_after(a, t0_ticks);
		     0 <= i && i < a.length && a[i].t <= tf_ticks; i++) {
		    atext += '<tr><td>' + mstimstr(a[i].t) + '</td><td>'
		        + a[i].t + '</td><td>'
			+ a[i].a + '</td><td>' + a[i].s + '</td><td>'
			+ a[i].c + '</td><td>' + a[i].n + '</td><td>';
		    if (a[i].x) { atext += a[i].x; }
		    atext +=  '</td></tr>\n';
		}
		atext += '</table>\n</div></div>\n';
		atext += '</table>\n<p>\n';
	    }
	}
	atext += '<hr>\n';
	$('#anndata').html(atext);
    }
    else { $('#anndata').empty(); }

    if ($('#viewsig').prop('checked')) {
	if (signals) {
	    sig = [];
	    for (i = is = 0; i < signals.length; i++) {
		sname = signals[i].name;
		if (s_visible[sname]) {
		    sig[is++] = find_trace(db, record, sname, t0_ticks);
		}
	    }

	    stext = '<h3>Signals</h3>\n<p><table class="dtable">\n'
		+ '<tr><th>Time (elapsed)&nbsp;</th>';
	    for (i = 0; i < is; i++) {
		stext += '<th>' + sig[i].name + '&nbsp;</th>';
	    }
	    stext += '\n<tr><th></th>';
	    for (i = 0; i < is; i++) {
		u = sig[i].units;
		if (!u) { u = '[mV]'; }
		stext += '<th><i>(' + u + ')</i></th>';
	    }

	    for (t = t0_ticks; t < tf_ticks; t++) {
		stext += '</tr>\n<tr><td>' + mstimstr(t);
		for (j = 0; j < is; j++) {
		    stext += '</td><td>';
		    if (t%sig[j].tps === 0) {
			if (t >= sig[j].tf) {
			    sig[j] = find_trace(db, record, sig[j].name,
						sig[j].tf);
			}
			vi = sig[j].samp[(t - sig[j].t0)/sig[j].tps];
			if (vi === -32768) { stext += '-'; }
			else {
			    v = (vi - sig[j].base)/ sig[j].gain;
			    stext += v.toFixed(3);
			}
		    }
		}
		stext += '</td>';
	    }
	    stext += '</tr>\n</table>\n';
	}
	$('#sigdata').html(stext);
    }
    else { $('#sigdata').empty(); }
}

// Convert (x, y) in pixels to SVG coords and time in ticks
function svgxyt(x, y) {
    var ytemp;

    m = document.getElementById("viewport").getScreenCTM();
    ytemp = (y - m.f)/m.d;
    if (-svgf <= ytemp && ytemp <= svgh + svgf) {
	x_cursor = xx_cursor = (x - m.e)/m.a;
	if (x_cursor < 0) { x_cursor = 0; }
	else if (x_cursor > svgw) { x_cursor = svgw; }
	y_cursor = ytemp;
    }
    t_cursor = t0_ticks + x_cursor*tickfreq/tscl;
}

// Functions for communicating with the LightWAVE server

// Load the list of signals for the selected record
function slist(t0_string) {
    var i, t, title;

    title = 'LW: ' + sdb + '/' + record;
    $('.recann').html(sdb + '/' + record);
    document.title = title;
    $('#info').empty();
    $('#anndata').empty();
    $('#sigdata').empty();
    $('#plotdata').empty();
    m = null;
    nsig = 0;
    url = server + '?action=info&db=' + db + '&record=' + record
	+ server_flags;
    show_status(true);
    get_jsonp(url, function(data) {
	if (data.success) {
	    recinfo = data.info;
	    tickfreq = recinfo.tfreq;
	    if (tickfreq > 5) {
		$('#dtsliderunits').html('seconds');
		tscl = 1000;
		if (dt_sec > 60) { dt_sec = 10; }
		$('#swidth').val(dt_sec);
	    }
	    else {
		$('#dtsliderunits').html('minutes');
		if (tickfreq > 0.1) {
		    tscl = 100;
		    if (dt_sec < 60) { dt_sec = 60; }
		}
		else {
		    tscl = 10;
		    if (dt_sec < 300) { dt_sec = 300; }
		}
		$('#swidth').val(dt_sec/60);
	    }
	    dt_ticks = dt_sec * tickfreq;
	    set_sw_width(dt_sec);
	    if (recinfo.signal) {
		signals = recinfo.signal;
		nsig = signals.length;
		for (i = 0; i < nsig; i++) {
		    s_visible[signals[i].name] = mag[signals[i].name] = 1;
		}
		init_tpool(nsig * 8);
	    }
	    else {
		signals = null;
		nsig = 0;
	    }
	}
	else {
	    alert('Record ' + db + '/' + record + ' is not readable.\n');
	    return;
	}
	$('#tabs').tabs("enable");
	show_summary();
	$('#tabs').tabs("option", "active", $('#view').index());
	if (t0_string !== '') { t = strtim(t0_string); }
	else { t = 0; }
	t0_string = timstr(t);
	$('.t0_str').val(t0_string);
	go_here(t);
	$('#top').show();
	show_status(false);
    });
}

// Load the list of annotators in the selected database.
function alist() {
    url = server + '?action=alist&db=' + db + server_flags;
    show_status(true);
    get_jsonp(url, function(data) {
	if (data.success) { ann_set = data.annotator; }
	else { ann_set = []; }
	show_status(false);
    });
}

// Load the list of records in the selected database, and set up an event
// handler for record selection.
function rlist() {
    var i, rlist_text = '';
    url = server + '?action=rlist&db=' + db + server_flags;
    $('#rlname').empty();
    $('#rlist').html('Reading list of records in ' + sdb);
    $('#rslist').empty();
    show_status(true);
    get_jsonp(url, function(data) {
	if (data) {
	    rlist_text = '<select name=\"record\">\n'
		+ '<option value=\"\" selected>--Choose one--</option>\n';
	    for (i = 0; i < data.record.length; i++) {
	        rlist_text += '<option value=\"' + data.record[i]
		    + '\">' + data.record[i] + '</option>\n';
	    }
	    rlist_text += '</select>';
	}
	$('#rlname').html("Record:");
	$('#rlist').html(rlist_text);
	// fetch the list of signals when the user selects a record
	$('[name=record]').on("change", newrec);
	show_status(false);
    });
}

// Load the list of subrecords for the selected record, and set up an event
// handler for subrecord selection.
function rslist() {
    var i, rec, rslist_text = '';

    rec = record.slice(0, -1); // drop trailing '/'
    url = server + '?action=rlist&db=' + db + '/' + rec + server_flags;
    $('#rslist').html('Reading list of subrecords for ' + sdb + '/' + record);
    show_status(true);
    get_jsonp(url, function(data) {
	if (data) {
	    rslist_text = '<select name=\"subrec\">\n'
		+ '<option value=\"\" selected>--Choose one--</option>\n';
	    for (i = 0; i < data.record.length; i++) {
	        rslist_text += '<option value=\"' + data.record[i]
		    + '\">' + data.record[i] + '</option>\n';
	    }
	    rslist_text += '</select>';
	}
	$('#rslist').html(rslist_text);
	// fetch the list of signals when the user selects a subrecord
	$('[name=subrec]').on("change", newsubrec);
	show_status(false);
    });
}

// Load the list of databases and set up an event handler for db selection.
function dblist() {
    var dbi, dblist_text = '', dbparts, i, sdbi, timer;

    server = $('[name=server]').val();
    i = server.indexOf('?');
    if (i > 0) {
	server_flags = '&' + server.substring(i + 1);
	server = server.substring(0, i);
    }
    else {
	server_flags = '';
    }

    scribe = $('[name=scribe]').val();
    $('#dblist').html('<td colspan=2>Loading list of databases ...</td>');
    url = server + '?action=dblist' + server_flags;
    timer = setTimeout(alert_server_error, 10000);
    show_status(true);
    get_jsonp(url, function(data) {
	clearTimeout(timer);
	if (data && data.database && data.database.length > 0) {
	    dblist_text = '<td align=right>Database:</td>' +
		'<td colspan=2><select name=\"db\" id=\"db\">\n' +
		'<option value=\"\" selected>--Choose one--</option>\n';
	    for (i = 0; i < data.database.length; i++) {
    		dbi = data.database[i].name;
    		dbparts = dbi.split('/');
	        dblist_text += '<option value=\"' + dbi +
		        '\">' + data.database[i].desc + ' (' + dbi + ')</option>\n';
	    }
	    dblist_text += '</select></td>\n';
	    $('#dblist').html(dblist_text);
	    $('#sversion').html("version " + data.version);
	    $('#db').on("change", newdb); // invoke newdb when db changes
	}
	else { alert_server_error(); }
	show_status(false);
    });
}

// Retrieve one or more complete annotation files for the selected record
//  If pending edits exist in local storage, merge them
function read_annotations(t0_string) {
    var annreq = '', i, j, key, len, t, s, ss;

    nann = 0;	// new record -- (re)fill the cache
    selann = -1;  // discard selection, if any
    svsa = '';
    if (ann_set.length) {
	for (i = 0; i < ann_set.length; i++) {
	    annreq += '&annotator=' + encodeURIComponent(ann_set[i].name);
	}
	url = server + '?action=fetch&db=' + db + '&record=' + record + annreq
	    + '&dt=0' + server_flags;
	show_status(true);
	get_jsonp(url, function(data) {
	    slist(t0_string);
	    adt_ticks = 0;
	    for (i = 0; i < data.fetch.annotator.length; i++, nann++) {
		ann[i] = data.fetch.annotator[i];
		ann[i].state = 1;
		len = ann[i].annotation.length;
		if (len > 0) { t = ann[i].annotation[len-1].t; }
		if (t > adt_ticks) { adt_ticks = t; }
		for (j = 0; j < ann_set.length; j++) {
		    if (ann[i].name === ann_set[j].name) {
			ann[i].desc = ann_set[j].desc;
		    }
		}
		// if an edit log exists for this annotator, load and reapply it
		selarr = ann[i].annotation;
		load_editlog(db, record, ann[i].name, true);
		summarize(ann[i]);
	    }
	    if (nann > 0) {
		ann[0].state = 2;
		annselected = ann[0].name;
		selarr = ann[0].annotation;
		load_palette(ann[0].summary);
	    }
	    else {
		load_palette([]);
	    }
	    // also load any annotators created from scratch using LightWAVE
	    if (edits_pending(db, record, "new")) {
		for (i = 0; i < nann; i++) {
		    if (ann[i].name === "new") { break; }
		}
		if (i >= nann) { new_annset(); }
		for (i = 1; i <= 4; i++) {  // allow up to 5 new annotators
		    if (edits_pending(db, record, "new" + i)) {
			for (j = 0; j < nann; j++) {
			    if (ann[j].name === "new" + i) { break; }
			}
			if (j >= nann) { new_annset(); }
		    }
		}
	    }
	    show_status(false);
	});
    }
    else {
	load_palette([]);
	annselected = null;
	selarr = null;
	slist(t0_string);
    }
}

// Retrieve one or more signal segments starting at t for the selected record
function read_signals(t0, update) {
    var i, fetch, s, sigreq = '', t, tf, tr = t0 + dt_ticks, trace = '';

    if (signals) {
	for (i = 0; i < signals.length; i++) {
	    if (s_visible[signals[i].name] === 1) {
		t = t0;
		tf = t + dt_ticks;
		while (t < tf) {
		    trace = find_trace(db, record, signals[i].name, t);
		    if (trace) {
			trace.id = tid++;	// found, mark as recently used
			t = trace.tf;
		    }
		    else {
			if (t < tr) { tr = t; } // must read from t to tf
			sigreq += '&signal='
			    + encodeURIComponent(signals[i].name);
			break;
		    }
		}
	    }
	}
    }
    if (sigreq) {
	url = server
	    + '?action=fetch'
	    + '&db=' + db
	    + '&record=' + record
	    + sigreq
	    + '&t0=' + tr/tickfreq
	    + '&dt=' + dt_sec
	    + server_flags;
	show_status(true);
	get_jsonp(url, function(data) {
	    fetch = data.fetch;
	    if (fetch && fetch.hasOwnProperty('signal')) {
		s = data.fetch.signal;
		for (i = 0; i < s.length; i++) {
		    set_trace(db, record, s[i]);
		}
	    }
	    if (update) { update_output(); }
	    show_status(false);
	});
    }
    else if (update) { update_output(); }
}

// Show the number of AJAX calls to the server, and the number not yet answered
function show_status(requestp) {
    var i, status;

    if (requestp) {
	requests++; pending++;
	if (requests > 10) {
	    for (i = rqlog.length - 5; i > 0; i--) {
		if (rqlog[i] !== '\n') { break; }
	    }
	    rqlog = requests + ': ' + url + '<br>\n' + rqlog.substring(0, i);
	}
	else { rqlog = requests + ': ' + url + '<br>\n' + rqlog; }
	$('#requests').html(rqlog);
    }
    else {
	pending--;
    }
    status = 'Requests: ' + requests + '&nbsp;&nbsp;Pending: ' + pending;
    $('#status').html(status);
}

// Functions for communicating with the LightWAVE scribe (annotation recorder)

// Test that the LightWAVE scribe is operating properly
function test_sync() {
    var body, boundary, timer;

    timer = setTimeout(alert_scribe_error, 2000);
    boundary = '-----------------------------' +
	Math.floor(Math.random() * Math.pow(10, 8));
    body = '--' + boundary
        + '\r\nContent-Disposition: form-data; name="file";'
        + ' filename="empty.txt"\r\nContent-type: text/plain\r\n\r\n'
        + '\r\n--' + boundary + '--\r\n';
    scribe = $('[name=scribe]').val();
    $.ajax({
	contentType: "multipart/form-data",
	data: body,
	type: 'POST',
	url: scribe,
	complete:  function(e, xhr, settings){
	    clearTimeout(timer);
	    if (e.status === 200) {
		$('#syncnote').html("Edit backup test successful.");
	    }
	    else {
		$('#syncnote').html("Edit backup test failed.");
		alert_scribe_error();
	    };
	}});
}

// "Save pending edits" button handler
function sync_edits() {
    var body, boundary, cookie, etext = '', fname, i, timer;

    if (changes.length - undo_count < 1) { alert("No pending edits!"); return; }

    // Save current edits to local storage first, then reload them
    save_editlog(db, record, annselected);
    load_editlog(db, record, annselected, false);

    for (i = changes.length - 1; i >= undo_count; i--) {
	etext += changes[i] + '\r\n';
    }

    for (i = 0; i < nann; i++) {
	if (ann[i].state === 2) break;
    }
    if (i >= nann) { alert("Select an annotation set to back up!");  return; }

    timer = setTimeout(alert_scribe_error, 2000);
    boundary = '-----------------------------' +
	Math.floor(Math.random() * Math.pow(10, 8));
    fname = db.replace(/\//g, "+") + '+' + record.replace(/\//g, "+")
	+ '.' + ann[i].name + '.log';
    body = '--' + boundary
        + '\r\nContent-Disposition: form-data; name="file";'
        + ' filename="' + fname + '"\r\nContent-type: text/plain\r\n\r\n'
	+ '[LWEditLog-1.0] Record ' + db + '/' + record
	+ ', annotator ' + ann[i].name + ' (' + tickfreq
        + ' samples/second)\r\n\r\n' + etext
        + '\r\n--' + boundary + '--\r\n';

    scribe = $('[name=scribe]').val();
    $('#syncnote').html('<p>Waiting for edit backup (sending to ' + scribe
			+ ') ...');
    $.ajax({
	contentType: "multipart/form-data",
	data: body,
	type: 'POST',
	url: scribe,
	success:  function(data, result) {
	    clearTimeout(timer);
	    // remove_editlog(db, record, annselected);
	    etext = '<p>Edits for record <b>' + sdb + '/' + record
				+ '</b>, annotator <b>' + annselected
				+ '</b> backed up successfully.';
	    cookie = ((data && data.url) || $.cookie("LWURL"));
	    if (cookie) {
		cookie = new URL(cookie, scribe);
		etext += '<p><a href="' + cookie
		    + '/" target="other">Download'
		    + ' (opens in another browser tab or window)</a>';
	    }
	    $('#syncnote').html(etext);
	},
	statusCode: {
	    404: function() {
		clearTimeout(timer);
		$('#syncnote').html("Edit backup failed.");
		alert_scribe_error();
	    }
	}
    });
}

// "Choose input" tab handler functions

// When a new record is selected, reload data and show the first dt_sec seconds.
function newrec() {
    var i, prompt;

    // save any pending edits
    for (i = 0; i < nann; i++) {
	save_editlog(db, record, ann[i].name);
    }
    ann = [];
    record = $('[name=record]').val();
    if (record.match("/$")) {
	$('#rslist').html('<td align=right>Sub-record:</td>' +
		  '<td id="rslist">Reading list of sub-records...</td>');
	rslist();
	return;
    }
    $('#findbox').dialog("close");
    $('#add_typebox').dialog("close");
    prompt = 'Reading annotations for ' + sdb + '/' + record;
    $('#prompt').html(prompt);
    read_annotations("0");
    prompt = 'Click on the <b>View/edit</b> tab to view ' + sdb + '/' + record;
    $('#prompt').html(prompt);
    set_sw_width(dt_sec);
}

// When a new subrecord is selected, reload data and show the first dt_sec
// seconds.
function newsubrec() {
    var i, prompt;

    // save any pending edits
    for (i = 0; i < nann; i++) {
	save_editlog(db, record, ann[i].name);
    }
    ann = [];
    record = $('[name=record]').val() + $('[name=subrec]').val();
    $('#findbox').dialog("close");
    $('#add_typebox').dialog("close");
    prompt = 'Reading annotations for ' + sdb + '/' + record;
    $('#prompt').html(prompt);
    read_annotations("0");
    prompt = 'Click on the <b>View/edit</b> tab to view ' + sdb + '/' + record;
    $('#prompt').html(prompt);
    set_sw_width(dt_sec);
}

// When a new database is selected, reload the annotation and record lists.
function newdb() {
    var dbparts, i, title;

    // save any pending edits
    for (i = 0; i < nann; i++) {
	save_editlog(db, record, ann[i].name);
    }
    ann = [];
    ann_set = [];
    nann = 0;
    db = $('#db').val();
    dbparts = db.split('/');
    sdb = db;
    record = '';
    title = 'LightWAVE: ' + sdb;
    document.title = title;
    $('#tabs').tabs({disabled:[1,2]});
    $('#rlist').empty();
    $('#annsets').empty();
    $('#info').empty();
    $('#anndata').empty();
    $('#sigdata').empty();
    $('#plotdata').empty();
    alist();
    rlist();
    show_localstorage();
}

// Refresh either the View/edit or Tables tab
function update_output() {
    if (current_tab === 'View/edit') { show_plot(); }
    else if (current_tab === 'Tables') { show_tables(); }
}

// Refresh the signal window on the View/edit tab
function show_plot() {
    var a, downarrow, desc, dy, g, grd, i, imin, imax, ia, is, j, pv, s, sname,
      sva, svgts, svs, t, tf, title, tnext, tps, trace, tst, tt, ttick, txt,
      uparrow, v, x, xstep, xtick, x0q, x0r, x0s, y, ytop, y0, y0s = [], y1,
      y0a = [], z;

    width = $('#plotdata').width();  // total available width in View/edit panel
    swl = Math.round(width*svgl/svgtw);    // left column width
    sww = Math.round(width*svgw/svgtw);   // signal window width
    swr = width - (swl + sww);	     // right column width
    height = Math.round(0.55*sww);   // signal window height

    // calculate baselines for signals and annotators
    ia = is = 0;
    y = dy = Math.round(svgh/(nsig + nann + 1));
    while (is < nsig || ia < nann) {
	if (is < nsig) { y0s[is] = y; y += dy; is++; }
	if (ia < nann) { y0a[ia] = y; y += dy; ia++; }
    }
    if (nann > 0) { asy0 = y0a[0]; }

    svg = '<br><svg xmlns=\'http://www.w3.org/2000/svg\''
	+ ' xmlns:xlink=\'http://www.w3.org/1999/xlink\' class="svgplot"'
	+ ' width="' + width + '" height="' + height
	+ '" preserveAspectRatio="xMidYMid meet">\n';
    svg += '<g id="viewport" transform="scale(' + width/svgtw
	+ '),translate(' + svgl + ',' + svgf + ')">\n';

    // background grid
    grd = '<g id="grid">\n'
	+ '<circle cx="-' + svgf + '" cy="' + svgh
	+ '" r="' + svgc +'" stroke="rgb(200,100,100)"'
        + ' stroke-width="' + lwb + '" fill="red" fill-opacity="'
	+ g_visible + '"/>';
    if (g_visible === 0) {
	grd += '<title>(click to show grid)</title></g>';
    }
    else {
	x0s = (tscl-Math.floor((t0_ticks % tickfreq)*tscl/tickfreq))%tscl;
	x0r = x0s%griddx;
	x0q = Math.floor(x0s/griddx)*griddx;
	grd += '<title>(click to hide grid)</title></g>'
	    + '<path stroke="rgb(200,100,100)" fill="red" stroke-width="' + lwl
	    + '" d="M' + x0r + ',0 ';
	uparrow = ' l-' + adx1 + ',' + ady1 + 'l' + adx2 + ',0 l-' + adx1
	    + ',-' + ady1 +  'm' + griddx + ',-';
	for (x = 0; x + x0r <= svgw + 0.01 * griddx; x += griddx) {
	    if (x%tscl === x0q) { grd += 'l0,' + svgh + uparrow + svgh; }
	    else { grd += 'l0,' + svgh + ' m' + griddx + ',-' + svgh; }
	}
	grd += 'M0,0 ';
	for (y = 0; y <= svgh; y += 200) {
	    grd += 'l' + svgw + ',0 m-' + svgw +',200 ';
	}
	grd += '" />\n';
    }

    // timestamps
    svgts = svgh + 2*ady1;
    ttick = Math.floor(t0_ticks/tickint) * tickint;
    if (ttick < t0_ticks) { ttick += tickint; }

    tst = '<g id="times">\n';
    while (ttick <= tf_ticks + 0.1) {
	xtick = Math.round((ttick - t0_ticks)*tscl/tickfreq);
	tst += '<text x="' + xtick + '" y="' + svgts + '" font-size="' + svgtf
	    + '" fill="red" style="text-anchor: middle;">'
	    + timstr(ttick) + '</text>\n';
	ttick += tickint;
    }
    tst += '</g>\n';

    // annotator names and annotations
    sva = '<g id="mrkr">\n'
	+ '<circle cx="-' + svgf + '" cy="0" r="' + svgc
	+ '" stroke="rgb(0,0,200)"'
        + ' stroke-width="' + lwb + '" fill="blue" fill-opacity="'
	+ m_visible + '"/>';
    if (m_visible === 0) {
	sva += '<title>(click to show marker bars)</title></g>';
    }
    else {
	sva += '<title>(click to hide marker bars)</title></g>';
    }
    downarrow = ',0 l-' + adx1 + ',-' + ady1 + ' l' + adx2 + ',0 l-' + adx1
	+ ',' + ady1 + ' V';
    for (ia = 0; ia < nann; ia++) {
	y0 = y0a[ia];
	ytop = y0 - svgf;
	sva += '<g id="ann;;' + html_escape(ann[ia].name) + '">\n';
	if (ann[ia].state > 0) {
	    sva += '<title>' + html_escape(ann[ia].desc);
	    if (ann[ia].state === 2) {
		asy0 = y0;
		sva += ' (click for normal view)</title>';
		if (editing) {
		    sva += '<rect x="0" y="' + Number(ytop - svgf)
			+ '" width="' + svgw + '" height="' + 3*svgf
			+ '" fill="#88f" fill-opacity="0.2" />';
		}
	    }
	    else {
		sva += ' (click to hide)</title>';
	    }
	    sva += '<rect x="-' + svgl + '" y="' + ytop
		+ '" width="' + svgl + '" height="' + 2*svgf
		+ '" fill="white" />'
		+ '<text x="-50" y="' + y0
		+ '" font-size="' + svgf + '" fill="blue" font-style="italic"'
		+ ' style="text-anchor: end; dominant-baseline: middle"';
	    if (ann[ia].state === 2) { sva += ' font-weight="bold"'; }
	    sva += '>' + html_escape(ann[ia].name) + '</text></g>\n';
	    a = ann[ia].annotation;
	    desc = (ann[ia].description || {});
	    for (i = ann_after(a, t0_ticks);
		 0 <= i && i < a.length && a[i].t <= tf_ticks; i++) {
		x = Math.round((a[i].t - t0_ticks)*tscl/tickfreq);
		if (a[i].x) {
		    if (a[i].a === '+') { y = y0+svgf; }
		    else {y = y0-svgf; }
		    txt = html_escape(String(a[i].x));
		}
		else {
		    y = y0;
		    // display N annotations as bullets
		    if (a[i].a === 'N') { txt = '&bull;'; }
		    else if (a[i].a === '~' && nsig > 0) {
			y = y0-svgf;
			if (a[i].s == -1) {
			    txt = 'U';
			}
			else {
			    txt = '';
			    for (j = 0; j < 4 && j < nsig; j++) {
				if (a[i].s & (16 << j)) { txt += 'u'; }
				else if (a[i].s & (1 << j)) { txt += 'n'; }
				else { txt += 'c'; }
			    }
			}
		    }
		    else { txt = html_escape(a[i].a); }
		}
		if (m_visible) {
		    y1 = y - 150;
		    sva += '<path stroke="rgb(0,0,200)" stroke-width="' + lwl
			+ '" fill="blue" + opacity="' + m_visible
			+ '" d="M' + x + downarrow + y1
			+ ' m0,210 V' + svgh + '" />\n';
		}
		title = desc[a[i].a];
		if (title) {
		    sva += '<g><title>' + html_escape(title) + '</title>';
		}
		sva += '<text x="' + x + '" y="' + y
		    + '" style="text-anchor: middle;"';
		if (ann[ia].state === 2) { sva += ' font-weight="bold"'; }
		sva += ' font-size="' + svgf + '" fill="rgb(0,0,200)">'
		    + txt + '</text>\n';
		if (title) { sva += '</g>'; }
	    }
	}
	else {
	    sva += '<title>' + html_escape(ann[ia].desc)
	    	+ ' (click for highlighted view)</title>'
		+ '<rect x="-' + svgl + '" y="' + ytop
		+ '" width="' + svgl + '" height="' + 2*svgf
		+ '" fill="white" />'
		+ '<text x="-50" y="' + y0 + '"' + ' font-size="' + svgf
		+ '" fill="rgb(150,150,200)" font-style="italic"'
		+ ' style="text-anchor: end; dominant-baseline: middle">'
		+ html_escape(ann[ia].name) + '</text></g>\n';
	}
    }

    // signal names and traces
    svs = '';
    for (is = 0; is < nsig; is++) {
	y0 = y0s[is];
	ytop = y0 - svgf;
	sname = signals[is].name;
	trace = find_trace_in_range(db, record, sname, t0_ticks, tf_ticks);

	svs += '<g id="sig;;' + html_escape(sname) + '">\n';
	if (trace && s_visible[sname] === 1) {
	    svs += '<title>' + html_escape(sname);
	    if (sname === sigselected) {
		svs += ' (click for normal view)</title>';
	    }
	    else {
		svs += ' (click to hide)</title>';
	    }
	    svs += '<rect x="-' + svgl + '" y="' + ytop
		+ '" width="' + svgl + '" height="' + 2*svgf
		+ '" fill="white" />'
		+ '<text x="-50" y="' + y0
		+ '" font-size="' + svgf + '" fill="black" font-style="italic"'
		+ ' style="text-anchor: end; dominant-baseline: middle"';
	    if (sname === sigselected) { svs += ' font-weight="bold"'; }
	    svs += '>' + html_escape(sname) + '</text></g>\n';

	    s = trace.samp;
	    tps = trace.tps;
	    g = (-400*mag[sname]/(trace.scale*trace.gain));
	    z = trace.zbase*g - y0;
	    v = Math.round(g*s[imin] - z);
	    // move to start of trace
	    svs += '<path stroke="black" fill="none" stroke-width="';
	    if (sname === sigselected) { svs += lwb; }
	    else { svs += lwn; }
	    svs += '" d="';
	    tnext = t0_ticks;
	    tf = Math.min(tf_ticks, rdt_ticks);
	    xstep = tscl/tickfreq;
	    pv = false;
	    while (tnext < tf) {
		if (tnext > t0_ticks) {
		    trace = find_trace_in_range(db, record, sname, tnext, tf);
		    if (trace === null) {
			if (pending < 1) {
			    read_signals(t0_ticks, true);
			}
			else if (pending < 4) {
			    setTimeout(function() {
				trace = find_trace(db, record, sname, tnext);
			    },1000);  // try again after a second
			}
			else {
			    autoplay_off();
			    alert_server_error();
			}
			break;
		    }
		    s = trace.samp;
		}
		imin = Math.max(Math.floor((tnext - trace.t0)/tps), 0);
		imax = Math.min((tf - tnext)/tps + imin, s.length);
		t = imin * tps + trace.t0 - t0_ticks;
		for (i = imin; i < imax; i++) {
		    x = t*xstep;
		    if (s[i] !== -32768) {
			v = Math.round(g*s[i] - z);
			if (pv) { svs += ' '  + x + ',' + v; }
			else { svs += ' M' + x + ',' + v  + ' L' + x + ',' + v;}
			pv = true;
		    }
		    else { pv = false; }
		    t += tps;
		}
		tnext = trace.tf;
	    }
	    svs += '" />\n';
	}
	else {	// signal is hidden, show label only
	    svs += '<title>' + html_escape(sname)
		+ ' (click for highlighted view)</title>'
		+ '<rect x="-' + svgl + '" y="' + ytop
		+ '" width="' + svgl + '" height="' + 2*svgf
		+ '" fill="white" />'
		+ '<text x="-50" y="' + y0 + '"' + ' font-size="' + svgf
		+ '" fill="rgb(128,128,128)" font-style="italic"'
		+ ' style="text-anchor: end; dominant-baseline: middle">'
		+ html_escape(sname) + '</text></g>\n';
	}
    }

    svg += grd + tst + sva + svs;
    $('#plotdata').html(svg + '</svg>\n');
    m = document.getElementById("viewport").getScreenCTM();

    if (selann >= 0) {
	tt = selarr[selann].t - t0_ticks;
	if (0 <= tt && tt < dt_ticks) {
	    x = Math.round(tt * m.a * tscl/tickfreq + m.e);
	    highlight_selection();
	    show_time(x, 0);
	}
    }

    // Reset the svg handlers since the svg elements have changed.
    reset_svg_handlers();
}

// Reset the signal window event handlers (needed whenever SVG elements change)
function reset_svg_handlers() {
    if ($grid) { $grid.off('click'); }
    $grid = $('#grid');
    $grid.on('click', grid_mode);
    if ($mrkr) { $mrkr.off('click'); }
    $mrkr = $('#mrkr');
    $mrkr.on('click', mrkr_mode);
    if ($anames) { $anames.off('click'); }
    $anames = $("[id^='ann;;']");
    $anames.on('click', anames_mode);
    if ($snames) { $snames.off('click'); }
    $snames = $("[id^='sig;;']");
    $snames.on('click', snames_mode);
    if ($svg) {
	switch (emode) {
	case 1: $svg.off('mousemove'); break;
	case 2: $svg.off('mousedown mousemove mouseup'); break;
	case 3: $svg.off('mousedown mousemove mouseup'); break;
	}
    }
    $svg = $('svg');
    switch (emode) {
    case 1: $svg.on('mousemove', track_pointer); break;
    case 2:
	$svg.on('mousedown', select_ann)
	    .on('mousemove', track_pointer)
	    .on('mouseup', mark);
	break;
    case 3:
	$svg.on('mousedown', select_ann)
	    .on('mousemove', track_touch)
	    .on('mouseup', track_pointer);
	break;
    }
}

//-----------------------------------------------------------------------------
// Signal window event handlers

// Handle click on grid mode button (hide/show grid)
function grid_mode() {
    g_visible = 1 - g_visible; show_plot();
}

// Handle click on marker mode button (hide/show edit markers)
function mrkr_mode() {
    m_visible = 1 - m_visible; show_plot();
}

// Handle click on annotator name label (hide/select+highlight/show annotator)
function anames_mode() {
    var aname, i, j;

    aname = $(this).attr('id').split(";")[2];
    for (i = 0; i < nann; i++) {
	if (ann[i].name === aname) { break; }
    }
    if (i < nann) {
	switch (ann[i].state) {
	case 0:   // annotator is hidden: select it
	    for (j = 0; j < nann; j++) {  // reset current selection
		if (ann[j].state === 2) {
		    ann[j].state = 1;
		    break;
		}
	    }
	    ann[i].state = 2;  // select this annotator
	    if (annselected !== aname) {
		save_editlog(db, record, annselected);
		annselected = aname;
		selarr = ann[i].annotation;
		// reload the edit log, but don't reapply the changes
		load_editlog(db, record, aname, false);
	    }
	    load_palette(ann[i].summary);
	    ilast = selann = -1;  // clear annotation selection, if any
	    svsa = '';
	    break;
	case 1:   // annotator is visible, not selected:  hide it
	    ann[i].state = 0;
	    break;
	case 2:   // annotator is selected: deselect it, leave it visible
	    ann[i].state = 1;
	    ilast = selann = -1;
	    svsa = '';
	    break;
	}
    }
    show_plot();
}

// Handle click on signal name label (hide/select+highlight/show signal)
function snames_mode() {
    var sname;

    sname = $(this).attr('id').split(";")[2];
    if (s_visible[sname] === 0) {
	s_visible[sname] = 1;
	sigselected = sname;
	$('.stretch').removeAttr('disabled');
	$('.reset').removeAttr('disabled');
	$('.shrink').removeAttr('disabled');
    }
    else if (sigselected === sname) {
	sigselected = '';
	$('.stretch').attr('disabled', 'disabled');
	$('.reset').attr('disabled', 'disabled');
	$('.shrink').attr('disabled', 'disabled');
    }
    else { s_visible[sname] = 0; }
    read_signals(t0_ticks, true);
    show_plot();
}

// Handle click on grid mode button (hide/show grid)
function grid_mode() {
    g_visible = 1 - g_visible; show_plot();
}

// Handle click on marker mode button (hide/show edit markers)
function mrkr_mode() {
    m_visible = 1 - m_visible; show_plot();
}

// Handle click on annotator name label (hide/select+highlight/show annotator)
function anames_mode() {
    var aname, i, j;

    aname = $(this).attr('id').split(";")[2];
    for (i = 0; i < nann; i++) {
	if (ann[i].name === aname) { break; }
    }
    if (i < nann) {
	switch (ann[i].state) {
	case 0:   // annotator is hidden: select it
	    for (j = 0; j < nann; j++) {  // reset current selection
		if (ann[j].state === 2) {
		    ann[j].state = 1;
		    break;
		}
	    }
	    ann[i].state = 2;  // select this annotator
	    if (annselected !== aname) {
		save_editlog(db, record, annselected);
		annselected = aname;
		selarr = ann[i].annotation;
		// reload the edit log, but don't reapply the changes
		load_editlog(db, record, aname, false);
	    }
	    load_palette(ann[i].summary);
	    ilast = selann = -1;  // clear annotation selection, if any
	    svsa = '';
	    break;
	case 1:   // annotator is visible, not selected:  hide it
	    ann[i].state = 0;
	    break;
	case 2:   // annotator is selected: deselect it, leave it visible
	    ann[i].state = 1;
	    ilast = selann = -1;
	    svsa = '';
	    break;
	}
    }
    show_plot();
}

// Handle click on signal name label (hide/select+highlight/show signal)
function snames_mode() {
    var sname;

    sname = $(this).attr('id').split(";")[2];
    if (s_visible[sname] === 0) {
	s_visible[sname] = 1;
	sigselected = sname;
	$('.stretch').removeAttr('disabled');
	$('.reset').removeAttr('disabled');
	$('.shrink').removeAttr('disabled');
    }
    else if (sigselected === sname) {
	sigselected = '';
	$('.stretch').attr('disabled', 'disabled');
	$('.reset').attr('disabled', 'disabled');
	$('.shrink').attr('disabled', 'disabled');
    }
    else { s_visible[sname] = 0; }
    read_signals(t0_ticks, true);
    show_plot();
}

// Show the time corresponding to (x,y) as HH:MM:SS.mmm in upper right corner
function show_time(x, y) {
    svgxyt(x, y);
    var boxh, boxy0, label, ts, xc;

    ts = mstimstr(t_cursor);
    $('.pointer').html(ts);
    if (xx_cursor < 0) { return; }

    if (y != 0 && editing) {
	xc = x_cursor - 2*adx4;
	svc = '<path stroke="rgb(0,150,0)" stroke-width="' + lwn
	    + '" fill="none" style="cursor:pointer" d="M' + x_cursor
	    + ',0 l-' + adx2 + ',-' + ady1 + ' l' + adx4 + ',0 l-' + adx2
	    + ',' + ady1 + ' V' + svgh
	    + ' l-' + adx2 + ',' + ady1 + ' l' + adx4 + ',0 l-' + adx2
	    + ',-' + ady1 + '" />';

	boxh = 3*svgf;
	boxy0 = asy0 - 2*svgf;
	if (boxy0 < y_cursor && y_cursor < boxy0 + boxh) {
	    label = insert_mode ? selkey : "&#9003;";
	    svc += '<path stroke="rgb(0,150,0)" stroke-width="' + lwn
		+ '" d="M' + x_cursor + ',0 V' + boxy0
		+ ' m0,' + 3*svgf + ' V' + svgh + '" />'
		+ '<rect x="' + Number(x_cursor - svgf) + '" y="' + boxy0
		+ '" width="' + 2*svgf + '" height="' + boxh
		+ '" stroke="rgb(0,0,0)" stroke-width="' + lwn
		+ '" fill="#88f" fill-opacity="0.2" style="cursor:pointer" />'
		+ '<text x="' + x_cursor + '" y="' + Number(y_cursor - svgf)
		+ '" style="text-anchor: middle"'
		+ ' font-size="' + svgf + '" fill="rgb(0,0,200)">'
		+ label + '</text>\n';
	}

	$('#plotdata').html(svg + svc + svsa + '</svg>\n');

	reset_svg_handlers();
    }
}

// Track touch move ("swipe") events (no edit marker bar)
function track_touch(e) {
    var ts;

    c_velocity = 10;
    svgxyt(e.clientX, e.clientY);
    ts = mstimstr(t_cursor);
    $('.pointer').html(ts);
}

// Track mouse move ("drag") events (with edit marker bar)
function track_pointer(e) {
    c_velocity = 10;
    show_time(e.clientX, e.clientY);
}


// Initialize the palette with the most common annotation types in summary
function load_palette(summary) {
    var annot, f, i, imax, ptext = '';

    if (summary.length == 0) {
	summary = [[ 'N', -1 ]];
    }

    annot = { "t": null, "a": null, "c": null,
	      "n": null, "s": null, "x": null };
    palette = summary;
    imax = summary.length;
    if (imax > 20) { imax = 20; }
    for (i = 0; i < imax; i++) {
	ptext += '<button class="palette_ann"';
	if (i === 0) {
	    ptext += ' style="color: white; background-color: blue"';
	    seltype = '#palette_0';
	}
	else { ptext += ' style="color: blue; background-color: white"'; }
	ptext += ' id="palette_' + i + '">' + summary[i][0] + '</button>';
    }
    f = summary[0][0].split(":");
    switch (f.length) {
    case 1:
	if (f[0][0] === '(' && f[0].length > 1) {
	    annot.a = '+';
	    annot.x = f[0];
	}
	else { annot.a = f[0]; }
	break;
    case 2:
	annot.a = f[0];
	annot.x = f[1];
	break;
    }
    copy_to_template(annot);
    selkey = summary[0][0];
    $('#palette').html(ptext);
    $('.palette_ann').on('click', select_type);
}

// Calculate various dimensions related to the duration of the signal window
function set_sw_width(seconds) {
    dt_sec = seconds;
    if (dt_sec < 10) { tickint = tickfreq; griddt = tickfreq / 5; }
    else if (dt_sec < 21) { tickint = 5 * tickfreq; griddt = tickfreq / 5; }
    else if (dt_sec < 35) { tickint = 5 * tickfreq; griddt = tickfreq; }
    else if (dt_sec < 181) { tickint = 10 * tickfreq; griddt = 2 * tickfreq; }
    else if (dt_sec < 601) { tickint = 60 * tickfreq; griddt = 10 * tickfreq; }
    else if (dt_sec < 1801){ tickint = 300 * tickfreq; griddt = 60 * tickfreq; }
    else { tickint = 600 * tickfreq; griddt = 300 * tickfreq; }
    griddx = tscl * griddt / tickfreq;

    svgw = tscl*dt_sec;
    svgh = Math.round(svgw/2);
    svgl = Math.round(svgw/8);
    svgr = Math.round(svgw/24);
    svgtw= svgl + svgw + svgr;
    svgf = Math.round(svgw * 0.012);
    svgtf= Math.round(svgw * 0.01);
    svgc = Math.round(svgw * 0.008);
    lwl = Math.ceil(svgw * 0.0005);
    lwn = lwl * 2;
    lwb = lwl * 3;
    adx1 = Math.round(svgw * 0.002);
    adx2 = adx1 * 2;
    adx4 = adx1 * 4;
    ady1 = adx1 * 5;
}

// Create a palette button label/summary row name from an annotation
function askey(annot)
{
    var key;

    if (annot.x !== null && annot.x !== '') {
	if (annot.a === '+' && annot.x[0] === '(') { key = annot.x; }
	else { key = annot.a + ':' + annot.x; }
    }
    else { key = annot.a; }

    return key;
}

// Compile a summary of the annotation types in ann[i]
function summarize(annotator) {
    var a = annotator.annotation, i, key, s = {}, ss = [];

    for (i = 0; i < a.length; i++) {
	key = askey(a[i]);
	if (s.hasOwnProperty(key)) { s[key]++; }
	else { s[key] = 1; }
    }
    for (key in s) { ss.push([key, s[key]]); }
    // sort the types by prevalence (most to least frequent)
    annotator.summary = ss.sort(function(a, b) {return b[1] - a[1]});
}

// Handle browser window resize events
function resize_lightwave() {
    var vp = document.getElementById("viewport");
    m = (vp ? vp.getScreenCTM() : null);
    set_sw_width(dt_sec);
    $('#helpframe').attr('height', $(window).height() - 180 + 'px');
    show_plot(); // redraw signal window if resized
}

//-----------------------------------------------------------------------------// Navigation handler helper functions

// Prefetch data for later use
function prefetch(t_ticks) {
    if (t_ticks < 0) { t_ticks = 0; }
    if (t_ticks < rdt_ticks) { read_signals(t_ticks, false); }
}

// Move back (toward the beginning of the record) by the autoscroll increment
function scrollrev() {
    t0_ticks -= dt_sec;  // the increment was chosen to divide dt_ticks evenly
    if (t0_ticks <= 0) {
	t0_ticks = 0;
	autoplay_off();
    }
    go_here(t0_ticks);
    if (t0_ticks > 0) {
	prefetch(Math.floor((t0_ticks - 1)/dt_ticks) * dt_ticks);
    }
}

// Move forward (toward the end of the record) by the autoscroll increment
function scrollfwd() {
    t0_ticks += dt_sec;
    if (t0_ticks >= rdt_ticks - dt_ticks) { autoplay_off(); }
    go_here(t0_ticks);
    if (t0_ticks < rdt_ticks - dt_ticks	&& (t0_ticks % dt_ticks === 0)) {
	prefetch(t0_ticks + 2*dt_ticks);
    }
}

// Stop autoplay in the View/edit window and reset the autoplay button labels
function autoplay_off() {
    if (autoscroll) {
	clearInterval(autoscroll);
	autoscroll= null;
	$('.scrollfwd').html('&#9654;');
	$('.scrollrev').html('&#9664;');
    }
}

// Reset the signal window so that it begins at t_ticks
function go_here(t_ticks) {
    var title, t0_string, x, y;

    if (t_ticks >= rdt_ticks) {
	t_ticks = rdt_ticks;
	$('.fwd').attr('disabled', 'disabled');
	$('.eor').attr('disabled', 'disabled');
	$('.sfwd').attr('disabled', 'disabled');
    }
    else {
	$('.fwd').removeAttr('disabled');
	$('.eor').removeAttr('disabled');
	if (target && selarr) { $('.sfwd').removeAttr('disabled'); }
    }
    if (t_ticks <= 0) {
	t_ticks = 0;
	$('.rev').attr('disabled', 'disabled');
	$('.sor').attr('disabled', 'disabled');
	$('.srev').attr('disabled', 'disabled');
    }
    else {
	$('.rev').removeAttr('disabled');
	$('.sor').removeAttr('disabled');
	if (target && selarr) { $('.srev').removeAttr('disabled'); }
    }

    title = 'LW: ' + sdb + '/' + record;
    document.title = title;
    t0_string = timstr(t_ticks);
    $('.t0_str').val(t0_string);
    t0_ticks = t_ticks;
    tf_ticks = t_ticks + dt_ticks;

    read_signals(t0_ticks, true); // read signals not previously cached, if any

    if (tf_ticks >= rdt_ticks) {
	$('.fwd').attr('disabled', 'disabled');
	$('.eor').attr('disabled', 'disabled');
	$('.sfwd').attr('disabled', 'disabled');
    }
    if (m) {
	x = Math.round(x_cursor * m.a + m.e);
	y = Math.round(asy0 * m.d + m.f);
	show_time(x, y);
	highlight_selection();
    }
}

// Return true if sa[i].a matches target, false otherwise
function match(sa, i) {
    var m = false;

    switch (target) {
    case '*':
	m = true;
	break;
    case '*v':
	switch (sa[i].a) {
	case 'V':
	case 'E':
	case 'r':
	    m = true;
	    break;
	}
	break;
    case '*s':
	switch (sa[i].a) {
	case 'S':
	case 'A':
	case 'a':
	case 'J':
	case 'e':
	case 'j':
	case 'n':
	    m = true;
	    break;
	}
	break;
    case '*n':
	switch (sa[i].a) {
	case 'N':
	case 'L':
	case 'R':
	case 'B':
	case 'F':
	case '/':
	case 'f':
	case 'Q':
	case '?':
	    m = true;
	    break;
	}
	break;
    default:
	if (sa[i].a === target || sa[i].x === target) { m = true; }
	break;
    }
    return m;
}

//-----------------------------------------------------------------------------
// View/edit and Tables navigation button handlers

// Move so that the signal window begins at the "Go to:" position
function go_to() {
    var t_ticks,  t0_string;

    if (current_tab === 'View/edit') {
	t0_string = $('#view .t0_str').val();
    }
    else if (current_tab === 'Tables') {
	t0_string = $('#tables .t0_str').val();
    }
    $('.t0_str').val(t0_string);
    t_ticks = strtim(t0_string);
    go_here(t_ticks);
}

// Move to the beginning of the record
function gostart() {
    go_here(0);
}

// Move one screenful back (toward the beginning of the record)
function gorev() {
    var t_ticks, t0_string;

    t0_string = $('.t0_str').val();
    t_ticks = strtim(t0_string) - dt_ticks;
    go_here(Math.round(t_ticks / tickfreq) * tickfreq);
    prefetch(t_ticks - dt_ticks);
}

// Start autoplay in reverse and reset the scroll-reverse button label
function autoplay_rev() {
    var dti;

    if (autoscroll) { autoplay_off(); }
    else {
	dti = 50+dt_ticks*nsig/1000;
	autoscroll = setInterval(scrollrev, dti);
	$('.scrollrev').html('<div style="color: red">&#9632;</div>');
    }
}

// Start autoplay forward and reset the scroll-forward button label
function autoplay_fwd() {
    var dti;

    if (autoscroll) { autoplay_off(); }
    else {
	dti = 50+dt_ticks*nsig/1000;
	autoscroll = setInterval(scrollfwd, dti);
	$('.scrollfwd').html('<div style="color: red">&#9632;</div>');
    }
}

// Move one screenful forward (toward the end of the record)
function gofwd() {
    var t_ticks,  t0_string;

    t0_string = $('.t0_str').val();
    t_ticks = strtim(t0_string) + dt_ticks;
    go_here(Math.round(t_ticks / tickfreq) * tickfreq);
    prefetch(t_ticks + Number(dt_ticks));
}

// Move to the end of the record
function goend() {
    var t = Math.floor((rdt_ticks-1)/dt_ticks);
    go_here(t*dt_ticks);
}

// Search for the previous match and center the window on it, if there is one
function srev() {
    var halfdt, i, ia, na = 0, sa = '', t;

    // find the annotation set
    for (ia = 0; ia < nann; ia++) {
	if (ann[ia].state === 2) {
	    sa = ann[ia].annotation;
	    na = sa.length;
	    break;
	}
    }
    if (ia >= nann) { return; }  // annotation set not found

    // find the previous annotation matching the target before the signal window
    for (i = ann_before(sa, t0_ticks); i >= 0; i--) {
	if (match(sa, i)) { break; }
    }
    // if a match was found ...
    if (i >= 0) {
	halfdt = Math.floor(dt_ticks/2);
	t = sa[i].t - halfdt;
	go_here(t);	// show it

	// find the last annotation in the set before the new signal window
	while (i >= 0 && sa[i].t > t) { i--; }

	// find and cache the previous match, if any
	while (i >= 0 && !match(sa, i)) { i--; }

	// if another match was found ...
	if (i >= 0) {
	    t = sa[i].t - halfdt;
	    prefetch(t);  // cache it
	}
	else {
	    // otherwise, disable further reverse searches
	    $('.srev').attr('disabled', 'disabled');
	}
    }
    else {  // no match found, disable further reverse searches
	$('.srev').attr('disabled', 'disabled');
	alert(target + ' not found in ' + ann[ia].name
	      + ' before ' + timstr(t0_ticks));
    }
}

// Set target for searches with srev() and sfwd()
function find() {
    var content = '', i, ia;

    if (nann <= 0) { alert('No annotations to search!'); }
    for (ia = 0; ia < nann; ia++) {
	if (ann[ia].state === 2) { break; }
    }
    if (ia >= nann) {
	alert('No annotations have been chosen for searching!\n\n'
	      + 'Choose an annotation set to search by\n'
	      + 'clicking on its name (to the left of the\n'
	      + 'signal window) until it is highlighted.');
    }
    else if ($('#findbox').dialog("isOpen")) { $('#findbox').dialog("close"); }
    else {
	$('#target').val(target);
	$('#target').on("change", function() {
	    target = $('#target').val();
	    if (target !== '') {
		if (t0_ticks > 0) {
		    $('.srev').removeAttr('disabled');
		}
		if (tf_ticks <= rdt_ticks) {
		    $('.sfwd').removeAttr('disabled');
		}
	    }
	});

	$('#findbox').dialog("open");
	$('#findbox').dialog({
            height: 'auto',
	    beforeClose: function() {
		target = $('#target').val();
	    },
	    close: function() {
		if (target !== '') {
		    if (t0_ticks > 0) {
			$('.srev').removeAttr('disabled');
		    }
		    if (tf_ticks <= rdt_ticks) {
			$('.sfwd').removeAttr('disabled');
		    }
		}
	    }
	});
    }
}

// Search for the next match and center the window on it, if there is one
function sfwd() {
    var halfdt, i, ia, na = 0, sa = '', t;

    // find the annotation set
    for (ia = 0; ia < nann; ia++) {
	if (ann[ia].state === 2) {
	    sa = ann[ia].annotation;
	    na = sa.length;
	    break;
	}
    }
    if (ia >= nann) { return; }  // annotation set not found

    // find the next annotation matching the target after the signal window
    for (i = ann_after(sa, tf_ticks); i < na; i++) {
	if (match(sa, i)) { break; }
    }
    // if a match was found ...
    if (i < na) {
	halfdt = Math.floor(dt_ticks/2);
	t = sa[i].t - halfdt;
	go_here(t);	// show it

	// find the first annotation in the set after the new signal window
	t += +dt_ticks;
	while (i < na && sa[i].t < t) { i++; }

	// find and cache the next match, if any
	while (i < na && !match(sa, i)) { i++; }

	// if another match was found ...
	if (i < na) {
	    t = sa[i].t - halfdt;
	    prefetch(t);  // cache it
	}
	else {
	    // otherwise, disable further forward searches
	    $('.sfwd').attr('disabled', 'disabled');
	}
    }
    else {  // no match found, disable further forward searches
	$('.sfwd').attr('disabled', 'disabled');
	alert(target + ' not found in ' + ann[ia].name
	      + ' after ' + timstr(tf_ticks));
    }
}

// Signal amplitude adjustment button handlers

// Make the selected signal larger
function stretch_signal() {
    if (sigselected !== '' && mag[sigselected] < 1000) {
	mag[sigselected] *= 1.1;
	show_plot();
    }
}

// Reset the selected signal amplitude to the initial (default) value
function reset_signal() {
    if (sigselected !== '' && mag[sigselected] !== 1) {
	mag[sigselected] = 1.1;
	show_plot();
    }
}

// Make the selected signal smaller
function shrink_signal() {
    if (sigselected !== '' && mag[sigselected] > 0.001) {
	mag[sigselected] /= 1.1;
	show_plot();
    }
}

//-----------------------------------------------------------------------------
// Edit helper functions

// Mark the selected annotation with a rectangle
function highlight_selection() {
    var dt, x0, y0;

    svsa = '';
    if (selann >= 0) {
	dt = selarr[selann].t - t0_ticks;
	if (0 <= dt && dt <= dt_ticks) {
	    x0 = Math.floor(dt*tscl/tickfreq) - svgf;
	    y0 = asy0 - 2*svgf;
	    svsa = '<path stroke="rgb(0,0,0)" stroke-width="' + lwn
		+ '" fill="yellow" fill-opacity="0.2" d="M'
		+ x0 + ',' + y0 + ' l' + 2*svgf + ',0 l0,' + 3*svgf
		+ ' l-' + 2*svgf + ',0 l0,-' + 3*svgf + '" />';
	}
    }
}

// Mark the edit region with a rectangle
function highlight_phantom(t) {
    var dt, x0, y0;

    svsa = '';
    dt = t - t0_ticks;
    if (0 <= dt && dt <= dt_ticks) {
	x0 = Math.floor(dt*tscl/tickfreq) - svgf;
	y0 = asy0 - 2*svgf;
	svsa = '<path stroke="rgb(0,0,0)" stroke-width="' + lwn
	    + '" stroke-dasharray="2" fill="white" fill-opacity="0.2" d="M'
	    + x0 + ',' + y0 + ' l' + 2*svgf + ',0 l0,' + 3*svgf
	    + ' l-' + 2*svgf + ',0 l0,-' + 3*svgf + '" />';
    }
}

// Select the nearest annotation, if any are close enough to the pointer
function select_ann(e) {
    var dtr, dtf, dt_tol, i;

    selann = -1;
    svgxyt(e.clientX, e.clientY);
    if (editing && selarr && xx_cursor >= -svgf && x_cursor < svgw &&
	asy0 - 2*svgf < y_cursor && y_cursor < asy0 + svgf) {
	dt_tol = Math.round(dt_ticks * 0.012);
	dtr = dtf = dt_tol + 1;
	i = ann_after(selarr, t_cursor);

	if (i > 0) { dtr = t_cursor - selarr[i-1].t; }
	if (i >= 0 && i < selarr.length) { dtf = selarr[i].t - t_cursor; }

	if (dtr < dtf && dtr < dt_tol) { selann = i - 1; }
	else if (dtf < dt_tol) { selann = i; }
    }
    highlight_selection();
}

// Fill the fields of annot by copying those of template
function copy_from_template(annot)
{
    var i;

    annot.a = $('#edita').val();
    i = Number($('#edits').val());
    if (i < -128 || i > 127) { i = 0; $('#edits').val(null); }
    annot.s = i;
    i = Number($('#editc').val());
    if (i < 0    || i > 255) { i = 0; $('#edits').val(null); }
    annot.c = i;
    i = Number($('#editn').val());
    if (i < -128 || i > 127) { i = 0; $('#edits').val(null); }
    annot.n = i;
    annot.x = $('#editx').val();
}

// Fill in the fields of template by copying those of annot
function copy_to_template(annot)
{
    var i;
    $('#edita').val(annot.a);
    i = Number(annot.s);
    if (i < -128 || i > 127) { annot.s = 0; $('#edits').val(null); }
    else { $('#edits').val(annot.s); }
    if (i < 0    || i > 255) { annot.c = 0; $('#editc').val(null); }
    else { $('#editc').val(annot.c); }
    if (i < -128 || i > 127) { annot.n = 0; $('#editn').val(null); }
    else { $('#editn').val(annot.n); }
    $('#editx').val(annot.x);
}

function copy_template_to_palette() {
    var a, f, i, key, x;

    a = $('#edita').val();
    x = $('#editx').val();

    if (a === null || a.length === 0) {
	if (x !== null && x.length > 0) {
	    if (x[0] === '(') { a = '+'; }
	    else { a = '"'; }
	    $('#edita').val(a);
	}
    }
    if (x !== null && x.length > 0) {
	if (a === '+' && x[0] === '(') { key = x; }
	else { key = a + ':' + x; }
    }
    else { key = a; }
    for (i = 0; i < palette.length; i++) {
	if (key === palette[i][0]) { break; }
    }
    if (i >= palette.length) { // add to palette if new
	if (palette[0][1] < 0) {
	    palette[0][0] = key;  // replace unused entry
	}
	else {	// add new entry at head of array
	    palette.unshift([key, -1]);
	    if (palette.length > 20) {
		palette.pop();  // discard last entry if full
	    }
	}
	load_palette(palette);
    }
    else {   // if not new, just select key in palette
	f = seltype.split("_");
	if (i !== f[1]) { // if key not selected already
	    // deselect current selection
	    $(seltype).css("color", "blue")
		.css("background-color", "white");
	    // select chosen entry instead
	    seltype = '#palette_' + i;
	    $(seltype).css("color", "white")
		.css("background-color", "blue");
	}
    }
}

function delete_ann(annot) {
    var i, key;

    if (selarr) {
	i = ann_before(selarr, annot.t);
	if (i >= 0) {
	    if (Number(selarr[i].t) === annot.t) {
		selarr.splice(i, 1);
		selann = -1;
		if (palette) {
		    key = askey(annot);
		    for (i = 0; i < palette.length; i++) {
			if (palette[i][0] === key) {
			    palette[i][1]--;
			    break;
			}
		    }
		}
	    }
	}
	highlight_selection();
    }
}

function insert_ann(annot) {
    var a = {}, i, key;

    if (selarr) {
	a = annot;
	i = ann_after(selarr, annot.t);
	if (i === selarr.length) { selarr[i] = a; }
	else if (i === 0) { selarr.unshift(a); i = 0; }
	else { selarr.splice(i, 0, a); }
	selann = i;
	highlight_selection();

	if (palette) {
	    key = askey(annot);
	    for (i = 0; i < palette.length; i++) {
		if (palette[i][0] === key) {
		    if (palette[i][1] < 0) { palette[i][1] = 1; }
		    else { palette[i][1]++; }
		    break;
		}
	    }
	}
    }
}

function apply_edit(n, applyp) {
    var annot = {}, f, g, h, insertp;

    if (n < 0 || n >= changes.length) { return; }

    annot.a = 'N';
    annot.s = annot.c = annot.n = 0;
    annot.x = null;
    f = changes[n].split(',');
    if (f[0][0] === '-') { insertp = false; annot.t = -f[0]; }
    else if ('0' <= f[0][0] && f[0][0] <= '9') {
	insertp = true; annot.t = +f[0];
    }
    else { return; } // ignore invalid changes[n]
    if (f.length > 1) {
	if (f.length > 2) { annot.x = f.slice(2).join(','); }
	g = f[1].split('{');
	annot.a = g[0];
	if (g.length > 1) {
	    h = g[1].slice(0,-1).split('/');
	    if (h[0]) { annot.s = +h[0]; }
	    if (h[1]) { annot.c = +h[1]; }
	    if (h[2]) { annot.n = +h[2]; }
	}
    }
    if (applyp === false) { insertp = !insertp; }
    if (insertp) { insert_ann(annot); }
    else { delete_ann(annot); }
    show_summary();
}

//-----------------------------------------------------------------------------
// Annotation palette button handlers

// '+' button handler: hide or show add type to palette dialog
function toggle_add_typebox() {
    if (!editing) {
	$('.editgroup').hide();
    }
    else if (nann < 1) {
	alert('No annotations to edit!');
    }
    else if ($('#add_typebox').dialog("isOpen")) {
	$('#add_typebox').dialog("close");
    }
    else {
	$('#add_typebox').dialog("open");
	$('#add_typebox').dialog({
	    width: '650px',
	    height: 'auto',
	    dialogClass: "no-close",
	    buttons: [
		{ text: "Add",
		  click: function() { copy_template_to_palette(); }
		}
	    ]
	});
    }
}

// Copy button handler: copy selarr[selann] to the template and the palette
function copy_sel_to_template() {
    if (selarr && selann >= 0) {
	copy_to_template(selarr[selann]);
	copy_template_to_palette();
    }
}

// Delete button handler
function toggle_insert_mode() {
    if (insert_mode) {
	insert_mode = false;
	$('#insert_mode').css("color", "white").css("background-color", "red")
	    .attr("title", "click to return to insert mode");
    }
    else {
	insert_mode = true;
	$('#insert_mode').css("color", "red").css("background-color", "white")
	    .attr("title", "click to enter delete mode");
    }
}
// Handle clicks on annotation type buttons in annotation palette
function select_type(e) {
    var annot = { a : null, s: null, c: null, n: null, x: null }, f, s;

    $(seltype).css("color", "blue").css("background-color", "white");
    seltype = '#' + e.target.id;
    $(seltype).css("color", "white").css("background-color", "blue");
    s = $(seltype).text();
    f = s.split(":");
    switch (f.length) {
    case 1:
	if (f[0][0] === '(' && f[0].length > 1) {
	    annot.a = '+';
	    annot.x = f[0];
	}
	else { annot.a = f[0]; }
	break;
    case 2:
	annot.a = f[0];
	annot.x = f[1];
	break;
    }
    copy_to_template(annot);
    selkey = s;
}

//-----------------------------------------------------------------------------
// Edit button cluster handlers

// Select the previous annotation
function jump_left() {
    var i, rr, t, t0, x, y;

    t = t0_ticks + x_cursor*tickfreq/tscl;
    i = ann_before(selarr, t);
    if (i >= 0) {
	t = selarr[i].t;
	if (t < t0_ticks) {
	    do {
		t0_ticks -= dt_ticks;
	    } while (t < t0_ticks);
	    go_here(t - dt_ticks/2);
	}
	if (selann === i) {
	    selann = -1;
	    svsa = '';
	}
	else {
	    selann = i;
	    highlight_selection();
	}
    }
    else {
	selann = -1;
	if (selarr.length < 1) { t = 0; }
	else if (selarr.length < 2) {
	    t = selarr[0].t - tickfreq;
	    if (t < 0) { t = 0; }
	}
	else {
	    t0 = selarr[0].t;
	    rr = selarr[1].t - selarr[0].t;
	    if (rr > 1.5 * tickfreq) { rr = 1.5 * tickfreq; }
	    t = t0 - rr;
	    if (t < 0) { t = 0; }
	}
	t = t0 - rr;
	highlight_phantom(t);
    }
    x = Math.floor((t - t0_ticks)*tscl/tickfreq * m.a + m.e);
    y = Math.round(asy0 * m.d + m.f);
    c_velocity = 10;
    show_time(x, y);
}

// Move the edit marker bar incrementally to the left
function nudge_left() {
    var x, y;

    if (c_velocity > 0) { c_velocity = -10; }
    else if (c_velocity > -100) { c_velocity *= 1.1; }
    if (x_cursor > 0) { x_cursor += c_velocity; }
    x = Math.round(x_cursor * m.a + m.e);
    y = Math.round(asy0 * m.d + m.f) - 2*svgf;  // outside the selection box
    show_time(x, y);
}

// Move the edit marker bar incrementally to the right
function nudge_right() {
    var x, y;

    if (c_velocity < 0) { c_velocity = 10; }
    else if (c_velocity < 100) { c_velocity *= 1.1; }
    if (x_cursor < svgw) { x_cursor += c_velocity; }
    x = Math.round(x_cursor * m.a + m.e);
    y = Math.round(asy0 * m.d + m.f) - 2*svgf;  // outside the selection box
    show_time(x, y);
}

// Select the next annotation
function jump_right() {
    var i, rr, t, t0, x, y;

    t = t0_ticks + x_cursor*tickfreq/tscl;
    i = ann_after(selarr, t);
    if (0 <= i && i < selarr.length) {
	t = (selarr.length > 0) ? selarr[i].t : dt_ticks/2;
	if (t > t0_ticks + dt_ticks) { go_here(t - dt_ticks/2); }
	if (selann === i) {
	    selann = -1;
	    svsa = '';
	}
	else {
	    selann = i;
	    highlight_selection();
	}
    }
    else {
	selann = -1;
	t0 = (selarr.length > 0) ? selarr[i-1].t : t0_ticks;
	rr = (selarr.length > 1) ? t0 - selarr[i-2].t : tickfreq;
	if (rr > 1.5*tickfreq) { rr = 1.5*tickfreq; }
	t = t0 + rr;
	if (t > tf_ticks) go_here(t - dt_ticks/2);
	highlight_phantom(t);
    }
    x = Math.ceil((t - t0_ticks)*tscl/tickfreq * m.a + m.e);
    y = Math.round(asy0 * m.d + m.f);
    c_velocity = 10;
    show_time(x, y);
}

// Undo the previous edit
function undo() {
    if (undo_count < changes.length) {
	apply_edit(undo_count++, false);
	$('#redo').removeAttr('disabled');
	if (undo_count >= changes.length) {
	    $('#undo').attr('disabled', 'disabled');
	}
	show_editlog();
	update_output();
    }
}

// Commit the edit (insertion, deletion, move, or change) in progress
function mark(e) {
    var anew, asel = null, dt_tol, in_box = false;

    svgxyt(e.clientX, e.clientY);
    if (!editing || !selarr || xx_cursor < -svgf || x_cursor > svgw) {
	return;
    }
    dt_tol = Math.round(dt_ticks * 0.012);
    if (selann >= 0) {
	asel = selarr[selann];
	if (asy0 - 2*svgf < y_cursor && y_cursor < asy0 + svgf &&
	    asel.t - dt_tol < t_cursor && t_cursor < asel.t + dt_tol) {
	    in_box = true;
	}
    }

    anew = { t: null, a: null, s: null, c: null, n: null, x: null };
    copy_from_template(anew);
    anew.t = Math.round(t_cursor);

    // commit the edit
    if (insert_mode) {
	if (asel === null) {
	    edlog(anew, '+');	// insert new annotation
	}
	else if (in_box) {	// change selected annotation without moving it
	    anew.t = asel.t;	   // copy time of selected annotation
	    edlog(asel, '-');	   // remove selected annotation
	    edlog(anew, '+');	   // insert new annotation at old location
	}
	else if (asel.t !== anew.t) { // move selected annot without changing it
	    edlog(asel, '-');         // remove selected annotation
	    asel.t = anew.t;          // change its location
	    edlog(asel, '+');         // reinsert it
	}
    }
    else if (asel) {
	edlog(asel, '-');	// delete the selected annotation
    }
    else {			// can't delete -- no selection
	alert("Select an annotation to delete it,\n"
	      + "or click on the red button in the\n"
	      + "palette to return to insert mode.\n");
	return;
    }
    update_output();
}

// Redo the previously undone edit
function redo() {
    if (undo_count > 0) {
	apply_edit(--undo_count, true);
	$('#undo').removeAttr('disabled');
	if (undo_count <= 0) {
	    $('#redo').attr('disabled', 'disabled');
	}
	show_editlog();
	update_output();
    }
}

//-----------------------------------------------------------------------------
// Alert functions

// Warn if LightWAVE server is unresponsive/not running/not reachable
function alert_server_error() {
    alert('The LightWAVE server at\n' + server
	  + '\nis not responding properly.  Please check\n'
	  + 'the network connection.  Select another server\n'
	  + 'on the Settings tab if necessary.');
}

function alert_close_warning(){
    if (changes.length > undo_count) {
	save_editlog(db, record, annselected);
	return 'Your pending edits have been saved in local storage only. '
	    + ' If you wish to access them from another browser or computer,'
	    + ' click "Save pending edits" on the Settings tab before'
	    + ' reloading or leaving this page.';
    }
    return null;
}

// Warn if LightWAVE scribe is unresponsive/not running/not reachable
function alert_scribe_error() {
    alert('The LightWAVE scribe at\n' + scribe
	  + '\nis not responding properly.  Please check\n'
	  + 'the network connection.  Select another scribe\n'
	  + 'on the Settings tab if necessary.');
}

//-----------------------------------------------------------------------------
// Edit log functions

// Return true if an edit log exists for the specified record and annotator.
function edits_pending(db, record, annotator) {
    var key, s;

    key = 'LightWAVE-editlog|' + db + '|' + record + '|' + annotator;
    try { s = localStorage.getItem(key); }
    catch (e) { }
    if (s) { return true; }
    return false;
}

// Display the contents of local storage
//  This function is hidden;  to use it, click on "Show pending edit log" on,
//  the Settings tab, then change the database on the Choose input tab.
function show_localstorage() {
    var etext = '', i, key;

    try {
	for (i = 0; i < localStorage.length; i++) {
	    key = localStorage.key(i);
	    if (key.match(/^LightWAVE/)) {
		etext += '<p><b>' + key + '</b>: <pre>'
		    + localStorage.getItem(key) + '</pre><br><hr>';
	    }
	}
    }
    catch (e) {
	etext += '<i>(cannot access local storage)</i>';
    }
    $('#editlog').html(etext);
    etext = '';
}

// If an edit log exists for the specified record and annotator, load its
// contents into changes[].  If redo is true, reapply the changes.
function load_editlog(db, record, annotator, redo) {
    var i, key, n, s;

    key = 'LightWAVE-editlog|' + db + '|' + record + '|' + annotator;
    try { s = localStorage.getItem(key); }
    catch (e) { }
    if (s) {
	changes = s.split("\n");
	changes.pop();  // discard empty element after last '\n' in s
	if (redo) {
	    for (i = changes.length-1; i >= 0; i--) {
		if (changes[i]) { apply_edit(i, true); }
	    }
	}
	$('#redo').attr('disabled', 'disabled');
	$('#undo').removeAttr('disabled');
	undo_count = 0;
    }
    else {
	$('#redo').attr('disabled', 'disabled');
	$('#undo').attr('disabled', 'disabled');
    }
}

// If there are pending edits, save them in localstorage, then reset changes[].
function save_editlog(db, record, annotator) {
    var i, key, s = '';

    if (undo_count < changes.length) {
	key = 'LightWAVE-editlog|' + db + '|' + record + '|' + annotator;
	for (i = undo_count; i < changes.length; i++) {
	    if (changes[i]) { s += changes[i] + '\n'; }
	}
	localStorage.setItem(key, s);
    }
    changes = [];
    undo_count = 0;
}

function remove_editlog(db, record, annselected) {
    key = 'LightWAVE-editlog|' + db + '|' + record + '|' + annselected;
    localStorage.removeItem(key);
}

function edlog(annot, etype) {
    var etext = '', scn;

    if (!annot || annot.t < 0 || !annot.a || annot.a.length < 1
	|| /\s/g.test(annot.a) || (etype !== '+' && etype !== '-')) {
	return;  // check arguments, do nothing if annot or etype is defective
    }
    if (annot.x && annot.x.length > 0) { // fix whitespace in annot.x
	annot.x = annot.x.replace(/\s\s*/g, ' ').replace(/^\s|\s$/g, '');
    }

    if (annot.s || annot.c || annot.n) {
	scn = '{';
	if (annot.s && annot.s !== 0) { scn += annot.s; }
	scn += '/';
	if (annot.c && annot.c !== 0) { scn += annot.c; }
	scn += '/';
	if (annot.n && annot.n !== 0) { scn += annot.n; }
	scn += '}';
    }
    if (etype == '-') { etext = etype; }
    etext += annot.t;
    if (annot.a != 'N' || scn || annot.x) {
	etext += ',' + annot.a;
	if (scn) { etext += scn; }
	if (annot.x) { etext += ',' + annot.x; }
    }
    changes.splice(0, undo_count, etext);
    undo_count = 0;
    show_editlog();
    apply_edit(0, true);
}

function show_editlog() {
    var etext = '', i, n = changes.length;

    if (n > 10) { n = 10; }
    if (undo_count > 0) { etext = '<div style="color: red">'; }
    for (i = 0; i < n; i++) {
	etext += changes[i] + '<br>\n';
	if (i + 1 == undo_count) { etext += '</div>\n'; }
    }
    if (i <= undo_count) { etext += '</div>\n'; }
    $('#editlog').html(etext);
}

//-----------------------------------------------------------------------------
// Handlers for Settings tab

// "View (no editing)/Edit using mouse/Edit using touch" radio button handler
function handle_editmode() {
    if (!editing) { test_sync(); }

    // set state based on edit_mode radio buttons
    if ($('#no_edit').prop('checked')) {
	if (emode === 1) { return; } // do nothing if emode unchanged
	emode = 1;  // view only, no editing
	editing = mouse = false;
	$('.editgroup').hide();
    }
    else if ($('#mouse_edit').prop('checked')) {
	if (emode === 2) { return; }
	emode = 2;  // use mouse/trackball interface for editing
	editing = mouse = true;
	$('.editgroup').show();
    }
    else {
	if (emode === 3) { return; }
	emode = 3;  // use touch interface for editing
	editing = true; mouse = false;
	$('.editgroup').show();
    }

    if (db !== '' && record !== '') {  // return to View/edit tab if record open
	$('#tabs').tabs("option", "active", $('#view').index());
	show_plot();
    }
}

// "Set up new annotation set" handler (also called by read_annotations())
function new_annset() {
    var i, new_ann, new_ann_set, new_ann_array = [], new_summary = [];

    if (!db || !record) {
	alert("Please choose an input before setting up a new annotation set.");
	return;
    }
    new_ann_set = { name: "new", desc: "created using LightWAVE" };
    new_ann = { name: "new", desc: "created using LightWAVE", state: 2,
		annotation: new_ann_array, summary: new_summary };
    if (nann === 0) {
	ann_set[0] = new_ann_set;
	ann[0] = new_ann;
    }
    else {
	if (ann[0].name.substring(0,3) === "new") {
	    if (ann[0].annotation.length > 0) {
		if (ann[0].name.length === 3) { i = 1; }
		else { i = Number(ann[0].name.substring(3)) + 1; }
		if (i > 4) {  // no more than 5 "new" sets per record
		    alert("To create additional annotation sets, sync and"
			  + "rename or delete one or more existing sets.");
		    return;
		}
		new_ann_set.name = new_ann.name = "new" + i;
	    }
	    else { return; }  // don't create another if previous "new" is empty
	}
	ann_set.unshift(new_ann_set);
	ann.unshift(new_ann);
    }
    nann++;
    if (palette) {
	for (i = 0; i < palette.length; i++) {
	    new_ann.summary[i] = [ palette[i][0], -1 ];
	}
    }
    else { new_ann.summary[0] = [ 'N', -1 ]; }
    for (i = 1; i < nann; i++) {
	if (ann[i].state === 2) { ann[i].state = 1; break; }
    }
    ann[0].state = 2;
    if (annselected) {
	save_editlog(db, record, annselected);
    }
    annselected = ann[0].name;
    selarr = ann[0].annotation;
    load_editlog(db, record, annselected, true);
    if (i < nann) {
        summarize(ann[i]);
    }
    load_palette(ann[0].summary);
    ilast = selann = -1;
    svsa = '';
    $('#syncnote').html("Annotation set <b>"
			+ ann[0].name + "</b> has been initialized.");
    $('#tabs').tabs("option", "active", $('#view').index());
    show_plot();
    if (emode === 1) {
	$('#tabs').tabs("option", "active", $('#settings').index());
    }
}

// "Show/hide pending edit log" handler
function toggle_show_edits() {
    $('#editlog').toggle();
    if ($('#editlog').is(":hidden")) {
	$('#show_edits').html("Show pending edit log");
    }
    else {
	$('#show_edits').html("Hide pending edit log");
    }
}

// "Show status" button handler
function toggle_show_status() {
    $('#status').toggle();
    if ($('#status').is(":hidden")) {
	$('#show_status').html("Show status");
    }
    else {
	$('#show_status').html("Hide status");
    }
}

// "Show request log" button handler
function toggle_show_requests() {
    $('#requests').toggle();
    if ($('#requests').is(":hidden")) {
	$('#show_requests').html("Show request log");
    }
    else {
	$('#show_requests').html("Hide request log");
    }
}

// "Reset request log" button handler
function clear_requests() {
    requests = 0; pending = 1;
    rqlog = '';
    show_status(false);
    $('#requests').empty();
}

//-----------------------------------------------------------------------------
// Help tab button handlers

// "Main help" button handler (also called by $(document).ready())
function help() {
    $('#helpframe').attr('src', '/static/lightwave/doc/' + help_main);
}

// "Help topics" button handler
function help_topics() {
    $('#helpframe').attr('src', '/static/lightwave/doc/topics.html');
}

// "Contacts" button handler
function help_contacts() {
    $('#helpframe').attr('src', '/static/lightwave/doc/contacts.html');
}

//-----------------------------------------------------------------------------
// Set up user interface event handlers
function set_handlers() {
    $('#lwform').on("submit", false);      // disable form submission
    $(window).resize(resize_lightwave)
        .on("beforeunload", alert_close_warning);
    // Allow the browser to redraw content from its cache when switching tabs
    // (using jQuery UI 1.9 interface; use 'cache: true' with older jQuery UI)
    $('#tabs').tabs({
	beforeLoad: function(event, ui) {
	    if (ui.tab.data("loaded")) { event.preventDefault(); return; }
	    ui.jqXHR.success(function() { ui.tab.data("loaded", true); });
	},
	activate: function(event, ui) {
	    current_tab = $(ui.newTab).text();
	}
    });

    // Add touch handlers for View/edit tab if on iPad or other touch device.
    if ($.support.touch) {
	$('#view').addTouch();  // see jquery.ui.touch-lw.js
    }

    // Handlers for buttons and other controls:
    //  on View/edit and Tables tabs:
    $('.go_to').on("click", go_to);      // go to selected location

    $('.sor').on("click", gostart);	 // go to start of record
    $('.rev').on("click", gorev);	 // go back by dt_sec and plot or print
    $('.scrollrev').on("click", autoplay_rev); // toggle reverse autoscrolling
    $('.scrollfwd').on("click", autoplay_fwd); // toggle forward autoscrolling
    $('.fwd').on("click", gofwd);	 // advance by dt_sec and plot or print
    $('.eor').on("click", goend);	 // go to end of record

    $('.srev').on("click", srev);	 // search for previous 'Find' target
    $('.find').on("click", find);	 // open/close 'Find' dialog
    $('.sfwd').on("click", sfwd);	 // search for next 'Find' target

    // signal window
    $('.stretch').on("click", stretch_signal); // enlarge selected signal
    $('.reset').on("click", reset_signal);     // reset scale of selected signal
    $('.shrink').on("click", shrink_signal);   // reduce selected signal

    // editgroup buttons
    $('#add_type').on("click", toggle_add_typebox);
    $('#copyann').on("click", copy_sel_to_template);
    $('#insert_mode').on("click", toggle_insert_mode);
    $('#jumpleft').on("click", jump_left);      // select annotation to left
    $('#nudgeleft').on("click", nudge_left);    // move left one increment
    $('#nudgeright').on("click", nudge_right);  // move left one increment
    $('#jumpright').on("click", jump_right);    // select annotation to left
    $('#undo').on("click", undo);    // restore state before most recent edit
    $('#mark').on("click", mark);    // complete the pending edit
    $('#redo').on("click", redo);    // reapply most recent edit

    // Signal window duration slider on View/edit tab
    $(function() {
	$('#dtslider').slider({ value: dt_sec, min: 0, max: 60, step: 5,
	    slide: function(event, ui) {
		if (ui.value < 5) { ui.value = 1; }
		$('#swidth').val(ui.value);
		dt_sec = ui.value;
		if (tickfreq <= 5) { dt_sec *= 60; }
		dt_ticks = dt_sec * tickfreq;
		m = document.getElementById("viewport").getScreenCTM();
		set_sw_width(dt_sec);
		go_here(t0_ticks);
	    }
	});
	$('#swidth').val(dt_sec);
    });

    // disable search buttons until a target has been defined
    $('.sfwd').attr('disabled', 'disabled');
    $('.srev').attr('disabled', 'disabled');

    // disable signal resize buttons until a signal has been selected
    $('.stretch').attr('disabled', 'disabled');
    $('.reset').attr('disabled', 'disabled');
    $('.shrink').attr('disabled', 'disabled');

    // hide edit controls unless editing
    $('.editgroup').hide();

    // Find... dialog box
    $('#findbox').dialog({autoOpen: false});

    // Add type to palette dialog box
    $('#add_typebox').dialog({autoOpen: false});

    // on Settings tab:
    $('[name=server]').on("change", dblist); // use another lightwave server
    $('#show_status').on("click", toggle_show_status);
    $('#show_requests').on("click", toggle_show_requests);
    $('#clear_requests').on("click", clear_requests);
    $("#edit_mode").controlgroup().on("change", handle_editmode);
    $('#new_annset').on("click", new_annset);
    $('#show_edits').on("click", toggle_show_edits);
    $('#sync_edits').on("click", sync_edits);

    // disable editing if localStorage is unavailable
    try { var x = localStorage.length; }
    catch (e) { $('#edit_mode').controlgroup('disable'); }

    // on Help tab:
    $('#helpframe').attr('height', $(window).height() - 180 + 'px');
    $('#help_about').on("click", help);    // return to 'about' (main help doc)
    $('#help_topics').on("click", help_topics);  // show help topics
    $('#help_contacts').on("click", help_contacts); // show contacts
}

// Check for query string in URL, decode and run query or queries if present
function parse_url() {
    var host = '', dblist_text, dbparts, n, q, s, t, title, t0_string, v;

    server = (server || $('[name=default_server]').val());
    scribe = (scribe || $('[name=default_scribe]').val());

    // Set default server and scribe URLs
    if (window.location.protocol === 'file:') {
        host = 'https://physionet.org';
    }
    server = (server || host + '/cgi-bin/lightwave');
    scribe = (scribe || host + '/cgi-bin/lw-scribe');

    s = window.location.href.split("?");
    n = s.length;
    t = 0;
    t0_string = '0';

    $('#client').html('&nbsp;' + s[0]);   // show the client URL
    q = (n > 1 ? s[1] : '').split("&");
    for (n = 0; n < q.length; n++) {
	v = q[n].split("=");
	if (v[0] === 'db') { db = v[1]; }
	else if (v[0] === 'record') { record = v[1]; }
	else if (v[0] === 't0') {  t0_string = v[1]; }
    }

    // Convert relative URLs to absolute
    var a = document.createElement('a');
    a.href = server; server = a.href;
    a.href = scribe; scribe = a.href;

    $('[name=server]').val(server);     // set default server URL
    $('[name=scribe]').val(scribe);     // set default scribe URL
    var i = server.indexOf('?');
    if (i > 0) {
	server_flags = '&' + server.substring(i + 1);
	server = server.substring(0, i);
    }
    else {
	server_flags = '';
    }

    if (db === '') {
	$('#tabs').tabs({disabled:[1,2]});  // disable the View and Tables tabs
	$('#top').show();
	dblist();	// no query, get the list of databases
	return;
    }
    else {
	dbparts = db.split('/');
	if (dbparts.length > 1) { sdb = '.../' + dbparts.pop(); }
	else { sdb = db; }
	if (record === '') {
	    title = 'LightWAVE: ' + sdb;
	    document.title = title;
	    $('#tabs').tabs({disabled:[1,2]});  // disable View and Tables tabs
	    $('#top').show();
	    dblist_text = '<td align=right>Database:</td><td>' + db + '</td>';
	    $('#dblist').html(dblist_text);
	    alist();
	    rlist();
	}
	else {
	    $('#tabs').tabs();
	    // FIXME: when a record is selected via URL parameters,
	    // the 'choose input' tab is not functional.  The old code
	    // had "$('#tabs').tabs("remove",0);" here, which does not
	    // work anymore.  There must be some way to remove or
	    // disable the tab but I have no idea how.
	    title = 'LW: ' + sdb + '/' + record;
	    document.title = title;
	    $('.t0_str').val(t0_string);
	    current_tab = 'View/edit';
	    help_main = 'followed-link.html';
	    $('.recann').html(sdb + '/' + record);
	    dblist =  '<td align=right>Database:</td><td>' + db + '</td>';
	    $('#server').html(server);
	    $('#scribe').html(scribe);
	    $('#dblist').html(dblist);
	    rlist =  '<td align=right>Record:</td><td>' + record +
		'<div id="subrec"></div></td>';
	    $('#rlist').html(rlist);
	    url = server + '?action=alist&db=' + db + server_flags;
	    show_status(true);
	    get_jsonp(url, function(data) {
		if (data.success) { ann_set = data.annotator; }
		else { ann_set = ''; }
		read_annotations(t0_string);
		set_sw_width(dt_sec);
		show_status(false);
	    });
	}
    }
}

// When the page is ready, load the list of databases and set up event handlers.
$(document).ready(function(){
    parse_url();			// handle query string if present
    help();				// load help into the help tab
    set_handlers();			// set UI event handlers
});

}());
