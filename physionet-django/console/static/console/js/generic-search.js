const search = function () {
    let timeout;
    return (url, value, div = "#searchitems") => {
        clearTimeout(timeout)
        timeout = setTimeout(() => {
            $(div).load(url + "?&search=" + encodeURIComponent(value) + " " + div + ">");
    }, 500);
    }
}()