import os
from setuptools import setup, find_packages

setup(
    name='django-scrape',
    version='0.1',
    url='https://github.com/furious-luke/django-scrape',
    license='BSD',
    description='A django application for easier web scraping.',
    long_description=open(os.path.join(os.path.dirname(__file__), 'README.rst')).read(),
    author='Luke Hodkinson',
    author_email='furious.luke@gmail.com',
    packages=find_packages(),
    include_package_data=True,
    package_data={'': ['*.txt', '*.js', '*.html', '*.*']},
    install_requires=['setuptools'],
    classifiers = [
        'Framework :: Django',
        'Operating System :: OS Independent',
        'Programming Language :: Python'
    ]
)
