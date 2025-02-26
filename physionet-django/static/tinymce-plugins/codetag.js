tinymce.PluginManager.add('codetag', function(editor, url) {
    editor.ui.registry.addIcon('codetag', '<svg width="24" height="24"><rect x="8" y="6.75" width="2" height="10.5" ry=".75"/><rect x="9.75" y="17" width="5.5" height="2" ry=".75"/><rect x="15" y="6.75" width="2" height="2.5" ry=".75"/><rect x="9.75" y="5" width="5.5" height="2" ry=".75"/><rect x="15" y="14.75" width="2" height="2.5" ry=".75"/></svg>');

    editor.ui.registry.addToggleButton('codetag', {
        icon: 'codetag',
        tooltip: 'Code',
        onAction: (_) => editor.execCommand('mceToggleFormat', false, 'code'),
        onSetup: (api) => {
            api.setActive(editor.formatter.match('code'));
            const changed = editor.formatter.formatChanged('code', (state) => api.setActive(state));
            return () => changed.unbind();
        }
    });

    editor.addShortcut('meta+d', 'Code', () => {
        editor.execCommand('mceToggleFormat', false, 'code');
    });

    return {
        getMetadata: () => ({
            name: 'Code Tags',
            url: 'https://github.com/MIT-LCP/physionet-build',
        })
    };
});
