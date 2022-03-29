const filter = function () {
    let timeout;
    return (url, filters, div = "#searchitems") => {
        clearTimeout(timeout)

        const params = Object.keys(filters).map(key => `${key}=${filters[key]}`).join('&')
        timeout = setTimeout(() => {
            $(div).load(url + "?" + new URLSearchParams(params).toString() + " " + div + ">");
    }, 500);
    }
}()
