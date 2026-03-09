"""
Adaptive selector - Smart element extraction using Parsel.

Benefits of Parsel over raw lxml:
- Scrapy-like API (familiar to many developers)
- Cleaner CSS and XPath support
- Built-in text extraction utilities
- Better handling of encoding
- Automatic cleaning utilities
"""

import logging
from typing import Any
from urllib.parse import urljoin

from parsel import Selector as ParselSelector

logger = logging.getLogger(__name__)


class Selector:
    """
    Adaptive HTML selector with smart element extraction.

    Uses Parsel library (same as Scrapy) for robust parsing.
    Provides both CSS and XPath selectors with caching.
    """

    def __init__(self, html_content: str, base_url: str | None = None):
        self.html = html_content
        self.base_url = base_url
        self._selector = ParselSelector(text=html_content)
        self._cached_selectors: dict[str, list["SelectorElement"]] = {}

    def css(self, selector: str) -> list["SelectorElement"]:
        """
        Select elements using CSS selector.

        Args:
            selector: CSS selector string (supports pseudo-elements like ::text, ::attr(name))
        """
        if selector in self._cached_selectors:
            return self._cached_selectors[selector]

        try:
            elements = self._selector.css(selector)
            results = [SelectorElement(el, self.base_url) for el in elements]
            self._cached_selectors[selector] = results
            return results
        except Exception as e:
            logger.warning(f"CSS selector error: {e}")
            return []

    def xpath(self, selector: str) -> list["SelectorElement"]:
        """Select elements using XPath."""
        try:
            elements = self._selector.xpath(selector)
            return [SelectorElement(el, self.base_url) for el in elements]
        except Exception as e:
            logger.warning(f"XPath error: {e}")
            return []

    def find_all(
        self,
        tag: str | None = None,
        class_: str | None = None,
        id: str | None = None,
        **kwargs: Any,
    ) -> list["SelectorElement"]:
        """Find elements by attributes (BeautifulSoup-style)."""
        selectors = []

        if tag:
            selectors.append(tag)

        if class_:
            selectors.append(f".{class_}")

        if id:
            selectors.append(f"#{id}")

        # Add other attributes
        for attr, value in kwargs.items():
            if value:
                attr_name = attr.rstrip("_")
                selectors.append(f"[{attr_name}='{value}']")

        if not selectors:
            return []

        return self.css("".join(selectors))

    def find_by_text(self, text: str, tag: str | None = None) -> list["SelectorElement"]:
        """Find elements containing specific text (safe from injection)."""
        # Use Parsel's pseudo-selector for text containment
        if tag:
            selector = f"{tag}:contains('{text}')"
        else:
            selector = f"*:contains('{text}')"
        return self.css(selector)

    def get_text(self) -> str:
        """Get all text content from the document."""
        return self._selector.get().strip()

    def get_all_links(self) -> list[dict[str, str]]:
        """Extract all links with their text and href."""
        links = []
        for el in self.css("a"):
            href = el.href
            if href:
                links.append({
                    "text": el.text.strip(),
                    "href": href,
                })
        return links

    def get_images(self) -> list[dict[str, str]]:
        """Extract all images with src and alt."""
        images = []
        for el in self.css("img"):
            src = el.src
            if src:
                images.append({
                    "src": src,
                    "alt": el.get("alt", ""),
                })
        return images

    def get_forms(self) -> list[dict[str, Any]]:
        """Extract all forms with their inputs."""
        forms = []
        for form in self.css("form"):
            inputs = []
            for inp in form.css("input, select, textarea"):
                inputs.append({
                    "type": inp.get("type", "text"),
                    "name": inp.get("name", ""),
                    "value": inp.get("value", ""),
                })
            forms.append({
                "action": form.get("action", ""),
                "method": form.get("method", "GET").upper(),
                "inputs": inputs,
            })
        return forms

    def __call__(self, selector: str) -> list["SelectorElement"]:
        """Shortcut for css()."""
        return self.css(selector)


class SelectorElement:
    """Selected element wrapper with useful utilities."""

    def __init__(self, element: ParselSelector, base_url: str | None = None):
        self._element = element
        self.base_url = base_url

    @property
    def text(self) -> str:
        """Get text content (excluding HTML tags)."""
        # Use xpath string() to extract text only
        return ''.join(self._element.xpath('.//text()').getall()).strip()

    @property
    def html(self) -> str:
        """Get HTML content."""
        return self._element.get()

    @property
    def tag(self) -> str:
        """Get tag name."""
        # Parsel doesn't expose tag directly, extract from root
        return self._element.root.tag if hasattr(self._element.root, 'tag') else ''

    @property
    def attrib(self) -> dict[str, str]:
        """Get attributes."""
        return dict(self._element.root.attrib) if hasattr(self._element.root, 'attrib') else {}

    def get(self, attr: str, default: str = "") -> str:
        """Get attribute value."""
        return self._element.attrib.get(attr, default)

    def css(self, selector: str) -> list["SelectorElement"]:
        """Find child elements using CSS."""
        return [SelectorElement(el, self.base_url) for el in self._element.css(selector)]

    def xpath(self, selector: str) -> list["SelectorElement"]:
        """Find child elements using XPath."""
        return [SelectorElement(el, self.base_url) for el in self._element.xpath(selector)]

    def parent(self) -> "SelectorElement | None":
        """Get parent element."""
        parent = self._element.root.getparent() if hasattr(self._element.root, 'getparent') else None
        if parent is not None:
            # Wrap parent in a ParselSelector-like wrapper
            parent_selector = ParselSelector(root=parent)
            return SelectorElement(parent_selector, self.base_url)
        return None

    @property
    def href(self) -> str | None:
        """Get href attribute (resolves relative URLs)."""
        href = self._element.attrib.get("href")
        if href and self.base_url and not href.startswith(("http://", "https://", "//")):
            return urljoin(self.base_url, href)
        return href

    @property
    def src(self) -> str | None:
        """Get src attribute."""
        return self._element.attrib.get("src")

    def find_similar(self) -> list["SelectorElement"]:
        """Find similar elements based on structure and attributes."""
        classes = self._element.attrib.get("class", "").split()

        # Build selector based on tag and first class
        selector_parts = []
        if self.tag:
            selector_parts.append(self.tag)
        if classes:
            selector_parts.append(f".{classes[0]}")

        if not selector_parts:
            return []

        selector_str = "".join(selector_parts)
        return self.css(selector_str)

    def __repr__(self) -> str:
        return f"<SelectorElement tag={self.tag}>"


def from_response(response) -> Selector:
    """Create Selector from HTTP response."""
    return Selector(response.text, base_url=str(response.url))


def from_file(file_path: str, encoding: str = "utf-8") -> Selector:
    """Create Selector from HTML file."""
    with open(file_path, "r", encoding=encoding) as f:
        return Selector(f.read())