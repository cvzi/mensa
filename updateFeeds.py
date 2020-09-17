import importlib
import sys
import os
import traceback
import argparse
import urllib
import urllib3

allParsers = ['kaiserslautern', 'mensenat']

filenameTemplate = "{base}{{metaOrFeed}}/{parserName}_{{mensaReference}}.xml"
baseUrl = "https://cvzi.github.io/mensa/"
baseRepo = "https://github.com/cvzi/mensa/"
basePath = "docs/"

def generateIndexHtml(baseUrl, basePath):
    files = []

    for r, d, f in os.walk(basePath):
        p = baseUrl + r[len(basePath):]
        if p[-1] != '/':
            p += '/'
        for file in f:
            if file.endswith(('.xml', '.json')):
                files.append(f"{p}{file}")

    content = '<br>\n'.join(f'<a href="{file}">{file}</a>' for file in sorted(files, key=lambda s: os.path.splitext(s)[1] + s))

    if updateIndex:
        content = f'<a href="{baseRepo}actions/">Parser status</a><br>\n<br>\n{content}'

    with open(os.path.join(basePath, 'index.html'), 'w', encoding='utf8') as f:
        f.write(content)

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

    for parserName in allParsers:
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
                canteenCounter += 1

        except KeyboardInterrupt:
            print(" [Control-C]")
            return 130
        except BaseException:
            print(f"  {redError}")
            traceback.print_exc()
            return 1

    if updateIndex:
        print(f" - 📄 index.html", end="")
        generateIndexHtml(baseUrl=baseUrl, basePath=basePath)
        print(f"  {greenOk}")

    return 0


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
