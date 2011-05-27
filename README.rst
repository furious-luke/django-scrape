=============
django-scrape
=============

Description
===========

TODO

Dependencies
============

Just a couple of little packages I use to store my common utilities. It's
a bit annoying having to install these two packages, in the future I'll
embed them in ``django-scrape``.

  python-utils
    A small collection of simple Python utilities, found at
    "http://gitbub.com/furious-luke/python-utils".

  django-utils
    Some Django utilities, found at
    "http://gitbub.com/furious-luke/python-utils".

Building
========

Placing the ``djangoutils`` folder in your Python path (``PYTHONPATH``)
is sufficient, however if you'd prefer to install system-wide then
use ``setup.py``::

  sudo python setup.py install

Simple Example
==============

Learning by example is probably the easist way...

Setting up a Django model
-------------------------

The first step is to inherit any models you'd like to scrape from
the ``ScrapeModel`` class::

  from django.db import models
  from scrape.models import ScrapeModel

  class MyModel(ScrapeModel):
    text = models.CharField(max_length=100)

This automatically sets up meta information for each field in your
model. In this example you'll have the following fields provided::

  class MyModel(ScrapeModel):
    ...
    text_valid = models.BooleanField()
    text_timestamp = models.DateTimeField()
    text_source = models.URLField()
    ...

These are intended to indicate, in order, whether the field has been
validated manually, the last time at which the field was scraped
and from which site the field was scraped.

Preparing your Scrapy project
-----------------------------

The second step is to setup a Scrapy project and create the scrape
items. I'm going to assume you're familiar with Scrapy and can
setup a project. In your ``items.py`` you can specify items that
can be scraped directly into ``MyModel`` like this::

  from scrape.scrapy.items import *
  from <your_django_project> import MyModel

  class MyModel(DjangoItem):
    django_model = MyModel

This will automatically setup the required field on your Scrapy item; in
this case it will just be the ``text`` field (the automatically
generated scrape fields are also created, but they get filled in
automatically and as such don't need to be considered).

Your Scrapy spiders will also need to be modified a little. The simplest way
to ensure your scrape meta data is being filled correctly is to use
a ``DjangoXPathItemLoader`` in place of the conventional ``XPathItemLoader``
provided by Scrapy. The following snippet is a method on the Scrapy spider
used to scrape into ``MyModel``::

  def parse_some_page(self, response):
    ldr = DjangoXPathItemLoader(MyModel(), reponse, response.url)
    ldr.add_xpath('text', 'some selector')
    yield ldr.load_item()

The creation of the ``DjangoXPathItemLoader`` needs some explanation.
The first two arguements are self explanatory, but the last is a
little tricky. In order to properly handle ``ForeignKey`` fields in
Django models each scraped item that refers to a model must be given
a unique identifier of some kind. In this case I'm using the
URL of the page from which I've scraped this item. This may not
always be unique, so it's up to you to figure out how to provide
this uniqueness. I'll explain more about ``ForeignKey`` fields
later.

The last thing needed to setup a Scrapy project is some changes to
the ``settings.py`` file. Firstly, you'll need to setup your 
environment to find your Django project::

  os.environ['DJANGO_SETTINGS_MODULE'] = '<your_django_project>.settings'

You'll also need to add a pipeline::

  ITEM_PIPELINES = [
    ...
    'scrape.scrapy.pipelines.DjangoItemPipeline',
    ...
  ]

Using the "valid" fields
------------------------

Handling "ForeignKey" fields
----------------------------
