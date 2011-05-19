from django.contrib import admin
from django.forms.models import _get_foreign_key

import logging
logger = logging.getLogger(__name__)


def make_scrape_fieldsets(fieldsets, obj):
    if obj:

        # Remove references to scrape fields.
        scrape_fields_set = set(obj._scrape_fields)
        for name, options in fieldsets:
            fields = options.get('fields')
            if fields:
                options['fields'] = tuple([f for f in fields if f not in scrape_fields_set])

        # Append the new scrape fields fieldset.
        fieldsets = list(fieldsets)
        fieldsets.append(
            ('Scrape Metadata', {
                'classes': ('collapse',),
                'fields': obj._scrape_fields,
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
