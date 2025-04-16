'use strict';

(function() {
    // Tags and attributes used for display within the editor
    const BLOCK_MATH_TAG = 'div';
    const INLINE_MATH_TAG = 'var';
    const MATHML_ATTR = 'data-pnmath-mathml';
    const SOURCE_ATTR = 'data-pnmath-source';
    const INITIAL_ATTR = 'data-pnmath-initial';
    const DISPLAY_ATTR = 'data-pnmath-display';

    let globalStyle = null;

    tinymce.PluginManager.add('pnmath', function(editor, pluginURL) {
        if (!editor.options.isSet('allow_mathml_annotation_encodings')) {
            editor.options.set('allow_mathml_annotation_encodings',
                               ['application/x-tex']);
        }

        // PreInit: establish filters for converting input HTML
        editor.on('PreInit', function() {
            let ser = tinymce.html.Serializer();
            let unsafeParser = new DOMParser();

            // Convert <math> to BLOCK_MATH_TAG / INLINE_MATH_TAG
            editor.parser.addNodeFilter('math', (nodes) => {
                for (let i = 0; i < nodes.length; i++) {
                    let node = nodes[i];

                    let mathml = ser.serialize(node);
                    let display = node.attr('display');
                    if (display !== undefined)
                        display = display.toLowerCase();
                    let tag = (display === 'block'
                               ? BLOCK_MATH_TAG
                               : INLINE_MATH_TAG);

                    let source = null;

                    // The TinyMCE parser (since TinyMCE 7.1.0) treats
                    // math elements as opaque and doesn't provide
                    // access to their descendants.  Instead, use a
                    // DOMParser to parse the annotations.  (This
                    // should be safe since we are simply extracting
                    // the textContent and we never insert the parsed
                    // nodes into the document.)
                    let annotations = unsafeParser.parseFromString(
                        mathml, 'text/html'
                    ).getElementsByTagName('annotation');

                    tinymce.each(annotations, (ann) => {
                        let encoding = ann.getAttribute('encoding');
                        if (encoding === 'application/x-tex') {
                            source = ann.textContent;
                        }
                    });

                    let vnode = tinymce.html.Node.create(tag, {
                        [MATHML_ATTR]: mathml,
                        [SOURCE_ATTR]: source,
                        [DISPLAY_ATTR]: display,
                        [INITIAL_ATTR]: node.attr(INITIAL_ATTR),
                    });
                    let tnode = tinymce.html.Node.create('#text');
                    tnode.value = (source === null ? '...' : source);
                    vnode.append(tnode);
                    node.replace(vnode);
                }
            });
        });

        // SetContent: update elements after editor content is changed
        editor.on('SetContent', function(o) {
            let eqns = editor.dom.select('[' + MATHML_ATTR + ']');
            tinymce.each(eqns, function(eqn) {
                if (eqn.getAttribute('contenteditable') === 'false')
                    return;

                eqn.setAttribute('contenteditable', 'false');

                let mathml = eqn.getAttribute(MATHML_ATTR);
                let source = eqn.getAttribute(SOURCE_ATTR);
                let dblk = (eqn.getAttribute(DISPLAY_ATTR) === 'block');
                let initial = (eqn.getAttribute(INITIAL_ATTR) === '1');

                if (dblk) {
                    eqn.style.display = 'block';
                    eqn.style.marginLeft = '0';
                    eqn.style.marginRight = '0';
                    eqn.style.textAlign = 'center';
                } else {
                    eqn.style.display = 'inline-block';
                }
                eqn.style.fontStyle = 'italic';
                eqn.style.minWidth = '0.5em';
                eqn.style.minHeight = '1em';
                eqn.style.padding = '1px';
                eqn.style.border = '1px dotted currentcolor';
                updateMathContent(eqn, mathml, source, dblk, initial);
            });
        });

        // PreProcess: convert editor content to output HTML
        // (convert BLOCK_MATH_TAG / INLINE_MATH_TAG to <math>)
        editor.on('PreProcess', function(o) {
            let eqns = editor.dom.select('[' + MATHML_ATTR + ']', o.node);
            tinymce.each(eqns, function(eqn) {
                let mathml = eqn.getAttribute(MATHML_ATTR);
                let math = editor.dom.createFragment(mathml);
                editor.dom.replace(math, eqn);
            });
        });

        function updateMathContent(eqn, mathml, source, dblk, initial) {
            // If the "initial" flag is set, equation is newly
            // added/changed.  Try to render immediately so we don't
            // create extra undo levels.
            if (initial && source !== null) {
                if (MATHJAX.callSync(editor, (MathJax) => {
                    try {
                        mathml = MathJax.tex2mml(source, {display: dblk});
                        mathml = addTeXAnnotation(mathml, source);
                        let svg = MathJax.mathml2svg(mathml);
                        setMathSVGContent(eqn, mathml, svg);
                    } catch (err) {
                        console.log('sync tex->svg input: ' + source);
                        console.log('sync tex->svg failed: ' + err.message);
                    }
                })) {
                    return;
                }
            }

            // Otherwise, render asynchronously once MathJax is ready.
            MATHJAX.callLater(editor, (MathJax) => {
                let mathmlPromise = null;
                if (initial) {
                    mathmlPromise = MathJax.tex2mmlPromise(source, {
                        display: dblk,
                    }).then((mathml) => {
                        return addTeXAnnotation(mathml, source);
                    }).catch((err) => {
                        console.log('tex2mml input: ' + source);
                        console.log('tex2mml failed: ' + err.message);
                    });
                } else {
                    mathmlPromise = Promise.resolve(mathml);
                }
                return mathmlPromise.then((mathml) => {
                    return MathJax.mathml2svgPromise(mathml).then((svg) => {
                        silentChange(() => {
                            setMathSVGContent(eqn, mathml, svg);
                        });
                    }).catch((err) => {
                        console.log('mathml2svg input: ' + mathml);
                        console.log('mathml2svg failed: ' + err.message);
                    });
                });
            });
        }

        function setMathSVGContent(eqn, mathml, svg) {
            eqn.setAttribute(MATHML_ATTR, mathml);
            eqn.removeAttribute(INITIAL_ATTR);

            svg = editor.dom.select('svg', svg)[0];

            // add a backdrop so it is visible with selection
            eqn.style.position = 'relative';
            let img = editor.dom.create('img');
            img.src = ('data:image/gif;base64,R0lGODlhAQABAIAAA' +
                       'AAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7');
            img.style.position = 'absolute';
            img.style.top = img.style.left = 0;
            img.style.width = img.style.height = '100%';

            eqn.replaceChildren(img, svg);
            eqn.style.border = 'none';
        }

        function addTeXAnnotation(mathml, source) {
            let dom = editor.dom;
            let math = dom.createFragment(mathml);
            math = dom.select('math', math)[0];
            let semantics = dom.create('semantics');
            if (math.childElementCount === 1) {
                semantics.appendChild(math.firstElementChild);
            } else {
                let mrow = dom.create('mrow');
                while (math.childElementCount > 0)
                    mrow.appendChild(math.firstElementChild);
                semantics.appendChild(mrow);
            }
            let annotation = dom.create('annotation', {
                encoding: 'application/x-tex',
            })
            annotation.appendChild(document.createTextNode(source));
            semantics.appendChild(annotation);
            math.appendChild(semantics);
            return math.outerHTML;
        }

        function initialMathML(source, dblk) {
            let mathml = ('<math ' + (dblk ? 'display="block" ' : ' ') +
                          INITIAL_ATTR + '="1">' +
                          '<merror><mtext>MATH</mtext></merror></math>');
            return addTeXAnnotation(mathml, source);
        }

        function silentChange(callback) {
            if (!editor.undoManager.hasUndo()) {
                callback();
                editor.undoManager.reset();
            } else {
                callback();
            }
        }

        ////////////////////////////////////////////////////////////////
        // Dialog

        function openEditorDialog(default_dblk) {
            let node = editor.selection.getNode();
            let source = node.getAttribute(SOURCE_ATTR);
            let dblk = (node.getAttribute(DISPLAY_ATTR) === 'block');
            let dialogTitle = 'Edit Equation';

            if (source === null) {
                dialogTitle = 'Insert Equation';
                source = editor.selection.getContent({format: 'text'});
                dblk = default_dblk;
            }

            let previewid = editor.dom.uniqueId();
            let previewPending = false;

            function updatePreview(api) {
                let source = api.getData().source.trim();
                let dblk = (api.getData().display === 'block');
                api.setEnabled('save', (source !== ''));

                if (previewPending)
                    return;

                let preview = document.getElementById(previewid);
                preview.style.textAlign = 'center';
                preview.style.minHeight = '2em';

                previewPending = true;
                MATHJAX.callSoon(editor, (MathJax) => {
                    return MathJax.tex2svgPromise(source, {display: dblk});
                }).then((out) => {
                    let svg = editor.dom.select('svg', out)[0];
                    preview.replaceChildren(svg);
                }).catch((err) => {
                    preview.textContent = 'Error: ' + err;
                }).finally(() => {
                    previewPending = false;
                    if (source !== api.getData().source.trim())
                        updatePreview(api);
                });
            }

            let api = editor.windowManager.open({
                title: dialogTitle,
                size: 'medium',
                body: {
                    type: 'panel',
                    items: [{
                        type: 'input',
                        name: 'source',
                        label: 'LaTeX code',
                    }, {
                        type: 'selectbox',
                        name: 'display',
                        label: 'Display style',
                        items: [
                            {value: 'inline', text: 'Inline'},
                            {value: 'block', text: 'Block'},
                        ],
                    }, {
                        type: 'label',
                        label: 'Preview',
                        items: [{
                            type: 'htmlpanel',
                            html: '<div id="' + previewid + '"></div>',
                        }]
                    }],
                },
                buttons: [
                    {type: 'cancel', text: 'Cancel'},
                    {type: 'submit', buttonType: 'primary',
                     name: 'save', text: 'Save'},
                ],
                initialData: {
                    source: source,
                    display: (dblk ? 'block' : 'inline'),
                },
                onChange: updatePreview,
                onSubmit: (api) => {
                    let source = api.getData().source.trim();
                    let dblk = (api.getData().display === 'block');
                    editor.insertContent(initialMathML(source, dblk));
                    api.close();
                },
            });
            updatePreview(api);
        }

        ////////////////////////////////////////////////////////////////
        // Editor commands

        editor.addCommand('InlineMath', (ui, v, w) => {
            let source = editor.selection.getContent({format: 'text'});
            source = source.trim();
            editor.insertContent(initialMathML(source, false));
        });

        editor.addCommand('BlockMath', (ui, v, w) => {
            let source = editor.selection.getContent({format: 'text'});
            source = source.trim();
            editor.insertContent(initialMathML(source, true));
        });

        ////////////////////////////////////////////////////////////////
        // Toolbar button

        editor.ui.registry.addIcon('math', '<svg width="24" height="24"><path d="m8.221 6c-1.619 0.00497-3.045 0.815-3.221 2.133v1.867h1.067c0-1.067 0.3974-2 2.183-2h0.579c-0.2155 4.325-0.4372 5.996-1.332 7.294-0.8863 1.285-1.647 1.618-2.497 1.706v1c1.613-0.1895 2.844-1.067 3.581-2.14 1.188-1.727 1.386-3.964 1.632-7.86h2.442c-0.3318 2.638-0.4742 5.205-0.4193 7.236 0.0243 0.9001 0.2674 1.885 1.019 2.431 0.7856 0.5704 2.584 0.3558 3.259-0.4623 1.084-1.314 1.486-2.373 1.486-4.205h-1c-0.1736 1.587-0.6367 2.98-1.503 2.958-0.5835-0.01479-1.007-0.6616-1.031-1.685-0.0347-1.472 0.09667-3.403 0.5012-6.273h3.033v-2z"/></svg>');

        function isMathSelected() {
            let node = editor.selection.getNode();
            return (node.getAttribute(MATHML_ATTR) !== null);
        }

        editor.ui.registry.addToggleButton('math', {
            icon: 'math',
            tooltip: 'Equation',
            onAction: () => openEditorDialog(false),
            onSetup: (api) => {
                api.setActive(isMathSelected());
                let handler = () => api.setActive(isMathSelected());
                editor.on('nodechange', handler);
                return () => editor.off('nodechange', handler)
            },
        });

        editor.addShortcut('meta+e', 'Equation', () => {
            openEditorDialog(false);
        });

        ////////////////////////////////////////////////////////////////
        // DOM event handlers

        function getEventMathElement(ev) {
            if (ev.target.closest !== undefined)
                return ev.target.closest('[' + MATHML_ATTR + ']');
            return null;
        }

        editor.on('dblclick', function(ev) {
            let eqn = getEventMathElement(ev);
            if (eqn !== null) {
                editor.selection.select(eqn);
                openEditorDialog();
                ev.preventDefault();
            }
        });

        editor.on('keydown', function(ev) {
            if (!ev.shiftKey && !ev.ctrlKey && !ev.altKey && !ev.metaKey
                && ev.key === 'Enter' && isMathSelected()) {
                openEditorDialog();
                ev.preventDefault();
            }
        });

        ////////////////////////////////////////////////////////////////
        // Stylesheets

        editor.contentCSS.push(pluginURL + '/pnmath.css');

        if (globalStyle === null) {
            globalStyle = document.createElement('link');
            globalStyle.type = 'text/css';
            globalStyle.rel = 'stylesheet';
            globalStyle.href = pluginURL + '/pnmath.css';
            document.head.appendChild(globalStyle);
        }

        ////////////////////////////////////////////////////////////////

        return {
            getMetadata: () => ({
                name: 'Math Tags',
                url: 'https://github.com/MIT-LCP/physionet-build',
            })
        };
    });

    ////////////////////////////////////////////////////////////////
    // MathJax loader

    const MATHJAX = {
        initPromise: null,
        queuePromise: null,
        globalMathJax: null,

        load: function(editor) {
            if (this.initPromise === null) {
                this.initPromise = new Promise((resolve, reject) => {
                    let url = editor.getParam('pnmath_mathjax_url');
                    url = url + 'tex-mml-svg.js';
                    console.log('Loading MathJax from ' + url);

                    let wnd = editor.getWin();
                    let doc = editor.getDoc();
                    wnd.MathJax = {
                        loader: {
                            load: ['ui/safe'],
                        },
                        startup: {
                            pageReady: () => {
                                console.log('MathJax loaded');
                                this.globalMathJax = wnd.MathJax;
                                resolve(wnd.MathJax);
                            },
                        },
                    };
                    let script = doc.createElement('script');
                    script.type = 'text/javascript';
                    script.src = url;
                    script.async = true;
                    script.onerror = () => {
                        reject('Failed to load script ' + url);
                    };
                    doc.head.appendChild(script);
                });
            }
            return this.initPromise;
        },

        callSync: function(editor, callback) {
            if (this.globalMathJax === null) {
                return false;
            } else {
                callback(this.globalMathJax);
                return true;
            }
        },

        callSoon: function(editor, callback) {
            return this.load(editor).then(callback);
        },

        callLater: function(editor, callback) {
            if (this.queuePromise === null)
                this.queuePromise = Promise.resolve();
            this.queuePromise = this.queuePromise.then(() => {
                return this.load(editor).then(callback).catch((err) => {
                    console.log('Error in MATHJAX.callLater: ' + err);
                });
            });
            return this.queuePromise;
        },
    }
})();
