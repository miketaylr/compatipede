import cairo
import difflib
import os
import time
import sys

from gi.repository import GLib
from gi.repository import Gtk
from gi.repository import WebKit

from abpy import Filter


adblock = Filter()

if not os.path.exists('screenshots'):
    os.makedirs('screenshots')

IOS_UA = 'Mozilla/5.0 (iPhone; U; CPU iPhone OS 4_3_2 like Mac OS X; en-us) AppleWebKit/533.17.9 (KHTML, like Gecko) Version/5.0.2 Mobile/8H7 Safari/6533.18.5'
FOS_UA = 'Mozilla/5.0 (Mobile; rv:18.0) Gecko/18.0 Firefox/18.0'

SIMPLFY_SCRIPT = """
function removeAttr(attr){
    var xpElms = document.evaluate('//*[@'+attr+']', document.documentElement, null, XPathResult.UNORDERED_NODE_SNAPSHOT_TYPE, null );
    var elm;
    for(var i=0; elm = xpElms.snapshotItem(i); i++){
        elm.removeAttribute(attr)
    }
}
removeAttr('href');
removeAttr('src');
removeAttr('value');
// remove <!-- comment --> and text nodes
var xpElms = document.evaluate('//comment()|//text()', document.documentElement, null, XPathResult.UNORDERED_NODE_SNAPSHOT_TYPE, null );
for(var i=0; elm = xpElms.snapshotItem(i); i++){
    if(!(elm.parentElement.tagName in {'SCRIPT':1,'STYLE':1}))
        elm.parentElement.removeChild(elm)
}
"""


def wait(timeout=15):
    t = time.time()
    if timeout == -1:
        timeout = sys.maxint
    while time.time() - t < timeout:
        Gtk.main_iteration_do(True)


class Tab(WebKit.WebView):

    def __init__(self, uri, user_agent="", tab_type=""):
        WebKit.WebView.__init__(self)
        self.window = window = Gtk.Window()
        window.set_size_request(540, 960)
        scrolled_window = Gtk.ScrolledWindow()
        window.add(scrolled_window)
        #window.add(self)
        scrolled_window.add(self)
        window.show_all()

        self._filter = adblock
        self._uri = uri
        self._user_agent = user_agent
        self._tab_type = tab_type
        self._doms = []
        self._subframes = []
        self._settings = self.get_settings()

        self.connect('frame-created', self._on_frame_created)
        self.connect('resource-request-starting',
                     self._on_resource_request_starting)

        self.set_user_agent(user_agent)
        self.load_uri(uri)
        self.set_title("%s %s" % (tab_type, uri))

    def close(self):
        self.window.destroy()

    def set_title(self, title):
        self.window.set_title(title)

    @property
    def document(self):
        return self.get_dom_document()

    @property
    def doms(self):
        return [frame.get_dom_document() for frame in self.frames]

    @property
    def frames(self):
        self._subframes = filter(lambda f: f.get_parent() is not None,
                                 self._subframes)
        return set([self.get_main_frame()] + self._subframes)

    def _on_frame_created(self, view, frame):
        self._subframes.append(frame)

    def _on_resource_request_starting(self, view, frame, resource,
                                      request, response):
        uri = request.get_uri()
        if self._filter.match(uri):
            request.set_uri("about:blank")
            elements = self._find_element_all('[src="%s"]' % uri)
            for element in elements:
                element.get_style().set_property("display", "none", "high")
                #element.get_parent_element().remove_child(element)

    def _get_element_by_id(self, element, dom=None):
        doms = [dom] if dom else self.doms
        elements = []
        for dom in doms:
            res = dom.get_element_by_id(element)
            if res:
                elements.append(res)
        return elements

    def _get_element_by_class_name(self, element, dom=None):
        doms = [dom] if dom else self.doms
        elements = []
        for dom in doms:
            res = dom.get_elements_by_class_name(element)
            elements += [res.item(i) for i in xrange(res.get_length())]
        return elements

    def _get_element_by_name(self, element, dom=None):
        doms = [dom] if dom else self.doms
        elements = []
        for dom in doms:
            res = dom.get_elements_by_name(element)
            elements += [res.item(i) for i in xrange(res.get_length())]
        return elements

    def _get_element_by_tag_name(self, element, dom=None):
        doms = [dom] if dom else self.doms
        elements = []
        for dom in doms:
            res = dom.get_elements_by_tag_name(element)
            elements += [res.item(i) for i in xrange(res.get_length())]
        return elements

    def _query_selector_all(self, element, dom=None):
        doms = [dom] if dom else self.doms
        elements = []
        for dom in doms:
            try:
                res = dom.query_selector_all(element)
                elements += [res.item(i) for i in xrange(res.get_length())]
            except:
                pass
        return elements

    def _find_element_in_dom(self, element, dom):
        elements = []
        for e in self._get_element_by_id(element, dom):
            if not e in elements:
                elements.append(e)
        for e in self._get_element_by_class_name(element, dom):
            if not e in elements:
                elements.append(e)
        for e in self._query_selector_all(element, dom):
            if not e in elements:
                elements.append(e)
        return elements

    def _find_element_all(self, element):
        elements = set()
        for dom in self.doms:
            elements.update(self._find_element_in_dom(element, dom))
        return elements

    def simplfy(self):
        self.execute_script(SIMPLFY_SCRIPT)

    def set_user_agent(self, user_agent):
        self._settings.set_property('user-agent', user_agent)

    def get_element_inner_html(self, element):
        while not self.ready:
            wait(3)
        htmls = [e.get_inner_html() for e in self._find_element_all(element)]
        return list((htmls))

    def take_screenshot(self, path, width=-1, height=-1):
        dview = self.get_dom_document().get_default_view()
        width = dview.get_inner_width() if width == -1 else width
        height = dview.get_outer_height() if height == -1 else height
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        self.draw(cairo.Context(surf))
        surf.write_to_png(path)

    @property
    def ready(self):
        return self.get_load_status() == WebKit.LoadStatus.FINISHED

    @property
    def source(self):
        return self.document.get_document_element().get_outer_html()

    @property
    def documents(self):
        return self.get_dom_document()


def analyze(links):
    while len(links):
        link = links.pop()
        ios_tab = Tab("http://%s" % link, IOS_UA, "ios")
        fos_tab = Tab("http://%s" % link, FOS_UA, "fos")

        t = time.time()
        while not (ios_tab.ready and fos_tab.ready) and time.time() - t < 15:
            wait(1)

        ios_tab.take_screenshot("screenshots/%s--ios" % link)
        fos_tab.take_screenshot("screenshots/%s--fos" % link)
        ios_tab.simplfy()
        fos_tab.simplfy()

        diff = difflib.SequenceMatcher(None, ios_tab.source, fos_tab.source)
        ios_tab.close()
        fos_tab.close()
        print link, diff.ratio()
        print "--------"
        time.sleep(1)

        #TODO:
        #style_sheets = root_tab.get_dom_document().get_style_sheets()
        #styles = [style_sheets.item(i) for i in xrange(style_sheets.get_length())]
        #for style in styles:
        #    print style
        #    rules = style.get_rules()
        #    print rules, style.get_href(), style.get_property("css-rules")
        #    if not rules:
        #        continue
        #    rules = [rules.item(i) for i in xrange(rules.get_length())]
        #     print rules


if __name__ == "__main__":
    mainloop = GLib.MainLoop()
    root_tab = Tab("http://www.alexa.com/topsites/countries/BR")
    links = root_tab.get_element_inner_html('small topsites-label')
    analyze(links)
    mainloop.run()