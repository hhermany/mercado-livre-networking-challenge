from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "templates"


class TemplateRenderer:
    """Render network device configurations from Jinja2 templates."""

    def __init__(self) -> None:
        self.environment = Environment(
            loader=FileSystemLoader(TEMPLATE_DIR),
            undefined=StrictUndefined,
            autoescape=False,
            keep_trailing_newline=True,
        )

    def render(self, template_path: str, context: dict) -> str:
        """Render a template using the provided context."""

        template = self.environment.get_template(template_path)

        return template.render(**context)
