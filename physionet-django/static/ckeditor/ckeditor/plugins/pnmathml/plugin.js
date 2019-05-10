/**
 * @license Copyright (c) 2003-2019, CKSource - Frederico Knabben. All rights reserved.
 * Copyright (c) 2019 Laboratory for Computational Physiology
 * For licensing, see LICENSE.md or https://ckeditor.com/legal/ckeditor-oss-license
 */

/**
 * @fileOverview This plugin allows inserting equations, which are created and
 * edited using LaTeX syntax, and saved as MathML.  It is based on the official
 * [Mathematical Formulas](https://ckeditor.com/cke4/addon/mathjax) plugin.
 */

'use strict';

( function() {
	CKEDITOR.plugins.add( 'pnmathml', {
		// jscs:disable maximumLineLength
		lang: 'en', // %REMOVE_LINE_CORE%
		// jscs:enable maximumLineLength
		requires: 'widget,dialog',
		icons: 'inlineEquation,blockEquation',
		hidpi: true, // %REMOVE_LINE_CORE%

		init: function( editor ) {
			if ( !editor.config.mathJaxLib ) {
				CKEDITOR.error( 'mathjax-no-config' );
			}

			editor.widgets.add( 'inlineEquation', {
				inline: true,
				dialog: 'pnmathml',
				button: editor.lang.pnmathml.inlineButton,
				mask: true,

				// FIXME: this is incomplete
				allowedContent: 'span,math,semantics,annotation[encoding]',

				requiredContent: 'math',

				pathName: editor.lang.pnmathml.pathName,

				template: '<span style="display:inline-block" data-cke-survive=1></span>',

				parts: {
					span: 'span'
				},

				defaults: function() {
					return CKEDITOR.plugins.pnmathml.widgetDefaults( editor, false );
				},

				init: function() {
					CKEDITOR.plugins.pnmathml.widgetInit( this, editor, false );
				},

				data: function() {
					if ( this.frameWrapper )
						this.frameWrapper.setValue( this.data.math, this.data.mathml );
				},

				upcast: function( el, data ) {
					return CKEDITOR.plugins.pnmathml.widgetUpcast( el, data, false );
				},

				downcast: function( el ) {
					return CKEDITOR.plugins.pnmathml.widgetDowncast( this, editor, el, false );
				}
			} );

			editor.widgets.add( 'blockEquation', {
				inline: false,
				dialog: 'pnmathml',
				button: editor.lang.pnmathml.blockButton,
				mask: true,

				// FIXME: this is incomplete
				allowedContent: 'div,math[display],semantics,annotation[encoding]',

				requiredContent: 'math[display]',

				pathName: editor.lang.pnmathml.pathName,

				template: '<div style="text-align:center" data-cke-survive=1></div>',

				parts: {
					span: 'div'
				},

				defaults: function() {
					return CKEDITOR.plugins.pnmathml.widgetDefaults( editor, true );
				},

				init: function() {
					CKEDITOR.plugins.pnmathml.widgetInit( this, editor, true );
				},

				data: function() {
					if ( this.frameWrapper )
						this.frameWrapper.setValue( this.data.math, this.data.mathml );
				},

				upcast: function( el, data ) {
					return CKEDITOR.plugins.pnmathml.widgetUpcast( el, data, true );
				},

				downcast: function( el ) {
					return CKEDITOR.plugins.pnmathml.widgetDowncast( this, editor, el, true );
				}
			} );

			// Add dialog.
			CKEDITOR.dialog.add( 'pnmathml', this.path + 'dialogs/pnmathml.js' );

			// Add MathJax script to page preview.
			editor.on( 'contentPreview', function( evt ) {
				evt.data.dataValue = evt.data.dataValue.replace(
					/<\/head>/,
					'<script src="' + CKEDITOR.getUrl( editor.config.mathJaxLib ) + '"><\/script><\/head>'
				);
			} );

			editor.on( 'paste', function( evt ) {
				// Firefox does remove iFrame elements from pasted content so this event do the same on other browsers.
				// Also iFrame in paste content is reason of "Unspecified error" in IE9 (https://dev.ckeditor.com/ticket/10857).
				var regex = new RegExp( '<iframe[^>]*?' + '.*?<\/iframe>', 'ig' );
				evt.data.dataValue = evt.data.dataValue.replace( regex, '' );
			} );
		}
	} );

	/**
	 * @private
	 * @singleton
	 * @class CKEDITOR.plugins.pnmathml
	 */
	CKEDITOR.plugins.pnmathml = {};

	/**
	 * Determine default values for widget.
	 *
	 * @private
	 * @param {CKEDITOR.editor} editor The current editor.
	 * @param {Boolean} blockStyle True if widget is "block" style.
	 * @returns {Object} Default values for widget data.
	 */
	CKEDITOR.plugins.pnmathml.widgetDefaults = function( editor, blockStyle ) {
		// If any text is currently selected, use that as the default TeX expression.
		var sel = editor.getSelection(), text = null;
		if ( sel )
			text = sel.getSelectedText();

		text = ( text || 'x^2' );
		if ( blockStyle )
			text = '\\[' + text + '\\]';
		else
			text = '\\(' + text + '\\)';

		return {
			math: text,
			mathml: null
		};
	};

	/**
	 * Widget initialization.
	 *
	 * @private
	 * @param {CKEDITOR.plugins.widget} widget New widget to initialize.
	 * @param {CKEDITOR.editor} editor The current editor.
	 * @param {Boolean} blockStyle True if widget is "block" style.
	 */
	CKEDITOR.plugins.pnmathml.widgetInit = function( widget, editor, blockStyle ) {
		var iframe = widget.parts.span.getChild( 0 );

		// Check if span contains iframe and create it otherwise.
		if ( !iframe || iframe.type != CKEDITOR.NODE_ELEMENT || !iframe.is( 'iframe' ) ) {
			if ( iframe )
				widget.parts.span.setHtml( '' );
			iframe = new CKEDITOR.dom.element( 'iframe' );
			iframe.setAttributes( {
				style: 'border:0;width:0;height:0',
				scrolling: 'no',
				frameborder: 0,
				allowTransparency: true,
				src: CKEDITOR.plugins.pnmathml.fixSrc
			} );
			widget.parts.span.append( iframe );
		}

		// Wait for ready because on some browsers iFrame will not
		// have document element until it is put into document.
		// This is a problem when you crate widget using dialog.
		widget.once( 'ready', function() {
			// Src attribute must be recreated to fix custom domain error after undo
			// (see iFrame.removeAttribute( 'src' ) in frameWrapper.load).
			if ( CKEDITOR.env.ie )
				iframe.setAttribute( 'src', CKEDITOR.plugins.pnmathml.fixSrc );

			this.frameWrapper = new CKEDITOR.plugins.pnmathml.frameWrapper( iframe, editor, !blockStyle, function( mml ) {
				if ( !widget.data.mathml )
					widget.newMathML = mml;
			} );
			this.frameWrapper.setValue( this.data.math, this.data.mathml );
		} );
	};

	/**
	 * Widget upcasting.
	 *
	 * @private
	 * @param {CKEDITOR.htmlParser.node} el Element to check for castability.
	 * @param {Object} data Object in which to store widget data values.
	 * @param {Boolean} blockStyle True if upcasting to a "block" widget.
	 */
	CKEDITOR.plugins.pnmathml.widgetUpcast = function( el, data, blockStyle ) {
		var math = null, semantics = null;

		if ( blockStyle ) {
			if ( el.name === 'math' && el.attributes[ 'display' ] === 'block' )
				math = el;
			else {
				if ( el.name !== 'div' )
					return;
				for ( var i = 0; i < el.children.length; i++ ) {
					var c = el.children[ i ];
					if ( c.type === CKEDITOR.NODE_ELEMENT && c.name === 'math' && math === null )
						math = c;
					else if ( !CKEDITOR.plugins.pnmathml.isWhitespace( c ) )
						return;
				}
				if ( math === null || math.attributes[ 'display' ] !== 'block' )
					return;
			}
		}
		else {
			if ( el.name !== 'math' || el.attributes[ 'display' ] === 'block' )
				return;
			math = el;
		}

		for ( var i = 0; i < math.children.length; i++ ) {
			var c = math.children[ i ];
			if ( c.type === CKEDITOR.NODE_ELEMENT && c.name === 'semantics' && semantics === null )
				semantics = c;
			else if ( !CKEDITOR.plugins.pnmathml.isWhitespace( c ) )
				return;
		}
		if ( semantics === null )
			return;

		for ( var i = 0; i < semantics.children.length; i++ ) {
			var c = semantics.children[ i ];
			if ( c.type === CKEDITOR.NODE_ELEMENT && c.name === 'annotation' && c.attributes[ 'encoding' ] === 'application/x-tex' ) {
				if ( c.children.length !== 1 || c.children[ 0 ].type !== CKEDITOR.NODE_TEXT )
					return;

				if ( blockStyle ) {
					data.math = '\\[' + CKEDITOR.tools.htmlDecode( c.children[ 0 ].value ) + '\\]';
					data.mathml = math.getOuterHtml();

					el.name = 'div';
					el.setHtml( '' );
					el.attributes = {
						'style': 'text-align:center',
						'data-cke-survive': 1
					};
				}
				else {
					data.math = '\\(' + CKEDITOR.tools.htmlDecode( c.children[ 0 ].value ) + '\\)';
					data.mathml = math.getOuterHtml();

					el.name = 'span';
					el.setHtml( '' );
					el.attributes = {
						'style': 'display:inline-block',
						'data-cke-survive': 1
					};
				}
				return el;
			}
		}
	};

	/**
	 * Widget downcasting.
	 *
	 * @private
	 * @param {CKEDITOR.plugins.widget} widget Widget to downcast.
	 * @param {CKEDITOR.editor} editor The current editor.
	 * @param {CKEDITOR.htmlParser.node} el Widget's main element.
	 * @param {Boolean} blockStyle True if widget is "block" style.
	 */
	CKEDITOR.plugins.pnmathml.widgetDowncast = function( widget, editor, el, blockStyle ) {
		var mathml = ( widget.data.mathml || widget.newMathML );
		if ( !mathml ) {
			var src = CKEDITOR.plugins.pnmathml.trim( CKEDITOR.tools.htmlEncode( widget.data.math ) );
			var attr = ( blockStyle ? ' display="block"' : '' );
			mathml =
				'<math xmlns="http://www.w3.org/1998/Math/MathML"' + attr + '>' +
					'<semantics>' +
						'<merror><mtext>ERROR</mtext></merror>' +
						'<annotation encoding="application/x-tex">' + src + '</annotation>' +
					'</semantics>' +
				'</math>';
		}
		if ( blockStyle )
			mathml = '<div>' + mathml + '</div>';
		var math = CKEDITOR.htmlParser.fragment.fromHtml( mathml );
		editor.filter.applyTo( math );
		el.replaceWith( math );
		return math;
	};

	/**
	 * A variable to fix problems with `iframe`. This variable is global
	 * because it is used in both the widget and the dialog window.
	 *
	 * @private
	 * @property {String} fixSrc
	 */
	CKEDITOR.plugins.pnmathml.fixSrc =
		// In Firefox src must exist and be different than about:blank to emit load event.
		CKEDITOR.env.gecko ? 'javascript:true' : // jshint ignore:line
		// Support for custom document.domain in IE.
		CKEDITOR.env.ie ? 'javascript:' + // jshint ignore:line
						'void((function(){' + encodeURIComponent(
							'document.open();' +
							'(' + CKEDITOR.tools.fixDomain + ')();' +
							'document.close();'
						) + '})())' :
		// In Chrome src must be undefined to emit load event.
						'javascript:void(0)'; // jshint ignore:line

	/**
	 * Loading indicator image generated by http://preloaders.net.
	 *
	 * @private
	 * @property {String} loadingIcon
	 */
	CKEDITOR.plugins.pnmathml.loadingIcon = CKEDITOR.plugins.get( 'pnmathml' ).path + 'images/loader.gif';

	/**
	 * Computes predefined styles and copies them to another element.
	 *
	 * @private
	 * @param {CKEDITOR.dom.element} from Copy source.
	 * @param {CKEDITOR.dom.element} to Copy target.
	 */
	CKEDITOR.plugins.pnmathml.copyStyles = function( from, to ) {
		var stylesToCopy = [ 'color', 'font-family', 'font-style', 'font-weight', 'font-variant', 'font-size' ];

		for ( var i = 0; i < stylesToCopy.length; i++ ) {
			var key = stylesToCopy[ i ],
				val = from.getComputedStyle( key );
			if ( val )
				to.setStyle( key, val );
		}
	};

	/**
	 * Checks if a node is either an HTML comment, or a text node
	 * containing only whitespace characters.
	 *
	 * @private
	 * @param {CKEDITOR.htmlParser.node} el An HTML parser node.
	 * @returns {Boolean} True if node contains only whitespace.
	 */
	CKEDITOR.plugins.pnmathml.isWhitespace = function( el ) {
		if ( el.type === CKEDITOR.NODE_TEXT )
			return !( /\S/.test( el.value ) );
		else
			return ( el.type === CKEDITOR.NODE_COMMENT );
	};

	/**
	 * Splits a MathJax input string, such as '\(1+1=2\)', into the
	 * prefix '\(', expression '1+1=2', and suffix '\)'.
	 *
	 * @private
	 * @param {String} value Input string.
	 * @returns {Array} Array of three strings: prefix, expression, and suffix.
	 */
	CKEDITOR.plugins.pnmathml.splitInput = function( value ) {
		var start = value.substring( 0, 2 );
		var end = value.substring( value.length - 2 );

		if ( ( start === '\\(' && end === '\\)' ) || ( start === '\\[' && end === '\\]' ) )
			return [ start, value.substring( 2, value.length - 2 ), end ];
		else
			throw "unexpected value: " + value;
	}

	/**
	 * Trims MathJax value from '\(1+1=2\)' to '1+1=2'.
	 *
	 * @private
	 * @param {String} value String to trim.
	 * @returns {String} Trimed string.
	 */
	CKEDITOR.plugins.pnmathml.trim = function( value ) {
		var parts = CKEDITOR.plugins.pnmathml.splitInput( value );
		return parts[ 1 ];
	};

	/**
	 * FrameWrapper is responsible for communication between the MathJax library
	 * and the `iframe` element that is used for rendering mathematical formulas
	 * inside the editor.
	 * It lets you create visual mathematics by using the
	 * {@link CKEDITOR.plugins.pnmathml.frameWrapper#setValue setValue} method.
	 *
	 * @private
	 * @class CKEDITOR.plugins.pnmathml.frameWrapper
	 * @constructor Creates a class instance.
	 * @param {CKEDITOR.dom.element} iFrame The `iframe` element to be wrapped.
	 * @param {CKEDITOR.editor} editor The editor instance.
	 * @param {Boolean} inline True to align the frame with the text baseline.
	 * @param {Function} callback Function to call with converted MathML syntax.
	 */
	if ( !( CKEDITOR.env.ie && CKEDITOR.env.version == 8 ) ) {
		CKEDITOR.plugins.pnmathml.frameWrapper = function( iFrame, editor, inline, callback ) {

			var buffer, preview, base, value, newValue,
				doc = iFrame.getFrameDocument(),

				// Is MathJax loaded and ready to work.
				isInit = false,

				// Is MathJax parsing Tex.
				isRunning = false,

				// Function called when MathJax is loaded.
				loadedHandler = CKEDITOR.tools.addFunction( function() {
					preview = doc.getById( 'preview' );
					base = doc.getById( 'base' );
					buffer = doc.getById( 'buffer' );
					isInit = true;

					if ( newValue )
						update();

					// Private! For test usage only.
					CKEDITOR.fire( 'mathJaxLoaded', iFrame );
				} ),

				// Function called when MathJax finish his job.
				updateDoneHandler = CKEDITOR.tools.addFunction( function( mml ) {
					CKEDITOR.plugins.pnmathml.copyStyles( iFrame, preview );

					preview.setHtml( buffer.getHtml() );

					editor.fire( 'lockSnapshot' );

					iFrame.setStyles( {
						height: 0,
						width: 0
					} );

					// Set iFrame dimensions.
					var height = Math.max( doc.$.body.offsetHeight, doc.$.documentElement.offsetHeight ),
						width = Math.max( preview.$.offsetWidth, doc.$.body.scrollWidth ),
						align = 'middle';

					if ( inline ) {
						var ascent = base.$.offsetTop + base.$.offsetHeight;
						align = ( ascent - height ) + 'px';
					}

					iFrame.setStyles( {
						'vertical-align': align,
						height: height + 'px',
						width: width + 'px'
					} );

					editor.fire( 'unlockSnapshot' );

					// Private! For test usage only.
					CKEDITOR.fire( 'mathJaxUpdateDone', iFrame );

					// If value changed in the meantime update it again.
					if ( value != newValue )
						update();
					else {
						if ( mml && callback )
							callback( mml );
						isRunning = false;
					}
				} );

			iFrame.on( 'load', load );

			load();

			function load() {
				doc = iFrame.getFrameDocument();

				if ( doc.getById( 'preview' ) )
					return;

				// Because of IE9 bug in a src attribute can not be javascript
				// when you undo (https://dev.ckeditor.com/ticket/10930). If you have iFrame with javascript in src
				// and call insertBefore on such element then IE9 will see crash.
				if ( CKEDITOR.env.ie )
					iFrame.removeAttribute( 'src' );

				doc.write( '<!DOCTYPE html>' +
							'<html>' +
							'<head>' +
								'<meta charset="utf-8">' +
								'<script type="text/x-mathjax-config">' +

									// MathJax configuration, disable messages.
									'MathJax.Hub.Config( {' +
										'menuSettings: { semantics: true },' +
										'showMathMenu: false,' +
										'messageStyle: "none"' +
									'} );' +

									// Get main CKEDITOR form parent.
									'function getCKE() {' +
										'if ( typeof window.parent.CKEDITOR == \'object\' ) {' +
											'return window.parent.CKEDITOR;' +
										'} else {' +
											'return window.parent.parent.CKEDITOR;' +
										'}' +
									'}' +

									// Asynchronously convert equation to MathML.  This code is adapted from the
									// MathJax docs, but note that jax must be passed as the second argument to
									// jax.root.toMathML, in order to generate semantics/annotation tags.
									'function getMathML( jax, callback ) {' +
										'var mml;' +
										'try {' +
											'mml = jax.root.toMathML( "", jax );' +
										'} catch( err ) {' +
											'if ( !err.restart ) {' +
												'throw err;' +
											'}' +
											'return MathJax.Callback.After( [ getMathML, jax, callback ], err.restart );' +
										'}' +
										'MathJax.Callback( callback )( mml );' +
									'}' +

									// Run MathJax.Hub with its actual parser and call callback function after that.
									// Because MathJax.Hub is asynchronous create MathJax.Hub.Queue to wait with callback.
									'function update() {' +
										'MathJax.Hub.Queue(' +
											'[ \'Typeset\', MathJax.Hub, this.buffer ],' +
											'function() {' +
												'var jax = MathJax.Hub.getAllJax()[ 0 ];' +
												'if ( jax ) {' +
													'getMathML( jax, function( mml ) {' +
														'getCKE().tools.callFunction( ' + updateDoneHandler + ', mml );' +
													'} );' +
												'}' +
												'else {' +
													'getCKE().tools.callFunction( ' + updateDoneHandler + ', null );' +
												'}' +
											'}' +
										');' +
									'}' +

									// Run MathJax for the first time, when the script is loaded.
									// Callback function will be called then it's done.
									'MathJax.Hub.Queue( function() {' +
										'getCKE().tools.callFunction(' + loadedHandler + ');' +
									'} );' +
								'</script>' +

								// Load MathJax lib.
								'<script src="' + ( editor.config.mathJaxLib ) + '"></script>' +
							'</head>' +
							'<body style="padding:0;margin:0;background:transparent;overflow:hidden;white-space:nowrap">' +
								( inline ? '<span id="base" style="display:inline-block;height:1px"></span>' : '' ) +
								'<span id="preview"></span>' +

								// Render everything here and after that copy it to the preview.
								'<span id="buffer" style="display:none"></span>' +
							'</body>' +
							'</html>' );
			}

			// Run MathJax parsing Tex.
			function update() {
				isRunning = true;

				value = newValue;

				editor.fire( 'lockSnapshot' );

				buffer.setHtml( value );

				// Set loading indicator.
				preview.setHtml( '<img src=' + CKEDITOR.plugins.pnmathml.loadingIcon + ' alt=' + editor.lang.pnmathml.loading + '>' );

				iFrame.setStyles( {
					height: '16px',
					width: '16px',
					display: 'inline',
					'vertical-align': 'middle'
				} );

				editor.fire( 'unlockSnapshot' );

				// Run MathJax.
				doc.getWindow().$.update( value );
			}

			return {
				/**
				 * Sets the TeX value to be displayed in the `iframe` element inside
				 * the editor. This function will activate the MathJax
				 * library which interprets TeX expressions and converts them into
				 * their representation that is displayed in the editor.
				 *
				 * @param {String} value TeX string.
				 */
				setValue: function( texValue, mathmlValue ) {
					newValue = ( mathmlValue || CKEDITOR.tools.htmlEncode( texValue ) );

					if ( isInit && !isRunning )
						update();
				}
			};
		};
	} else {
		// In IE8 MathJax does not work stable so instead of using standard
		// frame wrapper it is replaced by placeholder to show pure TeX in iframe.
		CKEDITOR.plugins.pnmathml.frameWrapper = function( iFrame, editor, inline, callback ) {
			iFrame.getFrameDocument().write( '<!DOCTYPE html>' +
				'<html>' +
				'<head>' +
					'<meta charset="utf-8">' +
				'</head>' +
				'<body style="padding:0;margin:0;background:transparent;overflow:hidden">' +
					'<span style="white-space:nowrap;" id="tex"></span>' +
				'</body>' +
				'</html>' );

			return {
				setValue: function( texValue, mathmlValue ) {
					var doc = iFrame.getFrameDocument(),
						tex = doc.getById( 'tex' );

					tex.setHtml( CKEDITOR.plugins.pnmathml.trim( CKEDITOR.tools.htmlEncode( texValue ) ) );

					CKEDITOR.plugins.pnmathml.copyStyles( iFrame, tex );

					editor.fire( 'lockSnapshot' );

					iFrame.setStyles( {
						width: Math.min( 250, tex.$.offsetWidth ) + 'px',
						height: doc.$.body.offsetHeight + 'px',
						display: 'inline',
						'vertical-align': 'middle'
					} );

					editor.fire( 'unlockSnapshot' );
				}
			};
		};
	}
} )();

/**
 * Sets the path to the MathJax library. It can be both a local resource and
 * a location different than the default CDN. For correct operation, the
 * specified configuration must support both TeX and MathML input.
 *
 * Please note that this must be a full or absolute path.
 *
 * Read more in the {@glink guide/dev_mathjax documentation}
 * and see the {@glink examples/mathjax example}.
 *
 *		config.mathJaxLib = '//cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.4/MathJax.js?config=TeX-AMS-MML_HTMLorMML';
 *
 * **Note:** Since CKEditor 4.5 this option does not have a default value, so it must
 * be set in order to enable the MathJax plugin.
 *
 * @since 4.3
 * @cfg {String} mathJaxLib
 * @member CKEDITOR.config
 */
