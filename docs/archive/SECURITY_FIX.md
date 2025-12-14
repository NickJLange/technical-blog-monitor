# Security Fix: HTML Injection Prevention in render_mermaid.py

## Vulnerability

**File:** `tools/render_mermaid.py` (lines 6-31)

**Issue:** Raw mermaid source code was embedded directly into the HTML `<pre>` tag without proper escaping, allowing malicious content to break out and inject arbitrary HTML/JavaScript.

### Attack Vector Example

A malicious `.mmd` file containing:
```
</pre><script>alert('XSS')</script><pre>
```

Would result in **unescaped HTML (vulnerable)**:
```html
<pre class="mermaid">
</pre><script>alert('XSS')</script><pre>
</pre>
```

This allows the script tag to execute outside the `<pre>` element.

## Fix Applied

### Changes Made

1. **Import HTML escape function** (line 3):
   ```python
   from html import escape
   ```

2. **Escape mermaid code after reading** (lines 11-13):
   ```python
   # HTML-escape the mermaid code to prevent injection attacks
   # This ensures characters like <, >, &, " are encoded while preserving newlines
   escaped_mermaid_code = escape(mermaid_code)
   ```

3. **Use escaped variable in template** (line 28):
   ```python
   {escaped_mermaid_code}  # Instead of {mermaid_code}
   ```

### How It Works

The `html.escape()` function encodes dangerous characters:
- `<` → `&lt;`
- `>` → `&gt;`
- `&` → `&amp;`
- `"` → `&quot;`
- `'` → `&#x27;` (optional)

**Newlines are preserved**, so the mermaid diagram still renders correctly.

### Example After Fix

The same malicious `.mmd` file would now result in **properly escaped HTML (safe)**:
```html
<pre class="mermaid">
&lt;/pre&gt;&lt;script&gt;alert('XSS')&lt;/script&gt;&lt;pre&gt;
</pre>
```

This displays the escaped text harmlessly instead of executing any code.

## Testing

Added comprehensive security test suite in `monitor/tests/test_render_mermaid_security.py`:

- ✅ Prevents closing `</pre>` tag breakout
- ✅ Escapes `<script>` tags
- ✅ Escapes event handlers
- ✅ Preserves ampersands in diagrams
- ✅ Preserves valid mermaid syntax
- ✅ Escapes quotes in attributes

All 6 security tests pass.

## Standards

- Uses Python's built-in `html.escape()` function (standard library)
- Follows OWASP recommendations for output encoding
- No external dependencies required
- Compatible with all Python 3.x versions

## References

- [OWASP Output Encoding Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html)
- [Python html.escape() documentation](https://docs.python.org/3/library/html.html#html.escape)
