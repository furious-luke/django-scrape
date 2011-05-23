from django.contrib import admin
from django.forms.models import _get_foreign_key

import logging
logger = logging.getLogger(__name__)


def make_scrape_fieldsets(fieldsets, obj):
    if obj:

        # Remove references to scrape fields, except for the '_valid' guys.
        scrape_fields = [n for n in obj._scrape_fields if n[-6:] != '_valid']
        scrape_fields_set = set(scrape_fields)
        scrape_valid_fields_set = set(obj._scrape_valid_fields)
        target_fields_set = set(obj._scrape_target_fields)
        for name, options in fieldsets:
            fields = options.get('fields')
            if fields:
                new_fields = []
                for field_name in fields:
                    if field_name not in target_fields_set:
                        continue
                    new_fields.append(field_name)
                    valid_name = field_name + '_valid'
                    if valid_name in scrape_valid_fields_set:
                        new_fields.append(valid_name)
                options['fields'] = tuple(new_fields)

        # Append the new scrape fields fieldset.
        fieldsets = list(fieldsets)
        fieldsets.append(
            ('Scrape Metadata', {
                'classes': ('collapse',),
                'fields': scrape_fields,
            }),
        )
        fieldsets = tuple(fieldsets)

    return fieldsets


class ScrapeModelAdmin(admin.ModelAdmin):

    def __init__(self, *args, **kwargs):
        super(ScrapeModelAdmin, self).__init__(*args, **kwargs)
        list_filter = list(self.list_filter)
        list_filter.extend(self.model._scrape_valid_fields)
        self.list_filter = tuple(list_filter)

    def get_fieldsets(self, request, obj=None):
        fieldsets = super(ScrapeModelAdmin, self).get_fieldsets(request, obj)
        return make_scrape_fieldsets(fieldsets, obj)


class ScrapeStackedInline(admin.StackedInline):

    def get_fieldsets(self, request, obj=None):
        fieldsets = super(ScrapeStackedInline, self).get_fieldsets(request, obj)
        return make_scrape_fieldsets(fieldsets, self.model)


class ScrapeTabularInline(admin.TabularInline):

    def get_fieldsets(self, request, obj=None):
        fieldsets = super(ScrapeTabularInline, self).get_fieldsets(request, obj)
        return make_scrape_fieldsets(fieldsets, self.model)
