import sys
import os
import logging
import collections

include = os.path.relpath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, include)

isPyIdle = "idlelib" in sys.modules
endVT = "" if isPyIdle else "\033[0m"
greenVT = "" if isPyIdle else "\033[1;32m"
greenOk = f"{greenVT}Ok{endVT}"


class ParserMeta(type):
    def __instancecheck__(cls, instance):
        return cls.__subclasscheck__(type(instance))

    def __subclasscheck__(cls, subclass):

        if not hasattr(subclass, 'feed') and not hasattr(subclass, 'feed_today') and not hasattr(subclass, 'feed_all'):
            return False

        if (hasattr(subclass, 'feed') and not callable(subclass.feed)) or (hasattr(subclass, 'feed_today') and not callable(subclass.feed_today)) or (hasattr(subclass, 'feed_all') and not callable(subclass.feed_all)):
            return False

        return (hasattr(subclass, 'json') and
                callable(subclass.json) and
                hasattr(subclass, 'meta') and
                callable(subclass.meta))


class ParserInterface(metaclass=ParserMeta):
    pass


def test_all_parser():
    moduleNames = ['kaiserslautern', 'mensenat', 'koeln',
                   'eurest', 'markas', 'mampf1a', 'inetmenue']

    print("Importing %s" % (", ".join(moduleNames), ))

    modules = map(__import__, moduleNames)

    for mod in modules:
        print("Parser() of %s" % mod.__name__)

        parser = mod.Parser('http://localhost/')

        assert isinstance(parser, ParserInterface)
        assert isinstance(parser.canteens, collections.abc.Mapping)
        assert len(parser.canteens)


def run_all():
    for fname, f in list(globals().items()):
        if fname.startswith('test_'):
            print(f"{fname}()...")
            f()
            print(f"...{fname}() -> {greenOk}.")


if __name__ == '__main__':
    # logging.basicConfig(level=logging.DEBUG)
    logging.basicConfig(level=logging.WARNING)
    run_all()
