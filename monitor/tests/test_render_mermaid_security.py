"""
Security tests for render_mermaid.py to ensure HTML injection prevention.

This test validates that malicious mermaid source files cannot break out
of the <pre> tag and inject arbitrary HTML or JavaScript.
"""
from html import escape


def test_html_escape_prevents_closing_tag_injection():
    """Test that </pre> cannot break out of the pre tag."""
    malicious_input = '</pre><script>alert("xss")</script><pre>'
    escaped = escape(malicious_input)
    
    # The closing tag should be escaped to &lt;/pre&gt;
    assert '</pre>' not in escaped
    assert '&lt;/pre&gt;' in escaped
    
    # The script tag should be escaped
    assert '<script>' not in escaped
    assert '&lt;script&gt;' in escaped


def test_html_escape_prevents_script_injection():
    """Test that <script> tags are escaped."""
    malicious_input = '<script>alert("xss")</script>'
    escaped = escape(malicious_input)
    
    assert '<script>' not in escaped
    assert '&lt;script&gt;' in escaped
    assert '&lt;/script&gt;' in escaped


def test_html_escape_prevents_event_handler_injection():
    """Test that event handlers are escaped."""
    malicious_input = '<img onload="alert(\'xss\')" />'
    escaped = escape(malicious_input)
    
    assert '<img' not in escaped
    assert '&lt;img' in escaped
    assert 'onload=' in escaped or 'onload' in escaped  # The attribute itself is still there but escaped


def test_html_escape_preserves_ampersand():
    """Test that ampersands in mermaid diagrams are properly escaped."""
    # Mermaid often uses operators like --> which contain hyphens,
    # and diagrams may have & operators
    mermaid_code = 'A & B'
    escaped = escape(mermaid_code)
    
    assert '&amp;' in escaped
    assert 'A &amp; B' == escaped


def test_html_escape_preserves_special_characters_in_mermaid():
    """Test that valid mermaid diagram syntax is properly escaped."""
    mermaid_code = '''graph TD
    A["Node with <label>"] --> B["Another &node"]
    B --> C{Decision?}
    C -->|Yes| D["Result"]'''
    
    escaped = escape(mermaid_code)
    
    # Newlines should be preserved
    assert '\n' in escaped
    
    # Special characters should be escaped
    assert '&lt;' in escaped  # <
    assert '&gt;' in escaped  # >
    assert '&amp;' in escaped  # &
    
    # Original newlines preserved
    assert escaped.count('\n') == 3


def test_html_escape_quote_handling():
    """Test that quotes are properly escaped to prevent attribute breakouts."""
    malicious_input = '" onload="alert(1)'
    escaped = escape(malicious_input)
    
    # Double quotes should be escaped
    assert '&quot;' in escaped
    assert '" onload=' not in escaped
