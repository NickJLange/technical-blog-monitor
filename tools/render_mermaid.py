import sys
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

async def render_mermaid(input_path: Path, output_path: Path):
    with open(input_path, 'r') as f:
        mermaid_code = f.read()

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{ margin: 0; padding: 20px; background: white; }}
            .mermaid {{ display: flex; justify-content: center; }}
        </style>
    </head>
    <body>
        <pre class="mermaid">
{mermaid_code}
        </pre>
        <script type="module">
            import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
            mermaid.initialize({{ startOnLoad: true, theme: 'default' }});
        </script>
    </body>
    </html>
    """

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html_content)
        
        # Wait for mermaid to render
        try:
            # Wait for the svg to appear inside the pre class="mermaid" (mermaid replaces the text)
            # Actually mermaid replaces <pre> or inserts <svg> after/inside.
            # Usually it replaces the element or appends. 
            # Let's wait for an SVG to be present.
            await page.wait_for_selector('.mermaid svg', state='visible', timeout=10000)
            
            # Get the element to screenshot
            params = await page.locator('.mermaid').bounding_box()
            
            # Add a little padding
            if params:
                await page.locator('.mermaid').screenshot(path=str(output_path))
                print(f"Successfully rendered {output_path}")
            else:
                print(f"Could not find mermaid element bounding box")
                
        except Exception as e:
            print(f"Error rendering: {e}")
            # Debug: save html
            await page.screenshot(path=f"{output_path}.error.png")
        
        await browser.close()

async def main():
    if len(sys.argv) < 3:
        print("Usage: python render_mermaid.py <input.mmd> <output.png>")
        sys.exit(1)
        
    input_file = Path(sys.argv[1])
    output_file = Path(sys.argv[2])
    
    if not input_file.exists():
        print(f"Input file not found: {input_file}")
        sys.exit(1)
        
    await render_mermaid(input_file, output_file)

if __name__ == "__main__":
    asyncio.run(main())
