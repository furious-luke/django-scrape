import os
from twisted.internet.defer import Deferred, DeferredList
from scrapy.utils.misc import arg_to_iter
from scrapy import log
from scrapy.exceptions import DropItem
from scrapy.conf import settings
from scrapy.contrib.pipeline.images import ImagesPipeline
from django.db.models import OneToOneField, ForeignKey, FileField, ImageField
from django.db.models import Model as DjangoModel
from django.db.models.fields.related import RelatedField, ManyToManyField
from django.core.files import File

import items


class DjangoItemPipeline(object):

    def __init__(self):
        self.spider_objs = {}

    def open_spider(self, spider):
        self.spider_objs[spider] = {}

    def close_spider(self, spider):
        del self.spider_objs[spider]

    def process_item(self, item, spider):
        obj_map = self.spider_objs[spider]
        rel_fields = item._model_rel_fields

        # If there are no related fields to resolve just save and return.
        if not rel_fields:
            return self.save_item(None, item, spider)

        # Build a list of outstanding requests.
        req_ids = sum([arg_to_iter(item.get(f.name, [])) for f in rel_fields], [])
        req_ids = [u for u in req_ids if (u not in obj_map or isinstance(obj_map[u], Deferred))]

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

    def drop_item(self, spider, id, msg):
        if id is not None:
            dfd = self.spider_objs[spider].get(id)
            self.spider_objs[spider][id] = None
            if isinstance(dfd, Deferred):
                dfd.callback(None)
        raise DropItem(msg)

    def save_item(self, result, item, spider):
        obj_map = self.spider_objs[spider]
        # for k,v in obj_map.iteritems():
        #     if isinstance(v, Deferred):
        #         print '***: ' + repr(k)
        item_id = item.get('id')

        # Map the item's values.
        for field in item._model_fields:
            name = field.name

            # Process related fields.
            if field in item._model_rel_fields:

                # Map the related IDs to objects.
                ids = item.get(name, [])
                objs = []
                for id in arg_to_iter(ids):
                    obj = obj_map[id]

                    # Check that this is a valid object.
                    if not isinstance(obj, DjangoModel):
                        self.drop_item(
                            spider, item_id, 
                            '%s.%s had an invalid related object for "%s".'%(
                                item.django_model.__name__, name, item['scrape_url']
                            )
                        )

                    # Add to the set of objects.
                    objs.append(obj)

                # Coerce to fit the type of field.
                if len(objs) == 1 and field not in item._model_m2m_fields:
                    item[name] = objs[0]
                elif objs:
                    item[name] = objs

            # Process file fields.
            elif field in item._model_file_fields or field in item._model_img_fields:
                file_field = item.get(item.get(name), None)
                if file_field:
                    file_info = file_field[0]
                    path = os.path.join(settings['IMAGES_STORE'], file_info['path'])
                    filename = os.path.basename(path)
                    item[name] = path
                else:
                    item[name] = None

            # Check for missing/empty values.
            if item.get(name) in [None, '', []]:
                if field.blank == False:
                    self.drop_item(
                        spider, item_id,
                        '%s.%s cannot be null for "%s".'%(
                            item.django_model.__name__, name, item['scrape_url'])
                    )

        # Store the results.
        obj = item.save()

        # Store the resultant django object and call the deferred object.
        if item_id is not None:
            dfd = obj_map.get(item_id)
            if isinstance(dfd, Deferred):
                obj_map[item_id] = obj
                dfd.callback(None)
            else:
                obj_map[item_id] = obj

        # Need to return the item, as this is what gets eventually handed on to the next link
        # in the item pipeline.
        return item


class FixedImagesPipeline(ImagesPipeline):

    def item_completed(self, results, item, info):
        if 'images' in item.fields and 'image_urls' in item.fields:
            item['images'] = [x for ok, x in results if ok]
        elif results:
            raise DropItem('Confused, item has no "images" field, yet images were found.')
        return item
