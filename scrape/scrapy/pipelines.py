import os
from twisted.internet.defer import Deferred, DeferredList
from scrapy.utils.misc import arg_to_iter
from scrapy import log
from scrapy.exceptions import DropItem
from scrapy.conf import settings
from scrapy.contrib.pipeline.images import ImagesPipeline
from django.db.models import OneToOneField, ForeignKey, FileField
from django.db.models import Model as DjangoModel
from django.db.models.fields.related import RelatedField, ManyToManyField
from django.core.files import File

import items


def is_validated(obj, field_name, item):
    if hasattr(item._scrape_model):
        valid_name = field_name + '_valid'
        return getattr(obj.scrape, valid_name)
    return False


def model_fill(obj, info_dict, item):
    all_fields = obj._meta.fields + obj._meta.many_to_many
    for field in all_fields:
        name = field.name
        if name in ['id', 'pk']:
            continue
        if name not in info_dict:
            continue
        if is_validated(obj, name, item):
            continue
        cur_val = getattr(obj, name)
        modified = False
        if isinstance(field, ManyToManyField):
            for val in conv.to_list(info_dict[name]):
                if not cur_val.filter(pk=val.pk).exists():
                    cur_val.add(val)
                    modified = True
        else:
            if not cur_val:
                setattr(obj, name, info_dict[name])
                modified = True
        if modified:
            if hasattr(item._scrape_model):
                src_name = name + '_source'
                setattr(obj.scrape, src_name, item[src_name])
                ts_name = name + '_timestamp'
                setattr(obj.scrape, ts_name, item[ts_name])
                


class DjangoItemPipeline(object):

    def __init__(self):
        self.spider_objs = {}

    def open_spider(self, spider):
        self.spider_objs[spider] = {}

    def close_spider(self, spider):
        del self.spider_objs[spider]

    def process_item(self, item, spider):
        obj_map = self.spider_objs[spider]

        fields = self._process_fields(item)
        related_fields = fields['foreign_key'] + fields['one_to_one'] + fields['many_to_many']

        # If there are no related fields to resolve just save and return.
        if not related_fields:
            return self.save_item(None, item, spider)

        # Build a list of outstanding requests.
        req_ids = [u for u in self.get_request_ids(item, related_fields) \
                       if (u not in obj_map or isinstance(obj_map[u], Deferred))]

        # If there are no requests to perform, fill, save and return.
        if not req_ids:
            return self.save_item(None, item, spider)

        # Defer?
        dlist = []
        for id in req_ids:
            if id not in obj_map:
                obj_map[id] = Deferred()
            dfd = obj_map[id]
            assert dfd is not None
            dlist.append(dfd)
        return DeferredList(dlist, consumeErrors=1).addCallback(self.save_item, item, spider)

    def get_request_ids(self, item, related_fields):
        reqs = []
        for field in related_fields:
            reqs.extend(arg_to_iter(item.get(field.name, [])))
        return reqs

    def save_item(self, result, item, spider):
        obj_map = self.spider_objs[spider]
        id = item.get('id')

        # Create an info dict full of our information.
        file_fields = {}
        info = {}
        all_fields = item.django_model._meta.fields + item.django_model._meta.many_to_many
        for field in all_fields:
            if field.name == 'id':
                continue
            if field.name in item and item[field.name] not in [None, '', []]:
                if isinstance(field, RelatedField):
                    ids = item.get(field.name, [])
                    links = [obj_map[u] for u in arg_to_iter(ids)]
                    if len(links) == 1 and not isinstance(field, ManyToManyField):
                        info[field.name] = links[0]
                    elif links:
                        info[field.name] = links
                    # Confirm that each link is valid.
                    for o in arg_to_iter(info[field.name]):
                        if not isinstance(o, DjangoModel):
                            if id is not None:
                                dfd = self.spider_objs[spider].get(id)
                                self.spider_objs[spider][id] = None
                                if isinstance(dfd, Deferred):
                                    dfd.callback(None)
                            raise DropItem('%s.%s had an invalid related object for "%s".'%
                                           (item.django_model.__name__, field.name, item['scrape_url']))
                elif isinstance(field, FileField):
                    file_field = item.get(field.name)
                    if file_field:
                        file_field = item[file_field]
                        file_info = file_field[0]
                        path = os.path.join(settings['IMAGES_STORE'], file_info['path'])
                        filename = os.path.basename(path)
                        info[field.name + '__contains'] = filename
                        file_fields[field.name] = path
                    else:
                        del info[field.name]
                else:
                    info[field.name] = item[field.name]

        # Check for null fields.
        for field in all_fields:
            if field.name == 'id' or isinstance(field, FileField): # TODO: Check file field for blank.
                continue
            if not field.blank and info.get(field.name) in [None, '', []]:
                if id is not None:
                    dfd = self.spider_objs[spider].get(id)
                    self.spider_objs[spider][id] = None
                    if isinstance(dfd, Deferred):
                        dfd.callback(None)
                raise DropItem('%s.%s cannot be null for "%s".'%(item.django_model.__name__, field.name, item['scrape_url']))

        # Store the results.
        if hasattr(item.django_model.objects, 'get_existing_or_create'):
            obj, created = item.django_model.objects.get_existing_or_create(**info)
        else:
            obj, created = item.django_model.objects.get_or_create(**info)
        if not created and not getattr(obj, 'valid', False):
            # Before filling, eliminate anything used as a filter. This is for FileFields at the moment.
            for k, v in info.iteritems():
                if '__' in k:
                    del info[k]
            model_fill(obj, info, item)
            obj.save()

        # If the object was just created, add file fields.
        elif created:
            for field in all_fields:
                if field.name == 'id':
                    continue
                if isinstance(field, FileField) and field.name in file_fields:
                    path = file_fields[field.name]
                    filename = os.path.basename(path)
                    getattr(obj, field.name).save(filename, File(open(path, 'rb')))
                obj.save()

        # Store the resultant django object and call the deferred object.
        if id is not None:
            dfd = self.spider_objs[spider].get(id)
            if isinstance(dfd, Deferred):
                self.spider_objs[spider][id] = obj
                dfd.callback(None)
            else:
                self.spider_objs[spider][id] = obj

        # Need to return the item, as this is what gets eventually handed on to the next link
        # in the item pipeline.
        return item

    def _process_fields(self, item):
        field_dict = dict(basic=[], one_to_one=[], foreign_key=[], many_to_many=[])
        for field in item.django_model._meta.fields:
            if field.name == 'id':
                continue
            if isinstance(field, OneToOneField):
                field_dict['one_to_one'].append(field)
            elif isinstance(field, ForeignKey):
                field_dict['foreign_key'].append(field)
            else:
                field_dict['basic'].append(field)
        field_dict['many_to_many'] = list(item.django_model._meta.many_to_many)
        return field_dict


class FixedImagesPipeline(ImagesPipeline):

    def item_completed(self, results, item, info):
        if 'images' in item.fields and 'image_urls' in item.fields:
            item['images'] = [x for ok, x in results if ok]
        elif results:
            raise DropItem('Confused, item has no "images" field, yet images were found.')
        return item
