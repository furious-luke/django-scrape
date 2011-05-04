from django import forms


class ScrapeModelFormMetaclass(forms.ModelFormMetaclass):

    def __new__(cls, name, bases, attrs):

        # Redirect to the actual model we want.
        meta = attrs['Meta']
        scrape_model = meta.model
        model = scrape_model.Meta.scrape_target_model
        attrs['Meta'].model = model

        # To get a list of scrape model fields we need to first construct a
        # scrape model.
        obj = scrape_model()
        field_names = obj._meta.get_all_field_names()
        field_names_set = set([f if f[-len('_valid'):] == '_valid' for f in field_names])

        # Construct as if we are using the target model.
        new_class = super(ModelFormMetaclass, cls).__new__(cls, name, bases, attrs)

        # Loop over base_fields so that we can insert the appropriate scrape fields
        # in the correct order.
        new_base_fields = []
        for base_field in new_class.base_fields:
            new_base_fields.append(base_field)
            field_name = base_field[0].name + '_valid'

            # Do we have a connected scrape "valid" field?
            if field_name in field_names_set:
                new_base_fields.append((field_name, forms.BooleanField))


class ScrapeModelForm(forms.ModelForm):
    __metaclass__ = ScrapeModelFormMetaclass
