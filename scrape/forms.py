from django import forms
from django.forms.models import ModelFormMetaclass
from django.utils.datastructures import SortedDict


class ScrapeModelFormMetaclass(ModelFormMetaclass):

    def __new__(cls, name, bases, attrs):

        # If we don't have a model yet, just proceed as a regular ModelForm.
        meta = attrs.get('Meta')
        if not meta:
            return super(ScrapeModelFormMetaclass, cls).__new__(cls, name, bases, attrs)

        # We get given both the target model and the scrape model.
        scrape_model = meta.scrape_model
#        del meta.scrape_model

        # To get a list of scrape model fields we need to first construct a
        # scrape model.
        fields = scrape_model._scraped_fields
        field_names = [f.name + '_valid' for f in fields]
        field_names_set = set(field_names)

        # Construct as if we are using the target model.
        new_class = super(ScrapeModelFormMetaclass, cls).__new__(cls, name, bases, attrs)

        # Loop over base_fields so that we can insert the appropriate scrape fields
        # in the correct order.
        new_base_fields = []
        for base_field in new_class.base_fields.iteritems():
            new_base_fields.append(base_field)
            field_name = base_field[0] + '_valid'

            # Do we have a connected scrape "valid" field?
            if field_name in field_names_set:
                new_base_fields.append((field_name, forms.BooleanField(required=False)))

        # Stomp/add new attributes.
        new_class.base_fields = SortedDict(new_base_fields)
        new_class._scrape_field_names = list(field_names_set)

        return new_class


class ScrapeModelForm(forms.ModelForm):
    __metaclass__ = ScrapeModelFormMetaclass

    def __init__(self, *args, **kwargs):
        super(ScrapeModelForm, self).__init__(*args, **kwargs)

        # Pull the values from the instance, if it is passed in.
        inst = kwargs.get('instance')
        if inst:

            # Make sure we actually have a scrape model.
            try:
                scrape_obj = inst.scrape
            except:
                scrape_obj = None
            if scrape_obj:
                for field_name in self._scrape_field_names:
                    self.initial[field_name] = getattr(scrape_obj, field_name)

    def save(self, commit=True):
        obj = super(ScrapeModelForm, self).save(commit=False)

        # Set values on the scrape object.
        try:
            scrape_obj = obj.scrape
        except:
            scrape_obj = None
        if scrape_obj:
            for field_name in self._scrape_field_names:
                setattr(scrape_obj, field_name, self.cleaned_data[field_name])

        if commit:
            obj.save()

        # Unfortunately we have to commit the scrape object immediately, as the admin site
        # won't do it for us.
        scrape_obj.save()

        return obj
