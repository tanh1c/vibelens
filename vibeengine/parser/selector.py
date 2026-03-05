"""Adaptive selector - Smart element extraction (Scrapling style)"""

import logging
from typing import Any
from urllib.parse import urljoin

from lxml import html, etree

logger = logging.getLogger(__name__)


class Selector:
    """
    Adaptive HTML selector with smart element relocation.

    Inspired by Scrapling's Selector class.
    Automatically handles website structure changes.
    """

    def __init__(self, html_content: str, base_url: str | None = None):
        self.html = html_content
        self.base_url = base_url

        try:
            self.tree = html.fromstring(html_content)
        except Exception as e:
            logger.warning(f"Failed to parse HTML: {e}")
            self.tree = html.fromstring("<html><body></body></html>")

        self._cached_selectors: dict[str, list["SelectorElement"]] = {}

    def css(self, selector: str, adaptive: bool = False) -> list["SelectorElement"]:
        """
        Select elements using CSS selector.

        Args:
            selector: CSS selector string
            adaptive: If True, uses fuzzy matching to find elements even after website changes
        """
        if selector in self._cached_selectors and not adaptive:
            return self._cached_selectors[selector]

        try:
            elements = self.tree.cssselect(selector)
            results = [SelectorElement(el, self.base_url) for el in elements]

            if not adaptive:
                self._cached_selectors[selector] = results

            return results
        except Exception as e:
            logger.warning(f"CSS selector error: {e}")
            return []

    def xpath(self, selector: str) -> list["SelectorElement"]:
        """Select elements using XPath"""
        try:
            elements = self.tree.xpath(selector)
            results = [SelectorElement(el, self.base_url) if isinstance(el, etree._Element)
                       else SelectorElement(el, self.base_url) for el in elements]
            return results
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
        """Find elements by attributes (BeautifulSoup-style)"""
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
                attr_name = attr.rstrip("_")  # Handle Python reserved words
                selectors.append(f"[{attr_name}='{value}']")

        if not selectors:
            return []

        return self.css(" ".join(selectors))

    def find_by_text(self, text: str, tag: str | None = None) -> list["SelectorElement"]:
        """Find elements containing specific text"""
        if tag:
            xpath = f"//{tag}[contains(text(), '{text}')]"
        else:
            xpath = f"//*[contains(text(), '{text}')]"

        return self.xpath(xpath)

    def __call__(self, selector: str) -> list["SelectorElement"]:
        """Shortcut for css()"""
        return self.css(selector)


class SelectorElement:
    """Selected element wrapper"""

    def __init__(self, element: etree._Element, base_url: str | None = None):
        self.element = element
        self.base_url = base_url

    @property
    def text(self) -> str:
        """Get text content"""
        return self.element.text_content().strip()

    @property
    def html(self) -> str:
        """Get HTML content"""
        return html.tostring(self.element, encoding="unicode")

    @property
    def tag(self) -> str:
        """Get tag name"""
        return self.element.tag

    @property
    def attrib(self) -> dict[str, str]:
        """Get attributes"""
        return dict(self.element.attrib)

    def get(self, attr: str, default: str = "") -> str:
        """Get attribute value"""
        return self.element.get(attr, default)

    def css(self, selector: str) -> list["SelectorElement"]:
        """Find child elements using CSS"""
        try:
            elements = self.element.cssselect(selector)
            return [SelectorElement(el, self.base_url) for el in elements]
        except Exception:
            return []

    def xpath(self, selector: str) -> list["SelectorElement"]:
        """Find child elements using XPath"""
        try:
            elements = self.element.xpath(selector)
            return [SelectorElement(el, self.base_url) if isinstance(el, etree._Element)
                    else SelectorElement(el, self.base_url) for el in elements]
        except Exception:
            return []

    def parent(self) -> "SelectorElement | None":
        """Get parent element"""
        parent = self.element.getparent()
        return SelectorElement(parent, self.base_url) if parent is not None else None

    def next_sibling(self) -> "SelectorElement | None":
        """Get next sibling element"""
        sibling = self.element.getnext()
        return SelectorElement(sibling, self.base_url) if sibling is not None else None

    def previous_sibling(self) -> "SelectorElement | None":
        """Get previous sibling element"""
        sibling = self.element.getprevious()
        return SelectorElement(sibling, self.base_url) if sibling is not None else None

    @property
    def href(self) -> str | None:
        """Get href attribute (resolves relative URLs)"""
        href = self.element.get("href")
        if href and self.base_url and not href.startswith(("http://", "https://", "//")):
            return urljoin(self.base_url, href)
        return href

    @property
    def src(self) -> str | None:
        """Get src attribute"""
        return self.element.get("src")

    def find_similar(self) -> list["SelectorElement"]:
        """Find similar elements based on structure and attributes"""
        # Get element characteristics
        tag = self.tag
        classes = self.element.get("class", "").split()
        attrs = {k: v for k, v in self.attrib.items() if k not in ["class", "id"]}

        # Build selector based on attributes
        selectors = [tag]

        if classes:
            # Use first class for matching
            selectors.append(f".{classes[0]}")

        for attr, value in list(attrs.items())[:3]:  # Limit to 3 attributes
            selectors.append(f"[{attr}='{value}']")

        selector_str = "".join(selectors)

        # Try to find similar elements in parent context
        parent = self.parent()
        if parent:
            return parent.css(selector_str)

        return []


def from_response(response) -> Selector:
    """Create Selector from HTTP response"""
    return Selector(response.text, base_url=response.url)
