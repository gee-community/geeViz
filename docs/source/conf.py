# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here.
import pathlib
import sys, os, re, shutil

# sys.path.insert(0, os.path.abspath("..Examples/"))
# sys.path.insert(0, os.path.abspath(".."))

# sys.path.insert(0, pathlib.Path(__file__).parents[2].resolve().as_posix())
# sys.path.insert(0, os.path.abspath(".../simulator"))
# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information


def GetVersion(initPath):
    with open(initPath) as f:
        return f.read().split("__version__ = ")[-1][:-1]
        # return re.findall(r"__version__\s*=\s*\'([.\d]+)\'", f.read())[0]


build_folder = r"A:\GEE\gee_py_modules_package\geeViz\docs\build"
info_folder = r"A:\GEE\gee_py_modules_package\geeViz\docs\source\info"
if os.path.exists(build_folder):
    shutil.rmtree(build_folder)
if os.path.exists(info_folder):
    shutil.rmtree(info_folder)

initPath = r"A:\GEE\gee_py_modules_package\geeViz\__init__.py"
project = "geeViz"
copyright = "2024, Ian Housman, Josh Heyer"
author = "Ian Housman, Josh Heyer"
release = GetVersion(initPath)

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.coverage",
    "sphinx.ext.napoleon",
]

templates_path = ["_templates"]
exclude_patterns = []


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "furo"
html_static_path = ["_static"]

dark_text_color = "#00bfa5"
light_text_color = "#00897b"

html_logo = f"./{html_static_path[0]}/RCR-logo.jpg"
html_favicon = html_logo
pygments_style = "sphinx"
pygments_dark_style = "monokai"

html_title = f"{project} {release} docs"

# googleanalytics_id = "G-FZJPNRXYD2"

html_theme_options = {
    "announcement": f"<i>geeViz</i> docs are still in development",
    "light_css_variables": {
        "color-brand-primary": light_text_color,
        "color-brand-content": light_text_color,
        # "color-admonition-background": text_color,
        "font-stack": "Roboto, sans-serif",
        "font-stack--monospace": "Courier, monospace",
    },
    "dark_css_variables": {
        "color-brand-primary": dark_text_color,
        "color-brand-content": dark_text_color,
        # "color-admonition-background": text_color,
        "font-stack": "Roboto, sans-serif",
        "font-stack--monospace": "Courier, monospace",
    },
    "footer_icons": [
        {
            "name": "RedCastle Resources Inc",
            "url": "https://www.redcastleresources.com/",
            "html": f"<img src='{html_logo}'  alt='RedCastle Inc. Logo' href='#' title='Click to learn more about RedCastle Resources Inc.'>",
            "class": "",
        },
    ],
}
