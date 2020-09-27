import importlib
import sys
import os
import traceback
import argparse
import urllib
import urllib3
import string

allParsers = ['kaiserslautern', 'mensenat']

filenameTemplate = "{base}{{metaOrFeed}}/{parserName}_{{mensaReference}}.xml"
baseUrl = "https://cvzi.github.io/mensa/"
baseRepo = "https://github.com/cvzi/mensa/"
basePath = "docs/"

def generateIndexHtml(baseUrl, basePath, errors=None):
    files = []

    for r, d, f in os.walk(basePath):
        p = baseUrl + r[len(basePath):]
        if p[-1] != '/':
            p += '/'
        for file in f:
            if file.endswith(('.xml', '.json')):
                files.append(f"{p}{file}")

    with open('html/index.html', 'r', encoding='utf8') as f:
        template = string.Template(f.read())

    content = []
    first = True
    for file in sorted(files, key=lambda s: s[len(baseUrl):].split('/').pop()):
        if file.endswith('.json'):
            if not first:
                content.append('</ul>')
            first = False
            content.append(f'<li><h3><a href="{file}">🐏 {file[len(baseUrl):]}</a></h3>')
            content.append('<ul style="list-style-type:none">')
        else:
            icon = '🈺' if '/meta/' in file else '🍱'
            content.append(f'  <li><a href="{file}">{icon} {file[len(baseUrl):]}</a></li>')
    content.append('</ul>')
    content.append('</li>')
    content = '<ol style="list-style-type:none">\n' + '\n'.join(content) + '\n</ol>'

    content = f'\n{content}\n'

    status = '<h3><a href="{baseRepo}actions/">🗿 Parser status</a></h3>'
    if errors:
        status += '\n<pre>' + '\n'.join(errors) + '</pre>'

    with open(os.path.join(basePath, 'index.html'), 'w', encoding='utf8') as f:
        f.write(template.substitute(content=content, status=status))

def main(updateJson=True,
         updateMeta=True,
         updateFeed=True,
         updateIndex=True,
         selectedParser='',
         selectedMensa='',
         baseUrl=baseUrl,
         basePath=basePath):

    greenOk = "Ok" if "idlelib" in sys.modules else "\033[1;32mOk\033[0m"
    redError = "Error" if "idlelib" in sys.modules else "\033[1;31m⚠️ Error\033[0m"
    errors = []

    for parserName in allParsers:
        if not updateJson and not updateMeta and not updateFeed:
            continue
        if selectedParser and parserName != selectedParser:
            continue
        print(f"🗳️ {parserName}")
        try:
            module = importlib.import_module(parserName)
            parser = module.getParser(filenameTemplate.format(
                base=baseUrl, parserName=parserName))

            if updateJson:
                filename = os.path.join(basePath, f'{parserName}.json')
                print(f" - 🐏 {filename}", end="")
                os.makedirs(os.path.dirname(filename), exist_ok=True)
                content = parser.json()
                with open(filename, 'w', encoding='utf8') as f:
                    f.write(content)
                print(f"  {greenOk}")

            canteenCounter = 0
            for mensaReference in parser.canteens:
                if selectedMensa and selectedMensa != mensaReference:
                    continue
                print(f"  - 🏫 {mensaReference}")
                try:
                    if updateMeta:
                        filename = filenameTemplate.format(base=basePath, parserName=parserName).format(metaOrFeed='meta', mensaReference=mensaReference)
                        print(f"    - 🈺 {filename}", end="")
                        os.makedirs(os.path.dirname(filename), exist_ok=True)
                        content = parser.meta(mensaReference)
                        with open(filename, 'w', encoding='utf8') as f:
                            f.write(content)
                        print(f"  {greenOk}")
                    if updateFeed:
                        filename = filenameTemplate.format(base=basePath, parserName=parserName).format(metaOrFeed='feed', mensaReference=mensaReference)
                        print(f"    - 🍱 {filename}", end="")
                        os.makedirs(os.path.dirname(filename), exist_ok=True)
                        content = parser.feed(mensaReference)
                        with open(filename, 'w', encoding='utf8') as f:
                            f.write(content)
                        print(f"  {greenOk}")
                except KeyboardInterrupt as e:
                    raise e
                except (IOError, ConnectionError, urllib.error.URLError, urllib3.exceptions.HTTPError) as e:
                    if canteenCounter == 0:
                        # Assumption: this errors affects the whole parser, skip the whole parser
                        raise e
                    else:
                        print(f"  {redError}")
                        traceback.print_exc()
                except BaseException:
                    print(f"  {redError}")
                    traceback.print_exc()
                    errors.append(f"{parserName}/{mensaReference}:")
                    errors.append(traceback.format_exc())
                canteenCounter += 1

        except KeyboardInterrupt:
            print(" [Control-C]")
            return 130
        except BaseException:
            print(f"  {redError}")
            errors.append(f"{parserName}:")
            errors.append(traceback.format_exc())
            traceback.print_exc()

    if updateIndex:
        print(f" - 📄 index.html", end="")
        generateIndexHtml(baseUrl=baseUrl, basePath=basePath, errors=errors)
        print(f"  {greenOk}")

    return min(0, len(errors))


if __name__ == "__main__":
    # Arguments
    parser = argparse.ArgumentParser(
        description='Update github pages')
    parser.add_argument(
        '-meta',
        dest='updateMeta',
        action='store_const',
        const=True,
        default=False,
        help='Update meta xml')
    parser.add_argument(
        '-feed',
        dest='updateFeed',
        action='store_const',
        const=True,
        default=False,
        help='Update feed xml')
    parser.add_argument(
        '-json',
        dest='updateJson',
        action='store_const',
        const=True,
        default=False,
        help='Update json')
    parser.add_argument(
        '-index',
        dest='updateIndex',
        action='store_const',
        const=True,
        default=False,
        help='Update index.html')
    parser.add_argument(
        '-parser',
        dest='selectedParser',
        default='',
        help='Parser name')
    parser.add_argument(
        '-canteen',
        dest='selectedMensa',
        default='',
        help='Mensa reference')
    parser.add_argument(
        '-url',
        dest='baseUrl',
        default=baseUrl,
        help='Base URL')
    parser.add_argument(
        '-out',
        dest='basePath',
        default=basePath,
        help='Output directory')

    args = parser.parse_args()

    sys.exit(main(**vars(args)))
