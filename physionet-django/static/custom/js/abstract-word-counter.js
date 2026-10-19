// Live word counter for the Abstract field's TinyMCE editor.
var ABSTRACT_WORD_LIMIT = 250;

function countWords(html) {
    var text = html.replace(/<[^>]+>/g, ' ');
    var matches = text.match(/\S+/g);
    return matches ? matches.length : 0;
}

function updateAbstractWordCount(editor, counterEl) {
    var count = countWords(editor.getContent());
    counterEl.textContent = count + ' / ' + ABSTRACT_WORD_LIMIT + ' words';
    counterEl.style.color = count > ABSTRACT_WORD_LIMIT ? '#a94442' : '#6c757d';
}

function attachAbstractWordCounter(editor) {
    var counterEl = document.createElement('div');
    counterEl.style = 'text-align: right; font-size: 0.85em; margin-top: 4px;';
    editor.getContainer().insertAdjacentElement('afterend', counterEl);

    editor.on('input change undo redo setcontent', function () {
        updateAbstractWordCount(editor, counterEl);
    });

    updateAbstractWordCount(editor, counterEl);
}

function initAbstractWordCounter() {
    var editor = window.tinymce && window.tinymce.get('id_abstract');
    if (!editor) {
        setTimeout(initAbstractWordCounter, 200);
        return;
    }

    if (editor.initialized) {
        attachAbstractWordCounter(editor);
    } else {
        editor.on('init', function () {
            attachAbstractWordCounter(editor);
        });
    }
}

document.addEventListener('DOMContentLoaded', initAbstractWordCounter);
