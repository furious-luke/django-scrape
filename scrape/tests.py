from django.test import TestCase
from django.db import IntegrityError
from django.db import models
import models as scrape_models


class ScrapeModelBaseTestCase(TestCase):

    def setUp(self):
        class Target(models.Model):
            f1 = models.CharField()
            f2 = models.FloatField()

        self.Target = Target

    def test_bad_target(self):
        def do_test():
            class TestModel(scrape_models.ScrapeModel):
                class Meta:
                    scrape_target_model = None
        self.assertRaises(TypeError, do_test)

    def test_new(self):
        class TestNewModel(scrape_models.ScrapeModel):
            class Meta:
                scrape_target_model = self.Target

        fields = TestNewModel._meta.fields
        self.assertEquals(fields[2].name, 'f1_valid')
        self.assertIsInstance(fields[2], models.BooleanField)
        self.assertEquals(fields[3].name, 'f1_source')
        self.assertIsInstance(fields[3], models.URLField)
        self.assertEquals(fields[4].name, 'f1_timestamp')
        self.assertIsInstance(fields[4], models.DateTimeField)
        self.assertEquals(fields[5].name, 'f2_valid')
        self.assertIsInstance(fields[5], models.BooleanField)
        self.assertEquals(fields[6].name, 'f2_source')
        self.assertIsInstance(fields[6], models.URLField)
        self.assertEquals(fields[7].name, 'f2_timestamp')
        self.assertIsInstance(fields[7], models.DateTimeField)
        self.assertEquals(fields[8].name, 'target')
        self.assertIsInstance(fields[8], models.OneToOneField)

    def test_exclude(self):
        class TestExcludeModel(scrape_models.ScrapeModel):
            class Meta:
                scrape_target_model = self.Target
                scrape_exclude_fields = ('f1',)

        fields = TestExcludeModel._meta.fields
        self.assertEquals(fields[2].name, 'f2_valid')
        self.assertIsInstance(fields[2], models.BooleanField)
        self.assertEquals(fields[3].name, 'f2_source')
        self.assertIsInstance(fields[3], models.URLField)
        self.assertEquals(fields[4].name, 'f2_timestamp')
        self.assertIsInstance(fields[4], models.DateTimeField)
        self.assertEquals(fields[5].name, 'target')
        self.assertIsInstance(fields[5], models.OneToOneField)

    def test_include(self):
        class TestIncludeModel(scrape_models.ScrapeModel):
            class Meta:
                scrape_target_model = self.Target
                scrape_include_fields = ('f2',)

        fields = TestIncludeModel._meta.fields
        self.assertEquals(fields[2].name, 'f2_valid')
        self.assertIsInstance(fields[2], models.BooleanField)
        self.assertEquals(fields[3].name, 'f2_source')
        self.assertIsInstance(fields[3], models.URLField)
        self.assertEquals(fields[4].name, 'f2_timestamp')
        self.assertIsInstance(fields[4], models.DateTimeField)
        self.assertEquals(fields[5].name, 'target')
        self.assertIsInstance(fields[5], models.OneToOneField)
