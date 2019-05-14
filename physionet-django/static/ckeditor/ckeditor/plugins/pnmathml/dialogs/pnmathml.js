/**
 * @license Copyright (c) 2003-2019, CKSource - Frederico Knabben. All rights reserved.
 * Copyright (c) 2019 Laboratory for Computational Physiology
 * For licensing, see LICENSE.md or https://ckeditor.com/legal/ckeditor-oss-license
 */

'use strict';

CKEDITOR.dialog.add( 'pnmathml', function( editor ) {

	var preview,
		lang = editor.lang.pnmathml;

	return {
		title: lang.title,
		minWidth: 350,
		minHeight: 100,
		contents: [
			{
				id: 'info',
				elements: [
					{
						id: 'equation',
						type: 'textarea',
						label: lang.dialogInput,

						onLoad: function() {
							var that = this;

							if ( !( CKEDITOR.env.ie && CKEDITOR.env.version == 8 ) ) {
								this.getInputElement().on( 'input', function() {
									// Add \( and \) for preview.
									preview.setValue( that.mathPrefix + that.getInputElement().getValue() + that.mathSuffix );
								} );
							}
						},

						setup: function( widget ) {
							// Remove \( and \).
							var parts = CKEDITOR.plugins.pnmathml.splitInput( widget.data.math );
							this.mathPrefix = parts[ 0 ];
							this.mathSuffix = parts[ 2 ];
							this.setValue( parts[ 1 ] );
						},

						commit: function( widget ) {
							// Add \( and \) to make TeX be parsed by MathJax by default.
							widget.setData( {
								math: this.mathPrefix + this.getValue() + this.mathSuffix,
								mathml: null
							} );
						}
					},
					{
						id: 'documentation',
						type: 'html',
						html:
							'<div style="width:100%;text-align:right;margin:-8px 0 10px">' +
								'<a class="cke_mathjax_doc" href="' + lang.docUrl + '" target="_black" style="cursor:pointer;color:#00B2CE;text-decoration:underline">' +
									lang.docLabel +
								'</a>' +
							'</div>'
					},
					( !( CKEDITOR.env.ie && CKEDITOR.env.version == 8 ) ) && {
						id: 'preview',
						type: 'html',
						html:
							'<div style="width:100%;text-align:center;">' +
								'<iframe style="border:0;width:0;height:0;font-size:20px" scrolling="no" frameborder="0" allowTransparency="true" src="' + CKEDITOR.plugins.pnmathml.fixSrc + '"></iframe>' +
							'</div>',

						onLoad: function() {
							var iFrame = CKEDITOR.document.getById( this.domId ).getChild( 0 );
							preview = new CKEDITOR.plugins.pnmathml.frameWrapper( iFrame, editor );
						},

						setup: function( widget ) {
							preview.setValue( widget.data.math );
						}
					}
				]
			}
		]
	};
} );

/* borrowed from https://github.com/buzinas/ie9-oninput-polyfill */
if ( CKEDITOR.env.ie && CKEDITOR.env.version === 9 ) {
	document.addEventListener( 'selectionchange', function() {
		var el = document.activeElement;
		if ( el.tagName === 'TEXTAREA' || ( el.tagName === 'INPUT' && el.type === 'text' ) ) {
			var ev = document.createEvent( 'CustomEvent' );
			ev.initCustomEvent( 'input', true, true, {} );
			el.dispatchEvent( ev );
		}
	} );
}
