"""A Dracula-themed Swagger UI.

FastAPI's `/docs` is Swagger UI with its default stylesheet. This replaces the route
with the same page plus an override sheet, because Swagger UI ships no theming hook --
there is no palette to configure, only CSS to outrank.

Which is why the rules below are written against Swagger UI's own class names
(`.opblock-post`, `.scheme-container`) rather than anything semantic. That coupling is
real: a major Swagger UI upgrade can rename them and the page quietly reverts to white.
The test for this file therefore checks that the *page still renders*, not that any
particular rule took effect -- a theme that silently stops applying is a cosmetic
problem, and failing the suite over it would be worse than the white background.

Colours are the canonical Dracula palette. Methods are mapped by how much damage they
do: cyan reads, green creates, orange changes, red deletes.
"""

from __future__ import annotations

from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse

# https://draculatheme.com/contribute -- the official palette, unmodified.
BACKGROUND = "#282a36"
CURRENT_LINE = "#44475a"
SELECTION = "#44475a"
FOREGROUND = "#f8f8f2"
COMMENT = "#6272a4"
CYAN = "#8be9fd"
GREEN = "#50fa7b"
ORANGE = "#ffb86c"
PINK = "#ff79c6"
PURPLE = "#bd93f9"
RED = "#ff5555"
YELLOW = "#f1fa8c"

#: One rule per method, generated so a new HTTP verb cannot be styled inconsistently
#: by hand. Ordered by consequence: reading is safe, deleting is not.
METHOD_COLOURS = {
    "get": CYAN,
    "post": GREEN,
    "patch": ORANGE,
    "put": PURPLE,
    "delete": RED,
    "head": COMMENT,
    "options": COMMENT,
}


def _method_rules() -> str:
    return "\n".join(f"""
.swagger-ui .opblock.opblock-{method} {{
  background: rgba(68, 71, 90, .35);
  border-color: {colour};
}}
.swagger-ui .opblock.opblock-{method} .opblock-summary {{ border-color: {colour}; }}
.swagger-ui .opblock.opblock-{method} .opblock-summary-method {{
  background: {colour};
  color: {BACKGROUND};
  text-shadow: none;
  font-weight: 700;
}}
.swagger-ui .opblock.opblock-{method} .tab-header .tab-item.active h4 span::after {{
  background: {colour};
}}""" for method, colour in METHOD_COLOURS.items())


