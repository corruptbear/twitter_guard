from os.path import dirname, join, abspath
from setuptools import setup
from setuptools.command.install import install

setup_args = {
    'cmdclass': {'install': install},
    'name': 'twitter_guard',
    'version': "0.0.1",
    'license': 'MIT',
    'description': 'Personal Anti-Harassment Twitter Bot',
    'long_description': open(join(abspath(dirname(__file__)), "docs/README.md")).read(),
    'long_description_content_type': 'text/markdown',
    'url': 'https://github.com/corruptbear/twitter_guard',
    'project_urls': {
        'Bug Tracker': 'https://github.com/corruptbear/twitter_guard/issues',
        'Documentation': 'https://github.com/corruptbear/twitter_guard/docs/README.md',
        'Source Code': 'https://github.com/corruptbeartwitter_guard',
    },
    'python_requires': '~=3.9',
    #'classifiers': ['Development Status :: 5 - Production/Stable',
    #                'Intended Audience :: Developers',
    #                'License :: OSI Approved :: Apache Software License',
    #                'Operating System :: POSIX',
    #                'Operating System :: Microsoft :: Windows',
    #                'Operating System :: MacOS :: MacOS X',
    #                'Topic :: Software Development :: Testing',
    #                'Topic :: Software Development :: Libraries',
    #                'Programming Language :: Python :: 3.9'],
    'package_dir': {
        'twitter_guard': 'twitter_guard',
        #'twitter_guard.common': 'twitter_guard/common',
    },
    'packages': ['twitter_guard',
                 #'twitter_guard.common',
             ],
    'include_package_data': True,
    'install_requires': [
        'matplotlib~=3.7.1',
        'numpy~=1.22.3',
        'pyparsing~=3.0.9',
        'python_dateutil~=2.8.2',
        'pytz~=2020.4',
        'PyYAML~=6.0',
        'requests~=2.28.2',
        'selenium>=4.8.3',
        'snscrape>=0.6.1.20230314',
        'webdriver_manager==3.8.5',
    ],
    'zip_safe': False
}

setup(**setup_args)
