# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys

sys.path.insert(0, os.path.abspath("../.."))

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "Ragnerock"
copyright = "2026, john@ragnerock.com, matthew@ragnerock.com"
author = "john@ragnerock.com, matthew@ragnerock.com"
release = "0.1.0"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "myst_parser",
]

templates_path = ["_templates"]
exclude_patterns = []

# -- Autodoc -----------------------------------------------------------------

autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
    "member-order": "bysource",
    "special-members": "__init__",
    "exclude-members": "__weakref__,model_config,model_fields,model_computed_fields",
}
autodoc_typehints = "description"
autodoc_typehints_description_target = "documented"
autoclass_content = "class"
autosummary_generate = True

# -- Napoleon (Google-style docstrings) --------------------------------------

napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = False
napoleon_use_admonition_for_notes = True
napoleon_use_admonition_for_references = False
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_preprocess_types = True
napoleon_attr_annotations = True

# -- Intersphinx -------------------------------------------------------------

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "pydantic": ("https://docs.pydantic.dev/latest/", None),
}

# -- MyST --------------------------------------------------------------------

myst_enable_extensions = [
    "colon_fence",
    "deflist",
]
myst_heading_anchors = 3

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "furo"
html_title = "Ragnerock"
html_static_path = ["_static"]
html_css_files = ["ragnerock.css"]
html_favicon = "_static/favicon.svg"
html_logo = "_static/ragnerock-logo.svg"

# Furo theme options
html_theme_options = {
    "sidebar_hide_name": True,
    "light_css_variables": {
        "color-brand-primary": "#3b7ef0",
        "color-brand-content": "#2563eb",
        "font-stack": "Inter, -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Helvetica Neue', sans-serif",
        "font-stack--monospace": "'JetBrains Mono', 'SF Mono', Monaco, Consolas, 'Liberation Mono', monospace",
    },
    "dark_css_variables": {
        "color-brand-primary": "#3b7ef0",
        "color-brand-content": "#5c9ef3",
        "font-stack": "Inter, -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Helvetica Neue', sans-serif",
        "font-stack--monospace": "'JetBrains Mono', 'SF Mono', Monaco, Consolas, 'Liberation Mono', monospace",
    },
    "footer_icons": [
        {
            "name": "Ragnerock",
            "url": "https://ragnerock.com",
            "html": "ragnerock.com",
            "class": "",
        },
    ],
}

# Default to dark mode to match the site.
pygments_style = "default"
pygments_dark_style = "monokai"
