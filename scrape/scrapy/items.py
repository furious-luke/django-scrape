import os
from datetime import datetime
from scrapy.item import Field, Item, ItemMeta
from scrapy.contrib.loader import ItemLoader, XPathItemLoader
import django.db.models as django_models
from django.core.files import File
from django.db.models import OneToOneField, ForeignKey, FileField, ImageField
from django.db.models.fields.related import RelatedField, ManyToManyField
from django.db.models.fields.subclassing import SubfieldBase
from processors import *
from gigspot_site.scrape import utils
from gigspot_site.scrape.utils import conv
from gigspot_site.address.models import AddressField


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
        scrape_model = False
        try:
            from gigspot_site.scrape.models import ScrapeModel
            if isinstance(django_model, type(ScrapeModel)):
                scrape_model = True
        except:
            pass

        # If we were flagged as using a ScrapeModel, hunt down the actual target.
        if scrape_model:
            cls._scrape_model = django_model
            target = django_model._meta.get_field_by_name('target')[0]
            django_model = target.rel.to
        else:
            cls._scrape_model = None

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

                # If we have a scrape model, add the extra fields.
                if scrape_model:
                    cls.fields[field.name + '_source'] = Field()
                    cls.fields[field.name + '_timestamp'] = Field(input_processor=DateTime())

        # Create a group of related fields.
        cls._model_rel_fields = cls._model_fk_fields + cls._model_m2m_fields
        cls._model_fields = cls._model_reg_fields + cls._model_rel_fields + cls._model_file_fields + \
            cls._model_img_fields

        return cls


def get_field_query(field, value):
    if value in ('', None, []):
        return None
    if isinstance(field, AddressField):
        # Unfortunate, but necessary.
        address = field.to_python(value)
        address.locality.state.country.save()
        address.locality.state.save()
        address.locality.state_id = address.locality.state.pk
        address.locality.save()
        address.locality_id = address.locality.pk
        address.save()
        return ('', address)
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
    scrape_url = Field()

    def save(self):
        # Create a search filter, beginning by adding all my unique fields.
        fltr = {}
        for field in self._model_fields:
            if field.unique or isinstance(field, FileField):
                query = get_field_query(field, self.get(field.name, None))
                if query:
                    fltr.update({field.name + query[0]: query[1]})

        # Now add all the fields that must be unique combined.
        for unique_set in self.django_model._meta.unique_together:
            cur_fltr = {}
            for field_name in unique_set:
                field = self.django_model._meta.get_field_by_name(field_name)[0]
                query = get_field_query(field, self.get(field.name, None))
                if not query: # if any of the fields are not supplied, we can't use it
                    cur_fltr = {}
                    break
                cur_fltr.update({field.name + query[0]: query[1]})
            if cur_fltr:
                fltr.update(cur_fltr)

        # Either get an existing object or create a new one.
        if fltr:
            obj, created = self.django_model.objects.get_or_create(**fltr)
        else:
            obj, created = self.django_model.objects.create(), True

        # We perform a fill operation even on new objects because of the possibility
        # that the filter we uesed to find an existing object contained '__' notations,
        # e.g. any many-to-many field.
        for field in self._model_fields:

            # If the field is an m2m, perform a merge.
            if isinstance(field, ManyToManyField):
                to_insert = arg_to_iter(self.get(field.name))
                existing = getattr(obj, field.name).all()
                to_insert = [t for t in to_insert if t not in existing]
                for itm in to_insert:
                    getattr(obj, field.name).add(itm)

            # If we have a file field we need special consideration.
            elif isinstance(field, FileField):
                path = self.get(field.name)
                filename = os.path.basename(path)
                getattr(obj, field.name).save(filename, File(open(path, 'rb')))

            # Otherwise just check if a value already exists.
            elif getattr(obj, field.name) in ['', None]:
                setattr(obj, field.name, self.get(field.name))

        return obj


class DjangoItemLoader(ItemLoader):

    def __init__(self, item, response, id=None, **kwargs):
        ItemLoader.__init__(self, item, **kwargs)
        self._source = str(response.url)
        if id is not None:
            self.add_value('id', id)
        self.add_value('scrape_url', response.url)

    def add_value(self, field_name, value, *args, **kwargs):
        return self._wrapper(field_name, value, 'add_value', *args, **kwargs)

    def replace_value(self, field_name, value, *args, **kwargs):
        return self._wrapper(field_name, value, 'replace_value', *args, **kwargs)

    def _wrapper(self, field_name, value, call, *args, **kwargs):
        parent = super(DjangoItemLoader, self)

        # If we using our special ScrapeModel class, add in the extra bits.
        if self.item._scrape_model and field_name not in ['id', 'scrape_url']:
            parent.replace_value(field_name + '_source', self._source)
            parent.replace_value(field_name + '_timestamp', datetime.now())

        return getattr(parent, call)(field_name, value, *args, **kwargs)


class DjangoXPathItemLoader(XPathItemLoader):

    def __init__(self, item, response, id, selector=None, **context):
        XPathItemLoader.__init__(self, item, selector, response, **context)
        self._source = str(response.url)
        if id is not None:
            self.add_value('id', id)
        self.add_value('scrape_url', response.url)

    def add_value(self, field_name, value, *args, **kwargs):
        return self._wrapper(field_name, value, 'add_value', *args, **kwargs)

    def replace_value(self, field_name, value, *args, **kwargs):
        return self._wrapper(field_name, value, 'replace_value', *args, **kwargs)

    def _wrapper(self, field_name, value, call, *args, **kwargs):
        parent = super(DjangoXPathItemLoader, self)

        # If we using our special ScrapeModel class, add in the extra bits.
        if self.item._scrape_model and field_name not in ['id', 'scrape_url']:
            parent.replace_value(field_name + '_source', self._source)
            parent.replace_value(field_name + '_timestamp', datetime.now())

        return getattr(parent, call)(field_name, value, *args, **kwargs)
