'use strict';

window.newsImageUploadHandler = (blobInfo, progress) => new Promise((resolve, reject) => {
  const xhr = new XMLHttpRequest();
  const url = tinymce.activeEditor.options.get('images_upload_url');
  xhr.open('POST', url);
  const csrfCookie = document.cookie.split('; ')
    .find(c => c.startsWith('csrftoken='));
  if (csrfCookie) {
    xhr.setRequestHeader('X-CSRFToken', csrfCookie.split('=')[1]);
  }
  xhr.onload = () => {
    if (xhr.status === 200) {
      resolve(JSON.parse(xhr.responseText).location);
    } else {
      reject('Upload failed: ' + xhr.status);
    }
  };
  xhr.onerror = () => reject('Upload failed');
  const fd = new FormData();
  fd.append('file', blobInfo.blob(), blobInfo.filename());
  xhr.send(fd);
});
