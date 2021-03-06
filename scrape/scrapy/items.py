import os, urllib2
from datetime import datetime
from scrapy.exceptions import DropItem
from scrapy.item import Field, Item, ItemMeta
from scrapy.contrib.loader import ItemLoader, XPathItemLoader
import django.db.models as django_models
from django.core.files import File
from django.db.models import OneToOneField, ForeignKey, FileField, ImageField
from django.db.models.fields.related import RelatedField, ManyToManyField
from django.db.models.fields.subclassing import SubfieldBase
from django.core.exceptions import ObjectDoesNotExist
from processors import *
from address.models import AddressField
from pythonutils.conv import to_datetime

# Don't assume googlemaps is available.
try:
    from googlemaps import GoogleMapsError
except:
    pass


class DjangoItemMeta(ItemMeta):

    def  __new__(mcs, class_name, bases, attrs):

        # Use this function to pick an appropriate input processor.
        def select_input_processor(field):
            if isinstance(field, django_models.FloatField):
                return Float()
            elif isinstance(field, django_models.IntegerField):
                return Int()
            elif isinstance(field, django_models.BooleanField):
                return Bool()
            elif isinstance(field, django_models.DateTimeField):
                return DateTime()
            elif isinstance(field, django_models.DateField):
                return Date()
            else:
                return MapCompose(RemoveEntities(), Strip())

        # Instantiate our class from the parent and copy their fields.
        cls = super(DjangoItemMeta, mcs).__new__(mcs, class_name, bases, attrs)
        cls.fields = cls.fields.copy()

        # If no Django model was given just use a normal item.
        django_model = cls.django_model
        if not django_model:
            return cls

        # Are we using a ScrapeModel?
        cls._scrape_model = False
        try:
            from scrape.models import ScrapeModel
            if isinstance(django_model, type(ScrapeModel)):
                cls._scrape_model = True
        except:
            pass

        # Make room for our fields.
        cls._model_meta = django_model._meta
        cls._model_fields = django_model._meta.fields + django_model._meta.many_to_many
        cls._model_m2m_fields = []
        cls._model_fk_fields = []
        cls._model_reg_fields = []
        cls._model_file_fields = []
        cls._model_img_fields = []

        # Do a pass over all the fields.
        for field in cls._model_fields:

            # Don't bother looking at the ID field.
            if field.name == 'id':
                continue

            # Different action for each different kind of field.
            ip = select_input_processor(field)
            op = TakeFirst()
            if isinstance(field, ManyToManyField):
                cls._model_m2m_fields.append(field)
                op = PassThrough()

            elif isinstance(field, (ForeignKey, OneToOneField)):
                if issubclass(field.__metaclass__, SubfieldBase):
                    # TODO: This is kind of a hack.
                    cls._model_reg_fields.append(field)
                else:
                    cls._model_fk_fields.append(field)

            elif isinstance(field, ImageField):
                cls._model_img_fields.append(field)

            elif isinstance(field, FileField):
                cls._model_file_fields.append(field)

            else:
                cls._model_reg_fields.append(field)

            # If we don't already have a field defined, create a new one.
            if field.name not in cls.fields:
                cls.fields[field.name] = Field(input_processor=ip, output_processor=op)

        # Create a group of related fields.
        cls._model_rel_fields = cls._model_fk_fields + cls._model_m2m_fields
        cls._model_fields = cls._model_reg_fields + cls._model_rel_fields + cls._model_file_fields + \
            cls._model_img_fields

        return cls


def get_field_value(item, field, value, pipeline, spider):
    if value in ('', None, []):
        return None
    if isinstance(field, AddressField):
        try:
            address = field.to_python(value)
        except GoogleMapsError, urllib2.HTTPError:
            pipeline.drop_item(spider, item.get('id'), 'Failed to geolocate address.')
        address.locality.state.country.save()
        address.locality.state.country_id = address.locality.state.country.pk
        address.locality.state.save()
        address.locality.state_id = address.locality.state.pk
        address.locality.save()
        address.locality_id = address.locality.pk
        address.save()
        return address
    else:
        return value


def get_field_query(item, field, value, pipeline, spider, use_null=False):
    if value in ('', None, []):
        if use_null:
            if isinstance(field, (django_models.CharField, django_models.TextField)):
                return ('', '')
            else:
                return ('__isnull', True)
        else:
            return None
    value = get_field_value(item, field, value, pipeline, spider)
    if isinstance(field, AddressField):
        return ('', value)
    elif isinstance(field, ManyToManyField):
        return ('__contains', value)
    elif isinstance(field, FileField):
        return ('__contains', os.path.basename(value))
    return ('', value)


