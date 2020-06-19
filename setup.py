import io
import os
import re

from setuptools import find_packages
from setuptools import setup
import versioneer


def read(filename):
    filename = os.path.join(os.path.dirname(__file__), filename)
    text_type = type(u"")
    with io.open(filename, mode="r", encoding="utf-8") as fd:
        return re.sub(text_type(r":[a-z]+:`~?(.*?)`"), text_type(r"``\1``"), fd.read())


setup(
    version=versioneer.get_version(),
    cmdclass=versioneer.get_cmdclass(),
    name="generic_scpi_driver",
    url="http://gitlab.npl.co.uk/yourname/packagename",
    license="None",
    author="Charles Baynham",
    author_email="charles.baynham@npl.co.uk",
    description="A generic template for creating python object-based drivers for SCPI hardware devices which communicate via VISA. Compatible with ARTIQ. ",
    long_description=read("README.rst"),
    packages=find_packages(exclude=("tests",)),
    install_requires=["pyvisa"],
    extras_require={"dev": ["pre-commit", "tox", "sphinx", "sphinx_rtd_theme"]},
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
    ],
)
