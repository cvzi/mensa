from pyopenmensa.feed import LazyBuilder

__all__ = ['xmlEscape', 'StyledLazyBuilder']

def xmlEscape(s):
    s = str(s).replace('&', '&amp;')  # amp first!
    s = s.replace('>', '&gt;')
    s = s.replace('<', '&lt;')
    return s

class StyledLazyBuilder(LazyBuilder):
    def toXMLFeed(self, styles=['https://cvzi.github.io/om-style/latest/basic.css', 'https://cvzi.github.io/om-style/latest/lightgreen.css']):
        feed = self.toXML()
        xml_header = '<?xml version="1.0" encoding="UTF-8"?>\n'
        if styles:
            for style in styles:
                xml_header += '<?xml-stylesheet href="' + style + '" type="text/css"?>\n'
        return xml_header + feed.toprettyxml(indent='  ')
