from django.db import models
from django.db.models import fields
from django.db.models.base import ModelBase


class ScrapeModelMetaclass(ModelBase):

    ## Override creation.
    # We need to extract the target model from Meta, then create new fields on this class to
    # represent the validity of target model's fields.
    def __new__(cls, name, bases, attrs):

        def _is_target_field(field_name, include_fields, exclude_fields):
            return not (field_name in exclude_fields or (include_fields and field_name not in include_fields))

        # Find the Meta class in our attributes.
        meta = attrs.get('Meta', None)

        # Extract any meta information.
        include_fields = getattr(meta, 'scrape_include_fields', [])
        exclude_fields = getattr(meta, 'scrape_exclude_fields', [])

        # Delete our meta values as Django complains if it finds unknown values.
        if hasattr(meta, 'scrape_include_fields'):
            del meta.scrape_include_fields
        if hasattr(meta, 'scrape_exclude_fields'):
            del meta.scrape_exclude_fields

        # Pull the fields from our model.
        target_fields = []
        for field_name, value in attrs.iteritems():
            if not isinstance(value, fields.Field):
                continue
            target_fields.append((field_name, value))

        # If there are no target fields end it here.
        if not target_fields:
            return super(ScrapeModelMetaclass, cls).__new__(cls, name, bases, attrs)

        # Add the appropriate fields to our attribute dictionary.
        scrape_fields = []
        scrape_valid_fields = []
        for field_name, field in target_fields:
            if field_name in ['id', 'pk']: # Skip the primary key.
                continue
            if not _is_target_field(field_name, include_fields, exclude_fields):
                continue

            # Add the "valid" field.
            attname = field_name + '_valid'
            scrape_fields.append(attname)
            scrape_valid_fields.append(attname)
            if attname in attrs:
                raise TypeError('Class attribute "%s" already exists for "%s".'%(attname, name))
            attrs[attname] = models.BooleanField(default=False)

            # Add the "source" field.
            attname = field_name + '_source'
            scrape_fields.append(attname)
            if attname in attrs:
                raise TypeError('Class attribute "%s" already exists for "%s".'%(attname, name))
            attrs[attname] = models.URLField(verify_exists=False, blank=True, null=True)

            # Add the "timestamp" field.
            attname = field_name + '_timestamp'
            scrape_fields.append(attname)
            if attname in attrs:
                raise TypeError('Class attribute "%s" already exists for "%s".'%(attname, name))
            attrs[attname] = models.DateTimeField(blank=True, null=True)

        # Call our parent's __new__.
        inst = super(ScrapeModelMetaclass, cls).__new__(cls, name, bases, attrs)

        # Add an attribute to get the fields that are to be scraped.
        target_fields = [f[0] for f in target_fields]
        if hasattr(inst, '_scrape_target_fields'):
            raise TypeError('Conflict for "_scrape_target_fields" in "%s".'%name)
        inst._scrape_target_fields = target_fields
        if hasattr(inst, '_scrape_fields'):
            raise TypeError('Conflict for "_scrape_fields" in "%s".'%name)
        inst._scrape_fields = scrape_fields
        if hasattr(inst, '_scrape_valid_fields'):
            raise TypeError('Conflict for "_scrape_valid_fields" in "%s".'%name)
        inst._scrape_valid_fields = scrape_valid_fields

        # Return the instance.
        return inst




class ScrapeModel(models.Model):
    __metaclass__ = ScrapeModelMetaclass

    class Meta:
        abstract = True