DRACULA_CSS = f"""
:root {{ color-scheme: dark; }}

body, .swagger-ui {{ background: {BACKGROUND}; color: {FOREGROUND}; }}

/* The default topbar is a green band advertising Swagger; the page already says
   what it is. */
.swagger-ui .topbar {{ display: none; }}

.swagger-ui, .swagger-ui .info li, .swagger-ui .info p, .swagger-ui .info table,
.swagger-ui .opblock-description-wrapper p, .swagger-ui .opblock-title_normal p,
.swagger-ui .response-col_status, .swagger-ui table thead tr td,
.swagger-ui table thead tr th, .swagger-ui .parameter__name,
.swagger-ui .parameter__type, .swagger-ui label, .swagger-ui .tab li,
.swagger-ui .opblock-tag small, .swagger-ui .responses-inner h4,
.swagger-ui .responses-inner h5 {{ color: {FOREGROUND}; }}

.swagger-ui .info .title,
.swagger-ui .opblock-tag {{ color: {PURPLE}; }}
.swagger-ui .info .title small pre {{ background: {CURRENT_LINE}; color: {FOREGROUND}; }}

/* The invariants live in the description, so they need to be readable prose rather
   than an afterthought. */
.swagger-ui .info .description h3 {{ color: {PINK}; }}
.swagger-ui .info .description table {{ border-color: {CURRENT_LINE}; }}
.swagger-ui .info .description td, .swagger-ui .info .description th {{
  border-color: {CURRENT_LINE};
  padding: .4em .8em;
}}
.swagger-ui .info .description code, .swagger-ui code {{
  background: {CURRENT_LINE};
  color: {YELLOW};
  padding: .1em .35em;
  border-radius: 3px;
}}

.swagger-ui .opblock-tag {{ border-color: {CURRENT_LINE}; }}
.swagger-ui .opblock {{ box-shadow: none; }}
.swagger-ui .opblock .opblock-summary-path,
.swagger-ui .opblock .opblock-summary-path__deprecated {{ color: {FOREGROUND}; }}
.swagger-ui .opblock .opblock-summary-description {{ color: {COMMENT}; }}
.swagger-ui .opblock-body {{ background: rgba(40, 42, 54, .6); }}
.swagger-ui .opblock-section-header {{
  background: {CURRENT_LINE};
  box-shadow: none;
}}
.swagger-ui .opblock-section-header h4,
.swagger-ui .opblock-section-header > label {{ color: {FOREGROUND}; }}

{_method_rules()}

/* Tables, parameters, responses */
.swagger-ui table {{ background: transparent; }}
.swagger-ui table thead tr td, .swagger-ui table thead tr th {{
  border-color: {CURRENT_LINE};
  color: {COMMENT};
}}
.swagger-ui .parameters-col_description input[type=text],
.swagger-ui select, .swagger-ui textarea, .swagger-ui input[type=text] {{
  background: {CURRENT_LINE};
  color: {FOREGROUND};
  border: 1px solid {COMMENT};
}}
.swagger-ui .parameter__name.required::after {{ color: {RED}; }}
.swagger-ui .parameter__type {{ color: {CYAN}; }}
.swagger-ui .prop-format {{ color: {COMMENT}; }}

/* Payload and response bodies */
.swagger-ui .highlight-code > .microlight,
.swagger-ui .body-param__example, .swagger-ui pre {{
  background: #21222c !important;
  color: {FOREGROUND};
  border-radius: 4px;
}}
.swagger-ui .microlight code {{ background: transparent; }}
.swagger-ui .response-col_description__inner div.markdown {{
  background: #21222c;
  color: {FOREGROUND};
}}

/* Buttons */
.swagger-ui .btn {{
  color: {FOREGROUND};
  border-color: {COMMENT};
  background: {CURRENT_LINE};
}}
.swagger-ui .btn.execute {{
  background: {GREEN};
  color: {BACKGROUND};
  border-color: {GREEN};
  font-weight: 700;
}}
.swagger-ui .btn.try-out__btn {{ border-color: {PURPLE}; color: {PURPLE}; }}
.swagger-ui .btn.cancel {{ border-color: {RED}; color: {RED}; }}
.swagger-ui .btn.authorize {{ border-color: {GREEN}; color: {GREEN}; }}
.swagger-ui .btn.authorize svg {{ fill: {GREEN}; }}

/* Models */
.swagger-ui section.models {{ border-color: {CURRENT_LINE}; }}
.swagger-ui section.models h4 {{ color: {PURPLE}; }}
.swagger-ui section.models .model-container {{ background: rgba(68, 71, 90, .35); }}
.swagger-ui .model-title, .swagger-ui .model {{ color: {FOREGROUND}; }}
.swagger-ui .model-toggle::after {{ filter: invert(1); }}
.swagger-ui .prop-type {{ color: {CYAN}; }}
.swagger-ui .model .property.primitive {{ color: {COMMENT}; }}

/* The enum values are the point of publishing them, so give them a colour that
   reads rather than the default grey. */
.swagger-ui .model .prop-enum, .swagger-ui .renderedMarkdown code {{ color: {YELLOW}; }}

.swagger-ui .scheme-container {{
  background: {CURRENT_LINE};
  box-shadow: none;
}}
.swagger-ui .dialog-ux .modal-ux {{
  background: {BACKGROUND};
  border-color: {COMMENT};
}}
.swagger-ui .dialog-ux .modal-ux-header h3,
.swagger-ui .dialog-ux .modal-ux-content h4,
.swagger-ui .dialog-ux .modal-ux-content p {{ color: {FOREGROUND}; }}

.swagger-ui svg:not(:root) {{ fill: {FOREGROUND}; }}
.swagger-ui .loading-container .loading::after {{ color: {FOREGROUND}; }}
::-webkit-scrollbar {{ width: 10px; height: 10px; }}
::-webkit-scrollbar-track {{ background: {BACKGROUND}; }}
::-webkit-scrollbar-thumb {{ background: {CURRENT_LINE}; border-radius: 5px; }}
::-webkit-scrollbar-thumb:hover {{ background: {COMMENT}; }}
"""


def swagger_ui(*, openapi_url: str, title: str) -> HTMLResponse:
    """The stock Swagger UI page with the override sheet appended.

    Appended rather than substituted: Swagger UI's own stylesheet still does the
    layout, and reimplementing that to change colours would be a far larger thing to
    keep working across upgrades.
    """
    page = get_swagger_ui_html(openapi_url=openapi_url, title=title)
    html = page.body.decode()
    html = html.replace("</head>", f"<style>{DRACULA_CSS}</style></head>")
    return HTMLResponse(html)
