import importlib
import sys
import os
import io
import traceback
import argparse
import urllib
import urllib3
import string

allParsers = ['kaiserslautern', 'mensenat', 'koeln',
              'eurest', 'markas', 'mampf1a', 'inetmenue', 'greifswald']

repo_path = os.path.dirname(__file__)
filename_template = "{base}{{metaOrFeed}}/{parserName}_{{mensaReference}}.xml"
base_url = "https://cvzi.github.io/mensa/"
base_repo = "https://github.com/cvzi/mensa/"
base_path = "docs/"


log_file = None
greenOk = "Ok" if "idlelib" in sys.modules else "\033[1;32mOk\033[0m"
redError = "Error" if "idlelib" in sys.modules else "\033[1;31m⚠️ Error\033[0m"


def log(*objects, sep=' ', end='\n', file=sys.stdout, flush=False):
    print(*objects, sep=sep, end=end, file=file, flush=flush)
    if log_file and not log_file.closed:
        print(*objects, sep=sep, end=end, file=log_file, flush=flush)


def generateIndexHtml(baseUrl, basePath, errors=None):
    files = []

    for r, _, f in os.walk(os.path.join(repo_path, basePath)):
        p = baseUrl + r[len(os.path.join(repo_path, basePath)):]
        if p[-1] != '/':
            p += '/'
        for file in f:
            if file.endswith(('.xml', '.json')):
                files.append(f"{p}{file}")

    with open(os.path.join(repo_path, 'html/index.html'), 'r', encoding='utf8') as f:
        template = string.Template(f.read())

    def sortKey(s):
        parts = s[len(baseUrl):].split('/')
        s = parts[-1].upper() + (parts[-2] if len(parts) > 1 else "")
        return s

    content = []
    first = True

    for file in sorted(files, key=sortKey):
        if file.endswith('.json'):
            if not first:
                content.append('</ul>')
            first = False

            content.append(
                f'<li><h3 id="{file[len(baseUrl):-5]}"><a href="{file}">🐏 {file[len(baseUrl):]}</a></h3>')
            content.append('<ul style="list-style-type:none">')
        else:
            icon = '🈺' if '/meta/' in file else '🍱'
            content.append(
                f'  <li><a href="{file}">{icon} {file[len(baseUrl):]}</a></li>')
    content.append('</ul>')
    content.append('</li>')
    content = '<ol style="list-style-type:none">\n' + \
        '\n'.join(content) + '\n</ol>'

    content = f'\n{content}\n'

    status = f'<h3><a href="{base_repo}actions/">🗿 Parser status</a></h3>'
    if errors:
        status += '\n<pre>' + '\n'.join(errors) + '</pre>'

    with io.open(os.path.join(repo_path, basePath, 'index.html'), 'w', encoding='utf8', newline='\n') as f:
        f.write(template.substitute(content=content, status=status))


def updateFeeds(force=None,
                updateJson=True,
                updateMeta=True,
                updateFeed=True,
                updateToday=False,
                updateIndex=True,
                selectedParser='',
                selectedMensa='',
                baseUrl=base_url,
                basePath=base_path):

    errors = []

    for parserName in allParsers:
        if not updateJson and not updateMeta and not updateFeed and not updateToday:
            continue
        if selectedParser and parserName != selectedParser:
            continue
        log(f"🗳️ {parserName}")
        try:
            module = importlib.import_module(parserName)
            parser = module.Parser(filename_template.format(
                base=baseUrl, parserName=parserName))

            if updateJson:
                filename = os.path.join(basePath, f'{parserName}.json')
                log(f" - 🐏 {filename}", end="", flush=True)
                os.makedirs(os.path.dirname(filename), exist_ok=True)
                content = parser.json()
                with io.open(os.path.join(repo_path, filename), 'w', encoding='utf8', newline='\n') as f:
                    f.write(content)
                log(f"  {greenOk}")

            canteenCounter = 0
            for mensaReference in parser.canteens:
                if selectedMensa and selectedMensa != mensaReference:
                    continue
                log(f"  - 🏫 {mensaReference}")
                try:
                    if updateMeta:
                        filename = filename_template.format(base=basePath, parserName=parserName).format(
                            metaOrFeed='meta', mensaReference=mensaReference)
                        log(f"    - 🈺 {filename}", end="", flush=True)
                        os.makedirs(os.path.dirname(filename), exist_ok=True)
                        content = parser.meta(mensaReference)
                        with io.open(os.path.join(repo_path, filename), 'w', encoding='utf8', newline='\n') as f:
                            f.write(content)
                        log(f"  {greenOk}")
                    if updateFeed or updateToday:
                        if updateToday:
                            feedMethods = [feedMethod for feedMethod in [
                                "feed_today"] if hasattr(parser, feedMethod)]
                            if not feedMethods and not updateMeta:
                                log("\033[F\033[K", end="")
                        else:
                            feedMethods = [feedMethod for feedMethod in [
                                "feed", "feed_today", "feed_all", "feed_full"] if hasattr(parser, feedMethod)]
                        for feedMethod in feedMethods:
                            fileTitle = "today" if feedMethod == "feed_today" else "feed"
                            filename = filename_template.format(base=basePath, parserName=parserName).format(
                                metaOrFeed=fileTitle, mensaReference=mensaReference)
                            log(f"    - 🍱 {filename}", end="", flush=True)
                            os.makedirs(os.path.dirname(
                                filename), exist_ok=True)
                            content = getattr(parser, feedMethod)(
                                mensaReference)
                            if type(content) is bytes:
                                with open(os.path.join(repo_path, filename), 'wb') as f:
                                    f.write(content)
                            else:
                                with io.open(os.path.join(repo_path, filename), 'w', encoding='utf8', newline='\n') as f:
                                    f.write(content)
                            log(f"  {greenOk}")
                except KeyboardInterrupt as e:
                    raise e
                except (IOError, urllib3.exceptions.HTTPError) as e:
                    if canteenCounter == 0:
                        # Assumption: this errors affects the whole parser, skip the whole parser
                        raise e
                    else:
                        log(f"  {redError}")
                        traceback.print_exc()
                except BaseException:
                    log(f"  {redError}")
                    traceback.print_exc()
                    errors.append(f"{parserName}/{mensaReference}:")
                    errors.append(traceback.format_exc())
                canteenCounter += 1

        except KeyboardInterrupt:
            log(" [Control-C]")
            return 130
        except BaseException:
            log(f"  {redError}")
            errors.append(f"{parserName}:")
            errors.append(traceback.format_exc())
            traceback.print_exc()

    if updateIndex:
        log(" - 📄 index.html", end="", flush=True)
        generateIndexHtml(baseUrl=baseUrl, basePath=basePath, errors=errors)
        log(f"  {greenOk}")

    return min(0, len(errors))


def startFromTerminal(exitAfterwards=True):
    # Arguments
    parser = argparse.ArgumentParser(
        description='Update github pages')
    parser.add_argument(
        '-force',
        dest='force',
        action='store_const',
        const=True,
        default=False,
        help='Force update')
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
        help='Update all feed xml')
    parser.add_argument(
        '-today',
        dest='updateToday',
        action='store_const',
        const=True,
        default=False,
        help='Update today feed xml')
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
        default=base_url,
        help='Base URL')
    parser.add_argument(
        '-out',
        dest='basePath',
        default=base_path,
        help='Output directory')

    args = parser.parse_args()

    exitCode = updateFeeds(**vars(args))

    if exitAfterwards:
        sys.exit(exitCode)
    return exitCode


if __name__ == "__main__":
    startFromTerminal()
