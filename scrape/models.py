from django.db import models
from django.db.models.base import ModelBase


class ScrapeModelBase(ModelBase):

    ## Override creation.
    # We need to extract the target model from Meta, then create new fields on this class to
    # represent the validity of target model's fields.
    def __new__(cls, name, bases, attrs):

        # Find the Meta class in our attributes.
        try:
            meta = attrs['Meta']
        except:
            return super(ScrapeModelBase, cls).__new__(cls, name, bases, attrs)
            # raise TypeError('No "Meta" found during construction of "%s".'%name)

        # Extract all our bits of info.
        try:
            target_model = getattr(meta, 'scrape_target_model')
        except:
            return super(ScrapeModelBase, cls).__new__(cls, name, bases, attrs)
            # raise TypeError('Need to define "scrape_target_model" in "Meta" for "%s".'%name)
        include_fields = getattr(meta, 'scrape_include_fields', [])
        exclude_fields = getattr(meta, 'scrape_exclude_fields', [])

        # Delete our meta values as Django complains if it finds unknown values.
        if hasattr(meta, 'scrape_target_model'):
            del meta.scrape_target_model
        if hasattr(meta, 'scrape_include_fields'):
            del meta.scrape_include_fields
        if hasattr(meta, 'scrape_exclude_fields'):
            del meta.scrape_exclude_fields

        # Pull the fields from our target model.
        try:
            target_fields = target_model._meta.fields + target_model._meta.many_to_many
        except:
            raise TypeError('Couldn\'t extract fields from target model in "%s", are you passing ' \
                                'the class itself, not the name?'%name);

        # Add the appropriate fields to our attribute dictionary.
        scraped_fields = []
        for field in target_fields:
            if field.name == 'id': # Skip the ID.
                continue
            if field.name in exclude_fields or (include_fields and field.name not in include_fields):
                continue
            scraped_fields.append(field)

            # Add the "valid" field.
            attname = field.name + '_valid'
            if attname in attrs:
                raise TypeError('Class attribute "%s" already exists for "%s".'%(attname, name))
            attrs[attname] = models.BooleanField(default=False)

            # Add the "source" field.
            attname = field.name + '_source'
            if attname in attrs:
                raise TypeError('Class attribute "%s" already exists for "%s".'%(attname, name))
            attrs[attname] = models.URLField(blank=True, null=True)

            # Add the "timestamp" field.
            attname = field.name + '_timestamp'
            if attname in attrs:
                raise TypeError('Class attribute "%s" already exists for "%s".'%(attname, name))
            attrs[attname] = models.DateTimeField(blank=True, null=True)

        # Add a foreign-key to the target model.
        if 'target' in attrs:
            raise TypeError('Conflict for "target" in "%s".'%name)
        attrs['target'] = models.OneToOneField(target_model, related_name='scrape')

        # Add an attribute to get the fields that are to be scraped.
        if '_scraped_fields' in attrs:
            raise TypeError('Conflict for "_scraped_fields" in "%s".'%name)
        attrs['_scraped_fields'] = scraped_fields

        # Call our parent's __new__.
        return super(ScrapeModelBase, cls).__new__(cls, name, bases, attrs)


class ScrapeModel(models.Model):
    __metaclass__ = ScrapeModelBase
