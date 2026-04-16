import pytest
from src.parser import clean_html, parse_html_to_chunks
from bs4 import BeautifulSoup


def test_clean_html():
    html = """
    <html>
        <body>
            <header>Header</header>
            <nav>Nav</nav>
            <main>
                <h1>Title</h1>
                <p>Content</p>
                <script>alert(1)</script>
            </main>
            <footer>Footer</footer>
        </body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    main = clean_html(soup)

    text = main.get_text()
    assert "Header" not in text
    assert "Nav" not in text
    assert "Footer" not in text
    assert "alert(1)" not in text
    assert "Title" in text
    assert "Content" in text


def test_parse_html_to_chunks():
    html = """
    <html>
        <body>
            <main>
                <h1>Page Title</h1>
                <p>Intro text</p>
                <h2>Section 1</h2>
                <p>Section 1 text</p>
                <h3>Subsection</h3>
                <p>Sub text</p>
                <h2>Section 2</h2>
                <ul>
                    <li>Item A</li>
                    <li>Item B</li>
                </ul>
            </main>
        </body>
    </html>
    """

    chunks = parse_html_to_chunks(html, "http://test.com", "1.0")

    assert len(chunks) == 4

    # Chunk 1
    assert chunks[0]["breadcrumbs"] == ["Page Title"]
    assert chunks[0]["content"] == "Intro text"

    # Chunk 2
    assert chunks[1]["breadcrumbs"] == ["Page Title", "Section 1"]
    assert chunks[1]["content"] == "Section 1 text"

    # Chunk 3
    assert chunks[2]["breadcrumbs"] == ["Page Title", "Section 1", "Subsection"]
    assert chunks[2]["content"] == "Sub text"

    # Chunk 4
    assert chunks[3]["breadcrumbs"] == ["Page Title", "Section 2"]
    assert "Item A" in chunks[3]["content"]
    assert "Item B" in chunks[3]["content"]
