from datetime import datetime
import dateutil.parser, re
from scrapy.contrib.loader.processor import *
from scrapy.utils.markup import remove_entities
from scrapy.utils.misc import arg_to_iter
from scrapy import log


class PassThrough(object):

    def __call__(self, values):
        return values


class Prefix(object):

    def __init__(self, prefix=u''):
        self.prefix = prefix

    def __call__(self, values):
        return [self.prefix + v for v in arg_to_iter(values)]


class Strip(object):

    def __call__(self, values):
        return [v.strip() for v in arg_to_iter(values)]


class RemoveEntities(object):

    def __call__(self, values):
        return [remove_entities(v) for v in arg_to_iter(values)]


class Exclude(object):

    def __init__(self, *args):
        self.excludes = args

    def __call__(self, values):
        return [v for v in arg_to_iter(values) if v not in self.excludes]


class Split(object):

    def __init__(self, token=u' '):
        self.token = token

    def __call__(self, values):
        return sum([v.split(self.token) for v in arg_to_iter(values)], [])


class Float(object):

    def __call__(self, values):
        new_values = []
        for v in arg_to_iter(values):
            if isinstance(v, (str, unicode)):
                v = remove_entities(v).strip()
            new_values.append(float(v))
        return new_values


class Int(object):

    def __call__(self, values):
        new_values = []
        for v in arg_to_iter(values):
            if isinstance(v, (str, unicode)):
                v = remove_entities(v).strip()
            new_values.append(int(v))
        return new_values


class Bool(object):

    def __call__(self, values):
        new_values = []
        for v in arg_to_iter(values):
            if isinstance(v, (str, unicode)):
                v = remove_entities(v).strip()
                v = (v.lower() == 'true')
            else:
                v = bool(v)
            new_values.append(v)
        return new_values


class Slice(object):

    def __init__(self, begin, end=None):
        self.begin = begin
        self.end = end

    def __call__(self, values):
        return [v[self.begin:self.end] for v in arg_to_iter(values)]


class GenreMash(object):

    def __call__(self, values):
        out_values = []
        values = arg_to_iter(values)
        while values:
            val = values.pop(0)
            if values and val == 'R' and values[0] == 'B':
                values.pop(0)
                out_values.append('R&B')
            elif val:
                out_values.append(val)
        return out_values


class DateTime(object):

    def __call__(self, values):
        out_values = []
        for v in arg_to_iter(values):
            if isinstance(v, (str, unicode)):
                try:
                    out_values.append(dateutil.parser.parse(str(v), fuzzy=True))
                except:
                    log.msg('Failed to convert datetime string: "%s"'%v, level=log.WARNING)
                    out_values.append(None)
            elif isinstance(v, datetime):
                out_values.append(v)
            else:
                out_values.append(datetime(v))
        return out_values


class Date(object):

    def __call__(self, values):
        return [v.date() for v in DateTime()(values)]