class DjangoItem(Item):
    __metaclass__ = DjangoItemMeta
    django_model = None

    # We use the "id" field to form links between models for related fields.
    id = Field(input_processor=MapCompose(RemoveEntities(), Strip()), output_processor=TakeFirst())
    scrape_url = Field(output_processor=TakeFirst())

    def save(self, pipeline, spider):
        # Convert all our values as needed. Mostly for addresses, dammit.
        for field in self._model_fields:
            value = self.get(field.name)
            if value not in ['', None, []]:
                self[field.name] = get_field_value(self, field, value, pipeline, spider)

        # Create a search filter, beginning by adding all my unique fields.
        fltr = {}
        for field in self._model_fields:
            if field.unique or isinstance(field, FileField):
                query = get_field_query(self, field, self.get(field.name, None), pipeline, spider)
                if query:
                    fltr.update({field.name + query[0]: query[1]})

        # Now add all the fields that must be unique combined.
        for unique_set in self.django_model._meta.unique_together:
            cur_fltr = {}
            for field_name in unique_set:
                field = self.django_model._meta.get_field_by_name(field_name)[0]
                query = get_field_query(self, field, self.get(field.name, None), pipeline, spider, use_null=True)
                cur_fltr.update({field.name + query[0]: query[1]})
            if cur_fltr:
                fltr.update(cur_fltr)

        # Either get an existing object or create a new one.
        if fltr:
            obj, created = self.django_model.objects.get_or_create(**fltr)
        else:

            # If we're making a new object, be sure to fill required fields.
            required = {}
            for field in self._model_fields:
                if field.blank == False:
                    value = self.get(field.name)
                    if value is None:
                        print self
                    assert value is not None
                    required[field.name] = value
            obj, created = self.django_model.objects.create(**required), True

        # We perform a fill operation even on new objects because of the possibility
        # that the filter we uesed to find an existing object contained '__' notations,
        # e.g. any many-to-many field.
        for field in self._model_fields:
            name = field.name
            cur_value = getattr(obj, name)

            # If the value to set is empty, skip it.
            if self.get(name) in [None, '']:
                continue

            # If we're using a ScrapeModel, first check if the field has already been
            # validated.
            if self._scrape_model:
                if getattr(obj, name + '_valid') == True:
                    continue # alrady validated, skip

            # If the field is an m2m, perform a merge.
            modified = False
            if isinstance(field, ManyToManyField):
                to_insert = arg_to_iter(self.get(name))
                existing = cur_value.all()
                to_insert = [t for t in to_insert if t not in existing]
                for itm in to_insert:
                    cur_value.add(itm)
                    modified = True

            # If we have a file field we need special consideration.
            elif isinstance(field, FileField):

                # Only change it if it does not already have a value. If we don't
                # observe this, we end up with duplicate files.
                if cur_value in ['', None]:
                    path = self.get(name)
                    filename = os.path.basename(path)
                    cur_value.save(filename, File(open(path, 'rb')))
                    modified = True

            # # Otherwise just check if a value already exists.
            # elif cur_value in ['', None]:
            #     setattr(obj, name, self.get(name))
            #     modified = True

            # Otherwise, stomp on existing value, bearing in mind that we've already
            # checked if the value we're writing is empty.
            else:
                setattr(obj, name, self.get(name))
                modified = True

            # If we're using a scrape model and we changed the field, update the scrape data. Or,
            # if there is no existing value for either the source or timestamp, fill them in.
            if self._scrape_model:

                # Timestamp.
                cur_name = name + '_timestamp'
                cur_val = getattr(obj, cur_name)
                if not cur_val or modified:
                    setattr(obj, cur_name, datetime.now())#to_datetime(self[cur_name]))

                # Source
                cur_name = name + '_source'
                cur_val = getattr(obj, cur_name)
                if not cur_val or modified:
                    setattr(obj, cur_name, self['scrape_url'])#self[cur_name])

        # Save both the object and the scrape object.
        obj.save()

        return obj


class DjangoItemLoader(ItemLoader):

    def __init__(self, item, response, id=None, **kwargs):
        ItemLoader.__init__(self, item, **kwargs)
#        self._source = str(response.url)
        if id is not None:
            self.add_value('id', id)
        self.add_value('scrape_url', response.url)

    def add_value(self, field_name, value, *args, **kwargs):
        return self._wrapper(field_name, value, 'add_value', *args, **kwargs)

    def replace_value(self, field_name, value, *args, **kwargs):
        return self._wrapper(field_name, value, 'replace_value', *args, **kwargs)

    def _wrapper(self, field_name, value, call, *args, **kwargs):
        parent = super(DjangoItemLoader, self)
        return getattr(parent, call)(field_name, value, *args, **kwargs)


class DjangoXPathItemLoader(XPathItemLoader):

    def __init__(self, item, response, id, selector=None, **context):
        XPathItemLoader.__init__(self, item, selector, response, **context)
#        self._source = str(response.url)
        if id is not None:
            self.add_value('id', id)
        self.add_value('scrape_url', response.url)

    def add_value(self, field_name, value, *args, **kwargs):
        return self._wrapper(field_name, value, 'add_value', *args, **kwargs)

    def replace_value(self, field_name, value, *args, **kwargs):
        return self._wrapper(field_name, value, 'replace_value', *args, **kwargs)

    def _wrapper(self, field_name, value, call, *args, **kwargs):
        parent = super(DjangoXPathItemLoader, self)
        return getattr(parent, call)(field_name, value, *args, **kwargs)
