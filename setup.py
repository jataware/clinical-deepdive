from setuptools import find_packages, setup

"""
version managed by bump2version
"""
VERSION = "0.1.0"


def read_requirements(path: str):
    with open(path) as f:
        return f.read().splitlines()


setup(
    name="clinical-deepdive",
    version=VERSION,
    platforms=["POSIX"],
    python_requires=">= 3.8",
    package_dir={"": "src"},
    packages=find_packages("src", exclude=["tests"]),
    include_package_data=True,
    test_suite="tests",
    install_requires=read_requirements("requirements.txt"),
    zip_safe=False,
    entry_points={
        "console_scripts": ["clinical-deepdive=clinical_deepdive.app:main"],
    },
)
