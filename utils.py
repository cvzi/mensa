
def xmlEscape(s):
    s = str(s).replace('&', '&amp;')  # amp first!
    s = s.replace('>', '&gt;')
    s = s.replace('<', '&lt;')
    return s
